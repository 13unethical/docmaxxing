"""Blog posts from ``content/blog/*.md``.

Each file starts with a front matter block::

    ---
    title: What a 20% AI score in Turnitin means
    seo_title: Turnitin AI Score Explained | DocMaxxing   (optional, <= 60 chars)
    description: One or two sentences for search results (<= 155 chars).
    date: 2026-11-02
    updated: 2026-11-10                                   (optional)
    author: DocMaxxing Editorial                          (required to publish; drafts may omit)
    lang: en                                              (en -> /blog/<slug>, ru -> /ru/blog/<slug>)
    slug: turnitin-ai-score                               (optional, defaults to the file name)
    alternate: /ru/blog/some-slug                         (optional, same post in the other language)
    draft: true                                           (drafts are never published or listed)
    ---

The body is a small Markdown subset: ``##``/``###`` headings, paragraphs, ``-``/``1.`` lists,
``>`` quotes, fenced code, ``**bold**``, ``*italic*``, ```code``` and ``[links](/url)``.

Publishing gate (``publication_issues`` / tests): a non-draft post must have ``date``,
``author``, and must not contain the marker ``TODO-AMAL`` (see ``seo/ARTICLE_CHECKLIST.md``).
"""

from __future__ import annotations

import dataclasses
import html
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xml.sax.saxutils import escape as xml_escape

from services.seo import (
    DESCRIPTION_MAX,
    OG_IMAGE_DEFAULT,
    REPO_ROOT,
    SITE_NAME,
    SITE_URL,
    TITLE_MAX,
    PublicPage,
    absolute_url,
    canonical_url,
    og_image_path_for,
)

CONTENT_DIR = REPO_ROOT / "content" / "blog"
BLOG_INDEX_PATH = "/blog"


TODO_AMAL_MARKER = "TODO-AMAL"


@dataclass(frozen=True)
class Post:
    slug: str
    lang: str
    title: str
    seo_title: str
    description: str
    date: str
    updated: str | None
    author: str
    draft: bool
    html: str
    source: str
    raw: str = ""
    alternates: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> str:
        return f"/ru/blog/{self.slug}" if self.lang == "ru" else f"/blog/{self.slug}"

    @property
    def lastmod(self) -> str:
        return self.updated or self.date

    @property
    def author_name(self) -> str:
        """Visible + JSON-LD author name (front matter, else site name)."""
        return self.author or SITE_NAME

    def page(self) -> PublicPage:
        og = og_image_path_for(self.path)
        return PublicPage(
            path=self.path,
            title=self.seo_title,
            description=self.description,
            lang=self.lang,
            h1=self.title,
            og_image=og,
            breadcrumb=_short(self.title, 60),
            sources=(self.source,),
            alternates=dict(self.alternates),
            images=(og,),
        )

    def article_node(self) -> dict[str, Any]:
        author_name = self.author_name
        if author_name == SITE_NAME or author_name.lower().startswith("docmaxxing"):
            author: dict[str, Any] = {"@type": "Organization", "name": author_name, "url": SITE_URL}
        else:
            author = {"@type": "Person", "name": author_name}
        og_path = og_image_path_for(self.path)
        image = absolute_url(og_path if (REPO_ROOT / og_path.lstrip("/")).is_file() else OG_IMAGE_DEFAULT)
        return {
            "@type": "BlogPosting",
            "headline": _short(self.title, 110),
            "description": self.description,
            "datePublished": self.date,
            "dateModified": self.lastmod,
            "inLanguage": self.lang,
            "mainEntityOfPage": canonical_url(self.path),
            "url": canonical_url(self.path),
            "image": [image],
            "author": author,
            "publisher": {"@id": f"{SITE_URL}/#organization"},
        }


