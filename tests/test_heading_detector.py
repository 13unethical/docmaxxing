"""Regression tests for Learning Journal heading detection bugs.

HeadingDetector must identify the heading FIRST and never absorb the first
sentence or promote stopwords (are / the / as) into headings.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from formatter.document_reconstruction import reconstruct_blocks, reconstruct_document_before_format
from services.heading_detector import HeadingDetector
from services.document_structure_engine import detect_heading_level, split_embedded_heading_paragraph

LEARNING_JOURNAL = Path("/Users/nazirov/Desktop/Learning-Journal.docx")


@pytest.fixture
def detector() -> HeadingDetector:
    return HeadingDetector()


# ---------------------------------------------------------------------------
# Unit: HeadingDetector splits (bugs 1–6)
# ---------------------------------------------------------------------------

CASES = [
    (
        "bug1_entry2",
        "Journal Entry 2: Strategic Resource Reconfiguration. Building on the evolutionary framework, this entry examines how firms leverage internal strengths.",
        "Journal Entry 2: Strategic Resource Reconfiguration.",
        "Building on the evolutionary framework, this entry examines how firms leverage internal strengths.",
    ),
    (
        "bug3_entry1",
        "Journal Entry 1: Digital Transformation as an Evolutionary Process. Digital transformation is not a discrete event but an ongoing process.",
        "Journal Entry 1: Digital Transformation as an Evolutionary Process.",
        "Digital transformation is not a discrete event but an ongoing process.",
    ),
    (
        "bug4_entry3",
        "Journal Entry 3: Entrepreneurial Implementation. Survival in international markets depends on integrating digital tools into core strategic operations.",
        "Journal Entry 3: Entrepreneurial Implementation.",
        "Survival in international markets depends on integrating digital tools into core strategic operations.",
    ),
    (
        "bug5_entry4",
        "Journal Entry 4: Entrepreneurial Agility in Global Markets. Strategic application of firm-specific resources remains the key to success in digitally transformed markets.",
        "Journal Entry 4: Entrepreneurial Agility in Global Markets.",
        "Strategic application of firm-specific resources remains the key to success in digitally transformed markets.",
    ),
    (
        "bug6_reflection",
        "Reflection. This journal has synthesized the evolutionary nature of digital transformation with the strategic necessity of resource management.",
        "Reflection",
        "This journal has synthesized the evolutionary nature of digital transformation with the strategic necessity of resource management.",
    ),
]


@pytest.mark.parametrize("case_id,merged,heading,body", CASES, ids=[c[0] for c in CASES])
def test_heading_detector_splits_learning_journal_cases(
    detector: HeadingDetector,
    case_id: str,
    merged: str,
    heading: str,
    body: str,
):
    split = detector.split_embedded(merged)
    assert split is not None, case_id
    assert split.heading == heading
    assert split.body == body
    assert split.body[:1].isupper()


def test_heading_detector_never_promotes_stopwords(detector: HeadingDetector):
    for word in ("are", "the", "as", "in", "of", "because", "however"):
        assert detector.is_forbidden_heading(word)
        assert detect_heading_level(word, True) == 0


def test_heading_detector_never_splits_barney_sentence(detector: HeadingDetector):
    """Bug 2: never promote 'are' (or other stopwords) out of a prose sentence."""
    prose = (
        "According to Barney (1991), sustainable advantage requires resources that are "
        "valuable, rare, inimitable, and non-substitutable."
    )
    assert detector.split_embedded(prose) is None
    assert detect_heading_level(prose, True) == 0
    for token in prose.split():
        if token.lower().strip(".,;:") in {"are", "that", "and"}:
            assert detect_heading_level(token, True) == 0


def test_heading_detector_space_merged_journal_without_period(detector: HeadingDetector):
    merged = "Journal Entry 1: Reflection on Week 1 Today I learned about entrepreneurship."
    split = detector.split_embedded(merged)
    assert split is not None
    assert split.heading.startswith("Journal Entry 1:")
    assert "Today I learned" in (split.body or "")
    assert "Today" not in split.heading
    assert split.body[:1].isupper()


def test_heading_detector_references_does_not_absorb_citation(detector: HeadingDetector):
    merged = "References Barney, J. (1991). Hard Resources and Long-lasting Competitive Advantage."
    split = detector.split_embedded(merged)
    assert split is not None
    assert split.heading == "References"
    assert split.body.startswith("Barney")


def test_split_embedded_wrapper_matches_detector():
    text = (
        "Journal Entry 2: Strategic Resource Reconfiguration. "
        "Building on the evolutionary framework, this entry examines firms."
    )
    heading, body = split_embedded_heading_paragraph(text)
    assert heading == "Journal Entry 2: Strategic Resource Reconfiguration."
    assert body is not None and body.startswith("Building on")


# ---------------------------------------------------------------------------
# Integration: full Learning-Journal.docx reconstruction
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not LEARNING_JOURNAL.exists(), reason="Learning-Journal.docx not on Desktop")
def test_learning_journal_docx_reconstruction_headings():
    doc = Document(str(LEARNING_JOURNAL))
    result = reconstruct_document_before_format(doc, prefer_ai=False)

    headings = [a.text for a in result.assignments if a.level and a.level >= 2]
    bodies = [a.text for a in result.assignments if a.level is None]

    assert any(h.startswith("Journal Entry 1: Digital Transformation as an Evolutionary Process") for h in headings)
    assert any(h.startswith("Journal Entry 2: Strategic Resource Reconfiguration") for h in headings)
    assert any(h.startswith("Journal Entry 3: Entrepreneurial Implementation") for h in headings)
    assert any(h.startswith("Journal Entry 4: Entrepreneurial Agility in Global Markets") for h in headings)
    assert "Reflection" in headings
    assert "Reflection." not in headings
    assert "References" in headings

    # Never invent stopword headings.
    assert "are" not in headings
    assert "the" not in headings
    assert "as" not in headings

    # Citations must stay body/reference — never Heading 2.
    assert not any(h.startswith("Barney") for h in headings)

    # First sentence of each body must start with a capital and must not be a title fragment.
    for body in bodies:
        if not body or body.startswith("##") or body.startswith("Barney") or body.startswith("Chen"):
            continue
        if body.startswith("Digital transformation represents"):
            continue  # intro paragraph
        assert body[:1].isupper(), body[:60]
        assert not body.startswith("as an Evolutionary")
        assert not body.startswith("the evolutionary framework")
        assert not body.startswith(". ")
        assert not body.startswith("Survival") or body.startswith("Survival in")

    # Heading must not include first sentence fragments.
    for h in headings:
        if h.startswith("Journal Entry 2"):
            assert "Building on" not in h
            assert h.rstrip(".").endswith("Reconfiguration")
        if h.startswith("Journal Entry 3"):
            assert "Survival" not in h
        if h.startswith("Journal Entry 1"):
            assert "as an Evolutionary Process" in h
        if h.startswith("Journal Entry 4"):
            assert "Strategic application" not in h


def test_soft_newlines_never_split_barney_sentence():
    """Root cause: soft wraps mid-sentence must not create paragraphs or headings."""
    merged = (
        "Journal Entry 2: Strategic Resource Reconfiguration. Building on the evolutionary "
        "framework, this entry examines how firms leverage internal strengths. According to "
        "Barney (1991), sustainable advantage requires resources that\nare\nvaluable, rare, "
        "inimitable, and non-substitutable (VRIN)."
    )
    blocks = reconstruct_blocks([merged], document_type="learning_journal")
    texts = [b.text for b in blocks]
    assert "are" not in {t.lower() for t in texts}
    assert "Are" not in texts
    body = next(b.text for b in blocks if b.kind == "body" and "Barney" in b.text)
    assert "that are valuable" in body
    assert "\n" not in body
    assert blocks[0].text.startswith("Journal Entry 2: Strategic Resource Reconfiguration")
    assert "Building on" not in blocks[0].text


def test_line_wrapped_orphan_tokens_are_merged():
    """When wraps already became separate paragraphs, rejoin the sentence."""
    paras = [
        "Journal Entry 2: Strategic Resource Reconfiguration. Building on the evolutionary "
        "framework, this entry examines how firms. According to Barney (1991), sustainable "
        "advantage requires resources that",
        "are",
        "valuable, rare, inimitable, and non-substitutable (VRIN).",
    ]
    blocks = reconstruct_blocks(paras, document_type="learning_journal")
    texts = [b.text for b in blocks]
    assert not any(t.lower() == "are" for t in texts)
    joined = " ".join(texts)
    assert "that are valuable" in joined
