"""Site-wide SEO metadata, sitemap, and JSON-LD for public pages."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SITE_URL = "https://docmaxxing.com"
SITE_NAME = "DocMaxxing"

DEFAULT_TITLE = (
    "DocMaxxing — #1 Academic AI Tools: Humanizer, Formatter & Assignment Helper"
)
DEFAULT_DESCRIPTION = (
    "Bypass Turnitin AI detection, format essays to APA/MLA in 1 click, "
    "and solve assignments with DocMaxxing. Built for university students."
)
DEFAULT_KEYWORDS = [
    "AI humanizer",
    "bypass Turnitin",
    "essay formatter",
    "APA 7 generator",
    "assignment helper",
]

SITEMAP_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("/", "daily", "1.0"),
    ("/humanizer", "weekly", "0.9"),
    ("/formatter", "weekly", "0.9"),
    ("/assignments", "weekly", "0.85"),
    ("/pricing", "monthly", "0.8"),
)

_PAGE_OVERRIDES: dict[str, dict[str, Any]] = {
    "/": {
        "title": DEFAULT_TITLE,
        "description": DEFAULT_DESCRIPTION,
    },
    "/humanizer": {
        "title": "Undetectable AI Humanizer — Bypass Turnitin | DocMaxxing",
        "description": (
            "Humanize ChatGPT and AI essays to pass Turnitin and GPTZero. "
            "Paste or upload text — get natural, undetectable academic writing in seconds."
        ),
        "h1": "Undetectable AI Humanizer — Bypass Turnitin & GPTZero",
        "lede": (
            "Rewrite AI-detected paragraphs into natural student voice. "
            "Built for essays, reports, and coursework."
        ),
        "keywords": [
            "AI humanizer",
            "bypass Turnitin",
            "GPTZero",
            "undetectable AI",
            "humanize ChatGPT",
        ],
    },
    "/formatter": {
        "title": "APA/MLA Essay Formatter & Citation Generator | DocMaxxing",
        "description": (
            "Format essays to APA 7, MLA 9, Harvard, Chicago, or IEEE in one click. "
            "Upload DOCX or paste text — citations, margins, and headings done for you."
        ),
        "h1": "Automatic Academic Essay Formatter (APA, MLA, Harvard, Chicago)",
        "lede": (
            "Turn a rough draft into a submission-ready document with the right "
            "style profile, spacing, and reference layout."
        ),
        "keywords": [
            "essay formatter",
            "APA 7 generator",
            "MLA formatter",
            "citation generator",
            "Harvard referencing",
        ],
    },
    "/assignment": {
        "title": "AI Assignment Helper & Homework Solver | DocMaxxing",
        "description": (
            "Upload your brief and get a researched, cited, formatted assignment. "
            "Transparent pricing, step-by-step progress, and free revisions."
        ),
        "h1": "AI Assignment Helper — Step-by-Step College Homework Assistant",
        "lede": (
            "From lecturer brief to finished DOCX — research, writing, humanizing, "
            "and formatting in one guided workflow."
        ),
        "keywords": [
            "assignment helper",
            "homework solver",
            "AI essay writer",
            "college assignment",
            "coursework help",
        ],
    },
    "/assignments": {
        "title": "AI Assignment Helper & Homework Solver | DocMaxxing",
        "description": (
            "Upload your brief and get a researched, cited, formatted assignment. "
            "Transparent pricing, step-by-step progress, and free revisions."
        ),
        "h1": "AI Assignment Helper — Step-by-Step College Homework Assistant",
        "lede": (
            "From lecturer brief to finished DOCX — research, writing, humanizing, "
            "and formatting in one guided workflow."
        ),
        "keywords": [
            "assignment helper",
            "homework solver",
            "AI essay writer",
            "college assignment",
            "coursework help",
        ],
    },
    "/pricing": {
        "title": "Pricing — Simple Credit Packs | DocMaxxing",
        "description": (
            "Pay only for what you use. Credit packs for Humanizer, Turnitin checks, "
            "Formatting, and full Assignment help — no subscription."
        ),
    },
    "/turnitin": {
        "title": "Turnitin Similarity & AI Check | DocMaxxing",
        "description": (
            "Submit essays for similarity and AI detection reports. "
            "Fast Turnitin-style checks with downloadable PDF results."
        ),
    },
    "/check": {
        "title": "Academic Check — Draft vs Assignment Brief | DocMaxxing",
        "description": (
            "Compare your draft to your assignment brief for free. "
            "Get a readiness score, missing requirements, and an action plan."
        ),
    },
}


def _keywords_csv(keywords: list[str] | None = None) -> str:
    return ", ".join(keywords or DEFAULT_KEYWORDS)


def _canonical_url(path: str) -> str:
    path = (path or "/").split("?", 1)[0].rstrip("/") or "/"
    if path == "/":
        return SITE_URL
    return f"{SITE_URL}{path}"


def page_seo_for_path(path: str) -> dict[str, Any]:
    """Build template context for <head> meta tags and Open Graph."""
    path = (path or "/").split("?", 1)[0] or "/"
    override = _PAGE_OVERRIDES.get(path, {})
    title = str(override.get("title") or DEFAULT_TITLE)
    description = str(override.get("description") or DEFAULT_DESCRIPTION)
    keywords = list(override.get("keywords") or DEFAULT_KEYWORDS)
    canonical = _canonical_url(path)
    og_image = f"{SITE_URL}/icon.png"

    return {
        "site_name": SITE_NAME,
        "site_url": SITE_URL,
        "title": title,
        "description": description,
        "h1": override.get("h1"),
        "lede": override.get("lede"),
        "keywords": keywords,
        "keywords_csv": _keywords_csv(keywords),
        "canonical": canonical,
        "og_title": title,
        "og_description": description,
        "og_url": canonical,
        "og_type": "website",
        "og_image": og_image,
        "twitter_card": "summary_large_image",
        "json_ld": json.dumps(build_json_ld(), ensure_ascii=False),
    }


def build_json_ld() -> dict[str, Any]:
    """Schema.org WebSite + Organization graph for rich results / sitelinks."""
    org_id = f"{SITE_URL}/#organization"
    website_id = f"{SITE_URL}/#website"
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": org_id,
                "name": SITE_NAME,
                "url": SITE_URL,
                "logo": {
                    "@type": "ImageObject",
                    "url": f"{SITE_URL}/icon.png",
                },
            },
            {
                "@type": "WebSite",
                "@id": website_id,
                "url": SITE_URL,
                "name": SITE_NAME,
                "description": DEFAULT_DESCRIPTION,
                "publisher": {"@id": org_id},
                "inLanguage": "en",
            },
        ],
    }


def sitemap_xml() -> str:
    lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, changefreq, priority in SITEMAP_ENTRIES:
        loc = SITE_URL if path == "/" else f"{SITE_URL}{path}"
        lines.extend(
            [
                "  <url>",
                f"    <loc>{loc}</loc>",
                f"    <lastmod>{lastmod}</lastmod>",
                f"    <changefreq>{changefreq}</changefreq>",
                f"    <priority>{priority}</priority>",
                "  </url>",
            ]
        )
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def robots_txt() -> str:
    return "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "",
            f"Sitemap: {SITE_URL}/sitemap.xml",
            "",
        ]
    )
