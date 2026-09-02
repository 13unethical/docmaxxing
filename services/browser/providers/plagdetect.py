"""PlagDetect provider — upload, poll, and download Turnitin-style reports.

Browser lifecycle is owned by BrowserService. This module drives the third-party
PlagDetect dashboard (not official Turnitin): submit a file, wait for processing,
read similarity / AI scores from the submissions table, and download both reports.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.browser.browser_service import BrowserService
from services.browser.providers.base import Provider

PROVIDER_NAME = "plagdetect"

_PLACEHOLDER_HOSTS = frozenset(
    {
        "your-plagdetect-site.com",
        "example.com",
        "localhost",
    }
)
_LOGIN_HINTS = ("/login", "/sign-in", "/signin", "/auth")
_POLL_INTERVAL_S = 2.0
_RELOAD_EVERY_N_POLLS = 2
_DOWNLOAD_TIMEOUT_MS = 25_000


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _check_timeout_s() -> int:
    return _env_int("PLAGDETECT_CHECK_TIMEOUT", 540)


def _base_url() -> str:
    return (os.environ.get("PLAGDETECT_BASE_URL") or "").strip().rstrip("/")


def _dashboard_url() -> str:
    explicit = (os.environ.get("PLAGDETECT_DASHBOARD_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    base = _base_url()
    if base:
        return f"{base}/dashboard"
    return ""


def _host_from_url(url: str) -> str:
    match = re.match(r"https?://([^/]+)", url or "")
    return (match.group(1) if match else "").lower()


def plagdetect_config() -> dict[str, str]:
    """Return the active PlagDetect URLs (read fresh from the environment)."""
    return {
        "base_url": _base_url(),
        "dashboard_url": _dashboard_url(),
    }


def _validate_urls() -> None:
    base = _base_url()
    dash = _dashboard_url()
    if not base or not dash:
        raise PlagDetectAutomationError(
            "PLAGDETECT_BASE_URL is not configured. "
            "Open your PlagDetect dashboard in Chrome, copy the address bar URL "
            "(e.g. https://app.example.com/dashboard), and set PLAGDETECT_BASE_URL "
            "and PLAGDETECT_DASHBOARD_URL in .env, then restart python3 app.py.",
            {"configured": plagdetect_config()},
        )
    host = _host_from_url(base)
    if host in _PLACEHOLDER_HOSTS or "your-plagdetect" in host:
        raise PlagDetectAutomationError(
            f"PLAGDETECT_BASE_URL still uses a placeholder host ({host}). "
            "Set the real dashboard URL from your browser address bar in .env.",
            {"configured": plagdetect_config()},
        )
    if not base.startswith("http"):
        raise PlagDetectAutomationError(
            "PLAGDETECT_BASE_URL must start with http:// or https://",
            {"configured": plagdetect_config()},
        )


class PlagDetectAutomationError(Exception):
    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def _page() -> Any:
    return BrowserService.instance().get_or_create_page(PROVIDER_NAME)


def _profile_path() -> str:
    return str(BrowserService.instance().user_data_dir.resolve())


def _is_login_url(url: str) -> bool:
    lowered = (url or "").lower()
    return any(h in lowered for h in _LOGIN_HINTS)


def _collect_diagnostics(page: Any, *, step: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    diag: dict[str, Any] = {"step": step}
    try:
        diag["current_url"] = page.url
        diag["page_title"] = page.title()
        diag["visible_buttons"] = page.evaluate(
            """() => Array.from(document.querySelectorAll('button, [role="button"], a'))
                .map(el => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' '))
                .filter(Boolean)
                .slice(0, 40)"""
        )
    except Exception as exc:  # noqa: BLE001
        diag["diagnostics_error"] = str(exc)
    if extra:
        diag.update(extra)
    return diag


def _credentials() -> tuple[str, str]:
    email = (os.environ.get("PLAGDETECT_EMAIL") or "").strip()
    password = (os.environ.get("PLAGDETECT_PASSWORD") or "").strip()
    return email, password


def _is_session_logged_in(page: Any) -> bool:
    if _is_login_url(page.url):
        return False
    return _ensure_logged_in(page)


def _login_with_credentials(page: Any, email: str, password: str) -> bool:
    """Fill PlagDetect's email/password form and submit. Returns True if session looks logged in."""
    login_url = f"{_base_url()}/accounts/login"
    if not _is_login_url(page.url):
        page.goto(login_url, wait_until="domcontentloaded")
    else:
        # Already on a login redirect; stay put.
        pass
    page.wait_for_timeout(600)

    filled = bool(
        page.evaluate(
            """([email, password]) => {
                const visible = (el) => {
                    if (!el) return false;
                    const st = getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                };
                const inputs = Array.from(document.querySelectorAll('input')).filter(visible);
                const emailEl = inputs.find(el => {
                    const t = (el.type || '').toLowerCase();
                    const n = (el.name || el.id || el.autocomplete || '').toLowerCase();
                    return t === 'email' || n.includes('email') || n.includes('login') || n.includes('user');
                }) || inputs.find(el => (el.type || '').toLowerCase() === 'text');
                const passEl = inputs.find(el => (el.type || '').toLowerCase() === 'password');
                if (!emailEl || !passEl) return false;
                const setVal = (el, val) => {
                    el.focus();
                    el.value = '';
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.value = val;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                };
                setVal(emailEl, email);
                setVal(passEl, password);
                return true;
            }""",
            [email, password],
        )
    )
    if not filled:
        # Playwright fallbacks for React-controlled inputs
        try:
            email_loc = page.locator(
                'input[type="email"], input[name="email"], input[name="login"], '
                'input[autocomplete="email"], input[autocomplete="username"]'
            ).first
            pass_loc = page.locator('input[type="password"]').first
            email_loc.fill(email, timeout=5_000)
            pass_loc.fill(password, timeout=5_000)
            filled = True
        except Exception:  # noqa: BLE001
            return False

    # Prefer clicking the Log In button; fall back to form submit / Enter.
    clicked = bool(
        page.evaluate(
            """() => {
                const visible = (el) => {
                    if (!el) return false;
                    const st = getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                };
                const buttons = Array.from(
                    document.querySelectorAll('button, input[type="submit"], a')
                ).filter(visible);
                const btn = buttons.find(el => {
                    const t = (el.innerText || el.value || el.textContent || '').trim().toLowerCase();
                    return t === 'log in' || t === 'login' || t === 'sign in';
                });
                if (btn) { btn.click(); return true; }
                const form = document.querySelector('form');
                if (form) { form.requestSubmit ? form.requestSubmit() : form.submit(); return true; }
                return false;
            }"""
        )
    )
    if not clicked:
        try:
            page.locator('input[type="password"]').first.press("Enter")
        except Exception:  # noqa: BLE001
            pass

    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(1500)

    # If still on login, try navigating to dashboard once (cookie may have been set).
    if _is_login_url(page.url):
        page.goto(_dashboard_url(), wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

    return _is_session_logged_in(page)


def _require_login(page: Any) -> bool:
    """Ensure an authenticated PlagDetect session; auto-login when env credentials exist."""
    if _is_session_logged_in(page):
        return True
    email, password = _credentials()
    if not email or not password:
        return False
    return _login_with_credentials(page, email, password)


def start_interactive_login() -> dict[str, Any]:
    _validate_urls()
    page = _page()
    page.goto(_dashboard_url(), wait_until="domcontentloaded")
    page.wait_for_timeout(800)

    logged_in = _is_session_logged_in(page)
    auto_attempted = False
    if not logged_in:
        email, password = _credentials()
        if email and password:
            auto_attempted = True
            logged_in = _login_with_credentials(page, email, password)

    if logged_in:
        message = "Logged in to PlagDetect."
    elif auto_attempted:
        message = (
            "Auto-login failed. Check PLAGDETECT_EMAIL / PLAGDETECT_PASSWORD, "
            "or sign in manually in the Chrome profile."
        )
    elif not _credentials()[0]:
        message = (
            "Not logged in. Set PLAGDETECT_EMAIL and PLAGDETECT_PASSWORD in .env "
            "(then restart), or sign in manually in Chrome."
        )
    else:
        message = "Chrome opened PlagDetect. Sign in manually if needed."

    return {
        "success": logged_in,
        "logged_in": logged_in,
        "cdp_url": BrowserService.instance().cdp_url,
        "profile": _profile_path(),
        "current_url": page.url,
        "configured_dashboard_url": _dashboard_url(),
        "message": message,
    }


def check_interactive_login() -> dict[str, Any]:
    _validate_urls()
    page = _page()
    page.goto(_dashboard_url(), wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    logged_in = _require_login(page)
    return {
        "success": True,
        "logged_in": logged_in,
        "current_url": page.url,
        "title": page.title(),
        "profile": _profile_path(),
        "configured_dashboard_url": _dashboard_url(),
        "message": "Logged in." if logged_in else "Not logged in yet — set PLAGDETECT_EMAIL/PASSWORD or finish login in Chrome.",
    }


def get_session_status() -> dict[str, Any]:
    _validate_urls()
    page = _page()
    page.goto(_dashboard_url(), wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    logged_in = _is_session_logged_in(page)
    identity = page.evaluate(
        """() => {
            const emailRe = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}/i;
            const body = document.body ? document.body.innerText : '';
            const email = (body.match(emailRe) || [])[0] || null;
            return { email };
        }"""
    )
    cred_email, cred_password = _credentials()
    return {
        "logged_in": logged_in,
        "current_url": page.url,
        "configured_dashboard_url": _dashboard_url(),
        "username": (identity or {}).get("email"),
        "plan": None,
        "credentials_configured": bool(cred_email and cred_password),
    }


def _set_toggle(page: Any, label_fragment: str, enabled: bool) -> bool:
    """Set Exclude bibliography / Exclude quotes to the desired state.

    Returns True when the switch was found and matches ``enabled``.
    """
    ok = bool(
        page.evaluate(
            """([label, on]) => {
                const norm = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
                const target = norm(label);
                const isChecked = (el) => {
                    if (!el) return false;
                    if (typeof el.checked === 'boolean') return el.checked;
                    const aria = el.getAttribute('aria-checked');
                    if (aria === 'true') return true;
                    if (aria === 'false') return false;
                    const cls = (el.className || '').toString().toLowerCase();
                    return cls.includes('checked') || cls.includes('is-on') || cls.includes('active');
                };
                const clickEl = (el) => {
                    if (!el) return;
                    try { el.click(); } catch (_) {}
                };
                const candidates = Array.from(
                    document.querySelectorAll('label, button, [role="switch"], span, div, p')
                );
                for (const node of candidates) {
                    const text = norm(node.innerText || node.textContent || '');
                    // Prefer short label nodes so we don't match huge containers.
                    if (!text.includes(target) || text.length > 80) continue;

                    let root = node.closest('label, [class*="toggle"], [class*="switch"], .flex, form, div') || node.parentElement;
                    if (!root) continue;

                    // Walk up a bit if the checkbox/switch is a sibling of the label.
                    let input =
                        root.querySelector('input[type="checkbox"], input[role="switch"], [role="switch"]') ||
                        null;
                    if (!input && node.parentElement) {
                        root = node.parentElement.parentElement || node.parentElement;
                        input = root.querySelector('input[type="checkbox"], input[role="switch"], [role="switch"]');
                    }
                    if (!input) {
                        // Some UIs put the switch next to the label as a button.
                        const sib = node.parentElement
                            ? Array.from(node.parentElement.children).find(
                                  (c) => c !== node && (
                                      c.matches?.('button, [role="switch"], input') ||
                                      /switch|toggle/i.test(c.className || '')
                                  )
                              )
                            : null;
                        input = sib || null;
                    }
                    if (!input) continue;

                    let checked = isChecked(input);
                    if (checked === !!on) return true;
                    clickEl(input);
                    // Also try the visual track if nested.
                    const track = (input.closest('label, div') || root).querySelector(
                        '[class*="switch"], [class*="toggle"], [role="switch"]'
                    );
                    if (track && track !== input && isChecked(input) !== !!on) clickEl(track);
                    checked = isChecked(input);
                    return checked === !!on;
                }
                return false;
            }""",
            [label_fragment, bool(enabled)],
        )
    )
    page.wait_for_timeout(350)
    return ok


def _apply_exclude_toggles(
    page: Any,
    *,
    exclude_bibliography: bool,
    exclude_quotes: bool,
) -> dict[str, bool]:
    """Apply both exclude switches before upload; retry once if needed."""
    bib_ok = _set_toggle(page, "bibliography", exclude_bibliography)
    quotes_ok = _set_toggle(page, "quotes", exclude_quotes)
    if not bib_ok or not quotes_ok:
        page.wait_for_timeout(500)
        if not bib_ok:
            bib_ok = _set_toggle(page, "exclude bibliography", exclude_bibliography)
        if not quotes_ok:
            quotes_ok = _set_toggle(page, "exclude quotes", exclude_quotes)
    return {"bibliography": bib_ok, "quotes": quotes_ok}


def _parse_percent(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", str(text))
    if match:
        return float(match.group(1))
    return None


AI_WORD_LIMIT_DISPLAY = "AI needs 300–30,000 words"
_AI_WORD_LIMIT_RE = re.compile(
    r"300\s*[-–—to]+\s*30[,\s]?000|30[,\s]?000\s*words|AI reports require",
    re.I,
)


def _is_ai_word_limit_text(text: str | None) -> bool:
    """True when PlagDetect refuses AI because the document is outside 300–30,000 words."""
    return bool(_AI_WORD_LIMIT_RE.search(text or ""))


def _row_has_similarity(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    return _parse_percent(row.get("similarity_text")) is not None


def _ai_unavailable_reason(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    blob = " ".join(
        str(row.get(k) or "")
        for k in ("ai_text", "status_text", "row_text")
    )
    if _is_ai_word_limit_text(blob):
        return AI_WORD_LIMIT_DISPLAY
    return None


def _highlights_timeout_s() -> int:
    return _env_int("PLAGDETECT_HIGHLIGHTS_TIMEOUT", 180)


def _column_index(column: str) -> int:
    mapping = _LAST_COL_MAP or {
        "ai": 3,
        "similarity": 2,
        "highlights": 5,
        "status": 4,
    }
    return mapping[column]


_LAST_COL_MAP: dict[str, int] | None = None


def _parse_score_text(text: str | None) -> dict[str, Any]:
    """Parse a PlagDetect score cell (supports numeric %, *%, and dashes)."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw or raw in {"-", "—"}:
        return {"numeric": None, "display": None}
    if "*" in raw:
        return {"numeric": None, "display": "*%"}
    numeric = _parse_percent(raw)
    if numeric is not None:
        display = f"{int(numeric) if numeric == int(numeric) else numeric:g}%"
        return {"numeric": numeric, "display": display}
    token = raw.split()[0] if raw else None
    return {"numeric": None, "display": token}


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKPOINT_ROOT = _REPO_ROOT / "data" / "turnitin" / "checkpoints"


def _checkpoint_path(submission_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", submission_id)
    return _CHECKPOINT_ROOT / f"{safe}.json"


def _load_checkpoint(submission_id: str | None) -> dict[str, Any] | None:
    if not submission_id:
        return None
    path = _checkpoint_path(submission_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_checkpoint(submission_id: str, data: dict[str, Any]) -> None:
    path = _checkpoint_path(submission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _clear_checkpoint(submission_id: str | None) -> None:
    if not submission_id:
        return
    path = _checkpoint_path(submission_id)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _persist_store_external_id(submission_id: str, external_id: str) -> None:
    """Write the PlagDetect id into SQLite as soon as the upload lands.

    The watcher refunds when this is missing. Checkpoint files alone are easy
    to miss if a second Chrome job starts before scores come back.
    """
    ext = str(external_id or "").strip()
    if not submission_id or not ext:
        return
    try:
        from services.turnitin_service.store import TurnitinStore

        TurnitinStore().update(submission_id, external_id=ext)
    except Exception:  # noqa: BLE001
        pass


def _reload_dashboard(page: Any) -> None:
    try:
        page.goto(_dashboard_url(), wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_timeout(600)
    except Exception:  # noqa: BLE001
        pass


def _refresh_submissions_view(page: Any, *, force_reload: bool = False) -> None:
    """Refresh the submissions table."""
    if force_reload:
        _reload_dashboard(page)
        return
    try:
        page.evaluate(
            """() => {
                const refresh = Array.from(document.querySelectorAll('button, [role="button"], a'))
                    .find(el => /refresh|reload/i.test(el.innerText || el.textContent || ''));
                if (refresh) { refresh.click(); return true; }
                return false;
            }"""
        )
        page.wait_for_timeout(300)
    except Exception:  # noqa: BLE001
        pass


def _wait_for_file_attached_in_modal(page: Any, filename: str) -> None:
    """Wait until the modal shows the selected filename."""
    stem = Path(filename).name.lower()
    try:
        page.wait_for_function(
            """(name) => {
                const text = (document.body.innerText || '').toLowerCase();
                return text.includes(name) || text.includes('.docx') || text.includes('.pdf');
            }""",
            stem,
            timeout=12_000,
        )
    except Exception:  # noqa: BLE001
        pass


def _read_submissions_table(page: Any) -> list[dict[str, Any]]:
    global _LAST_COL_MAP
    payload = page.evaluate(
        """() => {
            const rows = [];
            let colMap = { similarity: 2, ai: 3, status: 4, highlights: 5 };
            const tables = Array.from(document.querySelectorAll('table'));
            for (const table of tables) {
                const heads = Array.from(table.querySelectorAll('thead th, thead td'))
                    .map(h => (h.innerText || h.textContent || '').trim().toLowerCase());
                if (heads.length) {
                    heads.forEach((h, i) => {
                        if (h.includes('similar')) colMap.similarity = i;
                        else if (h.includes('highlight')) colMap.highlights = i;
                        else if (h === 'ai' || h.includes('ai score') || h.includes('ai %')) colMap.ai = i;
                        else if (h.includes('status')) colMap.status = i;
                        else if (h.includes('file')) colMap.filename = i;
                    });
                }
                const trs = Array.from(table.querySelectorAll('tbody tr'));
                for (const tr of trs) {
                    const cells = Array.from(tr.querySelectorAll('td')).map(td =>
                        (td.innerText || td.textContent || '').trim().replace(/\\s+/g, ' ')
                    );
                    if (!cells.length) continue;
                    const idMatch = (cells[0] || '').match(/#?([a-zA-Z0-9]+)/);
                    const cell = (i) => (i >= 0 && i < cells.length ? cells[i] : '');
                    rows.push({
                        id: idMatch ? idMatch[1] : null,
                        filename: cell(colMap.filename || 1) || cells[1] || cells[0] || '',
                        similarity_text: cell(colMap.similarity),
                        ai_text: cell(colMap.ai),
                        status_text: cell(colMap.status),
                        highlights_text: cell(colMap.highlights),
                        row_text: cells.join(' | '),
                    });
                }
            }
            return { rows, colMap };
        }"""
    )
    if isinstance(payload, dict):
        cmap = payload.get("colMap") or {}
        try:
            _LAST_COL_MAP = {
                "similarity": int(cmap.get("similarity", 2)),
                "ai": int(cmap.get("ai", 3)),
                "status": int(cmap.get("status", 4)),
                "highlights": int(cmap.get("highlights", 5)),
            }
        except (TypeError, ValueError):
            pass
        return list(payload.get("rows") or [])
    return list(payload or [])


def _normalize_filename(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _wait_for_upload_row(
    page: Any,
    filename: str,
    *,
    exclude_external_id: str | None = None,
    timeout_s: float = 45.0,
) -> dict[str, Any] | None:
    """Wait for the PlagDetect row created by our upload."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        rows = _read_submissions_table(page)
        for row in rows:
            if exclude_external_id and row.get("id") == exclude_external_id:
                continue
            if _row_status(row) in {"running", "queued"}:
                return row
        row = _find_row(rows, filename, exclude_external_id=exclude_external_id)
        if row and row.get("id"):
            return row
        page.wait_for_timeout(int(_POLL_INTERVAL_S * 1000))
        _refresh_submissions_view(page)
    return None


def _find_row(
    rows: list[dict[str, Any]],
    filename: str,
    external_id: str | None = None,
    *,
    prefer_processing: bool = False,
    exclude_external_id: str | None = None,
) -> dict[str, Any] | None:
    target = filename.lower()
    target_norm = _normalize_filename(filename)
    stem_norm = _normalize_filename(Path(filename).stem)

    if external_id:
        for row in rows:
            if row.get("id") == external_id:
                return row

    candidates: list[dict[str, Any]] = []
    for row in rows:
        if exclude_external_id and row.get("id") == exclude_external_id:
            continue
        fn = (row.get("filename") or "").lower()
        fn_norm = _normalize_filename(fn)
        if fn == target or target in fn or fn in target:
            candidates.append(row)
            continue
        if target_norm and fn_norm and (target_norm in fn_norm or fn_norm in target_norm):
            candidates.append(row)
            continue
        if stem_norm and fn_norm and (stem_norm in fn_norm or fn_norm in stem_norm):
            candidates.append(row)

    if not candidates:
        if prefer_processing:
            for row in rows:
                if exclude_external_id and row.get("id") == exclude_external_id:
                    continue
                status = _row_status(row)
                if status in {"running", "queued"}:
                    return row
        return None

    if prefer_processing:
        for row in candidates:
            if _row_status(row) in {"running", "queued"}:
                return row
    return candidates[0]


def _row_status(row: dict[str, Any]) -> str:
    """Map a PlagDetect table row to queued/running/completed/failed.

    Similarity already scored counts as completed even if the AI cell or
    status column says Failed (PlagDetect does this when AI is outside
    the 300–30,000 word window).
    """
    if _row_has_similarity(row):
        return "completed"
    # Prefer the status column — scanning full row_text can match AI help copy.
    text = (row.get("status_text") or "").upper()
    if "COMPLET" in text or "DONE" in text or "SUCCESS" in text:
        return "completed"
    if "FAIL" in text or "ERROR" in text:
        if _ai_unavailable_reason(row) and _row_has_similarity(row):
            return "completed"
        return "failed"
    if "RUN" in text or "PROCESS" in text or "PENDING" in text:
        return "running"
    if "QUEUE" in text:
        return "queued"
    ai = _parse_percent(row.get("ai_text"))
    if ai is not None:
        return "completed"
    row_blob = (row.get("row_text") or "").upper()
    if "FAIL" in row_blob or "ERROR" in row_blob:
        return "failed"
    return "running"


def _ensure_logged_in(page: Any) -> bool:
    if _is_login_url(page.url):
        return False
    try:
        return bool(
            page.evaluate(
                """() => {
                    const text = (document.body.innerText || '').toLowerCase();
                    return text.includes('my submissions')
                        || text.includes('available slots')
                        || text.includes('upload document')
                        || text.includes('exclude bibliography');
                }"""
            )
        )
    except Exception:  # noqa: BLE001
        return False


def _close_visible_modals(page: Any) -> None:
    page.evaluate(
        """() => {
            const isVisible = el => {
                if (!el) return false;
                const st = getComputedStyle(el);
                if (st.display === 'none' || st.visibility === 'hidden') return false;
                return el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
            };
            document.querySelectorAll('.modal-close').forEach(btn => {
                const modal = btn.closest('.modal, [role="dialog"]');
                if (modal && isVisible(modal)) btn.click();
            });
            document.querySelectorAll('.modal button, [role="dialog"] button').forEach(btn => {
                const modal = btn.closest('.modal, [role="dialog"]');
                if (!modal || !isVisible(modal)) return;
                const t = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                if (t === '×' || t === 'x' || t.includes('cancel') || t === 'close') btn.click();
            });
        }"""
    )
    page.wait_for_timeout(300)


def _submit_modal_visible(page: Any) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                    const isVisible = el => {
                        if (!el) return false;
                        const st = getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden') return false;
                        return el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
                    };
                    for (const modal of document.querySelectorAll('.modal, [role="dialog"]')) {
                        if (!isVisible(modal)) continue;
                        const t = (modal.innerText || modal.textContent || '').toLowerCase();
                        if (t.includes('submit new file') || t.includes('click to upload')) return true;
                    }
                    return false;
                }"""
            )
        )
    except Exception:  # noqa: BLE001
        return False


def _click_dashboard_submit_file(page: Any) -> None:
    """Open the 'Submit New File' modal from the dashboard."""
    clicked = page.evaluate(
        """() => {
            const inModal = el => !!el.closest('.modal, [role="dialog"], [class*="modal" i]');
            const buttons = Array.from(document.querySelectorAll('button, [role="button"], a'));
            for (const el of buttons) {
                if (inModal(el)) continue;
                const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                if (t === 'submit file' || t.includes('submit file')) {
                    el.click();
                    return true;
                }
            }
            return false;
        }"""
    )
    if not clicked:
        raise PlagDetectAutomationError(
            "Could not find the dashboard Submit File button.",
            _collect_diagnostics(page, step="open_submit_modal"),
        )


def _wait_for_submit_modal(page: Any) -> None:
    if _submit_modal_visible(page):
        page.wait_for_timeout(400)
        return
    try:
        page.wait_for_function(
            """() => {
                const isVisible = el => {
                    if (!el) return false;
                    const st = getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    return el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
                };
                for (const modal of document.querySelectorAll('.modal, [role="dialog"]')) {
                    if (!isVisible(modal)) continue;
                    const t = (modal.innerText || modal.textContent || '').toLowerCase();
                    if (t.includes('submit new file') || t.includes('click to upload')) return true;
                }
                return false;
            }""",
            timeout=12_000,
        )
    except Exception as exc:  # noqa: BLE001
        raise PlagDetectAutomationError(
            "Submit New File modal did not appear. "
            "Make sure you are logged in to plagdetect.org in the automation Chrome window.",
            _collect_diagnostics(page, step="wait_submit_modal"),
        ) from exc
    page.wait_for_timeout(400)


def _open_submit_modal(page: Any) -> None:
    _close_visible_modals(page)
    if _submit_modal_visible(page):
        return
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            _click_dashboard_submit_file(page)
            _wait_for_submit_modal(page)
            return
        except PlagDetectAutomationError as exc:
            last_error = exc
            _close_visible_modals(page)
            page.wait_for_timeout(500)
    if last_error:
        raise last_error
    raise PlagDetectAutomationError(
        "Could not open Submit New File modal.",
        _collect_diagnostics(page, step="open_submit_modal"),
    )


def _upload_file_in_modal(page: Any, file_path: str) -> None:
    """Attach the document inside the open modal."""
    resolved = str(Path(file_path).resolve())

    modal_input = page.locator('.modal input[type="file"], [role="dialog"] input[type="file"], #file')
    if modal_input.count() > 0:
        try:
            modal_input.first.set_input_files(resolved)
            page.wait_for_timeout(900)
            return
        except Exception:  # noqa: BLE001
            pass

    file_inputs = page.locator('input[type="file"]')
    for idx in range(file_inputs.count() - 1, -1, -1):
        try:
            file_inputs.nth(idx).set_input_files(resolved)
            page.wait_for_timeout(900)
            return
        except Exception:  # noqa: BLE001
            continue

    # Fallback: click the drop zone and use the native file chooser.
    try:
        with page.expect_file_chooser(timeout=15_000) as fc_info:
            zone_clicked = page.evaluate(
                """() => {
                    const nodes = Array.from(document.querySelectorAll('div, label, button, p, span'));
                    for (const node of nodes) {
                        const t = (node.innerText || node.textContent || '').toLowerCase();
                        if (t.includes('click to upload') || t.includes('drag and drop')) {
                            node.click();
                            return true;
                        }
                    }
                    return false;
                }"""
            )
            if not zone_clicked:
                raise PlagDetectAutomationError(
                    "Could not find upload zone in modal.",
                    _collect_diagnostics(page, step="modal_upload_zone"),
                )
        fc_info.value.set_files(resolved)
        page.wait_for_timeout(900)
    except PlagDetectAutomationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PlagDetectAutomationError(
            f"Could not attach file in modal: {exc}",
            _collect_diagnostics(page, step="modal_upload_file"),
        ) from exc


def _confirm_modal_submit(page: Any) -> None:
    """Click the modal's Submit File button (same label as the dashboard opener)."""
    label = page.evaluate(
        """() => {
            const modal = document.querySelector('.modal:not([style*="display: none"])')
                || document.querySelector('.modal.show')
                || document.querySelector('[role="dialog"]')
                || Array.from(document.querySelectorAll('.modal'))
                    .find(m => (m.innerText || '').toLowerCase().includes('submit new file'));
            if (!modal) return null;
            const buttons = Array.from(modal.querySelectorAll('button, [role="button"]'));
            for (const btn of buttons) {
                const t = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                if (t === 'submit file') {
                    btn.click();
                    return t;
                }
            }
            for (const word of ['submit', 'upload', 'proceed', 'analyze', 'check']) {
                for (const btn of buttons) {
                    const t = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                    if (!t || t.includes('cancel') || t.includes('close')) continue;
                    if (t === word || t.includes(word)) {
                        btn.click();
                        return t;
                    }
                }
            }
            return null;
        }"""
    )
    if not label:
        raise PlagDetectAutomationError(
            "Could not find the confirm button inside Submit New File modal.",
            _collect_diagnostics(page, step="modal_confirm"),
        )
    page.wait_for_timeout(1200)
    try:
        page.wait_for_function(
            """() => {
                const text = (document.body.innerText || '').toLowerCase();
                return !text.includes('submit new file');
            }""",
            timeout=20_000,
        )
    except Exception:  # noqa: BLE001
        pass


def _submit_file_via_modal(page: Any, file_path: str) -> None:
    _open_submit_modal(page)
    _upload_file_in_modal(page, file_path)
    _wait_for_file_attached_in_modal(page, Path(file_path).name)
    _confirm_modal_submit(page)


def _find_row_by_external_id(rows: list[dict[str, Any]], external_id: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("id") == external_id:
            return row
    return None


def _highlights_needs_generation(text: str | None) -> bool:
    lowered = (text or "").lower()
    return "get highlights" in lowered or "unlock highlights" in lowered


def _highlights_processing(text: str | None) -> bool:
    lowered = (text or "").upper()
    return "PROCESS" in lowered or "PENDING" in lowered


def _click_get_highlights(page: Any, external_id: str) -> bool:
    col_idx = _column_index("highlights")
    return bool(
        page.evaluate(
            """([externalId, colIdx]) => {
                const trs = Array.from(document.querySelectorAll('table tbody tr'));
                for (const tr of trs) {
                    const cells = Array.from(tr.querySelectorAll('td'));
                    if (!cells.length) continue;
                    const idText = (cells[0].innerText || cells[0].textContent || '').trim();
                    if (!idText.includes(externalId)) continue;
                    const cell = cells[colIdx];
                    if (!cell) return false;
                    const btn = cell.querySelector('button, a');
                    if (!btn) return false;
                    const label = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                    if (label.includes('get highlights')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""",
            [external_id, col_idx],
        )
    )


def _confirm_highlights_modal(page: Any) -> None:
    page.evaluate(
        """() => {
            const modal = Array.from(document.querySelectorAll('.modal, [role="dialog"]'))
                .find(m => (m.innerText || m.textContent || '').toLowerCase().includes('highlights'));
            if (!modal) return false;
            const buttons = Array.from(modal.querySelectorAll('button, [role="button"]'));
            for (const word of ['generate highlights', 'generate', 'proceed', 'confirm']) {
                for (const btn of buttons) {
                    const t = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                    if (t.includes(word)) { btn.click(); return true; }
                }
            }
            return false;
        }"""
    )
    page.wait_for_timeout(900)


def _fetch_ai_highlights(
    page: Any,
    external_id: str,
    dest: Path,
) -> tuple[dict[str, Any], bool]:
    """Request AI Highlights when AI score is *% and download the report."""
    parsed: dict[str, Any] = {"numeric": None, "display": None}
    _reload_dashboard(page)
    deadline = time.monotonic() + _highlights_timeout_s()
    triggered = False
    poll_count = 0

    while time.monotonic() < deadline:
        rows = _read_submissions_table(page)
        row = _find_row_by_external_id(rows, external_id)
        if row is None:
            page.wait_for_timeout(int(_POLL_INTERVAL_S * 1000))
            poll_count += 1
            if poll_count % _RELOAD_EVERY_N_POLLS == 0:
                _reload_dashboard(page)
            continue

        hl_text = row.get("highlights_text") or ""
        if _highlights_needs_generation(hl_text) and not triggered:
            if _click_get_highlights(page, external_id):
                _confirm_highlights_modal(page)
                triggered = True
            page.wait_for_timeout(int(_POLL_INTERVAL_S * 1000))
            continue

        candidate = _parse_score_text(hl_text)
        if candidate.get("numeric") is not None:
            parsed = candidate
            break
        if _highlights_processing(hl_text):
            page.wait_for_timeout(int(_POLL_INTERVAL_S * 1000))
            poll_count += 1
            if poll_count % _RELOAD_EVERY_N_POLLS == 0:
                _reload_dashboard(page)
            continue
        if hl_text.strip() in {"-", "—", ""} and not triggered:
            if _click_get_highlights(page, external_id):
                _confirm_highlights_modal(page)
                triggered = True
            page.wait_for_timeout(int(_POLL_INTERVAL_S * 1000))
            continue
        break

    if parsed.get("numeric") is None:
        rows = _read_submissions_table(page)
        row = _find_row_by_external_id(rows, external_id)
        if row:
            parsed = _parse_score_text(row.get("highlights_text"))

    ok = False
    if parsed.get("numeric") is not None:
        _reload_dashboard(page)
        ok = _download_report(page, external_id, "highlights", dest)
    return parsed, ok


def _inspect_download_control(page: Any, external_id: str, column: str) -> dict[str, Any]:
    """Locate the Download control in a PlagDetect score cell (href preferred)."""
    col_idx = _column_index(column)
    return page.evaluate(
        """([externalId, colIdx]) => {
            const score = (el) => {
                const label = ((el.innerText || el.textContent || '') + ' '
                    + (el.getAttribute('aria-label') || '') + ' '
                    + (el.getAttribute('title') || '') + ' '
                    + (el.getAttribute('href') || '')).toLowerCase();
                let pts = 0;
                if (label.includes('download')) pts += 5;
                if (label.includes('.pdf') || (el.getAttribute('href') || '').includes('pdf')) pts += 4;
                if (el.hasAttribute('download')) pts += 4;
                if ((el.tagName || '').toLowerCase() === 'a' && el.getAttribute('href')) pts += 2;
                if ((el.tagName || '').toLowerCase() === 'button') pts += 1;
                return pts;
            };
            const trs = Array.from(document.querySelectorAll('table tbody tr'));
            for (const tr of trs) {
                const cells = Array.from(tr.querySelectorAll('td'));
                if (!cells.length) continue;
                const idText = (cells[0].innerText || cells[0].textContent || '').trim();
                if (!idText.includes(externalId)) continue;
                const cell = cells[colIdx];
                if (!cell) return { found: false };
                const candidates = Array.from(
                    cell.querySelectorAll('a, button, [role="button"]')
                );
                if (!candidates.length) return { found: false, cellText: (cell.innerText || '').trim() };
                candidates.sort((a, b) => score(b) - score(a));
                const el = candidates[0];
                const href = el.getAttribute('href') || null;
                return {
                    found: true,
                    href,
                    label: (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim(),
                    tag: (el.tagName || '').toLowerCase(),
                    score: score(el),
                };
            }
            return { found: false };
        }""",
        [external_id, col_idx],
    ) or {"found": False}


def _click_download_in_row(page: Any, external_id: str, column: str) -> bool:
    """Click Download in the PlagDetect row (AI=2, similarity=3, highlights=5)."""
    col_idx = _column_index(column)
    return bool(
        page.evaluate(
            """([externalId, colIdx]) => {
                const score = (el) => {
                    const label = ((el.innerText || el.textContent || '') + ' '
                        + (el.getAttribute('aria-label') || '') + ' '
                        + (el.getAttribute('title') || '') + ' '
                        + (el.getAttribute('href') || '')).toLowerCase();
                    let pts = 0;
                    if (label.includes('download')) pts += 5;
                    if (label.includes('.pdf') || (el.getAttribute('href') || '').includes('pdf')) pts += 4;
                    if (el.hasAttribute('download')) pts += 4;
                    if ((el.tagName || '').toLowerCase() === 'a' && el.getAttribute('href')) pts += 2;
                    if ((el.tagName || '').toLowerCase() === 'button') pts += 1;
                    return pts;
                };
                const trs = Array.from(document.querySelectorAll('table tbody tr'));
                for (const tr of trs) {
                    const cells = Array.from(tr.querySelectorAll('td'));
                    if (!cells.length) continue;
                    const idText = (cells[0].innerText || cells[0].textContent || '').trim();
                    if (!idText.includes(externalId)) continue;
                    const cell = cells[colIdx];
                    if (!cell) return false;
                    const candidates = Array.from(
                        cell.querySelectorAll('a, button, [role="button"]')
                    );
                    if (!candidates.length) return false;
                    candidates.sort((a, b) => score(b) - score(a));
                    const el = candidates[0];
                    if (score(el) <= 0) return false;
                    el.click();
                    return true;
                }
                return false;
            }""",
            [external_id, col_idx],
        )
    )


def _absolute_url(page: Any, href: str) -> str:
    from urllib.parse import urljoin

    return urljoin(page.url or _dashboard_url(), href)


def _download_via_http(page: Any, href: str, dest: Path) -> bool:
    """Fetch a report PDF using the authenticated browser cookie jar."""
    if not href or href.startswith("javascript:") or href == "#":
        return False
    url = _absolute_url(page, href)
    try:
        response = page.context.request.get(url, timeout=_DOWNLOAD_TIMEOUT_MS)
        if not response.ok:
            print(f"[plagdetect] HTTP download failed ({response.status}): {url}", flush=True)
            return False
        body = response.body()
        if not body or len(body) < 64:
            return False
        ctype = (response.headers.get("content-type") or "").lower()
        looks_pdf = (
            body[:4] == b"%PDF"
            or "pdf" in ctype
            or "octet-stream" in ctype
            or url.lower().endswith(".pdf")
        )
        if not looks_pdf:
            print(f"[plagdetect] HTTP download was not a PDF ({ctype}): {url}", flush=True)
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return dest.is_file() and dest.stat().st_size > 0
    except Exception as exc:  # noqa: BLE001
        print(f"[plagdetect] HTTP download error: {exc}", flush=True)
        return False


def _download_via_playwright_event(page: Any, external_id: str, column: str, dest: Path) -> bool:
    try:
        with page.expect_download(timeout=_DOWNLOAD_TIMEOUT_MS) as dl_info:
            if not _click_download_in_row(page, external_id, column):
                return False
        download = dl_info.value
        dest.parent.mkdir(parents=True, exist_ok=True)
        download.save_as(str(dest))
        return dest.is_file() and dest.stat().st_size > 0
    except Exception as exc:  # noqa: BLE001
        print(f"[plagdetect] Playwright download event failed ({column}): {exc}", flush=True)
        return False


def _download_via_cdp_dir(page: Any, external_id: str, column: str, dest: Path) -> bool:
    """Last resort: force Chrome download path via CDP, then pick up the file."""
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="plagdetect-dl-"))
    session = None
    try:
        session = page.context.new_cdp_session(page)
        # Prefer Page.setDownloadBehavior — Browser.setDownloadBehavior is rejected
        # on some Chrome+CDP combos (see cdp_compat.py).
        try:
            session.send(
                "Page.setDownloadBehavior",
                {"behavior": "allow", "downloadPath": str(tmp), "eventsEnabled": True},
            )
        except Exception:  # noqa: BLE001
            try:
                session.send(
                    "Browser.setDownloadBehavior",
                    {
                        "behavior": "allow",
                        "downloadPath": str(tmp),
                        "eventsEnabled": True,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[plagdetect] CDP setDownloadBehavior failed: {exc}", flush=True)
                return False

        before = {p.name for p in tmp.iterdir()} if tmp.is_dir() else set()
        if not _click_download_in_row(page, external_id, column):
            return False

        deadline = time.monotonic() + (_DOWNLOAD_TIMEOUT_MS / 1000.0)
        chosen: Path | None = None
        while time.monotonic() < deadline:
            page.wait_for_timeout(400)
            files = [
                p
                for p in tmp.iterdir()
                if p.is_file()
                and not p.name.endswith(".crdownload")
                and not p.name.endswith(".tmp")
                and p.name not in before
            ]
            pdfs = [p for p in files if p.suffix.lower() == ".pdf" or p.read_bytes()[:4] == b"%PDF"]
            pool = pdfs or files
            if pool:
                chosen = max(pool, key=lambda p: p.stat().st_mtime)
                if chosen.stat().st_size > 0:
                    break
                chosen = None
        if chosen is None:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(chosen.read_bytes())
        return dest.is_file() and dest.stat().st_size > 0
    except Exception as exc:  # noqa: BLE001
        print(f"[plagdetect] CDP dir download failed ({column}): {exc}", flush=True)
        return False
    finally:
        if session is not None:
            try:
                session.detach()
            except Exception:  # noqa: BLE001
                pass
        try:
            for p in tmp.iterdir():
                p.unlink(missing_ok=True)
            tmp.rmdir()
        except Exception:  # noqa: BLE001
            pass


def _wait_for_download_controls(page: Any, external_id: str, timeout_s: float = 20.0) -> bool:
    """Wait until score cells expose Download controls after processing finishes."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        ai = _inspect_download_control(page, external_id, "ai")
        sim = _inspect_download_control(page, external_id, "similarity")
        if ai.get("found") and sim.get("found"):
            return True
        if ai.get("found") or sim.get("found"):
            # Partial is still useful — keep waiting briefly for the other.
            page.wait_for_timeout(800)
            return True
        page.wait_for_timeout(800)
        _refresh_submissions_view(page, force_reload=False)
    return False


def _download_report(page: Any, external_id: str, column: str, dest: Path) -> bool:
    """Download one PlagDetect report PDF into ``dest``.

    Order: authenticated HTTP (href) → Playwright download event → CDP download dir.
    CDP ``expect_download`` often fails with ``connect_over_cdp(no_defaults=True)``.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    info = _inspect_download_control(page, external_id, column)
    href = (info or {}).get("href")
    if href and _download_via_http(page, str(href), dest):
        return True
    if _download_via_playwright_event(page, external_id, column, dest):
        return True
    if _download_via_cdp_dir(page, external_id, column, dest):
        return True
    print(
        f"[plagdetect] Could not download {column} report for {external_id} "
        f"(control={info})",
        flush=True,
    )
    return False


def _download_both_reports(
    page: Any,
    external_id: str,
    ai_dest: Path,
    sim_dest: Path,
) -> tuple[bool, bool]:
    """Download both PDFs after scores complete; never blocks job success."""
    _reload_dashboard(page)
    _wait_for_download_controls(page, external_id)
    ai_ok = _download_report(page, external_id, "ai", ai_dest)
    sim_ok = _download_report(page, external_id, "similarity", sim_dest)
    if ai_ok and sim_ok:
        return ai_ok, sim_ok
    _reload_dashboard(page)
    _wait_for_download_controls(page, external_id, timeout_s=10.0)
    if not ai_ok:
        ai_ok = _download_report(page, external_id, "ai", ai_dest)
    if not sim_ok:
        sim_ok = _download_report(page, external_id, "similarity", sim_dest)
    return ai_ok, sim_ok


def submit_check(
    file_path: str,
    *,
    exclude_bibliography: bool = False,
    exclude_quotes: bool = False,
    report_dir: str | None = None,
    submission_id: str | None = None,
) -> dict[str, Any]:
    """Upload a document to PlagDetect, wait for scores, download both reports."""
    _validate_urls()
    path = Path(file_path)
    if not path.is_file():
        return {"success": False, "error": "file not found"}

    page = _page()
    started = time.monotonic()
    filename = path.name
    checkpoint = _load_checkpoint(submission_id)
    external_id: str | None = (checkpoint or {}).get("external_id")
    plagdetect_filename: str | None = (checkpoint or {}).get("plagdetect_filename")
    uploaded = bool((checkpoint or {}).get("uploaded"))

    page.goto(_dashboard_url(), wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(800)

    if not _require_login(page):
        return {
            "success": False,
            "error": "LOGIN_REQUIRED",
            "message": (
                "PlagDetect session is not logged in. "
                "Set PLAGDETECT_EMAIL and PLAGDETECT_PASSWORD in .env and restart, "
                "then call /api/browser/providers/plagdetect/login once."
            ),
        }

    if not uploaded:
        _reload_dashboard(page)
        if not _require_login(page):
            return {"success": False, "error": "LOGIN_REQUIRED"}
        _apply_exclude_toggles(
            page,
            exclude_bibliography=exclude_bibliography,
            exclude_quotes=exclude_quotes,
        )
        _submit_file_via_modal(page, str(path.resolve()))
        page.wait_for_timeout(2500)
        upload_row = _wait_for_upload_row(
            page,
            filename,
            exclude_external_id=external_id,
        )
        if upload_row is None:
            raise PlagDetectAutomationError(
                "Upload started but the submission row did not appear.",
                _collect_diagnostics(page, step="wait_upload_row", extra={"filename": filename}),
            )
        external_id = upload_row.get("id") or external_id
        plagdetect_filename = upload_row.get("filename") or plagdetect_filename
        if submission_id and external_id:
            _save_checkpoint(
                submission_id,
                {
                    "uploaded": True,
                    "external_id": external_id,
                    "plagdetect_filename": plagdetect_filename,
                    "source_filename": filename,
                },
            )
            _persist_store_external_id(submission_id, external_id)
            uploaded = True

    if not external_id:
        raise PlagDetectAutomationError(
            "Missing PlagDetect submission id after upload.",
            _collect_diagnostics(page, step="missing_external_id"),
        )

    deadline = time.monotonic() + _check_timeout_s()
    row: dict[str, Any] | None = None
    status = "queued"
    poll_count = 0

    while time.monotonic() < deadline:
        if _is_login_url(page.url) and not _require_login(page):
            return {"success": False, "error": "LOGIN_REQUIRED", "external_id": external_id}

        page.wait_for_timeout(int(_POLL_INTERVAL_S * 1000))
        poll_count += 1
        _refresh_submissions_view(page, force_reload=(poll_count % _RELOAD_EVERY_N_POLLS == 0))

        rows = _read_submissions_table(page)
        row = _find_row(rows, filename, external_id)
        if row is None:
            continue
        external_id = row.get("id") or external_id
        plagdetect_filename = row.get("filename") or plagdetect_filename
        status = _row_status(row)
        if status == "failed" and _row_has_similarity(row):
            status = "completed"
            break
        if status == "failed":
            return {
                "success": False,
                "error": row.get("status_text") or "External check failed",
                "external_id": external_id,
            }
        if status == "completed":
            break

    if row is None or status != "completed":
        raise PlagDetectAutomationError(
            "Timed out waiting for PlagDetect results.",
            _collect_diagnostics(
                page,
                step="poll_results",
                extra={"filename": filename, "external_id": external_id},
            ),
        )

    ai_parsed = _parse_score_text(row.get("ai_text"))
    sim_parsed = _parse_score_text(row.get("similarity_text"))
    ai_unavailable = _ai_unavailable_reason(row)
    if ai_unavailable:
        ai_parsed = {"numeric": None, "display": None}

    out_dir = Path(report_dir) if report_dir else path.parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    ai_report = out_dir / f"{path.stem}_ai_report.pdf"
    sim_report = out_dir / f"{path.stem}_similarity_report.pdf"

    ai_ok = False
    sim_ok = False
    if external_id:
        for attempt in range(1, 4):
            try:
                if ai_unavailable:
                    sim_ok = _download_report(page, external_id, "similarity", sim_report)
                    ai_ok = False
                else:
                    ai_ok, sim_ok = _download_both_reports(page, external_id, ai_report, sim_report)
            except Exception as exc:  # noqa: BLE001
                print(f"[plagdetect] report download attempt {attempt} failed: {exc}", flush=True)
                ai_ok, sim_ok = False, False
            if sim_ok and (ai_ok or ai_unavailable):
                break
            print(
                f"[plagdetect] report download incomplete "
                f"(ai={ai_ok}, similarity={sim_ok}, ai_unavailable={bool(ai_unavailable)}) "
                f"— retry {attempt}/3",
                flush=True,
            )
            page.wait_for_timeout(1500)
            _reload_dashboard(page)

    _clear_checkpoint(submission_id)
    elapsed = round(time.monotonic() - started, 3)
    return {
        "success": True,
        "external_id": external_id,
        "filename": filename,
        "plagdetect_filename": plagdetect_filename,
        "similarity": sim_parsed["numeric"],
        "similarity_display": sim_parsed["display"],
        "ai_score": ai_parsed["numeric"],
        "ai_score_display": ai_parsed["display"],
        "ai_unavailable": ai_unavailable,
        "ai_report_path": str(ai_report.resolve()) if ai_ok else None,
        "similarity_report_path": str(sim_report.resolve()) if sim_ok else None,
        "elapsed_seconds": elapsed,
        "current_url": page.url,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_reports(
    *,
    external_id: str,
    report_dir: str | Path,
    submission_id: str | None = None,
    fetch_similarity: bool = True,
    fetch_ai: bool = True,
    fetch_highlights: bool = False,
) -> dict[str, Any]:
    """Re-download report PDFs from PlagDetect for an existing submission."""
    _validate_urls()
    ext = (external_id or "").strip()
    if not ext:
        raise PlagDetectAutomationError(
            "PlagDetect submission id is required.",
            _collect_diagnostics(None, step="fetch_reports"),
        )

    page = _page()
    page.goto(_dashboard_url(), wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(800)

    if not _require_login(page):
        return {"success": False, "error": "LOGIN_REQUIRED"}

    out_dir = Path(report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = submission_id or ext
    started = time.monotonic()

    ai_report = out_dir / f"{stem}_ai_report.pdf"
    sim_report = out_dir / f"{stem}_similarity_report.pdf"
    hl_report = out_dir / f"{stem}_highlights_report.pdf"

    ai_ok = False
    sim_ok = False
    hl_ok = False
    hl_parsed: dict[str, Any] = {"numeric": None, "display": None}

    _reload_dashboard(page)
    _wait_for_download_controls(page, ext)
    if fetch_ai:
        ai_ok = _download_report(page, ext, "ai", ai_report)
    if fetch_similarity:
        sim_ok = _download_report(page, ext, "similarity", sim_report)
    if (fetch_ai and not ai_ok) or (fetch_similarity and not sim_ok):
        _reload_dashboard(page)
        _wait_for_download_controls(page, ext, timeout_s=10.0)
        if fetch_ai and not ai_ok:
            ai_ok = _download_report(page, ext, "ai", ai_report)
        if fetch_similarity and not sim_ok:
            sim_ok = _download_report(page, ext, "similarity", sim_report)

    if fetch_highlights:
        rows = _read_submissions_table(page)
        row = _find_row_by_external_id(rows, ext)
        if row:
            hl_parsed = _parse_score_text(row.get("highlights_text"))
        if hl_parsed.get("numeric") is not None or hl_parsed.get("display"):
            hl_ok = _download_report(page, ext, "highlights", hl_report)
        else:
            # Score not ready yet — try Get Highlights flow.
            try:
                hl_parsed, hl_ok = _fetch_ai_highlights(page, ext, hl_report)
            except Exception:  # noqa: BLE001
                pass

    return {
        "success": True,
        "external_id": ext,
        "ai_report_path": str(ai_report.resolve()) if ai_ok else None,
        "similarity_report_path": str(sim_report.resolve()) if sim_ok else None,
        "ai_highlights": hl_parsed.get("numeric"),
        "ai_highlights_display": hl_parsed.get("display"),
        "ai_highlights_report_path": str(hl_report.resolve()) if hl_ok else None,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "current_url": page.url,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def submit_highlights(
    *,
    external_id: str,
    report_dir: str | Path,
    submission_id: str | None = None,
) -> dict[str, Any]:
    """Request AI Highlights on PlagDetect (user-initiated) and download the PDF."""
    _validate_urls()
    ext = (external_id or "").strip()
    if not ext:
        raise PlagDetectAutomationError(
            "PlagDetect submission id is required for AI Highlights.",
            _collect_diagnostics(None, step="highlights"),
        )

    page = _page()
    page.goto(_dashboard_url(), wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(800)

    if not _require_login(page):
        return {"success": False, "error": "LOGIN_REQUIRED"}

    out_dir = Path(report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = submission_id or ext
    highlights_report = out_dir / f"{stem}_highlights_report.pdf"

    started = time.monotonic()
    highlights_parsed, highlights_ok = _fetch_ai_highlights(page, ext, highlights_report)

    if highlights_parsed.get("numeric") is None and not highlights_parsed.get("display"):
        raise PlagDetectAutomationError(
            "AI Highlights did not finish in time.",
            _collect_diagnostics(
                page,
                step="highlights",
                extra={"external_id": ext},
            ),
        )

    return {
        "success": True,
        "external_id": ext,
        "ai_highlights": highlights_parsed.get("numeric"),
        "ai_highlights_display": highlights_parsed.get("display"),
        "ai_highlights_report_path": str(highlights_report.resolve()) if highlights_ok else None,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "current_url": page.url,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


class PlagDetectProvider(Provider):
    name = PROVIDER_NAME

    def initialize(self) -> None:
        self.page()

    def login(self, *, credentials: dict[str, Any] | None = None) -> Any:
        return start_interactive_login()

    def is_logged_in(self) -> bool:
        try:
            return bool(get_session_status().get("logged_in"))
        except Exception:  # noqa: BLE001
            return False

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "logged_in": self.is_logged_in()}

    def execute(self, task: Any) -> Any:
        if isinstance(task, dict) and task.get("operation") == "check":
            payload = task.get("payload") or {}
            return submit_check(
                str(payload.get("file_path") or ""),
                exclude_bibliography=bool(payload.get("exclude_bibliography")),
                exclude_quotes=bool(payload.get("exclude_quotes")),
                report_dir=payload.get("report_dir"),
                submission_id=payload.get("submission_id"),
            )
        if isinstance(task, dict) and task.get("operation") == "highlights":
            payload = task.get("payload") or {}
            return submit_highlights(
                external_id=str(payload.get("external_id") or ""),
                report_dir=str(payload.get("report_dir") or ""),
                submission_id=payload.get("submission_id"),
            )
        if isinstance(task, dict) and task.get("operation") == "fetch_reports":
            payload = task.get("payload") or {}
            return fetch_reports(
                external_id=str(payload.get("external_id") or ""),
                report_dir=str(payload.get("report_dir") or ""),
                submission_id=payload.get("submission_id"),
                fetch_similarity=bool(payload.get("fetch_similarity", True)),
                fetch_ai=bool(payload.get("fetch_ai", True)),
                fetch_highlights=bool(payload.get("fetch_highlights", False)),
            )
        raise NotImplementedError(f"Unsupported PlagDetect task: {task!r}")
