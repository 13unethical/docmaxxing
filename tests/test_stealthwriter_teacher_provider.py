"""Tests for StealthWriterTeacherProvider (isolated training adapter).

ALL tests use fake/mock browser objects — no real Chrome is launched,
no real StealthWriter requests are made.

Safety checks
-------------
* No BrowserService.instance() call in provider source
* No BrowserService.reset_instance() call
* No JobManager reference
* No WalletService reference
* No dataset_logger reference
* No 'app' module import
"""
from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
from services.humanizer_training.teacher.stealthwriter_provider import (
    StealthWriterTeacherProvider,
    TrainingBrowserConfig,
    TeacherResult,
    _word_count,
    _is_sign_in_url,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROVIDER_SRC = (
    Path(__file__).resolve().parent.parent
    / "services/humanizer_training/teacher/stealthwriter_provider.py"
)


_BASE_CFG = dict(
    cdp_port=19333,
    user_data_dir="browser_profiles/test_training_chrome",
    session_dir="browser_profiles/test_training_sessions",
    model="Legacy 5.1",
    level=8,
    timeout_s=5.0,
    max_retries=2,
    retry_delay_s=0.0,
    max_text_words=5000,
)


def _make_config(**overrides) -> TrainingBrowserConfig:
    """Return a TrainingBrowserConfig pointing to test-only dirs."""
    return TrainingBrowserConfig(**{**_BASE_CFG, **overrides})


class _FakePage:
    """Minimal fake Playwright page that simulates a successful humanization."""

    def __init__(self, *, humanized: str = "Humanized output text here.", sign_in: bool = False):
        self._url = "https://stealthwriter.ai/sign-in" if sign_in else "https://stealthwriter.ai/dashboard/humanizer"
        self._humanized = humanized
        self.closed = False
        self.goto_calls: list[str] = []

    @property
    def url(self) -> str:
        return self._url

    def goto(self, url: str, **_: object) -> None:
        self.goto_calls.append(url)

    def wait_for_load_state(self, *_: object, **__: object) -> None:
        pass

    def wait_for_timeout(self, *_: object, **__: object) -> None:
        pass

    def is_closed(self) -> bool:
        return self.closed

    # Locators
    def get_by_placeholder(self, *_: object, **__: object) -> "_FakeLocator":
        return _FakeLocator(visible=True)

    def get_by_role(self, role: str, **kwargs: object) -> "_FakeLocator":
        name_pattern = kwargs.get("name")
        if role == "button":
            # Simulate "Humanize" button
            import re
            if name_pattern and re.search(r"humanize", str(name_pattern), re.I):
                return _FakeLocator(visible=True, count=1)
            if name_pattern and re.search(r"rehumanize|humanize more", str(name_pattern), re.I):
                return _FakeLocator(visible=False, count=0)
            if name_pattern and re.search(r"humanizing", str(name_pattern), re.I):
                return _FakeLocator(visible=False, count=0)
        return _FakeLocator(visible=False, count=0)

    def locator(self, selector: str, **__: object) -> "_FakeLocator":
        if selector == "textarea":
            return _FakeLocator(visible=True, count=1)
        return _FakeLocator(visible=False, count=0)

    def evaluate(self, script: str, *args: object, **__: object) -> object:
        # Return humanized text for the result extraction JS
        if "whitespace-pre-wrap" in script or "rehumanize" in script.lower():
            return self._humanized
        # Return False for generation_busy checks
        return False

    def keyboard(self) -> None:
        pass

    @property
    def keyboard(self):  # type: ignore[override]
        kb = SimpleNamespace()
        kb.press = lambda *_: None
        kb.insert_text = lambda *_: None
        return kb

    def title(self) -> str:
        return "StealthWriter Humanizer"

    def screenshot(self, **_: object) -> None:
        pass

    def context(self) -> object:
        return SimpleNamespace(add_cookies=lambda _: None, cookies=lambda: [])


class _FakeLocator:
    def __init__(self, *, visible: bool = False, count: int = 0) -> None:
        self._visible = visible
        self._count = count

    def count(self) -> int:
        return self._count

    def first(self) -> "_FakeLocator":
        return self

    @property
    def first(self) -> "_FakeLocator":  # type: ignore[override]
        return self

    def is_visible(self, **_: object) -> bool:
        return self._visible

    def scroll_into_view_if_needed(self, **_: object) -> None:
        pass

    def click(self, **_: object) -> None:
        pass

    def fill(self, *_: object, **__: object) -> None:
        pass

    def focus(self, **_: object) -> None:
        pass

    def input_value(self, **_: object) -> str:
        return ""

    def inner_text(self, **_: object) -> str:
        return ""

    def get_attribute(self, *_: object, **__: object) -> str | None:
        return None

    def evaluate(self, *_: object, **__: object) -> object:
        return False

    def filter(self, **_: object) -> "_FakeLocator":
        return self

    def nth(self, _: int) -> "_FakeLocator":
        return self


class _FakeConnection:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.context = SimpleNamespace(add_cookies=lambda _: None, cookies=lambda: [], storage_state=lambda: {})
        pages_ns = SimpleNamespace()
        pages_ns.get_or_create = lambda name: page
        self.pages = pages_ns

    def get_or_create_page(self, name: str) -> _FakePage:
        return self._page


# ---------------------------------------------------------------------------
# 1. Config / isolated paths
# ---------------------------------------------------------------------------

class TestConfig:
    def test_default_paths_differ_from_production(self):
        cfg = TrainingBrowserConfig()
        assert "training" in cfg.user_data_dir
        assert "training" in cfg.session_dir
        assert cfg.cdp_port != 9222, "Training port must differ from production 9222"

    def test_defaults_from_env(self, monkeypatch):
        monkeypatch.setenv("TRAINING_CDP_PORT", "19999")
        monkeypatch.setenv("TRAINING_STEALTHWRITER_MODEL", "Legacy 5.1")
        monkeypatch.setenv("TRAINING_STEALTHWRITER_LEVEL", "6")
        cfg = TrainingBrowserConfig()
        assert cfg.cdp_port == 19999
        assert cfg.model == "Legacy 5.1"
        assert cfg.level == 6

    def test_user_data_dir_never_production(self):
        cfg = _make_config()
        assert "chrome_user_data" not in cfg.user_data_dir

    def test_session_dir_never_production(self):
        cfg = _make_config()
        # Must not be the production sessions directory
        assert cfg.session_dir != "browser_profiles/sessions"


# ---------------------------------------------------------------------------
# 2. Word count / TEXT_TOO_LONG
# ---------------------------------------------------------------------------

class TestWordLimit:
    def _make_provider_with_fake_start(self) -> StealthWriterTeacherProvider:
        cfg = _make_config(max_text_words=10)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True  # skip actual Chrome start
        return p

    def test_text_too_long_no_browser_call(self):
        p = self._make_provider_with_fake_start()
        with patch.object(p, "_page", side_effect=AssertionError("_page must not be called")):
            result = p.rewrite("word " * 11)
        assert result.error == "TEXT_TOO_LONG"
        assert result.success is False
        assert result.humanized_text is None

    def test_text_too_long_detail_has_word_count(self):
        p = self._make_provider_with_fake_start()
        result = p.rewrite("word " * 20)
        assert "20" in (result.error_detail or "")

    def test_empty_input(self):
        p = self._make_provider_with_fake_start()
        result = p.rewrite("   ")
        assert result.error == "EMPTY_INPUT"

    def test_within_limit_proceeds(self):
        cfg = _make_config(max_text_words=50, max_retries=1, timeout_s=5.0)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True
        with patch(
            "services.humanizer_training.teacher.stealthwriter_provider._humanize_once",
            return_value={"success": True, "humanized_text": "Rewritten fine."},
        ):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("word " * 10)
        # NOT TEXT_TOO_LONG — it proceeded to the provider
        assert result.error != "TEXT_TOO_LONG"


# ---------------------------------------------------------------------------
# 3. Successful rewrite
# ---------------------------------------------------------------------------

class TestSuccessfulRewrite:
    def test_returns_teacher_result_on_success(self):
        cfg = _make_config(max_retries=1, timeout_s=5.0)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True

        humanized = "This is the teacher-rewritten version of the text."

        with patch(
            "services.humanizer_training.teacher.stealthwriter_provider._humanize_once",
            return_value={
                "success": True,
                "humanized_text": humanized,
                "requested_model": "Legacy 5.1",
                "verified_model": "Legacy 5.1",
                "ui_model_label": "Ghost 5.1 Legacy",
                "requested_level": 8,
                "verified_level": 8,
                "selection_verified": True,
                "last_successful_stage": "LEVEL_VERIFIED",
            },
        ):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Some academic text about something scholarly.")

        assert result.success is True
        assert result.humanized_text == humanized
        assert result.provider == "stealthwriter_training"
        assert result.model == "Legacy 5.1"
        assert result.level == 8
        assert result.elapsed_seconds >= 0.0
        assert result.error is None
        assert result.meta["selection_verified"] is True
        assert result.meta["verified_model"] == "Legacy 5.1"
        assert result.meta["ui_model_label"] == "Ghost 5.1 Legacy"
        assert result.meta["verified_level"] == 8
        assert result.meta["last_successful_stage"] == "LEVEL_VERIFIED"

    def test_result_contains_no_user_id(self):
        result = TeacherResult(
            success=True, humanized_text="text",
            provider="stealthwriter_training",
            model="Legacy 5.1", level=8, elapsed_seconds=0.1,
        )
        # TeacherResult must not have user_id or credit fields
        assert not hasattr(result, "user_id")
        assert not hasattr(result, "credits")
        assert not hasattr(result, "wallet")


# ---------------------------------------------------------------------------
# 4. LOGIN_REQUIRED — no retry
# ---------------------------------------------------------------------------

class TestLoginRequired:
    def test_login_required_returns_immediately_no_retry(self):
        cfg = _make_config(max_retries=3, retry_delay_s=0.0)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True

        call_count = 0

        def fake_humanize_once(*_a, **_k):
            nonlocal call_count
            call_count += 1
            return {"success": False, "error": "LOGIN_REQUIRED"}

        with patch(
            "services.humanizer_training.teacher.stealthwriter_provider._humanize_once",
            side_effect=fake_humanize_once,
        ):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Some text about academic writing.")

        assert result.error == "LOGIN_REQUIRED"
        assert result.success is False
        assert call_count == 1, "LOGIN_REQUIRED must NOT be retried"


# ---------------------------------------------------------------------------
# 5. NO_CHANGE retry
# ---------------------------------------------------------------------------

class TestNoChangeRetry:
    def test_no_change_retries_up_to_max(self):
        cfg = _make_config(max_retries=3, retry_delay_s=0.0)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True

        call_count = 0

        def fake_once(*_a, **_k):
            nonlocal call_count
            call_count += 1
            return {"success": False, "error": "NO_CHANGE", "error_detail": "limit toast"}

        with patch(
            "services.humanizer_training.teacher.stealthwriter_provider._humanize_once",
            side_effect=fake_once,
        ):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Academic text for testing retry behavior.")

        assert result.error == "NO_CHANGE"
        assert call_count == cfg.max_retries

    def test_no_change_then_success(self):
        cfg = _make_config(max_retries=3, retry_delay_s=0.0)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True

        attempts = iter([
            {"success": False, "error": "NO_CHANGE"},
            {"success": True, "humanized_text": "Rewritten on second attempt."},
        ])

        with patch(
            "services.humanizer_training.teacher.stealthwriter_provider._humanize_once",
            side_effect=lambda *_a, **_k: next(attempts),
        ):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Text needing multiple attempts.")

        assert result.success is True
        assert result.humanized_text == "Rewritten on second attempt."


# ---------------------------------------------------------------------------
# 6. TIMEOUT retry
# ---------------------------------------------------------------------------

class TestTimeoutRetry:
    def test_timeout_retries_bounded(self):
        cfg = _make_config(max_retries=2, retry_delay_s=0.0)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True

        call_count = 0

        def fake_once(*_a, **_k):
            nonlocal call_count
            call_count += 1
            return {"success": False, "error": "TIMEOUT"}

        with patch(
            "services.humanizer_training.teacher.stealthwriter_provider._humanize_once",
            side_effect=fake_once,
        ):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Some long academic text content.")

        assert result.error == "TIMEOUT"
        assert call_count == cfg.max_retries
        assert result.success is False


# ---------------------------------------------------------------------------
# 7. Bounded retries on unknown error
# ---------------------------------------------------------------------------

class TestBoundedRetries:
    def test_exception_retried_bounded(self):
        cfg = _make_config(max_retries=2, retry_delay_s=0.0)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True

        call_count = 0

        def fake_once(*_a, **_k):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Unexpected Playwright crash")

        with patch(
            "services.humanizer_training.teacher.stealthwriter_provider._humanize_once",
            side_effect=fake_once,
        ):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Testing exception handling during rewrite.")

        assert result.error == "EXCEPTION"
        assert call_count == cfg.max_retries
        assert result.success is False

    def test_no_infinite_loop(self):
        """Verify max_retries is strictly enforced even with persistent errors."""
        cfg = _make_config(max_retries=5, retry_delay_s=0.0)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True

        count = 0

        def always_fail(*_a, **_k):
            nonlocal count
            count += 1
            return {"success": False, "error": "PASTE_FAILED"}

        with patch(
            "services.humanizer_training.teacher.stealthwriter_provider._humanize_once",
            side_effect=always_fail,
        ):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Any text at all.")

        assert count == 5
        assert result.success is False


# ---------------------------------------------------------------------------
# 8. Isolation: no production singletons
# ---------------------------------------------------------------------------

class TestIsolation:
    def test_provider_does_not_call_browser_service_instance(self):
        cfg = _make_config()
        with patch("services.browser.browser_service.BrowserService.instance") as mock_inst:
            mock_inst.side_effect = AssertionError("BrowserService.instance must never be called by training provider")
            p = StealthWriterTeacherProvider(cfg)
            # Just constructing the provider must not call BrowserService.instance
        mock_inst.assert_not_called()

    def test_provider_does_not_call_browser_service_reset_instance(self):
        cfg = _make_config()
        with patch("services.browser.browser_service.BrowserService.reset_instance") as mock_reset:
            mock_reset.side_effect = AssertionError("reset_instance must never be called")
            _ = StealthWriterTeacherProvider(cfg)
        mock_reset.assert_not_called()

    def test_no_job_manager_import(self):
        """stealthwriter_provider.py must not import JobManager."""
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [a.name for a in node.names]
                for name in names:
                    assert "JobManager" not in name, f"Training provider imports JobManager: {name}"

    def test_no_wallet_service_import(self):
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    assert "Wallet" not in alias.name, f"Training provider imports wallet code: {alias.name}"
                if isinstance(node, ast.ImportFrom):
                    assert "wallet" not in (node.module or "").lower(), \
                        f"Training provider imports from wallet module: {node.module}"

    def test_no_dataset_logger_import(self):
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "dataset_logger" not in (node.module or ""), \
                    f"Training provider imports dataset_logger"

    def test_no_app_import(self):
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        # "app" should not appear as an import target (allow comments)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name != "app", "Must not import app"
                elif isinstance(node, ast.ImportFrom):
                    assert (node.module or "") != "app", "Must not import from app"

    def test_no_browser_service_instance_in_source(self):
        """AST check: BrowserService must not be imported (only ChromeLauncher etc. are allowed)."""
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if "browser_service" in module:
                    for alias in node.names:
                        assert alias.name != "BrowserService", \
                            "Training provider must not import BrowserService"

    def test_provider_uses_training_port_not_9222(self):
        cfg = _make_config()
        assert cfg.cdp_port != 9222

    def test_provider_uses_training_user_data_dir(self):
        cfg = _make_config()
        assert "chrome_user_data" not in cfg.user_data_dir


# ---------------------------------------------------------------------------
# 9. Static safety check (source-level)
# ---------------------------------------------------------------------------

class TestStaticSafetyCheck:
    def test_forbidden_imports_absent(self):
        """AST-level check: none of the forbidden modules/classes are imported."""
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_modules = {"app", "dataset_logger"}
        forbidden_names = {"BrowserService", "JobManager", "WalletService"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert mod not in forbidden_modules, f"Forbidden module import: {mod}"
                for alias in node.names:
                    assert alias.name not in forbidden_names, \
                        f"Forbidden name imported: {alias.name}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_modules, \
                        f"Forbidden top-level import: {alias.name}"

    def test_no_import_from_app(self):
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("app"), \
                    f"Training provider imports from app: {node.module}"

    def test_no_production_browser_service_import(self):
        """Allowed: import ChromeLauncher / BrowserPool / SessionStore.
        Forbidden: import BrowserService (the singleton owner)."""
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if "browser_service" in module:
                    names = [alias.name for alias in node.names]
                    assert "BrowserService" not in names, \
                        "Training provider must not import BrowserService directly"


# ---------------------------------------------------------------------------
# 10. Isolated paths verified
# ---------------------------------------------------------------------------

class TestIsolatedPaths:
    def test_session_path_differs_from_production(self, tmp_path):
        cfg = _make_config(session_dir=str(tmp_path / "training_sessions"))
        p = StealthWriterTeacherProvider(cfg)
        # SessionStore should use training dir
        session_path = p._sessions._path("stealthwriter")
        assert "training" in str(session_path) or str(tmp_path) in str(session_path)

    def test_chrome_launcher_uses_training_port(self):
        cfg = _make_config(cdp_port=19333)
        p = StealthWriterTeacherProvider(cfg)
        assert p._launcher._port == 19333

    def test_chrome_launcher_uses_training_user_data_dir(self):
        cfg = _make_config(user_data_dir="browser_profiles/test_training_chrome")
        p = StealthWriterTeacherProvider(cfg)
        assert "test_training" in str(p._launcher._user_data_dir)


# ---------------------------------------------------------------------------
# 11. ProviderFactory supports "stealthwriter"
# ---------------------------------------------------------------------------

class TestProviderFactory:
    def test_factory_builds_bridge_for_stealthwriter(self):
        from services.humanizer_training.teacher.provider import ProviderFactory
        from services.humanizer_training.teacher.config import TeacherProviderConfig

        cfg = TeacherProviderConfig(
            provider_name="stealthwriter",
            model="Legacy 5.1",
            level=8,
            timeout_s=150,
            max_retries=3,
        )
        factory = ProviderFactory(config=cfg)
        provider = factory.build()
        from services.humanizer_training.teacher.provider import StealthWriterBridgeProvider
        assert isinstance(provider, StealthWriterBridgeProvider)

    def test_factory_mock_still_works(self):
        from services.humanizer_training.teacher.provider import ProviderFactory
        from services.humanizer_training.teacher.config import TeacherProviderConfig

        cfg = TeacherProviderConfig(provider_name="mock_teacher", model="mock-v1")
        factory = ProviderFactory(config=cfg)
        provider = factory.build()
        from services.humanizer_training.teacher.provider import MockTeacherProvider
        assert isinstance(provider, MockTeacherProvider)


# ---------------------------------------------------------------------------
# 12. Regression: level parsing in StealthWriterBridgeProvider
# ---------------------------------------------------------------------------

class TestLevelParsing:
    """Regression for ValueError: int('default')."""

    def test_parse_level_default_string(self):
        from services.humanizer_training.teacher.provider import _parse_level
        assert _parse_level("default") == 8

    def test_parse_level_none(self):
        from services.humanizer_training.teacher.provider import _parse_level
        assert _parse_level(None) == 8

    def test_parse_level_empty_string(self):
        from services.humanizer_training.teacher.provider import _parse_level
        assert _parse_level("") == 8

    def test_parse_level_numeric_string_8(self):
        from services.humanizer_training.teacher.provider import _parse_level
        assert _parse_level("8") == 8

    def test_parse_level_numeric_string_10(self):
        from services.humanizer_training.teacher.provider import _parse_level
        assert _parse_level("10") == 10

    def test_parse_level_int_passthrough(self):
        from services.humanizer_training.teacher.provider import _parse_level
        assert _parse_level(8) == 8

    def test_bridge_does_not_crash_with_default_level(self):
        """The exact scenario that caused the production ValueError."""
        from services.humanizer_training.teacher.config import TeacherProviderConfig
        from services.humanizer_training.teacher.provider import StealthWriterBridgeProvider

        cfg = TeacherProviderConfig(
            provider_name="stealthwriter",
            model="Legacy 5.1",
            level="default",
        )
        # Must not raise ValueError
        bridge = StealthWriterBridgeProvider(cfg)
        assert bridge._sw._cfg.level == 8

    def test_bridge_explicit_level_10(self):
        from services.humanizer_training.teacher.config import TeacherProviderConfig
        from services.humanizer_training.teacher.provider import StealthWriterBridgeProvider

        cfg = TeacherProviderConfig(
            provider_name="stealthwriter",
            model="Legacy 5.1",
            level="10",
        )
        bridge = StealthWriterBridgeProvider(cfg)
        assert bridge._sw._cfg.level == 10


class TestStealthWriterDefaults:
    def test_bridge_uses_legacy_default_model_for_generic_default(self):
        from services.humanizer_training.teacher.config import TeacherProviderConfig
        from services.humanizer_training.teacher.provider import StealthWriterBridgeProvider

        cfg = TeacherProviderConfig(
            provider_name="stealthwriter",
            model="mock-v1",
            level="default",
            timeout_s=45.0,
            extra={"explicit_model": False, "explicit_timeout": False},
        )
        bridge = StealthWriterBridgeProvider(cfg)
        assert bridge._sw._cfg.model == "Legacy 5.1"

    def test_bridge_keeps_explicit_legacy_model(self):
        from services.humanizer_training.teacher.config import TeacherProviderConfig
        from services.humanizer_training.teacher.provider import StealthWriterBridgeProvider

        cfg = TeacherProviderConfig(
            provider_name="stealthwriter",
            model="Legacy 5.1",
            level="default",
            extra={"explicit_model": True},
        )
        bridge = StealthWriterBridgeProvider(cfg)
        assert bridge._sw._cfg.model == "Legacy 5.1"

    def test_bridge_uses_default_timeout_150(self):
        from services.humanizer_training.teacher.config import TeacherProviderConfig
        from services.humanizer_training.teacher.provider import StealthWriterBridgeProvider

        cfg = TeacherProviderConfig(
            provider_name="stealthwriter",
            model="Legacy 5.1",
            level="default",
            timeout_s=45.0,
            extra={"explicit_timeout": False},
        )
        bridge = StealthWriterBridgeProvider(cfg)
        assert bridge._sw._cfg.timeout_s == 150.0

    def test_bridge_keeps_explicit_timeout_90(self):
        from services.humanizer_training.teacher.config import TeacherProviderConfig
        from services.humanizer_training.teacher.provider import StealthWriterBridgeProvider

        cfg = TeacherProviderConfig(
            provider_name="stealthwriter",
            model="Legacy 5.1",
            level="default",
            timeout_s=90.0,
            extra={"explicit_timeout": True},
        )
        bridge = StealthWriterBridgeProvider(cfg)
        assert bridge._sw._cfg.timeout_s == 90.0


# ---------------------------------------------------------------------------
# 13. Fail-closed model / level selection (no real browser)
# ---------------------------------------------------------------------------

_MOD = "services.humanizer_training.teacher.stealthwriter_provider"


class _RealisticStealthWriterModelMenu:
    """Mock DOM fixture matching current StealthWriter model menu.

    Top-level:
      Ghost 5.2 Mini
      Ghost 5.2 Pro
      Legacy ▼

    Expanded Legacy:
      Ghost 5.1 Legacy
      Ghost 4.6 Legacy
    """

    TOP_LEVEL = ("Ghost 5.2 Mini", "Ghost 5.2 Pro", "Legacy")
    LEGACY_OPTIONS = ("Ghost 5.1 Legacy", "Ghost 4.6 Legacy")

    def __init__(
        self,
        *,
        selected: str = "Ghost 5.2 Mini",
        legacy_expanded: bool = False,
        include_ghost_51_legacy: bool = True,
    ) -> None:
        self.selected = selected
        self.legacy_expanded = legacy_expanded
        self.include_ghost_51_legacy = include_ghost_51_legacy
        self.humanize_clicked = False
        self.clicks: list[str] = []

    def visible_options(self) -> list[str]:
        opts = list(self.TOP_LEVEL)
        if self.legacy_expanded:
            legacy = list(self.LEGACY_OPTIONS)
            if not self.include_ghost_51_legacy:
                legacy = [x for x in legacy if x != "Ghost 5.1 Legacy"]
            opts.extend(legacy)
        return opts

    def click_label(self, label: str) -> bool:
        norm = re.sub(r"\s+", " ", label).strip()
        self.clicks.append(norm)
        if re.fullmatch(r"Legacy([ ▼▾]*)?", norm, flags=re.I):
            self.legacy_expanded = True
            return True
        visible = self.visible_options()
        # Exact match only among currently visible options.
        for opt in visible:
            if opt.lower() == norm.lower():
                if opt == "Legacy":
                    self.legacy_expanded = True
                    return True
                self.selected = opt
                return True
        return False


class TestModelMatchHelpers:
    def test_a_ghost_51_legacy_maps_to_legacy_51(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            _canonical_model_name,
            _model_matches_desired,
        )

        assert _canonical_model_name("Ghost 5.1 Legacy") == "Legacy 5.1"
        assert _model_matches_desired("Ghost 5.1 Legacy", "Legacy 5.1") is True
        assert _model_matches_desired("Legacy 5.1", "Legacy 5.1") is True

    def test_b_ghost_46_legacy_fails(self):
        from services.humanizer_training.teacher.stealthwriter_provider import _model_matches_desired

        assert _model_matches_desired("Ghost 4.6 Legacy", "Legacy 5.1") is False

    def test_c_ghost_52_mini_fails(self):
        from services.humanizer_training.teacher.stealthwriter_provider import _model_matches_desired

        assert _model_matches_desired("Ghost 5.2 Mini", "Legacy 5.1") is False
        assert _model_matches_desired("Ghost 5.2 Pro", "Legacy 5.1") is False
        assert _model_matches_desired("Ghost 5.1", "Legacy 5.1") is False


class TestVisibleModelLabelSelectedState:
    """Live-DOM selected-state verification (no browser). Mini before Legacy in all fixtures."""

    @staticmethod
    def _closed_row(
        *,
        mini_selected: bool = False,
        pro_selected: bool = False,
        legacy_classes: list[str] | None = None,
    ) -> list[dict]:
        # DOM order: Mini, Pro, then Legacy (reproduces old first-match bug if order is used).
        return [
            {
                "text": "Ghost 5.2 Mini",
                "role": "tab",
                "aria_selected": mini_selected,
                "class_list": ["data-active:bg-background", "data-active:shadow-sm"],
            },
            {
                "text": "Ghost 5.2 Pro",
                "role": "tab",
                "aria_selected": pro_selected,
                "class_list": ["data-active:bg-background", "data-active:shadow-sm"],
            },
            {
                "text": "Ghost 5.1 Legacy",
                "aria_haspopup": "menu",
                "class_list": list(legacy_classes or []),
            },
        ]

    def test_a_legacy_selected_via_exact_class_tokens(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            _pick_model_label_from_candidates,
        )

        label = _pick_model_label_from_candidates(
            self._closed_row(
                legacy_classes=["bg-background", "text-foreground", "shadow-sm"],
            )
        )
        assert label == "Ghost 5.1 Legacy"

    def test_b_mini_aria_selected_true(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            _pick_model_label_from_candidates,
        )

        label = _pick_model_label_from_candidates(
            self._closed_row(mini_selected=True, legacy_classes=["text-foreground"])
        )
        assert label == "Ghost 5.2 Mini"

    def test_c_pro_aria_selected_true(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            _pick_model_label_from_candidates,
        )

        label = _pick_model_label_from_candidates(
            self._closed_row(pro_selected=True, legacy_classes=["text-foreground"])
        )
        assert label == "Ghost 5.2 Pro"

    def test_d_data_active_variant_tokens_do_not_select_legacy(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            _pick_model_label_from_candidates,
        )

        label = _pick_model_label_from_candidates(
            self._closed_row(
                legacy_classes=["data-active:bg-background", "data-active:shadow-sm"],
            )
        )
        assert label == ""

    def test_e_legacy_missing_shadow_sm_not_selected(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            _pick_model_label_from_candidates,
        )

        label = _pick_model_label_from_candidates(
            self._closed_row(legacy_classes=["bg-background", "text-foreground"])
        )
        assert label == ""

    def test_f_legacy_missing_bg_background_not_selected(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            _pick_model_label_from_candidates,
        )

        label = _pick_model_label_from_candidates(
            self._closed_row(legacy_classes=["text-foreground", "shadow-sm"])
        )
        assert label == ""

    def test_g_canonical_matcher_rejects_non_legacy51(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            _model_matches_desired,
        )

        assert _model_matches_desired("Ghost 5.2 Mini", "Legacy 5.1") is False
        assert _model_matches_desired("Ghost 5.2 Pro", "Legacy 5.1") is False
        assert _model_matches_desired("Ghost 4.6 Legacy", "Legacy 5.1") is False
        assert _model_matches_desired("Ghost 5.1", "Legacy 5.1") is False
        assert _model_matches_desired("Ghost 5.1 Legacy", "Legacy 5.1") is True

    def test_h_mini_before_legacy_still_returns_legacy_when_selected(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            _pick_model_label_from_candidates,
        )

        # Explicit old bug: Mini is first in DOM order but Legacy is actually selected.
        candidates = self._closed_row(
            legacy_classes=["bg-background", "text-foreground", "shadow-sm"],
        )
        assert candidates[0]["text"] == "Ghost 5.2 Mini"
        label = _pick_model_label_from_candidates(candidates)
        assert label == "Ghost 5.1 Legacy"

    def test_visible_model_label_uses_page_evaluate_js(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            _VISIBLE_MODEL_LABEL_JS,
            _visible_model_label,
        )

        page = MagicMock()
        page.evaluate.return_value = "Ghost 5.1 Legacy"
        assert _visible_model_label(page) == "Ghost 5.1 Legacy"
        page.evaluate.assert_called_once_with(_VISIBLE_MODEL_LABEL_JS)
        assert 'button[role="tab"][aria-selected="true"]' in _VISIBLE_MODEL_LABEL_JS
        assert "classList.contains('bg-background')" in _VISIBLE_MODEL_LABEL_JS
        assert "classList.contains('shadow-sm')" in _VISIBLE_MODEL_LABEL_JS
        assert "selectedScore" not in _VISIBLE_MODEL_LABEL_JS
        # Must not use broad substring class heuristics / first-match fallback.
        assert "candidates[0]" not in _VISIBLE_MODEL_LABEL_JS
        assert r"\bbg-background\b" not in _VISIBLE_MODEL_LABEL_JS


class TestFailClosedModelSelection:
    def test_ghost_51_legacy_already_selected_passes(self):
        from services.humanizer_training.teacher.stealthwriter_provider import _ensure_model_selected

        page = MagicMock()
        with patch(f"{_MOD}._visible_model_label", return_value="Ghost 5.1 Legacy"):
            with patch(f"{_MOD}._open_model_selector") as open_sel:
                verified = _ensure_model_selected(page, "Legacy 5.1")
        assert verified == "Ghost 5.1 Legacy"
        open_sel.assert_not_called()

    def test_d_legacy_group_collapsed_expand_select_ghost_51_legacy(self):
        from services.humanizer_training.teacher.stealthwriter_provider import _ensure_model_selected

        menu = _RealisticStealthWriterModelMenu(selected="Ghost 5.2 Mini", legacy_expanded=False)
        page = MagicMock()

        def click_first(_page, patterns):
            for pattern in patterns:
                for opt in menu.visible_options():
                    if pattern.search(opt):
                        return menu.click_label(opt)
            return False

        def visible(_page):
            return menu.selected

        with patch(f"{_MOD}._visible_model_label", side_effect=visible):
            with patch(f"{_MOD}._open_model_selector", return_value=True):
                with patch(f"{_MOD}._click_first_visible", side_effect=click_first):
                    with patch(f"{_MOD}._dismiss_ui_overlays"):
                        verified = _ensure_model_selected(page, "Legacy 5.1")
        assert verified == "Ghost 5.1 Legacy"
        assert menu.selected == "Ghost 5.1 Legacy"
        assert "Legacy" in menu.clicks
        assert "Ghost 5.1 Legacy" in menu.clicks

    def test_e_ghost_51_legacy_missing_fails_no_humanize(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            SelectionFailed,
            _ensure_model_selected,
            _humanize_once,
        )

        menu = _RealisticStealthWriterModelMenu(
            selected="Ghost 5.2 Mini",
            legacy_expanded=False,
            include_ghost_51_legacy=False,
        )
        page = MagicMock()
        page.url = "https://stealthwriter.ai/dashboard/humanizer"
        humanize_clicks: list[bool] = []

        def click_first(_page, patterns):
            for pattern in patterns:
                for opt in menu.visible_options():
                    if pattern.search(opt):
                        return menu.click_label(opt)
            return False

        with patch(f"{_MOD}._visible_model_label", side_effect=lambda _p: menu.selected):
            with patch(f"{_MOD}._open_model_selector", return_value=True):
                with patch(f"{_MOD}._click_first_visible", side_effect=click_first):
                    with patch(f"{_MOD}._dismiss_ui_overlays"):
                        with pytest.raises(SelectionFailed) as exc:
                            _ensure_model_selected(page, "Legacy 5.1")
        assert exc.value.code == "MODEL_SELECTION_FAILED"
        assert "Ghost 5.1 Legacy" in (exc.value.detail or "")

        with patch(f"{_MOD}._ensure_model_selected", side_effect=SelectionFailed("MODEL_SELECTION_FAILED", "missing")):
            with patch(f"{_MOD}._click_humanize_button", side_effect=lambda *_: humanize_clicks.append(True)):
                result = _humanize_once(page, "Some academic source text here.", "Legacy 5.1", 8, 5.0)
        assert result["error"] == "MODEL_SELECTION_FAILED"
        assert humanize_clicks == []

    def test_ghost_remains_selected_fails_no_humanize(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            SelectionFailed,
            _ensure_model_selected,
            _humanize_once,
        )

        page = MagicMock()
        page.url = "https://stealthwriter.ai/dashboard/humanizer"
        humanize_clicks: list[bool] = []

        with patch(f"{_MOD}._visible_model_label", return_value="Ghost 5.2 Mini"):
            with patch(f"{_MOD}._open_model_selector", return_value=True):
                with patch(f"{_MOD}._expand_legacy_group", return_value=True):
                    with patch(f"{_MOD}._select_legacy_51_option", return_value=True):
                        with pytest.raises(SelectionFailed) as exc:
                            _ensure_model_selected(page, "Legacy 5.1")
        assert exc.value.code == "MODEL_SELECTION_FAILED"
        assert "Ghost 5.2 Mini" in (exc.value.detail or "")

        with patch(f"{_MOD}._ensure_model_selected", side_effect=SelectionFailed("MODEL_SELECTION_FAILED", "ghost")):
            with patch(f"{_MOD}._click_humanize_button", side_effect=lambda *_: humanize_clicks.append(True)):
                result = _humanize_once(page, "Some academic source text here.", "Legacy 5.1", 8, 5.0)
        assert result["error"] == "MODEL_SELECTION_FAILED"
        assert humanize_clicks == []

    def test_ghost_46_legacy_never_accepted_as_legacy_51(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            SelectionFailed,
            _ensure_model_selected,
        )

        page = MagicMock()
        with patch(f"{_MOD}._visible_model_label", return_value="Ghost 4.6 Legacy"):
            with patch(f"{_MOD}._open_model_selector", return_value=True):
                with patch(f"{_MOD}._expand_legacy_group", return_value=True):
                    with patch(f"{_MOD}._select_legacy_51_option", return_value=True):
                        # After "select", UI still Ghost 4.6 Legacy → fail closed
                        with pytest.raises(SelectionFailed) as exc:
                            _ensure_model_selected(page, "Legacy 5.1")
        assert exc.value.code == "MODEL_SELECTION_FAILED"


class TestFailClosedLevelSelection:
    def test_g_level_8_already_selected_passes(self):
        from services.humanizer_training.teacher.stealthwriter_provider import _ensure_rewrite_level

        page = MagicMock()
        with patch(f"{_MOD}._visible_selected_level", return_value=8):
            with patch(f"{_MOD}._click_level_chip") as click:
                assert _ensure_rewrite_level(page, 8) == 8
        click.assert_not_called()

    def test_f_level_7_remains_selected_fails_no_humanize(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            SelectionFailed,
            _ensure_rewrite_level,
            _humanize_once,
        )

        page = MagicMock()
        page.url = "https://stealthwriter.ai/dashboard/humanizer"
        humanize_clicks: list[bool] = []

        with patch(f"{_MOD}._visible_selected_level", side_effect=[7, 7]):
            with patch(f"{_MOD}._click_level_chip", return_value=True):
                with pytest.raises(SelectionFailed) as exc:
                    _ensure_rewrite_level(page, 8)
        assert exc.value.code == "LEVEL_SELECTION_FAILED"

        with patch(f"{_MOD}._ensure_model_selected", return_value="Ghost 5.1 Legacy"):
            with patch(
                f"{_MOD}._ensure_rewrite_level",
                side_effect=SelectionFailed("LEVEL_SELECTION_FAILED", "wanted=8 got=7"),
            ):
                with patch(f"{_MOD}._click_humanize_button", side_effect=lambda *_: humanize_clicks.append(True)):
                    result = _humanize_once(page, "Some academic source text here.", "Legacy 5.1", 8, 5.0)
        assert result["error"] == "LEVEL_SELECTION_FAILED"
        assert humanize_clicks == []

    def test_unverifiable_level_fails_closed(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            SelectionFailed,
            _ensure_rewrite_level,
            _verify_selection_gate,
        )

        page = MagicMock()
        with patch(f"{_MOD}._visible_selected_level", side_effect=[None, None]):
            with patch(f"{_MOD}._click_level_chip", return_value=True):
                with pytest.raises(SelectionFailed) as exc:
                    _ensure_rewrite_level(page, 8)
        assert exc.value.code == "LEVEL_SELECTION_FAILED"

        with patch(f"{_MOD}._visible_model_label", return_value="Ghost 5.1 Legacy"):
            with patch(f"{_MOD}._visible_selected_level", return_value=None):
                with pytest.raises(SelectionFailed) as gate_exc:
                    _verify_selection_gate(page, "Legacy 5.1", 8)
        assert gate_exc.value.code == "LEVEL_SELECTION_FAILED"


class TestSelectionMetadataAndGate:
    def test_f_metadata_records_requested_verified_and_ui_label(self):
        from services.humanizer_training.teacher.stealthwriter_provider import _selection_meta

        meta = _selection_meta(
            requested_model="Legacy 5.1",
            ui_model_label="Ghost 5.1 Legacy",
            requested_level=8,
            verified_level=8,
            last_successful_stage="LEVEL_VERIFIED",
        )
        assert meta == {
            "requested_model": "Legacy 5.1",
            "verified_model": "Legacy 5.1",
            "ui_model_label": "Ghost 5.1 Legacy",
            "requested_level": 8,
            "verified_level": 8,
            "selection_verified": True,
            "last_successful_stage": "LEVEL_VERIFIED",
        }

        cfg = _make_config(max_retries=1)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True
        with patch(
            f"{_MOD}._humanize_once",
            return_value={
                "success": True,
                "humanized_text": "Rewritten output for metadata check.",
                **meta,
            },
        ):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Academic text for metadata verification path.")
        assert result.meta == meta

    def test_h_selection_verified_false_without_dom_fields(self):
        cfg = _make_config(max_retries=1)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True
        with patch(
            f"{_MOD}._humanize_once",
            return_value={"success": True, "humanized_text": "text without verification keys"},
        ):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Academic text missing verification keys.")
        assert result.meta["selection_verified"] is False

    def test_pre_humanize_gate_blocks_click(self):
        from services.humanizer_training.teacher.stealthwriter_provider import _humanize_once

        page = MagicMock()
        page.url = "https://stealthwriter.ai/dashboard/humanizer"
        humanize_clicks: list[bool] = []

        with patch(f"{_MOD}._ensure_model_selected", return_value="Ghost 5.1 Legacy"):
            with patch(f"{_MOD}._ensure_rewrite_level", return_value=8):
                with patch(f"{_MOD}._find_input_textarea", return_value=MagicMock()):
                    with patch(f"{_MOD}._paste_into_input"):
                        with patch(
                            f"{_MOD}._verify_selection_gate",
                            side_effect=__import__(
                                "services.humanizer_training.teacher.stealthwriter_provider",
                                fromlist=["SelectionFailed"],
                            ).SelectionFailed("MODEL_SELECTION_FAILED", "gate"),
                        ):
                            with patch(
                                f"{_MOD}._click_humanize_button",
                                side_effect=lambda *_: humanize_clicks.append(True),
                            ):
                                result = _humanize_once(
                                    page, "Some academic source text here.", "Legacy 5.1", 8, 5.0
                                )
        assert result["error"] == "MODEL_SELECTION_FAILED"
        assert humanize_clicks == []

    def test_selection_failure_does_not_retry(self):
        cfg = _make_config(max_retries=3, retry_delay_s=0.0)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True
        calls = {"n": 0}

        def once(*_a, **_k):
            calls["n"] += 1
            return {"success": False, "error": "MODEL_SELECTION_FAILED", "error_detail": "ghost"}

        with patch(f"{_MOD}._humanize_once", side_effect=once):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Academic text should not retry selection failures.")
        assert result.error == "MODEL_SELECTION_FAILED"
        assert calls["n"] == 1
        assert result.meta["selection_verified"] is False


class TestIsolationExtended:
    def test_i_provider_source_has_no_browser_service_instance(self):
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        assert "BrowserService.instance" not in src
        assert "BrowserService.reset_instance" not in src

    def test_j_no_job_manager_in_source(self):
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    assert "JobManager" not in alias.name
                if isinstance(node, ast.ImportFrom):
                    assert "jobs" not in (node.module or "")
                    assert not (node.module or "").endswith("providers.stealthwriter")
        assert "BrowserService.instance()" not in src
        assert "from services.browser.providers.stealthwriter" not in src
        assert "import services.browser.providers.stealthwriter" not in src


# ---------------------------------------------------------------------------
# 14. Observability / fail-closed diagnostics (no real browser)
# ---------------------------------------------------------------------------


class TestObservabilitySelectionFailures:
    def test_a_model_click_ok_verification_fails(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            SelectionFailed,
            _ensure_model_selected,
        )

        page = MagicMock()
        with patch(f"{_MOD}._visible_model_label", return_value="Ghost 5.2 Mini"):
            with patch(f"{_MOD}._open_model_selector", return_value=True):
                with patch(f"{_MOD}._expand_legacy_group", return_value=True):
                    with patch(f"{_MOD}._select_legacy_51_option", return_value=True):
                        with pytest.raises(SelectionFailed) as exc:
                            _ensure_model_selected(page, "Legacy 5.1")
        assert exc.value.code == "MODEL_SELECTION_FAILED"
        assert exc.value.failed_stage == "MODEL_VERIFICATION"

    def test_b_level_click_ok_verification_fails(self):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            SelectionFailed,
            _ensure_rewrite_level,
        )

        page = MagicMock()
        with patch(f"{_MOD}._visible_selected_level", side_effect=[7, 7]):
            with patch(f"{_MOD}._click_level_chip", return_value=True):
                with pytest.raises(SelectionFailed) as exc:
                    _ensure_rewrite_level(page, 8)
        assert exc.value.code == "LEVEL_SELECTION_FAILED"
        assert exc.value.failed_stage == "LEVEL_VERIFICATION"

    def test_c_model_selection_failed_not_retried(self):
        cfg = _make_config(max_retries=3, retry_delay_s=0.0)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True
        calls = {"n": 0}

        def once(*_a, **_k):
            calls["n"] += 1
            return {
                "success": False,
                "error": "MODEL_SELECTION_FAILED",
                "error_detail": "verify failed",
                "retryable": False,
                "failed_stage": "MODEL_VERIFICATION",
                "last_successful_stage": "MODEL_OPTION_CLICKED",
                "visible_model_label": "Ghost 5.2 Mini",
                "requested_model": "Legacy 5.1",
                "requested_level": 8,
            }

        with patch(f"{_MOD}._humanize_once", side_effect=once):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Academic text for non-retry model failure.", document_id="doc-obs-1")
        assert result.error == "MODEL_SELECTION_FAILED"
        assert calls["n"] == 1
        assert result.meta["failed_stage"] == "MODEL_VERIFICATION"
        assert result.meta["retryable"] is False

    def test_d_level_selection_failed_not_retried(self):
        cfg = _make_config(max_retries=3, retry_delay_s=0.0)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True
        calls = {"n": 0}

        def once(*_a, **_k):
            calls["n"] += 1
            return {
                "success": False,
                "error": "LEVEL_SELECTION_FAILED",
                "error_detail": "wanted=8 got=7",
                "retryable": False,
                "failed_stage": "LEVEL_VERIFICATION",
                "last_successful_stage": "LEVEL_OPTION_CLICKED",
                "visible_level": 7,
                "requested_model": "Legacy 5.1",
                "requested_level": 8,
            }

        with patch(f"{_MOD}._humanize_once", side_effect=once):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Academic text for non-retry level failure.", document_id="doc-obs-2")
        assert result.error == "LEVEL_SELECTION_FAILED"
        assert calls["n"] == 1
        assert result.meta["failed_stage"] == "LEVEL_VERIFICATION"

    def test_h_successful_run_selection_verified(self):
        cfg = _make_config(max_retries=1)
        p = StealthWriterTeacherProvider(cfg)
        p._started = True
        with patch(
            f"{_MOD}._humanize_once",
            return_value={
                "success": True,
                "humanized_text": "Rewritten verified output.",
                "requested_model": "Legacy 5.1",
                "verified_model": "Legacy 5.1",
                "ui_model_label": "Ghost 5.1 Legacy",
                "requested_level": 8,
                "verified_level": 8,
                "selection_verified": True,
                "last_successful_stage": "LEVEL_VERIFIED",
            },
        ):
            with patch.object(p, "_page", return_value=MagicMock()):
                result = p.rewrite("Academic text success path.")
        assert result.meta["selection_verified"] is True
        assert result.meta["last_successful_stage"] == "LEVEL_VERIFIED"

    def test_i_screenshot_path_when_debug_enabled(self, tmp_path):
        from services.humanizer_training.teacher.stealthwriter_provider import (
            SelectionFailed,
            _selection_failure_payload,
            RunTrace,
        )

        page = MagicMock()
        page.url = "https://stealthwriter.ai/dashboard/humanizer"
        page.screenshot = MagicMock()
        trace = RunTrace()
        trace.mark("MODEL_OPTION_CLICKED")
        with patch(f"{_MOD}._visible_model_label", return_value="Ghost 5.2 Mini"):
            with patch(f"{_MOD}._visible_selected_level", return_value=8):
                payload = _selection_failure_payload(
                    page,
                    model="Legacy 5.1",
                    level=8,
                    trace=trace,
                    exc=SelectionFailed(
                        "MODEL_SELECTION_FAILED",
                        "verify failed",
                        failed_stage="MODEL_VERIFICATION",
                    ),
                    debug_screenshots=True,
                    debug_dir=str(tmp_path / "debug"),
                    document_id="doc-shot-1",
                )
        assert payload["screenshot_path"]
        assert payload["screenshot_path"].endswith(".png")
        assert "MODEL_SELECTION_FAILED" in payload["screenshot_path"]
        page.screenshot.assert_called_once()


class TestDocumentCollectorFailurePersistence:
    def test_e_f_g_j_failure_jsonl_created_with_stage_and_model(self, tmp_path):
        from services.humanizer_training.teacher.documents.collector import TeacherDocumentCollector
        from services.humanizer_training.teacher.documents.schema import DocumentCollectorConfig
        from services.humanizer_training.teacher.provider import TeacherProviderError

        class _FailProvider:
            def __init__(self) -> None:
                self.calls = 0

            def rewrite(self, source_text: str, **kwargs):
                self.calls += 1
                raise TeacherProviderError(
                    "MODEL_SELECTION_FAILED",
                    "wanted Legacy 5.1 got Ghost 5.2 Mini",
                    meta={
                        "requested_model": "Legacy 5.1",
                        "requested_level": 8,
                        "visible_model_label": "Ghost 5.2 Mini",
                        "visible_level": 8,
                        "failed_stage": "MODEL_VERIFICATION",
                        "last_successful_stage": "MODEL_OPTION_CLICKED",
                        "current_url": "https://stealthwriter.ai/dashboard/humanizer",
                        "retryable": False,
                        "source_text": "SHOULD_NOT_PERSIST",
                    },
                    retryable=False,
                )

        provider = _FailProvider()
        cfg = DocumentCollectorConfig(
            count=1,
            seed=303,
            output_dir=str(tmp_path / "out"),
            dry_run=False,
            max_retries=3,
            model="Legacy 5.1",
            level=8,
        )
        with patch(
            "services.humanizer_training.teacher.documents.collector.generate_documents"
        ) as gen:
            from services.humanizer_training.teacher.documents.schema import SyntheticDocument
            from types import SimpleNamespace

            doc = SyntheticDocument(
                document_id="doc-fail-1",
                source_text="## Intro\n" + ("word " * 200),
                domain="business",
                document_type="explanation",
                language="en",
                seed=303,
                word_count=200,
                body_word_count=200,
                references_present=False,
                references_word_count=0,
                section_count=1,
                section_titles=["Intro"],
                length_bucket="3000_4500",
            )
            plan = SimpleNamespace(section_count_histogram={"1": 1})
            gen.return_value = ([doc], plan)
            with patch(
                "services.humanizer_training.teacher.documents.collector.summarize_document_plan",
                return_value={"document_types": {"explanation": 1}},
            ):
                result = TeacherDocumentCollector(cfg, provider=provider).run()

        assert provider.calls == 1  # C/D: no retry for MODEL_SELECTION_FAILED
        failures_path = tmp_path / "out" / "failures.jsonl"
        assert failures_path.exists()
        rows = [json.loads(line) for line in failures_path.read_text().splitlines() if line.strip()]
        assert len(rows) == 1
        row = rows[0]
        assert row["error_code"] == "MODEL_SELECTION_FAILED"
        assert row["failed_stage"] == "MODEL_VERIFICATION"
        assert row["requested_model"] == "Legacy 5.1"
        assert row["visible_model_label"] == "Ghost 5.2 Mini"
        assert row["document_id"] == "doc-fail-1"
        assert "source_text" not in row
        assert "SHOULD_NOT_PERSIST" not in json.dumps(row)
        assert result.manifest["failure_count"] == 1
        assert result.manifest["failure_codes"]["MODEL_SELECTION_FAILED"] == 1
        assert result.manifest["failure_stages"]["MODEL_VERIFICATION"] == 1
        assert result.manifest["provider_error_count"] == 1

    def test_k_production_imports_absent_in_collector(self):
        src = (
            Path(__file__).resolve().parent.parent
            / "services/humanizer_training/teacher/documents/collector.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "browser_service" not in mod
                assert not mod.endswith("providers.stealthwriter")
                for alias in node.names:
                    assert alias.name not in {"BrowserService", "JobManager", "WalletService"}
