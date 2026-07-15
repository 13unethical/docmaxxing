"""Mock section reviewer — replace with real QA later."""

from __future__ import annotations

from typing import Protocol

from services.assignment_pipeline.models import utc_now
from services.writer_engine.models import SectionReview, WriterEngineInput, WriterSection


class SectionReviewer(Protocol):
    def review_section(self, *, section: WriterSection, payload: WriterEngineInput) -> SectionReview:
        ...


class MockSectionReviewer:
    VERSION = "mock-1.0"

    def review_section(self, *, section: WriterSection, payload: WriterEngineInput) -> SectionReview:
        text = section.generated_text.strip()

        if not text:
            return SectionReview(
                passed=False,
                score=0,
                missing_points=["Section text is empty"],
                warnings=["Regenerate this section only"],
                needs_revision=True,
                review_message="Section text is empty.",
                reviewed_at=utc_now(),
            )

        score = 88
        passed = True
        missing_points: list[str] = []
        warnings: list[str] = []

        if section.revision_count == 0 and "analysis" in section.title.lower():
            score = 64
            passed = False
            missing_points.append("Critical analysis needs stronger comparative evaluation")
            warnings.append("Increase theory comparison and evidence weighting")
        elif section.revision_count > 0:
            score = 91
            passed = True
            warnings.append("Section meets blueprint objective after revision")

        if len(text.split()) < max(20, section.estimated_words // 20):
            warnings.append("Expand section toward target word allocation in production writer")

        return SectionReview(
            passed=passed,
            score=score,
            requirement_coverage=score,
            argument_quality=score,
            academic_style=score,
            citation_quality=score,
            critical_thinking=score,
            missing_points=missing_points,
            warnings=warnings,
            needs_revision=not passed,
            review_message="Mock section review",
            reviewed_at=utc_now(),
        )
