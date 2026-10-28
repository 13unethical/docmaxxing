"""QLoRA SFT of a chat model on ``section_sft`` (needs a CUDA GPU and requirements-student.txt)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from humanizer_student.data import fit_to_length, read_rows, to_prompt_completion

LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


@dataclass
class TrainConfig:
    base_model: str = "Qwen/Qwen3-8B"
    data_dir: str = "data/humanizer_training/section_sft"
    output_dir: str = "data/humanizer_training/student_runs/qwen3_8b_lora_v1"
    max_length: int = 4096
    epochs: float = 2.0
    batch_size: int = 2
    grad_accum: int = 8
    learning_rate: float = 1e-4
    warmup_ratio: float = 0.03
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    load_in_4bit: bool = True
    eval_steps: int = 50
    seed: int = 51
    limit: int | None = None
    lora_targets: list[str] = field(default_factory=lambda: list(LORA_TARGETS))


def load_pairs(cfg: TrainConfig, tokenizer: Any) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    data_dir = Path(cfg.data_dir)
    stats: dict[str, int] = {}
    splits = []
    for name in ("train", "val"):
        rows = read_rows(data_dir / f"{name}.jsonl", limit=cfg.limit)
        pairs, dropped = fit_to_length((to_prompt_completion(r, tokenizer) for r in rows), tokenizer, cfg.max_length)
        stats[f"{name}_rows"] = len(pairs)
        stats[f"{name}_dropped_too_long"] = dropped
        splits.append(pairs)
    return splits[0], splits[1], stats


def train(cfg: TrainConfig) -> dict[str, Any]:
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(cfg.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    train_pairs, val_pairs, stats = load_pairs(cfg, tokenizer)

    bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    dtype = torch.bfloat16 if bf16 else torch.float16
    quant = (
        BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=dtype,
        )
        if cfg.load_in_4bit
        else None
    )
    model = AutoModelForCausalLM.from_pretrained(
        cfg.base_model, quantization_config=quant, torch_dtype=dtype, device_map="auto", attn_implementation="sdpa"
    )
    model.config.use_cache = False

    args = SFTConfig(
        output_dir=str(out / "checkpoints"),
        num_train_epochs=cfg.epochs,
        per_device_train_batch_size=cfg.batch_size,
        per_device_eval_batch_size=cfg.batch_size,
        gradient_accumulation_steps=cfg.grad_accum,
        learning_rate=cfg.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=cfg.warmup_ratio,
        max_grad_norm=1.0,
        bf16=bf16,
        fp16=not bf16,
        gradient_checkpointing=True,
        optim="paged_adamw_8bit" if cfg.load_in_4bit else "adamw_torch",
        max_length=cfg.max_length,
        packing=False,
        completion_only_loss=True,
        eval_strategy="steps",
        eval_steps=cfg.eval_steps,
        save_strategy="steps",
        save_steps=cfg.eval_steps,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=5,
        report_to="none",
        seed=cfg.seed,
        data_seed=cfg.seed,
    )
    trainer = SFTTrainer(
        model=model,
        args=args,
        train_dataset=Dataset.from_list(train_pairs),
        eval_dataset=Dataset.from_list(val_pairs),
        processing_class=tokenizer,
        peft_config=LoraConfig(
            r=cfg.lora_r,
            lora_alpha=cfg.lora_alpha,
            lora_dropout=cfg.lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=cfg.lora_targets,
        ),
    )
    result = trainer.train()
    adapter_dir = out / "adapter"
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    summary = {
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "config": asdict(cfg),
        "data": stats,
        "train_loss": result.training_loss,
        "eval": trainer.evaluate(),
        "adapter_dir": str(adapter_dir),
    }
    (out / "train_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
