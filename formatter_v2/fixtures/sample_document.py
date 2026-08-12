"""Canonical sample document covering every ParagraphRole."""

from __future__ import annotations

from formatter_v2.render.document import Block
from formatter_v2.spec import ParagraphRole


def sample_blocks() -> list[Block]:
    """Meaningful English academic text — one or more blocks per ParagraphRole."""
    return [
        Block(ParagraphRole.COVER_TITLE, "Climate Adaptation in Coastal Cities"),
        Block(ParagraphRole.COVER_FIELD, "Alex Morgan"),
        Block(ParagraphRole.COVER_FIELD, "University of Example"),
        Block(ParagraphRole.COVER_FIELD, "Module: Environmental Policy 301"),
        Block(ParagraphRole.DOC_TITLE, "Climate Adaptation in Coastal Cities"),
        Block(ParagraphRole.SUBTITLE, "A comparative review of planning responses"),
        Block(ParagraphRole.ABSTRACT_HEADING, "Abstract"),
        Block(
            ParagraphRole.ABSTRACT,
            "Coastal cities face accelerating flood risk as sea levels rise. "
            "This paper reviews adaptation strategies across five jurisdictions "
            "and argues that institutional capacity predicts implementation quality "
            "more reliably than GDP alone.",
        ),
        Block(
            ParagraphRole.KEYWORDS,
            "Keywords: climate adaptation, coastal planning, flood risk, governance",
        ),
        Block(ParagraphRole.TOC_HEADING, "Table of Contents"),
        Block(ParagraphRole.TOC_ENTRY, "1. Introduction ........................ 1"),
        Block(ParagraphRole.TOC_ENTRY, "2. Methods ............................. 3"),
        Block(ParagraphRole.ABBREVIATION_ENTRY, "IPCC — Intergovernmental Panel on Climate Change"),
        Block(ParagraphRole.ABBREVIATION_ENTRY, "SLR — Sea-Level Rise"),
        Block(ParagraphRole.HEADING_1, "Introduction"),
        Block(
            ParagraphRole.BODY_FIRST,
            "Urban coastlines concentrate population, infrastructure, and economic activity "
            "in zones increasingly exposed to storm surge and chronic inundation.",
        ),
        Block(
            ParagraphRole.BODY,
            "Scholars distinguish between protective, accommodative, and retreat-oriented "
            "strategies, yet comparative evidence on what governments actually implement "
            "remains fragmented.",
        ),
        Block(ParagraphRole.HEADING_2, "Research Questions"),
        Block(
            ParagraphRole.BODY,
            "The study asks how planning regimes allocate responsibility for adaptation "
            "and whether participatory processes change the distribution of costs.",
        ),
        Block(ParagraphRole.HEADING_3, "Scope and Limitations"),
        Block(
            ParagraphRole.BODY,
            "The analysis is limited to publicly available plans published after 2015 "
            "and does not evaluate private insurance markets in depth.",
        ),
        Block(ParagraphRole.HEADING_4, "Terminological notes."),
        Block(
            ParagraphRole.BODY,
            "Throughout, adaptation refers to adjustments that reduce harm from climate "
            "impacts already locked into the climate system.",
        ),
        Block(
            ParagraphRole.BLOCK_QUOTE,
            "Adaptation is not merely a technical fix; it is a political process "
            "that redistributes risk across communities and generations.",
        ),
        Block(ParagraphRole.LIST_BULLET, "Hard protection (sea walls, barriers)"),
        Block(ParagraphRole.LIST_BULLET, "Nature-based solutions (wetlands, dunes)"),
        Block(ParagraphRole.LIST_NUMBER, "Map exposure under mid-century scenarios"),
        Block(ParagraphRole.LIST_NUMBER, "Score institutional capacity indicators"),
        Block(ParagraphRole.TABLE_CAPTION, "Table 1. Adaptation instruments by city"),
        Block(ParagraphRole.TABLE_HEADER, "City | Instrument | Status"),
        Block(ParagraphRole.TABLE_CELL, "Rotterdam | Storm surge barrier | Operational"),
        Block(ParagraphRole.FIGURE_CAPTION, "Figure 1. Flood exposure under RCP4.5"),
        Block(ParagraphRole.APPENDIX_HEADING, "Appendix A"),
        Block(
            ParagraphRole.BODY,
            "Supplementary coding sheets and plan excerpts are available on request.",
        ),
        Block(ParagraphRole.FOOTNOTE, "IPCC AR6 Working Group II, 2022."),
        Block(ParagraphRole.REFERENCES_HEADING, "References"),
        Block(
            ParagraphRole.REFERENCES_ENTRY,
            "Aerts, J. C. J. H. (2018). Coastal flood risk and adaptation. Nature Climate Change.",
        ),
        Block(
            ParagraphRole.REFERENCES_ENTRY,
            "Adger, W. N. (2006). Vulnerability. Global Environmental Change, 16(3), 268–281.",
        ),
        Block(
            ParagraphRole.REFERENCES_ENTRY,
            "IPCC. (2022). Climate Change 2022: Impacts, Adaptation and Vulnerability.",
        ),
    ]


def assert_all_roles_covered(blocks: list[Block] | None = None) -> None:
    blocks = blocks or sample_blocks()
    present = {b.role for b in blocks}
    missing = [r for r in ParagraphRole if r not in present]
    if missing:
        raise AssertionError(
            "sample_blocks missing roles: " + ", ".join(r.value for r in missing)
        )
