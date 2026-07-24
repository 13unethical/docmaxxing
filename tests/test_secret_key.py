"""SECRET_KEY startup enforcement."""

from __future__ import annotations

import pytest


def test_require_strong_secret_key_rejects_weak(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "change-me-to-a-long-random-string-6f2b9c1a4d8e7f0a3b5c9d2e")
    # Import the helper by executing the same rules inline via app module reload is heavy;
    # call the validation logic from a fresh import path.
    import importlib
    import sys

    # Ensure a clean import of app would SystemExit — test the function by copying criteria
    # through importing after patching. Prefer unit-testing via exec of the helper.
    from pathlib import Path

    # Load only the validation by reading from app after setting env and importing a tiny copy.
    # Direct approach: define expected behavior matching app._require_strong_secret_key
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    # Import app module would boot Flask — too heavy / needs strong key.
    # Replicate call: import app with strong key first then call helper.
    monkeypatch.setenv(
        "SECRET_KEY",
        "wVRVvkbgAyKnE6hEbbWbE6H3wq0QEBSN95rrRDqEK6qRBoMzRnjnQhj1V95xJz7M",
    )
    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_module

    with pytest.raises(SystemExit):
        monkeypatch.setenv("SECRET_KEY", "short")
        app_module._require_strong_secret_key()

    with pytest.raises(SystemExit):
        monkeypatch.setenv("SECRET_KEY", "change-me-" + ("x" * 40))
        app_module._require_strong_secret_key()

    monkeypatch.setenv(
        "SECRET_KEY",
        "wVRVvkbgAyKnE6hEbbWbE6H3wq0QEBSN95rrRDqEK6qRBoMzRnjnQhj1V95xJz7M",
    )
    assert len(app_module._require_strong_secret_key()) >= 32
