"""Site-wide SEO metadata, sitemap, robots.txt and JSON-LD for public pages.

Search-engine verification tags are read from the environment at render time:
``GOOGLE_SITE_VERIFICATION``, ``YANDEX_VERIFICATION``, ``BING_SITE_VERIFICATION``
(the token only, not the whole <meta> tag). A tag is printed only when its variable is set.
"""

from __future__ import annotations

import functools
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape as xml_escape

SITE_URL = "https://docmaxxing.com"
SITE_NAME = "DocMaxxing"
REPO_ROOT = Path(__file__).resolve().parents[1]

TITLE_MAX = 60
DESCRIPTION_MAX = 155

DEFAULT_TITLE = "Free AI Detector & AI Humanizer for Students | DocMaxxing"
DEFAULT_DESCRIPTION = (
    "Check your essay for AI for free, see which sentences look AI-written, and humanize "
    "them into natural writing. Free formatting too. No sign-up needed."
)
DEFAULT_KEYWORDS = [
    "AI detector",
    "free AI detector",
    "AI humanizer",
    "free AI humanizer",
    "humanize AI text",
    "essay formatter",
]

OG_IMAGE_DEFAULT = "/static/og/default.png"
OG_IMAGE_HUMANIZER = "/static/og/humanizer.png"
OG_IMAGE_DETECTOR = "/static/og/ai-detector.png"
OG_IMAGE_SIZE = (1200, 630)

ROBOTS_INDEX = "index, follow"
ROBOTS_NOINDEX = "noindex, follow"

# Pages that must never show up in search results. They stay crawlable (not blocked in
# robots.txt) so crawlers can actually see the noindex tag.
NOINDEX_PATHS = frozenset({"/login", "/register", "/account", "/admin", "/ru/humanizer"})
NOINDEX_PREFIXES = ("/verify-email/", "/admin/")

_OG_LOCALES = {"en": "en_US", "ru": "ru_RU"}


@dataclass(frozen=True)
class PublicPage:
    path: str
    title: str
    description: str
    lang: str = "en"
    h1: str | None = None
    lede: str | None = None
    keywords: tuple[str, ...] = ()
    og_image: str = OG_IMAGE_DEFAULT
    # Name of this page in the BreadcrumbList; None = no breadcrumbs (home page).
    breadcrumb: str | None = None
    # Files whose last change is the page's <lastmod> in the sitemap.
    sources: tuple[str, ...] = ()
    software_app: bool = False
    # hreflang -> path of the same page in that language (this page included).
    alternates: dict[str, str] = field(default_factory=dict)
    in_sitemap: bool = True


def _info(path: str, template: str, title: str, description: str, crumb: str) -> PublicPage:
    return PublicPage(
        path=path,
        title=title,
        description=description,
        breadcrumb=crumb,
        sources=(f"templates/info/{template}",),
    )


