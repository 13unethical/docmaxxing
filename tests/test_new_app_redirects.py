"""Old server-rendered pages send visitors to the matching screen of the new app.

Public landing pages stay server-rendered for guests (and crawlers); without them, guests
get the app's own landing at /, /ai-detector and /humanizer. Signed-in users go to the app.
"""

from __future__ import annotations

import pytest

from services.economy import auth as economy_auth
from services.economy import db as economy_db


@pytest.fixture()
def client(monkeypatch):
    from app import app

    monkeypatch.delenv("LEGACY_UI", raising=False)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture()
def signed_in_client(client, tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    user = economy_auth.create_user("redirects@example.com", "secret123")
    economy_auth.mark_email_verified(user["id"], user["email"])
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    return client


PUBLIC_PAGES = ["/", "/humanizer", "/ru/humanizer", "/pricing", "/formatter"]


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_public_pages_render_for_guests(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, path
    assert "Location" not in resp.headers
    html = resp.get_data(as_text=True)
    robots = "noindex, follow" if path == "/ru/humanizer" else "index, follow"
    assert f'<meta name="robots" content="{robots}"' in html


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ("/", "/app#/home"),
        ("/humanizer", "/app#/humanizer"),
        ("/ru/humanizer", "/app#/humanizer"),
        ("/pricing", "/app#/pricing"),
        ("/formatter", "/app#/format"),
        ("/pricing?paid=1&utm_source=x", "/app?paid=1&utm_source=x#/pricing"),
    ],
)
def test_public_pages_redirect_signed_in_users(signed_in_client, path, target):
    resp = signed_in_client.get(path)
    assert resp.status_code == 302
    assert resp.headers["Location"] == target


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ("/veil", "/app#/veil"),
        ("/admin", "/app#/admin"),
        ("/turnitin", "/app#/turnitin"),
    ],
)
def test_app_only_pages_still_redirect_guests(client, path, target):
    resp = client.get(path)
    assert resp.status_code == 302
    assert resp.headers["Location"] == target


@pytest.mark.parametrize("path", ["/login", "/register", "/privacy", "/terms", "/app", "/api/version"])
def test_kept_pages_do_not_redirect_to_app(client, path):
    resp = client.get(path)
    assert "#/" not in resp.headers.get("Location", "")


def test_classic_param_and_legacy_env_skip_redirect(signed_in_client, monkeypatch):
    assert signed_in_client.get("/pricing?classic=1").status_code == 200
    monkeypatch.setenv("LEGACY_UI", "1")
    assert signed_in_client.get("/pricing").status_code == 200


def test_app_is_noindex_without_root_canonical(client):
    html = client.get("/app").get_data(as_text=True)
    assert '<meta name="description"' in html
    assert '<meta name="robots" content="noindex, follow"' in html
    assert 'rel="canonical"' not in html
    assert "cloud.umami.is/script.js" in html


def test_post_is_not_redirected(client):
    resp = client.post("/account")
    assert "#/" not in resp.headers.get("Location", "")


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ("/pricing", "/app#/pricing"),
        ("/formatter", "/app#/format"),
    ],
)
def test_without_landing_pages_guests_go_to_the_app(client, monkeypatch, path, target):
    monkeypatch.setenv("GUEST_LANDING_PAGES", "0")
    resp = client.get(path)
    assert resp.status_code == 302
    assert resp.headers["Location"] == target


@pytest.mark.parametrize(
    ("path", "tab", "h1"),
    [
        ("/", "detect", "Check your text for AI"),
        ("/ai-detector", "detect", "Free AI Detector"),
        ("/humanizer", "humanize", "Free AI Humanizer"),
    ],
)
def test_without_landing_pages_guests_get_the_app_landing_in_place(client, monkeypatch, path, tab, h1):
    from services.seo import canonical_url

    monkeypatch.setenv("GUEST_LANDING_PAGES", "0")
    resp = client.get(path)
    assert resp.status_code == 200, path
    html = resp.get_data(as_text=True)
    assert 'id="app"' in html
    assert html.count("<h1") == 1
    assert f'id="hero-h">{h1}</h1>' in html
    assert f'"tab": "{tab}"' in html
    assert '<meta name="robots" content="index, follow"' in html
    assert f'<link rel="canonical" href="{canonical_url(path)}" />' in html
    assert '"@type": "FAQPage"' in html
    assert '<details class="card">' in html


def test_ai_detector_page_sends_signed_in_users_to_the_dashboard(signed_in_client):
    resp = signed_in_client.get("/ai-detector")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/app#/home"


def test_without_landing_pages_the_app_is_indexed_under_the_root(client, monkeypatch):
    from services.seo import SITE_URL, sitemap_xml

    monkeypatch.setenv("GUEST_LANDING_PAGES", "0")
    html = client.get("/app").get_data(as_text=True)
    assert '<meta name="robots" content="index, follow"' in html
    assert f'<link rel="canonical" href="{SITE_URL}" />' in html
    assert '"landing":' not in html
    xml = sitemap_xml()
    for path in ("", "/ai-detector", "/humanizer", "/faq"):
        assert f"<loc>{SITE_URL}{path}</loc>" in xml
    for path in ("/pricing", "/formatter"):
        assert f"<loc>{SITE_URL}{path}</loc>" not in xml
