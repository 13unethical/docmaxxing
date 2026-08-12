from __future__ import annotations

from docx import Document

from formatter_v2.render.model import DocumentModel
from formatter_v2.spec import ParagraphRole
from formatter_v2.structure.from_heuristics import HeuristicsExtractor
from formatter_v2.structure.from_word_styles import WordStylesExtractor


def _word_doc_from_lines(lines: list[str]) -> Document:
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    return doc


def _extract_both(lines: list[str]) -> list[DocumentModel]:
    heuristic = HeuristicsExtractor().extract(lines)
    styled = WordStylesExtractor().extract(_word_doc_from_lines(lines))
    return [heuristic, styled]


def test_appendix_paragraphs_go_to_appendices_not_body() -> None:
    lines = [
        "Introduction",
        "Body paragraph one about the topic.",
        "References",
        "Smith, J. (2020). Coastal governance.",
        "8 Appendix A",
        "Extra materials that are not bibliography entries at all.",
    ]
    for model in _extract_both(lines):
        assert any(b.role == ParagraphRole.APPENDIX_HEADING for b in model.appendices)
        assert any(
            isinstance(b.text, str) and "Extra materials" in b.text
            for b in model.appendices
        )
        assert not any(
            isinstance(b.text, str) and "8 Appendix A" in b.text
            for b in model.body
        )


def test_appendix_appears_after_references_in_output() -> None:
    lines = [
        "Introduction",
        "Body paragraph one about the topic.",
        "References",
        "Smith, J. (2020). Coastal governance.",
        "Doe, A. (2019). Flood maps.",
        "Appendix A",
        "More appendix text.",
    ]
    for model in _extract_both(lines):
        refs_texts = [b.text for b in model.references if isinstance(b.text, str)]
        last_ref_pos = max(
            i
            for i, b in enumerate(refs_texts)
            if "Smith" in b or "Doe" in b or "References" in b
        )
        # Construct the effective render order used by pipeline:
        # body → references → appendices.
        all_texts = [
            *(b.text for b in model.body if isinstance(b.text, str)),
            *(b.text for b in model.references if isinstance(b.text, str)),
            *(b.text for b in model.appendices if isinstance(b.text, str)),
        ]
        # Ensure appendix appears after the last references entry.
        assert all_texts.index("Appendix A") > max(
            i
            for i, t in enumerate(all_texts)
            if t in {"Smith, J. (2020). Coastal governance.", "Doe, A. (2019). Flood maps."}
        )


def test_multiple_appendices_keep_their_order() -> None:
    lines = [
        "Introduction",
        "References",
        "Smith, J. (2020). Coastal governance.",
        "Appendix A",
        "Appendix A text.",
        "Appendix B",
        "Appendix B text.",
    ]
    for model in _extract_both(lines):
        appendix_headings = [
            b.text
            for b in model.appendices
            if b.role == ParagraphRole.APPENDIX_HEADING and isinstance(b.text, str)
        ]
        assert appendix_headings == ["Appendix A", "Appendix B"]


def test_document_without_appendix_has_empty_appendices() -> None:
    lines = [
        "Introduction",
        "References",
        "Smith, J. (2020). Coastal governance.",
        "Regular concluding paragraph.",
    ]
    for model in _extract_both(lines):
        assert model.appendices == []


def test_appendix_mention_in_body_does_not_move_content() -> None:
    lines = [
        "Methodology",
        "We designed a mixed-methods instrument for the pilot cohort.",
        "Appendix B contains the full survey instrument",
        "The recruitment stage used stratified sampling by region.",
        "Data collection lasted six weeks in total.",
        "Responses were anonymised before coding.",
        "Two raters validated category assignments independently.",
        "Inter-rater agreement was above the acceptance threshold.",
    ]
    for model in _extract_both(lines):
        assert model.appendices == []
        assert any(
            isinstance(b.text, str)
            and b.text == "Appendix B contains the full survey instrument"
            for b in model.body
        )


def test_see_appendix_c_reference_is_not_treated_as_heading() -> None:
    lines = [
        "Results",
        "For raw items, see Appendix C for instrument details.",
        "We then compare subgroup outcomes by exposure level.",
        "Finally, we discuss limitations and external validity.",
    ]
    for model in _extract_both(lines):
        assert model.appendices == []
        assert any(
            isinstance(b.text, str) and b.text.startswith("For raw items, see Appendix C")
            for b in model.body
        )


def test_real_appendix_heading_in_last_third_still_moves() -> None:
    lines = [
        "Introduction",
        "Body paragraph one about the topic.",
        "Body paragraph two continues the argument.",
        "Body paragraph three discusses method limits.",
        "Body paragraph four adds context and constraints.",
        "References",
        "Smith, J. (2020). Coastal governance.",
        "Appendix C",
        "Survey instrument and coding guide.",
    ]
    for model in _extract_both(lines):
        assert any(
            b.role == ParagraphRole.APPENDIX_HEADING and isinstance(b.text, str) and b.text == "Appendix C"
            for b in model.appendices
        )
        assert any(
            isinstance(b.text, str) and "Survey instrument and coding guide." in b.text
            for b in model.appendices
        )

