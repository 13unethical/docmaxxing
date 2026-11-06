"""DPO of the student humanizer on Turnitin paragraph labels of its own candidates.

A pair is two candidates of the same source paragraph: one Turnitin left clean (chosen) and one it
flagged (rejected). Training starts from a merged model (e.g. v4) with a fresh LoRA; the reference
policy is that model without the adapter.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from humanizer_student.data import build_prompt
from humanizer_student.train import LORA_TARGETS

CHOSEN_MAX_FRAC = 0.1
REJECTED_MIN_FRAC = 0.5
# With judge scores, chosen candidates need at least this meaning and fluency (1-5) and at most this
# length relative to the source: pairs on Turnitin labels alone taught v5 to garble and pad its text.
CHOSEN_MIN_QUALITY = 4
CHOSEN_MAX_LENGTH = 1.3


def system_prompt(level: int) -> str:
    """Same text as services/humanizer_engine/student_humanizer.system_prompt."""
    return (
        "Rewrite the user's text so it reads like natural writing by a student. Keep the meaning, "
        "facts, numbers, names, in-text citations and paragraph breaks. Do not add headings, "
        f"comments or new content. Rewrite strength: {int(level)}/10."
    )


def build_pairs(rows: list[dict], *, max_per_source: int = 4, seed: int = 0,
                quality: dict[str, tuple[int, int]] | None = None, max_weak_per_source: int = 1) -> list[dict]:
    """(chosen, rejected) candidates per source paragraph from Turnitin label rows.

    ``quality``: candidate text -> (meaning, fluency) from a blind judge. When given, chosen candidates
    must also pass the quality and length bars, and up to ``max_weak_per_source`` pairs per source
    reject a clean candidate the judge scored below the bar; flagged rejected ones come first."""
    rng = random.Random(seed)
    groups: dict[tuple[str, str], dict[str, dict]] = {}
    for r in rows:
        groups.setdefault((r["essay"], r["source"]), {})[r["text"]] = r

    def weak(text: str) -> bool:
        q = (quality or {}).get(text)
        return q is not None and min(q) < CHOSEN_MIN_QUALITY

    def good(text: str, source: str) -> bool:
        if quality is None:
            return True
        q = quality.get(text)
        return (q is not None and min(q) >= CHOSEN_MIN_QUALITY
                and len(text.split()) <= CHOSEN_MAX_LENGTH * len(source.split()))

    pairs = []
    for (essay, source), cands in groups.items():
        clean = [c for c in cands.values() if c["ai_frac"] <= CHOSEN_MAX_FRAC and good(c["text"], source)]
        flagged = [c for c in cands.values() if c["ai_frac"] >= REJECTED_MIN_FRAC]
        weak_clean = [c for c in cands.values() if c["ai_frac"] < REJECTED_MIN_FRAC and weak(c["text"])]
        combos = [(c, f) for c in clean for f in flagged]
        rng.shuffle(combos)
        weak_combos = [(c, f) for c in clean for f in weak_clean]
        rng.shuffle(weak_combos)
        combos = combos[:max_per_source]
        combos += weak_combos[: min(max_weak_per_source, max_per_source - len(combos))]
        for c, f in combos:
            pairs.append({"essay": essay, "source": source, "chosen": c["text"], "rejected": f["text"]})
    return pairs


def split_by_essay(pairs: list[dict], val_share: float = 0.1) -> tuple[list[dict], list[dict]]:
    def is_val(essay: str) -> bool:
        return int(hashlib.sha1(essay.encode()).hexdigest(), 16) % 1000 < val_share * 1000

    return [p for p in pairs if not is_val(p["essay"])], [p for p in pairs if is_val(p["essay"])]


@dataclass
class DPOConfig:
    base_model: str
    data_dir: str
    output_dir: str
    level: int = 10
    beta: float = 0.1
    # NLL on the chosen text (RPO): keeps outputs fluent while preferences shift.
    rpo_alpha: float | None = None
    epochs: float = 2.0
    learning_rate: float = 2e-5
    batch_size: int = 4
    grad_accum: int = 4
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    max_length: int = 1536
    seed: int = 51


def _dataset(path: Path, tokenizer: Any, level: int) -> list[dict[str, str]]:
    eos = tokenizer.eos_token or ""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        p = json.loads(line)
        messages = [{"role": "system", "content": system_prompt(level)}, {"role": "user", "content": p["source"]}]
        out.append({"prompt": build_prompt(tokenizer, messages), "chosen": p["chosen"] + eos,
                    "rejected": p["rejected"] + eos})
    return out


def train_dpo(cfg: DPOConfig, callbacks: list[Any] | None = None) -> dict[str, Any]:
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from transformers.trainer_utils import get_last_checkpoint
    from trl import DPOConfig as TrlDPOConfig
    from trl import DPOTrainer

    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(cfg.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    train_rows = _dataset(Path(cfg.data_dir) / "pairs_train.jsonl", tokenizer, cfg.level)
    val_rows = _dataset(Path(cfg.data_dir) / "pairs_val.jsonl", tokenizer, cfg.level)
    model = AutoModelForCausalLM.from_pretrained(
        cfg.base_model, dtype=torch.bfloat16, device_map="auto", attn_implementation="sdpa"
    )
    model.config.use_cache = False
    args = TrlDPOConfig(
        output_dir=str(out / "checkpoints"),
        beta=cfg.beta,
        **({"loss_type": ["sigmoid", "sft"], "loss_weights": [1.0, cfg.rpo_alpha]} if cfg.rpo_alpha else {}),
        num_train_epochs=cfg.epochs,
        per_device_train_batch_size=cfg.batch_size,
        per_device_eval_batch_size=cfg.batch_size,
        gradient_accumulation_steps=cfg.grad_accum,
        learning_rate=cfg.learning_rate,
        lr_scheduler_type="cosine",
        warmup_steps=0.05,
        max_grad_norm=1.0,
        bf16=True,
        gradient_checkpointing=True,
        max_length=cfg.max_length,
        eval_strategy="steps",
        eval_steps=20,
        save_strategy="steps",
        save_steps=20,
        save_total_limit=2,
        logging_steps=5,
        report_to="none",
        seed=cfg.seed,
    )
    trainer = DPOTrainer(
        model=model,
        ref_model=None,
        args=args,
        train_dataset=Dataset.from_list(train_rows),
        eval_dataset=Dataset.from_list(val_rows),
        processing_class=tokenizer,
        peft_config=LoraConfig(
            r=cfg.lora_r, lora_alpha=cfg.lora_alpha, lora_dropout=cfg.lora_dropout, bias="none",
            task_type="CAUSAL_LM", target_modules=list(LORA_TARGETS),
        ),
        callbacks=callbacks,
    )
    checkpoints = out / "checkpoints"
    last = get_last_checkpoint(str(checkpoints)) if checkpoints.is_dir() else None
    result = trainer.train(resume_from_checkpoint=last)
    adapter_dir = out / "adapter"
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    summary = {
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "config": asdict(cfg),
        "pairs": {"train": len(train_rows), "val": len(val_rows)},
        "resumed_from": Path(last).name if last else "",
        "train_loss": result.training_loss,
        "eval": trainer.evaluate(),
        "adapter_dir": str(adapter_dir),
    }
    (out / "train_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    return summary
