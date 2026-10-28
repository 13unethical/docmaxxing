"""Bulk teacher collection: per-document levels, account quota, limit handling (no browser)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.humanizer_training.bulk import (
    BulkConfig,
    QuotaLedger,
    next_reset,
    parse_level_weights,
    reuse_production_session,
    run_cycle,
    sw_day,
)
from services.humanizer_training.teacher.documents.collector import TeacherDocumentCollector
from services.humanizer_training.teacher.documents.schema import DocumentCollectorConfig, SyntheticDocument
from services.humanizer_training.teacher.documents.source_pool import SourcePool
from services.humanizer_training.teacher.provider import TeacherProviderError, TeacherResult

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def _doc(doc_id: str) -> SyntheticDocument:
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


def _pool(root: Path, n: int) -> SourcePool:
    pool = SourcePool(root)
    for i in range(n):
        pool.add(_doc(f"src-{i:03d}"))
    return pool


class _Provider:
    """Echoes the requested level like the real provider's DOM-verified meta."""

    def __init__(self, *, fail_on_call: int | None = None, code: str = "DAILY_LIMIT", wrong_level: bool = False):
        self.calls: list[int] = []
        self.fail_on_call = fail_on_call
        self.code = code
        self.wrong_level = wrong_level

    def rewrite(self, source_text: str, **kwargs) -> TeacherResult:
        level = int(kwargs["level"])
        self.calls.append(level)
        if self.fail_on_call is not None and len(self.calls) >= self.fail_on_call:
            raise TeacherProviderError(self.code, "You have reached your daily limit", retryable=False)
        verified = level + 1 if self.wrong_level else level
        return TeacherResult(
            text=source_text.replace("discussion", "examination"),
            provider="stealthwriter_training",
            version="Legacy 5.1",
            meta={
                "requested_model": "Legacy 5.1",
                "verified_model": "Legacy 5.1",
                "ui_model_label": "Ghost 5.1 Legacy",
                "requested_level": level,
                "verified_level": verified,
                "selection_verified": True,
                "last_successful_stage": "RESULT_EXTRACTED",
            },
        )


def _collect(tmp_path: Path, provider, *, count: int, weights=None, pool_size: int | None = None):
    pool = _pool(tmp_path / "pool", pool_size or count)
    cfg = DocumentCollectorConfig(
        count=count,
        output_dir=str(tmp_path / "run"),
        source_pool_dir=str(pool.root),
        level_weights=weights,
    )
    return pool, TeacherDocumentCollector(cfg, provider=provider).run()


def test_level_weights_parse_and_reject_out_of_range():
    assert parse_level_weights("4:1, 8:3,10") == {4: 1.0, 8: 3.0, 10: 1.0}
    with pytest.raises(ValueError):
        parse_level_weights("11:1")


def test_each_document_gets_its_own_recorded_level(tmp_path: Path):
    provider = _Provider()
    _pool_, result = _collect(tmp_path, provider, count=40, weights={4: 1, 6: 1, 8: 1, 10: 1})
    rows = [json.loads(l) for l in (tmp_path / "run" / "documents.jsonl").read_text().splitlines()]
    assert result.summary["successful"] == 40
    assert len(set(provider.calls)) == 4
    assert [r["teacher_level"] for r in rows] == provider.calls
    assert all(r["teacher_meta"]["verified_level"] == r["teacher_level"] for r in rows)
    assert sum(result.summary["successful_by_level"].values()) == 40


def test_level_pick_is_stable_for_a_document(tmp_path: Path):
    cfg = DocumentCollectorConfig(output_dir=str(tmp_path), level_weights={4: 1, 10: 1})
    collector = TeacherDocumentCollector(cfg, provider=_Provider())
    assert [collector._level_for("src-7") for _ in range(5)] == [collector._level_for("src-7")] * 5


def test_unverified_level_is_rejected(tmp_path: Path):
    _pool_, result = _collect(tmp_path, _Provider(wrong_level=True), count=2, weights={4: 1, 6: 1})
    assert result.summary["successful"] == 0
    failures = (tmp_path / "run" / "failures.jsonl").read_text()
    assert "WRONG_LEVEL" in failures


def test_without_weights_only_level_8_passes(tmp_path: Path):
    provider = _Provider()
    _pool_, result = _collect(tmp_path, provider, count=2)
    assert provider.calls == [8, 8]
    assert result.summary["successful"] == 2


def test_daily_limit_stops_and_keeps_the_document_pending(tmp_path: Path):
    provider = _Provider(fail_on_call=3)
    pool, result = _collect(tmp_path, provider, count=5)
    assert result.summary["stopped_reason"] == "DAILY_LIMIT"
    assert result.summary["successful"] == 2
    assert len(provider.calls) == 3
    assert pool.pending_count() == 3
    assert not (tmp_path / "run" / "failed_documents.jsonl").exists()


def test_pool_retires_a_document_after_repeated_failures(tmp_path: Path):
    pool = _pool(tmp_path / "pool", 2)
    assert pool.record_failure("src-000") is False
    assert pool.pending_count() == 2
    # A failed document moves to the back of the queue.
    assert [d.document_id for d in pool.peek(2)] == ["src-001", "src-000"]
    assert pool.record_failure("src-000") is True
    assert pool.pending_count() == 1
    assert (pool.failed_dir / "src-000.json").is_file()


