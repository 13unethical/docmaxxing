from __future__ import annotations

from services.alerts import telegram_alerts as alerts


def test_send_telegram_alert_deduplicates_with_cooldown(monkeypatch):
    sent: list[dict] = []

    class _Resp:
        ok = True
        status_code = 200
        text = "ok"

    def _fake_post(url, json, timeout):  # noqa: ANN001
        sent.append({"url": url, "json": json, "timeout": timeout})
        return _Resp()

    monkeypatch.setenv("TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("CHAT_ID", "123")
    monkeypatch.setattr(alerts.requests, "post", _fake_post)
    monkeypatch.setattr(alerts, "_LAST_SENT", {})

    assert alerts.send_telegram_alert("hello", key="k", cooldown_sec=60) is True
    assert alerts.send_telegram_alert("hello", key="k", cooldown_sec=60) is False
    assert len(sent) == 1


def test_alerts_reuse_support_bot_and_chat(monkeypatch):
    """Alerts must go through the same bot/chat as support chat by default."""
    sent: list[dict] = []

    class _Resp:
        ok = True
        status_code = 200
        text = "ok"

    monkeypatch.setenv("TELEGRAM_TOKEN", "support-bot-token")
    monkeypatch.setenv("CHAT_ID", "555")
    monkeypatch.delenv("TELEGRAM_ALERT_CHAT_ID", raising=False)
    monkeypatch.setattr(
        alerts.requests,
        "post",
        lambda url, json, timeout: (sent.append({"url": url, "json": json}), _Resp())[1],
    )
    monkeypatch.setattr(alerts, "_LAST_SENT", {})

    assert alerts.notify_stealthwriter_session_down(current_url="x", active_jobs=0) is True
    assert sent[0]["url"].endswith("/botsupport-bot-token/sendMessage")
    assert sent[0]["json"]["chat_id"] == "555"


def test_send_telegram_alert_without_config_returns_false(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_ALERT_CHAT_ID", raising=False)
    monkeypatch.setattr(alerts, "_LAST_SENT", {})

    assert alerts.send_telegram_alert("x", key="k2", cooldown_sec=0) is False

def test_notify_humanize_failure_includes_fix_hint(monkeypatch):
    sent: list[dict] = []

    class _Resp:
        ok = True
        status_code = 200
        text = "ok"

    monkeypatch.setenv("TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("CHAT_ID", "99")
    monkeypatch.setenv("TELEGRAM_HUMANIZE_ALERT_COOLDOWN_SEC", "0")
    monkeypatch.setattr(
        alerts.requests,
        "post",
        lambda url, json, timeout: (sent.append(json), _Resp())[1],
    )
    monkeypatch.setattr(alerts, "_LAST_SENT", {})

    assert (
        alerts.notify_humanize_failure(
            code="FREE_ENGINE_UNAVAILABLE",
            message="student model returned None",
            user_id=42,
            free_run=True,
            words=120,
            path="/api/browser/providers/stealthwriter/humanize",
            source="landing",
        )
        is True
    )
    text = sent[0]["text"]
    assert "Humanizer failed: FREE_ENGINE_UNAVAILABLE" in text
    assert "user:42" in text
    assert "Words: 120" in text
    assert "Fix:" in text
    assert "Modal" in text

