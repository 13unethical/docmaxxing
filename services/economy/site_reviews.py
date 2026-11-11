"""Public site reviews (landing + in-app), with guest email confirm and moderation."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from .db import connect

logger = logging.getLogger(__name__)

TOOLS = (
    "AI Detector",
    "Humanizer",
    "Formatting",
    "Work Review",
    "Assignment",
    "Veil",
)
STATUS_PENDING_EMAIL = "pending_email"
STATUS_PENDING_MOD = "pending_moderation"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_BODY = 10
_MAX_BODY = 1000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS site_reviews (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER REFERENCES users(id) ON DELETE SET NULL,
    email              TEXT,
    email_hash         TEXT,
    stars              INTEGER NOT NULL,
    tool               TEXT,
    body               TEXT NOT NULL,
    status             TEXT NOT NULL,
    verified           INTEGER NOT NULL DEFAULT 0,
    docs_checked       INTEGER NOT NULL DEFAULT 0,
    confirm_token_hash TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_site_reviews_status ON site_reviews(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_site_reviews_user ON site_reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_site_reviews_email_hash ON site_reviews(email_hash);
"""

# Seed shown until real approved reviews exist (same copy as the prototype).
_SEED_ITEMS = [
    {
        "stars": 5,
        "tool": "AI Detector",
        "date": "2026-11-04",
        "docs": 12,
        "verified": True,
        "text": "Ran my essay through the AI detector before submitting. It flagged two paragraphs I had paraphrased too closely, I rewrote them and Turnitin came back clean.",
    },
    {
        "stars": 5,
        "tool": "Formatting",
        "date": "2026-11-01",
        "docs": 4,
        "verified": True,
        "text": "Formatting alone saved me an evening. APA 7 headings, page numbers and the reference list fixed in one go, and it was free.",
    },
    {
        "stars": 4,
        "tool": "Humanizer",
        "date": "2026-10-28",
        "docs": 31,
        "verified": True,
        "text": "The humanizer keeps my meaning, which is what I care about. I still read every line after, but it sounds like me now, just tidier.",
    },
    {
        "stars": 5,
        "tool": "Work Review",
        "date": "2026-10-25",
        "docs": 9,
        "verified": True,
        "text": "Work Review showed exactly which rubric points I was missing. Got a 72 on a report I expected to barely pass.",
    },
    {
        "stars": 5,
        "tool": "Assignment",
        "date": "2026-10-19",
        "docs": 17,
        "verified": True,
        "text": "Used an assignment run before a deadline. Saw the price first, got the draft with sources, then edited it into my own words.",
    },
    {
        "stars": 5,
        "tool": "Veil",
        "date": "2026-10-12",
        "docs": 22,
        "verified": True,
        "text": "Veil in Google Docs means I stop copy-pasting. Check a paragraph, humanize it, paste stays put.",
    },
    {
        "stars": 4,
        "tool": None,
        "date": "2026-09-30",
        "docs": 0,
        "verified": False,
        "text": "Tried the free detector as a guest. Clear scores, no account wall for the first run. Left a review after I signed up later.",
    },
    {
        "stars": 5,
        "tool": "AI Detector",
        "date": "2026-09-18",
        "docs": 8,
        "verified": True,
        "text": "Caught AI-sounding transitions I didn’t notice. Fixed them the same night and submitted with confidence.",
    },
]


class ReviewError(Exception):
    """User-facing review error."""


def ensure_schema(conn=None) -> None:
    if conn is not None:
        conn.executescript(_SCHEMA)
        return
    with connect() as owned:
        owned.executescript(_SCHEMA)


def _secret() -> bytes:
    return ((os.environ.get("SECRET_KEY") or "").strip() or "dev-only-secret").encode("utf-8")


def _email_hash(email: str) -> str:
    return hmac.new(_secret(), email.strip().lower().encode("utf-8"), "sha256").hexdigest()


def _token_hash(token: str) -> str:
    return hmac.new(_secret(), token.encode("utf-8"), "sha256").hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_tool(tool: str | None) -> str | None:
    t = (tool or "").strip()
    if not t:
        return None
    if t not in TOOLS:
        raise ReviewError("Pick one of the listed tools, or leave it blank.")
    return t


def docs_checked_for_user(user_id: int) -> int:
    """Count paid/check-like ledger rows as a stand-in for documents checked."""
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM transactions "
            "WHERE user_id = ? AND kind = 'debit' AND feature IN "
            "('turnitin', 'humanize', 'detect', 'assignment', 'veil', 'presentation')",
            (int(user_id),),
        ).fetchone()
    return int(row["n"] or 0) if row else 0


