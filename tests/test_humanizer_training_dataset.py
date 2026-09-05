from __future__ import annotations

import ast
import json
from pathlib import Path

from services.humanizer_training.config import DatasetBuildConfig, TrainingExample
from services.humanizer_training.dedupe import (
    dedupe_examples,
    make_pair_hash,
    make_source_group_key,
    make_source_hash,
)
from services.humanizer_training.filters import evaluate_example
from services.humanizer_training.pipeline import build_dataset
from services.humanizer_training.split import split_by_source_group


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _all_dataset_rows(output_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for name in ("train.jsonl", "validation.jsonl", "test.jsonl"):
        rows.extend(_read_jsonl(output_dir / name))
    return rows


def _as_example(source: str, target: str) -> TrainingExample:
    source_norm = source.strip()
    target_norm = target.strip()
    return TrainingExample(
        source_text=source_norm,
        target_text=target_norm,
        source_type="synthetic",
        language="en",
        domain="academic",
        word_count_source=len(source_norm.split()),
        word_count_target=len(target_norm.split()),
        quality_flags=[],
        dedupe_key=make_pair_hash(source_norm, target_norm),
        source_hash=make_source_hash(source_norm),
        source_group=make_source_group_key(source_norm),
        metadata={},
    )


def test_offline_builder_filters_dedupes_and_exports(tmp_path: Path):
    input_path = tmp_path / "synthetic.jsonl"
    records = [
        {"source_type": "synthetic", "source_text": "", "target_text": "valid target text that is long enough"},
        {"source_type": "synthetic", "source_text": "valid source text that is long enough", "target_text": ""},
        {
            "source_type": "synthetic",
            "source_text": "This source sentence stays exactly the same for unchanged detection in the pipeline.",
            "target_text": "This source sentence stays exactly the same for unchanged detection in the pipeline.",
        },
        {
            "source_type": "synthetic",
            "source_text": " ".join(["source"] * 20),
            "target_text": "short text",
        },
        {
            "source_type": "public",
            "source_text": "Prior studies (Smith, 2021) report measurable gains in academic outcomes over semesters.",
            "target_text": "Prior studies report measurable gains in academic outcomes across multiple semesters in context.",
        },
        {
            "source_type": "public",
            "source_text": "The policy improved completion rates by 45% in 2024 based on monitored institutional records.",
            "target_text": "The policy improved completion rates significantly based on monitored institutional records and review.",
        },
        {
            "source_type": "synthetic",
            "source_text": "Duplicate source record with enough words for acceptance and deterministic pipeline processing.",
            "target_text": "Duplicate target record with enough words for acceptance and deterministic pipeline processing.",
        },
        {
            "source_type": "synthetic",
            "source_text": "Duplicate source record with enough words for acceptance and deterministic pipeline processing.",
            "target_text": "Duplicate target record with enough words for acceptance and deterministic pipeline processing.",
        },
        {
            "source_type": "synthetic",
            "source_text": "Shared source text should not appear in multiple splits because grouping must prevent leakage.",
            "target_text": "Shared source text should not appear across shards because grouping prevents leakage by design.",
        },
        {
            "source_type": "synthetic",
            "source_text": "Shared source text should not appear in multiple splits because grouping must prevent leakage.",
            "target_text": "Alternative rewrite for same source text that should be removed by source-level deduplication.",
        },
    ]
    for idx in range(18):
        records.append(
            {
                "source_type": "synthetic",
                "source_text": f"Sample source {idx} contains enough academic words for stable filtering and split safety checks.",
                "target_text": f"Sample target {idx} rewrites the academic wording while preserving meaning and structural coherence.",
            }
        )

    input_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    manifest = build_dataset(
        DatasetBuildConfig(
            input_path=input_path,
            output_dir=output_dir,
            include_database=False,
            min_words=8,
            max_words=200,
            seed=7,
        )
    )

    assert (output_dir / "manifest.json").is_file()
    assert manifest["rejection_reasons"]["EMPTY_SOURCE"] >= 1
    assert manifest["rejection_reasons"]["EMPTY_TARGET"] >= 1
    assert manifest["rejection_reasons"]["UNCHANGED"] >= 1
    assert manifest["rejection_reasons"]["LENGTH_OUTLIER"] >= 1
    assert manifest["rejected_count"] == 4
    assert manifest["dedupe"]["dropped_exact_pair"] >= 1
    assert manifest["dedupe"]["dropped_same_source"] >= 1
    assert manifest["train_count"] + manifest["validation_count"] + manifest["test_count"] == manifest["accepted_count"]

    rows = _all_dataset_rows(output_dir)
    assert rows
    # JSONL structure is training-only fields.
    for row in rows:
        assert set(row.keys()) == {
            "dedupe_key",
            "domain",
            "language",
            "quality_flags",
            "source_text",
            "source_type",
            "target_text",
            "word_count_source",
            "word_count_target",
        }

    # Citation/numeric structural checks are flagged deterministically.
    all_flags = [flag for row in rows for flag in row["quality_flags"]]
    assert "CITATION_MISMATCH" in all_flags
    assert "NUMERIC_MISMATCH" in all_flags

    # Same source text never crosses split files.
    source_to_split: dict[str, str] = {}
    for split_name in ("train", "validation", "test"):
        for row in _read_jsonl(output_dir / f"{split_name}.jsonl"):
            source = row["source_text"]
            prev = source_to_split.get(source)
            if prev is None:
                source_to_split[source] = split_name
            else:
                assert prev == split_name


def test_db_rows_default_not_eligible_without_column(tmp_path: Path, monkeypatch):
    from services.economy import db as economy_db

    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    with economy_db.connect() as conn:
        conn.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
            ("u@example.com", "User", "x"),
        )
        user_id = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()["id"])
        conn.execute(
            "INSERT INTO humanizer_dataset_logs (user_id, source, original_text, humanized_text) VALUES (?, ?, ?, ?)",
            (user_id, "standalone", "source text enough words here yes", "target text enough words here yes"),
        )

    out_dir = tmp_path / "out-db"
    manifest = build_dataset(
        DatasetBuildConfig(
            input_path=None,
            output_dir=out_dir,
            include_database=True,
        )
    )
    assert manifest["accepted_count"] == 0
    assert _all_dataset_rows(out_dir) == []


