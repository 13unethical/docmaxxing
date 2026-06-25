"""
Per-paragraph heading assignments — source of truth from structure recovery through formatting.

Priority when resolving final level:
  1. AI-assigned level (never re-guessed)
  2. Existing Word heading style on the paragraph
  3. Heuristic detect_heading_level()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from formatter.paragraph_style import heading_style_for_level


@dataclass
class ParagraphHeadingAssignment:
    """Planned heading metadata for one document paragraph index."""

    text: str = ""
    level: int | None = None
    source: str = "none"  # ai | word_style | heuristic | none
    confidence: float | None = None

    @property
    def is_ai_locked(self) -> bool:
        return self.source == "ai" and isinstance(self.level, int) and self.level > 0


@dataclass
class StructureApplyResult:
    """Output of rebuild_document_from_recovery."""

    assignments: list[ParagraphHeadingAssignment]
    recovery_mode: str = ""
    ai_powered: bool = False


@dataclass
class HeadingApplyDiagnostic:
    """Runtime record for one formatted heading paragraph."""

    paragraph: str
    source: str
    level: int
    recovered_level: int | None
    applied_style: str
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "paragraph": self.paragraph,
            "source": self.source,
            "level": self.level,
            "recovered_level": self.recovered_level,
            "applied_style": self.applied_style,
            "confidence": self.confidence,
        }


@dataclass
class StructureRecoveryDebugReport:
    """Structure Recovery Debug verification payload."""

    recovery_mode: str
    ai_powered: bool
    headings: list[HeadingApplyDiagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_mode": self.recovery_mode,
            "ai_powered": self.ai_powered,
            "headings": [h.to_dict() for h in self.headings],
        }


def resolve_paragraph_heading_level(
    *,
    assignment: ParagraphHeadingAssignment | None,
    word_style_level: int | None,
    heuristic_level: int,
    auto_headings: bool,
) -> tuple[int, str, int | None]:
    """
    Return (final_level, source_used, recovered_level).

    recovered_level is the AI-planned level when source is ai, else None.
    """
    if assignment and assignment.is_ai_locked:
        return assignment.level, "ai", assignment.level

    if word_style_level is not None and word_style_level > 0:
        return word_style_level, "word_style", None

    if auto_headings and heuristic_level > 0:
        return heuristic_level, "heuristic", None

    return 0, "none", None


def applied_style_name(level: int) -> str:
    if level <= 0:
        return "Normal"
    return heading_style_for_level(level) or "Normal"