_PAGES: tuple[PublicPage, ...] = (
    PublicPage(
        path="/",
        title=DEFAULT_TITLE,
        description=DEFAULT_DESCRIPTION,
        h1="AI Humanizer and Writing Tools for Students",
        keywords=tuple(DEFAULT_KEYWORDS),
        sources=("templates/app_v2.html", "static/app2/app.js", "services/site_content.py"),
        software_app=True,
    ),
    PublicPage(
        path="/ai-detector",
        title="Free AI Detector — Check Essays for AI | DocMaxxing",
        description=(
            "Free AI detector for students: paste your essay, get an AI score and see which "
            "sentences look AI-written. Tuned on real Turnitin reports. No sign-up."
        ),
        h1="Free AI Detector",
        keywords=("AI detector", "free AI detector", "AI checker", "check essay for AI", "ChatGPT detector"),
        og_image=OG_IMAGE_DETECTOR,
        breadcrumb="AI Detector",
        sources=("templates/app_v2.html", "static/app2/app.js", "services/site_content.py"),
        software_app=True,
    ),
    PublicPage(
        path="/humanizer",
        title="Free AI Humanizer — Humanize AI Text Online | DocMaxxing",
        description=(
            "Paste an AI draft and get natural, readable writing in seconds. Free AI humanizer "
            "for essays and reports — no sign-up needed for short texts."
        ),
        h1="Free AI Humanizer — Turn AI Text into Natural Writing",
        keywords=("AI humanizer", "free AI humanizer", "humanize AI text", "rewrite ChatGPT text"),
        og_image=OG_IMAGE_HUMANIZER,
        breadcrumb="AI Humanizer",
        sources=("templates/app_v2.html", "static/app2/app.js", "services/site_content.py"),
        software_app=True,
    ),
    # On hold (noindex, unlinked) until there is a real Russian engine.
    PublicPage(
        path="/ru/humanizer",
        title="Хуманайзер текста онлайн бесплатно | DocMaxxing",
        description=(
            "Хуманайзер текста: перепишите черновик после ChatGPT так, чтобы он звучал "
            "естественно. Английские тексты — уже сейчас, русский движок готовим."
        ),
        lang="ru",
        h1="Хуманайзер текста онлайн бесплатно",
        keywords=("хуманайзер", "хуманайзер текста", "очеловечить текст", "AI humanizer"),
        og_image=OG_IMAGE_HUMANIZER,
        breadcrumb="Хуманайзер",
        sources=("templates/landing/humanizer_ru.html", "templates/landing/base.html"),
        software_app=True,
        in_sitemap=False,
    ),
    PublicPage(
        path="/formatter",
        title="Free APA, MLA & Harvard Essay Formatter | DocMaxxing",
        description=(
            "Format an essay in APA 7, MLA 9, Harvard, Chicago or IEEE for free. Upload a DOCX "
            "or paste text — margins, headings and references are set for you."
        ),
        h1="Free Essay Formatter for APA, MLA, Harvard and Chicago",
        lede=(
            "Turn a rough draft into a submission-ready document with the right "
            "style profile, spacing, and reference layout."
        ),
        keywords=("essay formatter", "APA 7 formatter", "MLA formatter", "Harvard referencing"),
        breadcrumb="Essay Formatter",
        sources=("templates/format_v2.html", "templates/index.html"),
        software_app=True,
    ),
    PublicPage(
        path="/pricing",
        title="Pricing — Plans, Credit Packs & Free Tools | DocMaxxing",
        description=(
            "See what DocMaxxing costs: free formatting and free humanizer runs, monthly plans, "
            "and one-time credit packs for paid tools. No hidden fees."
        ),
        breadcrumb="Pricing",
        sources=("templates/pricing.html",),
    ),
    _info(
        "/about",
        "about.html",
        "About DocMaxxing — Academic Writing Tools for Students",
        "Who we are and what DocMaxxing does: a free essay formatter, an AI humanizer, AI checks, "
        "an editor, slides and assignment help in one place.",
        "About",
    ),
    _info(
        "/faq",
        "faq.html",
        "DocMaxxing FAQ — Humanizer, Credits, Formatting & Plans",
        "Answers about the AI humanizer and its free limits, free formatting, credits and plans, "
        "AI checks, Workspace, Slides, referrals and refunds.",
        "FAQ",
    ),
    _info(
        "/terms",
        "terms.html",
        "Terms and Conditions | DocMaxxing",
        "The rules for using DocMaxxing: accounts, credits and payments, Earn & Share, "
        "your content and academic integrity, acceptable use and liability.",
        "Terms and Conditions",
    ),
    _info(
        "/privacy",
        "privacy.html",
        "Privacy Policy | DocMaxxing",
        "What data DocMaxxing collects, how we use it, which processors see it, how long we "
        "keep it, and how to exercise your choices.",
        "Privacy Policy",
    ),
    _info(
        "/contact",
        "contact.html",
        "Contact DocMaxxing Support — Email, WhatsApp, Telegram",
        "Reach DocMaxxing support by email, WhatsApp or in-app chat. Hours, what to include in "
        "your message, sales and custom credit requests.",
        "Contact",
    ),
    _info(
        "/credits",
        "credits.html",
        "How Credits Work — Costs per Tool | DocMaxxing",
        "How DocMaxxing credits work: the welcome bonus, what each paid action costs, packages, "
        "earning credits without buying, and refunds for failed runs.",
        "Credits",
    ),
    _info(
        "/account-info",
        "account.html",
        "Your DocMaxxing Account — Profile, Security, Access",
        "What a free DocMaxxing account unlocks, which profile settings you can change, and how "
        "we keep your sign-in and documents secure.",
        "Account",
    ),
    _info(
        "/disclaimer",
        "disclaimer.html",
        "Disclaimer — Limits of AI Outputs | DocMaxxing",
        "Important limits of DocMaxxing outputs: AI and detection scores, the assignment "
        "pipeline, formatting checks and third-party services.",
        "Disclaimer",
    ),
    _info(
        "/payment-policy",
        "payment.html",
        "Payment Policy | DocMaxxing",
        "Who can pay, what you pay for, which processors handle checkout, when credits appear, "
        "and what happens with failed paid actions or chargebacks.",
        "Payment Policy",
    ),
    _info(
        "/delivery-policy",
        "delivery.html",
        "Delivery Policy — Digital Outputs | DocMaxxing",
        "How DocMaxxing delivers digital results: instant delivery, assignment packaging, "
        "delivery times, failed deliveries and how long files are kept.",
        "Delivery Policy",
    ),
    _info(
        "/refund-policy",
        "refund.html",
        "Refund Policy | DocMaxxing",
        "Purchases are final, plans can be cancelled any time, and credits for failed actions "
        "return automatically. Billing errors and chargebacks explained.",
        "Refund Policy",
    ),
    _info(
        "/changelog",
        "changelog.html",
        "Changelog — Product Updates | DocMaxxing",
        "What changed in DocMaxxing, newest first: new tools, humanizer and formatter "
        "improvements, assignment quality work and billing updates.",
        "Changelog",
    ),
)

