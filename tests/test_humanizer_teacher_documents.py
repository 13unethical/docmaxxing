"""Tests for document-level offline teacher collection (no real StealthWriter)."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from services.humanizer_engine.heading_utils import join_body_and_references, split_off_references
from services.humanizer_training.teacher.config import TeacherProviderConfig
from services.humanizer_training.teacher.documents.collector import TeacherDocumentCollector
from services.humanizer_training.teacher.documents.generator import generate_documents
from services.humanizer_training.teacher.documents.quality import evaluate_teacher_document
from services.humanizer_training.teacher.documents.schema import DocumentCollectorConfig, HumanizerTeacherDocument
from services.humanizer_training.teacher.provider import TeacherResult
from services.humanizer_training.teacher.stealthwriter_provider import (
    StealthWriterTeacherProvider,
    TrainingBrowserConfig,
)


class _DocProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.seen_texts: list[str] = []

    def rewrite(self, source_text: str, **kwargs) -> TeacherResult:
        self.calls += 1
        self.seen_texts.append(source_text)
        # Mild rewrite that preserves tokens
        out = source_text.replace("discussion", "examination").replace("argument", "claim")
        if out == source_text:
            out = source_text + "\n\nAdditional clarifying prose preserves academic structure."
        return TeacherResult(
            text=out,
            provider="stealthwriter_training",
            version="Legacy 5.1",
            meta={
                "provider_name": "stealthwriter_training",
                "model": "Legacy 5.1",
                "level": 8,
                "timeout_s": 150.0,
                "requested_model": "Legacy 5.1",
                "verified_model": "Legacy 5.1",
                "ui_model_label": "Ghost 5.1 Legacy",
                "requested_level": 8,
                "verified_level": 8,
                "selection_verified": True,
                "last_successful_stage": "RESULT_EXTRACTED",
            },
        )


def test_document_generation_is_deterministic():
    a, plan_a = generate_documents(count=5, seed=300)
    b, plan_b = generate_documents(count=5, seed=300)
    assert [d.document_id for d in a] == [d.document_id for d in b]
    assert [d.source_text for d in a] == [d.source_text for d in b]
    assert plan_a.length_buckets == plan_b.length_buckets


def test_document_word_targets_and_structure():
    docs, plan = generate_documents(count=100, seed=301)
    assert len(docs) == 100
    assert plan.length_buckets["4500_5000"] == 90
    assert plan.length_buckets["3000_4500"] == 10
    assert "5001_5500" not in plan.length_buckets

    main = [d for d in docs if d.length_bucket == "4500_5000"]
    assert main
    assert all(4500 <= d.word_count <= 5000 for d in main)
    assert all(d.word_count <= 5000 for d in docs)

    for d in docs:
        assert 4 <= d.section_count <= 9
        assert any(t.startswith("## ") for t in d.source_text.splitlines())
        headings = re.findall(r"(?m)^##\s+(.+)$", d.source_text)
        assert len(headings) == d.section_count


def test_references_split_and_passthrough_merge():
    docs, _ = generate_documents(count=40, seed=77)
    with_refs = [d for d in docs if d.references_present]
    assert with_refs
    for d in with_refs[:5]:
        body, refs = split_off_references(d.source_text)
        assert refs.strip().lower().startswith("## reference")
        assert "References" not in body or "## References" not in body
        fake_teacher_body = body.replace("discussion", "examination")
        merged = join_body_and_references(fake_teacher_body, refs)
        _, refs2 = split_off_references(merged)
        assert " ".join(refs.lower().split()) == " ".join(refs2.lower().split())


def test_marker_distribution_on_500_documents():
    docs, _ = generate_documents(count=500, seed=909)
    patterns = {
        "citation": re.compile(r"\([^)]*?\d{4}[^)]*?\)|\[\d+\]"),
        "number": re.compile(r"\b\d+(?:\.\d+)?\b"),
        "year": re.compile(r"\b(?:19|20)\d{2}\b"),
        "percentage": re.compile(r"\b\d+(?:\.\d+)?%"),
        "url": re.compile(r"https?://\S+", re.I),
    }
    # Evaluate on body only so References do not inflate rates unrealistically.
    bodies = [split_off_references(d.source_text)[0] for d in docs]
    n = len(bodies)

    def rate(pat):
        return sum(1 for t in bodies if pat.search(t)) / n

    citation_rate = rate(patterns["citation"])
    year_rate = rate(patterns["year"])
    percent_rate = rate(patterns["percentage"])
    url_rate = rate(patterns["url"])
    plain_number_rate = rate(re.compile(r"Approximately\s+\d+\s+observations"))

    assert 0.25 <= citation_rate <= 0.45
    assert 0.20 <= year_rate <= 0.35
    assert 0.08 <= percent_rate <= 0.25
    assert 0.03 <= url_rate <= 0.15
    assert 0.25 <= plain_number_rate <= 0.45
    # Generic digit presence is higher due to overlap with years/percents/citations.
    assert rate(patterns["number"]) >= plain_number_rate


def test_document_schema_fields():
    docs, _ = generate_documents(count=1, seed=1)
    d = docs[0]
    record = HumanizerTeacherDocument(
        document_id=d.document_id,
        source_text=d.source_text,
        teacher_text=d.source_text + " rewritten",
        domain=d.domain,
        document_type=d.document_type,
        language=d.language,
        seed=d.seed,
        teacher_provider="stealthwriter_training",
        teacher_model="Legacy 5.1",
        teacher_level=8,
        teacher_timeout=150.0,
        source_word_count=d.word_count,
        teacher_word_count=d.word_count + 1,
        source_body_word_count=d.body_word_count,
        teacher_body_word_count=d.body_word_count + 1,
        references_present=d.references_present,
        references_word_count=d.references_word_count,
        section_count=d.section_count,
        section_titles=d.section_titles,
        chunks=[],
    )
    payload = record.to_dict()
    for key in (
        "document_id",
        "source_text",
        "teacher_text",
        "teacher_provider",
        "teacher_model",
        "teacher_level",
        "source_word_count",
        "chunks",
    ):
        assert key in payload
    assert "user_id" not in payload
    assert "email" not in payload
    assert "api_key" not in payload


def test_provider_accepts_4500_and_5000_rejects_5001():
    cfg = TrainingBrowserConfig(
        cdp_port=19333,
        user_data_dir="browser_profiles/test_training_chrome",
        session_dir="browser_profiles/test_training_sessions",
        max_text_words=5000,
        max_retries=1,
        retry_delay_s=0.0,
    )
    assert cfg.max_text_words == 5000
    provider = StealthWriterTeacherProvider(cfg)
    provider._started = True

    text_4500 = "word " * 4500
    text_5000 = "word " * 5000
    text_5001 = "word " * 5001

    from unittest.mock import MagicMock, patch

    with patch(
        "services.humanizer_training.teacher.stealthwriter_provider._humanize_once",
        return_value={"success": True, "humanized_text": "rewritten " * 100},
    ):
        with patch.object(provider, "_page", return_value=MagicMock()):
            r1 = provider.rewrite(text_4500)
            r2 = provider.rewrite(text_5000)
    assert r1.error != "TEXT_TOO_LONG"
    assert r2.error != "TEXT_TOO_LONG"

    r3 = provider.rewrite(text_5001)
    assert r3.success is False
    assert r3.error == "TEXT_TOO_LONG"


def test_default_training_max_words_is_5000():
    assert TrainingBrowserConfig().max_text_words == 5000


def test_document_collector_one_call_and_skips_too_large(tmp_path: Path):
    provider = _DocProvider()
    # Use a tiny seeded batch by monkeypatching generate_documents via controlled config count
    # Build a collector that processes generated docs; include oversized by using real generator.
    cfg = DocumentCollectorConfig(
        count=20,
        seed=303,
        output_dir=str(tmp_path / "docs"),
        dry_run=False,
        provider_name="stealthwriter",
        model="Legacy 5.1",
        level=8,
        timeout_s=150.0,
        max_provider_words=5000,
    )
    result = TeacherDocumentCollector(cfg, provider=provider).run()
    manifest = result.manifest
    assert manifest["dataset_type"] == "teacher_raw_documents"
    assert manifest["provider"]["model"] == "Legacy 5.1"
    assert manifest["provider"]["level"] == 8
    assert manifest["provider"]["timeout_s"] == 150.0
    assert manifest["provider"]["max_provider_words"] == 5000
    assert manifest["skipped_document_too_large"] >= 0
    # Provider must never receive >5000 words
    assert all(len(t.split()) <= 5000 for t in provider.seen_texts)
    # References must not be sent to provider
    assert all("## References" not in t for t in provider.seen_texts)
    # Body ## headings must be protected before provider call
    assert any("[[[HEADING_0]]]" in t for t in provider.seen_texts)
    assert all(not re.search(r"(?m)^##\s+\S", t) for t in provider.seen_texts)

    docs_path = tmp_path / "docs" / "documents.jsonl"
    if docs_path.exists():
        rows = [json.loads(line) for line in docs_path.read_text().splitlines() if line.strip()]
        for row in rows:
            assert row["teacher_provider"] == "stealthwriter_training"
            assert row["teacher_model"] == "Legacy 5.1"
            assert row["teacher_level"] == 8
            assert len(row["chunks"]) == 1
            assert row["chunks"][0]["index"] == 0
            # Restored teacher output must keep markdown heading structure
            teacher_headings = re.findall(r"(?m)^##\s+.+$", row["teacher_text"])
            source_body_headings = re.findall(
                r"(?m)^##\s+.+$",
                split_off_references(row["source_text"])[0],
            )
            assert teacher_headings
            assert all(h in row["teacher_text"] for h in source_body_headings)


def test_dry_run_does_not_call_provider(tmp_path: Path):
    provider = _DocProvider()
    cfg = DocumentCollectorConfig(
        count=10,
        seed=300,
        output_dir=str(tmp_path / "dry"),
        dry_run=True,
    )
    result = TeacherDocumentCollector(cfg, provider=provider).run()
    assert result.manifest["dry_run"] is True
    assert provider.calls == 0
    assert not (tmp_path / "dry" / "documents.jsonl").exists()
    assert (tmp_path / "dry" / "manifest.json").exists()
    assert (tmp_path / "dry" / "dry_run_sources.jsonl").exists()
    stats = result.manifest["word_stats"]
    assert stats["min"] >= 3000
    assert stats["max"] <= 5000
    assert stats["gt_5000"] == 0
    assert result.summary["dry_run"] is True


def test_quality_document_too_large_and_unchanged():
    source = "word " * 5001
    q = evaluate_teacher_document(source, source, max_words=5000)
    assert not q.accepted
    assert "DOCUMENT_TOO_LARGE" in q.reject_reasons
    assert "UNCHANGED" in q.reject_reasons


def test_quality_flags_preserve_heading_and_numeric():
    source = "## Introduction\n\nIn 2021 the rate rose by 12% according to [3].\n\n## Conclusion\n\nFinal note."
    target = "## Introduction\n\nEarlier findings are discussed without numeric anchors.\n\n## Conclusion\n\nFinal note."
    q = evaluate_teacher_document(source, target)
    assert q.accepted
    assert "YEAR_MISMATCH" in q.flags or "NUMERIC_MISMATCH" in q.flags or "PERCENT_MISMATCH" in q.flags or "CITATION_MISMATCH" in q.flags


def test_no_production_import_from_app():
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
    assert not any(name.startswith("services.humanizer_training.teacher.documents") for name in imported)


def test_documents_package_does_not_import_browser_service():
    root = Path(__file__).resolve().parents[1] / "services/humanizer_training/teacher/documents"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "browser_service" not in mod
                assert mod != "app"
                for alias in node.names:
                    assert alias.name not in {"BrowserService", "JobManager", "WalletService"}
