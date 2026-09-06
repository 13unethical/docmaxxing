"""Helpers for training-only headed manual login on headless VPS hosts.

Uses a private Xvfb display (default ``:99``). Does not open public VNC/CDP ports.
Collector / production paths must not import or call this for normal runs.

Critical: do **not** rely on ``ChromeLauncher.ensure_running()`` to start headed
Chrome — it will silently reuse an existing headless CDP on the same port.
Headed login launches Chrome itself with an explicit ``DISPLAY`` env and argv
that never contains ``--headless``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from services.browser.chrome_launcher import resolve_chrome_path

DEFAULT_XVFB_DISPLAY = ":99"
DEFAULT_TRAINING_CDP_HOST = "127.0.0.1"
DEFAULT_TRAINING_CDP_PORT = 9333

# Headed Chrome on Linux VPS (root) still needs sandbox flags; never add --headless.
# --ozone-platform=x11 forces a real X11 window under Xvfb (avoids headless ozone).
HEADED_LOGIN_CHROME_EXTRA_ARGS: tuple[str, ...] = (
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--ozone-platform=x11",
)


@dataclass(slots=True)
class XvfbSession:
    display: str
    process: subprocess.Popen[bytes] | None
    started_by_us: bool

    def stop(self) -> None:
        if not self.started_by_us or self.process is None:
            return
        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception:  # noqa: BLE001
                self.process.kill()
        except Exception:  # noqa: BLE001
            pass
        self.process = None
        self.started_by_us = False


@dataclass(slots=True)
class HeadedChromeSession:
    """OS-owned headed Chrome process for training login only."""

    host: str
    port: int
    display: str
    user_data_dir: Path
    process: subprocess.Popen[bytes] | None
    args: list[str] = field(default_factory=list)

    @property
    def cdp_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def stop(self) -> None:
        if self.process is None:
            return
        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except Exception:  # noqa: BLE001
                self.process.kill()
        except Exception:  # noqa: BLE001
            pass
        self.process = None


def xvfb_binary() -> str | None:
    return shutil.which("Xvfb")


def require_xvfb_binary() -> str:
    path = xvfb_binary()
    if not path:
        raise FileNotFoundError(
            "Xvfb is not installed on this host. Install it manually "
            "(e.g. `apt-get install -y xvfb`) then re-run with --headed-login. "
            "This tool will not install packages automatically."
        )
    return path


def display_is_ready(display: str, *, timeout_s: float = 0.5) -> bool:
    """Return True if an X server already answers on ``display``."""
    xdpyinfo = shutil.which("xdpyinfo")
    env = {**os.environ, "DISPLAY": display}
    if xdpyinfo:
        try:
            completed = subprocess.run(
                [xdpyinfo],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(0.2, float(timeout_s)),
                check=False,
            )
            return completed.returncode == 0
        except Exception:  # noqa: BLE001
            return False
    num = display.lstrip(":")
    lock = f"/tmp/.X{num}-lock"
    return os.path.exists(lock)


def start_xvfb(*, display: str = DEFAULT_XVFB_DISPLAY) -> XvfbSession:
    """Start Xvfb on ``display`` if needed. Never auto-installs packages."""
    binary = require_xvfb_binary()
    if display_is_ready(display):
        return XvfbSession(display=display, process=None, started_by_us=False)

    proc = subprocess.Popen(
        [
            binary,
            display,
            "-screen",
            "0",
            "1280x720x24",
            "-ac",
            "-nolisten",
            "tcp",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"Xvfb exited early while starting display {display} "
                f"(exit={proc.returncode})."
            )
        if display_is_ready(display, timeout_s=0.4):
            return XvfbSession(display=display, process=proc, started_by_us=True)
        time.sleep(0.2)
    proc.terminate()
    raise RuntimeError(f"Xvfb did not become ready on display {display}.")


def apply_display_env(display: str) -> str:
    """Set process DISPLAY (also inherited by children unless overridden)."""
    os.environ["DISPLAY"] = display
    return display


def headed_login_chrome_extra_args() -> list[str]:
    """Explicit args for headed training login (no --headless)."""
    return list(HEADED_LOGIN_CHROME_EXTRA_ARGS)


def chrome_args_are_headed(args: Sequence[str]) -> bool:
    return not any(str(a).startswith("--headless") for a in args)


def build_headed_chrome_argv(
    *,
    chrome_path: str,
    host: str = DEFAULT_TRAINING_CDP_HOST,
    port: int = DEFAULT_TRAINING_CDP_PORT,
    user_data_dir: str | Path,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    """Build Chrome argv for headed training login. Never includes --headless."""
    extras = list(extra_args) if extra_args is not None else headed_login_chrome_extra_args()
    # Defense-in-depth: strip any accidental headless flags.
    extras = [a for a in extras if not str(a).startswith("--headless")]
    if not chrome_args_are_headed(extras):
        raise RuntimeError("headed Chrome argv still contains --headless")
    user_dir = Path(user_data_dir).expanduser().resolve()
    user_dir.mkdir(parents=True, exist_ok=True)
    # Bind debugging to localhost only (SSH tunnel for remote view).
    # Chrome uses --remote-debugging-port with default bind 127.0.0.1 in practice
    # when not using --remote-debugging-address; keep host explicit in docs/CDP URL.
    _ = host
    argv = [
        chrome_path,
        f"--remote-debugging-port={int(port)}",
        f"--user-data-dir={user_dir}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        *extras,
    ]
    if not chrome_args_are_headed(argv):
        raise RuntimeError("built Chrome argv unexpectedly contains --headless")
    return argv


def child_env_with_display(display: str) -> dict[str, str]:
    """Environment for the Chrome child: force DISPLAY, never empty."""
    env = {k: str(v) for k, v in os.environ.items()}
    env["DISPLAY"] = display
    return env


def fetch_cdp_version(
    *, host: str = DEFAULT_TRAINING_CDP_HOST, port: int = DEFAULT_TRAINING_CDP_PORT, timeout: float = 1.5
) -> dict[str, Any] | None:
    url = f"http://{host}:{int(port)}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def cdp_user_agent(version_payload: dict[str, Any] | None) -> str:
    if not version_payload:
        return ""
    return str(version_payload.get("User-Agent") or version_payload.get("userAgent") or "")


def is_headless_user_agent(user_agent: str) -> bool:
    return "HeadlessChrome" in (user_agent or "")


def assert_cdp_is_headed(
    *, host: str = DEFAULT_TRAINING_CDP_HOST, port: int = DEFAULT_TRAINING_CDP_PORT
) -> dict[str, Any]:
    """Fail closed if CDP browser is HeadlessChrome."""
    payload = fetch_cdp_version(host=host, port=port, timeout=2.0)
    if payload is None:
        raise RuntimeError(
            f"CDP not reachable at http://{host}:{port}/json/version after headed launch."
        )
    ua = cdp_user_agent(payload)
    if is_headless_user_agent(ua):
        raise RuntimeError(
            "Headed login failed: Chrome User-Agent contains HeadlessChrome. "
            f"UA={ua!r}. Stop any leftover training Chrome on port {port} "
            "(it was likely reused or launched with --headless=new), then retry "
            "`python3 scripts/login_stealthwriter_training.py --headed-login`."
        )
    return payload


def assert_no_existing_headless_cdp(
    *, host: str = DEFAULT_TRAINING_CDP_HOST, port: int = DEFAULT_TRAINING_CDP_PORT
) -> None:
    """Refuse to proceed if port already serves HeadlessChrome."""
    payload = fetch_cdp_version(host=host, port=port, timeout=1.0)
    if payload is None:
        return
    ua = cdp_user_agent(payload)
    if is_headless_user_agent(ua):
        raise RuntimeError(
            f"Training CDP http://{host}:{port} is already running as HeadlessChrome. "
            "Kill that process before --headed-login, e.g.\n"
            f"  ss -lntp | grep {port}\n"
            f"  pkill -f 'remote-debugging-port={port}'\n"
            "Then re-run headed login."
        )
    # Non-headless already up: also refuse so we own a clean launch.
    raise RuntimeError(
        f"Training CDP http://{host}:{port} is already in use (UA={ua!r}). "
        "Stop it first, then re-run --headed-login."
    )


def launch_headed_training_chrome(
    *,
    display: str,
    user_data_dir: str | Path,
    host: str = DEFAULT_TRAINING_CDP_HOST,
    port: int = DEFAULT_TRAINING_CDP_PORT,
    chrome_path: str | None = None,
) -> HeadedChromeSession:
    """Start headed Chrome with DISPLAY forced in the child environment."""
    apply_display_env(display)
    if not display_is_ready(display, timeout_s=1.0):
        raise RuntimeError(
            f"DISPLAY={display} is not ready. Is Xvfb running? "
            "Install/start Xvfb before --headed-login."
        )
    binary = (chrome_path or resolve_chrome_path() or "").strip()
    if not binary:
        raise RuntimeError(
            "Google Chrome executable not found. Set BROWSER_CHROME_PATH."
        )
    assert_no_existing_headless_cdp(host=host, port=port)
    argv = build_headed_chrome_argv(
        chrome_path=binary,
        host=host,
        port=port,
        user_data_dir=user_data_dir,
    )
    env = child_env_with_display(display)
    print(
        f"Launching HEADED training Chrome: {binary} "
        f"(DISPLAY={display} CDP http://{host}:{port})",
        flush=True,
    )
    print(f"  argv extras: {[a for a in argv if a.startswith('--')]}", flush=True)
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )
    session = HeadedChromeSession(
        host=host,
        port=int(port),
        display=display,
        user_data_dir=Path(user_data_dir).expanduser().resolve(),
        process=proc,
        args=list(argv),
    )
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"Headed Chrome exited early (code={proc.returncode}). "
                f"DISPLAY={display}. Check Xvfb and Chrome deps."
            )
        payload = fetch_cdp_version(host=host, port=port, timeout=0.8)
        if payload is not None:
            assert_cdp_is_headed(host=host, port=port)
            return session
        time.sleep(0.25)
    proc.terminate()
    raise RuntimeError(
        f"Headed Chrome did not expose CDP at http://{host}:{port} within 30s."
    )


def is_training_dashboard_url(url: str) -> bool:
    """True only when the browser is on a post-login StealthWriter dashboard."""
    low = (url or "").strip().lower()
    if not low:
        return False
    if "/sign-in" in low or "/signin" in low or "/login" in low:
        return False
    return "/dashboard" in low