PUBLIC_PAGES: dict[str, PublicPage] = {page.path: page for page in _PAGES}

# Public pages served to guests instead of the app (signed-in users go to /app#/<screen>).
GUEST_LANDING_PATHS = frozenset({"/", "/humanizer", "/ru/humanizer", "/pricing", "/formatter"})
# Without those pages, guests get the app's own landing at these URLs (no redirect), opened on
# the matching tool and with the page's text already in the HTML for crawlers.
APP_LANDING_PATHS = frozenset({"/", "/ai-detector", "/humanizer"})


def normalize_path(path: str | None) -> str:
    path = (path or "/").split("?", 1)[0] or "/"
    return path.rstrip("/") or "/"


def canonical_url(path: str) -> str:
    path = normalize_path(path)
    return SITE_URL if path == "/" else f"{SITE_URL}{path}"


def absolute_url(path: str) -> str:
    return path if path.startswith("http") else f"{SITE_URL}{path}"


def page_lang(path: str) -> str:
    path = normalize_path(path)
    return "ru" if path == "/ru" or path.startswith("/ru/") else "en"


def guest_landings_enabled() -> bool:
    """Server-rendered landing pages for guests. Off: guests go straight to the app."""
    return (os.environ.get("GUEST_LANDING_PAGES") or "").strip().lower() in {"1", "true", "yes"}


def is_noindex_path(path: str) -> bool:
    raw = (path or "/").split("?", 1)[0] or "/"
    norm = normalize_path(raw)
    if norm in NOINDEX_PATHS or (norm == "/app" and guest_landings_enabled()):
        return True
    return any(raw.startswith(prefix) for prefix in NOINDEX_PREFIXES)


def is_public_path(path: str) -> bool:
    """Indexable pages (static registry plus published blog posts)."""
    path = normalize_path(path)
    if path in PUBLIC_PAGES:
        return True
    from services import blog

    return blog.page_for_path(path) is not None


def verification_tags() -> dict[str, str]:
    tags = {
        "google": (os.environ.get("GOOGLE_SITE_VERIFICATION") or "").strip(),
        "yandex": (os.environ.get("YANDEX_VERIFICATION") or "").strip(),
        "bing": (os.environ.get("BING_SITE_VERIFICATION") or "").strip(),
    }
    return {name: value for name, value in tags.items() if value}


def _keywords_csv(keywords: Iterable[str] | None = None) -> str:
    return ", ".join(keywords or DEFAULT_KEYWORDS)


