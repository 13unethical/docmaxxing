"""Veil sidebar item opens the external Hostinger site."""

from __future__ import annotations

from app import app


def _client():
    app.config["TESTING"] = True
    return app.test_client()


def test_veil_sidebar_link():
    html = _client().get("/").get_data(as_text=True)
    assert 'title="Veil"' in html
    assert "Veil (Stealth)" not in html
    assert 'href="/veil"' in html
    assert 'target="_blank"' in html
    assert "nav-discount-badge" in html
    assert "NEW" in html


def test_veil_local_route_renders_landing():
    res = _client().get("/veil")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Veil" in html
    assert "Focus on the reading" in html
    assert "Follows your eyes" in html
    assert "Alt+Q" in html
    assert "Alt+S" in html
    assert "Load unpacked" in html
    assert "2,200" in html
    assert "30 days" in html
    assert 'href="/veil/download"' not in html
    assert 'action="/veil/unlock"' not in html
    assert "/login?next=/veil" in html
    lowered = html.lower()
    assert "undetectable" not in lowered
    assert "proctor" not in lowered
    assert "screen share" not in lowered
    assert "99.4%" not in html
    # Ensure it is a standalone landing page without the DocMaxxing left app sidebar
    assert "app-sidebar" not in html

