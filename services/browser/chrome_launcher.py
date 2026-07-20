"""ChromeLauncher — owns the OS-level Google Chrome process for CDP automation.

Automatically launches Chrome with remote debugging if it is not already
running, or reuses an existing CDP endpoint. No manual terminal commands are
ever required.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

try:  # optional; used for pid discovery + memory metrics
    import psutil  # type: ignore
except Exception:  # noqa: BLE001
    psutil = None  # type: ignore

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 9222
_DEFAULT_USER_DATA_DIR = Path("browser_profiles/chrome_user_data")

_MACOS_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
_LINUX_CANDIDATES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
_WINDOWS_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def resolve_chrome_path() -> str | None:
    """Best-effort resolution of the Google Chrome executable."""
    override = (
        os.environ.get("BROWSER_CHROME_PATH")
        or os.environ.get("BROWSER_EXECUTABLE_PATH")
        or ""
    ).strip()
    if override and Path(override).is_file():
        return override

    if sys.platform == "darwin" and _MACOS_CHROME.is_file():
        return str(_MACOS_CHROME)

    if sys.platform.startswith("linux"):
        for name in _LINUX_CANDIDATES:
            found = shutil.which(name)
            if found:
                return found

    if os.name == "nt":
        for candidate in _WINDOWS_CANDIDATES:
            if Path(candidate).is_file():
                return candidate

    # Last resort: anything named chrome on PATH.
    return shutil.which("google-chrome") or shutil.which("chrome")


class ChromeLauncher:
    """Launch or reuse a Google Chrome instance exposing the DevTools Protocol."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        user_data_dir: str | Path | None = None,
        chrome_path: str | None = None,
        extra_args: list[str] | None = None,
    ) -> None:
        self._host = host or os.environ.get("BROWSER_CDP_HOST", _DEFAULT_HOST)
        self._port = int(port or os.environ.get("BROWSER_CDP_PORT", _DEFAULT_PORT))
        self._user_data_dir = Path(
            user_data_dir
            or os.environ.get("CHROME_USER_DATA_DIR")
            or os.environ.get("BROWSER_USER_DATA_DIR")
            or _DEFAULT_USER_DATA_DIR
        ).expanduser()
        self._chrome_path = chrome_path or resolve_chrome_path()
        if extra_args is not None:
            self._extra_args = list(extra_args)
        else:
            raw = (os.environ.get("BROWSER_EXTRA_ARGS") or "").strip()
            self._extra_args = [a for a in raw.split() if a]
            # Headless Linux VPS defaults when no display is available.
            if (
                sys.platform.startswith("linux")
                and not os.environ.get("DISPLAY")
                and not any(a.startswith("--headless") for a in self._extra_args)
            ):
                self._extra_args.extend(
                    [
                        "--headless=new",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                    ]
                )

        self._process: subprocess.Popen[bytes] | None = None
        self._launched_here = False

    # ------------------------------------------------------------------ props
    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def cdp_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    @property
    def user_data_dir(self) -> Path:
        return self._user_data_dir

    @property
    def chrome_path(self) -> str | None:
        return self._chrome_path

    # ------------------------------------------------------------------ cdp
    def cdp_version(self, timeout: float = 1.0) -> dict[str, Any] | None:
        """Return Chrome's /json/version payload if CDP is reachable."""
        try:
            with urllib.request.urlopen(f"{self.cdp_url}/json/version", timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def is_cdp_available(self) -> bool:
        return self.cdp_version() is not None

    def is_running(self) -> bool:
        return self.is_cdp_available()

    # ------------------------------------------------------------------ lifecycle
    def ensure_running(self) -> dict[str, Any]:
        """Guarantee a CDP-reachable Chrome. Reuse if present, else launch."""
        if self.is_cdp_available():
            return {"launched": False, "reused": True, "cdp_url": self.cdp_url, "pid": self.pid}
        return self.launch()

    def launch(self) -> dict[str, Any]:
        """Launch a new Chrome process with remote debugging enabled."""
        if self.is_cdp_available():
            return {"launched": False, "reused": True, "cdp_url": self.cdp_url, "pid": self.pid}

        if not self._chrome_path:
            raise RuntimeError(
                "Google Chrome executable not found. Set BROWSER_CHROME_PATH to the "
                "Chrome binary path."
            )

        self._user_data_dir.mkdir(parents=True, exist_ok=True)
        args = [
            self._chrome_path,
            f"--remote-debugging-port={self._port}",
            f"--user-data-dir={self._user_data_dir.resolve()}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            *self._extra_args,
        ]
        print(f"Launching Chrome: {self._chrome_path} (CDP {self.cdp_url})", flush=True)
        self._process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._launched_here = True
        self._wait_for_cdp(timeout=30.0)
        return {"launched": True, "reused": False, "cdp_url": self.cdp_url, "pid": self.pid}

    def restart(self) -> dict[str, Any]:
        """Terminate the Chrome we launched (if any) and start a fresh one."""
        self.stop()
        # Give the OS a moment to release the debugging port.
        for _ in range(20):
            if not self.is_cdp_available():
                break
            time.sleep(0.25)
        return self.launch()

    def stop(self) -> None:
        """Terminate Chrome only if this launcher started it."""
        if self._process is not None and self._launched_here:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    self._process.kill()
            except Exception:  # noqa: BLE001
                pass
        self._process = None
        self._launched_here = False

    def _wait_for_cdp(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_cdp_available():
                return
            time.sleep(0.25)
        raise RuntimeError(
            f"Chrome did not expose CDP at {self.cdp_url} within {timeout:.0f}s."
        )

    # ------------------------------------------------------------------ metrics
    @property
    def pid(self) -> int | None:
        if self._process is not None and self._process.poll() is None:
            return self._process.pid
        return self._discover_pid_on_port()

    def _discover_pid_on_port(self) -> int | None:
        if psutil is None:
            return None
        needle = f"--remote-debugging-port={self._port}"
        # Primary: scan process cmdlines (no root required on macOS).
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = proc.info.get("cmdline") or []
                except Exception:  # noqa: BLE001
                    continue
                if not cmdline:
                    continue
                joined = " ".join(cmdline)
                if needle in joined and "--type=" not in joined:
                    return int(proc.info["pid"])
        except Exception:  # noqa: BLE001
            pass
        # Fallback: socket table (may require elevated privileges).
        try:
            for conn in psutil.net_connections(kind="inet"):
                laddr = getattr(conn, "laddr", None)
                if (
                    laddr
                    and getattr(laddr, "port", None) == self._port
                    and conn.status == psutil.CONN_LISTEN
                    and conn.pid
                ):
                    return int(conn.pid)
        except Exception:  # noqa: BLE001
            return None
        return None

    def memory_usage(self) -> dict[str, Any] | None:
        """RSS of the Chrome process tree in MB (requires psutil)."""
        pid = self.pid
        if psutil is None or pid is None:
            return None
        try:
            proc = psutil.Process(pid)
            procs = [proc, *proc.children(recursive=True)]
            rss = 0
            for p in procs:
                try:
                    rss += p.memory_info().rss
                except Exception:  # noqa: BLE001
                    continue
            return {
                "rss_mb": round(rss / (1024 * 1024), 1),
                "process_count": len(procs),
            }
        except Exception:  # noqa: BLE001
            return None

    def status(self) -> dict[str, Any]:
        return {
            "cdp_url": self.cdp_url,
            "available": self.is_cdp_available(),
            "pid": self.pid,
            "launched_here": self._launched_here,
            "chrome_path": self._chrome_path,
            "user_data_dir": str(self._user_data_dir.resolve()),
        }
