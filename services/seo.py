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

# Public social / profile links — single source for Organization.sameAs and site footers.
# TODO: add Knowledge Graph profiles (Wikipedia, Wikidata, LinkedIn, Crunchbase) when available.
SOCIAL_LINKS: tuple[dict[str, str], ...] = (
    {"label": "Telegram", "url": "https://t.me/docmaxxing", "icon": "telegram"},
    {"label": "Instagram", "url": "https://www.instagram.com/doc.maxxing", "icon": "instagram"},
    {"label": "YouTube", "url": "https://www.youtube.com/@docmaxxing", "icon": "youtube"},
    {"label": "X", "url": "https://x.com/docmaxxing", "icon": "xlogo"},
    {"label": "TikTok", "url": "https://www.tiktok.com/@docmaxxing", "icon": "tiktok"},
)


def organization_same_as() -> list[str]:
    """https profile URLs for Organization.sameAs (skips mailto: and empty entries)."""
    return [item["url"] for item in SOCIAL_LINKS if str(item.get("url") or "").startswith("http")]

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

OG_IMAGE_DEFAULT = "/static/og/home.webp"
OG_IMAGE_HUMANIZER = "/static/og/ai-humanizer.webp"
OG_IMAGE_DETECTOR = "/static/og/ai-detector.webp"
OG_IMAGE_FORMATTER = "/static/og/formatter.webp"
OG_IMAGE_SIZE = (1200, 630)

# On-page product screenshots (WebP + JPEG fallback under the same stem).
MEDIA_DETECTOR_HIGHLIGHTS = "/static/media/ai-detector-sentence-highlights.webp"
MEDIA_DETECTOR_SCORE = "/static/media/ai-detector-overall-score.webp"
MEDIA_HUMANIZER_RESULT = "/static/media/ai-humanizer-result-panel.webp"
MEDIA_HUMANIZER_COMPARE = "/static/media/ai-humanizer-before-after.webp"
MEDIA_FORMATTER_PREVIEW = "/static/media/essay-formatter-apa-preview.webp"
MEDIA_FORMATTER_SETTINGS = "/static/media/essay-formatter-style-settings.webp"


def og_stem_for_path(path: str) -> str:
    """Map a public path to ``static/og/<stem>.webp`` (``/`` → ``home``)."""
    if path == "/":
        return "home"
    clean = path.strip("/").replace("/", "-")
    return re.sub(r"[^a-z0-9\-]+", "-", clean.lower()).strip("-") or "page"


def og_image_path_for(path: str) -> str:
    """Relative OG image URL for a public page or blog path."""
    return f"/static/og/{og_stem_for_path(path)}.webp"

ROBOTS_INDEX = "index, follow"
ROBOTS_NOINDEX = "noindex, follow"

# Pages that must never show up in search results. They stay crawlable (not blocked in
# robots.txt) so crawlers can actually see the noindex tag.
# Keep /about, /faq, /pricing, /contact indexable (marketing + support).
NOINDEX_PATHS = frozenset(
    {
        "/login",
        "/register",
        "/account",
        "/account-info",
        "/admin",
        "/terms",
        "/privacy",
        "/delivery-policy",
        "/refund-policy",
    }
)
NOINDEX_PREFIXES = ("/verify-email/", "/admin/", "/cite/")

_OG_LOCALES = {"en": "en_US", "ru": "ru_RU", "uz": "uz_UZ"}


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
    # Absolute-path image URLs for sitemap ``image:image`` (OG + on-page shots).
    images: tuple[str, ...] = ()


def _info(
    path: str,
    template: str,
    title: str,
    description: str,
    crumb: str,
    *,
    indexable: bool | None = None,
) -> PublicPage:
    og = og_image_path_for(path)
    if indexable is None:
        indexable = path not in NOINDEX_PATHS
    return PublicPage(
        path=path,
        title=title,
        description=description,
        og_image=og,
        breadcrumb=crumb,
        sources=(f"templates/info/{template}",),
        images=(og,),
        in_sitemap=indexable,
    )


