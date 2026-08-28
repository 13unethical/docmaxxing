"""Author-year citation formats used in real student papers."""

from __future__ import annotations

from services.check_citations import (
    format_citation_summary,
    match_citations,
    parse_in_text_citations,
    parse_reference_entry,
)


def _labels(cites: list[dict]) -> list[str]:
    return [str(c.get("label") or "").lower() for c in cites]


def test_narrative_and_citation():
    cites = parse_in_text_citations("Smith and Jones (2020) argue that coastal planning must change.")
    assert any("smith" in label and "2020" in label for label in _labels(cites))


def test_et_al_parenthetical():
    cites = parse_in_text_citations("Recent reviews agree (Smith et al., 2020).")
    assert any("smith" in label and "2020" in label for label in _labels(cites))


def test_world_bank_nd():
    cites = parse_in_text_citations("Income series follow official tables (World Bank, n.d.).")
    assert any("world bank" in label and "n.d" in label for label in _labels(cites))
    ref = parse_reference_entry("World\xa0Bank.\xa0(n.d.). GDP per capita – Uzbekistan [Data set].")
    assert ref is not None
    assert "world bank" in " ".join(ref["surnames"])
    assert ref["year"] == "n.d"


def test_citation_with_page():
    cites = parse_in_text_citations("The estimate is conservative (Smith, 2020, p. 15).")
    assert any("smith" in label and "2020" in label for label in _labels(cites))
    assert not any("15" in (c.get("year") or "") for c in cites)


def test_multiple_sources_in_one_parenthesis():
    cites = parse_in_text_citations("Several studies agree (Smith et al., 2020; Jones, 2019).")
    labels = _labels(cites)
    assert any("smith" in label and "2020" in label for label in labels)
    assert any("jones" in label and "2019" in label for label in labels)


def test_organization_unesco():
    cites = parse_in_text_citations("The framework is set out (UNESCO, 2021).")
    assert any("unesco" in label and "2021" in label for label in _labels(cites))


def test_missing_in_text_sources_use_direct_wording():
    result = match_citations(
        body_text="The claim is overstated (Khasanov, 2022; Abdullaev, 2023).",
        reference_lines=[
            "Bryman, A. (2012). The End of the Paradigm Wars?",
        ],
    )
    assert "2 sources cited in text but missing from your reference list" in result["summary"]
    assert "khasanov" in result["summary"].lower() or any("khasanov" in m.lower() for m in result["mismatches"])


def test_format_citation_summary_missing_only():
    message = format_citation_summary(
        listed=14,
        cited=28,
        uncited=[],
        missing=[{"label": f"A {i}"} for i in range(14)],
    )
    assert message == "14 sources cited in text but missing from your reference list"