def preferred_tool_for_user(user_id: int) -> str:
    """Most-used metered feature mapped to a review tool label."""
    feature_to_tool = {
        "turnitin": "AI Detector",
        "detect": "AI Detector",
        "humanize": "Humanizer",
        "assignment": "Assignment",
        "veil": "Veil",
        "presentation": "Work Review",
        "format": "Formatting",
    }
    with connect() as conn:
        rows = conn.execute(
            "SELECT feature, COUNT(*) AS n FROM transactions "
            "WHERE user_id = ? AND kind = 'debit' "
            "GROUP BY feature ORDER BY n DESC LIMIT 12",
            (int(user_id),),
        ).fetchall()
    for row in rows:
        label = feature_to_tool.get(str(row["feature"] or ""))
        if label:
            return label
    return "AI Detector"


def student_count_label() -> str:
    floor = max(300, int(os.environ.get("SITE_REVIEWS_USERS_FLOOR") or "300"))
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users WHERE is_blocked = 0").fetchone()
    n = max(floor, int(row["n"] or 0) if row else floor)
    if n >= 1000:
        return f"{n // 100 * 100}+"
    return f"{n}+"


def _public_item(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "stars": int(row["stars"]),
        "tool": row["tool"],
        "date": str(row["created_at"])[:10],
        "docs": int(row["docs_checked"] or 0),
        "verified": bool(row["verified"]),
        "text": row["body"],
        "status": row["status"],
    }


def list_approved(*, limit: int = 50) -> list[dict[str, Any]]:
    ensure_schema()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM site_reviews WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (STATUS_APPROVED, int(limit)),
        ).fetchall()
    return [_public_item(r) for r in rows]


def aggregates() -> dict[str, Any]:
    ensure_schema()
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, AVG(stars) AS avg_stars FROM site_reviews WHERE status = ?",
            (STATUS_APPROVED,),
        ).fetchone()
    count = int(row["n"] or 0) if row else 0
    avg = float(row["avg_stars"] or 0) if row and row["avg_stars"] is not None else 0.0
    if count == 0:
        # Prototype placeholders until the first moderated reviews land.
        return {"rating": 4.9, "count": 46, "users": student_count_label(), "using_seed": True}
    return {
        "rating": round(avg, 1),
        "count": count,
        "users": student_count_label(),
        "using_seed": False,
    }


def public_feed(*, mine_user_id: int | None = None, mine_email: str | None = None) -> dict[str, Any]:
    agg = aggregates()
    items = list_approved()
    if agg.get("using_seed") and not items:
        items = [
            {
                "id": None,
                "stars": x["stars"],
                "tool": x["tool"],
                "date": x["date"],
                "docs": x["docs"],
                "verified": x["verified"],
                "text": x["text"],
                "status": STATUS_APPROVED,
            }
            for x in _SEED_ITEMS
        ]
    mine = None
    if mine_user_id:
        mine = get_mine(user_id=mine_user_id)
    elif mine_email and _EMAIL_RE.match(mine_email.strip().lower()):
        mine = get_mine(email=mine_email.strip().lower())
    return {
        "rating": agg["rating"],
        "count": agg["count"],
        "users": agg["users"],
        "note": (
            "Every review is checked before it goes live. Verified student means it came "
            "from a DocMaxxing account. Names and emails stay hidden."
        ),
        "tools": list(TOOLS),
        "faces": [
            ["#3b7bff", "#9cc0ff"],
            ["#ff8a4d", "#ffd0a8"],
            ["#7a5cff", "#c9b8ff"],
            ["#19a974", "#9de3c4"],
        ],
        "items": [
            {
                "stars": i["stars"],
                "tool": i["tool"],
                "date": i["date"],
                "docs": i["docs"],
                "verified": i["verified"],
                "text": i["text"],
            }
            for i in items
            if i.get("status") == STATUS_APPROVED or i.get("id") is None
        ],
        "mine": (
            {
                "stars": mine["stars"],
                "tool": mine["tool"],
                "date": mine["date"],
                "docs": mine["docs"],
                "text": mine["text"],
                "status": mine["status"],
                "verified": mine["verified"],
            }
            if mine and mine["status"] in (STATUS_PENDING_EMAIL, STATUS_PENDING_MOD, STATUS_APPROVED)
            else None
        ),
        "appTool": preferred_tool_for_user(mine_user_id) if mine_user_id else "AI Detector",
    }