def page_seo_for_path(
    path: str,
    *,
    args: Any = None,
    page: PublicPage | None = None,
    robots: str | None = None,
    faq: list[tuple[str, str]] | None = None,
    extra_nodes: list[dict[str, Any]] | None = None,
    og_type: str = "website",
) -> dict[str, Any]:
    """Build template context for <head> meta tags, Open Graph and JSON-LD.

    ``page`` overrides the registry entry (blog posts); ``faq`` adds an FAQPage whose
    question/answer text must equal what the page shows.
    """
    norm = normalize_path(path)
    if page is None:
        page = PUBLIC_PAGES.get(norm)
        if page is None:
            from services import blog

            page = blog.page_for_path(norm)
    if faq is None and page is not None:
        from services.site_content import faq_for_path

        faq = faq_for_path(page.path)

    if robots is None:
        classic = bool(args is not None and str(args.get("classic") or "") == "1")
        robots = ROBOTS_NOINDEX if (is_noindex_path(path) or classic) else ROBOTS_INDEX
    indexable = robots == ROBOTS_INDEX

    lang = page.lang if page else page_lang(norm)
    title = page.title if page else DEFAULT_TITLE
    description = page.description if page else DEFAULT_DESCRIPTION
    keywords = list(page.keywords) if page and page.keywords else list(DEFAULT_KEYWORDS)
    # Without landing pages the app is what guests see at "/".
    canonical = canonical_url("/" if norm == "/app" else norm) if indexable else None
    og_image = absolute_url(page.og_image if page else OG_IMAGE_DEFAULT)
    alternates = [
        (hreflang, canonical_url(alt_path)) for hreflang, alt_path in (page.alternates if page else {}).items()
    ]
    if alternates:
        alternates.append(("x-default", canonical_url(page.alternates.get("en", page.path))))
    og_locale = _OG_LOCALES.get(lang, "en_US")
    og_locale_alternates = [
        _OG_LOCALES[h] for h, _ in alternates if h in _OG_LOCALES and _OG_LOCALES[h] != og_locale
    ]

    return {
        "site_name": SITE_NAME,
        "site_url": SITE_URL,
        "title": title,
        "description": description,
        "h1": page.h1 if page else None,
        "lede": page.lede if page else None,
        "keywords": keywords,
        "keywords_csv": _keywords_csv(keywords),
        "canonical": canonical,
        "robots": robots,
        "lang": lang,
        "alternates": alternates if indexable else [],
        "og_title": title,
        "og_description": description,
        "og_url": canonical or canonical_url(norm),
        "og_type": og_type,
        "og_image": og_image,
        "og_image_width": OG_IMAGE_SIZE[0],
        "og_image_height": OG_IMAGE_SIZE[1],
        "og_image_alt": title,
        "og_locale": og_locale,
        "og_locale_alternates": og_locale_alternates,
        "twitter_card": "summary_large_image",
        "verification": verification_tags(),
        "json_ld": json_ld_script(build_json_ld(norm, page=page, faq=faq, extra_nodes=extra_nodes)),
    }


def json_ld_script(data: dict[str, Any]) -> str:
    """JSON for a <script type="application/ld+json"> body; "</" cannot close the tag early."""
    return json.dumps(data, ensure_ascii=False, indent=None).replace("</", "<\\/")


def _organization_ids() -> tuple[str, str]:
    return f"{SITE_URL}/#organization", f"{SITE_URL}/#website"


