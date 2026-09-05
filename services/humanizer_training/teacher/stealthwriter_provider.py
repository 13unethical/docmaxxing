"""StealthWriterTeacherProvider — isolated training-only browser adapter.

ISOLATION CONTRACT
==================
* No calls to the production browser singleton or any of its reset helpers.
* No access to the production job queue or worker thread.
* No access to billing, credits, or usage-event code.
* No access to the production activity logger.
* No import from the Flask application entry-point.
* Owns its own ChromeLauncher, BrowserPool, and SessionStore instances, all
  pointing to training-specific directories and a separate CDP port.
* Can coexist with a running production browser on the same machine as long as
  TRAINING_CDP_PORT differs from the production port (default 9222).

USAGE
=====
Build the provider with TrainingBrowserConfig (env-driven or explicit), then
call rewrite().  The provider does NOT manage Chrome lifecycle automatically;
call start() / stop() explicitly from the CLI script.

No production file was modified to create this module.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Re-use the low-level browser infrastructure classes ONLY (not BrowserService).
# These classes are stateless / configurable via constructor args and have
# no singleton behaviour of their own.
# ---------------------------------------------------------------------------
from services.browser.chrome_launcher import ChromeLauncher
from services.browser.browser_pool import BrowserPool
from services.browser.session_store import SessionStore

# ---------------------------------------------------------------------------
# NO imports from:
#   services.browser.browser_service      (production singleton)
#   services.browser.jobs.*               (production worker/queue)
#   services.browser.providers.stealthwriter  (production provider)
#   services.dataset_logger               (production logger)
#   app                                   (Flask application)
# ---------------------------------------------------------------------------

_HUMANIZER_URL = "https://stealthwriter.ai/dashboard/humanizer"
_DASHBOARD_URL = "https://stealthwriter.ai/dashboard"
_SIGN_IN_URL = "https://stealthwriter.ai/sign-in"
_PROVIDER_NAME = "stealthwriter"

# --------------------------------------------------------------------------- config


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class TrainingBrowserConfig:
    """All training-specific paths/ports, fully separated from production."""

    # Chrome process
    cdp_port: int = field(
        default_factory=lambda: _env_int("TRAINING_CDP_PORT", 9333)
    )
    user_data_dir: str = field(
        default_factory=lambda: os.environ.get(
            "TRAINING_CHROME_USER_DATA_DIR",
            "browser_profiles/training_chrome",
        )
    )

    # Session storage
    session_dir: str = field(
        default_factory=lambda: os.environ.get(
            "TRAINING_SESSION_DIR",
            "browser_profiles/training_sessions",
        )
    )

    # StealthWriter knobs
    model: str = field(
        default_factory=lambda: (
            os.environ.get("TRAINING_STEALTHWRITER_MODEL") or "Legacy 5.1"
        ).strip() or "Legacy 5.1"
    )
    level: int = field(
        default_factory=lambda: max(
            1, min(10, _env_int("TRAINING_STEALTHWRITER_LEVEL", 8))
        )
    )
    timeout_s: float = field(
        default_factory=lambda: _env_float("TRAINING_STEALTHWRITER_TIMEOUT_S", 150.0)
    )
    max_retries: int = field(
        default_factory=lambda: _env_int("TRAINING_STEALTHWRITER_MAX_RETRIES", 3)
    )
    retry_delay_s: float = 2.0
    backoff_multiplier: float = 2.0
    max_delay_s: float = 30.0

    # Match production StealthWriter/HUMANIZE_BATCH cap (do not change production constants).
    max_text_words: int = 5000

    # Training-only debug / observability (never used by production).
    debug_screenshots: bool = field(
        default_factory=lambda: _env_bool("TRAINING_DEBUG_SCREENSHOTS", True)
    )
    debug_dir: str = field(
        default_factory=lambda: os.environ.get(
            "TRAINING_DEBUG_DIR",
            "data/humanizer_training/debug",
        )
    )

# --------------------------------------------------------------------------- result


@dataclass
class TeacherResult:
    success: bool
    humanized_text: str | None
    provider: str
    model: str
    level: int
    elapsed_seconds: float
    error: str | None = None
    error_detail: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


NON_RETRYABLE_ERRORS: frozenset[str] = frozenset(
    {
        "MODEL_SELECTION_FAILED",
        "LEVEL_SELECTION_FAILED",
        "LOGIN_REQUIRED",
    }
)


class SelectionFailed(Exception):
    """Fail-closed model/level selection error — never click Humanize after this."""

    def __init__(
        self,
        code: str,
        detail: str | None = None,
        *,
        failed_stage: str | None = None,
        debug: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.detail = detail
        self.failed_stage = failed_stage
        self.debug = dict(debug or {})
        super().__init__(f"{code}: {detail}" if detail else code)


class RunTrace:
    """Training-only stage telemetry. Click ≠ verified — mark verified only after DOM check."""

    __slots__ = ("last_successful_stage", "failed_stage", "stages")

    def __init__(self) -> None:
        self.last_successful_stage: str | None = None
        self.failed_stage: str | None = None
        self.stages: list[str] = []

    def mark(self, stage: str) -> None:
        self.stages.append(stage)
        self.last_successful_stage = stage

    def fail(self, stage: str) -> None:
        self.failed_stage = stage


# --------------------------------------------------------------------------- helpers (page-level, copied selectors only)


def _is_sign_in_url(url: str) -> bool:
    lower = (url or "").lower()
    return "/sign-in" in lower or "/signin" in lower


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


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
    ]
    for loc in candidates:
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=2000):
                return loc.first
        except Exception:  # noqa: BLE001
            continue
    return None


def _button_looks_disabled(button: Any) -> bool:
    try:
        if button.get_attribute("disabled") is not None:
            return True
        if (button.get_attribute("aria-disabled") or "").lower() == "true":
            return True
        return bool(
            button.evaluate(
                """el => {
                    if (el.disabled) return true;
                    const s = window.getComputedStyle(el);
                    return s.pointerEvents === 'none' || Number(s.opacity) < 0.6;
                }"""
            )
        )
    except Exception:  # noqa: BLE001
        return False


def _dismiss_ui_overlays(page: Any) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
    except Exception:  # noqa: BLE001
        pass
    try:
        page.locator("body").click(position={"x": 8, "y": 8}, timeout=1500)
        page.wait_for_timeout(100)
    except Exception:  # noqa: BLE001
        pass


def _read_locator_text(locator: Any) -> str:
    try:
        tag = locator.evaluate("el => (el.tagName || '').toLowerCase()")
        if tag in {"textarea", "input"}:
            return (locator.input_value() or "").strip()
        return (locator.inner_text() or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _set_textarea_value(locator: Any, page: Any, text: str) -> bool:
    try:
        locator.evaluate(
            """(el, value) => {
                const proto = el.tagName === 'TEXTAREA'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                if (setter) setter.call(el, value);
                else el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            text,
        )
        page.wait_for_timeout(200)
        return _read_locator_text(locator).strip() == text.strip()
    except Exception:  # noqa: BLE001
        return False