def test_sw_day_and_reset_follow_utc_midnight():
    tashkent = timezone(timedelta(hours=5))
    late = datetime(2026, 10, 27, 4, 30, tzinfo=tashkent)  # 23:30 UTC on the 26th
    assert sw_day(late) == "2026-10-26"
    assert next_reset(late) == datetime(2026, 10, 27, 0, 0, tzinfo=timezone.utc)


def _cfg(tmp_path: Path, **kw) -> BulkConfig:
    base = dict(daily_limit=13, production_reserve=10, batch_size=10, root=tmp_path / "bulk", pool_root=tmp_path / "pool")
    base.update(kw)
    return BulkConfig(**base)


def test_cycle_spends_only_the_training_share(tmp_path: Path):
    _pool(tmp_path / "pool", 8)
    cfg = _cfg(tmp_path, level_weights={8: 1})
    provider = _Provider()
    first = run_cycle(cfg, provider=provider, now=NOW, clock=lambda: NOW)
    assert first.action == "batch_done"
    assert first.detail["requested"] == 3
    assert len(provider.calls) == 3
    assert QuotaLedger(cfg.root, sw_day(NOW)).used() == 3
    second = run_cycle(cfg, provider=provider, now=NOW, clock=lambda: NOW)
    assert second.action == "quota_done"
    assert second.wait_s == pytest.approx((next_reset(NOW) - NOW).total_seconds() + 120)
    assert len(provider.calls) == 3
    assert SourcePool(cfg.pool_root).pending_count() == 5


def test_retries_that_use_up_the_share_end_the_day_without_a_limit_alert(tmp_path: Path):
    _pool(tmp_path / "pool", 5)
    cfg = _cfg(tmp_path, daily_limit=12, level_weights={8: 1})

    class Flaky(_Provider):
        def rewrite(self, source_text: str, **kwargs):
            if len(self.calls) == 0:
                self.calls.append(8)
                raise TeacherProviderError("TIMEOUT", "slow", retryable=True)
            return super().rewrite(source_text, **kwargs)

    result = run_cycle(cfg, provider=Flaky(), now=NOW, clock=lambda: NOW)
    assert result.action == "quota_done"
    assert result.detail["successful"] == 1
    assert QuotaLedger(cfg.root, sw_day(NOW)).used() == 2


def test_stealthwriter_limit_message_pauses_for_an_hour(tmp_path: Path):
    _pool(tmp_path / "pool", 4)
    cfg = _cfg(tmp_path, daily_limit=100)
    result = run_cycle(cfg, provider=_Provider(fail_on_call=1), now=NOW, clock=lambda: NOW)
    assert result.action == "limit_hit"
    later = NOW + timedelta(minutes=20)
    waiting = run_cycle(cfg, provider=_Provider(), now=later, clock=lambda: later)
    assert waiting.action == "limit_wait"
    assert waiting.wait_s == pytest.approx(40 * 60)
    after = NOW + timedelta(minutes=61)
    resumed = run_cycle(cfg, provider=_Provider(), now=after, clock=lambda: after)
    assert resumed.action == "batch_done"


def test_cycle_waits_when_disabled_paused_or_pool_empty(tmp_path: Path):
    assert run_cycle(_cfg(tmp_path, daily_limit=0), provider=_Provider(), now=NOW, clock=lambda: NOW).action == "disabled"
    cfg = _cfg(tmp_path, daily_limit=100)
    assert run_cycle(cfg, provider=_Provider(), now=NOW, clock=lambda: NOW).action == "pool_empty"
    cfg.root.mkdir(parents=True)
    (cfg.root / "PAUSE").touch()
    assert run_cycle(cfg, provider=_Provider(), now=NOW, clock=lambda: NOW).action == "paused"


def _multi_paragraph_pool(root: Path, n: int) -> None:
    pool = SourcePool(root)
    for i in range(n):
        doc = _doc(f"src-{i:03d}")
        doc.source_text = doc.source_text.replace(
            "carefully.", "carefully.\n\nA second paragraph of the discussion adds detail."
        ).replace("adoption.", "adoption.\n\nAnother paragraph extends the discussion further.")
        pool.add(doc)


def test_lost_paragraph_breaks_pause_collection(tmp_path: Path):
    _multi_paragraph_pool(tmp_path / "pool", 6)
    cfg = _cfg(tmp_path, daily_limit=100, batch_size=3, level_weights={8: 1})

    class Flattening(_Provider):
        def rewrite(self, source_text: str, **kwargs):
            result = super().rewrite(source_text, **kwargs)
            result.text = " ".join(result.text.split())
            return result

    result = run_cycle(cfg, provider=Flattening(), now=NOW, clock=lambda: NOW)
    assert result.action == "paused_quality"
    assert result.detail["paragraph_preservation"] == 0.0
    assert (cfg.root / "PAUSE").exists()
    assert run_cycle(cfg, provider=_Provider(), now=NOW, clock=lambda: NOW).action == "paused"


