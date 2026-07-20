"""CitationService — the only citation entry point the frontend depends on.

It delegates lookups to a swappable :class:`CitationProvider` and formats
normalized :class:`Work` objects into in-text citations and full references for
APA 7, MLA, Harvard and Chicago.
"""

from __future__ import annotations

from typing import Any

from services.citation_service.models import Work
from services.citation_service.provider import CitationProvider

SUPPORTED_STYLES = ("APA 7", "MLA", "Harvard", "Chicago")

# Frontend style label -> citation_engine style key.
_STYLE_MAP = {
    "APA 7": "APA",
    "APA": "APA",
    "MLA": "MLA",
    "MLA 9": "MLA",
    "HARVARD": "Harvard",
    "CHICAGO": "Chicago",
}


def _normalize_style(style: str | None) -> tuple[str, str]:
    label = (style or "APA 7").strip()
    key = _STYLE_MAP.get(label.upper(), _STYLE_MAP.get(label, "APA"))
    return label, key


def _split_author(display: str) -> tuple[str, str]:
    """('Lehtola, T.') -> ('Lehtola', 'T.'). ('WHO') -> ('WHO', '')."""
    display = (display or "").strip()
    if "," in display:
        family, _, initials = display.partition(",")
        return family.strip(), initials.strip()
    parts = display.split()
    if len(parts) >= 2:
        return parts[-1], " ".join(p[0].upper() + "." for p in parts[:-1])
    return display, ""


def _authors_reference(authors: list[str], style_key: str) -> str:
    people = [_split_author(a) for a in authors if a and a.strip()]
    if not people:
        return ""

    if style_key == "MLA":
        first = f"{people[0][0]}, {people[0][1]}".rstrip(", ").strip()
        return first + (", et al." if len(people) > 1 else "")

    formatted = [f"{fam}, {ini}".rstrip(", ").strip() for fam, ini in people]
    if len(formatted) == 1:
        return formatted[0]
    joiner = " & " if style_key in {"APA", "Harvard"} else ", and "
    return ", ".join(formatted[:-1]) + joiner + formatted[-1]


def _format_reference(work: Work, style_key: str) -> str:
    authors = _authors_reference(work.authors, style_key)
    year = work.year or "n.d."
    title = (work.title or "Untitled").strip()
    journal = (work.journal or "").strip()
    vol = (work.volume or "").strip()
    issue = (work.issue or "").strip()
    pages = (work.pages or "").strip()
    doi_url = f"https://doi.org/{work.doi}" if work.doi else (work.url or "")

    if style_key == "APA":
        vol_bit = f", {vol}" if vol else ""
        iss_bit = f"({issue})" if issue else ""
        pg_bit = f", {pages}" if pages else ""
        src = f" {journal}{vol_bit}{iss_bit}{pg_bit}." if journal else ""
        tail = f" {doi_url}" if doi_url else ""
        lead = f"{authors} " if authors else ""
        return f"{lead}({year}). {title}.{src}{tail}".strip()

    if style_key == "MLA":
        extra = ""
        if vol:
            extra += f", vol. {vol}"
        if issue:
            extra += f", no. {issue}"
        if year != "n.d.":
            extra += f", {year}"
        if pages:
            extra += f", pp. {pages}"
        src = f' "{title}." {journal}{extra}.' if journal else f" {title}. {year}."
        tail = f" {doi_url}" if doi_url else ""
        lead = f"{authors.rstrip('.')}." if authors else ""
        return f"{lead}{src}{tail}".strip()

    if style_key == "Harvard":
        vol_bit = f", {vol}" if vol else ""
        iss_bit = f"({issue})" if issue else ""
        pg_bit = f", pp. {pages}" if pages else ""
        src = f" '{title}', {journal}{vol_bit}{iss_bit}{pg_bit}." if journal else f" {title}."
        tail = f" Available at: {doi_url}" if doi_url else ""
        lead = f"{authors} " if authors else ""
        return f"{lead}({year}).{src}{tail}".strip()

    # Chicago (author-date)
    vol_bit = f" {vol}" if vol else ""
    iss_bit = f", no. {issue}" if issue else ""
    pg_bit = f": {pages}" if pages else ""
    src = f' "{title}." {journal}{vol_bit}{iss_bit}{pg_bit}.' if journal else f" {title}."
    tail = f" {doi_url}" if doi_url else ""
    lead = f"{authors.rstrip('.')}. " if authors else ""
    return f"{lead}{year}.{src}{tail}".strip()


def _intext(work: Work, style_key: str) -> str:
    families = work.author_families() or ["Anon."]
    if len(families) == 1:
        name = families[0]
    elif len(families) == 2:
        joiner = " & " if style_key in {"APA", "Harvard"} else " and "
        name = f"{families[0]}{joiner}{families[1]}"
    else:
        name = f"{families[0]} et al."

    if style_key == "MLA":
        return f"({name})"
    return f"({name}, {work.year})"


def _label(work: Work) -> str:
    families = work.author_families() or ["Anon."]
    if len(families) == 1:
        name = families[0]
    elif len(families) == 2:
        name = f"{families[0]} & {families[1]}"
    else:
        name = f"{families[0]} et al."
    return f"{name}, {work.year}"


class CitationService:
    def __init__(self, provider: CitationProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return getattr(self._provider, "name", "provider")

    def search(self, query: str, *, style: str | None = None, limit: int = 5) -> dict[str, Any]:
        label, style_key = _normalize_style(style)
        works = self._provider.search(query, limit=limit)
        return {
            "provider": self.provider_name,
            "style": label,
            "results": [self._present(work, style_key) for work in works],
        }

    def _present(self, work: Work, style_key: str) -> dict[str, Any]:
        payload = work.to_dict()
        payload.update(
            {
                "intext": _intext(work, style_key),
                "reference": _format_reference(work, style_key),
                "label": _label(work),
            }
        )
        return payload
