"""Chat rows from ``section_sft`` turned into prompt/completion text for one tokenizer."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

_LEVEL = re.compile(r"Rewrite strength:\s*(\d+)/10")


def read_rows(path: Path | str, *, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
                if limit and len(rows) >= limit:
                    break
    return rows


def split_messages(row: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    """(prompt messages, assistant target) of one ``section_sft`` row."""
    messages = list(row["messages"])
    if not messages or messages[-1]["role"] != "assistant":
        raise ValueError("row must end with an assistant message")
    return messages[:-1], messages[-1]["content"]


def level_of(row: dict[str, Any]) -> int | None:
    system = next((m["content"] for m in row["messages"] if m["role"] == "system"), "")
    match = _LEVEL.search(system)
    return int(match.group(1)) if match else None


def build_prompt(tokenizer: Any, messages: list[dict[str, str]]) -> str:
    """Chat-templated prompt ending at the assistant turn; Qwen3 thinking stays off."""
    return tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )


def to_prompt_completion(row: dict[str, Any], tokenizer: Any) -> dict[str, str]:
    """Plain-text pair so the trainer computes loss on the completion only."""
    messages, target = split_messages(row)
    eos = tokenizer.eos_token or ""
    completion = target if target.endswith(eos) else target + eos
    return {"prompt": build_prompt(tokenizer, messages), "completion": completion}


def fit_to_length(
    pairs: Iterable[dict[str, str]], tokenizer: Any, max_length: int
) -> tuple[list[dict[str, str]], int]:
    """Drop pairs longer than ``max_length`` tokens instead of clipping teacher text."""
    kept: list[dict[str, str]] = []
    dropped = 0
    for pair in pairs:
        size = len(tokenizer(pair["prompt"] + pair["completion"], add_special_tokens=False)["input_ids"])
        if size > max_length:
            dropped += 1
        else:
            kept.append(pair)
    return kept, dropped
