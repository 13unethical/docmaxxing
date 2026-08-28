"""SEO metadata, sitemap, and robots.txt."""

from __future__ import annotations

from app import app
from services.seo import (
    DEFAULT_DESCRIPTION,
    DEFAULT_TITLE,
    SITE_URL,
    page_seo_for_path,
    robots_txt,
    sitemap_xml,
)


def _client():
    app.config["TESTING"] = True
    return app.test_client()


def test_homepage_has_seo_meta_tags():
    with _client() as client:
        res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Academic AI Tools" in html
    assert DEFAULT_DESCRIPTION in html
    assert 'property="og:title"' in html
    assert 'property="og:description"' in html
    assert 'property="og:url"' in html
    assert 'content="https://docmaxxing.com"' in html
    assert 'property="og:type"' in html
    assert 'content="website"' in html
    assert 'rel="canonical"' in html
    assert "/icon.png" in html
    assert "/apple-icon.png" in html
    assert "application/ld+json" in html
    assert '"@type": "WebSite"' in html or '"@type":"WebSite"' in html
    assert '"@type": "Organization"' in html or '"@type":"Organization"' in html


def test_sitemap_xml_lists_public_urls():
    xml = sitemap_xml()
    assert "<?xml" in xml
    for path in ("", "/humanizer", "/formatter", "/assignments", "/pricing"):
        loc = SITE_URL if path == "" else f"{SITE_URL}{path}"
        assert loc in xml


def test_robots_txt_allows_indexing():
    text = robots_txt()
    assert "User-agent: *" in text
    assert "Allow: /" in text
    assert f"Sitemap: {SITE_URL}/sitemap.xml" in text


def test_sitemap_route():
    res = _client().get("/sitemap.xml")
    assert res.status_code == 200
    assert res.mimetype == "application/xml"


def test_robots_route():
    res = _client().get("/robots.txt")
    assert res.status_code == 200
    assert "text/plain" in (res.mimetype or "")


def test_formatter_landing_page():
    res = _client().get("/formatter", follow_redirects=False)
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "APA/MLA Essay Formatter" in html
    assert "Automatic Academic Essay Formatter" in html
    assert 'data-format-v2' in html


def test_assignments_landing_page():
    res = _client().get("/assignments")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "AI Assignment Helper" in html
    assert "Step-by-Step College Homework Assistant" in html
    assert 'data-assignment-page' in html


def test_humanizer_landing_page():
    res = _client().get("/humanizer")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Undetectable AI Humanizer" in html
    assert "Bypass Turnitin" in html
    assert html.count("<h1") == 1
    assert 'data-humanizer-page' in html


def test_icon_routes():
    client = _client()
    assert client.get("/icon.png").status_code == 200
    assert client.get("/apple-icon.png").status_code == 200


def test_humanizer_page_seo_override():
    seo = page_seo_for_path("/humanizer")
    assert "Undetectable AI Humanizer" in seo["title"]
    assert seo["canonical"] == f"{SITE_URL}/humanizer"
    assert seo["h1"]


def test_primary_nav_sitelinks_present():
    html = _client().get("/humanizer").get_data(as_text=True)
    assert 'href="/humanizer"' in html
    assert 'href="/formatter"' in html
    assert 'href="/assignments"' in html
    assert 'href="/pricing"' in html
    assert ">AI Humanizer</" in html or ">AI Humanizer</a>" in html
    assert ">Formatter</" in html
    assert ">Assignments</" in html
    assert ">Pricing</" in html
    assert 'aria-label="Main navigation"' in html
    assert "<nav" in html