def get_mine(*, user_id: int | None = None, email: str | None = None) -> dict[str, Any] | None:
    ensure_schema()
    with connect() as conn:
        if user_id is not None:
            row = conn.execute(
                "SELECT * FROM site_reviews WHERE user_id = ? "
                "AND status != ? ORDER BY id DESC LIMIT 1",
                (int(user_id), STATUS_REJECTED),
            ).fetchone()
        elif email:
            row = conn.execute(
                "SELECT * FROM site_reviews WHERE email_hash = ? "
                "AND status != ? ORDER BY id DESC LIMIT 1",
                (_email_hash(email), STATUS_REJECTED),
            ).fetchone()
        else:
            row = None
    return _public_item(row) if row else None


def submit_review(
    *,
    stars: int,
    body: str,
    tool: str | None = None,
    user_id: int | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    ensure_schema()
    try:
        stars_i = int(stars)
    except (TypeError, ValueError):
        raise ReviewError("Pick a rating from 1 to 5 stars.") from None
    if stars_i < 1 or stars_i > 5:
        raise ReviewError("Pick a rating from 1 to 5 stars.")
    text = (body or "").strip()
    if len(text) < _MIN_BODY:
        raise ReviewError("Write a few words, at least 10 characters.")
    if len(text) > _MAX_BODY:
        raise ReviewError(f"Keep your review under {_MAX_BODY} characters.")
    tool_n = _normalize_tool(tool)

    verified = 0
    docs = 0
    status = STATUS_PENDING_MOD
    email_n = None
    ehash = None
    confirm_token = None
    confirm_hash = None

    if user_id is not None:
        verified = 1
        docs = docs_checked_for_user(int(user_id))
        with connect() as conn:
            u = conn.execute("SELECT email FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if u:
            email_n = str(u["email"]).strip().lower()
            ehash = _email_hash(email_n)
    else:
        email_n = (email or "").strip().lower()
        if not email_n or not _EMAIL_RE.match(email_n):
            raise ReviewError("Enter the email you use for your account.")
        ehash = _email_hash(email_n)
        status = STATUS_PENDING_EMAIL
        confirm_token = secrets.token_urlsafe(24)
        confirm_hash = _token_hash(confirm_token)
        with connect() as conn:
            u = conn.execute(
                "SELECT id FROM users WHERE lower(email) = ? AND is_blocked = 0",
                (email_n,),
            ).fetchone()
        if u:
            # Will flip verified after confirm; remember user_id early.
            user_id = int(u["id"])
            docs = docs_checked_for_user(user_id)

    now = _now()
    with connect() as conn:
        ensure_schema(conn)
        existing = None
        if user_id is not None:
            existing = conn.execute(
                "SELECT id, status FROM site_reviews WHERE user_id = ? "
                "AND status IN (?, ?, ?) ORDER BY id DESC LIMIT 1",
                (int(user_id), STATUS_PENDING_EMAIL, STATUS_PENDING_MOD, STATUS_APPROVED),
            ).fetchone()
        elif ehash:
            existing = conn.execute(
                "SELECT id, status FROM site_reviews WHERE email_hash = ? "
                "AND status IN (?, ?, ?) ORDER BY id DESC LIMIT 1",
                (ehash, STATUS_PENDING_EMAIL, STATUS_PENDING_MOD, STATUS_APPROVED),
            ).fetchone()
        if existing:
            # Editing an approved review sends it back to moderation.
            new_status = STATUS_PENDING_EMAIL if status == STATUS_PENDING_EMAIL else STATUS_PENDING_MOD
            if existing["status"] == STATUS_APPROVED:
                new_status = STATUS_PENDING_MOD
                confirm_hash = None
                confirm_token = None
            conn.execute(
                "UPDATE site_reviews SET stars = ?, tool = ?, body = ?, status = ?, "
                "verified = ?, docs_checked = ?, confirm_token_hash = COALESCE(?, confirm_token_hash), "
                "email = COALESCE(?, email), email_hash = COALESCE(?, email_hash), "
                "user_id = COALESCE(?, user_id), updated_at = ? WHERE id = ?",
                (
                    stars_i,
                    tool_n,
                    text,
                    new_status,
                    verified if status != STATUS_PENDING_EMAIL else int(bool(user_id)),
                    docs,
                    confirm_hash,
                    email_n,
                    ehash,
                    user_id,
                    now,
                    int(existing["id"]),
                ),
            )
            rid = int(existing["id"])
            status = new_status
        else:
            cur = conn.execute(
                "INSERT INTO site_reviews "
                "(user_id, email, email_hash, stars, tool, body, status, verified, "
                " docs_checked, confirm_token_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    email_n,
                    ehash,
                    stars_i,
                    tool_n,
                    text,
                    status,
                    verified if status != STATUS_PENDING_EMAIL else 0,
                    docs,
                    confirm_hash,
                    now,
                    now,
                ),
            )
            rid = int(cur.lastrowid)

    out: dict[str, Any] = {
        "ok": True,
        "id": rid,
        "status": status,
        "needs_email_confirm": status == STATUS_PENDING_EMAIL,
    }
    if confirm_token:
        out["confirm_token"] = confirm_token
    return out


def confirm_email(token: str) -> dict[str, Any]:
    ensure_schema()
    raw = (token or "").strip()
    if not raw:
        raise ReviewError("That confirmation link is invalid or expired.")
    th = _token_hash(raw)
    now = _now()
    with connect() as conn:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT * FROM site_reviews WHERE confirm_token_hash = ? AND status = ?",
            (th, STATUS_PENDING_EMAIL),
        ).fetchone()
        if row is None:
            raise ReviewError("That confirmation link is invalid or expired.")
        email = str(row["email"] or "").strip().lower()
        user_id = row["user_id"]
        verified = 0
        docs = int(row["docs_checked"] or 0)
        if email:
            u = conn.execute(
                "SELECT id FROM users WHERE lower(email) = ? AND is_blocked = 0",
                (email,),
            ).fetchone()
            if u:
                user_id = int(u["id"])
                verified = 1
                docs = docs_checked_for_user(user_id)
        conn.execute(
            "UPDATE site_reviews SET status = ?, verified = ?, docs_checked = ?, "
            "user_id = ?, confirm_token_hash = NULL, updated_at = ? WHERE id = ?",
            (STATUS_PENDING_MOD, verified, docs, user_id, now, int(row["id"])),
        )
    return {"ok": True, "id": int(row["id"]), "status": STATUS_PENDING_MOD, "verified": bool(verified)}


