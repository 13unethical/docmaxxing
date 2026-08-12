"""CSL citation tests — no live network for render paths."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from formatter_v2.citations.models import CSLItem, TextFragment
from formatter_v2.citations.renderer import (
    CSL_STYLE_FOR_STYLE_NAME,
    formatted_text_plain,
    render_bibliography,
    render_citation,
)
from formatter_v2.citations.sources import from_doi, from_isbn, from_manual, from_raw_string, from_url
from formatter_v2.spec import StyleName

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "csl"


def _load(name: str) -> list[CSLItem]:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [CSLItem.model_validate(row) for row in data]


def test_ieee_bibliography_is_numbered_in_order_of_appearance() -> None:
    # Appearance order: beta, alpha, gamma (not alphabetical).
    corpus = _load("ieee_order.json")
    ordered = [corpus[1], corpus[0], corpus[2]]
    entries = render_bibliography(ordered, StyleName.IEEE)
    plains = [formatted_text_plain(e) for e in entries]
    assert plains[0].startswith("[1]")
    assert plains[1].startswith("[2]")
    assert plains[2].startswith("[3]")
    assert "Managed Retreat" in plains[0]
    assert "Coastal Flood Barriers" in plains[1]
    assert "Nature-Based Shoreline" in plains[2]


def test_ieee_intext_renders_bracket_number_matching_position() -> None:
    corpus = _load("ieee_order.json")
    ordered = [corpus[1], corpus[0], corpus[2]]  # beta=1, alpha=2, gamma=3
    cite = render_citation(["alpha2018"], StyleName.IEEE, "in_text", items=ordered)
    assert formatted_text_plain(cite) == "[2]"


def test_apa_uses_ampersand_inside_parentheses() -> None:
    items = _load("apa_two_authors.json")
    cite = render_citation([items[0].id], StyleName.APA7, "in_text", items=items)
    plain = formatted_text_plain(cite)
    assert "&" in plain
    assert "Smith" in plain and "Jones" in plain
    assert plain.startswith("(") and plain.endswith(")")


def test_apa_et_al_from_three_authors() -> None:
    items = _load("apa_three_authors.json")
    cite = render_citation([items[0].id], StyleName.APA7, "in_text", items=items)
    plain = formatted_text_plain(cite)
    assert "et al." in plain
    assert "Nguyen" in plain
    assert "Okeke" not in plain


def test_harvard_ctr_et_al_from_four_authors() -> None:
    items = _load("harvard_four_authors.json")
    cite = render_citation([items[0].id], StyleName.HARVARD, "in_text", items=items)
    plain = formatted_text_plain(cite)
    assert "et al." in plain
    assert "Brown" in plain
    assert "Clark" not in plain


def test_chicago_footnote_contains_source_title() -> None:
    items = _load("chicago_book.json")
    note = render_citation([items[0].id], StyleName.CHICAGO17, "note", items=items)
    plain = formatted_text_plain(note)
    assert "The Lost Title of Coastal Memory" in plain


def test_mla_intext_has_no_year() -> None:
    items = _load("mla_book.json")
    cite = render_citation([items[0].id], StyleName.MLA9, "in_text", items=items)
    plain = formatted_text_plain(cite)
    assert "2018" not in plain
    assert "Smith" in plain


def test_same_author_same_year_gets_a_and_b_suffix() -> None:
    items = _load("same_author_year.json")
    c1 = formatted_text_plain(
        render_citation([items[0].id], StyleName.APA7, "in_text", items=items)
    )
    c2 = formatted_text_plain(
        render_citation([items[1].id], StyleName.APA7, "in_text", items=items)
    )
    assert "2020a" in c1
    assert "2020b" in c2
    bib = [formatted_text_plain(e) for e in render_bibliography(items, StyleName.APA7)]
    assert any("2020a" in row for row in bib)
    assert any("2020b" in row for row in bib)


def test_journal_name_is_italic_fragment_not_plain_text() -> None:
    items = _load("journal_article.json")
    entry = render_bibliography(items, StyleName.APA7)[0]
    italic_bits = [f for f in entry if f.italic]
    assert italic_bits, "expected at least one italic fragment"
    joined_italic = "".join(f.text for f in italic_bits)
    assert "Journal of Examples" in joined_italic
    # Must not be a single unstyled blob containing the journal name only as plain text.
    assert not (
        len(entry) == 1
        and not entry[0].italic
        and "Journal of Examples" in entry[0].text
    )


def test_book_chapter_renders_with_editors() -> None:
    items = _load("book_chapter.json")
    plain = formatted_text_plain(render_bibliography(items, StyleName.APA7)[0])
    assert "Legal Tools for Managed Retreat" in plain
    assert "Editor" in plain
    assert "Climate Law in Practice" in plain
    assert "eds." in plain.lower() or "Ed." in plain or "edited" in plain.lower()


def test_source_without_author_falls_back_to_title() -> None:
    items = _load("no_author.json")
    cite = formatted_text_plain(
        render_citation([items[0].id], StyleName.APA7, "in_text", items=items)
    )
    bib = formatted_text_plain(render_bibliography(items, StyleName.APA7)[0])
    assert "About Climate Policy" in cite
    assert "About Climate Policy" in bib


def test_csl_style_mapping_covers_five_styles() -> None:
    for style in (
        StyleName.HARVARD,
        StyleName.APA7,
        StyleName.MLA9,
        StyleName.CHICAGO17,
        StyleName.IEEE,
    ):
        assert style in CSL_STYLE_FOR_STYLE_NAME
        path = (
            Path(__file__).resolve().parents[1]
            / "formatter_v2"
            / "citations"
            / "csl"
            / CSL_STYLE_FOR_STYLE_NAME[style]
        )
        assert path.is_file(), path


# ---------------------------------------------------------------------------
# sources.py — mocked requests only
# ---------------------------------------------------------------------------


def test_from_doi_parses_csl_json_response() -> None:
    payload = {
        "id": "https://doi.org/10.1000/xyz",
        "type": "article-journal",
        "title": "DOI Sample",
        "author": [{"family": "Lee", "given": "Kim"}],
        "issued": {"date-parts": [[2023]]},
        "DOI": "10.1000/xyz",
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    with patch("formatter_v2.citations.sources.requests.get", return_value=mock_resp) as get:
        item, err = from_doi("10.1000/xyz")
    assert err is None
    assert item is not None
    assert item.title == "DOI Sample"
    assert item.DOI == "10.1000/xyz"
    assert get.call_args.kwargs["headers"]["Accept"] == "application/vnd.citationstyles.csl+json"


def test_from_doi_network_error_returns_message() -> None:
    with patch(
        "formatter_v2.citations.sources.requests.get",
        side_effect=__import__("requests").Timeout(),
    ):
        item, err = from_doi("10.1000/xyz")
    assert item is None
    assert err is not None
    assert "timeout" in err.lower() or "timed out" in err.lower()


def test_from_isbn_maps_open_library() -> None:
    payload = {
        "title": "Open Library Book",
        "publishers": ["Example Press"],
        "publish_places": ["Boston"],
        "publish_date": "2017",
        "authors": [{"key": "/authors/OL1A"}],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    with patch("formatter_v2.citations.sources.requests.get", return_value=mock_resp):
        item, err = from_isbn("978-0-123456-78-9")
    assert err is None
    assert item is not None
    assert item.type == "book"
    assert item.title == "Open Library Book"
    assert item.publisher == "Example Press"
    assert item.issued is not None
    assert item.issued.date_parts == [[2017]]


def test_from_url_builds_webpage_item() -> None:
    html = """
    <html><head>
      <meta property="og:title" content="Page Title About Reefs" />
      <meta name="author" content="Casey Author" />
      <meta property="article:published_time" content="2021-05-01" />
      <title>Fallback</title>
    </head><body></body></html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html
    with patch("formatter_v2.citations.sources.requests.get", return_value=mock_resp):
        item, err = from_url("https://example.com/reefs")
    assert err is None
    assert item is not None
    assert item.type == "webpage"
    assert item.title == "Page Title About Reefs"
    assert item.author and item.author[0].literal == "Casey Author"
    assert item.issued and item.issued.date_parts == [[2021]]


