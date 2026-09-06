"""Tests for training-only headed login helpers (no live Chrome)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.browser.chrome_launcher import ChromeLauncher
from services.humanizer_training.teacher.headed_login import (
    HEADED_LOGIN_CHROME_EXTRA_ARGS,
    assert_cdp_is_headed,
    assert_no_existing_headless_cdp,
    build_headed_chrome_argv,
    child_env_with_display,
    chrome_args_are_headed,
    cdp_user_agent,
    headed_login_chrome_extra_args,
    is_headless_user_agent,
    is_training_dashboard_url,
    require_xvfb_binary,
)
from services.humanizer_training.teacher.stealthwriter_provider import (
    StealthWriterTeacherProvider,
    TrainingBrowserConfig,
)
import scripts.login_stealthwriter_training as login_script


def test_headed_login_cli_flag_parses():
    args = login_script.parse_args(["--headed-login"])
    assert args.headed_login is True
    assert args.xvfb_display == ":99"
    args2 = login_script.parse_args([])
    assert args2.headed_login is False


def test_headed_chrome_args_have_no_headless():
    args = headed_login_chrome_extra_args()
    assert chrome_args_are_headed(args)
    assert "--ozone-platform=x11" in args
    assert not any(a.startswith("--headless") for a in HEADED_LOGIN_CHROME_EXTRA_ARGS)


def test_build_headed_chrome_argv_strips_headless(tmp_path: Path):
    argv = build_headed_chrome_argv(
        chrome_path="/usr/bin/google-chrome",
        port=9333,
        user_data_dir=tmp_path / "training_chrome",
        extra_args=["--no-sandbox", "--headless=new", "--disable-gpu"],
    )
    assert chrome_args_are_headed(argv)
    assert any(a.startswith("--remote-debugging-port=9333") for a in argv)
    assert any(str(tmp_path / "training_chrome") in a for a in argv)


def test_child_env_forces_display(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    env = child_env_with_display(":99")
    assert env["DISPLAY"] == ":99"


def test_chrome_launcher_adds_headless_without_display(monkeypatch, tmp_path: Path):
    """Collector / default launcher path unchanged: no DISPLAY → headless."""
    if not sys.platform.startswith("linux"):
        monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("BROWSER_EXTRA_ARGS", raising=False)
    launcher = ChromeLauncher(
        port=19335,
        user_data_dir=tmp_path / "chrome",
        chrome_path="/usr/bin/google-chrome",
    )
    assert any(a.startswith("--headless") for a in launcher._extra_args)


def test_chrome_launcher_skips_headless_when_display_set(monkeypatch, tmp_path: Path):
    if not sys.platform.startswith("linux"):
        monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.delenv("BROWSER_EXTRA_ARGS", raising=False)
    launcher = ChromeLauncher(
        port=19336,
        user_data_dir=tmp_path / "chrome",
        chrome_path="/usr/bin/google-chrome",
    )
    assert chrome_args_are_headed(launcher._extra_args)


def test_training_provider_default_does_not_force_headed_args(monkeypatch, tmp_path: Path):
    """Collector path: chrome_extra_args=None → launcher keeps default headless-on-linux."""
    if not sys.platform.startswith("linux"):
        monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("BROWSER_EXTRA_ARGS", raising=False)
    cfg = TrainingBrowserConfig(
        cdp_port=19338,
        user_data_dir=str(tmp_path / "training_chrome"),
        session_dir=str(tmp_path / "training_sessions"),
        chrome_extra_args=None,
    )
    provider = StealthWriterTeacherProvider(cfg)
    assert any(a.startswith("--headless") for a in provider._launcher._extra_args)


def test_headless_user_agent_detection():
    assert is_headless_user_agent(
        "Mozilla/5.0 ... HeadlessChrome/150.0.0.0 Safari/537.36"
    )
    assert not is_headless_user_agent(
        "Mozilla/5.0 ... Chrome/150.0.0.0 Safari/537.36"
    )


def test_assert_cdp_is_headed_fails_on_headless_ua(monkeypatch):
    monkeypatch.setattr(
        "services.humanizer_training.teacher.headed_login.fetch_cdp_version",
        lambda **_k: {
            "User-Agent": "Mozilla/5.0 HeadlessChrome/150.0.0.0 Safari/537.36"
        },
    )
    with pytest.raises(RuntimeError, match="HeadlessChrome"):
        assert_cdp_is_headed(port=9333)


def test_assert_no_existing_headless_cdp(monkeypatch):
    monkeypatch.setattr(
        "services.humanizer_training.teacher.headed_login.fetch_cdp_version",
        lambda **_k: {
            "User-Agent": "Mozilla/5.0 HeadlessChrome/150.0.0.0 Safari/537.36"
        },
    )
    with pytest.raises(RuntimeError, match="already running as HeadlessChrome"):
        assert_no_existing_headless_cdp(port=9333)


def test_dashboard_url_gate():
    assert is_training_dashboard_url("https://app.stealthwriter.ai/dashboard") is True
    assert is_training_dashboard_url("https://app.stealthwriter.ai/sign-in") is False
    assert is_training_dashboard_url("") is False


def test_session_saved_only_after_dashboard_ok(tmp_path: Path):
    cfg = TrainingBrowserConfig(
        cdp_port=19340,
        user_data_dir=str(tmp_path / "training_chrome"),
        session_dir=str(tmp_path / "training_sessions"),
        chrome_extra_args=headed_login_chrome_extra_args(),
    )
    provider = StealthWriterTeacherProvider(cfg)
    provider.save_session = MagicMock(return_value=True)  # type: ignore[method-assign]

    bad_url = "https://example.com/sign-in"
    if is_training_dashboard_url(bad_url):
        provider.save_session()
    provider.save_session.assert_not_called()

    good_url = "https://example.com/dashboard"
    if is_training_dashboard_url(good_url):
        assert provider.save_session() is True
    provider.save_session.assert_called_once()


def test_require_xvfb_missing(monkeypatch):
    monkeypatch.setattr(
        "services.humanizer_training.teacher.headed_login.shutil.which",
        lambda _name: None,
    )
    with pytest.raises(FileNotFoundError, match="Xvfb is not installed"):
        require_xvfb_binary()


def test_cdp_user_agent_helper():
    assert "HeadlessChrome" in cdp_user_agent(
        {"User-Agent": "x HeadlessChrome/150 y"}
    )
