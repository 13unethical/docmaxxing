"""Legacy 5.1 / level-8 training eligibility for isolated teacher samples.

Fail-closed: missing selection telemetry is ineligible. Does not modify raw files.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


REQUIRED_PROVIDER = "stealthwriter_training"
REQUIRED_CANONICAL_MODEL = "Legacy 5.1"
REQUIRED_UI_MODEL = "Ghost 5.1 Legacy"
REQUIRED_LEVEL = 8
REQUIRED_STAGE = "RESULT_EXTRACTED"

REASON_WRONG_MODEL = "wrong_model"
REASON_WRONG_LEVEL = "wrong_level"
REASON_MOCK_DEFAULT = "mock_default_provider"
REASON_FAILED_NO_OUTPUT = "failed_no_output"
REASON_AMBIGUOUS_METADATA = "ambiguous_missing_metadata"
REASON_IDENTICAL_OUTPUT = "identical_output"
REASON_EMPTY_SOURCE = "empty_source"
REASON_WRONG_PROVIDER = "wrong_provider"
REASON_SELECTION_NOT_VERIFIED = "selection_not_verified"
REASON_STAGE_NOT_EXTRACTED = "stage_not_extracted"


@dataclass(slots=True)
class EligibilityVerdict:
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    provider: str | None = None
    requested_model: str | None = None
    verified_model: str | None = None
    ui_model_label: str | None = None
    requested_level: int | str | None = None
    verified_level: int | str | None = None
    selection_verified: bool | None = None
    result_stage: str | None = None
    has_source: bool = False
    has_output: bool = False
    output_differs: bool = False
    record_kind: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_teacher_sample(record: dict[str, Any]) -> EligibilityVerdict:
    """Evaluate one teacher record (document pair, short pair, or failure row)."""
    kind = _detect_kind(record)
    provider = _provider(record)
    requested_model, verified_model, ui_model = _models(record)
    requested_level, verified_level = _levels(record)
    selection_verified = _selection_verified(record)
    stage = _stage(record)
    source, output = _texts(record)
    has_source = bool(source.strip())
    has_output = bool(output.strip())
    differs = has_source and has_output and source.strip() != output.strip()

    reasons: list[str] = []

    if kind == "failure":
        reasons.append(REASON_FAILED_NO_OUTPUT)

    if _is_mock_or_default(provider, requested_model, verified_model, record):
        reasons.append(REASON_MOCK_DEFAULT)
    elif provider != REQUIRED_PROVIDER:
        reasons.append(REASON_WRONG_PROVIDER)

    # Proven selection telemetry is mandatory.
    missing_proof = (
        selection_verified is None
        or verified_model is None
        or ui_model is None
        or verified_level is None
        or stage is None
    )
    if missing_proof:
        reasons.append(REASON_AMBIGUOUS_METADATA)

    if selection_verified is not True:
        reasons.append(REASON_SELECTION_NOT_VERIFIED)

    if verified_model is not None and verified_model != REQUIRED_CANONICAL_MODEL:
        reasons.append(REASON_WRONG_MODEL)
    if ui_model is not None and ui_model != REQUIRED_UI_MODEL:
        reasons.append(REASON_WRONG_MODEL)
    # Claimed model without UI proof still counts as wrong when explicitly non-Legacy.
    claimed = requested_model or _teacher_version(record)
    if (
        verified_model is None
        and ui_model is None
        and claimed not in {None, REQUIRED_CANONICAL_MODEL, REQUIRED_UI_MODEL}
        and not _is_mock_or_default(provider, requested_model, verified_model, record)
    ):
        reasons.append(REASON_WRONG_MODEL)

    if verified_level is not None and _coerce_level(verified_level) != REQUIRED_LEVEL:
        reasons.append(REASON_WRONG_LEVEL)
    elif (
        verified_level is None
        and requested_level is not None
        and _coerce_level(requested_level) not in {None, REQUIRED_LEVEL}
    ):
        reasons.append(REASON_WRONG_LEVEL)

    if stage is not None and stage != REQUIRED_STAGE:
        reasons.append(REASON_STAGE_NOT_EXTRACTED)
    elif stage is None and kind != "failure":
        reasons.append(REASON_STAGE_NOT_EXTRACTED)

    if not has_source and kind != "failure":
        reasons.append(REASON_EMPTY_SOURCE)
    if kind != "failure":
        if not has_output:
            reasons.append(REASON_FAILED_NO_OUTPUT)
        elif has_source and not differs:
            reasons.append(REASON_IDENTICAL_OUTPUT)

    uniq: list[str] = []
    for r in reasons:
        if r not in uniq:
            uniq.append(r)

    eligible = (
        not uniq
        and provider == REQUIRED_PROVIDER
        and selection_verified is True
        and verified_model == REQUIRED_CANONICAL_MODEL
        and ui_model == REQUIRED_UI_MODEL
        and _coerce_level(verified_level) == REQUIRED_LEVEL
        and stage == REQUIRED_STAGE
        and has_source
        and has_output
        and differs
        and kind == "document_pair"
    )
    # Short pairs can be eligible only if they carry full proof fields (unlikely today).
    if (
        not uniq
        and kind == "short_pair"
        and provider == REQUIRED_PROVIDER
        and selection_verified is True
        and verified_model == REQUIRED_CANONICAL_MODEL
        and ui_model == REQUIRED_UI_MODEL
        and _coerce_level(verified_level) == REQUIRED_LEVEL
        and stage == REQUIRED_STAGE
        and has_source
        and has_output
        and differs
    ):
        eligible = True

    return EligibilityVerdict(
        eligible=eligible,
        reasons=uniq,
        provider=provider,
        requested_model=requested_model,
        verified_model=verified_model,
        ui_model_label=ui_model,
        requested_level=requested_level,
        verified_level=verified_level,
        selection_verified=selection_verified,
        result_stage=stage,
        has_source=has_source,
        has_output=has_output,
        output_differs=differs,
        record_kind=kind,
    )


def primary_quarantine_bucket(reasons: list[str]) -> str:
    """Map reason list to summary bucket (priority order)."""
    priority = [
        REASON_MOCK_DEFAULT,
        REASON_WRONG_PROVIDER,
        REASON_WRONG_MODEL,
        REASON_WRONG_LEVEL,
        REASON_FAILED_NO_OUTPUT,
        REASON_EMPTY_SOURCE,
        REASON_IDENTICAL_OUTPUT,
        REASON_AMBIGUOUS_METADATA,
        REASON_SELECTION_NOT_VERIFIED,
        REASON_STAGE_NOT_EXTRACTED,
    ]
    for key in priority:
        if key not in reasons:
            continue
        if key == REASON_WRONG_PROVIDER:
            return REASON_MOCK_DEFAULT
        if key in {REASON_EMPTY_SOURCE, REASON_IDENTICAL_OUTPUT}:
            return REASON_FAILED_NO_OUTPUT
        if key in {REASON_SELECTION_NOT_VERIFIED, REASON_STAGE_NOT_EXTRACTED}:
            return REASON_AMBIGUOUS_METADATA
        return key
    return REASON_AMBIGUOUS_METADATA


def _detect_kind(record: dict[str, Any]) -> str:
    if "error_code" in record and "document_id" in record and "teacher_text" not in record:
        return "failure"
    if "document_id" in record and ("teacher_text" in record or "teacher_meta" in record):
        return "document_pair"
    if "source_id" in record or "teacher_config" in record or "target_text" in record:
        return "short_pair"
    return "other"


def _provider(record: dict[str, Any]) -> str | None:
    for key in ("teacher_provider", "provider"):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    cfg = record.get("teacher_config")
    if isinstance(cfg, dict):
        val = cfg.get("provider_name")
        if isinstance(val, str) and val.strip():
            return val.strip()
    meta = record.get("teacher_meta") or record.get("meta") or {}
    if isinstance(meta, dict):
        val = meta.get("provider_name") or meta.get("provider")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _teacher_version(record: dict[str, Any]) -> str | None:
    val = record.get("teacher_version") or record.get("teacher_model")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _models(record: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    meta = record.get("teacher_meta") if isinstance(record.get("teacher_meta"), dict) else {}
    cfg = record.get("teacher_config") if isinstance(record.get("teacher_config"), dict) else {}
    requested = (
        meta.get("requested_model")
        or record.get("requested_model")
        or cfg.get("model")
        or record.get("teacher_model")
        or record.get("model")
    )
    verified = meta.get("verified_model")
    ui = meta.get("ui_model_label") or record.get("visible_model_label")
    return _as_str(requested), _as_str(verified), _as_str(ui)


def _levels(record: dict[str, Any]) -> tuple[Any, Any]:
    meta = record.get("teacher_meta") if isinstance(record.get("teacher_meta"), dict) else {}
    cfg = record.get("teacher_config") if isinstance(record.get("teacher_config"), dict) else {}
    if "requested_level" in meta:
        requested = meta.get("requested_level")
    elif "requested_level" in record:
        requested = record.get("requested_level")
    elif "level" in cfg:
        requested = cfg.get("level")
    elif "teacher_level" in record:
        requested = record.get("teacher_level")
    elif "level" in record:
        requested = record.get("level")
    else:
        requested = None
    verified = meta.get("verified_level") if "verified_level" in meta else None
    return requested, verified


def _selection_verified(record: dict[str, Any]) -> bool | None:
    meta = record.get("teacher_meta") if isinstance(record.get("teacher_meta"), dict) else {}
    if "selection_verified" in meta:
        return bool(meta.get("selection_verified"))
    if "selection_verified" in record:
        return bool(record.get("selection_verified"))
    return None


def _stage(record: dict[str, Any]) -> str | None:
    meta = record.get("teacher_meta") if isinstance(record.get("teacher_meta"), dict) else {}
    if meta.get("last_successful_stage"):
        return str(meta.get("last_successful_stage"))
    if record.get("last_successful_stage"):
        return str(record.get("last_successful_stage"))
    return None


def _texts(record: dict[str, Any]) -> tuple[str, str]:
    source = record.get("source_text") or ""
    output = record.get("teacher_text") or record.get("target_text") or ""
    if not isinstance(source, str):
        source = str(source or "")
    if not isinstance(output, str):
        output = ""
    # Ignore non-string teacher_output blobs for pair eligibility.
    return source, output


def _is_mock_or_default(
    provider: str | None,
    requested_model: str | None,
    verified_model: str | None,
    record: dict[str, Any],
) -> bool:
    cfg = record.get("teacher_config") if isinstance(record.get("teacher_config"), dict) else {}
    level_raw = cfg.get("level")
    if provider in {"mock_teacher", "mock"}:
        return True
    if requested_model == "mock-v1" or verified_model == "mock-v1":
        return True
    if record.get("teacher_version") == "mock-v1":
        return True
    if record.get("teacher_model") == "mock-v1":
        return True
    if str(level_raw).strip().lower() == "default":
        return True
    if provider and "mock" in provider.lower():
        return True
    return False


def _coerce_level(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, int):
        return raw
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _as_str(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None
