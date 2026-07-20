"""Crossref implementation of :class:`CitationProvider`."""

from __future__ import annotations

from typing import Any

import requests

from services.citation_service.models import Work
from services.citation_service.provider import CitationProvider, CitationProviderError

CROSSREF_WORKS = "https://api.crossref.org/works"
REQUEST_TIMEOUT = 18
USER_AGENT = "AcademicDocumentStudio/1.0 (mailto:edu@example.org)"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _authors(items: list) -> list[str]:
    out: list[str] = []
    for a in items or []:
        if not isinstance(a, dict):
            continue
        given = _clean(a.get("given"))
        family = _clean(a.get("family"))
        if family and given:
            initials = " ".join(part[0].upper() + "." for part in given.split() if part)
            out.append(f"{family}, {initials}".strip())
        elif family:
            out.append(family)
        elif a.get("name"):
            out.append(_clean(a.get("name")))
    return out


def _year(message: dict) -> str:
    for key in ("published-print", "published-online", "issued", "created"):
        part = message.get(key)
        if isinstance(part, dict):
            date_parts = part.get("date-parts")
            if date_parts and date_parts[0] and date_parts[0][0]:
                return str(date_parts[0][0])
    return "n.d."


def _work_from_message(message: dict) -> Work:
    titles = message.get("title") or []
    doi = _clean(message.get("DOI")) or None
    return Work(
        title=_clean(titles[0]) if titles else "Untitled",
        authors=_authors(message.get("author") or []),
        year=_year(message),
        journal=(message.get("container-title") or [None])[0],
        doi=doi,
        url=(f"https://doi.org/{doi}" if doi else _clean(message.get("URL")) or None),
        volume=_clean(message.get("volume")) or None,
        issue=_clean(message.get("issue")) or None,
        pages=_clean(message.get("page")) or None,
        publisher=_clean(message.get("publisher")) or None,
    )


class CrossrefProvider(CitationProvider):
    name = "crossref"

    def __init__(self, *, timeout: float = REQUEST_TIMEOUT) -> None:
        self._timeout = timeout

    def search(self, query: str, *, limit: int = 5) -> list[Work]:
        query = _clean(query)
        if not query:
            return []
        limit = max(1, min(int(limit or 5), 20))
        try:
            response = requests.get(
                CROSSREF_WORKS,
                params={
                    "query.bibliographic": query,
                    "rows": limit,
                    "select": "DOI,title,author,container-title,issued,published-print,"
                    "published-online,created,volume,issue,page,publisher,URL",
                },
                timeout=self._timeout,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            items = (response.json().get("message") or {}).get("items") or []
        except requests.RequestException as exc:
            raise CitationProviderError(f"Crossref search failed: {exc}") from exc
        except ValueError as exc:
            raise CitationProviderError(f"Crossref returned invalid JSON: {exc}") from exc

        works: list[Work] = []
        for message in items:
            if isinstance(message, dict) and (message.get("title") or message.get("DOI")):
                works.append(_work_from_message(message))
        return works

    def by_doi(self, doi: str) -> Work | None:
        doi = _clean(doi).removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        if not doi:
            return None
        try:
            response = requests.get(
                f"{CROSSREF_WORKS}/{requests.utils.quote(doi, safe='')}",
                timeout=self._timeout,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            message = response.json().get("message") or {}
        except (requests.RequestException, ValueError) as exc:
            raise CitationProviderError(f"Crossref DOI lookup failed: {exc}") from exc
        return _work_from_message(message) if message else None