def test_preserved_paragraphs_keep_collecting(tmp_path: Path):
    _multi_paragraph_pool(tmp_path / "pool", 6)
    cfg = _cfg(tmp_path, daily_limit=100, batch_size=3, level_weights={8: 1})
    result = run_cycle(cfg, provider=_Provider(), now=NOW, clock=lambda: NOW)
    assert result.action == "batch_done"
    assert result.detail["paragraph_preservation"] == 1.0


def test_levels_in_a_batch_follow_the_weights(tmp_path: Path):
    _pool(tmp_path / "pool", 200)
    cfg = _cfg(tmp_path, daily_limit=500, batch_size=200, level_weights={4: 1, 8: 3})
    provider = _Provider()
    run_cycle(cfg, provider=provider, now=NOW, clock=lambda: NOW)
    counts = Counter(provider.calls)
    assert set(counts) == {4, 8}
    assert 0.6 < counts[8] / 200 < 0.9


def test_production_session_is_copied_only_when_newer(tmp_path: Path):
    prod = tmp_path / "sessions" / "stealthwriter.json"
    train = tmp_path / "training" / "stealthwriter.json"
    prod.parent.mkdir()
    prod.write_text('{"cookies": []}')
    assert reuse_production_session(prod, train) is True
    assert train.read_text() == prod.read_text()
    assert reuse_production_session(prod, train) is False


def test_nightly_backfill_stands_down_while_bulk_is_enabled(tmp_path: Path, monkeypatch):
    from services.economy import db as economy_db
    from services.economy.site_settings import ensure_schema, ensure_today_row, update_site_settings
    from services.humanizer_training.synthetic_daily import plan_daily_backfill

    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    with economy_db.connect() as conn:
        ensure_schema(conn)
        ensure_today_row(conn)
    update_site_settings(humanizer_daily_limit=10)
    _pool(tmp_path / "pool", 3)
    monkeypatch.setenv("HUMANIZER_TRAINING_BULK_DAILY_LIMIT", "350")
    plan = plan_daily_backfill(force_window=True, output_root=tmp_path / "out", source_pool_root=tmp_path / "pool")
    assert plan.reason == "bulk_collection_active"
    assert plan.documents_to_attempt == 0


def _long_essay(sections: int, sentences: int, refs: bool = True) -> str:
    n = 0
    parts = []
    for s in range(sections):
        body = []
        for _ in range(sentences):
            n += 1
            body.append(f"Point {n} develops a separate strand of the argument with evidence from study {n}.")
        parts.append(f"## Part {s + 1}\n\n" + " ".join(body))
    tail = "\n\n## References\n\nSmith, J. (2020). A study. Journal, 1(1), 1-10." if refs else ""
    return "\n\n".join(parts) + tail


def test_overlong_source_loses_middle_sections_but_keeps_ends_and_references():
    from services.humanizer_training.teacher.documents.source_pool import MAX_WORDS, fit_source_length

    text = _long_essay(sections=12, sentences=34)  # ~5,700 words
    fitted = fit_source_length(text)
    titles = [line for line in fitted.splitlines() if line.startswith("## ")]
    assert len(fitted.split()) <= MAX_WORDS
    assert titles[0] == "## Part 1" and titles[-2] == "## Part 12" and titles[-1] == "## References"
    assert fit_source_length(_long_essay(5, 30)) == _long_essay(5, 30)


def test_truncated_writer_output_is_rejected():
    from services.humanizer_training.teacher.documents.source_pool import generate_source_document

    cut = _long_essay(sections=6, sentences=20).rsplit(" ", 3)[0]

    def reply(**_kw):
        return cut, {"model": "gemini-3.5-flash", "finish_reason": "MAX_TOKENS"}

    doc, reasons, _diag = generate_source_document(("business", "t", "essay", "a"), seed=1, reply_fn=reply)
    assert doc is None and "TRUNCATED" in reasons


def test_fill_pool_spreads_briefs_across_writer_models(tmp_path: Path, monkeypatch):
    from services.humanizer_training.teacher.documents import source_pool as sp

    calls: list[str] = []

    def reply_for(provider):
        def reply(**kw):
            calls.append(f"{provider}:{kw['model']}")
            return _long_essay(sections=6, sentences=32, refs=False), {"model": kw["model"]}

        return reply

    monkeypatch.setattr(sp, "_reply_fn_for", reply_for)
    mix = sp.parse_source_mix("gemini:gemini-3.5-flash:3,claude:claude-sonnet-4-6:1")
    result = sp.fill_source_pool(target_pending=40, root=tmp_path, workers=2, seed=5, mix=mix)
    assert result.generated == 40
    assert set(calls) == {"gemini:gemini-3.5-flash", "claude:claude-sonnet-4-6"}
    assert result.by_writer["gemini-3.5-flash"] > result.by_writer["claude-sonnet-4-6"]
    meta = json.loads(next((tmp_path / "pending").glob("*.json")).read_text())["source_generator"]
    assert meta["provider"] in {"gemini", "claude"}
