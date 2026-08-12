"""Canonical full DocumentModel for previews and builder smoke tests."""

from __future__ import annotations

from datetime import date

from formatter_v2.render.document import Block
from formatter_v2.render.model import DocumentModel
from formatter_v2.spec import CoverPage, FormatSpec, ParagraphRole


def captioned_table_blocks(description: str, rows: list[str], spec: FormatSpec) -> list[Block]:
    """Table caption above/below per ``spec.captions.table_position``."""
    caption = Block(ParagraphRole.TABLE_CAPTION, description)
    body_rows = [Block(ParagraphRole.TABLE_HEADER if i == 0 else ParagraphRole.TABLE_CELL, row) for i, row in enumerate(rows)]
    if spec.captions.table_position == "above":
        return [caption, *body_rows]
    return [*body_rows, caption]


def captioned_figure_blocks(description: str, placeholder: str, spec: FormatSpec) -> list[Block]:
    """Figure caption above/below per ``spec.captions.figure_position``."""
    caption = Block(ParagraphRole.FIGURE_CAPTION, description)
    figure = Block(ParagraphRole.BODY, placeholder)
    if spec.captions.figure_position == "above":
        return [caption, figure]
    return [figure, caption]


def sample_full_document(spec: FormatSpec) -> DocumentModel:
    """Full academic sample: cover identity, front matter, body with
    table+figure, references, two appendices."""
    cover = CoverPage(
        enabled=True,
        title="Climate Adaptation in Coastal Cities",
        subtitle="A comparative review of planning responses",
        student_name="Alex Morgan",
        university="University of Example",
        course="Environmental Policy 301",
        lecturer="Dr. Sam Rivera",
        submission_date=date(2026, 5, 15),
        word_count=2000,
        top_spacer_lines=3,
        page_break_after=True,
    )
    front = [
        Block(ParagraphRole.ABSTRACT_HEADING, "Abstract"),
        Block(
            ParagraphRole.ABSTRACT,
            "Coastal municipalities face rising seas and compound flood risk. "
            "This paper compares adaptation portfolios across three port cities.",
        ),
        Block(ParagraphRole.KEYWORDS, "Keywords: climate adaptation, coastal planning, resilience"),
    ]
    body: list[Block] = [
        Block(ParagraphRole.HEADING_1, "Introduction"),
        Block(
            ParagraphRole.BODY_FIRST,
            "Sea-level rise is already reshaping municipal budgets and land-use plans.",
        ),
        Block(
            ParagraphRole.BODY,
            "Planners must weigh hard protection against retreat and nature-based options.",
        ),
        Block(ParagraphRole.HEADING_2, "Methods"),
        Block(
            ParagraphRole.BODY,
            "We coded adaptation instruments from statutory plans and interviews.",
        ),
        *captioned_table_blocks(
            "Adaptation instruments by city",
            ["City | Instrument | Status", "Rotterdam | Storm surge barrier | Operational"],
            spec,
        ),
        *captioned_figure_blocks(
            "Flood exposure under RCP4.5",
            "[Figure: map placeholder]",
            spec,
        ),
        Block(ParagraphRole.HEADING_1, "Discussion"),
        Block(
            ParagraphRole.BODY,
            "Institutional capacity predicts whether soft measures scale beyond pilots.",
        ),
    ]
    references = [
        Block(ParagraphRole.REFERENCES_HEADING, spec.references.heading_text),
        Block(
            ParagraphRole.REFERENCES_ENTRY,
            "IPCC. (2022). Climate Change 2022: Impacts, Adaptation and Vulnerability.",
        ),
        Block(
            ParagraphRole.REFERENCES_ENTRY,
            "Smith, J. (2020). Coastal governance after the flood. Ocean Press.",
        ),
    ]
    appendices = [
        Block(ParagraphRole.APPENDIX_HEADING, "Appendix"),  # retitled by builder
        Block(ParagraphRole.BODY, "Interview protocol and coding sheet."),
        Block(ParagraphRole.APPENDIX_HEADING, "Appendix"),
        Block(ParagraphRole.BODY, "Supplementary flood-depth tables."),
    ]
    return DocumentModel(
        cover=cover,
        front_matter=front,
        body=body,
        references=references,
        appendices=appendices,
    )
