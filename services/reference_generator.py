"""
Build APA 7th-edition style web references from a URL or pasted source text.

Metadata is taken from HTML meta / JSON-LD when possible; gaps are filled with
sensible APA fallbacks (organization as author, (n.d.) for missing dates).
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# Reasonable timeout; some academic sites are slow
REQUEST_TIMEOUT = 18
USER_AGENT = (
    "Mozilla/5.0 (compatible; AcademicRefGenerator/1.0; "
    "+https://example.org/edu-tool)"
)


def _strip_tags(html_fragment: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", html_fragment)).strip()


def _hostname(url: str) -> str:
    try:
        host = urlparse(url).netloc or ""
        return host.lstrip("www.") or host
    except Exception:
        return ""


def _extract_json_ld_authors_date(obj: Any) -> tuple[list[str], str | None, str | None]:
    """Walk JSON-LD for author names, datePublished, headline/name as title."""
    authors: list[str] = []
    date_pub: str | None = None
    title: str | None = None

    def visit(node: Any) -> None:
        nonlocal date_pub, title
        if isinstance(node, dict):
            t = node.get("@type")
            if t and isinstance(t, str):
                types = {t.lower()}
            elif isinstance(t, list):
                types = {str(x).lower() for x in t}
            else:
                types = set()

            if "author" in node:
                a = node["author"]
                items = a if isinstance(a, list) else [a]
                for it in items:
                    if isinstance(it, dict):
                        name = it.get("name")
                        if isinstance(name, str) and name.strip():
                            authors.append(name.strip())
                    elif isinstance(it, str) and it.strip():
                        authors.append(it.strip())

            dp = node.get("datePublished") or node.get("dateCreated")
            if isinstance(dp, str) and dp.strip() and not date_pub:
                date_pub = dp.strip()

            if types & {"article", "newsarticle", "scholarlyarticle", "webpage", "blogposting"}:
                for key in ("headline", "name"):
                    v = node.get(key)
                    if isinstance(v, str) and v.strip() and not title:
                        title = v.strip()

            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for x in node:
                visit(x)

    visit(obj)
    return authors, date_pub, title


def _parse_iso_date(iso: str | None) -> tuple[str, str | None]:
    """
    Return (year_string, full_apa_parenthetical_date or None).
    apa_date: \"2021, January 15\" or \"2021\" if only year.
    """
    if not iso:
        return ("n.d.", None)
    s = iso.strip()
    # 2021-01-15 or 2021-01-15T12:00:00Z
    m = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", s)
    if not m:
        y = re.search(r"\b(19|20)\d{2}\b", s)
        return (y.group(0), None) if y else ("n.d.", None)
    year, mo, day = m.group(1), m.group(2), m.group(3)
    months = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    if mo and day:
        mi = int(mo, 10)
        if 1 <= mi <= 12:
            return year, f"{year}, {months[mi - 1]} {int(day, 10)}"
    if mo:
        mi = int(mo, 10)
        if 1 <= mi <= 12:
            return year, f"{year}, {months[mi - 1]}"
    return year, year


def _assert_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http:// and https:// URLs are supported.")


def fetch_page_metadata(url: str) -> dict[str, Any]:
    """HTTP GET and extract title, authors, date, site label from HTML."""
    _assert_public_http_url(url)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    r = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers, allow_redirects=True)
    r.raise_for_status()
    final_url = str(r.url)
    soup = BeautifulSoup(r.content, "html.parser")

    def read_meta_tag(prop: str | None = None, name: str | None = None, itemprop: str | None = None) -> str | None:
        tag = None
        if prop:
            tag = soup.find("meta", attrs={"property": prop})
        if not tag and name:
            tag = soup.find("meta", attrs={"name": name})
        if not tag and itemprop:
            tag = soup.find("meta", attrs={"itemprop": itemprop})
        if tag and tag.get("content"):
            return tag["content"].strip()
        return None

    title = (
        read_meta_tag(prop="og:title")
        or read_meta_tag(name="twitter:title")
        or (soup.title.get_text(strip=True) if soup.title else None)
    )
    site = read_meta_tag(prop="og:site_name") or read_meta_tag(name="application-name")
    author_meta = read_meta_tag(name="author") or read_meta_tag(name="article:author")

    authors: list[str] = []
    if author_meta:
        authors = [a.strip() for a in re.split(r"[,;]|\band\b", author_meta, flags=re.I) if a.strip()]

    date_raw = read_meta_tag(prop="article:published_time") or read_meta_tag(name="pubdate") or read_meta_tag(name="date")
    if not date_raw:
        tag_dp = soup.find("meta", attrs={"itemprop": "datePublished"})
        if tag_dp and tag_dp.get("content"):
            date_raw = tag_dp["content"].strip()

    # JSON-LD blocks
    ld_title = None
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        blobs = data if isinstance(data, list) else [data]
        for blob in blobs:
            la, dp, lt = _extract_json_ld_authors_date(blob)
            if la:
                authors = la
            if dp:
                date_raw = dp
            if lt:
                ld_title = lt

    if ld_title and not title:
        title = ld_title

    org = site or _hostname(final_url)
    return {
        "url": final_url,
        "title": _strip_tags(title) if title else None,
        "authors": authors,
        "date_raw": date_raw,
        "organization": org,
    }


# Authors run up to the parenthetical year, so initials like "J." stay attached.
_RAW_AUTHORS = re.compile(
    r"^(?P<authors>.*?)\s*\((?P<year>n\.d\.|\d{4})\)\.\s*(?P<title>.+?)\.\s*(?P<source>.+?)\s*$",
    re.I | re.DOTALL,
)


def parse_raw_source_text(text: str) -> dict[str, Any]:
    """
    Parse a single loose line/paragraph that looks like a reference or source note.
    Fallback: treat whole string as title-like with no year.
    """
    t = text.strip()
    if not t:
        return {}

    m = _RAW_AUTHORS.match(t.replace("\n", " "))
    if m:
        auth = m.group("authors").strip()
        if "," not in auth:
            auth = auth.rstrip(".")
        year = m.group("year").strip()
        title = m.group("title").strip()
        source = m.group("source").strip().rstrip(".")
        # Keep "Last, F. M." together; split multiple authors on ";" only.
        author_list = [a.strip() for a in auth.split(";") if a.strip()] or [auth]
        return {
            "title": title,
            "authors": author_list,
            "year_raw": year[:4] if year != "n.d." else "n.d.",
            "organization": source,
            "url": None,
        }

    # "Title — Site, 2023" style
    y = re.search(r"\b(19|20)\d{2}\b", t)
    return {
        "title": t,
        "authors": [],
        "year_raw": y.group(0) if y else None,
        "organization": None,
        "url": None,
    }


def _format_apa_author_list(authors: list[str], organization: str | None) -> str:
    if authors:
        parts = []
        for i, a in enumerate(authors):
            parts.append(a.strip())
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]}, & {parts[1]}"
        return ", ".join(parts[:-1]) + f", & {parts[-1]}"
    if organization and organization.strip():
        return organization.strip()
    return ""


def _apa_parenthetical(year: str, apa_inner: str | None) -> str:
    if year == "n.d.":
        return "(n.d.)"
    if apa_inner and apa_inner != year:
        return f"({apa_inner})"
    return f"({year})"


def build_apa_web_citation(
    *,
    authors: list[str],
    organization: str | None,
    year: str,
    apa_date_inner: str | None,
    title: str | None,
    source: str | None,
    url: str | None,
) -> str:
    """
    APA 7 reference-list style for a webpage / online article.

    Italics for the page title are indicated with asterisks for plain-text JSON.
    """
    src = (source or "").strip() or (organization or "").strip()
    ttl = (title or "Untitled webpage").strip()
    author_part = _format_apa_author_list(authors, organization)
    paren = _apa_parenthetical(year, apa_date_inner)
    entry_title = f"*{ttl}*"

    parts: list[str] = []
    if author_part:
        ap = author_part.rstrip(".")
        parts.append(f"{ap}. {paren}. {entry_title}.")
    else:
        parts.append(f"{entry_title}. {paren}.")
    if src:
        parts.append(f"{src}.")
    if url:
        parts.append(url.strip())
    return " ".join(parts)


def generate_apa_reference(
    *,
    url: str | None = None,
    raw_text: str | None = None,
) -> dict[str, Any]:
    """
    Produce the API JSON object: citation, authors, year, title, source.
    """
    authors: list[str] = []
    organization: str | None = None
    title: str | None = None
    source: str | None = None
    year = "n.d."
    apa_inner: str | None = None
    final_url: str | None = None

    if url and url.strip():
        final_url = url.strip()
        if not final_url.startswith(("http://", "https://")):
            final_url = "https://" + final_url
        _assert_public_http_url(final_url)
        meta = fetch_page_metadata(final_url)
        authors = meta.get("authors") or []
        title = meta.get("title")
        organization = meta.get("organization")
        dr = meta.get("date_raw")
        y, inner = _parse_iso_date(dr)
        year = y
        apa_inner = inner if y != "n.d." else None
        source = organization
        final_url = meta["url"]

    if raw_text and raw_text.strip():
        extra = parse_raw_source_text(raw_text)
        if extra:
            if extra.get("title") and not title:
                title = extra["title"]
            if extra.get("authors"):
                authors = extra["authors"]
            if extra.get("year_raw"):
                yr = extra["year_raw"]
                if yr == "n.d.":
                    year = "n.d."
                    apa_inner = None
                else:
                    year = str(yr)[:4]
                    apa_inner = year
            if extra.get("organization"):
                organization = extra["organization"]
                source = source or organization
            if extra.get("url"):
                final_url = extra["url"]

    # Organization as author when no listed authors
    author_field_org = None
    if not authors:
        author_field_org = organization or source or _hostname(final_url or "")

    citation = build_apa_web_citation(
        authors=authors,
        organization=author_field_org if not authors else None,
        year=year,
        apa_date_inner=apa_inner,
        title=title,
        source=source or organization,
        url=final_url,
    )

    # When organization used as author, authors array empty per APA display — user asked list; put org in authors
    authors_out = list(authors) if authors else []
    if not authors_out and author_field_org and author_field_org.strip():
        authors_out = [author_field_org.strip()]

    authors_out = [a.strip() for a in authors_out if a.strip()]

    return {
        "citation": citation,
        "authors": authors_out,
        "year": year if year != "n.d." else "n.d.",
        "title": (title or "").strip() or None,
        "source": (source or organization or "").strip() or None,
    }