def _paste_into_input(page: Any, input_box: Any, cleaned: str) -> None:
    try:
        input_box.scroll_into_view_if_needed(timeout=5000)
    except Exception:  # noqa: BLE001
        pass

    focused = False
    for kwargs in ({"timeout": 8000}, {"timeout": 5000, "force": True}):
        try:
            input_box.click(**kwargs)
            focused = True
            break
        except Exception:  # noqa: BLE001
            _dismiss_ui_overlays(page)
            page.wait_for_timeout(200)

    if not focused:
        try:
            input_box.focus(timeout=3000)
            focused = True
        except Exception:  # noqa: BLE001
            pass

    try:
        if focused:
            input_box.fill("")
            input_box.fill(cleaned)
        else:
            raise RuntimeError("textarea not focused")
        page.wait_for_timeout(300)
        if _read_locator_text(input_box).strip() == cleaned:
            return
    except Exception:  # noqa: BLE001
        pass

    try:
        if focused:
            input_box.click(force=True, timeout=3000)
        modifier = "Meta" if page.evaluate("() => navigator.platform.includes('Mac')") else "Control"
        page.keyboard.press(f"{modifier}+A")
        page.keyboard.insert_text(cleaned)
        page.wait_for_timeout(300)
        if _read_locator_text(input_box).strip() == cleaned:
            return
    except Exception:  # noqa: BLE001
        pass

    if _set_textarea_value(input_box, page, cleaned):
        return

    raise RuntimeError("Failed to paste text into textarea after all fallbacks.")


def _click_humanize_button(page: Any, button: Any) -> None:
    _dismiss_ui_overlays(page)
    try:
        button.scroll_into_view_if_needed(timeout=5000)
    except Exception:  # noqa: BLE001
        pass

    for _ in range(12):
        if not _button_looks_disabled(button):
            break
        page.wait_for_timeout(250)
    else:
        page.wait_for_timeout(400)

    for kwargs in ({"timeout": 8000}, {"timeout": 5000, "force": True}):
        try:
            button.click(**kwargs)
            page.wait_for_timeout(200)
            return
        except Exception:  # noqa: BLE001
            _dismiss_ui_overlays(page)
            refreshed = _find_humanize_button(page)
            if refreshed is not None:
                button = refreshed
            page.wait_for_timeout(250)

    try:
        button.evaluate("el => el.click()")
        page.wait_for_timeout(200)
        return
    except Exception:  # noqa: BLE001
        pass

    try:
        page.evaluate(
            r"""() => {
                const nodes = Array.from(document.querySelectorAll('button, [role="button"]'));
                const btn = nodes.find(el => /^\s*humanize\s*$/i.test((el.innerText || '').trim()));
                if (!btn) throw new Error('Humanize button not found in DOM');
                btn.click();
            }"""
        )
        page.wait_for_timeout(200)
        return
    except Exception:  # noqa: BLE001
        pass

    raise RuntimeError("Failed to click Humanize button after all fallbacks.")


_RESULT_EXTRACTION_JS = r"""(cleaned) => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const cleanedN = norm(cleaned);
    const selectors = ['div.whitespace-pre-wrap', '[class*="whitespace-pre-wrap"]'];
    let best = '';
    for (const sel of selectors) {
        for (const el of Array.from(document.querySelectorAll(sel))) {
            const tx = norm(el.innerText);
            if (tx.length > 20 && tx !== cleanedN && tx.length > best.length) best = tx;
        }
        if (best) break;
    }
    if (best) return best;
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
            if (tx.length > 25 && tx !== cleanedN && !skip.test(tx) && tx.length > best.length)
                best = tx;
        });
    }
    return best;
}"""


