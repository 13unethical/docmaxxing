"""Markdown blog: front matter, drafts, routes, sitemap and Article JSON-LD."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from services import blog
from services.economy import auth as economy_auth
from services.economy import db as economy_db
from services.seo import SITE_URL, sitemap_xml

REPO = Path(__file__).resolve().parents[1]


def _client():
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


def _graph(html: str) -> list[dict]:
    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    return json.loads(block)["@graph"]


def _post(directory: Path, name: str, **meta: str) -> None:
    body = meta.pop("body", "## Section\n\nSome **bold** text and a [link](/humanizer).\n")
    lines = ["---", *(f"{k}: {v}" for k, v in meta.items()), "---", "", body]
    (directory / name).write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture()
def posts(tmp_path, monkeypatch):
    directory = tmp_path / "blog"
    directory.mkdir()
    _post(
        directory,
        "detectors.md",
        title="How detectors work",
        description="A short guide to AI detectors.",
        date="2026-10-01",
        updated="2026-10-20",
        lang="en",
        alternate="/ru/blog/detektory",
    )
    _post(
        directory,
        "detektory.md",
        title="Как работают детекторы",
        description="Коротко о детекторах ИИ.",
        date="2026-10-02",
        lang="ru",
        alternate="/blog/detectors",
    )
    _post(
        directory,
        "secret.md",
        title="Unfinished post",
        description="Not ready yet.",
        date="2026-10-03",
        lang="en",
        draft="true",
    )
    monkeypatch.setattr(blog, "CONTENT_DIR", directory)
    return directory


# --- the repository's own drafts ----------------------------------------------


def test_repo_drafts_exist_and_are_not_published():
    drafts = {p.slug: p for p in blog.all_posts() if p.draft}
    assert {"turnitin-ai-score-asterisk", "how-ai-detectors-work", "kak-procitirovat-chatgpt-apa-7"} <= set(drafts)
    assert drafts["kak-procitirovat-chatgpt-apa-7"].lang == "ru"
    client = _client()
    for post in drafts.values():
        assert client.get(post.path).status_code == 404, post.path
        assert post.path not in sitemap_xml()


def test_repo_posts_have_valid_metadata():
    for post in blog.all_posts():
        assert len(post.seo_title) <= 60, post.slug
        assert len(post.description) <= 155, post.slug
        text = re.sub(r"<[^>]+>", " ", post.html).lower()
        for phrase in ("undetectable", "bypass", "guaranteed", "гарантированно"):
            assert phrase not in text, (post.slug, phrase)


def test_empty_blog_index_is_200_but_noindex(tmp_path, monkeypatch):
    monkeypatch.setattr(blog, "CONTENT_DIR", tmp_path / "missing")
    res = _client().get("/blog")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert '<meta name="robots" content="noindex, follow" />' in html
    assert 'rel="canonical"' not in html
    assert f"<loc>{SITE_URL}/blog</loc>" not in sitemap_xml()


# --- parsing --------------------------------------------------------------------


def test_front_matter_and_defaults(tmp_path):
    _post(tmp_path, "my-post.md", title="Title", description="Desc", date="2026-01-02", draft="false")
    post = blog.parse_post(tmp_path / "my-post.md")
    assert post is not None
    assert (post.slug, post.lang, post.draft, post.path) == ("my-post", "en", False, "/blog/my-post")
    assert post.seo_title == "Title | DocMaxxing"
    assert post.lastmod == "2026-01-02"


def test_incomplete_front_matter_is_skipped(tmp_path):
    _post(tmp_path, "a.md", title="No date", description="Desc")
    _post(tmp_path, "b.md", title="Bad lang", description="Desc", date="2026-01-02", lang="de")
    (tmp_path / "c.md").write_text("No front matter at all", encoding="utf-8")
    assert all(blog.parse_post(tmp_path / n) is None for n in ("a.md", "b.md", "c.md"))


def test_long_titles_are_trimmed_for_search_results(tmp_path):
    _post(tmp_path, "long.md", title="word " * 30, description="d " * 120, date="2026-01-02")
    post = blog.parse_post(tmp_path / "long.md")
    assert len(post.seo_title) <= 60
    assert len(post.description) <= 155


def test_markdown_rendering_is_escaped_and_safe():
    out = blog.render_markdown(
        "# Top\n\nHello <script>x</script> *em* **strong** `a<b` \\*% "
        "[ok](/faq) [bad](javascript:alert)\n\n- one\n- two\n\n1. first\n\n> quote\n\n```\n<raw>\n```"
    )
    assert '<h2 id="top">Top</h2>' in out
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<em>em</em>" in out and "<strong>strong</strong>" in out
    assert "<code>a&lt;b</code>" in out
    assert "*%" in out
    assert '<a href="/faq">ok</a>' in out
    assert "javascript" not in out
    assert "<ul><li>one</li><li>two</li></ul>" in out
    assert "<ol><li>first</li></ol>" in out
    assert "<blockquote><p>quote</p></blockquote>" in out
    assert "<pre><code>&lt;raw&gt;</code></pre>" in out


# --- routes ---------------------------------------------------------------------


def test_index_lists_published_posts_only(posts):
    res = _client().get("/blog")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert '<meta name="robots" content="index, follow" />' in html
    assert f'<link rel="canonical" href="{SITE_URL}/blog" />' in html
    assert 'href="/blog/detectors"' in html
    assert 'href="/ru/blog/detektory"' in html
    assert "Unfinished post" not in html
    assert html.count("<h1") == 1


def test_post_page_meta_and_article_json_ld(posts):
    res = _client().get("/blog/detectors")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "<title>How detectors work | DocMaxxing</title>" in html
    assert '<meta property="og:type" content="article" />' in html
    assert f'<link rel="canonical" href="{SITE_URL}/blog/detectors" />' in html
    assert f'<link rel="alternate" hreflang="ru" href="{SITE_URL}/ru/blog/detektory" />' in html
    assert re.search(r"<h1[^>]*>How detectors work</h1>", html)
    assert '<a href="/humanizer">link</a>' in html
    graph = _graph(html)
    article = next(n for n in graph if n["@type"] == "BlogPosting")
    assert article["headline"] == "How detectors work"
    assert article["datePublished"] == "2026-10-01"
    assert article["dateModified"] == "2026-10-20"
    assert article["mainEntityOfPage"] == f"{SITE_URL}/blog/detectors"
    crumbs = next(n for n in graph if n["@type"] == "BreadcrumbList")["itemListElement"]
    assert [c["name"] for c in crumbs] == ["Home", "Blog", "How detectors work"]


def test_russian_post(posts):
    res = _client().get("/ru/blog/detektory")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert '<html lang="ru">' in html
    assert '<meta property="og:locale" content="ru_RU" />' in html
    crumbs = next(n for n in _graph(html) if n["@type"] == "BreadcrumbList")["itemListElement"]
    assert [c["name"] for c in crumbs][:2] == ["Главная", "Блог"]
    assert _client().get("/blog/detektory").status_code == 404


def test_drafts_are_hidden_from_guests_and_sitemap(posts):
    assert _client().get("/blog/secret").status_code == 404
    xml = sitemap_xml()
    assert "/blog/secret" not in xml
    assert f"<loc>{SITE_URL}/blog</loc>" in xml
    assert f"<loc>{SITE_URL}/blog/detectors</loc>" in xml
    assert "<lastmod>2026-10-20</lastmod>" in xml
    assert 'hreflang="ru" href="https://docmaxxing.com/ru/blog/detektory"' in xml


def test_admin_can_preview_a_draft_without_indexing(posts, tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    economy_db.init_db()
    user = economy_auth.create_user("blog-admin@example.com", "secret123")
    economy_auth.mark_email_verified(user["id"], user["email"])
    with economy_db.connect() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user["id"],))
    client = _client()
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    res = client.get("/blog/secret")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert '<meta name="robots" content="noindex, follow" />' in html
    assert "Draft" in html


def test_trailing_slash_redirects_for_published_posts(posts):
    res = _client().get("/blog/detectors/")
    assert res.status_code == 301
    assert res.headers["Location"].endswith("/blog/detectors")


def test_hreflang_is_dropped_when_translation_is_a_draft(posts):
    _post(
        posts,
        "detektory.md",
        title="Как работают детекторы",
        description="Коротко о детекторах ИИ.",
        date="2026-10-02",
        lang="ru",
        draft="true",
    )
    html = _client().get("/blog/detectors").get_data(as_text=True)
    assert '<link rel="alternate" hreflang="ru"' not in html
