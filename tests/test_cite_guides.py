"""Pilot /cite/[style]-[source] pages — top-10 only, real CSL examples, overlap gate."""

from __future__ import annotations

from services.cite_guides import (
    PILOT_LIMIT,
    get_guide,
    pairwise_overlap_report,
    pilot_guides,
    top_pilot_rows,
)


def test_pilot_is_exactly_top_ten_supported_pairs() -> None:
    rows = top_pilot_rows()
    assert len(rows) == PILOT_LIMIT
    guides = pilot_guides()
    assert len(guides) == PILOT_LIMIT
    paths = {g.path for g in guides}
    assert paths == {f"/cite/{r['style_slug']}-{r['source_slug']}" for r in rows}


def test_examples_come_from_csl_renderer() -> None:
    guide = get_guide("apa7", "journal-article")
    assert guide is not None
    assert len(guide.examples) == 3
    normal = guide.examples[0].bibliography
    assert "Park" in normal
    assert "Journal of Campus Research" in normal
    assert "doi.org" in normal.lower() or "10.1234" in normal
    assert guide.examples[0].in_text.startswith("(")


def test_unknown_pair_is_not_a_guide() -> None:
    assert get_guide("ieee", "youtube-video") is None
    assert get_guide("apa7", "chatgpt") is None


def test_pairwise_overlap_under_thirty_percent() -> None:
    report = pairwise_overlap_report()
    assert report["passes_goal"], (
        f"worst overlap {report['worst_overlap_pct']}% — top pairs: {report['pairs'][:3]}"
    )
