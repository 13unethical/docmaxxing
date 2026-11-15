"""Admin Blog CMS for the SPA (#/blog) — persisted under data/, synced to public feed.

Publishing writes:
  1. data/spa_blog_cms.json — full draft/schedule/published admin state
  2. content/blog/<slug>.md — so classic /blog/<slug> also goes live
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import date
from html import unescape
from pathlib import Path
from typing import Any

from services.seo import REPO_ROOT

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
CMS_PATH = REPO_ROOT / "data" / "spa_blog_cms.json"
SEED_PATH = REPO_ROOT / "static" / "app2" / "blog_posts.json"
CONTENT_DIR = REPO_ROOT / "content" / "blog"

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TAG = re.compile(r"<[^>]+>")


def _default_meta() -> dict[str, Any]:
    if SEED_PATH.is_file():
        try:
            raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))
            return {
                "title": raw.get("title") or "Guides for better papers",
                "subtitle": raw.get("subtitle") or "",
                "landTitle": raw.get("landTitle") or "",
                "author": raw.get("author") or "DocMaxxing team",
                "bannerTitle": raw.get("bannerTitle") or "",
                "bannerText": raw.get("bannerText") or "",
                "cats": raw.get("cats") or [["all", "All"], ["ai", "AI detection"]],
            }
        except Exception:  # noqa: BLE001
            logger.exception("spa blog seed meta failed")
    return {
        "title": "Guides for better papers",
        "subtitle": "",
        "landTitle": "Practical guides for your next paper",
        "author": "DocMaxxing team",
        "bannerTitle": "Check your paper before you submit",
        "bannerText": "",
        "cats": [["all", "All"], ["ai", "AI detection"]],
    }


def _seed_posts() -> list[dict[str, Any]]:
    if not SEED_PATH.is_file():
        return []
    try:
        raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.exception("spa blog seed posts failed")
        return []
    out: list[dict[str, Any]] = []
    for p in raw.get("posts") or []:
        slug = str(p.get("slug") or "").strip()
        if not slug:
            continue
        out.append(
            {
                "id": slug,
                "title": p.get("title") or slug,
                "slug": slug,
                "dek": p.get("dek") or "",
                "html": p.get("html") or "",
                "status": "published",
                "publishedAt": p.get("date") or date.today().isoformat(),
                "scheduledAt": "",
                "views30": 0,
                "cover": p.get("cover") or {},
                "topic": p.get("cat") or "ai",
                "tool": "",
                "toolPlace": "aside",
                "seoTitle": p.get("title") or "",
                "seoDesc": p.get("dek") or "",
                "ogTitle": p.get("title") or "",
                "ogDesc": p.get("dek") or "",
                "min": int(p.get("min") or 5),
                "cta": p.get("cta") or "try",
            }
        )
    return out


def _read_cms() -> dict[str, Any]:
    if CMS_PATH.is_file():
        try:
            data = json.loads(CMS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("posts"), list):
                return data
        except Exception:  # noqa: BLE001
            logger.exception("spa blog cms read failed")
    return {"meta": _default_meta(), "posts": _seed_posts()}


def _write_cms(data: dict[str, Any]) -> None:
    CMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CMS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(CMS_PATH)


def list_admin_posts() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_read_cms().get("posts") or [])


def save_admin_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for raw in posts or []:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug") or "").strip().lower()
        title = str(raw.get("title") or "").strip() or "Untitled"
        if not slug:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "article"
        if not _SLUG.fullmatch(slug):
            slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-") or "article"
        status = str(raw.get("status") or "draft")
        if status not in {"draft", "scheduled", "published"}:
            status = "draft"
        cleaned.append(
            {
                "id": str(raw.get("id") or slug),
                "title": title,
                "slug": slug,
                "dek": str(raw.get("dek") or ""),
                "html": str(raw.get("html") or ""),
                "status": status,
                "publishedAt": str(raw.get("publishedAt") or ""),
                "scheduledAt": str(raw.get("scheduledAt") or ""),
                "views30": int(raw.get("views30") or 0),
                "cover": raw.get("cover") if isinstance(raw.get("cover"), dict) else {},
                "topic": str(raw.get("topic") or ""),
                "tool": str(raw.get("tool") or ""),
                "toolPlace": str(raw.get("toolPlace") or "aside"),
                "seoTitle": str(raw.get("seoTitle") or title),
                "seoDesc": str(raw.get("seoDesc") or raw.get("dek") or ""),
                "ogTitle": str(raw.get("ogTitle") or title),
                "ogDesc": str(raw.get("ogDesc") or raw.get("dek") or ""),
                "min": max(1, int(raw.get("min") or 5)),
                "cta": str(raw.get("cta") or "try"),
            }
        )
    with _LOCK:
        data = _read_cms()
        data["posts"] = cleaned
        data["meta"] = data.get("meta") or _default_meta()
        _write_cms(data)
        _sync_public_markdown(cleaned)
        # Invalidate classic blog cache so new md shows up.
        try:
            from services import blog as classic_blog

            classic_blog._cache.update(key=None, posts=[])  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
        return list(cleaned)


def public_boot() -> dict[str, Any]:
    """Payload for SPA BOOT.blog — published posts only."""
    with _LOCK:
        data = _read_cms()
    meta = data.get("meta") or _default_meta()
    posts = []
    for p in data.get("posts") or []:
        if p.get("status") != "published":
            continue
        posts.append(
            {
                "slug": p["slug"],
                "title": p["title"],
                "dek": p.get("dek") or "",
                "date": p.get("publishedAt") or date.today().isoformat(),
                "min": int(p.get("min") or 5),
                "cat": p.get("topic") or "ai",
                "cover": p.get("cover") or {},
                "html": p.get("html") or "",
                "path": f"/blog/{p['slug']}",
                "cta": p.get("cta") or "try",
            }
        )
    posts.sort(key=lambda x: (x.get("date") or "", x.get("slug") or ""), reverse=True)
    return {**meta, "posts": posts}


def _html_to_markdown_body(html: str) -> str:
    """Best-effort HTML → markdown so classic /blog can render CMS posts."""
    text = html or ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)<p[^>]*>", "", text)
    text = re.sub(r"(?i)<h2[^>]*>", "\n## ", text)
    text = re.sub(r"(?i)</h2\s*>", "\n\n", text)
    text = re.sub(r"(?i)<h3[^>]*>", "\n### ", text)
    text = re.sub(r"(?i)</h3\s*>", "\n\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?i)</?(ul|ol)[^>]*>", "\n", text)
    text = re.sub(r"(?i)<strong[^>]*>|<b[^>]*>", "**", text)
    text = re.sub(r"(?i)</strong\s*>|</b\s*>", "**", text)
    text = re.sub(r"(?i)<em[^>]*>|<i[^>]*>", "*", text)
    text = re.sub(r"(?i)</em\s*>|</i\s*>", "*", text)
    text = re.sub(
        r'(?i)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        lambda m: f"[{unescape(_TAG.sub('', m.group(2)))}]({m.group(1)})",
        text,
    )
    text = _TAG.sub("", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or "…"


def _sync_public_markdown(posts: list[dict[str, Any]]) -> None:
    """Write/update/delete CMS-managed markdown files under content/blog/."""
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    managed = {p.name for p in CONTENT_DIR.glob("*.cms.md")}
    keep: set[str] = set()
    for p in posts:
        if p.get("status") != "published":
            continue
        slug = p["slug"]
        name = f"{slug}.cms.md"
        keep.add(name)
        body = _html_to_markdown_body(str(p.get("html") or ""))
        desc = (p.get("seoDesc") or p.get("dek") or p["title"])[:155]
        pub = p.get("publishedAt") or date.today().isoformat()
        seo_title = (p.get("seoTitle") or p["title"])[:60]
        md = (
            "---\n"
            f"title: {p['title']}\n"
            f"seo_title: {seo_title}\n"
            f"description: {desc}\n"
            f"date: {pub}\n"
            f"lang: en\n"
            f"slug: {slug}\n"
            "---\n\n"
            f"{body}\n"
        )
        path = CONTENT_DIR / name
        try:
            path.write_text(md, encoding="utf-8")
        except Exception:  # noqa: BLE001
            logger.exception("spa blog markdown write failed slug=%s", slug)
    for stale in managed - keep:
        try:
            (CONTENT_DIR / stale).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            logger.exception("spa blog markdown delete failed name=%s", stale)