def test_training_package_not_imported_by_app_entrypoint():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
    assert not any(name.startswith("services.humanizer_training") for name in imported)


def test_year_mismatch_uses_full_year_tokens():
    same_year = evaluate_example(
        "The study was conducted in 2021 with a longitudinal design and robust controls.",
        "The study was conducted in 2021 using a longitudinal design with robust controls.",
        min_words=8,
        max_words=5000,
    )
    assert "YEAR_MISMATCH" not in same_year.quality_flags

    changed_year = evaluate_example(
        "The study was conducted in 2021 with a longitudinal design and robust controls.",
        "The study was conducted in 2024 using a longitudinal design with robust controls.",
        min_words=8,
        max_words=5000,
    )
    assert "YEAR_MISMATCH" in changed_year.quality_flags
    assert "NUMERIC_MISMATCH" in changed_year.quality_flags


def test_url_mismatch_is_flag_not_reject():
    verdict = evaluate_example(
        "See https://example.com/report for details in the official methodology notes and appendix.",
        "See the report for details in the official methodology notes and appendix for the discussion.",
        min_words=8,
        max_words=5000,
    )
    assert verdict.accepted is True
    assert "URL_MISMATCH" in verdict.quality_flags


def test_dedupe_keeps_distinct_academic_texts_with_similar_terminology():
    left = (
        "Academic integrity policy in higher education requires citation transparency, rubric alignment, "
        "methodological clarity, ethical sampling, longitudinal evidence synthesis, and theory-driven argumentation "
        "across institutional contexts with documented constraints and reflective evaluation practices."
    )
    right = (
        "Higher education policy analysis examines citation transparency, rubric alignment, methodological clarity, "
        "ethical sampling, longitudinal evidence synthesis, and theory-driven interpretation, but evaluates governance "
        "trade-offs, implementation barriers, and stakeholder incentives under different administrative constraints."
    )
    outcome = dedupe_examples([_as_example(left, left + " rewritten"), _as_example(right, right + " rewritten")])
    assert len(outcome.accepted) == 2
    assert outcome.dropped_near_source == 0


def test_dedupe_drops_near_duplicate_cosmetic_variation():
    base = (
        "This academic paragraph explains the policy evaluation framework with methodological transparency, "
        "structured evidence review, explicit assumptions, and reproducible interpretation across multiple cohorts "
        "while preserving references to implementation boundaries and measurable outcomes in the final section."
    )
    cosmetic = base.replace("reproducible interpretation", "reproducible interpretations")
    outcome = dedupe_examples([_as_example(base, base + " rewritten"), _as_example(cosmetic, cosmetic + " rewritten")])
    assert len(outcome.accepted) == 1
    assert outcome.dropped_near_source == 1


