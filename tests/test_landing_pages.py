"""Server-rendered landing pages: /, /humanizer, /ru/humanizer."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app import app
from services.seo import SITE_URL
from services.site_content import faq_items_for_path, plain_text

REPO = Path(__file__).resolve().parents[1]
LANDINGS = ["/", "/humanizer", "/ru/humanizer"]


def _client():
    app.config["TESTING"] = True
    return app.test_client()


def _html(path: str) -> str:
    res = _client().get(path)
    assert res.status_code == 200, path
    return res.get_data(as_text=True)


def _main_text(html: str) -> str:
    main = html.split("<main", 1)[1].split("</main>", 1)[0]
    main = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", main, flags=re.S)
    return plain_text(main)


def _graph(html: str) -> list[dict]:
    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    return json.loads(block)["@graph"]


@pytest.mark.parametrize(
    ("path", "h1", "lang"),
    [
        ("/humanizer", "Free AI Humanizer — Turn AI Text into Natural Writing", "en"),
        ("/ru/humanizer", "Хуманайзер текста онлайн бесплатно", "ru"),
        ("/", "AI Humanizer and Writing Tools for Students", "en"),
    ],
)
def test_landing_has_one_h1_and_lang(path, h1, lang):
    html = _html(path)
    assert html.count("<h1") == 1
    assert re.search(r"<h1[^>]*>(.*?)</h1>", html).group(1) == h1
    assert f'<html lang="{lang}">' in html
    robots = "noindex, follow" if path == "/ru/humanizer" else "index, follow"
    assert f'<meta name="robots" content="{robots}" />' in html


@pytest.mark.parametrize("path", LANDINGS)
def test_landing_is_complete_without_js(path):
    html = _html(path)
    words = len(_main_text(html).split())
    assert 800 <= words <= 1500, (path, words)
    assert "app2/app.js" not in html
    assert "app2/app.css" not in html
    for section in ("how-h", "faq-h"):
        assert f'id="{section}"' in html


@pytest.mark.parametrize("path", LANDINGS)
def test_widget_markup(path):
    html = _html(path)
    assert "data-lp-tool" in html
    assert 'id="lp-input"' in html
    assert 'id="lp-count"' in html
    assert 'id="lp-run"' in html
    assert 'id="lp-copy"' in html
    assert 'data-endpoint="/api/browser/providers/stealthwriter/humanize"' in html
    assert "landing/tool.js" in html
    assert "<noscript>" in html


def test_free_limit_text_comes_from_env(monkeypatch):
    assert "Free: up to 500 words, once a day" in _html("/humanizer")
    assert "Бесплатно: до 500 слов, 1 раз в день" in _html("/ru/humanizer")
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_WORDS", "700")
    monkeypatch.setenv("FREE_HUMANIZE_GUEST_DAILY", "5")
    assert "Free: up to 700 words, 5 times a day" in _html("/humanizer")
    assert "Бесплатно: до 700 слов, 5 раз в день" in _html("/ru/humanizer")
    assert 'data-max-words="700"' in _html("/humanizer")


def test_ru_widget_does_not_send_russian_text():
    html = _html("/ru/humanizer")
    assert 'data-block-cyrillic="1"' in html
    assert "/api/browser/providers/ru/humanize" not in html
    assert "Русскоязычный движок в разработке" in _main_text(html)
    assert 'data-block-cyrillic' not in _html("/humanizer")


def test_ru_humanizer_is_on_hold():
    for path in ("/humanizer", "/ru/humanizer"):
        assert 'hreflang="ru"' not in _html(path)
    assert '<meta name="robots" content="noindex, follow" />' in _html("/ru/humanizer")
    assert '<meta property="og:locale" content="ru_RU" />' in _html("/ru/humanizer")
    assert f'content="{SITE_URL}/static/og/humanizer.png"' in _html("/ru/humanizer")


@pytest.mark.parametrize("path", LANDINGS)
def test_faq_json_ld_matches_visible_faq(path):
    html = _html(path)
    graph = _graph(html)
    types = [n["@type"] for n in graph]
    assert "SoftwareApplication" in types
    faq = next(n for n in graph if n["@type"] == "FAQPage")
    items = faq_items_for_path(path)
    assert 8 <= len(items) <= 10
    visible = _main_text(html)
    assert len(faq["mainEntity"]) == len(items)
    for entity in faq["mainEntity"]:
        assert entity["name"] in visible
        assert entity["acceptedAnswer"]["text"] in visible
    if path != "/":
        assert "BreadcrumbList" in types


@pytest.mark.parametrize("path", LANDINGS)
def test_no_detector_evasion_promises(path):
    text = _main_text(_html(path)).lower()
    for phrase in ("undetectable", "bypass", "guaranteed", "100% human", "0% ai", "обход", "гарантированно",
                   "антиплагиат"):
        assert phrase not in text, (path, phrase)


@pytest.mark.parametrize("path", LANDINGS)
def test_internal_links_and_signup_event(path):
    html = _html(path)
    for href in ("/formatter", "/pricing", "/faq", "/blog", "/terms", "/privacy", "/contact"):
        assert f'href="{href}"' in html, (path, href)
    assert 'data-umami-event="landing_signup_click"' in html
    if path != "/ru/humanizer":
        assert 'href="/ru/humanizer"' not in html


def test_tool_js_is_dependency_free_and_tracks_runs():
    js = (REPO / "static" / "landing" / "tool.js").read_text(encoding="utf-8")
    assert "landing_humanize_run" in js
    assert "landing_signup_click" in js
    assert "import " not in js
    assert "http://" not in js and "https://" not in js
    assert "Создать аккаунт бесплатно" in js
    assert "Create a free account" in js


def test_landing_css_uses_font_display_swap():
    css = (REPO / "static" / "landing" / "landing.css").read_text(encoding="utf-8")
    assert "font-display: swap" in css
    assert (REPO / "static" / "landing" / "findsans-bold.woff2").is_file()


def test_every_sitemap_url_is_an_indexable_200():
    from services.seo import sitemap_xml

    client = _client()
    for loc in re.findall(r"<loc>(.*?)</loc>", sitemap_xml()):
        path = loc[len(SITE_URL):] or "/"
        res = client.get(path)
        assert res.status_code == 200, path
        html = res.get_data(as_text=True)
        assert '<meta name="robots" content="index, follow" />' in html, path
        assert f'<link rel="canonical" href="{loc}" />' in html, path
