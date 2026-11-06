"""SEO metadata, sitemap, robots.txt, JSON-LD, 404 and URL hygiene."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app import app
from services import seo as seo_module
from services.seo import (
    DEFAULT_DESCRIPTION,
    PUBLIC_PAGES,
    SITE_URL,
    file_lastmod,
    page_seo_for_path,
    robots_txt,
    sitemap_xml,
)
from services.site_content import faq_items_for_path, plain_text

REPO = Path(__file__).resolve().parents[1]
INFO_PATHS = [
    "/about", "/faq", "/terms", "/privacy", "/contact", "/credits", "/account-info",
    "/disclaimer", "/payment-policy", "/delivery-policy", "/refund-policy", "/changelog",
]


def _client():
    app.config["TESTING"] = True
    return app.test_client()


def _json_ld(html: str) -> list[dict]:
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert blocks, "no JSON-LD on page"
    return [node for block in blocks for node in json.loads(block)["@graph"]]


def _types(html: str) -> list[str]:
    return [node["@type"] for node in _json_ld(html)]


def _visible_text(html: str) -> str:
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    return plain_text(body)


# ------------------------------------------------------------------ head tags


def test_homepage_has_seo_meta_tags():
    res = _client().get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert DEFAULT_DESCRIPTION in html
    assert '<html lang="en"' in html
    assert 'property="og:title"' in html
    assert 'property="og:description"' in html
    assert '<link rel="canonical" href="https://docmaxxing.com" />' in html
    assert '<meta property="og:url" content="https://docmaxxing.com" />' in html
    assert '<meta property="og:type" content="website" />' in html
    assert '<meta property="og:locale" content="en_US" />' in html
    assert f'<meta property="og:image" content="{SITE_URL}/static/og/default.png" />' in html
    assert '<meta property="og:image:width" content="1200" />' in html
    assert '<meta property="og:image:height" content="630" />' in html
    assert "/apple-icon.png" in html
    assert 'href="/favicon.ico?v=2"' in html
    assert 'href="/site.webmanifest"' in html
    types = _types(html)
    assert {"WebSite", "Organization", "SoftwareApplication"} <= set(types)
    app_node = next(n for n in _json_ld(html) if n["@type"] == "SoftwareApplication")
    assert app_node["offers"] == {"@type": "Offer", "price": "0", "priceCurrency": "USD"}


def test_titles_and_descriptions_are_unique_and_short():
    titles = [p.title for p in PUBLIC_PAGES.values()]
    descriptions = [p.description for p in PUBLIC_PAGES.values()]
    assert len(set(titles)) == len(titles)
    assert len(set(descriptions)) == len(descriptions)
    for page in PUBLIC_PAGES.values():
        assert len(page.title) <= seo_module.TITLE_MAX, page.path
        assert len(page.description) <= seo_module.DESCRIPTION_MAX, page.path


def test_no_detector_evasion_promises_in_metadata():
    banned = ("undetectable", "bypass", "100% human", "0% ai")
    for page in PUBLIC_PAGES.values():
        text = f"{page.title} {page.description} {page.h1 or ''}".lower()
        assert not any(word in text for word in banned), page.path


@pytest.mark.parametrize("path", INFO_PATHS)
def test_info_pages_have_their_own_title_and_description(path):
    res = _client().get(path)
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    page = PUBLIC_PAGES[path]
    assert f"<title>{page.title}" in html.replace("&amp;", "&")
    assert f'<meta name="description" content="{page.description}"' in html.replace("&amp;", "&")
    assert f'<link rel="canonical" href="{SITE_URL}{path}" />' in html
    assert '<meta name="robots" content="index, follow" />' in html
    assert "BreadcrumbList" in _types(html)


def test_humanizer_og_image_and_no_ru_hreflang_while_ru_is_on_hold():
    seo = page_seo_for_path("/humanizer")
    assert seo["og_image"] == f"{SITE_URL}/static/og/humanizer.png"
    assert seo["alternates"] == []
    ru = page_seo_for_path("/ru/humanizer")
    assert ru["lang"] == "ru"
    assert ru["robots"] == "noindex, follow"
    assert ru["alternates"] == []


@pytest.mark.parametrize(
    "path", ["/app", "/login", "/register", "/account", "/admin", "/admin/dataset-stats", "/verify-email/code"]
)
def test_private_pages_are_noindex(path):
    seo = page_seo_for_path(path)
    assert seo["robots"] == "noindex, follow"
    assert seo["canonical"] is None


@pytest.mark.parametrize("path", ["/login", "/register", "/app"])
def test_private_pages_render_noindex_tag(path):
    html = _client().get(path).get_data(as_text=True)
    assert '<meta name="robots" content="noindex, follow" />' in html
    assert 'rel="canonical"' not in html


def test_classic_param_is_noindex():
    assert page_seo_for_path("/pricing", args={"classic": "1"})["robots"] == "noindex, follow"


def test_verification_tags_only_when_set(monkeypatch):
    for name in ("GOOGLE_SITE_VERIFICATION", "YANDEX_VERIFICATION", "BING_SITE_VERIFICATION"):
        monkeypatch.delenv(name, raising=False)
    html = _client().get("/faq").get_data(as_text=True)
    assert "google-site-verification" not in html
    assert "yandex-verification" not in html
    assert "msvalidate.01" not in html

    monkeypatch.setenv("GOOGLE_SITE_VERIFICATION", "g-token")
    monkeypatch.setenv("YANDEX_VERIFICATION", "y-token")
    monkeypatch.setenv("BING_SITE_VERIFICATION", "b-token")
    html = _client().get("/faq").get_data(as_text=True)
    assert '<meta name="google-site-verification" content="g-token" />' in html
    assert '<meta name="yandex-verification" content="y-token" />' in html
    assert '<meta name="msvalidate.01" content="b-token" />' in html


# ------------------------------------------------------------------ JSON-LD


def test_faq_page_json_ld_matches_visible_text():
    html = _client().get("/faq").get_data(as_text=True)
    faq_node = next(n for n in _json_ld(html) if n["@type"] == "FAQPage")
    visible = _visible_text(html)
    items = faq_items_for_path("/faq")
    assert len(faq_node["mainEntity"]) == len(items) >= 8
    for entity, (question, answer) in zip(faq_node["mainEntity"], items):
        assert entity["name"] == plain_text(question)
        assert entity["acceptedAnswer"]["text"] == plain_text(answer)
        assert entity["name"] in visible
        assert entity["acceptedAnswer"]["text"] in visible


def test_faq_and_about_are_current():
    faq = _visible_text(_client().get("/faq").get_data(as_text=True))
    about = _visible_text(_client().get("/about").get_data(as_text=True))
    for text in (faq, about):
        assert "Soon page" not in text
        assert "Coming soon" not in text
        assert "Workspace" in text
        assert "Slides" in text


def test_breadcrumbs_on_inner_pages():
    html = _client().get("/pricing").get_data(as_text=True)
    crumbs = next(n for n in _json_ld(html) if n["@type"] == "BreadcrumbList")
    assert [item["item"] for item in crumbs["itemListElement"]] == [SITE_URL, f"{SITE_URL}/pricing"]


def test_json_ld_cannot_close_script_tag():
    assert "</" not in seo_module.json_ld_script({"x": "</script><b>"})


# ------------------------------------------------------------------ sitemap / robots


def test_sitemap_lists_indexable_pages_only():
    xml = sitemap_xml()
    assert 'xmlns:xhtml="http://www.w3.org/1999/xhtml"' in xml
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    for path in ("/humanizer", "/formatter", "/pricing", *INFO_PATHS):
        assert f"{SITE_URL}{path}" in locs
    assert SITE_URL in locs
    for path in ("/ru/humanizer", "/assignments", "/app", "/login", "/register", "/veil", "/account"):
        assert f"{SITE_URL}{path}" not in locs
    assert "<priority>" not in xml


def test_sitemap_has_no_link_to_the_ru_humanizer():
    assert "/ru/humanizer" not in sitemap_xml()


def test_sitemap_lastmod_is_last_change_not_today(monkeypatch):
    monkeypatch.setattr(seo_module, "_git", lambda *args: "" if args[0] == "status" else "2026-03-14")
    file_lastmod.cache_clear()
    try:
        xml = sitemap_xml()
        block = xml.split(f"<loc>{SITE_URL}/terms</loc>", 1)[1].split("</url>", 1)[0]
        assert "<lastmod>2026-03-14</lastmod>" in block
    finally:
        file_lastmod.cache_clear()


def test_lastmod_falls_back_to_mtime_without_git(monkeypatch):
    monkeypatch.setattr(seo_module, "_git", lambda *args: "")
    file_lastmod.cache_clear()
    try:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", file_lastmod("templates/info/terms.html"))
        assert file_lastmod("templates/does-not-exist.html") is None
    finally:
        file_lastmod.cache_clear()


def test_robots_txt():
    text = robots_txt()
    assert "User-agent: *" in text
    assert "Allow: /" in text
    assert "Disallow: /api/" in text
    for path in ("/app", "/login", "/register", "/account", "/admin"):
        assert f"Disallow: {path}\n" not in text
    assert f"Sitemap: {SITE_URL}/sitemap.xml" in text


def test_sitemap_and_robots_routes():
    client = _client()
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    assert res.mimetype == "application/xml"
    res = client.get("/robots.txt")
    assert res.status_code == 200
    assert "text/plain" in (res.mimetype or "")


# ------------------------------------------------------------------ 404, slashes, icons


def test_custom_404_page():
    res = _client().get("/no-such-page")
    assert res.status_code == 404
    html = res.get_data(as_text=True)
    assert '<meta name="robots" content="noindex, follow" />' in html
    assert 'rel="canonical"' not in html
    for href in ("/humanizer", "/formatter", "/pricing"):
        assert f'href="{href}"' in html
    assert 'href="/ru/humanizer"' not in html
    assert html.count("<h1") == 1


def test_api_404_stays_json():
    res = _client().get("/api/no-such-endpoint")
    assert res.status_code == 404
    assert res.get_json()["error"] == "NOT_FOUND"


@pytest.mark.parametrize(
    ("path", "target"),
    [("/humanizer/", "/humanizer"), ("/faq/?a=1", "/faq?a=1"), ("/pricing/", "/pricing")],
)
def test_trailing_slash_redirects_permanently(path, target):
    res = _client().get(path)
    assert res.status_code == 301
    assert res.headers["Location"] == target


def test_trailing_slash_left_alone_outside_public_pages():
    assert _client().get("/api/version/").status_code != 301


def test_favicon_and_manifest():
    client = _client()
    res = client.get("/favicon.ico")
    assert res.status_code == 200
    assert res.data[:4] == b"\x00\x00\x01\x00"
    res = client.get("/site.webmanifest")
    assert res.status_code == 200
    manifest = json.loads(res.data)
    assert manifest["name"] == "DocMaxxing"
    assert manifest["icons"]


def test_icon_routes():
    client = _client()
    assert client.get("/icon.png").status_code == 200
    assert client.get("/apple-icon.png").status_code == 200


def test_og_images_are_1200x630():
    from PIL import Image

    for name in ("default.png", "humanizer.png"):
        with Image.open(REPO / "static" / "og" / name) as img:
            assert img.size == (1200, 630)


# ------------------------------------------------------------------ footers

FOOTER_LINKS = ("/humanizer", "/pricing", "/blog", "/faq", "/terms", "/privacy", "/contact")


def test_server_footer_has_real_links():
    html = _client().get("/faq").get_data(as_text=True)
    footer = html.split('<footer class="site-footer"', 1)[1]
    for href in FOOTER_LINKS:
        assert f'href="{href}"' in footer, href
    assert 'href="/ru/humanizer"' not in footer


def test_spa_landing_footer_has_real_links():
    js = (REPO / "static" / "app2" / "app.js").read_text(encoding="utf-8")
    footer = js.split("function landFooterHtml(", 1)[1].split("\n}\n", 1)[0]
    links = js.split("footer: {", 1)[1].split("socials:", 1)[0]
    # Landing footer: policy/company links are rendered as real paths, tools as /<route>
    assert "if (!inApp) return `<a href=\"${esc(l.path)}\">" in footer
    assert "<a href=\"/${i.route === 'format' ? 'formatter' : i.route}\">" in footer
    for href in FOOTER_LINKS:
        if href in ("/humanizer", "/pricing", "/blog"):
            assert f'href="{href}"' in footer or href == "/humanizer", href
        else:
            assert f"path: '{href}'" in links, href
    assert "route: 'humanizer'" in js
    assert "/ru/humanizer" not in footer
    assert "Terms · Privacy · Contact" not in js


def test_formatter_landing_page():
    res = _client().get("/formatter", follow_redirects=False)
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert PUBLIC_PAGES["/formatter"].title.replace("&", "&amp;") in html
    assert "data-format-v2" in html
