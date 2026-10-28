"""Quick Humanize API used by the Veil Chrome overlay."""

from __future__ import annotations

import pytest

from services.browser.jobs.models import Job, JobStatus
from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy.wallet import WalletService
from services.veil_tokens import issue_token


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    economy_db.init_db()
    return tmp_path


def _client():
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


def _user(email="hz-ext@example.com"):
    user = economy_auth.create_user(email, "secret123")
    economy_auth.mark_email_verified(user["id"], user["email"])
    return economy_auth.get_user(user["id"])


class _FakeWorker:
    job_timeout = 1


def _patch_humanizer(monkeypatch, *, text_out="Rewritten by StealthWriter.", fail=False, empty=False):
    import app as app_mod

    job = Job(provider="stealthwriter", operation="humanize", payload={"text": "x"}, max_retries=0)
    if fail:
        job.status = JobStatus.FAILED
        job.error = "provider crashed"
        job.error_code = "AUTOMATION_ERROR"
    elif empty:
        job.status = JobStatus.COMPLETED
        job.result = {"humanized_text": "", "elapsed_seconds": 0.2}
    else:
        job.status = JobStatus.COMPLETED
        job.result = {"humanized_text": text_out, "elapsed_seconds": 0.2}

    class _JM:
        def create(self, *_args, **_kwargs):
            return job

        def wait(self, *_args, **_kwargs):
            return job

        def get(self, _job_id):
            return job

    monkeypatch.setattr(app_mod, "ensure_engine_started", lambda: None)
    monkeypatch.setattr(app_mod, "job_manager", _JM())
    monkeypatch.setattr(app_mod, "browser_worker", _FakeWorker())
    return job


def test_extension_humanize_requires_a_key(economy):
    res = _client().post("/api/extension/humanize", json={"text": "Please rewrite this paragraph."})
    body = res.get_json()
    assert res.status_code == 401, body
    assert body["ok"] is False
    assert body["error"] == "AUTH_REQUIRED"


def test_extension_humanize_accepts_json_key_and_charges(economy, monkeypatch):
    _patch_humanizer(monkeypatch, text_out="A more natural paragraph.")
    user = _user()
    WalletService().set_balance(user["id"], 200)
    token = issue_token(user["id"])
    before = WalletService().get_balance(user["id"])

    res = _client().post(
        "/api/extension/humanize",
        json={"text": "Please rewrite this paragraph for a human reader.", "key": token},
    )
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["ok"] is True
    assert body["humanized_text"] == "A more natural paragraph."
    assert body["coins_charged"] > 0
    assert WalletService().get_balance(user["id"]) == before - body["coins_charged"]
    assert body["balance"] == before - body["coins_charged"]


def test_extension_humanize_accepts_bearer_token(economy, monkeypatch):
    _patch_humanizer(monkeypatch)
    user = _user("bearer@example.com")
    WalletService().set_balance(user["id"], 200)
    token = issue_token(user["id"])

    res = _client().post(
        "/api/extension/humanize",
        json={"text": "Please rewrite this paragraph for a human reader."},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["ok"] is True
    assert "StealthWriter" in body["humanized_text"]


def test_extension_humanize_blocks_empty_and_broke_users(economy, monkeypatch):
    _patch_humanizer(monkeypatch)
    user = _user("broke@example.com")
    WalletService().set_balance(user["id"], 0)
    token = issue_token(user["id"])
    client = _client()

    empty = client.post(
        "/api/extension/humanize",
        json={"text": "   ", "key": token},
    )
    assert empty.status_code == 400
    assert empty.get_json()["error"] == "EMPTY"
    assert WalletService().get_balance(user["id"]) == 0

    broke = client.post(
        "/api/extension/humanize",
        json={"text": "Please rewrite this paragraph for a human reader.", "key": token},
    )
    body = broke.get_json()
    assert broke.status_code == 402, body
    assert body["error"] == "INSUFFICIENT_COINS"
    assert WalletService().get_balance(user["id"]) == 0


def test_extension_humanize_refunds_when_the_job_fails(economy, monkeypatch):
    _patch_humanizer(monkeypatch, fail=True)
    user = _user("fail@example.com")
    WalletService().set_balance(user["id"], 200)
    token = issue_token(user["id"])
    before = WalletService().get_balance(user["id"])

    res = _client().post(
        "/api/extension/humanize",
        json={"text": "Please rewrite this paragraph for a human reader.", "key": token},
    )
    body = res.get_json()
    assert res.status_code == 500, body
    assert body["ok"] is False
    assert WalletService().get_balance(user["id"]) == before


def test_extension_humanize_refunds_empty_provider_output(economy, monkeypatch):
    _patch_humanizer(monkeypatch, empty=True)
    user = _user("empty@example.com")
    WalletService().set_balance(user["id"], 200)
    token = issue_token(user["id"])
    before = WalletService().get_balance(user["id"])

    res = _client().post(
        "/api/extension/humanize",
        json={"text": "Please rewrite this paragraph for a human reader.", "key": token},
    )
    body = res.get_json()
    assert res.status_code == 502, body
    assert body["error"] == "EMPTY_RESULT"
    assert WalletService().get_balance(user["id"]) == before
