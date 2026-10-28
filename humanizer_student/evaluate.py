"""Generate student rewrites for a held-out split and compare them with StealthWriter."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from humanizer_student.data import build_prompt, level_of, read_rows, split_messages
from humanizer_student.metrics import compare


def read_predictions(path: Path) -> list[dict[str, Any]]:
    return read_rows(path) if path.is_file() else []


def score_predictions(path: Path) -> dict[str, Any]:
    return compare(read_predictions(path))


def generate_predictions(
    *,
    base_model: str,
    adapter_dir: str | None,
    split_path: Path,
    out_path: Path,
    limit: int | None = None,
    batch_size: int = 4,
    temperature: float = 0.0,
    load_in_4bit: bool = True,
) -> int:
    """Append predictions to ``out_path``; rows already there are skipped (resumable)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    rows = read_rows(split_path, limit=limit)
    done = {p["index"] for p in read_predictions(out_path)}
    todo = [(i, r) for i, r in enumerate(rows) if i not in done]
    if not todo:
        return 0

    tokenizer = AutoTokenizer.from_pretrained(adapter_dir or base_model)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    dtype = torch.bfloat16 if bf16 else torch.float16
    quant = (
        BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype)
        if load_in_4bit
        else None
    )
    model = AutoModelForCausalLM.from_pretrained(
        base_model, quantization_config=quant, torch_dtype=dtype, device_map="auto"
    )
    if adapter_dir:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter_dir)
    model.eval()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out_path.open("a", encoding="utf-8") as fh:
        for start in range(0, len(todo), batch_size):
            batch = todo[start : start + batch_size]
            prompts, sources, teachers = [], [], []
            for _, row in batch:
                messages, teacher = split_messages(row)
                prompts.append(build_prompt(tokenizer, messages))
                sources.append(messages[-1]["content"])
                teachers.append(teacher)
            enc = tokenizer(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
            longest_source = max(len(tokenizer(s, add_special_tokens=False)["input_ids"]) for s in sources)
            started = time.monotonic()
            with torch.no_grad():
                generated = model.generate(
                    **enc,
                    max_new_tokens=int(longest_source * 2) + 64,
                    do_sample=temperature > 0,
                    temperature=temperature if temperature > 0 else None,
                    top_p=0.9 if temperature > 0 else None,
                    pad_token_id=tokenizer.pad_token_id,
                )
            elapsed = (time.monotonic() - started) / len(batch)
            texts = tokenizer.batch_decode(generated[:, enc["input_ids"].shape[1] :], skip_special_tokens=True)
            for (index, row), source, teacher, text in zip(batch, sources, teachers, texts):
                fh.write(
                    json.dumps(
                        {
                            "index": index,
                            "level": level_of(row),
                            "source": source,
                            "teacher": teacher,
                            "prediction": text.strip(),
                            "seconds": round(elapsed, 2),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                written += 1
            fh.flush()
    return written
