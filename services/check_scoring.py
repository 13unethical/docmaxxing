"""Weighted scoring and action plan — no AI."""

from __future__ import annotations

from typing import Any

_CHECK_REASONS: dict[str, tuple[str, str]] = {
    "word_count": ("requirements_match", "требуется бриф"),
    "sections": ("structure", "требуется бриф"),
    "references": ("references", "требуется бриф"),
    "in_text_citations": ("references", "требуется бриф"),
    "formatting": ("formatting", "требуется .docx"),
    "academic_style": ("clarity_organization", "требуется бриф"),
}


def _active_validations(validations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        v
        for v in validations
        if v.get("status") not in ("SKIP", "NOT_APPLICABLE", "NOT_CHECKED", "CANNOT_VERIFY")
        and float(v.get("weight") or 0) > 0
    ]


def compute_readiness_score(validations: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalised score: Σ(w×c) / Σ(w) × 100 over applied checks."""
    active = _active_validations(validations)
    if not active:
        return {
            "score": 0,
            "applicable_weight": 0.0,
            "checks_applied": 0,
            "earned": 0.0,
        }
    total_weight = sum(float(v["weight"]) for v in active)
    earned = sum(float(v["weight"]) * float(v.get("completion") or 0) for v in active)
    if total_weight <= 0:
        return {
            "score": 0,
            "applicable_weight": 0.0,
            "checks_applied": 0,
            "earned": 0.0,
        }
    score = int(round(earned / total_weight * 100))
    return {
        "score": score,
        "applicable_weight": round(total_weight, 2),
        "checks_applied": len(active),
        "earned": round(earned, 4),
    }


def score_to_verdict(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Needs improvement"
    return "Major issues"


_CATEGORY_LABELS = {
    "requirements_match": "Requirements match",
    "structure": "Structure",
    "formatting": "Formatting",
    "references": "References / citations",
    "clarity_organization": "Clarity of organization",
}


def validations_to_categories(validations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group validations into category scores; unchecked categories are NOT_CHECKED."""
    buckets: dict[str, list[float]] = {k: [] for k in _CATEGORY_LABELS}
    for v in validations:
        cat = v.get("category") or "requirements_match"
        if cat not in buckets:
            buckets[cat] = []
        w = float(v.get("weight") or 0)
        if w <= 0 or v.get("status") in ("SKIP", "NOT_APPLICABLE", "NOT_CHECKED", "CANNOT_VERIFY"):
            continue
        buckets[cat].append(float(v.get("completion") or 0) * 100)

    out: dict[str, dict[str, Any]] = {}
    for key, label in _CATEGORY_LABELS.items():
        scores = buckets.get(key) or []
        if not scores:
            out[key] = {"score": None, "label": label, "status": "NOT_CHECKED"}
        else:
            avg = int(round(sum(scores) / len(scores)))
            out[key] = {"score": avg, "label": label, "status": "CHECKED"}
    return out


def build_not_checked(
    *,
    structured: dict[str, Any],
    validations: list[dict[str, Any]],
    has_docx: bool,
) -> list[dict[str, str]]:
    """Checks that were not run, with a short reason."""
    applied_ids = {str(v.get("id")) for v in validations if float(v.get("weight") or 0) > 0}
    items: list[dict[str, str]] = []

    candidates: list[str] = []
    if structured.get("word_min") is not None or structured.get("word_max") is not None:
        candidates.append("word_count")
    candidates.append("sections")
    if structured.get("references_required") or structured.get("peer_reviewed_refs") is not None:
        candidates.extend(["references", "in_text_citations"])
    elif structured.get("citation_style"):
        candidates.append("in_text_citations")
    if any(
        structured.get(k)
        for k in ("font_family", "font_size", "line_spacing", "page_numbers_required")
    ):
        candidates.append("formatting")
    candidates.append("academic_style")

    for check_id in candidates:
        if check_id in applied_ids:
            continue
        category, default_reason = _CHECK_REASONS.get(check_id, ("requirements_match", "требуется бриф"))
        reason = default_reason
        if check_id == "formatting" and not has_docx:
            reason = "требуется .docx"
        if check_id == "in_text_citations":
            cite_status = next(
                (str(v.get("status") or "") for v in validations if v.get("id") == "in_text_citations"),
                "",
            )
            if cite_status == "CANNOT_VERIFY":
                continue
        items.append({"id": check_id, "category": category, "reason": reason})

    return items


def build_action_plan(validations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Steps sorted by potential normalised score gain."""
    score_meta = compute_readiness_score(validations)
    applicable_weight = float(score_meta.get("applicable_weight") or 0) or 100.0

    candidates: list[dict[str, Any]] = []
    for v in validations:
        if v.get("status") in {"PASS", "NOT_CHECKED", "CANNOT_VERIFY", "SKIP", "NOT_APPLICABLE"} or not v.get("fix"):
            continue
        weight = float(v.get("weight") or 0)
        if weight <= 0:
            continue
        completion = float(v.get("completion") or 0)
        raw_gain = weight * (1.0 - completion)
        gain = round(raw_gain / applicable_weight * 100, 1)
        if gain < 0.5:
            continue
        candidates.append(
            {
                "step": v.get("fix") or "",
                "requirement": v.get("label") or "",
                "estimated_improvement": gain,
                "priority": v.get("priority") or "medium",
                "completion_pct": v.get("completion_pct"),
            }
        )
    candidates.sort(key=lambda x: (-float(x["estimated_improvement"]), x.get("priority") != "critical"))
    steps: list[dict[str, Any]] = []
    for i, c in enumerate(candidates[:6], start=1):
        steps.append(
            {
                "step_number": i,
                "title": c["requirement"],
                "action": c["step"],
                "estimated_improvement": c["estimated_improvement"],
                "priority": c["priority"],
            }
        )
    return steps
