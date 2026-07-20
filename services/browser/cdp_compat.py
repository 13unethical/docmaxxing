"""CDP connection compatibility helpers.

Root cause of the "Browser context management is not supported" failure
======================================================================

When Playwright attaches to an already-running Chrome via
``chromium.connect_over_cdp(...)`` it wraps the *pre-existing* default browser
context. While doing so, recent Playwright builds issue a browser-wide
``Browser.setDownloadBehavior`` CDP command to route downloads into a temp
folder. Some Chrome builds (observed with **Chrome 150 + Playwright 1.61**)
reject that command outright with::

    BrowserType.connect_over_cdp:
    Protocol error (Browser.setDownloadBehavior):
    Browser context management is not supported.

This aborts the whole ``connect_over_cdp`` call, so every Humanize job fails
before StealthWriter is even reached.

The fix (no architecture change, no UI workaround)
--------------------------------------------------

Playwright exposes ``no_defaults=True`` on ``connect_over_cdp``. With it, the
wrapped default context is created with
``acceptDownloads="internal-browser-default"``, which makes Playwright *skip*
the unsupported ``Browser.setDownloadBehavior`` command entirely. We keep using
the already-open context (``browser.contexts()[0]``) and never call
``browser.new_context()`` — staying fully CDP-native and reusing the real
Chrome profile/session.

``connect_over_cdp_compat`` applies ``no_defaults=True`` and falls back to a
plain connect on older Playwright versions that don't know the kwarg (those
versions predate the regression and connect fine anyway).
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from typing import Any


def connect_over_cdp_compat(
    chromium: Any,
    cdp_url: str,
    *,
    timeout_ms: int | None = None,
) -> Any:
    """Attach to Chrome via CDP without tripping ``Browser.setDownloadBehavior``.

    Reuses the existing context; never creates a new browser context.
    """
    kwargs: dict[str, Any] = {}
    if timeout_ms is not None:
        kwargs["timeout"] = timeout_ms
    try:
        # Preferred path: skip the unsupported browser-wide download-behavior call.
        return chromium.connect_over_cdp(cdp_url, no_defaults=True, **kwargs)
    except TypeError:
        # Older Playwright without `no_defaults` — connect the classic way.
        return chromium.connect_over_cdp(cdp_url, **kwargs)


# --------------------------------------------------------------------------- diagnostics
def playwright_version() -> str:
    try:
        import importlib.metadata as md

        return md.version("playwright")
    except Exception:  # noqa: BLE001
        try:
            import playwright  # type: ignore

            return getattr(playwright, "__version__", "unknown")
        except Exception:  # noqa: BLE001
            return "unknown"


def _json_version(cdp_url: str, timeout: float = 3.0) -> dict[str, Any]:
    base = cdp_url.rstrip("/")
    with urllib.request.urlopen(f"{base}/json/version", timeout=timeout) as resp:
        return json.load(resp)


def _chrome_launch_flags() -> list[str]:
    """Best-effort discovery of the debugged Chrome's command-line flags."""
    try:
        import psutil  # type: ignore
    except Exception:  # noqa: BLE001
        return []
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
        except Exception:  # noqa: BLE001
            continue
        if any("--remote-debugging-port" in str(arg) for arg in cmdline):
            return [str(a) for a in cmdline]
    return []


# Probe script executed in an isolated subprocess so a Playwright driver crash
# can never take down the Flask/worker process (they own their own Playwright).
_PROBE_SCRIPT = r"""
import json, sys
from playwright.sync_api import sync_playwright
cdp_url = sys.argv[1]
out = {"classic_ok": None, "set_download_behavior_supported": None,
       "no_defaults_ok": False, "contexts_after_connect": None, "error": None}
pw = None
try:
    pw = sync_playwright().start()
    try:
        b = pw.chromium.connect_over_cdp(cdp_url)
        out["classic_ok"] = True
        out["set_download_behavior_supported"] = True
        try: b.close()
        except Exception: pass
    except Exception as exc:
        out["classic_ok"] = False
        msg = str(exc)
        if "setDownloadBehavior" in msg or "Browser context management is not supported" in msg:
            out["set_download_behavior_supported"] = False
        else:
            out["error"] = msg[:300]
    try:
        b2 = pw.chromium.connect_over_cdp(cdp_url, no_defaults=True)
        out["no_defaults_ok"] = True
        try: out["contexts_after_connect"] = len(b2.contexts)
        except Exception: pass
        try: b2.close()
        except Exception: pass
    except TypeError:
        b2 = pw.chromium.connect_over_cdp(cdp_url)
        out["no_defaults_ok"] = True
        try: out["contexts_after_connect"] = len(b2.contexts)
        except Exception: pass
        try: b2.close()
        except Exception: pass
    except Exception as exc:
        out["error"] = (out["error"] or "") + " | no_defaults: " + str(exc)[:300]
finally:
    if pw is not None:
        try: pw.stop()
        except Exception: pass
print(json.dumps(out))
"""


def cdp_diagnostics(cdp_url: str) -> dict[str, Any]:
    """Return a full diagnostic report for the CDP connection.

    Safe to call from the Flask request thread: Chrome version comes over HTTP,
    flags from psutil, and the Playwright connection probe runs in an isolated
    subprocess so it can never disturb the long-lived BrowserService Playwright.
    """
    report: dict[str, Any] = {
        "cdp_url": cdp_url,
        "playwright_version": playwright_version(),
        "chrome_version": None,
        "protocol_version": None,
        "user_agent": None,
        "launch_mode": None,
        "chrome_flags": [],
        "contexts_after_connect": None,
        "set_download_behavior_supported": None,
        "connect_strategy": "connect_over_cdp(no_defaults=True)",
        "connect_ok": False,
        "notes": [],
    }

    # --- Chrome version + launch mode (HTTP only; no Playwright) --------------
    try:
        info = _json_version(cdp_url)
        report["chrome_version"] = info.get("Browser")
        report["protocol_version"] = info.get("Protocol-Version")
        ua = info.get("User-Agent") or ""
        report["user_agent"] = ua
        report["launch_mode"] = "headless" if "Headless" in ua else "headed (CDP attach)"
    except Exception as exc:  # noqa: BLE001
        report["notes"].append(f"Could not read {cdp_url}/json/version: {exc}")

    flags = _chrome_launch_flags()
    if flags:
        report["chrome_flags"] = flags
        report["launch_mode"] = (
            "headless" if any("--headless" in f for f in flags) else "headed (CDP attach)"
        )

    # --- Connection probe (isolated subprocess) ------------------------------
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE_SCRIPT, cdp_url],
            capture_output=True,
            text=True,
            timeout=45,
        )
        line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout.strip() else ""
        probe = json.loads(line) if line else {}
        report["set_download_behavior_supported"] = probe.get("set_download_behavior_supported")
        report["connect_ok"] = bool(probe.get("no_defaults_ok"))
        report["contexts_after_connect"] = probe.get("contexts_after_connect")
        if probe.get("set_download_behavior_supported") is False:
            report["notes"].append(
                "Classic connect_over_cdp rejected Browser.setDownloadBehavior "
                "→ using no_defaults=True (root-cause workaround)."
            )
        if probe.get("error"):
            report["notes"].append(f"probe: {probe['error']}")
        if proc.returncode != 0 and not report["connect_ok"]:
            report["notes"].append(
                f"probe subprocess exited {proc.returncode}: {(proc.stderr or '')[:200]}"
            )
    except Exception as exc:  # noqa: BLE001
        report["notes"].append(f"connection probe failed: {str(exc)[:200]}")

    return report