# ------------------------------------------------------------------ parsing

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _short(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,.:;—-")
    return cut + "…"


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict[str, Any] = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "\n".join(lines[i + 1 :])
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        lowered = value.lower()
        meta[key.strip().lower()] = True if lowered == "true" else False if lowered == "false" else value
    return {}, text


def parse_post(path: Path) -> Post | None:
    """A post from one Markdown file, or None when its front matter is incomplete."""
    raw = path.read_text(encoding="utf-8")
    meta, body = split_front_matter(raw)
    title = str(meta.get("title") or "").strip()
    description = str(meta.get("description") or "").strip()
    date = str(meta.get("date") or "").strip()
    lang = str(meta.get("lang") or "en").strip().lower()
    slug = str(meta.get("slug") or path.stem).strip().lower()
    if not title or not description or not _DATE.fullmatch(date) or lang not in ("en", "ru"):
        return None
    if not _SLUG.fullmatch(slug):
        return None
    updated = str(meta.get("updated") or "").strip()
    author = str(meta.get("author") or "").strip()
    seo_title = str(meta.get("seo_title") or "").strip()
    if not seo_title:
        with_brand = f"{title} | {SITE_NAME}"
        seo_title = with_brand if len(with_brand) <= TITLE_MAX else _short(title, TITLE_MAX)
    draft = meta.get("draft") is True
    post = Post(
        slug=slug,
        lang=lang,
        title=title,
        seo_title=_short(seo_title, TITLE_MAX),
        description=_short(description, DESCRIPTION_MAX),
        date=date,
        updated=updated if _DATE.fullmatch(updated) else None,
        author=author,
        draft=draft,
        html=render_markdown(body),
        source=_rel(path),
        raw=raw,
    )
    alternate = str(meta.get("alternate") or "").strip()
    if alternate.startswith(("/blog/", "/ru/blog/")):
        other = "ru" if lang == "en" else "en"
        post.alternates.update({lang: post.path, other: alternate})
    return post


def publication_issues(post: Post, *, raw: str | None = None) -> list[str]:
    """Reasons this post must not be published (empty = ok to set draft: false).

    Drafts may omit ``author`` and keep ``TODO-AMAL`` placeholders; published posts may not.
    ``date`` is already required to parse a post — we still report it if somehow blank.
    """
    issues: list[str] = []
    text = raw if raw is not None else (post.raw or "")
    if not (post.date or "").strip() or not _DATE.fullmatch(post.date.strip()):
        issues.append("missing or invalid date (need YYYY-MM-DD)")
    if not (post.author or "").strip():
        issues.append("missing author")
    if TODO_AMAL_MARKER in text:
        issues.append(f"unresolved {TODO_AMAL_MARKER} marker")
    return issues


def is_publishable(post: Post, *, raw: str | None = None) -> bool:
    return not publication_issues(post, raw=raw)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


# ------------------------------------------------------------------ markdown

_INLINE_CODE = re.compile(r"`([^`]+)`")
_ESCAPED = re.compile(r"\\([\\`*_\[\]()#>+\-.!])")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_OL_ITEM = re.compile(r"^\d+[.)]\s+")
_UL_ITEM = re.compile(r"^[-*+]\s+")


def _safe_href(url: str) -> str | None:
    if url.startswith(("/", "#", "https://", "http://", "mailto:")):
        return url
    return None


def _inline(text: str) -> str:
    codes: list[str] = []

    def stash(match: re.Match[str]) -> str:
        codes.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    def literal(match: re.Match[str]) -> str:
        codes.append(html.escape(match.group(1)))
        return f"\x00{len(codes) - 1}\x00"

    text = _INLINE_CODE.sub(stash, text)
    text = _ESCAPED.sub(literal, text)
    text = html.escape(text, quote=False)

    def link(match: re.Match[str]) -> str:
        href = _safe_href(html.unescape(match.group(2)))
        label = match.group(1)
        if href is None:
            return label
        external = href.startswith("http")
        attrs = ' rel="noopener"' if external else ""
        return f'<a href="{html.escape(href)}"{attrs}>{label}</a>'

    text = _LINK.sub(link, text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def _anchor(text: str, used: set[str]) -> str:
    base = re.sub(r"[^\w]+", "-", text.lower(), flags=re.UNICODE).strip("-") or "section"
    anchor, n = base, 2
    while anchor in used:
        anchor, n = f"{base}-{n}", n + 1
    used.add(anchor)
    return anchor


def render_markdown(text: str) -> str:
    out: list[str] = []
    para: list[str] = []
    items: list[str] = []
    list_tag: str | None = None
    quote: list[str] = []
    anchors: set[str] = set()
    lines = text.replace("\r\n", "\n").split("\n")

    def flush_para() -> None:
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    def flush_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append(f"<{list_tag}>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + f"</{list_tag}>")
            items.clear()
            list_tag = None

    def flush_quote() -> None:
        if quote:
            out.append(f"<blockquote><p>{_inline(' '.join(quote))}</p></blockquote>")
            quote.clear()

    def flush_all() -> None:
        flush_para()
        flush_list()
        flush_quote()

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        if line.startswith("```"):
            flush_all()
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
            i += 1
            continue
        if not line:
            flush_all()
        elif heading := _HEADING.match(line):
            flush_all()
            level = min(max(len(heading.group(1)), 2), 4)
            content = heading.group(2)
            plain = re.sub(r"[*`]", "", content)
            out.append(f'<h{level} id="{_anchor(plain, anchors)}">{_inline(content)}</h{level}>')
        elif line.startswith(">"):
            flush_para()
            flush_list()
            quote.append(line.lstrip(">").strip())
        elif _UL_ITEM.match(line) or _OL_ITEM.match(line):
            flush_para()
            flush_quote()
            tag = "ol" if _OL_ITEM.match(line) else "ul"
            if list_tag and list_tag != tag:
                flush_list()
            list_tag = tag
            items.append((_OL_ITEM if tag == "ol" else _UL_ITEM).sub("", line, count=1))
        elif list_tag and raw.startswith(("  ", "\t")):
            items[-1] += " " + line
        else:
            flush_list()
            flush_quote()
            para.append(line)
        i += 1
    flush_all()
    return "\n".join(out)


# ------------------------------------------------------------------ loading

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"key": None, "posts": []}


def _signature(directory: Path) -> tuple:
    if not directory.is_dir():
        return (str(directory),)
    return (str(directory),) + tuple(
        sorted((p.name, p.stat().st_mtime_ns) for p in directory.glob("*.md"))
    )


def all_posts() -> list[Post]:
    """Every parsable post, drafts included, newest first."""
    directory = Path(CONTENT_DIR)
    key = _signature(directory)
    with _cache_lock:
        if _cache["key"] == key:
            return list(_cache["posts"])
    posts = [p for p in (parse_post(f) for f in sorted(directory.glob("*.md"))) if p] if directory.is_dir() else []
    posts.sort(key=lambda p: (p.date, p.slug), reverse=True)
    with _cache_lock:
        _cache.update(key=key, posts=posts)
    return list(posts)


def published_posts(lang: str | None = None) -> list[Post]:
    """Non-draft posts that also pass the publish gate (no TODO-AMAL; date + author set)."""
    out: list[Post] = []
    for post in all_posts():
        if post.draft or (lang is not None and post.lang != lang):
            continue
        if publication_issues(post):
            continue
        out.append(post)
    return out


def find_post(lang: str, slug: str, *, include_drafts: bool = False) -> Post | None:
    for post in all_posts():
        if post.lang != lang or post.slug != slug:
            continue
        if include_drafts:
            return post
        if post.draft or publication_issues(post):
            continue
        return post
    return None


def index_page() -> PublicPage:
    og = og_image_path_for(BLOG_INDEX_PATH)
    return PublicPage(
        path=BLOG_INDEX_PATH,
        title="DocMaxxing Blog — AI Writing, Detection & Citations",
        description=(
            "Plain-English guides for students: how AI detectors work, what Turnitin AI scores "
            "mean, how to cite AI tools, and how to make your writing your own."
        ),
        h1="Blog",
        og_image=og,
        breadcrumb="Blog",
        images=(og,),
    )


def post_page(post: Post) -> PublicPage:
    """SEO entry for a post; hreflang links only point at published translations."""
    published = {p.path for p in published_posts()}
    alternates = post.alternates if all(path in published for path in post.alternates.values()) else {}
    return dataclasses.replace(post.page(), alternates=dict(alternates))


def page_for_path(path: str) -> PublicPage | None:
    """Registry entry for published blog pages (the index only once it lists posts)."""
    if path == BLOG_INDEX_PATH:
        return index_page() if published_posts() else None
    for post in published_posts():
        if post.path == path:
            return post_page(post)
    return None


def sitemap_pages() -> list[tuple[PublicPage, str | None]]:
    posts = published_posts()
    if not posts:
        return []
    pages: list[tuple[PublicPage, str | None]] = [(index_page(), max(p.lastmod for p in posts))]
    pages.extend((post_page(post), post.lastmod) for post in posts)
    return pages


_RU_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
_EN_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def display_date(date: str, lang: str) -> str:
    year, month, day = (int(part) for part in date.split("-"))
    months = _RU_MONTHS if lang == "ru" else _EN_MONTHS
    return f"{day} {months[month - 1]} {year}"


def _rss_pub_date(date: str) -> str:
    """RFC 822 date from YYYY-MM-DD (midnight UTC)."""
    from email.utils import formatdate
    from datetime import datetime, timezone

    year, month, day = (int(part) for part in date.split("-"))
    dt = datetime(year, month, day, tzinfo=timezone.utc)
    return formatdate(dt.timestamp(), usegmt=True)


def rss_xml() -> str:
    """RSS 2.0 feed of published posts (newest first)."""
    posts = published_posts()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        f"<title>{xml_escape(SITE_NAME)} Blog</title>",
        f"<link>{xml_escape(SITE_URL)}/blog</link>",
        f"<description>{xml_escape(index_page().description)}</description>",
        f"<language>en</language>",
    ]
    for post in posts:
        lines.extend(
            [
                "<item>",
                f"<title>{xml_escape(post.title)}</title>",
                f"<link>{xml_escape(canonical_url(post.path))}</link>",
                f'<guid isPermaLink="true">{xml_escape(canonical_url(post.path))}</guid>',
                f"<pubDate>{_rss_pub_date(post.date)}</pubDate>",
                f"<description>{xml_escape(post.description)}</description>",
                "</item>",
            ]
        )
    lines.extend(["</channel>", "</rss>", ""])
    return "\n".join(lines)