def build_json_ld(
    path: str = "/",
    *,
    page: PublicPage | None = None,
    faq: list[tuple[str, str]] | None = None,
    extra_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Schema.org graph: Organization + WebSite, plus per-page SoftwareApplication,
    BreadcrumbList, FAQPage and any extra nodes (Article for blog posts)."""
    org_id, website_id = _organization_ids()
    graph: list[dict[str, Any]] = [
        {
            "@type": "Organization",
            "@id": org_id,
            "name": SITE_NAME,
            "url": SITE_URL,
            "logo": {"@type": "ImageObject", "url": f"{SITE_URL}/icon.png"},
            "sameAs": [
                "https://t.me/docmaxxing",
                "https://www.instagram.com/doc.maxxing",
                "https://www.youtube.com/@docmaxxing",
                "https://x.com/docmaxxing",
                "https://www.tiktok.com/@docmaxxing",
            ],
        },
        {
            "@type": "WebSite",
            "@id": website_id,
            "url": SITE_URL,
            "name": SITE_NAME,
            "description": DEFAULT_DESCRIPTION,
            "publisher": {"@id": org_id},
            "inLanguage": ["en", "ru"],
        },
    ]
    if page is not None:
        url = canonical_url(page.path)
        if page.software_app:
            graph.append(
                {
                    "@type": "SoftwareApplication",
                    "name": page.h1 or page.title,
                    "url": url,
                    "applicationCategory": "EducationalApplication",
                    "operatingSystem": "Web",
                    "inLanguage": page.lang,
                    "publisher": {"@id": org_id},
                    "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
                }
            )
        if page.breadcrumb:
            home = "Главная" if page.lang == "ru" else "Home"
            crumbs = [(home, SITE_URL)]
            if page.path.startswith(("/blog/", "/ru/blog/")):
                crumbs.append(("Блог" if page.lang == "ru" else "Blog", f"{SITE_URL}/blog"))
            crumbs.append((page.breadcrumb, url))
            graph.append(
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": i, "name": name, "item": item}
                        for i, (name, item) in enumerate(crumbs, start=1)
                    ],
                }
            )
    if faq:
        graph.append(
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": question,
                        "acceptedAnswer": {"@type": "Answer", "text": answer},
                    }
                    for question, answer in faq
                ],
            }
        )
    graph.extend(extra_nodes or [])
    return {"@context": "https://schema.org", "@graph": graph}


# ------------------------------------------------------------------ sitemap


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


@functools.lru_cache(maxsize=512)
def file_lastmod(rel_path: str) -> str | None:
    """Date (YYYY-MM-DD) the file last changed: its last commit, or mtime when it has
    uncommitted edits or git is unavailable. None if the file does not exist."""
    path = REPO_ROOT / rel_path
    if not path.is_file():
        return None
    if not _git("status", "--porcelain", "--", rel_path):
        committed = _git("log", "-1", "--format=%cs", "--", rel_path)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", committed):
            return committed
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")


def page_lastmod(page: PublicPage) -> str | None:
    dates = [d for d in (file_lastmod(src) for src in page.sources) if d]
    return max(dates) if dates else None


@dataclass(frozen=True)
class SitemapEntry:
    path: str
    lastmod: str | None
    alternates: dict[str, str] = field(default_factory=dict)


def sitemap_entries() -> list[SitemapEntry]:
    from services import blog

    landings = guest_landings_enabled()
    entries = [
        SitemapEntry(page.path, page_lastmod(page), dict(page.alternates))
        for page in _PAGES
        if page.in_sitemap
        and (page.path in APP_LANDING_PATHS or landings or page.path not in GUEST_LANDING_PATHS)
    ]
    for post_page, lastmod in blog.sitemap_pages():
        entries.append(SitemapEntry(post_page.path, lastmod, dict(post_page.alternates)))
    return entries


def sitemap_xml() -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]
    for entry in sitemap_entries():
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(canonical_url(entry.path))}</loc>")
        if entry.lastmod:
            lines.append(f"    <lastmod>{entry.lastmod}</lastmod>")
        if entry.alternates:
            links = list(entry.alternates.items())
            links.append(("x-default", entry.alternates.get("en", entry.path)))
            for hreflang, alt_path in links:
                lines.append(
                    f'    <xhtml:link rel="alternate" hreflang="{hreflang}" '
                    f'href="{xml_escape(canonical_url(alt_path))}"/>'
                )
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def robots_txt() -> str:
    return "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /api/",
            "",
            f"Sitemap: {SITE_URL}/sitemap.xml",
            "",
        ]
    )


def webmanifest() -> dict[str, Any]:
    return {
        "name": SITE_NAME,
        "short_name": SITE_NAME,
        "description": DEFAULT_DESCRIPTION,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0b0b0f",
        "theme_color": "#0b0b0f",
        "icons": [
            {"src": "/static/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
            {"src": "/static/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
