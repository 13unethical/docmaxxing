"""Weighted scoring, priorities, and action plan — no AI."""

from __future__ import annotations

from typing import Any


def compute_readiness_score(validations: list[dict[str, Any]]) -> int:
    """Score = sum(weight × completion) over active checks."""
    active = [v for v in validations if v.get("status") != "SKIP" and float(v.get("weight") or 0) > 0]
    if not active:
        return 0
    total_weight = sum(float(v["weight"]) for v in active)
    earned = sum(float(v["weight"]) * float(v.get("completion") or 0) for v in active)
    if total_weight <= 0:
        return 0
    return int(round(earned))


def score_to_verdict(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Needs improvement"
    return "Major issues"


def validations_to_categories(validations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group validations into category scores for UI bars."""
    labels = {
        "requirements_match": "Requirements match",
        "structure": "Structure",
        "formatting": "Formatting",
        "references": "References / citations",
        "clarity_organization": "Clarity of organization",
    }
    buckets: dict[str, list[float]] = {k: [] for k in labels}
    for v in validations:
        cat = v.get("category") or "requirements_match"
        if cat not in buckets:
            buckets[cat] = []
        w = float(v.get("weight") or 0)
        if w <= 0 or v.get("status") == "SKIP":
            continue
        buckets[cat].append(float(v.get("completion") or 0) * 100)
    out: dict[str, dict[str, Any]] = {}
    for key, label in labels.items():
        scores = buckets.get(key) or []
        avg = int(round(sum(scores) / len(scores))) if scores else 100
        out[key] = {"score": avg, "label": label}
    return out


def build_priorities(validations: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {"critical": [], "medium": [], "low": []}
    for v in validations:
        if v.get("status") in ("PASS", "SKIP"):
            continue
        pri = v.get("priority") or "medium"
        if pri not in grouped:
            pri = "medium"
        label = v.get("label") or v.get("id") or "Requirement"
        if label not in grouped[pri]:
            grouped[pri].append(label)
    return grouped


def build_action_plan(validations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Steps sorted by potential score gain."""
    candidates: list[dict[str, Any]] = []
    for v in validations:
        if v.get("status") == "PASS" or not v.get("fix"):
            continue
        weight = float(v.get("weight") or 0)
        if weight <= 0:
            continue
        completion = float(v.get("completion") or 0)
        gain = round(weight * (1.0 - completion), 1)
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


def validations_to_issues(validations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert failed validations into issue cards for legacy UI."""
    issues: list[dict[str, Any]] = []
    for v in validations:
        if v.get("status") in ("PASS", "SKIP", "NEEDS_CONFIRMATION"):
            continue
        completion = float(v.get("completion") or 0)
        severity = "high" if completion < 0.4 else "medium" if completion < 0.75 else "low"
        msg = f"Required: {v.get('required')} · Detected: {v.get('detected')} · Completion: {v.get('completion_pct')}%"
        issues.append(
            {
                "category": v.get("category") or "requirements_match",
                "severity": severity,
                "title": v.get("label") or "Requirement",
                "message": msg,
                "fix": v.get("fix") or "Review this requirement against your brief.",
                "location": {"position": "throughout document"},
                "penalty": int(round(float(v.get("weight") or 10) * (1.0 - completion))),
                "validation_id": v.get("id"),
            }
        )
    return issues
