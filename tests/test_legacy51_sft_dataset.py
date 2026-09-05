"""Tests for Legacy 5.1 SFT dataset builder (no browser / StealthWriter)."""

from __future__ import annotations

import json
from pathlib import Path

from services.humanizer_training.legacy51_sft import build_legacy51_sft


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def _eligible_record(doc_id: str, source: str, target: str, *, flag: str | None = None) -> dict:
    return {
        "document_id": doc_id,
        "source_text": source,
        "teacher_text": target,
        "teacher_provider": "stealthwriter_training",
        "teacher_model": "Legacy 5.1",
        "teacher_level": 8,
        "domain": "business",
        "document_type": "explanation",
        "language": "en",
        "quality_flags": [flag] if flag else [],
        "teacher_meta": {
            "requested_model": "Legacy 5.1",
            "verified_model": "Legacy 5.1",
            "ui_model_label": "Ghost 5.1 Legacy",
            "requested_level": 8,
            "verified_level": 8,
            "selection_verified": True,
            "last_successful_stage": "RESULT_EXTRACTED",
        },
    }


def test_legacy51_sft_build_preserves_target_and_splits(tmp_path: Path):
    root = tmp_path / "data"
    docs = root / "teacher_raw_documents" / "run_x" / "documents.jsonl"
    records = [
        _eligible_record(
            "doc-a",
            "## Introduction\n\nSource alpha about markets and incentives in detail enough for hashing.\n\n## Conclusion\n\nEnd alpha.",
            "## Introduction\n\nRewritten alpha about markets and incentives with extra clauses carefully.\n\n## Conclusion\n\nEnd alpha rewritten.",
        ),
        _eligible_record(
            "doc-b",
            "## Introduction\n\nSource beta discusses institutional theory and community dynamics carefully.\n\n## Conclusion\n\nEnd beta.",
            "## Introduction\n\nRewritten beta discusses institutional theory and community dynamics with hedges.\n\n## Conclusion\n\nEnd beta rewritten.",
            flag="PERCENT_MISMATCH",
        ),
        _eligible_record(
            "doc-dup",
            "## Introduction\n\nSource alpha about markets and incentives in detail enough for hashing.\n\n## Conclusion\n\nEnd alpha.",
            "## Introduction\n\nRewritten alpha about markets and incentives with extra clauses carefully.\n\n## Conclusion\n\nEnd alpha rewritten.",
        ),
        _eligible_record(
            "doc-empty",
            "",
            "nonempty",
        ),
    ]
    # Fix empty source record metadata still present — hard reject expected.
    records[3]["source_text"] = ""
    records[3]["teacher_text"] = "nonempty target text"
    _write_jsonl(docs, records)

    index = tmp_path / "eligible_pairs_index.jsonl"
    _write_jsonl(
        index,
        [
            {
                "sample_id": r["document_id"],
                "source_path": "teacher_raw_documents/run_x/documents.jsonl",
                "line_no": i,
                "run_dir": "teacher_raw_documents/run_x",
                "provider": "stealthwriter_training",
                "verified_model": "Legacy 5.1",
                "ui_model_label": "Ghost 5.1 Legacy",
                "verified_level": 8,
                "selection_verified": True,
                "result_stage": "RESULT_EXTRACTED",
            }
            for i, r in enumerate(records, start=1)
        ],
    )

    out = tmp_path / "legacy51_sft"
    manifest = build_legacy51_sft(
        pairs_index=index,
        data_root=root,
        output_dir=out,
        seed=51,
    )

    assert manifest["total_eligible"] == 4
    assert manifest["final_usable"] == 2
    assert manifest["hard_rejected"] >= 2
    assert manifest["targets_unchanged_verified"] is True
    assert (out / "train.jsonl").exists()
    assert (out / "val.jsonl").exists()
    assert (out / "test.jsonl").exists()
    assert (out / "manifest.json").exists()
    assert (out / "quality_report.json").exists()
    assert (out / "README.md").exists()

    # Message format + verbatim target
    all_rows = []
    for name in ("train.jsonl", "val.jsonl", "test.jsonl"):
        for line in (out / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                all_rows.append(json.loads(line))
    assert len(all_rows) == 2
    for row in all_rows:
        assert list(row.keys()) == ["messages"]
        assert row["messages"][0]["role"] == "user"
        assert row["messages"][1]["role"] == "assistant"
        assert "Rewritten" in row["messages"][1]["content"]

    # Raw target unchanged vs export
    raw_targets = {r["document_id"]: r["teacher_text"] for r in records[:2]}
    meta = [
        json.loads(l)
        for l in (out / "samples_metadata.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip() and json.loads(l).get("status") == "accepted"
    ]
    exported = {m["sample_id"]: None for m in meta}
    for row, m in zip(
        [
            json.loads(l)
            for name in ("train.jsonl", "val.jsonl", "test.jsonl")
            for l in (out / name).read_text(encoding="utf-8").splitlines()
            if l.strip()
        ],
        # can't zip blindly; match by content
        [],
    ):
        pass
    for row in all_rows:
        content = row["messages"][1]["content"]
        assert content in raw_targets.values()

    soft = json.loads((out / "quality_report.json").read_text(encoding="utf-8"))
    assert soft["soft_flagged"] >= 1
    assert "PERCENT_MISMATCH" in soft["soft_flag_counts"]


def test_legacy51_sft_no_source_leakage_across_splits(tmp_path: Path):
    root = tmp_path / "data"
    docs = root / "teacher_raw_documents" / "run_y" / "documents.jsonl"
    records = []
    for i in range(10):
        src = f"## Introduction\n\nUnique source number {i} with enough distinct tokens about topic {i} academia.\n\n## Conclusion\n\nDone {i}."
        tgt = f"## Introduction\n\nUnique rewritten number {i} with enough distinct tokens about topic {i} academia carefully.\n\n## Conclusion\n\nDone {i} rewritten."
        records.append(_eligible_record(f"doc-{i}", src, tgt))
    _write_jsonl(docs, records)
    index = tmp_path / "index.jsonl"
    _write_jsonl(
        index,
        [
            {
                "sample_id": r["document_id"],
                "source_path": "teacher_raw_documents/run_y/documents.jsonl",
                "line_no": i,
                "run_dir": "teacher_raw_documents/run_y",
                "provider": "stealthwriter_training",
                "verified_model": "Legacy 5.1",
                "ui_model_label": "Ghost 5.1 Legacy",
                "verified_level": 8,
                "selection_verified": True,
                "result_stage": "RESULT_EXTRACTED",
            }
            for i, r in enumerate(records, start=1)
        ],
    )
    out = tmp_path / "out"
    build_legacy51_sft(pairs_index=index, data_root=root, output_dir=out, seed=51)

    def sources(name: str) -> set[str]:
        rows = [
            json.loads(l)
            for l in (out / name).read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        return {r["messages"][0]["content"] for r in rows}

    train, val, test = sources("train.jsonl"), sources("val.jsonl"), sources("test.jsonl")
    assert not (train & val)
    assert not (train & test)
    assert not (val & test)
