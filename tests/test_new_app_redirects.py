"""Old server-rendered pages send visitors to the matching screen of the new app."""

from __future__ import annotations

import pytest


@pytest.fixture()
def client(monkeypatch):
    from app import app

    monkeypatch.delenv("LEGACY_UI", raising=False)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ("/", "/app#/home"),
        ("/humanizer", "/app#/humanizer"),
        ("/pricing", "/app#/pricing"),
        ("/veil", "/app#/veil"),
        ("/admin", "/app#/admin"),
        ("/pricing?paid=1&utm_source=x", "/app?paid=1&utm_source=x#/pricing"),
    ],
)
def test_old_pages_redirect(client, path, target):
    resp = client.get(path)
    assert resp.status_code == 302
    assert resp.headers["Location"] == target


@pytest.mark.parametrize("path", ["/login", "/register", "/privacy", "/terms", "/app", "/api/version"])
def test_kept_pages_do_not_redirect_to_app(client, path):
    resp = client.get(path)
    assert "#/" not in resp.headers.get("Location", "")


def test_classic_param_and_legacy_env_skip_redirect(client, monkeypatch):
    assert client.get("/pricing?classic=1").status_code == 200
    monkeypatch.setenv("LEGACY_UI", "1")
    assert client.get("/pricing").status_code == 200


def test_app_has_seo_and_analytics(client):
    html = client.get("/app").get_data(as_text=True)
    assert '<meta name="description"' in html
    assert '<link rel="canonical" href="https://docmaxxing.com"' in html
    assert "cloud.umami.is/script.js" in html


def test_post_is_not_redirected(client):
    resp = client.post("/account")
    assert "#/" not in resp.headers.get("Location", "")
