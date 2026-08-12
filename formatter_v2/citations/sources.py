"""Fetch / build CSLItem from external identifiers and user input.

Network failures never raise out of these helpers — callers get
``(None, message)`` instead.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from formatter_v2.citations.models import CSLDate, CSLItem, CSLName, CSLType

DEFAULT_TIMEOUT_S = 12.0
CROSSREF_SCORE_THRESHOLD = 50.0

SourceResult = tuple[CSLItem | None, str | None]


class CitationSourceError(Exception):
    """Raised only when callers opt into exception style; helpers return tuples."""


def _clean_doi(doi: str) -> str:
    text = doi.strip()
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text, flags=re.I)
    return text.strip()


def _safe_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> tuple[requests.Response | None, str | None]:
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
    except requests.Timeout:
        return None, f"Timed out requesting {url}"
    except requests.RequestException as exc:
        return None, f"Network error requesting {url}: {exc}"
    if response.status_code >= 400:
        return None, f"HTTP {response.status_code} requesting {url}"
    return response, None


def _item_from_mapping(data: dict[str, Any], *, fallback_id: str) -> CSLItem:
    payload = dict(data)
    if not payload.get("id"):
        payload["id"] = fallback_id
    if "type" not in payload or payload["type"] not in {
        "article-journal",
        "book",
        "chapter",
        "webpage",
        "thesis",
        "report",
        "paper-conference",
    }:
        # Crossref / doi.org may return types outside our Literal — coerce.
        raw_type = str(payload.get("type") or "article-journal")
        allowed: set[str] = {
            "article-journal",
            "book",
            "chapter",
            "webpage",
            "thesis",
            "report",
            "paper-conference",
        }
        type_map = {
            "journal-article": "article-journal",
            "article": "article-journal",
            "book-chapter": "chapter",
            "posted-content": "webpage",
            "other": "webpage",
            "manuscript": "report",
            "report-component": "report",
            "proceedings-article": "paper-conference",
            "conference-paper": "paper-conference",
            "dissertation": "thesis",
        }
        payload["type"] = type_map.get(raw_type, raw_type if raw_type in allowed else "article-journal")
    return CSLItem.model_validate(payload)


def from_doi(doi: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> SourceResult:
    """Resolve a DOI via content negotiation (response is already CSL-JSON)."""
    cleaned = _clean_doi(doi)
    if not cleaned:
        return None, "Empty DOI"
    url = f"https://doi.org/{quote(cleaned)}"
    response, err = _safe_get(
        url,
        headers={"Accept": "application/vnd.citationstyles.csl+json"},
        timeout=timeout,
    )
    if err or response is None:
        return None, err or "Could not fetch DOI metadata"
    try:
        data = response.json()
    except ValueError:
        return None, "doi.org response is not JSON"
    try:
        item = _item_from_mapping(data, fallback_id=cleaned)
    except Exception as exc:  # noqa: BLE001 — validate soft-fails for callers
        return None, f"Could not parse CSL-JSON for DOI: {exc}"
    if not item.DOI:
        item = item.model_copy(update={"DOI": cleaned})
    return item, None


def from_isbn(isbn: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> SourceResult:
    """Resolve an ISBN via Open Library and map to CSLItem."""
    cleaned = re.sub(r"[^0-9Xx]", "", isbn.strip())
    if not cleaned:
        return None, "Empty ISBN"
    url = f"https://openlibrary.org/isbn/{cleaned}.json"
    response, err = _safe_get(url, timeout=timeout)
    if err or response is None:
        return None, err or "Could not fetch ISBN metadata"
    try:
        data = response.json()
    except ValueError:
        return None, "Open Library response is not JSON"

    title = data.get("title")
    authors: list[CSLName] = []
    # Open Library ISBN endpoint often omits author names; try authors API keys later if needed.
    for entry in data.get("authors") or []:
        if isinstance(entry, dict) and entry.get("key"):
            # Keep placeholder literal from key path if name unavailable.
            authors.append(CSLName(literal=str(entry["key"]).rstrip("/").split("/")[-1]))
    publishers = data.get("publishers") or []
    publish_places = data.get("publish_places") or []
    publish_date = data.get("publish_date")
    issued = None
    if isinstance(publish_date, str):
        year_match = re.search(r"(19|20)\d{2}", publish_date)
        if year_match:
            issued = CSLDate(date_parts=[[int(year_match.group(0))]])

    try:
        item = CSLItem(
            id=f"isbn:{cleaned}",
            type="book",
            title=title,
            author=authors or None,
            publisher=publishers[0] if publishers else None,
            publisher_place=publish_places[0] if publish_places else None,
            issued=issued,
            ISBN=cleaned,
            URL=f"https://openlibrary.org/isbn/{cleaned}",
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"Could not build CSLItem from Open Library: {exc}"
    return item, None


def from_url(url: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> SourceResult:
    """Build a webpage CSLItem from HTML metadata."""
    cleaned = url.strip()
    if not cleaned:
        return None, "Empty URL"
    if not re.match(r"^https?://", cleaned, flags=re.I):
        cleaned = "https://" + cleaned
    response, err = _safe_get(cleaned, headers={"User-Agent": "DocMaxxingFormatter/2.0"}, timeout=timeout)
    if err or response is None:
        return None, err or "Could not load the page"
    soup = BeautifulSoup(response.text, "html.parser")

    def meta(*names: str) -> str | None:
        for name in names:
            tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
            if tag and tag.get("content"):
                return str(tag["content"]).strip()
        return None

    title = meta("citation_title", "og:title", "twitter:title") or (
        soup.title.string.strip() if soup.title and soup.title.string else None
    )
    author_raw = meta("citation_author", "author", "og:article:author")
    authors = [CSLName(literal=author_raw)] if author_raw else None
    year = None
    date_raw = meta("citation_publication_date", "article:published_time", "og:updated_time")
    if date_raw:
        m = re.search(r"(19|20)\d{2}", date_raw)
        if m:
            year = int(m.group(0))
    issued = CSLDate(date_parts=[[year]]) if year else None
    container = meta("citation_journal_title", "og:site_name")

    try:
        item = CSLItem(
            id=cleaned,
            type="webpage",
            title=title or cleaned,
            author=authors,
            container_title=container,
            issued=issued,
            URL=cleaned,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"Could not build CSLItem from URL: {exc}"
    return item, None


def from_raw_string(text: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> SourceResult:
    """Fuzzy-match a bibliographic string via Crossref; None if score is too low."""
    query = text.strip()
    if not query:
        return None, "Empty source string"
    response, err = _safe_get(
        "https://api.crossref.org/works",
        params={"query.bibliographic": query, "rows": 1},
        headers={"User-Agent": "DocMaxxingFormatter/2.0 (mailto:support@docmaxxing.app)"},
        timeout=timeout,
    )
    if err or response is None:
        return None, err or "Could not query Crossref"
    try:
        payload = response.json()
    except ValueError:
        return None, "Crossref response is not JSON"
    items = (((payload or {}).get("message") or {}).get("items")) or []
    if not items:
        return None, "could not recognise the source"
    hit = items[0]
    score = float(hit.get("score") or 0)
    if score < CROSSREF_SCORE_THRESHOLD:
        return None, "could not recognise the source"
    # Crossref message item is not CSL-JSON; map common fields.
    doi = hit.get("DOI")
    if doi:
        return from_doi(doi, timeout=timeout)
    mapped = _crossref_work_to_csl(hit)
    try:
        item = _item_from_mapping(mapped, fallback_id=hit.get("URL") or query[:64])
    except Exception as exc:  # noqa: BLE001
        return None, f"Could not parse Crossref result: {exc}"
    return item, None


def _crossref_work_to_csl(work: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for person in work.get("author") or []:
        authors.append(
            {
                "family": person.get("family"),
                "given": person.get("given"),
                "literal": person.get("name"),
            }
        )
    issued_parts = ((work.get("issued") or {}).get("date-parts")) or None
    title_list = work.get("title") or []
    container_list = work.get("container-title") or []
    return {
        "id": work.get("DOI") or work.get("URL") or "crossref",
        "type": work.get("type") or "article-journal",
        "title": title_list[0] if title_list else None,
        "container-title": container_list[0] if container_list else None,
        "author": authors or None,
        "issued": {"date-parts": issued_parts} if issued_parts else None,
        "volume": work.get("volume"),
        "issue": work.get("issue"),
        "page": work.get("page"),
        "publisher": work.get("publisher"),
        "DOI": work.get("DOI"),
        "URL": work.get("URL"),
        "ISBN": (work.get("ISBN") or [None])[0] if isinstance(work.get("ISBN"), list) else work.get("ISBN"),
    }


def from_manual(fields: dict[str, Any]) -> SourceResult:
    """Build a CSLItem directly from a form payload."""
    try:
        item = CSLItem.model_validate(fields)
    except Exception as exc:  # noqa: BLE001
        return None, f"Invalid source fields: {exc}"
    return item, None


def coerce_csl_type(value: str) -> CSLType:
    """Public helper for forms — map free text to supported CSL types."""
    allowed: dict[str, CSLType] = {
        "article-journal": "article-journal",
        "book": "book",
        "chapter": "chapter",
        "webpage": "webpage",
        "thesis": "thesis",
        "report": "report",
        "paper-conference": "paper-conference",
    }
    return allowed.get(value, "article-journal")