def test_from_raw_string_rejects_low_score() -> None:
    payload = {"message": {"items": [{"score": 10, "title": ["Nope"], "type": "book"}]}}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    with patch("formatter_v2.citations.sources.requests.get", return_value=mock_resp):
        item, err = from_raw_string("some obscure string")
    assert item is None
    assert err == "could not recognise the source"


def test_from_manual_accepts_form_fields() -> None:
    item, err = from_manual(
        {
            "id": "manual-1",
            "type": "report",
            "title": "City Adaptation Baseline",
            "author": [{"literal": "City Planning Office"}],
            "issued": {"date-parts": [[2024]]},
        }
    )
    assert err is None
    assert item is not None
    assert item.type == "report"
    assert isinstance(item, CSLItem)


def test_references_entry_accepts_formatted_text_in_docx() -> None:
    """Smoke: FormattedText on REFERENCES_ENTRY survives into runs."""
    from formatter_v2.profiles import load_profile
    from formatter_v2.render.document import Block, render_document
    from formatter_v2.resolve import resolve_format_spec
    from formatter_v2.spec import ParagraphRole, UserOverrides

    fragments = [
        TextFragment(text="Smith, J. "),
        TextFragment(text="Journal of Examples", italic=True),
        TextFragment(text="."),
    ]
    profile = load_profile(StyleName.APA7)
    spec = resolve_format_spec(profile, UserOverrides()).spec
    doc = render_document(
        [Block(ParagraphRole.REFERENCES_ENTRY, fragments)],
        spec,
    )
    para = doc.paragraphs[0]
    assert para.text == "Smith, J. Journal of Examples."
    italic_runs = [r for r in para.runs if r.italic]
    assert any("Journal of Examples" in (r.text or "") for r in italic_runs)
