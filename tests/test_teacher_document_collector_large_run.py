"""Unit tests for large-run teacher document collector safeguards (no browser)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.humanizer_training.teacher.documents.collector import (
    TeacherDocumentCollector,
    _PROVIDER_INTERNAL_RETRIES,
)
from services.humanizer_training.teacher.documents.generator import DocumentSamplingPlan
from services.humanizer_training.teacher.documents.schema import (
    DocumentCollectorConfig,
    SyntheticDocument,
)
from services.humanizer_training.teacher.provider import TeacherProviderError, TeacherResult


def _mini_doc(doc_id: str = "doc-test-00000-aaaaaaaaaa", *, source: str | None = None) -> SyntheticDocument:
    text = source or (
        "## Introduction\n\n"
        "Academic prose about organizational strategy and stakeholder incentives with careful evidence.\n\n"
        "## Analysis\n\n"
        "Further clarification develops the claim without unsupported generalization.\n\n"
        "## Conclusion\n\n"
        "The discussion remains organized around evidence and cautious implication."
    )
    return SyntheticDocument(
        document_id=doc_id,
        source_text=text,
        domain="business",
        document_type="explanation",
        language="en",
        seed=500,
        word_count=len(text.split()),
        body_word_count=len(text.split()),
        references_present=False,
        references_word_count=0,
        section_count=3,
        section_titles=["Introduction", "Analysis", "Conclusion"],
        length_bucket="3000_4500",
    )


def _ok_meta(**overrides) -> dict:
    meta = {
        "requested_model": "Legacy 5.1",
        "verified_model": "Legacy 5.1",
        "ui_model_label": "Ghost 5.1 Legacy",
        "requested_level": 8,
        "verified_level": 8,
        "selection_verified": True,
        "last_successful_stage": "RESULT_EXTRACTED",
    }
    meta.update(overrides)
    return meta


def _patch_docs(monkeypatch, docs: list[SyntheticDocument]) -> None:
    plan = DocumentSamplingPlan(
        document_types={"explanation": len(docs)},
        domains={"business": len(docs)},
        topics={"digital_transformation_in_organizations": len(docs)},
        angles={"compare_policy_trade_offs": len(docs)},
        length_buckets={"3000_4500": len(docs)},
        with_references=0,
        section_count_histogram={3: len(docs)},
        combinations=[f"business|digital_transformation_in_organizations|explanation|compare_policy_trade_offs"]
        * len(docs),
    )

    def _fake(*, count: int, seed: int, domain: str | None = None):
        return docs[:count], plan

    monkeypatch.setattr(
        "services.humanizer_training.teacher.documents.collector.generate_documents",
        _fake,
    )


class _CountingProvider:
    def __init__(self, *, fail_times: int = 0, error: str = "TIMEOUT") -> None:
        self.calls = 0
        self.fail_times = fail_times
        self.error = error

    def rewrite(self, source_text: str, **kwargs) -> TeacherResult:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TeacherProviderError(
                self.error,
                f"{self.error} attempt {self.calls}",
                meta={"failed_stage": "RESULT_FOUND", "retryable": True},
                retryable=True,
            )
        out = source_text.replace("discussion", "examination")
        if out == source_text:
            out = source_text + "\n\nRewritten clarifying sentence."
        return TeacherResult(
            text=out,
            provider="stealthwriter_training",
            version="Legacy 5.1",
            meta=_ok_meta(),
        )


class _MetaProvider:
    def __init__(self, meta: dict, version: str = "Legacy 5.1", provider: str = "stealthwriter_training"):
        self.meta = meta
        self.version = version
        self.provider = provider
        self.calls = 0

    def rewrite(self, source_text: str, **kwargs) -> TeacherResult:
        self.calls += 1
        out = source_text + "\n\nRewritten clarifying sentence."
        return TeacherResult(
            text=out,
            provider=self.provider,
            version=self.version,
            meta=dict(self.meta),
        )


def test_bounded_attempts_no_nested_multiplication(tmp_path: Path, monkeypatch):
    _patch_docs(monkeypatch, [_mini_doc()])
    provider = _CountingProvider(fail_times=99, error="TIMEOUT")
    cfg = DocumentCollectorConfig(
        count=1,
        seed=500,
        output_dir=str(tmp_path / "run"),
        max_attempts_per_document=2,
        max_retries=2,
    )
    result = TeacherDocumentCollector(cfg, provider=provider).run()
    # Collector attempts=2 and provider is single-shot per call → exactly 2 rewrite calls.
    assert provider.calls == 2
    assert _PROVIDER_INTERNAL_RETRIES == 1
    assert result.summary["timeout_count"] == 2
    assert result.summary["failed"] >= 1
    assert result.summary["successful"] == 0
    assert (tmp_path / "run" / "failures.jsonl").exists()
    assert (tmp_path / "run" / "failed_documents.jsonl").exists()
    # Failed source archived (not deleted)
    failed = [
        json.loads(line)
        for line in (tmp_path / "run" / "failed_documents.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert failed[0]["source_text"]
    assert failed[0]["error_code"] == "TIMEOUT"


def test_max_attempts_one(tmp_path: Path, monkeypatch):
    _patch_docs(monkeypatch, [_mini_doc()])
    provider = _CountingProvider(fail_times=99, error="TIMEOUT")
    cfg = DocumentCollectorConfig(
        count=1,
        seed=500,
        output_dir=str(tmp_path / "run1"),
        max_attempts_per_document=1,
    )
    TeacherDocumentCollector(cfg, provider=provider).run()
    assert provider.calls == 1


def test_failed_sample_continues_to_next(tmp_path: Path, monkeypatch):
    docs = [_mini_doc("doc-a"), _mini_doc("doc-b", source=_mini_doc().source_text + "\n\nUnique trailer B.")]
    _patch_docs(monkeypatch, docs)

    class Flaky:
        def __init__(self) -> None:
            self.calls = 0

        def rewrite(self, source_text: str, **kwargs):
            self.calls += 1
            doc_id = kwargs.get("document_id")
            if doc_id == "doc-a":
                raise TeacherProviderError(
                    "TIMEOUT",
                    "boom",
                    meta={"failed_stage": "RESULT_FOUND"},
                    retryable=True,
                )
            out = source_text + "\n\nRewritten clarifying sentence."
            return TeacherResult(
                text=out,
                provider="stealthwriter_training",
                version="Legacy 5.1",
                meta=_ok_meta(),
            )

    provider = Flaky()
    cfg = DocumentCollectorConfig(
        count=2,
        seed=500,
        output_dir=str(tmp_path / "cont"),
        max_attempts_per_document=1,
    )
    result = TeacherDocumentCollector(cfg, provider=provider).run()
    assert result.summary["successful"] == 1
    assert result.summary["failed"] == 1
    rows = [
        json.loads(line)
        for line in (tmp_path / "cont" / "documents.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert rows[0]["document_id"] == "doc-b"


def test_resume_checkpoint_skips_committed(tmp_path: Path, monkeypatch):
    docs = [
        _mini_doc("doc-1", source=_mini_doc().source_text + "\n\nUnique one."),
        _mini_doc("doc-2", source=_mini_doc().source_text + "\n\nUnique two."),
    ]
    _patch_docs(monkeypatch, docs)
    provider = _CountingProvider(fail_times=0)
    out = tmp_path / "resume_run"
    cfg = DocumentCollectorConfig(
        count=2,
        seed=500,
        output_dir=str(out),
        max_attempts_per_document=1,
    )
    first = TeacherDocumentCollector(cfg, provider=provider).run()
    assert first.summary["successful"] == 2
    calls_after_first = provider.calls

    cfg2 = DocumentCollectorConfig(
        count=2,
        seed=500,
        output_dir=str(out),
        resume=True,
        max_attempts_per_document=1,
    )
    second = TeacherDocumentCollector(cfg2, provider=provider).run()
    assert provider.calls == calls_after_first  # no re-calls
    assert second.summary["successful"] == 0
    assert second.summary["already_completed_on_resume"] == 2
    rows = [
        json.loads(line)
        for line in (out / "documents.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 2


def test_resume_required_when_state_exists(tmp_path: Path, monkeypatch):
    _patch_docs(monkeypatch, [_mini_doc()])
    out = tmp_path / "need_resume"
    provider = _CountingProvider(fail_times=0)
    cfg = DocumentCollectorConfig(count=1, seed=500, output_dir=str(out))
    TeacherDocumentCollector(cfg, provider=provider).run()
    with pytest.raises(FileExistsError):
        TeacherDocumentCollector(
            DocumentCollectorConfig(count=1, seed=500, output_dir=str(out)),
            provider=provider,
        ).run()


def test_duplicate_source_prevented(tmp_path: Path, monkeypatch):
    same = _mini_doc().source_text + "\n\nShared body."
    docs = [_mini_doc("doc-1", source=same), _mini_doc("doc-2", source=same)]
    _patch_docs(monkeypatch, docs)
    provider = _CountingProvider(fail_times=0)
    cfg = DocumentCollectorConfig(count=2, seed=500, output_dir=str(tmp_path / "dup"))
    result = TeacherDocumentCollector(cfg, provider=provider).run()
    assert result.summary["successful"] == 1
    assert result.manifest["rejection_reasons"].get("DUPLICATE_SOURCE") == 1


def test_fail_closed_wrong_model(tmp_path: Path, monkeypatch):
    _patch_docs(monkeypatch, [_mini_doc()])
    provider = _MetaProvider(
        _ok_meta(verified_model="Mini", ui_model_label="Mini", selection_verified=True),
        version="Mini",
    )
    cfg = DocumentCollectorConfig(count=1, seed=500, output_dir=str(tmp_path / "bad_model"))
    result = TeacherDocumentCollector(cfg, provider=provider).run()
    assert result.summary["successful"] == 0
    assert result.manifest["rejection_reasons"].get("WRONG_MODEL") == 1


def test_fail_closed_wrong_level(tmp_path: Path, monkeypatch):
    _patch_docs(monkeypatch, [_mini_doc()])
    provider = _MetaProvider(_ok_meta(verified_level=3, requested_level=3))
    cfg = DocumentCollectorConfig(
        count=1, seed=500, output_dir=str(tmp_path / "bad_level"), level=8
    )
    result = TeacherDocumentCollector(cfg, provider=provider).run()
    assert result.summary["successful"] == 0
    assert result.manifest["rejection_reasons"].get("WRONG_LEVEL") == 1


def test_fail_closed_selection_and_stage(tmp_path: Path, monkeypatch):
    _patch_docs(monkeypatch, [_mini_doc("doc-sel"), _mini_doc("doc-stage", source=_mini_doc().source_text + " x")])
    # First wrong selection, second wrong stage — both rejected, run continues.
    class Seq:
        def __init__(self) -> None:
            self.n = 0

        def rewrite(self, source_text: str, **kwargs):
            self.n += 1
            meta = _ok_meta()
            if self.n == 1:
                meta["selection_verified"] = False
            else:
                meta["last_successful_stage"] = "RESULT_FOUND"
            return TeacherResult(
                text=source_text + "\n\nRewritten clarifying sentence.",
                provider="stealthwriter_training",
                version="Legacy 5.1",
                meta=meta,
            )

    cfg = DocumentCollectorConfig(count=2, seed=500, output_dir=str(tmp_path / "sel"))
    result = TeacherDocumentCollector(cfg, provider=Seq()).run()
    assert result.summary["successful"] == 0
    assert result.manifest["rejection_reasons"].get("SELECTION_NOT_VERIFIED") == 1
    assert result.manifest["rejection_reasons"].get("RESULT_STAGE_MISMATCH") == 1


def test_successful_commit_telemetry(tmp_path: Path, monkeypatch):
    _patch_docs(monkeypatch, [_mini_doc()])
    provider = _CountingProvider(fail_times=0)
    cfg = DocumentCollectorConfig(count=1, seed=500, output_dir=str(tmp_path / "ok"))
    result = TeacherDocumentCollector(cfg, provider=provider).run()
    assert result.summary["successful"] == 1
    assert result.manifest["sft_built"] is False
    row = json.loads((tmp_path / "ok" / "documents.jsonl").read_text().splitlines()[0])
    assert row["teacher_model"] == "Legacy 5.1"
    assert row["teacher_level"] == 8
    assert row["teacher_meta"]["selection_verified"] is True
    assert row["teacher_meta"]["last_successful_stage"] == "RESULT_EXTRACTED"
    assert row["heading_preservation"] == "exact"
    assert "ratio" in row
    assert "jaccard" in row
    assert "elapsed_seconds" in row
    summary = json.loads((tmp_path / "ok" / "collection_summary.json").read_text())
    assert summary["successful"] == 1
    assert summary["heading_preservation_rate"] == 1.0


def test_mock_provider_forbidden_without_flag(tmp_path: Path):
    cfg = DocumentCollectorConfig(
        count=1,
        seed=500,
        output_dir=str(tmp_path / "mock"),
        provider_name="mock_teacher",
        allow_mock_provider=False,
        dry_run=False,
    )
    with pytest.raises(ValueError, match="mock_teacher"):
        TeacherDocumentCollector(cfg)


def test_provider_factory_gets_single_internal_retry(monkeypatch, tmp_path: Path):
    captured: dict = {}

    class FakeBridge:
        def __init__(self, config):
            captured["max_retries"] = config.max_retries

        def rewrite(self, source_text: str, **kwargs):
            return TeacherResult(
                text=source_text + "\n\nRewritten clarifying sentence.",
                provider="stealthwriter_training",
                version="Legacy 5.1",
                meta=_ok_meta(),
            )

    monkeypatch.setattr(
        "services.humanizer_training.teacher.provider.StealthWriterBridgeProvider",
        FakeBridge,
    )
    _patch_docs(monkeypatch, [_mini_doc()])
    cfg = DocumentCollectorConfig(
        count=1,
        seed=500,
        output_dir=str(tmp_path / "factory"),
        provider_name="stealthwriter",
        max_attempts_per_document=2,
        max_retries=2,
    )
    # Build without injecting provider so factory path runs.
    collector = TeacherDocumentCollector(cfg)
    assert captured["max_retries"] == 1
    result = collector.run()
    assert result.summary["successful"] == 1
    assert result.manifest["provider"]["provider_internal_retries"] == 1
    assert result.manifest["provider"]["max_attempts_per_document"] == 2
