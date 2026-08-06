"""Ordered pipeline stage definitions and provider integration slots."""

from __future__ import annotations

from dataclasses import dataclass

from services.assignment_pipeline.models import PipelineStage, StageProvider


@dataclass(frozen=True)
class StageSpec:
    stage: PipelineStage
    label: str
    description: str
    provider: StageProvider
    order: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "stage": self.stage.value,
            "label": self.label,
            "description": self.description,
            "provider": self.provider.value,
            "order": self.order,
        }


PIPELINE_STAGE_SPECS: tuple[StageSpec, ...] = (
    StageSpec(
        PipelineStage.UPLOAD,
        "Upload",
        "Collect assignment brief, rubric, and supporting materials.",
        StageProvider.INTERNAL,
        1,
    ),
    StageSpec(
        PipelineStage.REQUIREMENT_ANALYSIS,
        "Requirement Analysis",
        "Extract structured requirements from uploaded documents.",
        StageProvider.GEMINI,
        2,
    ),
    StageSpec(
        PipelineStage.PRICING,
        "Pricing",
        "Calculate quote from extracted requirements and priority.",
        StageProvider.INTERNAL,
        3,
    ),
    StageSpec(
        PipelineStage.WAITING_FOR_PAYMENT,
        "Waiting for Payment",
        "Hold pipeline until payment is confirmed.",
        StageProvider.INTERNAL,
        4,
    ),
    StageSpec(
        PipelineStage.RESEARCH,
        "Research",
        "Gather sources and evidence aligned to requirements.",
        StageProvider.GEMINI,
        5,
    ),
    StageSpec(
        PipelineStage.BLUEPRINT,
        "Blueprint",
        "Plan document structure, section flow, and argument map.",
        StageProvider.CLAUDE,
        6,
    ),
    StageSpec(
        PipelineStage.WRITING,
        "Writing",
        "Draft sections according to blueprint and requirements.",
        StageProvider.CLAUDE,
        7,
    ),
    StageSpec(
        PipelineStage.MERGE,
        "Merge",
        "Combine section drafts into a single document.",
        StageProvider.INTERNAL,
        8,
    ),
    StageSpec(
        PipelineStage.CITATION_GENERATION,
        "Citation Generation",
        "Build reference list and in-text citations via Crossref.",
        StageProvider.CITATION_ENGINE,
        9,
    ),
    StageSpec(
        PipelineStage.HUMANIZATION,
        "Humanization",
        "Refine voice with StealthWriter Legacy 5.1 at rewrite level 10.",
        StageProvider.HUMANIZER,
        10,
    ),
    StageSpec(
        PipelineStage.FORMATTING,
        "Formatting",
        "Apply Format Engine styles, margins, headings, and page numbers.",
        StageProvider.FORMAT_ENGINE,
        11,
    ),
    StageSpec(
        PipelineStage.STYLE_REVIEW,
        "Academic Review",
        "Gemini review of the formatted document against requirements and rubric.",
        StageProvider.GEMINI,
        12,
    ),
    StageSpec(
        PipelineStage.REVISION,
        "Revision",
        "Gemini targeted fixes from the academic review report.",
        StageProvider.GEMINI,
        13,
    ),
    StageSpec(
        PipelineStage.REQUIREMENT_VALIDATION,
        "Requirement Validation",
        "Gemini comparison of the final document against Requirement JSON and rubric.",
        StageProvider.GEMINI,
        14,
    ),
    StageSpec(
        PipelineStage.AI_DETECTION,
        "AI Detection",
        "Skipped — ZeroGPT assignment gate disabled.",
        StageProvider.INTERNAL,
        15,
    ),
    StageSpec(
        PipelineStage.DELIVERY,
        "Delivery",
        "Package final document and release to the student.",
        StageProvider.INTERNAL,
        16,
    ),
)

PIPELINE_STAGES: tuple[PipelineStage, ...] = tuple(spec.stage for spec in PIPELINE_STAGE_SPECS)
_STAGE_ORDER = {spec.stage: spec.order for spec in PIPELINE_STAGE_SPECS}


def stage_index(stage: PipelineStage) -> int:
    return _STAGE_ORDER[stage]


def stage_after(stage: PipelineStage) -> PipelineStage | None:
    idx = PIPELINE_STAGES.index(stage)
    if idx + 1 >= len(PIPELINE_STAGES):
        return None
    return PIPELINE_STAGES[idx + 1]
