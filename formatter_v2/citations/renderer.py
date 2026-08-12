"""Render in-text citations and bibliographies via citeproc-py + vendored CSL."""

from __future__ import annotations

import string
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal, Sequence

from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle
from citeproc import formatter as citeproc_formatter
from citeproc.source.json import CiteProcJSON

from formatter_v2.citations.models import CSLItem, TextFragment
from formatter_v2.spec import StyleName

CSL_DIR = Path(__file__).resolve().parent / "csl"

# Requested name ``chicago-note-bibliography`` does not exist upstream.
# Closest match for StyleName.CHICAGO17:
#   chicago-notes-bibliography-17th-edition.csl
CSL_STYLE_FOR_STYLE_NAME: dict[StyleName, str] = {
    StyleName.APA7: "apa.csl",
    StyleName.MLA9: "modern-language-association.csl",
    StyleName.CHICAGO17: "chicago-notes-bibliography-17th-edition.csl",
    StyleName.IEEE: "ieee.csl",
    StyleName.HARVARD: "harvard-cite-them-right.csl",
}

CitationMode = Literal["in_text", "note"]
FormattedText = list[TextFragment]


class _FragmentHTMLParser(HTMLParser):
    """Convert citeproc HTML output into FormattedText fragments."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fragments: FormattedText = []
        self._italic = 0
        self._bold = 0
        self._small_caps = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower in {"i", "em"}:
            self._italic += 1
        elif lower in {"b", "strong"}:
            self._bold += 1
        elif lower == "span":
            style = dict(attrs).get("style") or ""
            if "small-caps" in style:
                self._small_caps += 1

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"i", "em"} and self._italic:
            self._italic -= 1
        elif lower in {"b", "strong"} and self._bold:
            self._bold -= 1
        elif lower == "span" and self._small_caps:
            self._small_caps -= 1

    def handle_data(self, data: str) -> None:
        if not data:
            return
        self.fragments.append(
            TextFragment(
                text=data,
                italic=self._italic > 0,
                bold=self._bold > 0,
                small_caps=self._small_caps > 0,
            )
        )


def html_to_formatted_text(html: str) -> FormattedText:
    parser = _FragmentHTMLParser()
    parser.feed(html)
    parser.close()
    return _merge_adjacent(parser.fragments)


def formatted_text_plain(fragments: FormattedText) -> str:
    return "".join(f.text for f in fragments)


def _merge_adjacent(fragments: FormattedText) -> FormattedText:
    if not fragments:
        return []
    merged: FormattedText = [fragments[0].model_copy()]
    for frag in fragments[1:]:
        prev = merged[-1]
        if (
            prev.italic == frag.italic
            and prev.bold == frag.bold
            and prev.small_caps == frag.small_caps
        ):
            merged[-1] = prev.model_copy(update={"text": prev.text + frag.text})
        else:
            merged.append(frag.model_copy())
    return merged


def _resolve_style_name(style: StyleName | str) -> StyleName:
    if isinstance(style, StyleName):
        if style == StyleName.CUSTOM:
            return StyleName.HARVARD
        return style
    return StyleName(style)


def _csl_path(style: StyleName) -> Path:
    filename = CSL_STYLE_FOR_STYLE_NAME.get(style)
    if not filename:
        raise ValueError(f"No CSL mapping for style {style!r}")
    path = CSL_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Vendored CSL style missing: {path}")
    return path


def _item_to_csl_json(item: CSLItem) -> dict:
    data = item.model_dump(by_alias=True, exclude_none=True)
    # citeproc-py lowercases ids when loading CiteProcJSON.
    data["id"] = str(data["id"])
    return data


def _author_year_key(item: CSLItem) -> tuple[str, int | None]:
    names: list[str] = []
    for person in item.author or []:
        if person.family:
            names.append(person.family.casefold())
        elif person.literal:
            names.append(person.literal.casefold())
    if not names and item.title:
        names.append(item.title.casefold())
    year = None
    if item.issued and item.issued.date_parts and item.issued.date_parts[0]:
        year = int(item.issued.date_parts[0][0])
    return ("|".join(names), year)


def assign_year_suffixes(items: Sequence[CSLItem]) -> list[CSLItem]:
    """citeproc-py does not fully implement disambiguate-add-year-suffix — do it here."""
    groups: dict[tuple[str, int | None], list[int]] = {}
    for idx, item in enumerate(items):
        key = _author_year_key(item)
        if key[1] is None:
            continue
        groups.setdefault(key, []).append(idx)

    out = list(items)
    for indices in groups.values():
        if len(indices) < 2:
            continue
        for offset, idx in enumerate(indices):
            suffix = string.ascii_lowercase[offset] if offset < 26 else str(offset + 1)
            out[idx] = out[idx].model_copy(update={"year_suffix": suffix})
    return out


def _load_bibliography(
    items: Sequence[CSLItem],
    style: StyleName,
) -> tuple[CitationStylesBibliography, list[CSLItem], dict[str, Citation]]:
    prepared = assign_year_suffixes(items)
    style_path = _csl_path(style)
    # Prefer vendored en-US locale sitting next to the CSL files.
    import citeproc.frontend as frontend

    original_locales = frontend.LOCALES_PATH
    frontend.LOCALES_PATH = str(CSL_DIR)
    try:
        csl_style = CitationStylesStyle(str(style_path), locale="en-US", validate=False)
    finally:
        frontend.LOCALES_PATH = original_locales

    json_items = [_item_to_csl_json(item) for item in prepared]
    source = CiteProcJSON(json_items)
    bibliography = CitationStylesBibliography(csl_style, source, citeproc_formatter.html)
    # Register in list order = order of appearance (IEEE numbering, …).
    citations_by_id: dict[str, Citation] = {}
    for item in prepared:
        key = str(item.id).lower()
        citation = Citation([CitationItem(key)])
        bibliography.register(citation)
        citations_by_id[key] = citation
    return bibliography, prepared, citations_by_id


def render_bibliography(
    items: Sequence[CSLItem],
    style: StyleName | str,
) -> list[FormattedText]:
    """Render a bibliography for ``items`` in the given academic style."""
    style_name = _resolve_style_name(style)
    if not items:
        return []
    bibliography, _prepared, _by_id = _load_bibliography(items, style_name)
    return [html_to_formatted_text(str(entry)) for entry in bibliography.bibliography()]


def render_citation(
    item_ids: Sequence[str],
    style: StyleName | str,
    mode: CitationMode,
    items: Sequence[CSLItem],
) -> FormattedText:
    """Render one in-text / note citation.

    ``items`` is the full ordered corpus (order of appearance). Required so IEEE
    bracket numbers and year-suffixes stay consistent with the bibliography.
    ``mode`` selects note vs in-text intent; the CSL file drives the actual layout.
    """
    del mode  # CSL class (in-text vs note) already encodes citation layout.
    style_name = _resolve_style_name(style)
    if not item_ids:
        return []
    bibliography, _prepared, citations_by_id = _load_bibliography(items, style_name)
    keys = [str(i).lower() for i in item_ids]

    def _warn(_citation_item: CitationItem) -> str:
        return "??"

    if len(keys) == 1 and keys[0] in citations_by_id:
        citation = citations_by_id[keys[0]]
    else:
        citation = Citation([CitationItem(k) for k in keys])
        bibliography.register(citation)
    rendered = bibliography.cite(citation, _warn)
    return html_to_formatted_text(str(rendered))


def style_csl_filename(style: StyleName | str) -> str:
    return CSL_STYLE_FOR_STYLE_NAME[_resolve_style_name(style)]
