"""Site reviews: submit, confirm, moderate, public feed."""

from __future__ import annotations

import pytest

from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.economy import site_reviews


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-site-reviews")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://docmaxxing.com")
    economy_db.init_db()
    return tmp_path


def test_seed_feed_then_approved_replaces(economy):
    feed = site_reviews.public_feed()
    assert feed["count"] == 46
    assert len(feed["items"]) >= 4

    user = economy_auth.create_user("rev@example.com", "secret12")
    res = site_reviews.submit_review(
        stars=5,
        body="Formatting saved me hours before the deadline.",
        tool="Formatting",
        user_id=user["id"],
    )
    assert res["status"] == site_reviews.STATUS_PENDING_MOD
    site_reviews.moderate(res["id"], approve=True)
    live = site_reviews.public_feed()
    assert live["count"] == 1
    assert live["items"][0]["tool"] == "Formatting"
    assert live["items"][0]["verified"] is True


def test_guest_confirm_links_account(economy, monkeypatch):
    sent = []

    def _fake_send(*, to_email, confirm_url):
        sent.append((to_email, confirm_url))
        return True

    monkeypatch.setattr(site_reviews, "send_confirm_email", _fake_send)
    user = economy_auth.create_user("guestmatch@example.com", "secret12")
    res = site_reviews.submit_review(
        stars=4,
        body="Tried the detector as a guest first, then signed up.",
        tool="AI Detector",
        email="guestmatch@example.com",
    )
    assert res["needs_email_confirm"] is True
    assert res.get("confirm_token")
    # Simulate the email path using the token from submit (API strips it after send).
    out = site_reviews.confirm_email(res["confirm_token"])
    assert out["status"] == site_reviews.STATUS_PENDING_MOD
    assert out["verified"] is True
    mine = site_reviews.get_mine(user_id=user["id"])
    assert mine and mine["status"] == site_reviews.STATUS_PENDING_MOD
