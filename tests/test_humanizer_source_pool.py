"""Claude-written source pool for teacher collection (no network, no browser)."""

from __future__ import annotations

import json
from pathlib import Path

from services.humanizer_training.synthetic_daily import plan_daily_backfill
from services.humanizer_training.teacher.documents.collector import TeacherDocumentCollector
from services.humanizer_training.teacher.documents.generator import generate_documents
from services.humanizer_training.teacher.documents.schema import (
    DocumentCollectorConfig,
    SyntheticDocument,
)
from services.humanizer_training.teacher.documents.source_pool import (
    SourcePool,
    clean_source_text,
    fill_source_pool,
    validate_source_text,
)
from services.humanizer_training.teacher.provider import TeacherProviderError, TeacherResult


def _essay(sections: int = 5, sentences_per_section: int = 40) -> str:
    parts = []
    n = 0
    for s in range(sections):
        sentences = []
        for _ in range(sentences_per_section):
            n += 1
            sentences.append(
                f"Observation {n} examines a distinct aspect of the case with evidence drawn from source {n}."
            )
        parts.append(f"## Section {s + 1}\n\n" + " ".join(sentences))
    return "\n\n".join(parts)


def _fake_reply(text: str):
    calls: list[dict] = []

    def reply(**kwargs):
        calls.append(kwargs)
        return text, {"model": "fake-claude", "latency_ms": 1}

    reply.calls = calls  # type: ignore[attr-defined]
    return reply


def test_clean_strips_title_and_preamble():
    raw = "Here is your essay:\n\n# Big Title\n\n## Introduction\n\nBody text.\n\n### Sub\n\nMore."
    cleaned = clean_source_text(raw)
    assert cleaned.startswith("## Introduction")
    assert "## Sub" in cleaned
    assert "Big Title" not in cleaned


def test_validate_accepts_real_essay_and_rejects_template_output():
    assert validate_source_text(_essay()) == []

    docs, _ = generate_documents(count=1, seed=561021)
    reasons = validate_source_text(docs[0].source_text)
    assert "REPETITIVE" in reasons


def test_validate_rejects_short_and_forbidden():
    assert "TOO_SHORT" in validate_source_text("## A\n\nshort.\n\n## B\n\nx.\n\n## C\n\ny.")
    text = _essay() + "\n\nThis was checked with Turnitin before submission."
    assert "FORBIDDEN_TERM" in validate_source_text(text)


def test_validate_rejects_tables_lists_and_diagrams():
    essay = _essay()
    first_break = essay.index("\n\n", essay.index("\n\n") + 2)
    for extra in (
        "| Factor | Effect |\n|---|---|\n| Cost | High |",
        "- first point\n- second point",
        "1. First step",
        "```\n+-----+\n| box |\n+-----+\n```",
    ):
        text = essay[:first_break] + "\n\n" + extra + essay[first_break:]
        assert "NON_PROSE" in validate_source_text(text), extra
    assert "NON_PROSE" not in validate_source_text(essay)


def test_fill_pool_tops_up_to_target_with_unique_briefs(tmp_path: Path):
    reply = _fake_reply(_essay())
    first = fill_source_pool(target_pending=4, root=tmp_path, workers=2, reply_fn=reply, seed=7)
    # Identical text from the fake makes identical document ids only if the brief also matches.
    assert first.generated == 4
    assert first.pending_after == 4
    pool = SourcePool(tmp_path)
    keys = {d.combination_key for d in pool.peek(10)}
    assert len(keys) == 4

    second = fill_source_pool(target_pending=4, root=tmp_path, reply_fn=reply, seed=8)
    assert second.requested == 0
    assert len(reply.calls) == 4
    assert reply.calls[0]["max_tokens"] >= 8000


def test_fill_pool_records_rejections(tmp_path: Path):
    reply = _fake_reply("## Only\n\nToo short to be useful.")
    result = fill_source_pool(target_pending=2, root=tmp_path, workers=1, reply_fn=reply, seed=3)
    assert result.generated == 0
    assert result.rejected == 2
    rows = [json.loads(line) for line in (tmp_path / "rejected.jsonl").read_text().splitlines()]
    assert all("TOO_SHORT" in r["reasons"] for r in rows)


