"""StealthWriter provider — page, selectors, buttons, workflow ONLY.

All browser lifecycle (Chrome, CDP, context, tabs, recovery, cookies) is owned
by BrowserService. This module never launches or closes a browser; it only asks
BrowserService for its persistent tab and drives the StealthWriter UI.

The humanize workflow is intentionally unchanged from the previous
implementation — only the source of the page has moved to BrowserService.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.browser.browser_service import BrowserService
from services.browser.providers.base import Provider

PROVIDER_NAME = "stealthwriter"

_HOME_URL = "https://stealthwriter.ai"
_DASHBOARD_URL = "https://stealthwriter.ai/dashboard"
_SIGN_IN_URL = "https://stealthwriter.ai/sign-in"
_HUMANIZER_URL = "https://stealthwriter.ai/dashboard/humanizer"
_SCREENSHOT_REL = Path("browser_profiles/debug/stealthwriter-home.png")
_HUMANIZE_TIMEOUT_MS = 120_000


def _page() -> Any:
    """The StealthWriter persistent tab, owned by BrowserService."""
    return BrowserService.instance().get_or_create_page(PROVIDER_NAME)


def _profile_path() -> str:
    return str(BrowserService.instance().user_data_dir.resolve())


# ------------------------------------------------------------------ login helpers
def start_interactive_login() -> dict[str, Any]:
    """Navigate the StealthWriter tab to sign-in for manual login."""
    page = _page()
    already = BrowserService.instance().is_running()
    page.goto(_SIGN_IN_URL, wait_until="domcontentloaded")
    return {
        "success": True,
        "already_open": already,
        "cdp_url": BrowserService.instance().cdp_url,
        "profile": _profile_path(),
        "message": "Attached to Chrome. Please login manually in the open browser.",
    }


def check_interactive_login() -> dict[str, Any]:
    """Check whether the StealthWriter session is authenticated. Never closes Chrome."""
    page = _page()
    page.goto(_DASHBOARD_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    current_url = page.url
    title = page.title()
    redirected = _is_sign_in_url(current_url)
    logged_in = (not redirected) and ("/dashboard" in current_url.lower())
    return {
        "success": True,
        "logged_in": logged_in,
        "dashboard_loaded": logged_in,
        "current_url": current_url,
        "title": title,
        "redirected": redirected,
        "cdp_url": BrowserService.instance().cdp_url,
        "profile": _profile_path(),
        "runtime_shutdown": False,
        "message": (
            "Login confirmed. Browser kept alive (CDP session)."
            if logged_in
            else "Not logged in yet. Finish login in Chrome, then call check-login again."
        ),
    }


def open_manual_login_browser() -> dict[str, Any]:
    """Alias for start_interactive_login (legacy /open endpoint)."""
    return start_interactive_login()


# ------------------------------------------------------------------ diagnostics
class StealthWriterAutomationError(Exception):
    """Raised when a UI step fails; carries diagnostics for the API response."""

    def __init__(self, message: str, diagnostics: dict[str, Any]) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


def _collect_page_diagnostics(page: Any, *, step: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    diag: dict[str, Any] = {"step": step}
    try:
        diag["current_url"] = page.url
        diag["page_title"] = page.title()
        diag["textarea_count"] = page.locator("textarea").count()
        diag["visible_buttons"] = page.evaluate(
            """() => Array.from(document.querySelectorAll('button, [role="button"], a'))
                .map(el => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' '))
                .filter(Boolean)
                .slice(0, 40)"""
        )
        diag["dom_snippet"] = page.evaluate(
            """() => {
                const root = document.querySelector('main') || document.body;
                const text = (root && root.innerText) ? root.innerText.slice(0, 2500) : '';
                const html = (root && root.innerHTML) ? root.innerHTML.slice(0, 2500) : '';
                return { text, html };
            }"""
        )
    except Exception as exc:  # noqa: BLE001
        diag["diagnostics_error"] = str(exc)
    if extra:
        diag.update(extra)
    return diag


def _read_locator_text(locator: Any) -> str:
    try:
        tag = locator.evaluate("el => (el.tagName || '').toLowerCase()")
        if tag in {"textarea", "input"}:
            return (locator.input_value() or "").strip()
        return (locator.inner_text() or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _find_input_textarea(page: Any) -> Any:
    candidates = [
        page.get_by_placeholder(re.compile(r"paste|text|humaniz|write|enter", re.I)),
        page.locator("textarea").first,
        page.locator('[contenteditable="true"]').first,
        page.locator('[role="textbox"]').first,
    ]
    for loc in candidates:
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=2000):
                return loc.first
        except Exception:  # noqa: BLE001
            continue
    return None


def _find_humanize_button(page: Any) -> Any:
    candidates = [
        page.get_by_role("button", name=re.compile(r"^\s*humanize\s*$", re.I)),
        page.get_by_role("button", name=re.compile(r"humanize", re.I)),
        page.locator("button").filter(has_text=re.compile(r"^\s*humanize\s*$", re.I)),
        page.locator("button").filter(has_text=re.compile(r"humanize", re.I)),
        page.locator('[type="submit"]').filter(has_text=re.compile(r"humanize", re.I)),
    ]
    for loc in candidates:
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=2000):
                return loc.first
        except Exception:  # noqa: BLE001
            continue
    return None


def _find_output_area(page: Any, input_locator: Any) -> Any:
    """Prefer a second textarea/output panel distinct from the input."""
    textareas = page.locator("textarea")
    try:
        count = textareas.count()
        if count >= 2:
            return textareas.nth(1)
    except Exception:  # noqa: BLE001
        pass
    for loc in [
        page.locator("[data-output]"),
        page.locator(".output, .result, [class*='output'], [class*='result']").locator(
            "textarea, [contenteditable='true']"
        ),
        page.get_by_role("textbox").nth(1),
    ]:
        try:
            if loc.count() > 0:
                return loc.first
        except Exception:  # noqa: BLE001
            continue
    return input_locator


# StealthWriter renders the result inside the "Humanized Result" card as a
# `div.whitespace-pre-wrap` whose sentences are clickable <span>s — NOT a second
# <textarea>. We read that div's innerText directly.
_RESULT_EXTRACTION_JS = r"""(cleaned) => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const cleanedN = norm(cleaned);

    // Preferred: the result prose container inside the Humanized Result card.
    const selectors = [
        'div.whitespace-pre-wrap',
        '[class*="whitespace-pre-wrap"]',
    ];
    let best = '';
    for (const sel of selectors) {
        for (const el of Array.from(document.querySelectorAll(sel))) {
            // A <textarea> is never matched by these div selectors, so this is
            // always the rendered output, never the input.
            const tx = norm(el.innerText);
            if (tx.length > 20 && tx !== cleanedN && tx.length > best.length) best = tx;
        }
        if (best) break;
    }
    if (best) return best;

    // Fallback: locate the result card via its action buttons, then take the
    // longest prose block that isn't the input or the help/footer line.
    const marker = Array.from(document.querySelectorAll('button')).find(
        b => /rehumanize|humanize more/i.test(norm(b.innerText))
    );
    if (marker) {
        let panel = marker;
        for (let k = 0; k < 8 && panel.parentElement; k++) {
            panel = panel.parentElement;
            if (norm(panel.innerText).length > 200) break;
        }
        const skip = /green = high human|click sentences|deep scan|^\d+\s+words$/i;
        panel.querySelectorAll('div, p, span').forEach(el => {
            if (el.querySelector('button')) return;
            const tx = norm(el.innerText);
            if (tx.length > 25 && tx !== cleanedN && !skip.test(tx) && tx.length > best.length) {
                best = tx;
            }
        });
    }
    return best;
}"""


def _extract_result_text(page: Any, cleaned: str) -> str:
    """Return the rendered humanized text, or '' if not present yet."""
    try:
        value = page.evaluate(_RESULT_EXTRACTION_JS, cleaned)
        return (value or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _result_ready(page: Any) -> bool:
    """The result card exposes Rehumanize / Humanize More once generation is done."""
    try:
        return (
            page.get_by_role(
                "button", name=re.compile(r"rehumanize|humanize more", re.I)
            ).count()
            > 0
        )
    except Exception:  # noqa: BLE001
        return False


def _generation_busy(page: Any) -> bool:
    """True only while generation is actually running.

    IMPORTANT: match the transient "Humanizing…" *button* only — a loose page
    text match for "humanizing" also hits StealthWriter's permanent FAQ line
    ("Common questions about humanizing text…"), which would make this return
    True forever and never let us read the result.
    """
    try:
        if (
            page.get_by_role("button", name=re.compile(r"humanizing", re.I)).count()
            > 0
        ):
            return True
        busy = page.locator('[aria-busy="true"], .animate-spin, [class*="spinner"]')
        return busy.count() > 0
    except Exception:  # noqa: BLE001
        return False


def _detect_limit_message(page: Any) -> str:
    """Return a visible StealthWriter limit/error toast message, or ''.

    Scans only toast/alert regions (not the FAQ body) for limit wording.
    """
    try:
        txt = page.evaluate(
            r"""() => {
                const norm = s => (s || '').replace(/\s+/g, ' ').trim();
                const nodes = document.querySelectorAll(
                    '[data-sonner-toast], [role="alert"], [role="status"], [class*="toast"]'
                );
                for (const n of nodes) {
                    const t = norm(n.innerText);
                    if (t && t.length < 240 &&
                        /limit|reached|upgrade|too many|no more|out of|daily|quota|suspend/i.test(t)) {
                        return t;
                    }
                }
                return '';
            }"""
        )
        return (txt or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _safe_url(page: Any) -> str | None:
    try:
        return page.url
    except Exception:  # noqa: BLE001
        return None


def _is_sign_in_url(url: str) -> bool:
    lower = (url or "").lower()
    return "/sign-in" in lower or "/signin" in lower


# ------------------------------------------------------------------ humanize workflow
def humanize_text(text: str) -> dict[str, Any]:
    """Run one end-to-end humanization in the shared long-lived browser.

    Does not perform login. If the session is expired, returns LOGIN_REQUIRED.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return {"success": False, "error": "text is required", "humanized_text": None}

    page = _page()
    started = time.monotonic()

    # Open humanizer directly — never navigate to /sign-in or attempt login.
    page.goto(_HUMANIZER_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=30_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(800)

    if _is_sign_in_url(page.url):
        return {"success": False, "error": "LOGIN_REQUIRED"}

    # Locate textarea
    input_box = _find_input_textarea(page)
    if input_box is None:
        raise StealthWriterAutomationError(
            "Could not locate humanizer textarea.",
            _collect_page_diagnostics(page, step="locate_textarea"),
        )

    # Clear and paste
    try:
        input_box.click(timeout=5000)
        input_box.fill("")
        input_box.fill(cleaned)
        # Confirm value stuck (React controlled inputs sometimes need a beat)
        page.wait_for_timeout(300)
        typed = _read_locator_text(input_box)
        if typed.strip() != cleaned:
            # Fallback: select-all + keyboard type for stubborn editors
            input_box.click()
            modifier = "Meta" if page.evaluate("() => navigator.platform.includes('Mac')") else "Control"
            page.keyboard.press(f"{modifier}+A")
            page.keyboard.insert_text(cleaned)
    except Exception as exc:  # noqa: BLE001
        raise StealthWriterAutomationError(
            f"Failed to paste text into textarea: {exc}",
            _collect_page_diagnostics(page, step="paste_text"),
        ) from exc

    # Click Humanize
    button = _find_humanize_button(page)
    if button is None:
        raise StealthWriterAutomationError(
            "Could not locate Humanize button.",
            _collect_page_diagnostics(page, step="locate_humanize_button"),
        )
    try:
        button.click(timeout=5000)
    except Exception as exc:  # noqa: BLE001
        raise StealthWriterAutomationError(
            f"Failed to click Humanize button: {exc}",
            _collect_page_diagnostics(page, step="click_humanize"),
        ) from exc

    # Wait until generation finishes. The result renders in the "Humanized
    # Result" card (a div.whitespace-pre-wrap), not a textarea.
    # Capture any pre-existing result so we only accept the freshly generated one.
    previous_result = _extract_result_text(page, cleaned)
    started_wait = time.monotonic()
    deadline = started_wait + (_HUMANIZE_TIMEOUT_MS / 1000)
    humanized = ""
    last_value = ""
    stable_reads = 0
    saw_busy = False
    busy_cleared_at: float | None = None
    noop_reads = 0

    def _no_change(reason: str) -> dict[str, Any]:
        return {
            "success": False,
            "error": "NO_CHANGE",
            "message": reason,
            "current_url": _safe_url(page),
        }

    _limit_reason = (
        "StealthWriter didn't rewrite the text — your free-plan daily "
        "humanization limit is likely reached (it resets at midnight UTC). "
        "Try again after the reset or upgrade the plan."
    )

    while time.monotonic() < deadline:
        try:
            page.wait_for_timeout(800)

            if _generation_busy(page):
                saw_busy = True
                busy_cleared_at = None
                noop_reads = 0
                continue
            if saw_busy and busy_cleared_at is None:
                busy_cleared_at = time.monotonic()

            # An explicit limit/error toast → stop immediately with a clear reason.
            toast = _detect_limit_message(page)
            if toast:
                return _no_change(toast)

            current = _extract_result_text(page, cleaned)

            # A genuinely rewritten result: different from input AND any leftover.
            if current and len(current) > 20 and current != cleaned and current != previous_result:
                if current == last_value:
                    stable_reads += 1
                else:
                    stable_reads = 0
                    last_value = current
                if stable_reads >= 2 or (_result_ready(page) and stable_reads >= 1):
                    humanized = current
                    break
                continue

            # No fresh result. Decide whether generation actually finished:
            #   * result card is present (Rehumanize/Humanize More), or
            #   * we saw "Humanizing…" and it cleared a few seconds ago, or
            #   * we never saw it start after a reasonable grace (limit blocked it).
            finished = (
                _result_ready(page)
                or (busy_cleared_at is not None and time.monotonic() - busy_cleared_at > 5)
                or (not saw_busy and time.monotonic() - started_wait > 25)
            )
            if finished:
                noop_reads += 1
                if noop_reads >= 3:
                    return _no_change(_limit_reason)
            else:
                noop_reads = 0
        except Exception:  # noqa: BLE001 — page may be torn down by recovery mid-wait
            if page.is_closed():
                raise
            page.wait_for_timeout(400)

    if not humanized:
        # Persist a full DOM snapshot so a real failure can be diagnosed without
        # spending another humanization.
        try:
            debug_path = Path("browser_profiles/debug/stealthwriter-output-timeout.html")
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(page.content(), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        raise StealthWriterAutomationError(
            "Timed out waiting for humanized output.",
            _collect_page_diagnostics(
                page,
                step="wait_for_output",
                extra={"last_output_preview": (last_value or "")[:500], "saw_busy": saw_busy},
            ),
        )

    elapsed = round(time.monotonic() - started, 3)
    return {
        "success": True,
        "humanized_text": humanized,
        "elapsed_seconds": elapsed,
        "current_url": page.url,
    }


def _read_sidebar_identity(page: Any) -> dict[str, str | None]:
    """Extract username and plan from the dashboard sidebar."""
    return page.evaluate(
        """() => {
            const plans = ['Scale', 'Pro', 'Plus', 'Starter', 'Free'];
            const roots = [
                document.querySelector('aside'),
                document.querySelector('[data-sidebar]'),
                document.querySelector('nav'),
                document.querySelector('[class*="sidebar"]'),
                document.body,
            ].filter(Boolean);

            let username = null;
            let plan = null;

            const emailRe = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}/i;
            for (const root of roots) {
                const text = (root.innerText || '').trim();
                if (!username) {
                    const m = text.match(emailRe);
                    if (m) username = m[0];
                }
                if (!plan) {
                    for (const p of plans) {
                        const re = new RegExp('\\\\b' + p + '\\\\b(?:\\\\s+plan)?', 'i');
                        if (re.test(text)) {
                            plan = p;
                            break;
                        }
                    }
                }
                if (username && plan) break;
            }

            const aside = document.querySelector('aside') || document.querySelector('[data-sidebar]');
            if (aside) {
                const nodes = Array.from(aside.querySelectorAll('p, span, div, a, button'))
                    .map(el => (el.innerText || '').trim())
                    .filter(t => t && t.length < 80);
                if (!username) {
                    for (const t of nodes) {
                        const m = t.match(emailRe);
                        if (m) { username = m[0]; break; }
                    }
                }
                if (!username) {
                    const skip = /humanizer|detector|dashboard|settings|billing|plans|logout|sign out|support/i;
                    for (let i = nodes.length - 1; i >= 0; i--) {
                        const t = nodes[i];
                        if (skip.test(t)) continue;
                        if (plans.some(p => new RegExp('^' + p + '$', 'i').test(t))) continue;
                        if (emailRe.test(t)) { username = t.match(emailRe)[0]; break; }
                        if (/^[A-Za-z][A-Za-z0-9 ._'-]{1,40}$/.test(t) && !/^[0-9]+$/.test(t)) {
                            username = t;
                            break;
                        }
                    }
                }
                if (!plan) {
                    for (const t of nodes) {
                        for (const p of plans) {
                            if (new RegExp('^' + p + '(?:\\\\s+plan)?$', 'i').test(t)) {
                                plan = p;
                                break;
                            }
                        }
                        if (plan) break;
                    }
                }
            }

            return { username, plan };
        }"""
    )


def get_session_status() -> dict[str, Any]:
    """Read login state, username, and plan from the dashboard sidebar."""
    page = _page()
    page.goto(_DASHBOARD_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=30_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(800)

    current_url = page.url
    if _is_sign_in_url(current_url):
        return {
            "logged_in": False,
            "current_url": current_url,
            "plan": None,
            "username": None,
        }

    identity = _read_sidebar_identity(page) or {}
    return {
        "logged_in": True,
        "current_url": current_url,
        "plan": identity.get("plan"),
        "username": identity.get("username"),
    }


# ------------------------------------------------------------------ provider class
class StealthWriterProvider(Provider):
    """StealthWriter provider — workflow only; BrowserService owns the browser."""

    name = PROVIDER_NAME
    provider_type = PROVIDER_NAME

    def initialize(self) -> None:
        # Ensure the provider tab exists; BrowserService handles Chrome/CDP.
        self.page()

    def login(self, *, credentials: dict[str, Any] | None = None) -> dict[str, Any]:
        # StealthWriter login is manual (Turnstile). Navigate the tab to sign-in.
        return start_interactive_login()

    def is_logged_in(self) -> bool:
        return bool(get_session_status().get("logged_in"))

    def humanize(self, text: str) -> dict[str, Any]:
        return humanize_text(text)

    def status(self) -> dict[str, Any]:
        return get_session_status()

    def health(self) -> dict[str, Any]:
        """Cheap, non-navigating snapshot for the aggregate health endpoint."""
        info: dict[str, Any] = {
            "provider": self.name,
            "has_page": False,
            "current_url": None,
            "logged_in": None,
        }
        svc = BrowserService.instance()
        try:
            if svc.is_running():
                page = svc.get_or_create_page(self.name)
                info["has_page"] = True
                url = page.url or ""
                info["current_url"] = url
                low = url.lower()
                if "/dashboard" in low:
                    info["logged_in"] = True
                elif _is_sign_in_url(low):
                    info["logged_in"] = False
        except Exception as exc:  # noqa: BLE001
            info["error"] = str(exc)
        return info

    def health_check(self) -> Any:
        """Deep health probe against the public homepage (kept for /health endpoint)."""
        from services.browser_automation.models import BrowserProviderType, ProviderHealth

        page = self.page()
        started = time.monotonic()
        response = page.goto(_HOME_URL, wait_until="networkidle")
        page_load_ms = int((time.monotonic() - started) * 1000)
        http_status = response.status if response is not None else None

        title = page.title()
        final_url = page.url

        turnstile = bool(
            page.locator("#cf-turnstile").count()
            or page.locator("[data-sitekey]").count()
            or page.locator('iframe[src*="challenges.cloudflare.com"]').count()
            or page.locator('iframe[src*="turnstile"]').count()
        )
        login_button = bool(
            page.locator('a[href="/sign-in"], a[href*="/sign-in"]').count()
            or page.get_by_role("link", name="Sign in").count()
            or page.get_by_role("button", name="Sign in").count()
            or page.get_by_text("Login with Google", exact=False).count()
        )
        dashboard = bool(
            page.locator('a[href="/dashboard"], a[href*="/dashboard"]').count()
            or page.get_by_text("Dashboard", exact=False).count()
        )
        humanizer = bool(
            page.locator('a[href*="humanizer"], a[href*="/humanize"]').count()
            or page.get_by_text("Humanizer", exact=False).count()
            or page.get_by_text("Humanize", exact=False).count()
        )
        logged_in = bool(page.locator('a[href="/dashboard/humanizer"]').count()) and not bool(
            page.locator('a[href="/sign-in"]').count()
        )

        cookies = page.context.cookies()
        local_storage_keys = page.evaluate("() => Object.keys(window.localStorage || {})")
        session_storage_keys = page.evaluate("() => Object.keys(window.sessionStorage || {})")

        screenshot_path = _SCREENSHOT_REL
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)

        details = {
            "title": title,
            "url": final_url,
            "http_status": http_status,
            "page_load_ms": page_load_ms,
            "turnstile": turnstile,
            "login_button": login_button,
            "dashboard": dashboard,
            "humanizer": humanizer,
            "logged_in": logged_in,
            "cookies": len(cookies),
            "localStorage_keys": local_storage_keys if isinstance(local_storage_keys, list) else [],
            "sessionStorage_keys": session_storage_keys if isinstance(session_storage_keys, list) else [],
            "screenshot": str(screenshot_path).replace("\\", "/"),
            "profile": _profile_path(),
        }
        healthy = http_status is not None and 200 <= int(http_status) < 400
        return ProviderHealth(
            provider_type=BrowserProviderType.STEALTHWRITER,
            healthy=healthy,
            message=(
                "StealthWriter public homepage loaded"
                if healthy
                else "StealthWriter homepage returned non-success status"
            ),
            checked_at=datetime.now(timezone.utc),
            details=details,
        )

    def check_authenticated(self) -> dict[str, Any]:
        page = self.page()
        page.goto(_DASHBOARD_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        current_url = page.url
        title = page.title()
        redirected = _is_sign_in_url(current_url)
        logged_in = (not redirected) and ("/dashboard" in current_url.lower())
        return {
            "logged_in": logged_in,
            "current_url": current_url,
            "title": title,
            "redirected": redirected,
        }

    def execute(self, task: Any) -> Any:
        from services.browser_automation.models import BrowserProviderType, TaskResult

        operation = getattr(task, "operation", None)
        if operation == "humanize":
            payload = getattr(task, "payload", {}) or {}
            result = self.humanize(str(payload.get("text") or ""))
            return TaskResult(
                task_id=getattr(task, "id", ""),
                provider_type=BrowserProviderType.STEALTHWRITER,
                success=bool(result.get("success")),
                data=result,
                error_message=None if result.get("success") else str(result.get("error")),
                completed_at=datetime.now(timezone.utc),
            )
        raise NotImplementedError(f"Unsupported StealthWriter operation: {operation!r}")

    def logout(self) -> None:
        raise NotImplementedError("StealthWriterProvider.logout is not implemented")

    def shutdown(self) -> None:
        # No-op: BrowserService owns the browser lifecycle.
        return None
