"""RU/UZ public SSR localization: hreflang, canonical, sitemap, switcher."""

from __future__ import annotations

import re

from app import app
from services.seo import PUBLIC_PAGES, SITE_URL, page_seo_for_path, sitemap_xml
from services.seo_i18n import LOCALES, PAGE_KEYS, alternates_for, locale_path

LOCALE_PATHS = [locale_path(lang, key) for lang in ("ru", "uz") for key in PAGE_KEYS]


def _client():
    app.config["TESTING"] = True
    return app.test_client()


def _html(path: str) -> str:
    res = _client().get(path)
    assert res.status_code == 200, path
    return res.get_data(as_text=True)


def test_locale_paths_are_registered_and_indexable():
    for path in LOCALE_PATHS:
        assert path in PUBLIC_PAGES, path
        page = PUBLIC_PAGES[path]
        assert page.in_sitemap
        seo = page_seo_for_path(path)
        assert seo["robots"] == "index, follow"
        assert seo["canonical"] == (SITE_URL if path == "/" else f"{SITE_URL}{path}")
        assert seo["lang"] in {"ru", "uz"}


def test_hreflang_en_ru_uz_x_default_on_marketing_pages():
    for key in PAGE_KEYS:
        alts = alternates_for(key)
        assert set(alts) == set(LOCALES)
        for lang in LOCALES:
            path = alts[lang]
            seo = page_seo_for_path(path)
            hrefs = dict(seo["alternates"])
            assert hrefs["en"] == f"{SITE_URL}{alts['en']}" if alts["en"] != "/" else SITE_URL
            assert hrefs["ru"].endswith(alts["ru"])
            assert hrefs["uz"].endswith(alts["uz"])
            assert hrefs["x-default"] == (SITE_URL if alts["en"] == "/" else f"{SITE_URL}{alts['en']}")


def test_locale_pages_render_review_copy_and_lang():
    for path in ("/ru", "/uz", "/ru/ai-detector", "/uz/humanizer", "/ru/faq", "/uz/about"):
        html = _html(path)
        page = PUBLIC_PAGES[path]
        assert f'<html lang="{page.lang}">' in html
        assert f"<title>{page.title}" in html.replace("&amp;", "&")
        assert page.h1 in html
        assert "[REVIEW]" in html
        assert 'hreflang="en"' in html and 'hreflang="ru"' in html and 'hreflang="uz"' in html
        assert 'hreflang="x-default"' in html
        assert f'<link rel="canonical" href="{SITE_URL}{path}" />' in html
        assert f'<meta property="og:locale" content="{"ru_RU" if page.lang == "ru" else "uz_UZ"}" />' in html


def test_lang_switcher_is_plain_links_not_js_redirect():
    for path in ("/", "/humanizer", "/ru/pricing", "/uz/formatter"):
        html = _html(path)
        assert 'aria-label="Language"' in html or 'aria-label="Language"' in html.replace("Language", "Language")
        assert 'hreflang="ru"' in html
        assert 'hreflang="uz"' in html
        # No auto language redirect helpers in landing markup.
        assert "navigator.language" not in html
        assert "Accept-Language" not in html


def test_sitemap_includes_all_locale_versions_with_xhtml_links():
    xml = sitemap_xml()
    for path in LOCALE_PATHS:
        assert f"<loc>{SITE_URL}{path}</loc>" in xml, path
        block = xml.split(f"<loc>{SITE_URL}{path}</loc>", 1)[1].split("</url>", 1)[0]
        assert 'hreflang="en"' in block
        assert 'hreflang="ru"' in block
        assert 'hreflang="uz"' in block
        assert 'hreflang="x-default"' in block


def test_json_ld_in_language_includes_uz():
    html = _html("/uz/ai-detector")
    assert '"inLanguage": "uz"' in html or '"inLanguage":"uz"' in html
    home = _html("/")
    assert '"inLanguage": ["en", "ru", "uz"]' in home.replace(" ", "") or (
        '"en"' in home and '"ru"' in home and '"uz"' in home and "inLanguage" in home
    )


def test_llms_txt_lists_ru_uz():
    from services.seo import llms_txt

    text = llms_txt()
    for path in ("/ru", "/ru/humanizer", "/uz", "/uz/ai-detector", "/uz/formatter"):
        assert f"{SITE_URL}{path}" in text


def test_app_untouched_by_locale_routes():
    res = _client().get("/app")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert '<meta name="robots" content="noindex, follow" />' in html


def test_no_ip_or_browser_language_auto_redirect():
    client = _client()
    res = client.get("/", headers={"Accept-Language": "ru-RU,ru;q=0.9"})
    assert res.status_code == 200
    assert res.headers.get("Location") in (None, "")
    res = client.get("/humanizer", headers={"Accept-Language": "uz"})
    assert res.status_code == 200
    assert "/uz/" not in (res.headers.get("Location") or "")