def _pool_doc(doc_id: str) -> SyntheticDocument:
    text = (
        f"## Introduction\n\nThe discussion of digital platforms frames case {doc_id} carefully.\n\n"
        "## Analysis\n\nEvidence from two firms suggests cautious adoption.\n\n"
        "## Conclusion\n\nThe discussion closes with implications for managers."
    )
    return SyntheticDocument(
        document_id=doc_id,
        source_text=text,
        domain="business",
        document_type="explanation",
        language="en",
        seed=1,
        word_count=len(text.split()),
        body_word_count=len(text.split()),
        references_present=False,
        references_word_count=0,
        section_count=3,
        section_titles=["Introduction", "Analysis", "Conclusion"],
        length_bucket="claude_medium",
        combination_key=f"business|t|explanation|{doc_id}",
    )


_OK_META = {
    "requested_model": "Legacy 5.1",
    "verified_model": "Legacy 5.1",
    "ui_model_label": "Ghost 5.1 Legacy",
    "requested_level": 8,
    "verified_level": 8,
    "selection_verified": True,
    "last_successful_stage": "RESULT_EXTRACTED",
}


class _Provider:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.calls = 0

    def rewrite(self, source_text: str, **kwargs) -> TeacherResult:
        self.calls += 1
        if self.error:
            raise TeacherProviderError(self.error, "Session expired", meta={}, retryable=False)
        return TeacherResult(
            text=source_text.replace("discussion", "examination"),
            provider="stealthwriter_training",
            version="Legacy 5.1",
            meta=dict(_OK_META),
        )


def test_collector_consumes_pool_and_marks_used(tmp_path: Path):
    pool = SourcePool(tmp_path / "pool")
    for i in range(3):
        pool.add(_pool_doc(f"src-{i}"))
    cfg = DocumentCollectorConfig(
        count=2,
        output_dir=str(tmp_path / "run"),
        source_pool_dir=str(pool.root),
    )
    result = TeacherDocumentCollector(cfg, provider=_Provider()).run()
    assert result.summary["successful"] == 2
    assert result.summary["source"] == "claude_pool"
    assert pool.pending_count() == 1
    assert pool.used_count() == 2
    rows = [json.loads(l) for l in (tmp_path / "run" / "documents.jsonl").read_text().splitlines()]
    assert {r["source_kind"] for r in rows} == {"claude_pool"}


def test_login_required_stops_run_and_keeps_documents_pending(tmp_path: Path):
    pool = SourcePool(tmp_path / "pool")
    for i in range(4):
        pool.add(_pool_doc(f"src-{i}"))
    provider = _Provider(error="LOGIN_REQUIRED")
    cfg = DocumentCollectorConfig(
        count=4,
        output_dir=str(tmp_path / "run"),
        source_pool_dir=str(pool.root),
    )
    result = TeacherDocumentCollector(cfg, provider=provider).run()
    assert provider.calls == 1
    assert result.summary["stopped_reason"] == "LOGIN_REQUIRED"
    assert result.summary["successful"] == 0
    assert pool.pending_count() == 4


def test_daily_plan_caps_attempts_by_pool(tmp_path: Path, monkeypatch):
    from services.economy import db as economy_db
    from services.economy.site_settings import ensure_schema, ensure_today_row, update_site_settings
    from services.humanizer_training.consent import ensure_training_consent_schema

    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    ensure_training_consent_schema()
    with economy_db.connect() as conn:
        ensure_schema(conn)
        ensure_today_row(conn)
    update_site_settings(humanizer_daily_limit=10)

    pool = SourcePool(tmp_path / "pool")
    empty = plan_daily_backfill(force_window=True, output_root=tmp_path / "out", source_pool_root=pool.root)
    assert empty.reason == "source_pool_empty"
    assert empty.documents_to_attempt == 0

    for i in range(3):
        pool.add(_pool_doc(f"src-{i}"))
    plan = plan_daily_backfill(force_window=True, output_root=tmp_path / "out", source_pool_root=pool.root)
    assert plan.reason == "ready"
    assert plan.documents_to_attempt == 3
