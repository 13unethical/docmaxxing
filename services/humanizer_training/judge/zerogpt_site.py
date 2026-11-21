"""ZeroGPT free-site detector for offline DPO labeling (training worker only).

Uses Playwright against https://www.zerogpt.com/ the same way students do in the browser.
Does not import production browser singletons or Flask routes.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_DETECT_URL = "https://www.zerogpt.com/"
_MAX_CHARS = 15_000
_PERCENT_UI = re.compile(
    r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:AI|GPT|probability|chance)",
    re.IGNORECASE,
)


class ZeroGPTSiteError(RuntimeError):
    def __init__(self, code: str, message: str = "", *, retryable: bool = True) -> None:
        self.code = code
        self.message = message or code
        self.retryable = retryable
        super().__init__(f"{code}: {self.message}")


def parse_detect_payload(payload: dict[str, Any]) -> float:
    """Map ZeroGPT detect JSON to ai_frac in 0..1."""
    if not payload:
        raise ValueError("empty payload")
    top = payload
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for blob in (top, data):
        for key in ("fakePercentage", "ai_percentage", "aiPercentage", "ai_prob", "ai_frac", "score"):
            if key in blob and blob[key] is not None:
                val = float(blob[key])
                return val / 100.0 if val > 1.0 else val
    if payload.get("success") is False:
        msg = str(payload.get("message") or "detect failed")
        raise ZeroGPTSiteError("API_DENIED", msg, retryable=False)
    raise ValueError(f"no AI% in payload keys={sorted(payload.keys())}")


def ai_frac_from_page_text(body: str) -> float | None:
    """Best-effort parse of the public results panel (e.g. ``72.8% AI GPT*``)."""
    if not body:
        return None
  # Prefer the main gauge line over incidental percentages.
    for pat in (
        re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%\s*AI\s*GPT", re.I),
        re.compile(r"Most of your text.*?\n.*?(\d{1,3}(?:\.\d+)?)\s*%", re.I | re.S),
        _PERCENT_UI,
    ):
        m = pat.search(body)
        if m:
            val = float(m.group(1))
            if 0 <= val <= 100:
                return val / 100.0
    return None


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
class ZeroGPTSiteConfig:
    detect_url: str = field(default_factory=lambda: (os.environ.get("ZEROGPT_SITE_URL") or _DETECT_URL).strip())
    headless: bool = field(default_factory=lambda: _env_bool("ZEROGPT_SITE_HEADLESS", True))
    timeout_ms: int = field(default_factory=lambda: _env_int("ZEROGPT_SITE_TIMEOUT_MS", 90_000))
    navigation_timeout_ms: int = field(default_factory=lambda: _env_int("ZEROGPT_SITE_NAV_TIMEOUT_MS", 60_000))
    cooldown_s: float = field(default_factory=lambda: _env_float("ZEROGPT_SITE_COOLDOWN_S", 1.25))
    user_data_dir: str = field(
        default_factory=lambda: os.environ.get("ZEROGPT_SITE_CHROME_DIR") or "browser_profiles/zerogpt_site_chrome"
    )
    cdp_port: int = field(default_factory=lambda: _env_int("ZEROGPT_SITE_CDP_PORT", 9344))


def _find_textarea(page: Any) -> Any:
    import re as _re

    candidates = [
        page.get_by_placeholder(_re.compile(r"paste|enter|text|detect", _re.I)),
        page.locator("textarea").first,
        page.locator('[role="textbox"]').first,
        page.locator('[contenteditable="true"]').first,
    ]
    for loc in candidates:
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=2500):
                return loc.first
        except Exception:  # noqa: BLE001
            continue
    return None


def _find_detect_button(page: Any) -> Any:
    import re as _re

    candidates = [
        page.get_by_role("button", name=_re.compile(r"detect", _re.I)),
        page.locator("button").filter(has_text=_re.compile(r"detect", _re.I)),
        page.get_by_role("button", name=_re.compile(r"check", _re.I)),
    ]
    for loc in candidates:
        try:
            if loc.count() > 0 and loc.first.is_visible(timeout=2500):
                return loc.first
        except Exception:  # noqa: BLE001
            continue
    return None


def _dismiss_overlays(page: Any) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(120)
    except Exception:  # noqa: BLE001
        pass


def _set_text(page: Any, box: Any, text: str) -> None:
    try:
        box.click(timeout=5000)
    except Exception:  # noqa: BLE001
        pass
    try:
        box.fill(text, timeout=10_000)
        if (box.input_value() or "").strip() == text.strip():
            return
    except Exception:  # noqa: BLE001
        pass
    box.evaluate(
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


class ZeroGPTSiteJudge:
    """One browser tab; call ``detect`` in a loop with ``cooldown_s`` between checks."""

    def __init__(self, config: ZeroGPTSiteConfig | None = None) -> None:
        self.config = config or ZeroGPTSiteConfig()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        from playwright.sync_api import sync_playwright

        Path(self.config.user_data_dir).mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.config.user_data_dir,
            headless=self.config.headless,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        self._context = self._browser
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(self.config.timeout_ms)
        self._page.goto(self.config.detect_url, wait_until="domcontentloaded", timeout=self.config.navigation_timeout_ms)
        self._page.wait_for_timeout(800)
        _dismiss_overlays(self._page)
        self._started = True

    def stop(self) -> None:
        if self._browser:
            try:
                self._browser.close()
            except Exception:  # noqa: BLE001
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
        self._started = False

    def __enter__(self) -> ZeroGPTSiteJudge:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def detect(self, text: str) -> dict[str, Any]:
        if not self._started or self._page is None:
            raise ZeroGPTSiteError("NOT_STARTED", "call start() first", retryable=False)
        cleaned = (text or "").strip()
        if not cleaned:
            return {"ai_frac": 0.0, "judge": "zerogpt_site", "channel": "empty"}
        if len(cleaned) > _MAX_CHARS:
            raise ZeroGPTSiteError("TOO_LONG", f"{len(cleaned)} chars > {_MAX_CHARS}", retryable=False)

        page = self._page
        captured: dict[str, Any] = {}

        def on_response(resp: Any) -> None:
            url = (resp.url or "").lower()
            if "detect" not in url or "zerogpt" not in url:
                return
            try:
                if resp.status != 200:
                    return
                body = resp.json()
                if isinstance(body, dict):
                    captured["api"] = body
            except Exception:  # noqa: BLE001
                pass

        page.on("response", on_response)
        try:
            if not page.url.startswith(self.config.detect_url.rstrip("/")):
                page.goto(
                    self.config.detect_url,
                    wait_until="domcontentloaded",
                    timeout=self.config.navigation_timeout_ms,
                )
            _dismiss_overlays(page)
            box = _find_textarea(page)
            if box is None:
                page.reload(wait_until="domcontentloaded")
                box = _find_textarea(page)
            if box is None:
                raise ZeroGPTSiteError("NO_INPUT", "textarea not found", retryable=True)
            _set_text(page, box, cleaned)
            btn = _find_detect_button(page)
            if btn is None:
                raise ZeroGPTSiteError("NO_BUTTON", "detect button not found", retryable=True)
            btn.click(timeout=15_000)
            deadline = time.monotonic() + self.config.timeout_ms / 1000.0
            ai_frac: float | None = None
            channel = "unknown"
            while time.monotonic() < deadline:
                if "api" in captured:
                    try:
                        ai_frac = parse_detect_payload(captured["api"])
                        channel = "api"
                        break
                    except ZeroGPTSiteError:
                        raise
                    except Exception:  # noqa: BLE001
                        pass
                body = ""
                try:
                    body = page.inner_text("body")
                except Exception:  # noqa: BLE001
                    pass
                ui = ai_frac_from_page_text(body)
                if ui is not None and ui > 0.001:
                    ai_frac = ui
                    channel = "ui"
                    break
                page.wait_for_timeout(400)
            if ai_frac is None:
                raise ZeroGPTSiteError("NO_SCORE", "timed out waiting for ZeroGPT result", retryable=True)
        finally:
            page.remove_listener("response", on_response)

        if self.config.cooldown_s > 0:
            time.sleep(self.config.cooldown_s)
        return {
            "ai_frac": round(float(ai_frac), 4),
            "judge": "zerogpt_site",
            "channel": channel,
            "raw_api": captured.get("api"),
        }


def run_detect_loop(
    rows: list[dict],
    *,
    judge: ZeroGPTSiteJudge,
    on_result: Callable[[dict], None] | None = None,
    sleep_on_error: float = 5.0,
) -> tuple[list[dict], dict]:
    """Label ``rows`` (must have ``text``); returns labeled rows and summary."""
    labeled: list[dict] = []
    errors = 0
    for i, row in enumerate(rows):
        text = row.get("text") or row.get("assistant") or ""
        attempt = 0
        while True:
            attempt += 1
            try:
                verdict = judge.detect(text)
                out = {**row, **verdict, "words": len(text.split())}
                labeled.append(out)
                if on_result:
                    on_result(out)
                break
            except ZeroGPTSiteError as exc:
                errors += 1
                if not exc.retryable or attempt >= 3:
                    print(f"label fail {i}: {exc}", flush=True)
                    break
                time.sleep(sleep_on_error)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"label fail {i}: {exc}", flush=True)
                break
        if (i + 1) % 10 == 0:
            print(f"zerogpt site labeled {len(labeled)}/{i + 1}", flush=True)
    summary = {"labeled": len(labeled), "errors": errors, "input": len(rows), "judge": "zerogpt_site"}
    return labeled, summary