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
    assert "Soon page" not in faq and "Coming soon" not in faq
    assert "Workspace" in faq and "Slides" in faq
    assert "Soon page" not in about and "Coming soon" not in about
    assert "Who we are" in about
    assert "support@docmaxxing.com" in about
    assert "TODO" in about


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


def _robots_groups(text: str) -> dict[str, list[str]]:
    """Map each User-agent name to the directive lines in its group (comments ignored)."""
    groups: dict[str, list[str]] = {}
    current: list[str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            current = groups.setdefault(agent, [])
            continue
        if current is not None and line.lower().startswith("sitemap:"):
            current = None
            continue
        if current is not None:
            current.append(line)
    return groups


def test_robots_txt():
    from services.seo import DISALLOW_PATHS, _AI_CRAWLER_USER_AGENTS

    text = robots_txt()
    assert DISALLOW_PATHS == ("/api/",)
    groups = _robots_groups(text)
    assert set(groups) == set(_AI_CRAWLER_USER_AGENTS) | {"*"}
    for agent, directives in groups.items():
        assert "Allow: /" in directives, agent
        for path in DISALLOW_PATHS:
            assert f"Disallow: {path}" in directives, agent
        # Disallow before Allow so first-match parsers still block /api/
        assert directives.index(f"Disallow: {DISALLOW_PATHS[0]}") < directives.index("Allow: /")
    for path in ("/app", "/login", "/register", "/account", "/admin"):
        assert f"Disallow: {path}" not in text
    assert f"Sitemap: {SITE_URL}/sitemap.xml" in text


def test_robots_txt_blocks_api_for_every_user_agent():
    """Each User-agent group allows ``/`` and forbids ``/api/...`` (no reliance on ``*``)."""
    from urllib.robotparser import RobotFileParser

    from services.seo import DISALLOW_PATHS, _AI_CRAWLER_USER_AGENTS

    text = robots_txt()
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    for agent in (*_AI_CRAWLER_USER_AGENTS, "*"):
        assert parser.can_fetch(agent, f"{SITE_URL}/"), agent
        assert parser.can_fetch(agent, f"{SITE_URL}/pricing"), agent
        for path in DISALLOW_PATHS:
            sample = f"{SITE_URL}{path.rstrip('/')}/version"
            assert not parser.can_fetch(agent, sample), (agent, sample)


def test_homepage_ssr_includes_about_link(monkeypatch):
    monkeypatch.setenv("GUEST_LANDING_PAGES", "0")
    html = _client().get("/").get_data(as_text=True)
    # Present in the server-rendered public block (before JS replaces the main column).
    assert 'href="/about"' in html


def test_llms_txt_lists_core_tools():
    from services.seo import llms_txt

    text = llms_txt()
    assert text.startswith("# DocMaxxing")
    for path in (
        "/ai-detector",
        "/humanizer",
        "/formatter",
        "/pricing",
        "/faq",
        "/credits",
        "/blog",
        "/about",
        "/blog/rss.xml",
    ):
        assert f"{SITE_URL}{path}" in text


def test_sitemap_and_robots_routes():
    client = _client()
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    assert res.mimetype == "application/xml"
    res = client.get("/robots.txt")
    assert res.status_code == 200
    assert "text/plain" in (res.mimetype or "")
    res = client.get("/llms.txt")
    assert res.status_code == 200
    assert "text/plain" in (res.mimetype or "")
    assert b"# DocMaxxing" in res.data


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
    page = PUBLIC_PAGES["/formatter"]
    assert page.title.replace("&", "&amp;") in html
    assert page.h1 in html
    assert "data-format-v2" in html
    visible = _visible_text(html)
    assert "What the essay formatter applies" in visible
    assert "APA 7" in visible and "MLA 9" in visible and "Harvard" in visible and "Chicago" in visible
    assert "Essay formatter FAQ" in visible
    assert {"SoftwareApplication", "FAQPage"} <= set(_types(html))
    assert f'<link rel="canonical" href="{SITE_URL}/formatter" />' in html


def _token_jaccard(a: str, b: str) -> float:
    left, right = set(a.lower().split()), set(b.lower().split())
    return len(left & right) / len(left | right) if left or right else 1.0


def test_humanizer_ssr_is_unique_vs_homepage():
    client = _client()
    home = _visible_text(client.get("/").get_data(as_text=True))
    hum_html = client.get("/humanizer").get_data(as_text=True)
    hum = _visible_text(hum_html)
    page = PUBLIC_PAGES["/humanizer"]
    assert page.title.replace("&", "&amp;") in hum_html
    assert page.h1 in hum
    assert "How the AI humanizer works" in hum
    assert "Before / after: humanize AI text" in hum
    assert "AI humanizer FAQ" in hum
    assert f'<link rel="canonical" href="{SITE_URL}/humanizer" />' in hum_html
    assert {"SoftwareApplication", "FAQPage"} <= set(_types(hum_html))
    words = hum.split()
    assert len(words) >= 600, len(words)
    overlap = _token_jaccard(home, hum)
    assert overlap < 0.35, overlap
    faq = faq_items_for_path("/humanizer") or []
    assert 5 <= len(faq) <= 6
    banned = ("guarantee", "undetectable", "0% ai", "bypass turnitin")
    for q, a in faq:
        blob = f"{q} {plain_text(a)}".lower()
        assert not any(b in blob for b in banned)


def test_turnitin_asterisk_post_meta_and_first_paragraph():
    from services import blog

    post = blog.find_post("en", "turnitin-ai-score-asterisk")
    assert post is not None
    assert len(post.seo_title) <= seo_module.TITLE_MAX
    assert len(post.description) <= seo_module.DESCRIPTION_MAX
    assert "asterisk" in post.description.lower() or "*%" in post.description
    html = _client().get(post.path).get_data(as_text=True)
    assert post.seo_title.replace("&", "&amp;") in html or post.seo_title in html
    assert post.author_name in html
    assert post.date in html or "2026-11-02" in html
    assert 'href="/ai-detector"' in html
    assert 'href="/humanizer"' in html
    # First visible paragraph answers the asterisk question.
    visible = _visible_text(html)
    head = visible[:500].lower()
    assert "*%" in head or "asterisk" in head
    assert "not" in head and ("high score" in head or "proof" in head)


# ------------------------------------------------------------------ pricing / about / social / RSS


def test_pricing_ssr_independent_of_guest_landing_flag(monkeypatch):
    from services.economy.pricing import pricing_page_packages

    monkeypatch.setenv("GUEST_LANDING_PAGES", "0")
    res = _client().get("/pricing")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Simple credit pricing" in html
    assert "/credits" in html and "/faq" in html
    assert html.count('href="/app#/pricing"') >= 1
    assert "Product" not in _types(html)
    app_node = next(n for n in _json_ld(html) if n["@type"] == "SoftwareApplication")
    offers = app_node["offers"]
    assert isinstance(offers, list)
    packages = pricing_page_packages()
    assert len(offers) == len(packages) >= 1
    banned = ("aggregateRating", "review", "shippingDetails", "hasMerchantReturnPolicy", "image")
    blob = json.dumps(app_node)
    for key in banned:
        assert key not in blob
    for offer, pkg in zip(offers, packages):
        assert offer["@type"] == "Offer"
        assert offer["priceCurrency"] == "USD"
        assert float(offer["price"]) == float(pkg["usd"])
        assert offer["name"] == pkg["name"]


def test_organization_same_as_uses_social_links():
    from services.seo import SOCIAL_LINKS, organization_same_as

    same = organization_same_as()
    assert same == [item["url"] for item in SOCIAL_LINKS]
    html = _client().get("/about").get_data(as_text=True)
    org = next(n for n in _json_ld(html) if n["@type"] == "Organization")
    assert org["sameAs"] == same
    footer = html.split('<footer class="site-footer"', 1)[1]
    for url in same:
        assert url in footer


def test_about_page_has_aboutpage_json_ld_and_placeholders():
    html = _client().get("/about").get_data(as_text=True)
    assert "AboutPage" in _types(html)
    about = next(n for n in _json_ld(html) if n["@type"] == "AboutPage")
    assert about["url"] == f"{SITE_URL}/about"
    visible = _visible_text(html)
    assert "Who we are" in visible
    assert "Who DocMaxxing is for" in visible
    assert "How we handle texts and privacy" in visible
    assert "support@docmaxxing.com" in visible
    assert "TODO" in visible


def test_blog_rss_feed_and_head_alternate():
    from services import blog

    res = _client().get("/blog/rss.xml")
    assert res.status_code == 200
    assert "rss" in (res.mimetype or "")
    xml = res.get_data(as_text=True)
    assert "<rss version=" in xml
    posts = blog.published_posts()
    assert posts
    assert f"<link>{SITE_URL}{posts[0].path}</link>" in xml
    assert "<lastmod>" not in xml  # RSS uses pubDate, not lastmod
    html = _client().get("/blog").get_data(as_text=True)
    assert 'rel="alternate" type="application/rss+xml"' in html
    assert 'href="/blog/rss.xml"' in html


def test_blog_post_shows_author_and_dates_in_html_and_json_ld():
    from services import blog

    post = blog.published_posts("en")[0]
    html = _client().get(post.path).get_data(as_text=True)
    assert post.author_name in html
    assert f'datetime="{post.date}"' in html
    article = next(n for n in _json_ld(html) if n["@type"] == "BlogPosting")
    assert article["datePublished"] == post.date
    assert article["dateModified"] == post.lastmod
    assert article["author"]["@type"] == "Organization"
    assert article["author"]["name"] == post.author_name
    crumbs = next(n for n in _json_ld(html) if n["@type"] == "BreadcrumbList")
    names = [c["name"] for c in crumbs["itemListElement"]]
    assert names[0] == "Home" and names[1] == "Blog"
