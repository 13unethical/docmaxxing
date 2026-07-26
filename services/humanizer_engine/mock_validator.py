"""Paragraph validation after humanization."""

from __future__ import annotations

import re
from typing import Protocol

from services.humanizer_engine.models import ParagraphValidation


class ParagraphValidator(Protocol):
    def validate(
        self,
        *,
        original_text: str,
        humanized_text: str,
        section: str,
        attempt: int,
    ) -> ParagraphValidation:
        ...


class ZeroGPTParagraphValidator:
    """Accept humanized output from external API without lexical overlap checks."""

    def validate(
        self,
        *,
        original_text: str,
        humanized_text: str,
        section: str,
        attempt: int,
    ) -> ParagraphValidation:
        _ = (section, attempt)
        from services.humanizer_engine.heading_utils import is_heading_only

        if is_heading_only(original_text):
            return ParagraphValidation(passed=True)
        if not humanized_text.strip():
            return ParagraphValidation(
                passed=False,
                issues=["Humanizer returned empty text"],
                preserved_meaning=False,
            )
        return ParagraphValidation(passed=True)


class MockParagraphValidator:
    def validate(
        self,
        *,
        original_text: str,
        humanized_text: str,
        section: str,
        attempt: int,
    ) -> ParagraphValidation:
        from services.humanizer_engine.heading_utils import is_heading_only

        if is_heading_only(original_text):
            return ParagraphValidation(passed=True)

        issues: list[str] = []
        preserved_meaning = _meaning_preserved(original_text, humanized_text)
        preserved_tone = bool(humanized_text.strip())
        preserved_formatting = _formatting_preserved(original_text, humanized_text)
        preserved_citations = _citations_preserved(original_text, humanized_text)
        preserved_flow = len(humanized_text.split()) >= max(3, int(len(original_text.split()) * 0.65))

        if not preserved_meaning:
            issues.append("Meaning drift detected between original and humanized paragraph")
        if not preserved_citations:
            issues.append("Citation markers were altered or removed")
        if not preserved_formatting:
            issues.append("Formatting markers were not preserved")
        if not preserved_flow:
            issues.append("Logical flow collapsed — paragraph is too short")

        if attempt == 1 and len(original_text) > 140 and re.search(r"\bobjective\b", original_text, re.IGNORECASE):
            issues.append("Academic tone needs refinement on first pass")
            preserved_tone = False

        passed = not issues and all(
            [preserved_meaning, preserved_tone, preserved_formatting, preserved_citations, preserved_flow]
        )
        return ParagraphValidation(
            passed=passed,
            issues=issues,
            preserved_meaning=preserved_meaning,
            preserved_tone=preserved_tone,
            preserved_formatting=preserved_formatting,
            preserved_citations=preserved_citations,
            preserved_flow=preserved_flow,
        )


def _meaning_preserved(original: str, humanized: str) -> bool:
    original_tokens = {token.lower() for token in re.findall(r"[A-Za-z]{5,}", original)}
    humanized_tokens = {token.lower() for token in re.findall(r"[A-Za-z]{5,}", humanized)}
    if not original_tokens:
        return bool(humanized.strip())
    overlap = len(original_tokens & humanized_tokens) / len(original_tokens)
    return overlap >= 0.45


def _citations_preserved(original: str, humanized: str) -> bool:
    citation_pattern = r"\([^)]{2,}\d{4}[^)]*\)"
    return len(re.findall(citation_pattern, original)) <= len(re.findall(citation_pattern, humanized)) + 1


def _formatting_preserved(original: str, humanized: str) -> bool:
    from services.humanizer_engine.heading_utils import is_heading_only

    if is_heading_only(original):
        return humanized.strip().startswith("## ")
    # Batched drafts keep markdown headings inside the body — require same count.
    orig_headings = len(re.findall(r"(?m)^##\s+", original))
    hum_headings = len(re.findall(r"(?m)^##\s+", humanized))
    if orig_headings and hum_headings < orig_headings:
        return False
    bullet_original = original.count("\n- ") + original.count("\n* ")
    bullet_humanized = humanized.count("\n- ") + humanized.count("\n* ")
    return bullet_humanized >= bullet_original
