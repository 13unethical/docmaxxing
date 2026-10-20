from __future__ import annotations

from services.browser.health_monitor import HealthMonitor


def test_session_alerts_on_down_and_restore(monkeypatch):
    down_calls: list[dict] = []
    restore_calls: list[dict] = []

    def _down(*, current_url, active_jobs):  # noqa: ANN001
        down_calls.append({"url": current_url, "jobs": active_jobs})
        return True

    def _restore(*, current_url):  # noqa: ANN001
        restore_calls.append({"url": current_url})
        return True

    monkeypatch.setattr("services.alerts.telegram_alerts.notify_stealthwriter_session_down", _down)
    monkeypatch.setattr("services.alerts.telegram_alerts.notify_stealthwriter_session_restored", _restore)

    monitor = HealthMonitor(service=None, job_manager=None, metrics=None, worker=None, interval=30)
    monitor._handle_stealthwriter_session_alerts(  # noqa: SLF001
        logged_in=False,
        current_url="https://stealthwriter.ai/sign-in",
        active_jobs=0,
    )
    monitor._handle_stealthwriter_session_alerts(  # noqa: SLF001
        logged_in=False,
        current_url="https://stealthwriter.ai/sign-in",
        active_jobs=0,
    )
    monitor._handle_stealthwriter_session_alerts(  # noqa: SLF001
        logged_in=True,
        current_url="https://stealthwriter.ai/dashboard",
        active_jobs=0,
    )

    assert len(down_calls) == 1
    assert len(restore_calls) == 1


class _FakeWorker:
    def __init__(self) -> None:
        self.calls = 0

    def submit(self, fn, timeout=None):  # noqa: ANN001
        self.calls += 1
        return fn()


class _FakeProvider:
    def __init__(self, logged_in: bool) -> None:
        self.logged_in = logged_in
        self.status_calls = 0

    def status(self):
        self.status_calls += 1
        return {"logged_in": self.logged_in, "current_url": "https://stealthwriter.ai/dashboard"}


class _FakeService:
    def __init__(self, provider) -> None:  # noqa: ANN001
        self._provider = provider

    def providers(self):
        return {"stealthwriter": self._provider}


def test_keepalive_runs_once_per_interval():
    provider = _FakeProvider(logged_in=True)
    worker = _FakeWorker()
    monitor = HealthMonitor(service=_FakeService(provider), job_manager=None, metrics=None, worker=worker)

    first = monitor._stealthwriter_keepalive(active_jobs=0)  # noqa: SLF001
    second = monitor._stealthwriter_keepalive(active_jobs=0)  # noqa: SLF001

    assert first["logged_in"] is True
    assert second == {}
    assert provider.status_calls == 1


def test_keepalive_skipped_while_jobs_active():
    provider = _FakeProvider(logged_in=True)
    monitor = HealthMonitor(service=_FakeService(provider), job_manager=None, metrics=None, worker=_FakeWorker())

    assert monitor._stealthwriter_keepalive(active_jobs=2) == {}  # noqa: SLF001
    assert provider.status_calls == 0
    assert monitor._stealthwriter_keepalive(active_jobs=0)["logged_in"] is True  # noqa: SLF001


def test_keepalive_disabled_by_env(monkeypatch):
    monkeypatch.setenv("STEALTHWRITER_KEEPALIVE_HOURS", "0")
    provider = _FakeProvider(logged_in=True)
    monitor = HealthMonitor(service=_FakeService(provider), job_manager=None, metrics=None, worker=_FakeWorker())

    assert monitor._stealthwriter_keepalive(active_jobs=0) == {}  # noqa: SLF001
    assert provider.status_calls == 0

