"""Detector-based selection of teacher targets for student training (no GPU)."""

from __future__ import annotations

import pytest

from humanizer_student.filtering import select_rows, target_text, word_windows


def _row(level: int, target: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": f"Rewrite it. Rewrite strength: {level}/10."},
            {"role": "user", "content": "source"},
            {"role": "assistant", "content": target},
        ]
    }


def test_word_windows_merge_short_tail():
    text = " ".join(f"w{i}" for i in range(250))
    sizes = [n for _, n in word_windows(text)]
    assert sizes == [110, 140]
    assert [n for _, n in word_windows(" ".join(["x"] * 260))] == [110, 110, 40]
    assert [n for _, n in word_windows("a b c")] == [3]
    assert list(word_windows("")) == []


def test_select_rows_drops_worst_share_within_each_level():
    rows = [_row(10, f"t{i}") for i in range(4)] + [_row(4, f"u{i}") for i in range(2)]
    scores = [0.9, 0.1, 0.5, 0.2, 0.8, 0.3]
    kept, stats = select_rows(rows, scores, drop_share=0.5)
    assert [target_text(r) for r in kept] == ["t1", "t3", "u1"]
    assert stats["10"] == {"rows": 4, "kept": 2, "mean_p": 0.425, "kept_mean_p": 0.15, "cutoff_p": 0.2}
    assert stats["4"]["kept"] == 1


def test_select_rows_rejects_misaligned_scores():
    with pytest.raises(ValueError):
        select_rows([_row(8, "a")], [0.1, 0.2], drop_share=0.3)