_PAGES: tuple[PublicPage, ...] = (
    PublicPage(
        path="/",
        title=DEFAULT_TITLE,
        description=DEFAULT_DESCRIPTION,
        h1="AI Humanizer and Writing Tools for Students",
        keywords=tuple(DEFAULT_KEYWORDS),
        og_image=OG_IMAGE_DEFAULT,
        sources=("templates/landing/home.html", "services/site_content.py"),
        software_app=True,
        images=(MEDIA_HUMANIZER_RESULT, MEDIA_DETECTOR_HIGHLIGHTS, MEDIA_FORMATTER_PREVIEW),
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
        sources=("templates/landing/ai_detector_en.html", "services/site_content.py"),
        software_app=True,
        images=(MEDIA_DETECTOR_HIGHLIGHTS, MEDIA_DETECTOR_SCORE),
    ),
    PublicPage(
        path="/humanizer",
        title="AI Humanizer: Make AI Text Sound Human | DocMaxxing",
        description=(
            "Free AI humanizer: humanize AI text from ChatGPT or Claude so it sounds human. "
            "Keeps meaning and citations. No sign-up for short essay drafts."
        ),
        h1="AI Humanizer — Make AI Text Sound Human",
        keywords=(
            "AI humanizer",
            "humanize AI text",
            "make AI text sound human",
            "free AI humanizer",
            "rewrite ChatGPT text",
        ),
        og_image=OG_IMAGE_HUMANIZER,
        breadcrumb="AI Humanizer",
        sources=("templates/landing/humanizer_en.html", "services/site_content.py"),
        software_app=True,
        images=(MEDIA_HUMANIZER_RESULT, MEDIA_HUMANIZER_COMPARE),
    ),
    PublicPage(
        path="/formatter",
        title="Essay Formatter — APA, MLA, Harvard, Chicago | DocMaxxing",
        description=(
            "Free essay formatter for APA 7, MLA 9, Harvard, Chicago and IEEE. Fonts, margins, "
            "spacing, cover page, citations and reference list from DOCX or paste."
        ),
        h1="Essay Formatter — APA, MLA, Harvard, Chicago",
        lede=(
            "Turn a rough draft into a submission-ready document with the right "
            "style profile, spacing, cover page, and reference layout."
        ),
        keywords=(
            "essay formatter",
            "APA 7 formatter",
            "MLA formatter",
            "Harvard referencing",
            "Chicago style formatter",
        ),
        og_image=OG_IMAGE_FORMATTER,
        breadcrumb="Essay Formatter",
        sources=("templates/format_v2.html", "templates/landing/_formatter_seo.html"),
        software_app=True,
        images=(MEDIA_FORMATTER_PREVIEW, MEDIA_FORMATTER_SETTINGS),
    ),
    PublicPage(
        path="/pricing",
        title="Pricing — Plans, Credit Packs & Free Tools | DocMaxxing",
        description=(
            "See what DocMaxxing costs: free formatting and free humanizer runs, monthly plans, "
            "and one-time credit packs for paid tools. No hidden fees."
        ),
        og_image="/static/og/pricing.webp",
        breadcrumb="Pricing",
        sources=("templates/pricing.html",),
        images=("/static/og/pricing.webp",),
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

def _build_public_pages() -> dict[str, PublicPage]:
    from services.seo_i18n import apply_en_alternates, build_localized_public_pages

    pages = {page.path: page for page in _PAGES}
    for page in build_localized_public_pages():
        pages[page.path] = page
    return apply_en_alternates(pages)


PUBLIC_PAGES: dict[str, PublicPage] = _build_public_pages()

_LOCALE_MARKETING_PATHS = frozenset(
    path
    for path in PUBLIC_PAGES
    if path == "/ru"
    or path == "/uz"
    or path.startswith("/ru/")
    or path.startswith("/uz/")
)

def _marketing_locale_paths() -> frozenset[str]:
    """All en/ru/uz marketing SSR paths (home, tools, pricing, faq, about)."""
    from services.seo_i18n import LOCALES, PAGE_KEYS, locale_path

    return frozenset(locale_path(lang, key) for lang in LOCALES for key in PAGE_KEYS)


# Public pages served to guests instead of the app (signed-in users go to /app#/<screen>).
# /pricing is always SSR for guests/bots (see ALWAYS_SSR_PATHS) — not gated on this flag.
GUEST_LANDING_PATHS = frozenset(
    {
        "/",
        "/ai-detector",
        "/humanizer",
        "/formatter",
        "/ru",
        "/ru/humanizer",
        "/ru/formatter",
        "/ru/ai-detector",
        "/uz",
        "/uz/humanizer",
        "/uz/formatter",
        "/uz/ai-detector",
    }
)
# Without those pages, guests get the app's own landing at these URLs (no redirect), opened on
# the matching tool and with the page's text already in the HTML for crawlers.
APP_LANDING_PATHS = frozenset({"/", "/ai-detector", "/humanizer", "/formatter"})
# Always server-rendered for anonymous visitors and crawlers (never redirect to /app#/...).
# Includes every localized marketing URL so /ru/* and /uz/* never 302 to /app for guests.
ALWAYS_SSR_PATHS = frozenset({"/pricing", "/ru/pricing", "/uz/pricing"} | _LOCALE_MARKETING_PATHS | _marketing_locale_paths())


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
    if path == "/ru" or path.startswith("/ru/"):
        return "ru"
    if path == "/uz" or path.startswith("/uz/"):
        return "uz"
    return "en"


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
    # Prefer the per-path generated OG board when the asset exists; else page.og_image.
    og_rel = og_image_path_for(page.path if page else norm)
    if not (REPO_ROOT / og_rel.lstrip("/")).is_file():
        og_rel = page.og_image if page else OG_IMAGE_DEFAULT
    og_image = absolute_url(og_rel)
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
            "email": "support@docmaxxing.com",
            "contactPoint": {
                "@type": "ContactPoint",
                "contactType": "customer support",
                "email": "support@docmaxxing.com",
                "telephone": "+998990779909",
                "availableLanguage": ["en", "ru", "uz"],
            },
            "sameAs": organization_same_as(),
        },
        {
            "@type": "WebSite",
            "@id": website_id,
            "url": SITE_URL,
            "name": SITE_NAME,
            "description": DEFAULT_DESCRIPTION,
            "publisher": {"@id": org_id},
            "inLanguage": ["en", "ru", "uz"],
        },
    ]
    if page is not None:
        url = canonical_url(page.path)
        about_paths = {"/about", "/ru/about", "/uz/about"}
        if page.path in about_paths:
            graph.append(
                {
                    "@type": "AboutPage",
                    "name": page.h1 or page.title,
                    "url": url,
                    "description": page.description,
                    "inLanguage": page.lang,
                    "isPartOf": {"@id": website_id},
                    "about": {"@id": org_id},
                }
            )
        if page.software_app:
            app_node: dict[str, Any] = {
                "@type": "SoftwareApplication",
                "name": page.h1 or page.title,
                "url": url,
                "applicationCategory": "EducationalApplication",
                "operatingSystem": "Web",
                "inLanguage": page.lang,
                "publisher": {"@id": org_id},
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            }
            app_images = [absolute_url(og_image_path_for(page.path))]
            app_images.extend(absolute_url(img) for img in page.images)
            app_node["image"] = app_images
            graph.append(app_node)
        if page.breadcrumb:
            home_labels = {"ru": "Главная", "uz": "Bosh sahifa", "en": "Home"}
            home = home_labels.get(page.lang, "Home")
            home_url = SITE_URL
            if page.lang in {"ru", "uz"}:
                home_url = canonical_url(f"/{page.lang}")
            crumbs = [(home, home_url)]
            if page.path.startswith(("/blog/", "/ru/blog/")):
                crumbs.append(("Блог" if page.lang == "ru" else "Blog", f"{SITE_URL}/blog"))
            elif page.path.startswith("/cite/"):
                crumbs.append(("Essay Formatter", f"{SITE_URL}/formatter"))
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
        faq_node: dict[str, Any] = {
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
        if page is not None:
            faq_node["inLanguage"] = page.lang
        graph.append(faq_node)
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
    images: tuple[str, ...] = ()


def _sitemap_images_for(page: PublicPage) -> tuple[str, ...]:
    """OG board plus on-page media, as absolute URLs for image:image."""
    seen: list[str] = []
    for rel in (og_image_path_for(page.path), *page.images):
        abs_url = absolute_url(rel)
        if abs_url not in seen:
            seen.append(abs_url)
    return tuple(seen)


def sitemap_entries() -> list[SitemapEntry]:
    from services import blog

    landings = guest_landings_enabled()
    entries = [
        SitemapEntry(
            page.path,
            page_lastmod(page),
            dict(page.alternates),
            _sitemap_images_for(page),
        )
        for page in PUBLIC_PAGES.values()
        if page.in_sitemap
        and (
            page.path in APP_LANDING_PATHS
            or page.path in ALWAYS_SSR_PATHS
            or landings
            or page.path not in GUEST_LANDING_PATHS
        )
    ]
    for post_page, lastmod in blog.sitemap_pages():
        entries.append(
            SitemapEntry(
                post_page.path,
                lastmod,
                dict(post_page.alternates),
                _sitemap_images_for(post_page),
            )
        )
    return entries


def sitemap_xml() -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
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
        for image_url in entry.images:
            lines.append("    <image:image>")
            lines.append(f"      <image:loc>{xml_escape(image_url)}</image:loc>")
            lines.append("    </image:image>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


# Paths blocked for every crawler group. Named User-agent blocks ignore ``*``, so
# these Disallow lines must be repeated in each group (RFC 9309 / robots.txt).
DISALLOW_PATHS: tuple[str, ...] = ("/api/",)

# AI / answer-engine crawlers that should explicitly be allowed to read public pages.
# ``User-agent: *`` already allows them; these blocks make the policy visible to auditors
# (GEO / ChatGPT / Perplexity / Claude / Google AI Overviews).
# Citation bots that GEO scores as "explicit" (not merely via User-agent: *):
# OAI-SearchBot, Claude-SearchBot, PerplexityBot, Googlebot, Applebot.
_AI_CRAWLER_USER_AGENTS = (
    "GPTBot",
    "OAI-SearchBot",
    "ChatGPT-User",
    "ClaudeBot",
    "Claude-SearchBot",
    "Claude-User",
    "PerplexityBot",
    "Perplexity-User",
    "Googlebot",
    "Google-Extended",
    "Google-CloudVertexBot",
    "Applebot-Extended",
    "Applebot",
    "Bingbot",
    "cohere-ai",
    "DuckAssistBot",
    "Bytespider",
    "meta-externalagent",
    "Meta-ExternalFetcher",
    "facebookexternalhit",
    "Amazonbot",
    "AI2Bot",
    "AI2Bot-Dolma",
    "xAI-Bot",
    "YouBot",
    "CCBot",
    "PetalBot",
)


def _robots_group_rules() -> list[str]:
    """Private Disallows then Allow — shared by every User-agent group.

    Disallow lines come first so first-match parsers (urllib.robotparser) still
    block ``/api/`` when ``Allow: /`` is also present. Longest-match parsers
    (Google) prefer the longer ``/api/`` path either way.
    """
    return [*[f"Disallow: {path}" for path in DISALLOW_PATHS], "Allow: /"]


def robots_txt() -> str:
    lines: list[str] = [
        "# DocMaxxing robots.txt — public pages are open to search and AI crawlers.",
        "# API routes stay private; everything else may be crawled and cited.",
        "# Named bot groups repeat Disallow (they do not inherit the wildcard group).",
        "",
    ]
    rules = _robots_group_rules()
    for agent in _AI_CRAWLER_USER_AGENTS:
        lines.append(f"User-agent: {agent}")
        lines.extend(rules)
        lines.append("")
    lines.append("User-agent: *")
    lines.extend(rules)
    lines.extend(["", f"Sitemap: {SITE_URL}/sitemap.xml", ""])
    return "\n".join(lines)


def llms_txt() -> str:
    """Machine-readable site summary for AI agents (https://llmstxt.org/)."""
    return "\n".join(
        [
            "# DocMaxxing",
            "",
            f"> {DEFAULT_DESCRIPTION}",
            "",
            "DocMaxxing is a set of academic writing tools for students: a free AI detector,",
            "an AI humanizer, a free essay formatter (APA, MLA, Harvard, Chicago, IEEE),",
            "credit-based Turnitin checks, a document workspace, slides, and assignment help.",
            "Public marketing pages are available in English (default), Russian (/ru/...), and",
            "Uzbek Latin (/uz/...). The product app at /app is English-only.",
            "",
            "## Primary tools",
            "",
            f"- [Free AI Detector]({SITE_URL}/ai-detector): paste an essay, get an AI score and",
            "  sentence-level highlights. Tuned on real Turnitin reports. No sign-up for short checks.",
            f"- [AI Humanizer]({SITE_URL}/humanizer): rewrite stiff AI-sounding drafts into natural",
            "  student writing while keeping meaning, numbers and citations. Free runs for short texts.",
            f"- [Essay Formatter]({SITE_URL}/formatter): format DOCX/paste text for APA 7, MLA 9,",
            "  Harvard, Chicago or IEEE — free.",
            "",
            "## Russian (ru)",
            "",
            f"- [Главная]({SITE_URL}/ru): проверка на ИИ, хуманайзер и оформление.",
            f"- [Проверка на ИИ]({SITE_URL}/ru/ai-detector)",
            f"- [Хуманайзер]({SITE_URL}/ru/humanizer)",
            f"- [Оформление]({SITE_URL}/ru/formatter)",
            f"- [Цены]({SITE_URL}/ru/pricing) · [FAQ]({SITE_URL}/ru/faq) · [О нас]({SITE_URL}/ru/about)",
            "",
            "## Oʻzbekcha (uz)",
            "",
            f"- [Bosh sahifa]({SITE_URL}/uz): AI matn tekshirish, humanizer va formatlash.",
            f"- [AI matn tekshirish]({SITE_URL}/uz/ai-detector)",
            f"- [Humanizer]({SITE_URL}/uz/humanizer)",
            f"- [Formatlash]({SITE_URL}/uz/formatter)",
            f"- [Narxlar]({SITE_URL}/uz/pricing) · [FAQ]({SITE_URL}/uz/faq) · [Haqida]({SITE_URL}/uz/about)",
            "",
            "## Plans and help",
            "",
            f"- [Pricing]({SITE_URL}/pricing): free tools, monthly plans and one-time credit packs.",
            f"- [FAQ]({SITE_URL}/faq): humanizer limits, credits, formatting, plans and refunds.",
            f"- [How credits work]({SITE_URL}/credits): welcome bonus and cost per paid action.",
            f"- [Blog]({SITE_URL}/blog): guides on AI detectors, Turnitin scores and citing AI tools.",
            f"- [Blog RSS]({SITE_URL}/blog/rss.xml): feed of published posts.",
            "",
            "## About",
            "",
            f"- [About DocMaxxing]({SITE_URL}/about)",
            f"- [Contact support]({SITE_URL}/contact): support@docmaxxing.com",
            f"- Site: {SITE_URL}",
            f"- Sitemap: {SITE_URL}/sitemap.xml",
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
