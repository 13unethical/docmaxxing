"""Resumable offline document-level teacher collector (one-call mode for <=5000 words).

Retry policy (large unattended runs):
- Collector owns a bounded attempt budget (`max_attempts_per_document`, default 2).
- Browser provider is constructed with `max_retries=1` so each collector attempt maps
  to exactly one `_humanize_once` call (no nested collector × provider multiplication).
- Failed documents are recorded and skipped; the run continues.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.humanizer_engine.heading_utils import join_body_and_references, split_off_references
from services.humanizer_training.heading_protection import (
    HeadingRestoreError,
    protect_training_headings,
    restore_training_headings,
)
from services.humanizer_training.teacher.documents.generator import (
    generate_documents,
    summarize_document_plan,
)
from services.humanizer_training.teacher.documents.quality import evaluate_teacher_document
from services.humanizer_training.teacher.documents.schema import (
    DocumentCollectorConfig,
    HumanizerTeacherDocument,
    TeacherChunkRecord,
)
from services.humanizer_training.teacher.provider import (
    ProviderFactory,
    TeacherProvider,
    TeacherProviderError,
)
from services.humanizer_training.teacher.config import TeacherProviderConfig

_CANONICAL_MODEL = "Legacy 5.1"
_CANONICAL_UI_LABEL = "Ghost 5.1 Legacy"
_CANONICAL_LEVEL = 8
_REQUIRED_RESULT_STAGE = "RESULT_EXTRACTED"
# Provider-internal retries are always forced to 1 when built by this collector.
_PROVIDER_INTERNAL_RETRIES = 1

_NON_RETRYABLE = frozenset(
    {
        "MODEL_SELECTION_FAILED",
        "LEVEL_SELECTION_FAILED",
        "LOGIN_REQUIRED",
        "HEADING_RESTORE_FAILED",
        "WRONG_MODEL",
        "WRONG_LEVEL",
        "SELECTION_NOT_VERIFIED",
        "RESULT_STAGE_MISMATCH",
        "MOCK_PROVIDER_FORBIDDEN",
        "DUPLICATE_SOURCE",
        "DUPLICATE_DOCUMENT_ID",
        "EMPTY_TEACHER",
        "UNCHANGED",
        "REFERENCE_CORRUPTION",
        "TEXT_TOO_LONG",
        "EMPTY_INPUT",
        "EMPTY_SOURCE",
    }
)
_FORBIDDEN_FAILURE_KEYS = frozenset(
    {
        "source_text",
        "teacher_text",
        "teacher_output",
        "text",
        "body",
        "cookies",
        "credentials",
        "api_key",
        "authorization",
        "password",
        "session",
    }
)


@dataclass(slots=True)
class DocumentCollectionResult:
    manifest: dict[str, Any]
    sampling_plan: dict[str, Any]
    summary: dict[str, Any]


class TeacherDocumentCollector:
    """Collect full-document teacher pairs. Does not call production BrowserService."""

    def __init__(
        self,
        config: DocumentCollectorConfig,
        provider: TeacherProvider | None = None,
    ) -> None:
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.documents_path = self.output_dir / "documents.jsonl"
        self.manifest_path = self.output_dir / "manifest.json"
        self.checkpoint_path = self.output_dir / "checkpoint.json"
        self.failures_path = self.output_dir / "failures.jsonl"
        self.failed_documents_path = self.output_dir / "failed_documents.jsonl"
        self.summary_path = self.output_dir / "collection_summary.json"
        self._provider_injected = provider is not None
        if provider is not None:
            self.provider = provider
        elif config.dry_run:
            self.provider = None
        else:
            provider_name = (config.provider_name or "").strip().lower()
            if provider_name == "mock_teacher" and not config.allow_mock_provider:
                raise ValueError(
                    "mock_teacher provider is forbidden for real document collection "
                    "(fail-closed). Pass allow_mock_provider only in tests."
                )
            # CRITICAL: provider internal retries = 1. Collector owns attempt budget.
            provider_cfg = TeacherProviderConfig(
                provider_name=config.provider_name,
                model=config.model,
                level=config.level,
                timeout_s=config.timeout_s,
                max_retries=_PROVIDER_INTERNAL_RETRIES,
                extra={
                    "explicit_model": True,
                    "explicit_level": True,
                    "explicit_timeout": True,
                    "provider_internal_retries": _PROVIDER_INTERNAL_RETRIES,
                },
            )
            self.provider = ProviderFactory(provider_cfg).build()

    def run(self) -> DocumentCollectionResult:
        run_started = time.monotonic()
        docs, plan = generate_documents(count=int(self.config.count), seed=int(self.config.seed))
        sampling = summarize_document_plan(plan)

        existing_success_ids = self._load_existing_ids()
        existing_source_hashes = self._load_existing_source_hashes()
        checkpoint = self._load_checkpoint()

        if not self.config.dry_run:
            self._enforce_resume_policy(checkpoint, existing_success_ids)

        completed: set[str] = set()
        successful_ids = set(existing_success_ids)
        failed_ids: set[str] = set(checkpoint.get("failed_document_ids") or [])
        skipped_ids: set[str] = set(checkpoint.get("skipped_document_ids") or [])

        if self.config.resume:
            completed.update(checkpoint.get("completed_document_ids") or [])
            completed.update(existing_success_ids)
            completed.update(failed_ids)
            completed.update(skipped_ids)
        prior_completed = set(completed)

        if self.config.dry_run:
            word_stats = _word_stats([d.word_count for d in docs])
            marker_stats = _marker_stats([d.source_text for d in docs])
            section_stats = {
                "mean_sections": round(sum(d.section_count for d in docs) / max(1, len(docs)), 2),
                "histogram": plan.section_count_histogram,
            }
            summary = self._empty_summary(requested=len(docs), wall_s=0.0)
            summary["dry_run"] = True
            manifest = self._build_manifest(
                sampling_plan=sampling,
                completed_count=len(completed),
                success_count=0,
                rejected_count=0,
                skipped_too_large=0,
                provider_errors=0,
                reject_reasons=Counter(),
                flags=Counter(),
                dry_run=True,
                word_stats=word_stats,
                marker_stats=marker_stats,
                section_stats=section_stats,
                failure_codes=Counter(),
                failure_stages=Counter(),
                summary=summary,
            )
            self._write_manifest(manifest)
            self._write_summary(summary)
            preview_path = self.output_dir / "dry_run_sources.jsonl"
            with preview_path.open("w", encoding="utf-8") as fh:
                for d in docs:
                    fh.write(
                        json.dumps(
                            {
                                "document_id": d.document_id,
                                "domain": d.domain,
                                "topic": d.topic,
                                "document_type": d.document_type,
                                "angle": d.angle,
                                "combination_key": d.combination_key,
                                "seed": d.seed,
                                "word_count": d.word_count,
                                "body_word_count": d.body_word_count,
                                "references_present": d.references_present,
                                "section_count": d.section_count,
                                "section_titles": d.section_titles,
                                "length_bucket": d.length_bucket,
                                "generation_prompt": d.generation_prompt,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            return DocumentCollectionResult(
                manifest=manifest, sampling_plan=sampling, summary=summary
            )

        success_count = 0
        rejected_count = 0
        skipped_too_large = 0
        provider_errors = 0
        timeout_count = 0
        reject_reasons: Counter[str] = Counter()
        flags_counter: Counter[str] = Counter()
        failure_codes: Counter[str] = Counter()
        failure_stages: Counter[str] = Counter()
        ratio_sum = 0.0
        ratio_n = 0
        heading_exact = 0
        heading_total = 0
        refs_ok = 0
        refs_total = 0
        max_attempts = self._attempt_budget()

        for doc in docs:
            if doc.document_id in completed:
                continue
            if doc.document_id in successful_ids:
                # Never re-commit a successfully archived sample.
                completed.add(doc.document_id)
                self._save_checkpoint(completed, successful_ids, failed_ids, skipped_ids)
                continue

            source_hash = _source_hash(doc.source_text)
            if source_hash in existing_source_hashes:
                rejected_count += 1
                reject_reasons["DUPLICATE_SOURCE"] += 1
                failure_codes["DUPLICATE_SOURCE"] += 1
                self._record_failed_document(
                    doc=doc,
                    error_code="DUPLICATE_SOURCE",
                    error_message="Source text already committed in this archive",
                    attempt=0,
                )
                failed_ids.add(doc.document_id)
                completed.add(doc.document_id)
                self._save_checkpoint(completed, successful_ids, failed_ids, skipped_ids)
                continue

            if doc.word_count > int(self.config.max_provider_words) or doc.body_word_count > int(
                self.config.max_provider_words
            ):
                skipped_too_large += 1
                reject_reasons["DOCUMENT_TOO_LARGE"] += 1
                self._append_jsonl(
                    self.failures_path,
                    self._failure_record(
                        document_id=doc.document_id,
                        attempt=0,
                        error_code="DOCUMENT_TOO_LARGE",
                        error_message=(
                            f"words={doc.word_count} body={doc.body_word_count} "
                            f"> max={self.config.max_provider_words}"
                        ),
                        meta={"failed_stage": "PRECHECK"},
                        retryable=False,
                    ),
                )
                self._record_failed_document(
                    doc=doc,
                    error_code="DOCUMENT_TOO_LARGE",
                    error_message="Document exceeds max_provider_words",
                    attempt=0,
                )
                skipped_ids.add(doc.document_id)
                completed.add(doc.document_id)
                self._save_checkpoint(completed, successful_ids, failed_ids, skipped_ids)
                continue

            body, refs = split_off_references(doc.source_text)
            if not body.strip():
                rejected_count += 1
                reject_reasons["EMPTY_SOURCE"] += 1
                failure_codes["EMPTY_SOURCE"] += 1
                self._record_failed_document(
                    doc=doc,
                    error_code="EMPTY_SOURCE",
                    error_message="Empty body after reference split",
                    attempt=0,
                )
                failed_ids.add(doc.document_id)
                completed.add(doc.document_id)
                self._save_checkpoint(completed, successful_ids, failed_ids, skipped_ids)
                continue

            # Training-only: protect ## headings before StealthWriter, restore after.
            protected_body, protected_headings = protect_training_headings(body)

            teacher_body: str | None = None
            provider_name = "stealthwriter_training"
            provider_model = self.config.model
            provider_meta: dict[str, Any] = {}
            elapsed_s: float | None = None
            last_error_code: str | None = None

            for attempt in range(1, max_attempts + 1):
                attempt_started = time.monotonic()
                try:
                    assert self.provider is not None
                    result = self.provider.rewrite(
                        protected_body, document_id=doc.document_id
                    )
                    try:
                        teacher_body = restore_training_headings(
                            result.text, protected_headings
                        )
                    except HeadingRestoreError as restore_exc:
                        raise TeacherProviderError(
                            "HEADING_RESTORE_FAILED",
                            str(restore_exc),
                            meta={
                                "failed_stage": "HEADING_RESTORE",
                                "heading_index": getattr(restore_exc, "index", None),
                            },
                            retryable=False,
                        ) from restore_exc
                    provider_name = result.provider
                    provider_model = result.version
                    provider_meta = dict(result.meta or {})
                    elapsed_s = round(time.monotonic() - attempt_started, 3)
                    provider_meta.setdefault("elapsed_seconds", elapsed_s)
                    break
                except TeacherProviderError as exc:
                    last_error_code = exc.code
                    record = self._failure_record(
                        document_id=doc.document_id,
                        attempt=attempt,
                        error_code=exc.code,
                        error_message=exc.message,
                        meta=exc.meta,
                        retryable=exc.retryable,
                    )
                    self._append_jsonl(self.failures_path, record)
                    failure_codes[exc.code] += 1
                    stage = str(record.get("failed_stage") or "provider")
                    failure_stages[stage] += 1
                    if exc.code == "TIMEOUT":
                        timeout_count += 1
                    print(
                        f"[doc-collector] provider failure doc={doc.document_id} "
                        f"code={exc.code} stage={stage} attempt={attempt}/{max_attempts} "
                        f"retryable={exc.retryable}",
                        flush=True,
                    )
                    if (
                        (not exc.retryable)
                        or exc.code in _NON_RETRYABLE
                        or attempt >= max_attempts
                    ):
                        provider_errors += 1
                        teacher_body = None
                        break
                    time.sleep(min(15.0, 1.0 * (2 ** (attempt - 1))))
                except Exception as exc:  # noqa: BLE001
                    code, detail = _parse_provider_exception(exc)
                    last_error_code = code
                    retryable = code not in _NON_RETRYABLE
                    record = self._failure_record(
                        document_id=doc.document_id,
                        attempt=attempt,
                        error_code=code,
                        error_message=detail,
                        meta={},
                        retryable=retryable,
                    )
                    self._append_jsonl(self.failures_path, record)
                    failure_codes[code] += 1
                    stage = str(record.get("failed_stage") or "provider")
                    failure_stages[stage] += 1
                    if code == "TIMEOUT":
                        timeout_count += 1
                    print(
                        f"[doc-collector] provider failure doc={doc.document_id} "
                        f"code={code} stage={stage} attempt={attempt}/{max_attempts} "
                        f"retryable={retryable}",
                        flush=True,
                    )
                    if (not retryable) or attempt >= max_attempts:
                        provider_errors += 1
                        teacher_body = None
                        break
                    time.sleep(min(15.0, 1.0 * (2 ** (attempt - 1))))

            if teacher_body is None:
                self._record_failed_document(
                    doc=doc,
                    error_code=last_error_code or "PROVIDER_FAILED",
                    error_message="Provider did not return usable teacher body",
                    attempt=max_attempts,
                )
                failed_ids.add(doc.document_id)
                completed.add(doc.document_id)
                self._save_checkpoint(completed, successful_ids, failed_ids, skipped_ids)
                continue

            policy_error = self._policy_gate(
                provider_name=provider_name,
                provider_model=provider_model,
                provider_meta=provider_meta,
            )
            if policy_error is not None:
                code, message = policy_error
                rejected_count += 1
                reject_reasons[code] += 1
                failure_codes[code] += 1
                self._append_jsonl(
                    self.failures_path,
                    self._failure_record(
                        document_id=doc.document_id,
                        attempt=max_attempts,
                        error_code=code,
                        error_message=message,
                        meta={**provider_meta, "failed_stage": "POLICY_GATE"},
                        retryable=False,
                    ),
                )
                self._record_failed_document(
                    doc=doc,
                    error_code=code,
                    error_message=message,
                    attempt=max_attempts,
                )
                failed_ids.add(doc.document_id)
                completed.add(doc.document_id)
                self._save_checkpoint(completed, successful_ids, failed_ids, skipped_ids)
                continue

            merged = join_body_and_references(teacher_body, refs)
            chunk = TeacherChunkRecord(
                chunk_id=f"{doc.document_id}-c0",
                index=0,
                source_text=body,
                teacher_text=teacher_body,
                source_word_count=_wc(body),
                teacher_word_count=_wc(teacher_body),
                status="completed",
                quality_flags=[],
            )
            quality = evaluate_teacher_document(
                doc.source_text,
                merged,
                max_words=int(self.config.max_provider_words),
                source_refs=refs,
                teacher_refs=refs,  # references are passthrough-original
                chunks=[chunk.to_dict()],
            )
            # References should be unchanged because we reattached originals
            if refs.strip() and "REFERENCES_CHANGED" in quality.flags:
                quality.flags = [f for f in quality.flags if f != "REFERENCES_CHANGED"]

            # Hard fail if references were corrupted despite passthrough intent.
            if refs.strip():
                _, merged_refs = split_off_references(merged)
                if _normalize(refs) != _normalize(merged_refs):
                    quality.reject_reasons = sorted(
                        set(quality.reject_reasons) | {"REFERENCE_CORRUPTION"}
                    )
                    quality.accepted = False

            if not quality.accepted:
                rejected_count += 1
                reject_reasons.update(quality.reject_reasons)
                for reason in quality.reject_reasons:
                    failure_codes[reason] += 1
                self._record_failed_document(
                    doc=doc,
                    error_code=(quality.reject_reasons[0] if quality.reject_reasons else "REJECTED"),
                    error_message=",".join(quality.reject_reasons),
                    attempt=max_attempts,
                    extra={"quality_flags": list(quality.flags)},
                )
                failed_ids.add(doc.document_id)
                completed.add(doc.document_id)
                self._save_checkpoint(completed, successful_ids, failed_ids, skipped_ids)
                continue

            flags_counter.update(quality.flags)
            src_wc = _wc(doc.source_text)
            tgt_wc = _wc(merged)
            body_src_wc = _wc(body)
            body_tgt_wc = _wc(teacher_body)
            ratio = (tgt_wc / float(src_wc)) if src_wc else 0.0
            jaccard = _token_jaccard(body, teacher_body)
            heading_status = (
                "mismatch" if "HEADING_MISMATCH" in quality.flags else "exact"
            )
            if refs.strip():
                references_status = "unchanged"
                refs_total += 1
                refs_ok += 1
            else:
                references_status = "no_references"

            heading_total += 1
            if heading_status == "exact":
                heading_exact += 1

            ratio_sum += ratio
            ratio_n += 1

            record = HumanizerTeacherDocument(
                document_id=doc.document_id,
                source_text=doc.source_text,
                teacher_text=merged,
                domain=doc.domain,
                document_type=doc.document_type,
                language=doc.language,
                seed=int(doc.seed),
                teacher_provider=provider_name,
                teacher_model=provider_model,
                teacher_level=int(self.config.level),
                teacher_timeout=float(self.config.timeout_s),
                source_word_count=src_wc,
                teacher_word_count=tgt_wc,
                source_body_word_count=body_src_wc,
                teacher_body_word_count=body_tgt_wc,
                references_present=bool(refs.strip()),
                references_word_count=_wc(refs),
                quality_flags=list(quality.flags),
                reject_reasons=[],
                created_at=datetime.now(timezone.utc).isoformat(),
                section_count=doc.section_count,
                section_titles=list(doc.section_titles),
                chunks=[chunk],
                status="accepted",
            )
            payload = record.to_dict()
            payload["topic"] = getattr(doc, "topic", "") or ""
            payload["angle"] = getattr(doc, "angle", "") or ""
            payload["combination_key"] = getattr(doc, "combination_key", "") or ""
            payload["generation_prompt"] = getattr(doc, "generation_prompt", "") or ""
            payload["ratio"] = round(ratio, 6)
            payload["jaccard"] = round(jaccard, 6)
            payload["heading_preservation"] = heading_status
            payload["references_preservation"] = references_status
            payload["elapsed_seconds"] = elapsed_s
            safe_meta = {
                k: provider_meta[k]
                for k in (
                    "requested_model",
                    "verified_model",
                    "ui_model_label",
                    "requested_level",
                    "verified_level",
                    "selection_verified",
                    "last_successful_stage",
                )
                if k in provider_meta
            }
            safe_meta.setdefault("selection_verified", True)
            safe_meta.setdefault("last_successful_stage", _REQUIRED_RESULT_STAGE)
            safe_meta.setdefault("verified_model", provider_model)
            safe_meta.setdefault("ui_model_label", _CANONICAL_UI_LABEL)
            safe_meta.setdefault("verified_level", int(self.config.level))
            payload["teacher_meta"] = safe_meta
            self._append_jsonl(self.documents_path, payload)
            success_count += 1
            successful_ids.add(doc.document_id)
            existing_source_hashes.add(source_hash)
            completed.add(doc.document_id)
            self._save_checkpoint(completed, successful_ids, failed_ids, skipped_ids)
            if self.config.delay_s > 0:
                time.sleep(float(self.config.delay_s))

        wall_s = round(time.monotonic() - run_started, 3)
        prior_success = len(existing_success_ids)
        total_success_in_archive = prior_success + success_count
        summary = {
            "requested": int(self.config.count),
            "successful": int(success_count),
            "successful_in_archive": int(total_success_in_archive),
            "failed": int(provider_errors + rejected_count),
            "skipped": int(skipped_too_large),
            "already_completed_on_resume": int(
                sum(1 for d in docs if d.document_id in prior_completed)
            ),
            "success_rate": round(success_count / max(1, int(self.config.count)), 4),
            "timeout_count": int(timeout_count),
            "average_output_source_ratio": round(ratio_sum / ratio_n, 4) if ratio_n else None,
            "heading_preservation_rate": (
                round(heading_exact / heading_total, 4) if heading_total else None
            ),
            "reference_preservation_rate": (
                round(refs_ok / refs_total, 4) if refs_total else None
            ),
            "quality_flag_counts": dict(sorted(flags_counter.items())),
            "elapsed_wall_seconds": wall_s,
            "estimated_avg_seconds_per_successful": (
                round(wall_s / success_count, 3) if success_count else None
            ),
            "max_attempts_per_document": max_attempts,
            "provider_internal_retries": _PROVIDER_INTERNAL_RETRIES,
            "seed": int(self.config.seed),
            "resume": bool(self.config.resume),
            "dry_run": False,
        }

        word_stats = _word_stats([d.word_count for d in docs])
        marker_stats = _marker_stats([d.source_text for d in docs])
        section_stats = {
            "mean_sections": round(sum(d.section_count for d in docs) / max(1, len(docs)), 2),
            "histogram": plan.section_count_histogram,
        }
        manifest = self._build_manifest(
            sampling_plan=sampling,
            completed_count=len(completed),
            success_count=success_count,
            rejected_count=rejected_count,
            skipped_too_large=skipped_too_large,
            provider_errors=provider_errors,
            reject_reasons=reject_reasons,
            flags=flags_counter,
            dry_run=False,
            word_stats=word_stats,
            marker_stats=marker_stats,
            section_stats=section_stats,
            failure_codes=failure_codes,
            failure_stages=failure_stages,
            summary=summary,
        )
        self._write_manifest(manifest)
        self._write_summary(summary)
        return DocumentCollectionResult(
            manifest=manifest, sampling_plan=sampling, summary=summary
        )

    def _attempt_budget(self) -> int:
        # Prefer explicit max_attempts_per_document; fall back to legacy max_retries.
        raw = getattr(self.config, "max_attempts_per_document", None)
        if raw is None:
            raw = getattr(self.config, "max_retries", 2)
        return max(1, min(2, int(raw)))

    def _enforce_resume_policy(
        self,
        checkpoint: dict[str, Any],
        existing_success_ids: set[str],
    ) -> None:
        has_state = bool(existing_success_ids) or bool(checkpoint) or self.failures_path.exists()
        if has_state and not self.config.resume:
            raise FileExistsError(
                f"Output dir already has collection state ({self.output_dir}). "
                "Re-run with --resume to continue, or choose a new --output-dir."
            )
        if not self.config.resume:
            return
        ck_seed = checkpoint.get("seed")
        if ck_seed is not None and int(ck_seed) != int(self.config.seed):
            raise ValueError(
                f"Resume seed mismatch: checkpoint seed={ck_seed} "
                f"vs requested seed={self.config.seed}"
            )
        ck_count = checkpoint.get("count")
        if ck_count is not None and int(ck_count) != int(self.config.count):
            raise ValueError(
                f"Resume count mismatch: checkpoint count={ck_count} "
                f"vs requested count={self.config.count}"
            )

    def _policy_gate(
        self,
        *,
        provider_name: str,
        provider_model: str,
        provider_meta: dict[str, Any],
    ) -> tuple[str, str] | None:
        name = (provider_name or "").lower()
        if "mock" in name and not self.config.allow_mock_provider:
            return "MOCK_PROVIDER_FORBIDDEN", f"provider={provider_name}"

        verified_model = str(
            provider_meta.get("verified_model") or provider_model or ""
        ).strip()
        ui_label = str(provider_meta.get("ui_model_label") or "").strip()
        if verified_model != _CANONICAL_MODEL:
            return (
                "WRONG_MODEL",
                f"verified={verified_model!r} version={provider_model!r} "
                f"expected={_CANONICAL_MODEL!r}",
            )
        if str(provider_model or "").strip() != _CANONICAL_MODEL:
            return (
                "WRONG_MODEL",
                f"provider version={provider_model!r} expected={_CANONICAL_MODEL!r}",
            )
        if not ui_label:
            return (
                "WRONG_MODEL",
                f"ui_model_label missing; expected={_CANONICAL_UI_LABEL!r}",
            )
        if ui_label != _CANONICAL_UI_LABEL:
            return (
                "WRONG_MODEL",
                f"ui_model_label={ui_label!r} expected={_CANONICAL_UI_LABEL!r}",
            )

        verified_level = provider_meta.get("verified_level", self.config.level)
        try:
            level_i = int(verified_level)
        except (TypeError, ValueError):
            return "WRONG_LEVEL", f"verified_level={verified_level!r}"
        if level_i != _CANONICAL_LEVEL or int(self.config.level) != _CANONICAL_LEVEL:
            return (
                "WRONG_LEVEL",
                f"verified_level={level_i} config_level={self.config.level} "
                f"expected={_CANONICAL_LEVEL}",
            )

        if not bool(provider_meta.get("selection_verified")):
            return "SELECTION_NOT_VERIFIED", "selection_verified must be true"

        stage = str(provider_meta.get("last_successful_stage") or "").strip()
        if stage != _REQUIRED_RESULT_STAGE:
            return (
                "RESULT_STAGE_MISMATCH",
                f"last_successful_stage={stage!r} expected={_REQUIRED_RESULT_STAGE!r}",
            )
        return None

    def _record_failed_document(
        self,
        *,
        doc: Any,
        error_code: str,
        error_message: str,
        attempt: int,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Archive failed source documents (never delete sources)."""
        payload = {
            "document_id": doc.document_id,
            "error_code": error_code,
            "error_message": error_message,
            "attempt": int(attempt),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain": doc.domain,
            "document_type": doc.document_type,
            "topic": getattr(doc, "topic", "") or "",
            "angle": getattr(doc, "angle", "") or "",
            "combination_key": getattr(doc, "combination_key", "") or "",
            "seed": int(doc.seed),
            "word_count": int(doc.word_count),
            "body_word_count": int(doc.body_word_count),
            "source_text": doc.source_text,
        }
        if extra:
            payload.update(extra)
        self._append_jsonl(self.failed_documents_path, payload)

    def _failure_record(
        self,
        *,
        document_id: str,
        attempt: int,
        error_code: str,
        error_message: str | None,
        meta: dict[str, Any],
        retryable: bool,
    ) -> dict[str, Any]:
        safe_meta = {
            k: v
            for k, v in (meta or {}).items()
            if k.lower() not in _FORBIDDEN_FAILURE_KEYS and not isinstance(v, (bytes, bytearray))
        }
        for key in list(safe_meta.keys()):
            val = safe_meta[key]
            if isinstance(val, str) and len(val) > 2000:
                safe_meta[key] = val[:200] + "…<truncated>"
        return {
            "document_id": document_id,
            "stage": "provider",
            "error_code": error_code,
            "error_message": error_message,
            "attempt": int(attempt),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": safe_meta.get("provider") or "stealthwriter_training",
            "model": safe_meta.get("requested_model") or self.config.model,
            "level": safe_meta.get("requested_level")
            if safe_meta.get("requested_level") is not None
            else int(self.config.level),
            "requested_model": safe_meta.get("requested_model") or self.config.model,
            "requested_level": safe_meta.get("requested_level")
            if safe_meta.get("requested_level") is not None
            else int(self.config.level),
            "visible_model_label": safe_meta.get("visible_model_label"),
            "visible_level": safe_meta.get("visible_level"),
            "failed_stage": safe_meta.get("failed_stage"),
            "last_successful_stage": safe_meta.get("last_successful_stage"),
            "current_url": safe_meta.get("current_url"),
            "retryable": bool(retryable),
            "screenshot_path": safe_meta.get("screenshot_path"),
            "selection_verified": False,
            "max_attempts_per_document": self._attempt_budget(),
            "provider_internal_retries": _PROVIDER_INTERNAL_RETRIES,
        }

    def _load_existing_ids(self) -> set[str]:
        ids: set[str] = set()
        if not self.documents_path.exists():
            return ids
        for line in self.documents_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            did = str(payload.get("document_id") or "").strip()
            if did:
                ids.add(did)
        return ids

    def _load_existing_source_hashes(self) -> set[str]:
        hashes: set[str] = set()
        if not self.documents_path.exists():
            return hashes
        for line in self.documents_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            src = payload.get("source_text")
            if isinstance(src, str) and src.strip():
                hashes.add(_source_hash(src))
        return hashes

    def _load_checkpoint(self) -> dict[str, Any]:
        if not self.checkpoint_path.exists():
            return {}
        try:
            return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_checkpoint(
        self,
        completed_document_ids: set[str],
        successful_document_ids: set[str],
        failed_document_ids: set[str],
        skipped_document_ids: set[str],
    ) -> None:
        payload = {
            "completed_document_ids": sorted(completed_document_ids),
            "successful_document_ids": sorted(successful_document_ids),
            "failed_document_ids": sorted(failed_document_ids),
            "skipped_document_ids": sorted(skipped_document_ids),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "seed": int(self.config.seed),
            "count": int(self.config.count),
            "max_attempts_per_document": self._attempt_budget(),
            "provider_internal_retries": _PROVIDER_INTERNAL_RETRIES,
        }
        self.checkpoint_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _empty_summary(self, *, requested: int, wall_s: float) -> dict[str, Any]:
        return {
            "requested": requested,
            "successful": 0,
            "successful_in_archive": 0,
            "failed": 0,
            "skipped": 0,
            "success_rate": 0.0,
            "timeout_count": 0,
            "average_output_source_ratio": None,
            "heading_preservation_rate": None,
            "reference_preservation_rate": None,
            "quality_flag_counts": {},
            "elapsed_wall_seconds": wall_s,
            "estimated_avg_seconds_per_successful": None,
            "max_attempts_per_document": self._attempt_budget(),
            "provider_internal_retries": _PROVIDER_INTERNAL_RETRIES,
            "seed": int(self.config.seed),
            "resume": bool(self.config.resume),
            "dry_run": True,
        }

    def _build_manifest(
        self,
        *,
        sampling_plan: dict[str, Any],
        completed_count: int,
        success_count: int,
        rejected_count: int,
        skipped_too_large: int,
        provider_errors: int,
        reject_reasons: Counter[str],
        flags: Counter[str],
        dry_run: bool,
        word_stats: dict[str, Any],
        marker_stats: dict[str, Any],
        section_stats: dict[str, Any],
        failure_codes: Counter[str],
        failure_stages: Counter[str],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "dataset_type": "teacher_raw_documents",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "seed": int(self.config.seed),
            "requested_count": int(self.config.count),
            "dry_run": bool(dry_run),
            "resume": bool(self.config.resume),
            "provider": {
                "provider_name": "stealthwriter_training",
                "model": self.config.model,
                "ui_model_label": _CANONICAL_UI_LABEL,
                "level": int(self.config.level),
                "timeout_s": float(self.config.timeout_s),
                "max_attempts_per_document": self._attempt_budget(),
                "provider_internal_retries": _PROVIDER_INTERNAL_RETRIES,
                "max_retries": self._attempt_budget(),  # legacy field = collector budget
                "max_provider_words": int(self.config.max_provider_words),
                "mode": "one_call_document_leq_5000",
                "required_selection_verified": True,
                "required_result_stage": _REQUIRED_RESULT_STAGE,
            },
            "sampling_plan": sampling_plan,
            "word_stats": word_stats,
            "marker_stats": marker_stats,
            "section_stats": section_stats,
            "completed_document_ids": int(completed_count),
            "successful_documents_added": int(success_count),
            "rejected_count": int(rejected_count),
            "skipped_document_too_large": int(skipped_too_large),
            "provider_error_count": int(provider_errors),
            "failure_count": int(sum(failure_codes.values())),
            "failure_codes": dict(sorted(failure_codes.items())),
            "failure_stages": dict(sorted(failure_stages.items())),
            "rejection_reasons": dict(sorted(reject_reasons.items())),
            "quality_flags": dict(sorted(flags.items())),
            "collection_summary": summary,
            "documents_file": str(self.documents_path),
            "checkpoint_file": str(self.checkpoint_path),
            "failures_file": str(self.failures_path),
            "failed_documents_file": str(self.failed_documents_path),
            "summary_file": str(self.summary_path),
            "documents_sha256": _file_sha256(self.documents_path)
            if self.documents_path.exists()
            else None,
            "sft_built": False,
            "note": "Raw teacher archive only; SFT dataset is built separately.",
        }

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_summary(self, summary: dict[str, Any]) -> None:
        self.summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _parse_provider_exception(exc: Exception) -> tuple[str, str]:
    text = str(exc)
    if "StealthWriter teacher error:" in text:
        rest = text.split("StealthWriter teacher error:", 1)[1].strip()
        if "—" in rest:
            code, detail = rest.split("—", 1)
            return code.strip() or "UNKNOWN", detail.strip()
        return rest.strip() or "UNKNOWN", text
    return "EXCEPTION", text


