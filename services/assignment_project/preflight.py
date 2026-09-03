"""Pipeline preflight: provider keys only — does not generate an assignment."""

from __future__ import annotations

import os
from typing import Any

from services.claude_client import claude_enabled, claude_model
from services.gemini_client import gemini_enabled, gemini_model


def _zerogpt_configured() -> bool:
    api_key = (os.environ.get("ZEROGPT_API_KEY") or "").strip()
    email = (os.environ.get("ZEROGPT_EMAIL") or "").strip()
    password = (os.environ.get("ZEROGPT_PASSWORD") or "").strip()
    return bool(api_key or (email and password))


def static_provider_checks() -> dict[str, Any]:
    """Check env/API keys. No LLM calls, no StealthWriter, no credits."""
    gemini_ok = gemini_enabled()
    claude_ok = claude_enabled()
    writer_ok = claude_ok or gemini_ok
    analysis_ok = gemini_ok or claude_ok
    zerogpt_ok = _zerogpt_configured()

    checks = [
        {
            "id": "gemini",
            "ok": gemini_ok,
            "required": False,
            "label": "Gemini (research, review, analysis)",
            "detail": gemini_model() if gemini_ok else "GOOGLE_API_KEY / GEMINI_API_KEY missing",
        },
        {
            "id": "claude",
            "ok": claude_ok,
            "required": False,
            "label": "Claude (assignment writing)",
            "detail": (
                claude_model()
                if claude_ok
                else "ANTHROPIC_API_KEY missing — writer falls back to Gemini"
            ),
        },
        {
            "id": "writer",
            "ok": writer_ok,
            "required": True,
            "label": "Writer provider",
            "detail": "claude" if claude_ok else ("gemini" if gemini_ok else "no LLM key"),
        },
        {
            "id": "analysis",
            "ok": analysis_ok,
            "required": True,
            "label": "Requirement analysis provider",
            "detail": "gemini" if gemini_ok else ("claude" if claude_ok else "no LLM key"),
        },
        {
            "id": "zerogpt",
            "ok": zerogpt_ok,
            "required": False,
            "label": "ZeroGPT (AI detect, optional)",
            "detail": "configured" if zerogpt_ok else "not configured",
        },
    ]
    blocking = [c for c in checks if c["required"] and not c["ok"]]
    return {
        "ok": not blocking,
        "generates_assignment": False,
        "spends_credits": False,
        "checks": checks,
        "blocking": [c["id"] for c in blocking],
    }


def with_stealthwriter_snapshot(
    payload: dict[str, Any],
    snapshot: dict[str, Any] | None,
    *,
    error: str | None = None,
) -> dict[str, Any]:
    """Attach a cheap StealthWriter tab snapshot (no humanize call)."""
    out = dict(payload)
    if error:
        check = {
            "id": "stealthwriter",
            "ok": False,
            "required": True,
            "label": "StealthWriter session",
            "detail": error[:300],
        }
        out["checks"] = list(out.get("checks") or []) + [check]
        out["blocking"] = list(out.get("blocking") or []) + ["stealthwriter"]
        out["ok"] = False
        out["stealthwriter"] = {"ok": False, "error": error[:300]}
        return out

    info = snapshot or {}
    logged_in = info.get("logged_in")
    url = str(info.get("current_url") or "")
    if logged_in is True:
        detail = "logged in"
        if url:
            detail += f" ({url.split('?')[0][:80]})"
        ok = True
    elif logged_in is False:
        detail = "signed out — Humanizer and Assignments will fail until session is restored"
        ok = False
    else:
        detail = "browser tab URL unknown — session not confirmed"
        ok = False

    check = {
        "id": "stealthwriter",
        "ok": ok,
        "required": True,
        "label": "StealthWriter session",
        "detail": detail,
    }
    out["checks"] = list(out.get("checks") or []) + [check]
    if not ok:
        out["blocking"] = list(out.get("blocking") or []) + ["stealthwriter"]
        out["ok"] = False
    out["stealthwriter"] = {
        "ok": ok,
        "logged_in": logged_in,
        "current_url": url[:200] if url else None,
        "has_page": bool(info.get("has_page")),
        "humanize_not_run": True,
    }
    return out