def _extract_result_text(page: Any, cleaned: str) -> str:
    try:
        value = page.evaluate(_RESULT_EXTRACTION_JS, cleaned)
        return (value or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _result_ready(page: Any) -> bool:
    try:
        return (
            page.get_by_role("button", name=re.compile(r"rehumanize|humanize more", re.I)).count() > 0
        )
    except Exception:  # noqa: BLE001
        return False


def _generation_busy(page: Any) -> bool:
    try:
        if page.get_by_role("button", name=re.compile(r"humanizing", re.I)).count() > 0:
            return True
        return page.locator('[aria-busy="true"], .animate-spin, [class*="spinner"]').count() > 0
    except Exception:  # noqa: BLE001
        return False


def _detect_limit_message(page: Any) -> str:
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
                        /limit|reached|upgrade|too many|no more|out of|daily|quota|suspend/i.test(t))
                        return t;
                }
                return '';
            }"""
        )
        return (txt or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _norm_label(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


# Internal canonical name → exact UI option label(s) in current StealthWriter UI.
# Screenshot (2026-09): Legacy group contains "Ghost 5.1 Legacy" / "Ghost 4.6 Legacy".
_CANONICAL_TO_UI_OPTIONS: dict[str, tuple[str, ...]] = {
    "Legacy 5.1": ("Ghost 5.1 Legacy",),
}

# UI labels (normalized lower) that map to a canonical training model.
_UI_LABEL_TO_CANONICAL: dict[str, str] = {
    "legacy 5.1": "Legacy 5.1",
    "ghost 5.1 legacy": "Legacy 5.1",
}

# Explicit non-matches for Legacy 5.1 (must never canonicalize to Legacy 5.1).
_REJECTED_AS_LEGACY_51: frozenset[str] = frozenset(
    {
        "ghost 5.2 mini",
        "ghost 5.2 pro",
        "ghost 4.6 legacy",
        "ghost 5.1",  # without trailing "Legacy"
    }
)


def _canonical_model_name(label: str) -> str | None:
    """Map internal or UI label to canonical training model name.

    Returns:
      - "Legacy 5.1" for internal name or UI "Ghost 5.1 Legacy"
      - the normalized label itself for known non-matching UI models
        (so they never equal Legacy 5.1)
      - None when the label is empty / unrecognized
    """
    n = _norm_label(label)
    if not n:
        return None
    low = n.lower()
    if low in _UI_LABEL_TO_CANONICAL:
        return _UI_LABEL_TO_CANONICAL[low]
    if n in _CANONICAL_TO_UI_OPTIONS:
        return n
    if low in _REJECTED_AS_LEGACY_51:
        return n
    return None


def _ui_option_labels_for_canonical(canonical: str) -> tuple[str, ...]:
    key = _canonical_model_name(canonical) or _norm_label(canonical)
    return _CANONICAL_TO_UI_OPTIONS.get(key, ())


_VISIBLE_MODEL_LABEL_JS = r"""() => {
    // Live StealthWriter closed model row (verified):
    //   Mini/Pro = button[role=tab][aria-selected=true|false]
    //   Ghost 5.1 Legacy = button[aria-haspopup=menu] with exact classList tokens
    //     bg-background + shadow-sm when selected (NOT data-active:bg-background).
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();

    // RULE 1: selected tab wins.
    const selectedTab = document.querySelector('button[role="tab"][aria-selected="true"]');
    if (selectedTab) {
        const t = norm(selectedTab.innerText || selectedTab.textContent || '');
        if (t) return t;
    }

    // RULE 2: Legacy menu trigger selected via exact classList token membership.
    const tabs = Array.from(document.querySelectorAll('button[role="tab"]'));
    const mini = tabs.find(el => /^Ghost 5\.2 Mini$/i.test(norm(el.innerText || el.textContent || '')));
    const pro = tabs.find(el => /^Ghost 5\.2 Pro$/i.test(norm(el.innerText || el.textContent || '')));
    const legacy = Array.from(document.querySelectorAll('button[aria-haspopup="menu"]')).find(
        el => /^Ghost 5\.1 Legacy$/i.test(norm(el.innerText || el.textContent || ''))
    );
    if (mini && pro && legacy) {
        const miniSel = (mini.getAttribute('aria-selected') || '').toLowerCase();
        const proSel = (pro.getAttribute('aria-selected') || '').toLowerCase();
        // Exact tokens only — classList.contains, never substring of className.
        if (
            miniSel === 'false'
            && proSel === 'false'
            && legacy.classList.contains('bg-background')
            && legacy.classList.contains('shadow-sm')
        ) {
            return 'Ghost 5.1 Legacy';
        }
    }

    // Conservative: no proven selected state (do NOT fall back to DOM order / first match).
    return '';
}"""


def _class_list_tokens(raw: dict[str, Any]) -> set[str]:
    """Exact classList-equivalent tokens (whitespace-split). Never substring-match."""
    if isinstance(raw.get("class_list"), (list, tuple, set)):
        return {str(t) for t in raw["class_list"] if str(t)}
    return {t for t in str(raw.get("class_name") or "").split() if t}


def _pick_model_label_from_candidates(candidates: list[dict[str, Any]]) -> str:
    """Pure selected-state picker used by unit tests (mirrors ``_VISIBLE_MODEL_LABEL_JS``).

    Each candidate dict may include:
      - text: str
      - role: \"tab\" | other
      - aria_selected: bool | None  (for tabs)
      - aria_haspopup: str | None   (\"menu\" for Legacy trigger)
      - class_list: list[str]       (preferred; exact tokens)
      - class_name: str             (whitespace-split into tokens)
    """
    # RULE 1: button[role=tab][aria-selected=true]
    for raw in candidates:
        text = _norm_label(str(raw.get("text") or ""))
        if not text:
            continue
        if str(raw.get("role") or "").lower() == "tab" and raw.get("aria_selected") is True:
            return text

    def _find(pred) -> dict[str, Any] | None:
        for raw in candidates:
            if pred(raw):
                return raw
        return None

    mini = _find(
        lambda r: str(r.get("role") or "").lower() == "tab"
        and _norm_label(str(r.get("text") or "")).lower() == "ghost 5.2 mini"
    )
    pro = _find(
        lambda r: str(r.get("role") or "").lower() == "tab"
        and _norm_label(str(r.get("text") or "")).lower() == "ghost 5.2 pro"
    )
    legacy = _find(
        lambda r: str(r.get("aria_haspopup") or "").lower() == "menu"
        and _norm_label(str(r.get("text") or "")).lower() == "ghost 5.1 legacy"
    )
    if mini is not None and pro is not None and legacy is not None:
        mini_sel = mini.get("aria_selected")
        pro_sel = pro.get("aria_selected")
        tokens = _class_list_tokens(legacy)
        # Exact token membership only — "data-active:bg-background" must NOT count.
        if (
            mini_sel is False
            and pro_sel is False
            and "bg-background" in tokens
            and "shadow-sm" in tokens
        ):
            return "Ghost 5.1 Legacy"

    # Conservative: no proven selected state (never first-DOM-match).
    return ""


def _visible_model_label(page: Any) -> str:
    """Read the currently selected model from the closed StealthWriter model row.

    Uses only live-DOM selected-state rules (aria-selected tab, or Legacy exact
    classList tokens). Never infers selection from DOM order.
    """
    try:
        return (page.evaluate(_VISIBLE_MODEL_LABEL_JS) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _model_matches_desired(visible: str, desired: str) -> bool:
    """Pass iff canonical(actual) == canonical(desired). Ghost 5.2 / 4.6 never match Legacy 5.1."""
    actual_canon = _canonical_model_name(visible)
    desired_canon = _canonical_model_name(desired)
    if not actual_canon or not desired_canon:
        return False
    return actual_canon == desired_canon


def _click_first_visible(page: Any, patterns: list[re.Pattern[str]]) -> bool:
    for pattern in patterns:
        candidates = [
            page.get_by_role("option", name=pattern),
            page.get_by_role("menuitem", name=pattern),
            page.get_by_role("button", name=pattern),
            page.locator('[role="option"], [role="menuitem"], button, [role="button"]').filter(
                has_text=pattern
            ),
            page.get_by_text(pattern),
        ]
        for loc in candidates:
            try:
                if loc.count() <= 0:
                    continue
                target = loc.first
                if target.is_visible(timeout=1500):
                    target.click(timeout=3000)
                    return True
            except Exception:  # noqa: BLE001
                continue
    return False


def _click_exact_option_label(page: Any, label: str) -> bool:
    """Click an option whose normalized text equals ``label`` (anchored exact match)."""
    wanted = _norm_label(label)
    if not wanted:
        return False
    pattern = re.compile(rf"^\s*{re.escape(wanted)}\s*$", re.I)
    return _click_first_visible(page, [pattern])


def _open_model_selector(page: Any) -> bool:
    """Open the StealthWriter model dropdown if it is not already open."""
    try:
        if page.get_by_role("option").count() > 0:
            return True
    except Exception:  # noqa: BLE001
        pass

    openers = [
        page.get_by_role("combobox"),
        page.locator('[aria-haspopup="listbox"]'),
        page.locator('button, [role="button"]').filter(
            has_text=re.compile(
                r"legacy|ghost\s*[0-9]|ninja|model|5\.2|5\.1|4\.6|mini|pro",
                re.I,
            )
        ),
        page.locator("select"),
    ]
    for loc in openers:
        try:
            if loc.count() <= 0:
                continue
            btn = loc.first
            if not btn.is_visible(timeout=1500):
                continue
            label = (_read_locator_text(btn) or "").lower()
            if label and re.search(r"humanize|rehumanize|sign|login|upgrade|support|copy", label):
                continue
            btn.click(timeout=3000)
            page.wait_for_timeout(350)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _expand_legacy_group(page: Any) -> bool:
    """Expand nested Legacy group (UI may show 'Legacy' or 'Legacy ▼')."""
    return _click_first_visible(
        page,
        [
            re.compile(r"^\s*legacy(\s*[▼▾])?\s*$", re.I),
            re.compile(r"^\s*legacy\s*models?\s*$", re.I),
        ],
    )


def _select_legacy_51_option(page: Any) -> bool:
    """Click the exact UI option for Legacy 5.1: 'Ghost 5.1 Legacy'."""
    for ui_label in _ui_option_labels_for_canonical("Legacy 5.1"):
        if _click_exact_option_label(page, ui_label):
            return True
    return False


def _page_url(page: Any) -> str | None:
    try:
        return str(page.url) if page is not None else None
    except Exception:  # noqa: BLE001
        return None


def _capture_selection_debug(
    page: Any,
    *,
    model: str,
    level: int,
    trace: RunTrace,
    failed_stage: str | None,
) -> dict[str, Any]:
    """Safe debug snapshot — no source text, cookies, or credentials."""
    visible_model = ""
    visible_level: int | None = None
    try:
        visible_model = _visible_model_label(page) or ""
    except Exception:  # noqa: BLE001
        pass
    try:
        visible_level = _visible_selected_level(page)
    except Exception:  # noqa: BLE001
        pass
    return {
        "requested_model": _norm_label(model) or "Legacy 5.1",
        "requested_level": int(level),
        "visible_model_label": visible_model or None,
        "visible_level": visible_level,
        "selection_stage": failed_stage,
        "last_successful_stage": trace.last_successful_stage,
        "failed_stage": failed_stage,
        "current_url": _page_url(page),
        "stages": list(trace.stages),
    }


def _maybe_save_debug_screenshot(
    page: Any,
    *,
    enabled: bool,
    debug_dir: str,
    error_code: str,
    document_id: str | None,
) -> str | None:
    """Save a PNG on failure only. Never called from production paths."""
    if not enabled or page is None:
        return None
    try:
        out_dir = Path(debug_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_doc = re.sub(r"[^A-Za-z0-9_.-]+", "_", document_id or "unknown")[:80]
        safe_err = re.sub(r"[^A-Za-z0-9_.-]+", "_", error_code or "ERROR")[:60]
        path = out_dir / f"{ts}_{safe_doc}_{safe_err}.png"
        page.screenshot(path=str(path), full_page=False)
        return str(path)
    except Exception:  # noqa: BLE001
        return None


def _ensure_model_selected(page: Any, model: str, trace: RunTrace | None = None) -> str:
    """Pin model to the desired canonical model and verify via DOM.

    Returns the verified *UI* label (e.g. 'Ghost 5.1 Legacy').
    Fail-closed: raises SelectionFailed(MODEL_SELECTION_FAILED) on any miss.
    Does not click Humanize — callers must gate that separately.
    Click alone never marks MODEL_VERIFIED — only DOM verification does.
    """
    tr = trace or RunTrace()
    wanted_raw = _norm_label(model) or "Legacy 5.1"
    wanted_canon = _canonical_model_name(wanted_raw) or wanted_raw
    current = _visible_model_label(page)
    if _model_matches_desired(current, wanted_canon):
        tr.mark("MODEL_ALREADY_MATCHED")
        tr.mark("MODEL_VERIFIED")
        return _norm_label(current) or wanted_raw

    # Native <select> path (verify after select)
    try:
        selects = page.locator("select")
        for i in range(selects.count()):
            sel = selects.nth(i)
            options = sel.locator("option")
            for j in range(options.count()):
                opt = options.nth(j)
                text = _norm_label(opt.inner_text() or "")
                value = (opt.get_attribute("value") or "").strip()
                blob = f"{text} {value}"
                if _model_matches_desired(blob, wanted_canon) or _model_matches_desired(text, wanted_canon):
                    tr.mark("MODEL_OPTION_FOUND")
                    sel.select_option(value=value or None, label=text or None)
                    tr.mark("MODEL_OPTION_CLICKED")
                    page.wait_for_timeout(200)
                    verified = _visible_model_label(page)
                    if _model_matches_desired(verified, wanted_canon):
                        tr.mark("MODEL_VERIFIED")
                        return _norm_label(verified) or text
                    tr.fail("MODEL_VERIFICATION")
                    raise SelectionFailed(
                        "MODEL_SELECTION_FAILED",
                        f"native select did not stick; wanted={wanted_canon!r} got={verified!r}",
                        failed_stage="MODEL_VERIFICATION",
                    )
    except SelectionFailed:
        raise
    except Exception:  # noqa: BLE001
        pass

    if not _open_model_selector(page):
        tr.fail("MODEL_MENU_OPENED")
        raise SelectionFailed(
            "MODEL_SELECTION_FAILED",
            "could not open model dropdown",
            failed_stage="MODEL_MENU_OPENED",
        )
    tr.mark("MODEL_MENU_OPENED")

    # Nested Legacy group is required when selecting Legacy 5.1.
    if wanted_canon == "Legacy 5.1" or "legacy" in wanted_canon.lower():
        if not _expand_legacy_group(page):
            tr.fail("LEGACY_GROUP_OPENED")
            raise SelectionFailed(
                "MODEL_SELECTION_FAILED",
                "Legacy group not found in model menu",
                failed_stage="LEGACY_GROUP_OPENED",
            )
        tr.mark("LEGACY_GROUP_OPENED")
        page.wait_for_timeout(200)

    if wanted_canon == "Legacy 5.1":
        if not _select_legacy_51_option(page):
            tr.fail("MODEL_OPTION_FOUND")
            raise SelectionFailed(
                "MODEL_SELECTION_FAILED",
                "UI option 'Ghost 5.1 Legacy' not found",
                failed_stage="MODEL_OPTION_FOUND",
            )
        tr.mark("MODEL_OPTION_FOUND")
        tr.mark("MODEL_OPTION_CLICKED")
    else:
        if not _click_exact_option_label(page, wanted_raw):
            tr.fail("MODEL_OPTION_FOUND")
            raise SelectionFailed(
                "MODEL_SELECTION_FAILED",
                f"UI option for {wanted_raw!r} not found",
                failed_stage="MODEL_OPTION_FOUND",
            )
        tr.mark("MODEL_OPTION_FOUND")
        tr.mark("MODEL_OPTION_CLICKED")

    page.wait_for_timeout(300)
    _dismiss_ui_overlays(page)

    verified = _visible_model_label(page)
    if not _model_matches_desired(verified, wanted_canon):
        tr.fail("MODEL_VERIFICATION")
        raise SelectionFailed(
            "MODEL_SELECTION_FAILED",
            f"wanted={wanted_canon!r} got={(verified or '(empty)')!r}",
            failed_stage="MODEL_VERIFICATION",
        )
    tr.mark("MODEL_VERIFIED")
    return _norm_label(verified) or wanted_raw


def _visible_selected_level(page: Any) -> int | None:
    """Read the selected Level chip (1–10). None = unverifiable → fail closed."""
    try:
        raw = page.evaluate(
            """() => {
                const label = Array.from(document.querySelectorAll('span,label,div,p'))
                  .find(el => {
                    const t = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                    return t === 'Level';
                  });
                if (!label) return null;
                let root = label.parentElement;
                for (let i = 0; i < 4 && root; i++) {
                  const buttons = Array.from(root.querySelectorAll('button'));
                  const selected = buttons.find(b => {
                    const t = (b.textContent || '').replace(/\\s+/g, ' ').trim();
                    if (!/^([1-9]|10)$/.test(t)) return false;
                    const cls = b.className || '';
                    const pressed = (b.getAttribute('aria-pressed') || '').toLowerCase() === 'true';
                    const ariaSelected = (b.getAttribute('aria-selected') || '').toLowerCase() === 'true';
                    return pressed || ariaSelected
                      || /\\bbg-background\\b/.test(cls)
                      || /\\bshadow-sm\\b/.test(cls)
                      || /\\bbing-/.test(cls)
                      || /selected|active/i.test(cls);
                  });
                  if (selected) {
                    const t = (selected.textContent || '').replace(/\\s+/g, ' ').trim();
                    const n = parseInt(t, 10);
                    return Number.isFinite(n) ? n : null;
                  }
                  root = root.parentElement;
                }
                return null;
            }"""
        )
        if raw is None:
            return None
        value = int(raw)
        if 1 <= value <= 10:
            return value
        return None
    except Exception:  # noqa: BLE001
        return None


def _click_level_chip(page: Any, level: int) -> bool:
    try:
        return bool(
            page.evaluate(
                """(wanted) => {
                    const label = Array.from(document.querySelectorAll('span,label,div,p'))
                      .find(el => {
                        const t = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                        return t === 'Level';
                      });
                    if (!label) return false;
                    let root = label.parentElement;
                    for (let i = 0; i < 4 && root; i++) {
                      const buttons = Array.from(root.querySelectorAll('button'));
                      const match = buttons.find(b => {
                        const t = (b.textContent || '').replace(/\\s+/g, ' ').trim();
                        return t === String(wanted);
                      });
                      if (match) { match.click(); return true; }
                      root = root.parentElement;
                    }
                    return false;
                }""",
                int(level),
            )
        )
    except Exception:  # noqa: BLE001
        return False


def _ensure_rewrite_level(page: Any, level: int, trace: RunTrace | None = None) -> int:
    """Pin Level chip and verify via DOM. Fail-closed on mismatch/unverifiable.

    Click alone never marks LEVEL_VERIFIED — only DOM verification does.
    """
    tr = trace or RunTrace()
    wanted = max(1, min(10, int(level)))
    current = _visible_selected_level(page)
    if current == wanted:
        tr.mark("LEVEL_OPTION_FOUND")
        tr.mark("LEVEL_VERIFIED")
        return wanted

    tr.mark("LEVEL_OPTION_FOUND")
    if not _click_level_chip(page, wanted):
        tr.fail("LEVEL_OPTION_CLICKED")
        raise SelectionFailed(
            "LEVEL_SELECTION_FAILED",
            f"could not click Level {wanted} chip",
            failed_stage="LEVEL_OPTION_CLICKED",
        )
    tr.mark("LEVEL_OPTION_CLICKED")
    page.wait_for_timeout(200)

    verified = _visible_selected_level(page)
    if verified is None:
        tr.fail("LEVEL_VERIFICATION")
        raise SelectionFailed(
            "LEVEL_SELECTION_FAILED",
            f"Level {wanted} selected but DOM verification unavailable",
            failed_stage="LEVEL_VERIFICATION",
        )
    if verified != wanted:
        tr.fail("LEVEL_VERIFICATION")
        raise SelectionFailed(
            "LEVEL_SELECTION_FAILED",
            f"wanted={wanted} got={verified}",
            failed_stage="LEVEL_VERIFICATION",
        )
    tr.mark("LEVEL_VERIFIED")
    return verified


def _verify_selection_gate(
    page: Any, model: str, level: int, trace: RunTrace | None = None
) -> tuple[str, int]:
    """Final pre-Humanize gate. Must pass before any Humanize click.

    Returns (ui_model_label, verified_level).
    """
    tr = trace or RunTrace()
    wanted_model = _norm_label(model) or "Legacy 5.1"
    wanted_level = max(1, min(10, int(level)))

    actual_model = _visible_model_label(page)
    if not _model_matches_desired(actual_model, wanted_model):
        tr.fail("MODEL_VERIFICATION")
        raise SelectionFailed(
            "MODEL_SELECTION_FAILED",
            f"pre-humanize gate: wanted={wanted_model!r} got={(actual_model or '(empty)')!r}",
            failed_stage="MODEL_VERIFICATION",
        )

    actual_level = _visible_selected_level(page)
    if actual_level is None:
        tr.fail("LEVEL_VERIFICATION")
        raise SelectionFailed(
            "LEVEL_SELECTION_FAILED",
            "pre-humanize gate: selected level unverifiable",
            failed_stage="LEVEL_VERIFICATION",
        )
    if actual_level != wanted_level:
        tr.fail("LEVEL_VERIFICATION")
        raise SelectionFailed(
            "LEVEL_SELECTION_FAILED",
            f"pre-humanize gate: wanted={wanted_level} got={actual_level}",
            failed_stage="LEVEL_VERIFICATION",
        )
    # Re-affirm verified stages after gate (DOM-backed).
    if tr.last_successful_stage != "LEVEL_VERIFIED":
        tr.mark("MODEL_VERIFIED")
        tr.mark("LEVEL_VERIFIED")
    return _norm_label(actual_model) or wanted_model, actual_level


def _selection_meta(
    *,
    requested_model: str,
    ui_model_label: str,
    requested_level: int,
    verified_level: int,
    last_successful_stage: str | None = None,
) -> dict[str, Any]:
    """Build success metadata with both canonical and raw UI labels."""
    requested = _canonical_model_name(requested_model) or _norm_label(requested_model) or "Legacy 5.1"
    ui_label = _norm_label(ui_model_label)
    verified = _canonical_model_name(ui_label) or requested
    meta = {
        "requested_model": requested,
        "verified_model": verified,
        "ui_model_label": ui_label,
        "requested_level": int(requested_level),
        "verified_level": int(verified_level),
        "selection_verified": True,
    }
    if last_successful_stage:
        meta["last_successful_stage"] = last_successful_stage
    return meta



# --------------------------------------------------------------------------- core humanize


def _selection_failure_payload(
    page: Any,
    *,
    model: str,
    level: int,
    trace: RunTrace,
    exc: SelectionFailed,
    debug_screenshots: bool,
    debug_dir: str,
    document_id: str | None,
) -> dict[str, Any]:
    failed_stage = exc.failed_stage or trace.failed_stage or "MODEL_VERIFICATION"
    if not trace.failed_stage:
        trace.fail(failed_stage)
    debug = _capture_selection_debug(
        page,
        model=model,
        level=level,
        trace=trace,
        failed_stage=failed_stage,
    )
    debug.update(exc.debug)
    shot = _maybe_save_debug_screenshot(
        page,
        enabled=debug_screenshots,
        debug_dir=debug_dir,
        error_code=exc.code,
        document_id=document_id,
    )
    if shot:
        debug["screenshot_path"] = shot
    return {
        "success": False,
        "error": exc.code,
        "error_detail": exc.detail,
        "retryable": False,
        "failed_stage": failed_stage,
        "last_successful_stage": trace.last_successful_stage,
        "debug": debug,
        "requested_model": debug.get("requested_model"),
        "requested_level": debug.get("requested_level"),
        "visible_model_label": debug.get("visible_model_label"),
        "visible_level": debug.get("visible_level"),
        "current_url": debug.get("current_url"),
        "screenshot_path": shot,
        "selection_verified": False,
    }


def _humanize_once(
    page: Any,
    cleaned: str,
    model: str,
    level: int,
    timeout_s: float,
    *,
    trace: RunTrace | None = None,
    debug_screenshots: bool = False,
    debug_dir: str = "data/humanizer_training/debug",
    document_id: str | None = None,
) -> dict[str, Any]:
    """Single attempt: navigate → select/verify → paste → gate → click → wait → extract."""
    tr = trace or RunTrace()
    page.goto(_HUMANIZER_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=30_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(800)
    tr.mark("PAGE_READY")

    if _is_sign_in_url(page.url):
        tr.fail("PAGE_READY")
        return {
            "success": False,
            "error": "LOGIN_REQUIRED",
            "retryable": False,
            "failed_stage": "PAGE_READY",
            "last_successful_stage": tr.last_successful_stage,
            "current_url": _page_url(page),
        }

    try:
        verified_model = _ensure_model_selected(page, model, tr)
        verified_level = _ensure_rewrite_level(page, level, tr)
    except SelectionFailed as exc:
        return _selection_failure_payload(
            page,
            model=model,
            level=level,
            trace=tr,
            exc=exc,
            debug_screenshots=debug_screenshots,
            debug_dir=debug_dir,
            document_id=document_id,
        )

    _dismiss_ui_overlays(page)

    input_box = _find_input_textarea(page)
    if input_box is None:
        tr.fail("EDITOR_FOUND")
        return {
            "success": False,
            "error": "TEXTAREA_NOT_FOUND",
            "retryable": True,
            "failed_stage": "EDITOR_FOUND",
            "last_successful_stage": tr.last_successful_stage,
        }
    tr.mark("EDITOR_FOUND")

    try:
        _paste_into_input(page, input_box, cleaned)
    except Exception as exc:  # noqa: BLE001
        tr.fail("TEXT_INSERTED")
        return {
            "success": False,
            "error": "PASTE_FAILED",
            "error_detail": str(exc),
            "retryable": True,
            "failed_stage": "TEXT_INSERTED",
            "last_successful_stage": tr.last_successful_stage,
        }
    tr.mark("TEXT_INSERTED")

    try:
        verified_model = _ensure_model_selected(page, model, tr)
        verified_level = _ensure_rewrite_level(page, level, tr)
        verified_model, verified_level = _verify_selection_gate(page, model, level, tr)
    except SelectionFailed as exc:
        return _selection_failure_payload(
            page,
            model=model,
            level=level,
            trace=tr,
            exc=exc,
            debug_screenshots=debug_screenshots,
            debug_dir=debug_dir,
            document_id=document_id,
        )

    _dismiss_ui_overlays(page)

    button = _find_humanize_button(page)
    if button is None:
        tr.fail("HUMANIZE_BUTTON_FOUND")
        return {
            "success": False,
            "error": "BUTTON_NOT_FOUND",
            "retryable": True,
            "failed_stage": "HUMANIZE_BUTTON_FOUND",
            "last_successful_stage": tr.last_successful_stage,
        }
    tr.mark("HUMANIZE_BUTTON_FOUND")

    try:
        _click_humanize_button(page, button)
    except Exception as exc:  # noqa: BLE001
        tr.fail("HUMANIZE_CLICKED")
        return {
            "success": False,
            "error": "CLICK_FAILED",
            "error_detail": str(exc),
            "retryable": True,
            "failed_stage": "HUMANIZE_CLICKED",
            "last_successful_stage": tr.last_successful_stage,
        }
    tr.mark("HUMANIZE_CLICKED")

    previous_result = _extract_result_text(page, cleaned)
    deadline = time.monotonic() + timeout_s
    humanized = ""
    last_value = ""
    stable_reads = 0
    saw_busy = False
    busy_cleared_at: float | None = None
    reclick_count = 0
    last_reclick_at = time.monotonic()

    while time.monotonic() < deadline:
        try:
            page.wait_for_timeout(800)

            if _generation_busy(page):
                saw_busy = True
                busy_cleared_at = None
                continue
            if saw_busy and busy_cleared_at is None:
                busy_cleared_at = time.monotonic()

            toast = _detect_limit_message(page)
            if toast:
                return {
                    "success": False,
                    "error": "NO_CHANGE",
                    "error_detail": toast,
                    "retryable": True,
                    "failed_stage": "RESULT_FOUND",
                    "last_successful_stage": tr.last_successful_stage,
                }

            current = _extract_result_text(page, cleaned)
            if current and len(current) > 20 and current != cleaned and current != previous_result:
                if current == last_value:
                    stable_reads += 1
                else:
                    stable_reads = 0
                    last_value = current
                if stable_reads >= 2 or (_result_ready(page) and stable_reads >= 1):
                    humanized = current
                    tr.mark("RESULT_FOUND")
                    tr.mark("RESULT_EXTRACTED")
                    break
                continue

            now = time.monotonic()
            if not saw_busy and reclick_count < 3 and now - last_reclick_at >= 8:
                reclick_count += 1
                last_reclick_at = now
                btn = _find_humanize_button(page)
                if btn is not None:
                    try:
                        _click_humanize_button(page, btn)
                    except Exception:  # noqa: BLE001
                        pass
                continue

            if (
                saw_busy
                and busy_cleared_at is not None
                and now - busy_cleared_at > 4
                and reclick_count < 4
                and _result_ready(page)
                and not current
            ):
                reclick_count += 1
                last_reclick_at = now
                try:
                    page.get_by_role("button", name=re.compile(r"rehumanize|humanize more", re.I)).first.click(
                        timeout=5000, force=True
                    )
                    saw_busy = False
                    busy_cleared_at = None
                except Exception:  # noqa: BLE001
                    pass
                continue

        except Exception:  # noqa: BLE001
            if page.is_closed():
                return {
                    "success": False,
                    "error": "PAGE_CLOSED",
                    "retryable": True,
                    "failed_stage": "RESULT_FOUND",
                    "last_successful_stage": tr.last_successful_stage,
                }
            page.wait_for_timeout(400)

    if not humanized:
        tr.fail("RESULT_FOUND")
        return {
            "success": False,
            "error": "TIMEOUT",
            "error_detail": f"saw_busy={saw_busy} reclicks={reclick_count}",
            "retryable": True,
            "failed_stage": "RESULT_FOUND",
            "last_successful_stage": tr.last_successful_stage,
        }

    return {
        "success": True,
        "humanized_text": humanized,
        **_selection_meta(
            requested_model=_norm_label(model) or "Legacy 5.1",
            ui_model_label=verified_model,
            requested_level=int(level),
            verified_level=int(verified_level),
            last_successful_stage=tr.last_successful_stage,
        ),
    }


# --------------------------------------------------------------------------- provider class


class StealthWriterTeacherProvider:
    """Isolated training-only StealthWriter provider.

    Owns its own ChromeLauncher / BrowserPool / SessionStore — never touches
    the production BrowserService singleton, JobManager, or any Docmaxxing
    credit/billing code.
    """

    def __init__(self, config: TrainingBrowserConfig | None = None) -> None:
        self._cfg = config or TrainingBrowserConfig()
        self._launcher = ChromeLauncher(
            port=self._cfg.cdp_port,
            user_data_dir=self._cfg.user_data_dir,
        )
        self._pool: BrowserPool | None = None
        self._sessions = SessionStore(base_dir=self._cfg.session_dir)
        self._started = False

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        """Launch (or attach to) the training Chrome and connect Playwright."""
        self._launcher.ensure_running()
        self._pool = BrowserPool(self._launcher.cdp_url, timeout_ms=int(self._cfg.timeout_s * 1000))
        self._pool.connect_all()
        self._restore_session()
        self._started = True

    def stop(self) -> None:
        """Disconnect Playwright and terminate the training Chrome process."""
        if self._pool is not None:
            try:
                self._pool.disconnect_all()
            except Exception:  # noqa: BLE001
                pass
        try:
            self._launcher.stop()
        except Exception:  # noqa: BLE001
            pass
        self._started = False

    def _restore_session(self) -> None:
        if not self._sessions.has(_PROVIDER_NAME):
            return
        if self._pool is None:
            return
        try:
            context = self._pool.acquire().context
            self._sessions.apply(_PROVIDER_NAME, context)
        except Exception:  # noqa: BLE001
            pass

    def save_session(self) -> bool:
        """Snapshot the current browser session to the training session file."""
        if self._pool is None:
            return False
        try:
            return self._sessions.save(_PROVIDER_NAME, self._pool.acquire().context)
        except Exception:  # noqa: BLE001
            return False

    def _page(self) -> Any:
        if self._pool is None:
            raise RuntimeError("Provider not started — call start() first.")
        conn = self._pool.acquire()
        page = conn.get_or_create_page(_PROVIDER_NAME)
        self._sessions.apply_to_page(_PROVIDER_NAME, page)
        return page

    # ------------------------------------------------------------------ public API

    def is_logged_in(self) -> bool:
        try:
            page = self._page()
            page.goto(_DASHBOARD_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            return not _is_sign_in_url(page.url) and "/dashboard" in page.url.lower()
        except Exception:  # noqa: BLE001
            return False

    def health_check(self) -> dict[str, Any]:
        """Lightweight check — navigate dashboard, report login state."""
        try:
            page = self._page()
            page.goto(_DASHBOARD_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            url = page.url
            logged_in = not _is_sign_in_url(url) and "/dashboard" in url.lower()
            return {
                "provider": "stealthwriter_training",
                "logged_in": logged_in,
                "current_url": url,
                "session_file": str(self._sessions._path(_PROVIDER_NAME)),
                "user_data_dir": str(self._cfg.user_data_dir),
                "cdp_port": self._cfg.cdp_port,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "provider": "stealthwriter_training",
                "logged_in": False,
                "error": str(exc),
            }

    def rewrite(self, source_text: str, *, document_id: str | None = None) -> TeacherResult:
        """Humanize source_text and return a TeacherResult.

        Returns immediately with error='TEXT_TOO_LONG' without hitting
        StealthWriter if the word count exceeds max_text_words.
        Returns error='LOGIN_REQUIRED' / selection failures without retry.
        Retries with exponential backoff for NO_CHANGE / TIMEOUT / other errors.
        """
        cleaned = (source_text or "").strip()
        if not cleaned:
            return TeacherResult(
                success=False, humanized_text=None,
                provider="stealthwriter_training",
                model=self._cfg.model, level=self._cfg.level,
                elapsed_seconds=0.0, error="EMPTY_INPUT",
                meta={"retryable": False, "failed_stage": "SESSION_READY"},
            )

        if _word_count(cleaned) > self._cfg.max_text_words:
            return TeacherResult(
                success=False, humanized_text=None,
                provider="stealthwriter_training",
                model=self._cfg.model, level=self._cfg.level,
                elapsed_seconds=0.0, error="TEXT_TOO_LONG",
                error_detail=f"{_word_count(cleaned)} words > limit {self._cfg.max_text_words}",
                meta={"retryable": False, "failed_stage": "SESSION_READY"},
            )

        started = time.monotonic()
        delay = self._cfg.retry_delay_s
        last_error: str = "UNKNOWN"
        last_detail: str | None = None
        last_meta: dict[str, Any] = {}

        for attempt in range(1, self._cfg.max_retries + 1):
            trace = RunTrace()
            trace.mark("SESSION_READY")
            try:
                page = self._page()
                result = _humanize_once(
                    page,
                    cleaned,
                    self._cfg.model,
                    self._cfg.level,
                    self._cfg.timeout_s,
                    trace=trace,
                    debug_screenshots=bool(self._cfg.debug_screenshots),
                    debug_dir=str(self._cfg.debug_dir),
                    document_id=document_id,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = "EXCEPTION"
                last_detail = str(exc)
                result = {
                    "success": False,
                    "error": "EXCEPTION",
                    "error_detail": str(exc),
                    "retryable": True,
                    "failed_stage": trace.failed_stage or "SESSION_READY",
                    "last_successful_stage": trace.last_successful_stage,
                }

            error = result.get("error") or ""

            if result.get("success"):
                meta = {
                    "requested_model": result.get("requested_model", self._cfg.model),
                    "verified_model": result.get("verified_model"),
                    "ui_model_label": result.get("ui_model_label"),
                    "requested_level": result.get("requested_level", self._cfg.level),
                    "verified_level": result.get("verified_level"),
                    "selection_verified": bool(result.get("selection_verified")),
                    "last_successful_stage": result.get("last_successful_stage"),
                }
                if not (
                    meta["selection_verified"]
                    and meta["verified_model"]
                    and meta["ui_model_label"]
                    and meta["verified_level"] is not None
                ):
                    meta["selection_verified"] = False
                return TeacherResult(
                    success=True,
                    humanized_text=result["humanized_text"],
                    provider="stealthwriter_training",
                    model=self._cfg.model,
                    level=self._cfg.level,
                    elapsed_seconds=round(time.monotonic() - started, 3),
                    meta=meta,
                )

            failure_meta = {
                "document_id": document_id,
                "provider": "stealthwriter_training",
                "requested_model": result.get("requested_model", self._cfg.model),
                "requested_level": result.get("requested_level", self._cfg.level),
                "visible_model_label": result.get("visible_model_label"),
                "visible_level": result.get("visible_level"),
                "failed_stage": result.get("failed_stage"),
                "last_successful_stage": result.get("last_successful_stage"),
                "error_code": error,
                "error_message": result.get("error_detail") or error,
                "current_url": result.get("current_url"),
                "retryable": bool(result.get("retryable", error not in NON_RETRYABLE_ERRORS)),
                "attempt": attempt,
                "selection_verified": False,
                "screenshot_path": result.get("screenshot_path"),
            }
            if isinstance(result.get("debug"), dict):
                # Merge safe debug keys only (already sanitized).
                for key in (
                    "visible_model_label",
                    "visible_level",
                    "selection_stage",
                    "stages",
                    "screenshot_path",
                    "current_url",
                ):
                    if key in result["debug"] and failure_meta.get(key) is None:
                        failure_meta[key] = result["debug"][key]
            last_meta = failure_meta

            # LOGIN_REQUIRED / selection failures — no retry (fail closed)
            if error in NON_RETRYABLE_ERRORS:
                return TeacherResult(
                    success=False, humanized_text=None,
                    provider="stealthwriter_training",
                    model=self._cfg.model, level=self._cfg.level,
                    elapsed_seconds=round(time.monotonic() - started, 3),
                    error=error,
                    error_detail=result.get("error_detail")
                    or (
                        "Session expired. Re-run login_stealthwriter_training.py."
                        if error == "LOGIN_REQUIRED"
                        else None
                    ),
                    meta=failure_meta,
                )

            last_error = error
            last_detail = result.get("error_detail")

            if attempt < self._cfg.max_retries:
                print(
                    f"[sw-training] attempt {attempt}/{self._cfg.max_retries} failed "
                    f"({error}), retrying in {delay:.1f}s",
                    flush=True,
                )
                time.sleep(delay)
                delay = min(delay * self._cfg.backoff_multiplier, self._cfg.max_delay_s)

        last_meta.setdefault("attempt", self._cfg.max_retries)
        last_meta.setdefault("error_code", last_error)
        last_meta.setdefault("retryable", True)
        return TeacherResult(
            success=False, humanized_text=None,
            provider="stealthwriter_training",
            model=self._cfg.model, level=self._cfg.level,
            elapsed_seconds=round(time.monotonic() - started, 3),
            error=last_error,
            error_detail=last_detail,
            meta=last_meta,
        )