def _wc(text: str) -> int:
    return len([p for p in (text or "").split() if p.strip()])


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _source_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


def _token_jaccard(left: str, right: str) -> float:
    a = set(_normalize(left).split())
    b = set(_normalize(right).split())
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def _word_stats(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"min": 0, "max": 0, "mean": 0, "median": 0, "count": 0}
    ordered = sorted(values)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {
        "min": min(values),
        "max": max(values),
        "mean": round(sum(values) / len(values), 1),
        "median": median,
        "count": len(values),
        "gt_5000": sum(1 for v in values if v > 5000),
        "lte_5000": sum(1 for v in values if v <= 5000),
    }


def _marker_stats(texts: list[str]) -> dict[str, Any]:
    import re

    patterns = {
        "citation": re.compile(r"\([^)]*?\d{4}[^)]*?\)|\[\d+\]"),
        "number": re.compile(r"\b\d+(?:\.\d+)?\b"),
        "year": re.compile(r"\b(?:19|20)\d{2}\b"),
        "percentage": re.compile(r"\b\d+(?:\.\d+)?%"),
        "url": re.compile(r"https?://\S+", re.I),
        "heading": re.compile(r"(?m)^##\s+.+$"),
    }
    n = max(1, len(texts))
    out: dict[str, Any] = {}
    for name, pat in patterns.items():
        hits = sum(1 for t in texts if pat.search(t or ""))
        out[name] = {"count": hits, "rate": round(hits / n, 3)}
    return out


def _file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()
