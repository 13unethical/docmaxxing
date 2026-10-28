import importlib.util
import json
import sys
from pathlib import Path

from humanizer_student.data import fit_to_length, level_of, to_prompt_completion
from humanizer_student.evaluate import score_predictions
from humanizer_student.metrics import chrf, compare, score_rewrite

ROOT = Path(__file__).resolve().parents[1]


class FakeTokenizer:
    eos_token = "<|im_end|>"

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt, enable_thinking):
        assert not tokenize and add_generation_prompt and not enable_thinking
        body = "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages)
        return body + "<|im_start|>assistant\n"

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": text.split()}


def _row(source="One two three.", target="Uno dos tres.", level=6):
    return {
        "messages": [
            {"role": "system", "content": f"Rewrite it. Rewrite strength: {level}/10."},
            {"role": "user", "content": source},
            {"role": "assistant", "content": target},
        ]
    }


def test_prompt_completion_keeps_target_out_of_prompt():
    pair = to_prompt_completion(_row(), FakeTokenizer())
    assert pair["prompt"].endswith("<|im_start|>assistant\n")
    assert "Uno dos tres." not in pair["prompt"] and "One two three." in pair["prompt"]
    assert pair["completion"] == "Uno dos tres.<|im_end|>"
    assert level_of(_row(level=10)) == 10


def test_too_long_pairs_are_dropped_not_clipped():
    tok = FakeTokenizer()
    short = to_prompt_completion(_row(), tok)
    long = to_prompt_completion(_row(source="w " * 500, target="v " * 500), tok)
    kept, dropped = fit_to_length([short, long], tok, max_length=100)
    assert kept == [short] and dropped == 1


def test_score_rewrite_checks_structure_and_markers():
    source = "Rates rose 12% in 2020 (Smith, 2019).\n\nThen they fell back sharply."
    good = "In 2020 rates climbed by 12% (Smith, 2019).\n\nAfterwards they dropped again quickly."
    merged = "Rates went up 12% in 2020 and then fell."
    row = score_rewrite(source, good, teacher=good)
    assert row["paragraphs_match"] and row["citations_kept"] == 1.0 and row["numbers_kept"] == 1.0
    assert row["chrf_vs_teacher"] == 100.0 and not row["unchanged"]
    bad = score_rewrite(source, merged)
    assert not bad["paragraphs_match"] and bad["citations_kept"] == 0.0
    assert score_rewrite(source, source)["unchanged"]
    assert score_rewrite(source, "## Intro\n\n" + good)["heading_leak"]


def test_chrf_orders_closer_rewrites_higher():
    ref = "The economy grew quickly during the decade."
    assert chrf(ref, ref) == 100.0
    assert chrf("The economy grew fast in the decade.", ref) > chrf("Cats sleep a lot.", ref)


def test_compare_reports_student_and_teacher_per_level(tmp_path):
    examples = [
        {"index": 0, "level": 4, "source": "a b c d.\n\ne f g.", "teacher": "a b x d.\n\ne f y.", "prediction": "a b x d.\n\ne f y."},
        {"index": 1, "level": 8, "source": "a b c d.", "teacher": "w x y z.", "prediction": ""},
    ]
    path = tmp_path / "predictions.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in examples))
    report = score_predictions(path)
    assert list(report) == ["all", "level_4", "level_8"]
    assert report["all"]["student"]["n"] == 2 and report["all"]["student"]["empty"] == 0.5
    assert report["level_4"]["student"]["chrf_vs_teacher"] == 100.0
    assert report["level_8"]["teacher"]["empty"] == 0.0
    assert report == compare(examples)


def test_train_cli_maps_flags_to_config():
    spec = importlib.util.spec_from_file_location("train_cli", ROOT / "scripts/train_humanizer_student.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["train_cli"] = mod
    spec.loader.exec_module(mod)
    cfg = mod.parse_config(["--base-model", "Qwen/Qwen3-4B", "--limit", "20", "--no-load-in-4bit", "--epochs", "1"])
    assert cfg.base_model == "Qwen/Qwen3-4B" and cfg.limit == 20 and cfg.load_in_4bit is False and cfg.epochs == 1.0
    assert mod.parse_config([]).max_length == 4096