def test_dedupe_drops_exact_duplicate_pair():
    source = (
        "Exact duplicate sample contains sufficient academic wording to verify pair-level hash deduplication logic."
    )
    target = "Rewritten duplicate sample contains sufficient academic wording to verify pair-level hash deduplication logic."
    outcome = dedupe_examples([_as_example(source, target), _as_example(source, target)])
    assert len(outcome.accepted) == 1
    assert outcome.dropped_exact_pair == 1


def test_tiny_dataset_split_behavior_expected():
    topics = ["algebra", "biology", "chemistry", "design"]
    examples = [
        _as_example(
            f"Tiny sample source about {topic} contains enough words for deterministic splitting behavior and leak-safe grouping.",
            f"Tiny sample target about {topic} preserves meaning for deterministic splitting behavior and leak-safe grouping.",
        )
        for topic in topics
    ]
    splits = split_by_source_group(examples, config=DatasetBuildConfig(seed=17))
    assert len(splits["train"]) == 3
    assert len(splits["validation"]) == 0
    assert len(splits["test"]) == 1


def test_split_uses_all_shards_when_groups_are_sufficient():
    topics = [
        "algebra", "biology", "chemistry", "design", "economics", "finance",
        "geology", "history", "informatics", "journalism", "kinetics", "linguistics",
        "mathematics", "neuroscience", "oceanography", "philosophy", "quantum",
        "rhetoric", "sociology", "topology",
    ]
    examples = [
        _as_example(
            f"Sufficient groups sample source about {topic} includes enough academic context for leakage-safe split assignment.",
            f"Sufficient groups sample target about {topic} includes enough academic context for leakage-safe split assignment rewrite.",
        )
        for topic in topics
    ]
    splits = split_by_source_group(examples, config=DatasetBuildConfig(seed=17))
    assert len(splits["train"]) > 0
    assert len(splits["validation"]) > 0
    assert len(splits["test"]) > 0


def test_deterministic_pipeline_outputs_and_hash(tmp_path: Path):
    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "humanizer_training" / "synthetic_pairs.jsonl"
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    m1 = build_dataset(
        DatasetBuildConfig(
            input_path=fixture,
            output_dir=out1,
            include_database=False,
            seed=17,
        )
    )
    m2 = build_dataset(
        DatasetBuildConfig(
            input_path=fixture,
            output_dir=out2,
            include_database=False,
            seed=17,
        )
    )

    assert (out1 / "train.jsonl").read_text(encoding="utf-8") == (out2 / "train.jsonl").read_text(encoding="utf-8")
    assert (out1 / "validation.jsonl").read_text(encoding="utf-8") == (out2 / "validation.jsonl").read_text(encoding="utf-8")
    assert (out1 / "test.jsonl").read_text(encoding="utf-8") == (out2 / "test.jsonl").read_text(encoding="utf-8")
    assert m1["dataset_sha256"] == m2["dataset_sha256"]
    assert m1["files"].keys() == m2["files"].keys()


def test_manifest_is_stable_except_created_at_on_repeat_run(tmp_path: Path):
    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "humanizer_training" / "synthetic_pairs.jsonl"
    out = tmp_path / "same-out"
    m1 = build_dataset(
        DatasetBuildConfig(
            input_path=fixture,
            output_dir=out,
            include_database=False,
            seed=17,
        )
    )
    m2 = build_dataset(
        DatasetBuildConfig(
            input_path=fixture,
            output_dir=out,
            include_database=False,
            seed=17,
        )
    )
    m1_no_time = dict(m1)
    m2_no_time = dict(m2)
    m1_no_time.pop("created_at", None)
    m2_no_time.pop("created_at", None)
    assert m1_no_time == m2_no_time


def test_loader_skips_malformed_jsonl_and_unsupported_source_type(tmp_path: Path):
    input_path = tmp_path / "mixed.jsonl"
    lines = [
        "{not valid json",
        json.dumps(
            {
                "source_type": "unknown_type",
                "source_text": "Unsupported source type sample with enough words to be skipped gracefully.",
                "target_text": "Unsupported source type target with enough words to be skipped gracefully.",
            }
        ),
        json.dumps(
            {
                "source_type": "synthetic",
                "source_text": "Valid synthetic sample with enough words for successful inclusion in dataset output.",
                "target_text": "Valid synthetic rewrite with enough words for successful inclusion in dataset output.",
            }
        ),
    ]
    input_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = build_dataset(
        DatasetBuildConfig(
            input_path=input_path,
            output_dir=tmp_path / "out-mixed",
            include_database=False,
        )
    )
    assert manifest["accepted_count"] == 1

