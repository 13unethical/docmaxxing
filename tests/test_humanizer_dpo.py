"""DPO pairs from Turnitin labels of humanizer candidates."""

from __future__ import annotations

from humanizer_student import dpo
from services.humanizer_engine import student_humanizer


def _row(essay, source, text, frac):
    return {"essay": essay, "source": source, "text": text, "ai_frac": frac}


def test_system_prompt_matches_production():
    for level in (8, 10):
        assert dpo.system_prompt(level) == student_humanizer.system_prompt(level)


def test_pairs_join_clean_and_flagged_candidates_of_one_source():
    rows = [
        _row("e1", "src a", "a clean", 0.0),
        _row("e1", "src a", "a flagged", 0.84),
        _row("e1", "src a", "a half", 0.3),
        _row("e1", "src b", "b clean", 0.05),
        _row("e1", "src b", "b clean 2", 0.0),
        _row("e2", "src c", "c flagged", 0.9),
        _row("e2", "src c", "c clean", 0.02),
        _row("e2", "src c", "c clean again", 0.0),
    ]
    pairs = dpo.build_pairs(rows, max_per_source=4)
    assert {(p["chosen"], p["rejected"]) for p in pairs} == {
        ("a clean", "a flagged"), ("c clean", "c flagged"), ("c clean again", "c flagged"),
    }
    assert len(dpo.build_pairs(rows, max_per_source=1)) == 2


def test_judge_scores_keep_weak_or_padded_rewrites_out_of_chosen_and_reject_weak_clean_ones():
    src = "one two three four five six seven eight nine ten"
    padded = " ".join(["word"] * 14)
    rows = [
        _row("e1", src, "good clean", 0.0),
        _row("e1", src, "garbled clean", 0.0),
        _row("e1", src, padded, 0.0),
        _row("e1", src, "flagged", 0.9),
        _row("e1", src, "unjudged clean", 0.0),
    ]
    quality = {"good clean": (5, 4), "garbled clean": (4, 2), padded: (5, 5), "flagged": (5, 5)}
    pairs = dpo.build_pairs(rows, max_per_source=10, quality=quality)
    assert {(p["chosen"], p["rejected"]) for p in pairs} == {
        ("good clean", "flagged"), ("good clean", "garbled clean"),
    }
    assert [p["rejected"] for p in dpo.build_pairs(rows, max_per_source=1, quality=quality)] == ["flagged"]
    assert len(dpo.build_pairs(rows, max_per_source=10, quality=quality, max_weak_per_source=0)) == 1


def test_split_keeps_each_essay_on_one_side():
    pairs = [{"essay": f"e{i}", "source": "s", "chosen": "c", "rejected": "r"} for i in range(200)]
    train, val = dpo.split_by_essay(pairs, val_share=0.1)
    assert len(train) + len(val) == 200
    assert 5 <= len(val) <= 40
    assert not {p["essay"] for p in train} & {p["essay"] for p in val}
