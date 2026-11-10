"""Read access to generated assignment content after a refund.

A refunded project keeps every stored artifact (audit, possible re-payment), but its
generated text, intermediate outputs and deliverables are no longer served to the owner.
"""

from __future__ import annotations

from typing import Any

# Artifacts the owner may still see on a refunded project: payment/refund state and the
# owner's own inputs. Everything else (drafts, sessions, reports, packages) is withheld.
REFUNDED_VISIBLE_ARTIFACTS = frozenset(
    {
        "payment_confirmed",
        "payment_confirmed_at",
        "payment_refunded",
        "payment_refunded_at",
        "payment_refund_coins",
        "payment_cycle_id",
        "payment_cycles",
        "pricing",
        "coins_charged",
        "plan_free_paper",
        "assignment_spec",
        "brief_instructions",
        "original_note",
        "assignment_images",
        "chat_transcript",
    }
)

# Generated-content keys added on top of the project dict by the project API payload.
GENERATED_PAYLOAD_KEYS = (
    "pipeline",
    "research_plan",
    "blueprint",
    "writer_session",
    "draft",
    "review_report",
    "revision_history",
    "humanizer_session",
    "humanized_draft",
    "detection_session",
    "detection_report",
    "delivery_package",
)

# (method, action under /api/assignment/projects/<id>/) still usable on a refunded project.
REFUNDED_ALLOWED_ACTIONS = frozenset(
    {
        ("GET", ""),
        ("POST", "files"),
        ("POST", "analyze-requirements"),
        ("POST", "pricing"),
        ("POST", "brief"),
        ("POST", "confirm-payment"),
        ("POST", "refund-failed"),
        ("PUT", "chat-transcript"),
    }
)


def generated_content_locked(artifacts: dict[str, Any] | None) -> bool:
    art = artifacts if isinstance(artifacts, dict) else {}
    return bool(art.get("payment_refunded"))


def refunded_action_allowed(method: str, action: str) -> bool:
    method = "GET" if method.upper() == "HEAD" else method.upper()
    return (method, action.strip("/")) in REFUNDED_ALLOWED_ACTIONS


def redact_project_dict(project: dict[str, Any]) -> dict[str, Any]:
    out = dict(project)
    artifacts = out.get("artifacts")
    if isinstance(artifacts, dict):
        out["artifacts"] = {k: v for k, v in artifacts.items() if k in REFUNDED_VISIBLE_ARTIFACTS}
    return out


def redact_project_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project API payload for a refunded project: owner inputs only, no generated content."""
    out = dict(payload)
    if isinstance(out.get("project"), dict):
        out["project"] = redact_project_dict(out["project"])
    for key in GENERATED_PAYLOAD_KEYS:
        out[key] = None
    out["content_locked"] = True
    return out
