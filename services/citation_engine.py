"""
Multi-style citation generation from URL, DOI, ISBN, title/author, manual fields, or pasted text.

Uses free public APIs (Crossref, Open Library) where needed — no paid keys.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from services.reference_generator import (
    fetch_page_metadata,
    generate_apa_reference,
    parse_raw_source_text,
)

CITATION_STYLES = frozenset({"APA", "Harvard", "MLA", "Chicago", "IEEE", "Vancouver"})
REQUEST_TIMEOUT = 18
USER_AGENT = "AcademicDocumentStudio/1.0 (mailto:edu@example.org)"


def _clean(s: str | None) -> str:
    return (s or "").strip()


def _authors_from_crossref(items: list) -> list[str]:
    out: list[str] = []
    for a in items or []:
        if not isinstance(a, dict):
            continue
        given = _clean(a.get("given"))
        family = _clean(a.get("family"))
        if family and given:
            initials = ". ".join(x[0].upper() + "." for x in given.split() if x)
            out.append(f"{family}, {initials}" if initials else family)
        elif family:
            out.append(family)
        elif a.get("name"):
            out.append(str(a["name"]).strip())
    return out


def _year_from_crossref(msg: dict) -> str:
    for key in ("published-print", "published-online", "created", "issued"):
        part = msg.get(key)
        if isinstance(part, dict):
            dp = part.get("date-parts")
            if dp and dp[0] and dp[0][0]:
                return str(dp[0][0])
    return "n.d."


def fetch_metadata_doi(doi: str) -> dict[str, Any]:
    doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    if not doi:
        raise ValueError("Enter a valid DOI.")
    url = f"https://api.crossref.org/works/{requests.utils.quote(doi, safe='')}"
    r = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    msg = r.json().get("message") or {}
    authors = _authors_from_crossref(msg.get("author") or [])
    title_list = msg.get("title") or []
    title = title_list[0] if title_list else None
    year = _year_from_crossref(msg)
    journal = (msg.get("container-title") or [None])[0]
    volume = msg.get("volume")
    issue = msg.get("issue")
    pages = msg.get("page")
    publisher = msg.get("publisher")
    return {
        "authors": authors,
        "year": year,
        "title": title,
        "journal": journal,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "publisher": publisher,
        "doi": doi,
        "url": f"https://doi.org/{doi}",
        "source_type": "journal" if journal else "other",
    }


def fetch_metadata_isbn(isbn: str) -> dict[str, Any]:
    raw = re.sub(r"[^0-9Xx]", "", isbn)
    if len(raw) not in (10, 13):
        raise ValueError("Enter a valid 10- or 13-digit ISBN.")
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{raw}&format=json&jscmd=data"
    r = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    data = r.json()
    key = f"ISBN:{raw}"
    book = data.get(key) or {}
    if not book:
        raise ValueError("No book found for this ISBN.")
    authors = [a.get("name", "").strip() for a in book.get("authors") or [] if a.get("name")]
    pub = book.get("publishers") or []
    publisher = pub[0].get("name") if pub else None
    year = None
    if book.get("publish_date"):
        m = re.search(r"\b(19|20)\d{2}\b", str(book["publish_date"]))
        year = m.group(0) if m else None
    return {
        "authors": authors,
        "year": year or "n.d.",
        "title": book.get("title"),
        "publisher": publisher,
        "url": book.get("url"),
        "source_type": "book",
    }


def search_metadata_title_author(title: str, author: str = "") -> dict[str, Any]:
    title = _clean(title)
    if not title:
        raise ValueError("Title is required.")
    q = title
    if author:
        q = f"{author} {title}"
    url = "https://api.crossref.org/works"
    r = requests.get(
        url,
        params={"query": q, "rows": 1},
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    r.raise_for_status()
    items = (r.json().get("message") or {}).get("items") or []
    if not items:
        return {
            "authors": [author] if author else [],
            "year": "n.d.",
            "title": title,
            "source_type": "other",
        }
    msg = items[0]
    authors = _authors_from_crossref(msg.get("author") or [])
    if not authors and author:
        authors = [author]
    tlist = msg.get("title") or []
    return {
        "authors": authors,
        "year": _year_from_crossref(msg),
        "title": tlist[0] if tlist else title,
        "journal": (msg.get("container-title") or [None])[0],
        "volume": msg.get("volume"),
        "issue": msg.get("issue"),
        "pages": msg.get("page"),
        "publisher": msg.get("publisher"),
        "doi": msg.get("DOI"),
        "url": f"https://doi.org/{msg['DOI']}" if msg.get("DOI") else None,
        "source_type": "journal" if msg.get("container-title") else "other",
    }


def metadata_from_manual(fields: dict[str, Any]) -> dict[str, Any]:
    authors_raw = _clean(fields.get("authors") or fields.get("author"))
    authors = [a.strip() for a in re.split(r"[;\n]", authors_raw) if a.strip()] if authors_raw else []
    return {
        "authors": authors,
        "year": _clean(fields.get("year")) or "n.d.",
        "title": _clean(fields.get("title")) or "Untitled",
        "journal": _clean(fields.get("journal")) or None,
        "volume": _clean(fields.get("volume")) or None,
        "issue": _clean(fields.get("issue")) or None,
        "pages": _clean(fields.get("pages")) or None,
        "publisher": _clean(fields.get("publisher")) or None,
        "doi": _clean(fields.get("doi")) or None,
        "url": _clean(fields.get("url")) or None,
        "source_type": "journal" if fields.get("journal") else ("book" if fields.get("publisher") else "web"),
    }


def metadata_from_paste(text: str) -> dict[str, Any]:
    parsed = parse_raw_source_text(text)
    if not parsed:
        raise ValueError("Could not parse pasted citation text.")
    authors = parsed.get("authors") or []
    year = parsed.get("year_raw") or "n.d."
    return {
        "authors": authors,
        "year": year,
        "title": parsed.get("title"),
        "publisher": parsed.get("organization"),
        "url": parsed.get("url"),
        "source_type": "web",
        "raw_paste": text.strip(),
    }


def _author_list_apa(authors: list[str], org: str | None = None) -> str:
    if authors:
        if len(authors) == 1:
            return authors[0]
        if len(authors) == 2:
            return f"{authors[0]}, & {authors[1]}"
        return ", ".join(authors[:-1]) + f", & {authors[-1]}"
    return org or ""


def format_citation(meta: dict[str, Any], style: str) -> str:
    st = (style or "APA").strip().upper()
    if st not in CITATION_STYLES:
        st = "APA"

    authors = meta.get("authors") or []
    year = str(meta.get("year") or "n.d.")
    title = _clean(meta.get("title")) or "Untitled"
    journal = _clean(meta.get("journal"))
    volume = _clean(meta.get("volume"))
    issue = _clean(meta.get("issue"))
    pages = _clean(meta.get("pages"))
    publisher = _clean(meta.get("publisher"))
    doi = _clean(meta.get("doi"))
    url = _clean(meta.get("url"))
    org = publisher or _clean(meta.get("organization"))

    if st == "APA":
        auth = _author_list_apa(authors, org).rstrip(".")
        paren = f"({year})" if year != "n.d." else "(n.d.)"
        if journal:
            vol_bit = f", *{volume}*" if volume else ""
            iss_bit = f"({issue})" if issue else ""
            pg = f", {pages}" if pages else ""
            doi_bit = f" https://doi.org/{doi}" if doi else (f" {url}" if url else "")
            if auth:
                return f"{auth}. {paren}. {title}. *{journal}*{vol_bit}{iss_bit}{pg}.{doi_bit}".strip()
            return f"{title}. {paren}. *{journal}*{vol_bit}{iss_bit}{pg}.{doi_bit}".strip()
        if publisher:
            if auth:
                return f"{auth}. {paren}. *{title}*. {publisher}."
            return f"*{title}*. {paren}. {publisher}."
        if auth:
            return f"{auth}. {paren}. *{title}*.{(' ' + url) if url else ''}"
        return f"*{title}*. {paren}.{(' ' + url) if url else ''}"

    if st == "Harvard":
        auth = _author_list_apa(authors, org)
        yr = year if year != "n.d." else "n.d."
        if journal:
            vol = f"{volume}({issue})" if volume and issue else (volume or "")
            pg = f", pp. {pages}" if pages else ""
            return f"{auth} ({yr}) '{title}', *{journal}*, {vol}{pg}."
        if auth:
            return f"{auth} ({yr}) *{title}*. {publisher or 'Online'}.{(' Available at: ' + url) if url else ''}"
        return f"*{title}* ({yr}). {publisher or 'Online'}."

    if st == "MLA":
        auth = authors[0] if authors else (org or "Unknown")
        src = journal or publisher or org or "Web"
        extra = ""
        if volume:
            extra += f", vol. {volume}"
        if issue:
            extra += f", no. {issue}"
        if pages:
            extra += f", pp. {pages}"
        if year != "n.d.":
            extra += f", {year}"
        if url:
            extra += f", {url}"
        return f'{auth}. "{title}." *{src}*{extra}.'

    if st == "Chicago":
        auth = _author_list_apa(authors, org)
        yr = year if year != "n.d." else "n.d."
        if journal:
            vol = f" {volume}, no. {issue}" if volume and issue else (f" {volume}" if volume else "")
            pg = f" ({pages})" if pages else ""
            return f'{auth}. "{title}." *{journal}*{vol}{pg} ({yr}).'
        return f'{auth}. *{title}*. {publisher or "N.p."}, {yr}.'

    if st == "IEEE":
        auth = ", ".join(authors) if authors else (org or "Unknown")
        if journal:
            vol = f", vol. {volume}" if volume else ""
            iss = f", no. {issue}" if issue else ""
            pg = f", pp. {pages}" if pages else ""
            return f'{auth}, "{title}," *{journal}*{vol}{iss}{pg}, {year}.'
        return f'{auth}, *{title}*. {publisher or "N.p."}, {year}.'

    if st == "Vancouver":
        auth = ", ".join(authors) if authors else (org or "Unknown")
        if journal:
            vol = f";{volume}" if volume else ""
            iss = f"({issue})" if issue else ""
            pg = f":{pages}" if pages else ""
            return f"{auth}. {title}. {journal}. {year}{vol}{iss}{pg}."
        return f"{auth}. {title}. {publisher or 'Place unknown'}; {year}."

    return format_citation(meta, "APA")


def generate_citation(
    *,
    mode: str,
    style: str = "APA",
    url: str | None = None,
    doi: str | None = None,
    isbn: str | None = None,
    title: str | None = None,
    author: str | None = None,
    manual: dict[str, Any] | None = None,
    paste: str | None = None,
) -> dict[str, Any]:
    """Unified entry: returns {citation, metadata, style}."""
    mode = (mode or "url").lower().strip()
    meta: dict[str, Any]

    if mode == "url":
        if not url or not _clean(url):
            raise ValueError("URL is required.")
        apa = generate_apa_reference(url=url.strip())
        meta = {
            "authors": apa.get("authors") or [],
            "year": apa.get("year") or "n.d.",
            "title": apa.get("title"),
            "url": url.strip(),
            "organization": apa.get("source"),
            "source_type": "web",
        }
        if not meta.get("title"):
            try:
                fetched = fetch_page_metadata(url if url.startswith("http") else "https://" + url)
                meta["title"] = fetched.get("title")
                meta["authors"] = fetched.get("authors") or meta["authors"]
            except Exception:
                pass
    elif mode == "doi":
        meta = fetch_metadata_doi(doi or "")
    elif mode == "isbn":
        meta = fetch_metadata_isbn(isbn or "")
    elif mode == "title":
        meta = search_metadata_title_author(title or "", author or "")
    elif mode == "manual":
        meta = metadata_from_manual(manual or {})
    elif mode == "paste":
        meta = metadata_from_paste(paste or "")
    else:
        raise ValueError(f"Unknown mode: {mode}")

    citation = format_citation(meta, style)
    return {
        "citation": citation,
        "metadata": meta,
        "style": (style or "APA").upper(),
        "authors": meta.get("authors") or [],
        "year": meta.get("year"),
        "title": meta.get("title"),
    }
