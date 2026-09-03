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