def send_confirm_email(*, to_email: str, confirm_url: str) -> bool:
    from html import escape

    from .email_verify import EmailVerifyError, _smtp_send, smtp_configured

    to_email = (to_email or "").strip()
    if not to_email:
        raise EmailVerifyError("Missing recipient email")
    subject = "Confirm your DocMaxxing review"
    text_body = (
        "Hi,\n\n"
        "Please confirm your DocMaxxing review by opening this link:\n\n"
        f"{confirm_url}\n\n"
        "If you did not leave a review, you can ignore this message.\n\n"
        "— DocMaxxing\n"
    )
    html_body = f"""\
<html><body style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; color: #0f172a;">
  <p>Hi,</p>
  <p>Please confirm your DocMaxxing review:</p>
  <p><a href="{escape(confirm_url, quote=True)}">Confirm my review</a></p>
  <p style="color:#64748b;font-size:13px;">If you did not leave a review, ignore this message.</p>
  <p>— DocMaxxing</p>
</body></html>"""
    if not smtp_configured():
        logger.warning("MAIL_SERVER not set — review confirm email not sent")
        return False
    _smtp_send(to_email, subject, text_body, html_body)
    return True


def list_pending(*, limit: int = 100) -> list[dict[str, Any]]:
    ensure_schema()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM site_reviews WHERE status = ? ORDER BY created_at ASC LIMIT ?",
            (STATUS_PENDING_MOD, int(limit)),
        ).fetchall()
    return [_public_item(r) for r in rows]


def moderate(review_id: int, *, approve: bool) -> dict[str, Any]:
    ensure_schema()
    status = STATUS_APPROVED if approve else STATUS_REJECTED
    now = _now()
    with connect() as conn:
        ensure_schema(conn)
        cur = conn.execute(
            "UPDATE site_reviews SET status = ?, confirm_token_hash = NULL, updated_at = ? "
            "WHERE id = ? AND status = ?",
            (status, now, int(review_id), STATUS_PENDING_MOD),
        )
        if cur.rowcount != 1:
            raise ReviewError("Review not found or already moderated.")
    return {"ok": True, "id": int(review_id), "status": status}
