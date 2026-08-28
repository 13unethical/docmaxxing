"""API error message mapping for UI."""

from __future__ import annotations

from pathlib import Path


def test_user_message_uses_sentence_in_error_field():
    js = Path(__file__).resolve().parents[1] / "static" / "api-errors.js"
    text = js.read_text(encoding="utf-8")
    assert "if (code && !isInternalCode(code)) return code" in text
