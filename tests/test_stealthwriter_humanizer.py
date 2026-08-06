"""Tests for StealthWriter Legacy 5.1 assignment humanizer."""

from __future__ import annotations

from services.browser.providers.stealthwriter import (
    ASSIGNMENT_STEALTHWRITER_LEVEL,
    DEFAULT_STEALTHWRITER_MODEL,
    _model_already_selected,
    _model_match_labels,
)
from services.humanizer_engine.stealthwriter_humanizer import StealthWriterTextHumanizer


class _FakePage:
    def __init__(self, label: str) -> None:
        self._label = label

    def evaluate(self, *_args, **_kwargs):
        return self._label


def test_default_model_is_legacy_5_1():
    assert DEFAULT_STEALTHWRITER_MODEL == "Legacy 5.1"


def test_assignment_default_level_is_10():
    assert ASSIGNMENT_STEALTHWRITER_LEVEL == 10
    assert StealthWriterTextHumanizer().level == 10


def test_model_match_labels_include_ghost_alias():
    labels = _model_match_labels("Legacy 5.1")
    assert "Legacy 5.1" in labels
    assert "Ghost 5.1" in labels
    assert "5.1" in labels


def test_model_already_selected_accepts_ghost_label():
    assert _model_already_selected(_FakePage("Ghost 5.1"), "Legacy 5.1")
    assert _model_already_selected(_FakePage("Legacy 5.1"), "Legacy 5.1")
    assert not _model_already_selected(_FakePage("Ghost 5.2 Mini"), "Legacy 5.1")


def test_stealthwriter_humanizer_passes_legacy_model():
    calls: list[dict] = []

    def fake_humanize(text: str, *, model: str | None = None, level: int | None = None):
        calls.append({"text": text, "model": model, "level": level})
        return {"success": True, "humanized_text": f"human::{text}"}

    humanizer = StealthWriterTextHumanizer(humanize_fn=fake_humanize)
    sample = (
        "This paragraph is long enough to trigger StealthWriter humanization "
        "because it exceeds the minimum character threshold used by the engine."
    )
    out = humanizer.humanize(sample)
    assert out.startswith("human::")
    assert calls and calls[0]["model"] == "Legacy 5.1"
    assert calls[0]["level"] == 10


def test_stealthwriter_humanizer_chunks_long_input():
    calls: list[str] = []

    def fake_humanize(text: str, *, model: str | None = None, level: int | None = None):
        calls.append(text)
        return {"success": True, "humanized_text": text[::-1]}

    humanizer = StealthWriterTextHumanizer(humanize_fn=fake_humanize, max_words=20)
    words = " ".join(f"word{i}" for i in range(45))
    # Pad so MIN_HUMANIZE_CHARS is satisfied even on short chunks after join.
    text = f"{words}. Extra padding so character length clears the minimum gate."
    humanizer.humanize(text)
    assert len(calls) >= 2


def test_stealthwriter_humanizer_raises_on_failure():
    def fake_humanize(text: str, *, model: str | None = None, level: int | None = None):
        return {"success": False, "error": "LOGIN_REQUIRED"}

    humanizer = StealthWriterTextHumanizer(humanize_fn=fake_humanize)
    sample = (
        "This paragraph is long enough to trigger StealthWriter humanization "
        "because it exceeds the minimum character threshold used by the engine."
    )
    try:
        humanizer.humanize(sample)
        raised = False
    except ValueError as exc:
        raised = True
        assert "LOGIN_REQUIRED" in str(exc)
    assert raised


def test_stealthwriter_humanizer_retries_then_raises_on_no_change():
    calls = {"n": 0}

    def fake_humanize(text: str, *, model: str | None = None, level: int | None = None):
        calls["n"] += 1
        return {
            "success": False,
            "error": "NO_CHANGE",
            "message": "daily humanization limit is likely reached",
        }

    humanizer = StealthWriterTextHumanizer(humanize_fn=fake_humanize)
    sample = (
        "This paragraph is long enough to trigger StealthWriter humanization "
        "because it exceeds the minimum character threshold used by the engine."
    )
    try:
        humanizer.humanize(sample)
        raised = False
    except ValueError as exc:
        raised = True
        assert "limit" in str(exc).lower() or "NO_CHANGE" in str(exc)
    assert raised
    assert calls["n"] == 3


def test_stealthwriter_humanizer_rejects_identical_output():
    def fake_humanize(text: str, *, model: str | None = None, level: int | None = None):
        return {"success": True, "humanized_text": text}

    humanizer = StealthWriterTextHumanizer(humanize_fn=fake_humanize)
    sample = (
        "This paragraph is long enough to trigger StealthWriter humanization "
        "because it exceeds the minimum character threshold used by the engine."
    )
    try:
        humanizer.humanize(sample)
        raised = False
    except ValueError:
        raised = True
    assert raised
