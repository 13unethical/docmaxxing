"""Unit tests for training-only heading protect/restore (no browser / StealthWriter)."""

from __future__ import annotations

import re

import pytest

from services.humanizer_training.heading_protection import (
    HeadingRestoreError,
    protect_training_headings,
    restore_training_headings,
)


def _heading_lines(text: str) -> list[str]:
    return [m.group(0).strip() for m in re.finditer(r"(?m)^##\s+.+$", text or "")]


class TestProtectRestoreTrainingHeadings:
    def test_a_multiple_headings(self):
        source = (
            "## Introduction\n\n"
            "Body one discusses methods.\n\n"
            "## Analysis\n\n"
            "Body two expands the claim.\n\n"
            "## Conclusion\n\n"
            "Body three wraps up."
        )
        protected, headings = protect_training_headings(source)
        assert headings == ["## Introduction", "## Analysis", "## Conclusion"]
        assert "## Introduction" not in protected
        assert "[[[HEADING_0]]]" in protected
        assert "[[[HEADING_1]]]" in protected
        assert "[[[HEADING_2]]]" in protected
        assert "Body one discusses methods." in protected

        rewritten = (
            protected.replace("discusses", "examines")
            .replace("expands", "develops")
            .replace("wraps up", "concludes carefully")
        )
        restored = restore_training_headings(rewritten, headings)
        assert _heading_lines(restored) == headings
        assert "examines methods" in restored
        assert "develops the claim" in restored
        assert "concludes carefully" in restored

    def test_b_consecutive_headings(self):
        source = "## Intro\n\n## Methods\n\nParagraph after consecutive headings."
        protected, headings = protect_training_headings(source)
        assert headings == ["## Intro", "## Methods"]
        assert protected.index("[[[HEADING_0]]]") < protected.index("[[[HEADING_1]]]")
        restored = restore_training_headings(
            protected.replace("Paragraph", "Revised paragraph"),
            headings,
        )
        assert _heading_lines(restored) == ["## Intro", "## Methods"]
        assert "Revised paragraph after consecutive headings." in restored

    def test_c_headings_with_punctuation(self):
        source = (
            "## Results: primary findings — overview\n\n"
            "Evidence follows.\n\n"
            "## Discussion (part 1)\n\n"
            "Interpretation follows."
        )
        protected, headings = protect_training_headings(source)
        assert headings == [
            "## Results: primary findings — overview",
            "## Discussion (part 1)",
        ]
        restored = restore_training_headings(
            protected.replace("Evidence", "Supporting evidence"),
            headings,
        )
        assert _heading_lines(restored) == headings
        assert "Supporting evidence follows." in restored

    def test_d_headings_with_numbers_and_percentages(self):
        source = (
            "## Chapter 2: Growth at 14%\n\n"
            "Numeric body with 2021 values.\n\n"
            "## Section 3.1 — 50% threshold\n\n"
            "More prose."
        )
        protected, headings = protect_training_headings(source)
        assert headings == [
            "## Chapter 2: Growth at 14%",
            "## Section 3.1 — 50% threshold",
        ]
        # Body rewrite must not affect restored heading markers/numbers.
        rewritten = protected.replace("Numeric body", "Adjusted body").replace(
            "2021", "2022"
        )
        restored = restore_training_headings(rewritten, headings)
        assert _heading_lines(restored) == headings
        assert "14%" in restored
        assert "50%" in restored
        assert "Adjusted body with 2022 values." in restored

    def test_e_heading_text_resembling_placeholders(self):
        source = (
            "## [[[HEADING_99]]] marker lookalike\n\n"
            "Body mentions [[[HEADING_0]]] as prose only.\n\n"
            "## Real Section\n\n"
            "Tail."
        )
        protected, headings = protect_training_headings(source)
        assert headings[0] == "## [[[HEADING_99]]] marker lookalike"
        assert headings[1] == "## Real Section"
        # Protected stream uses indices 0/1 for real heading slots.
        assert "[[[HEADING_0]]]" in protected
        assert "[[[HEADING_1]]]" in protected
        # Prose lookalike remains in body (not a heading line).
        assert "Body mentions [[[HEADING_0]]] as prose only." in protected

        restored = restore_training_headings(protected, headings)
        assert _heading_lines(restored)[0] == "## [[[HEADING_99]]] marker lookalike"
        assert _heading_lines(restored)[1] == "## Real Section"
        assert "Body mentions [[[HEADING_0]]] as prose only." in restored

    def test_f_no_headings(self):
        source = "Plain paragraph without markdown headings.\n\nSecond paragraph."
        protected, headings = protect_training_headings(source)
        assert headings == []
        assert "[[[HEADING_" not in protected
        assert "Plain paragraph" in protected
        restored = restore_training_headings(
            protected.replace("Plain", "Rewritten"),
            headings,
        )
        assert _heading_lines(restored) == []
        assert "Rewritten paragraph without markdown headings." in restored

    def test_g_exact_restoration_after_arbitrary_rewritten_body(self):
        source = (
            "## Introduction\n\n"
            "Alpha sentence about markets.\n\n"
            "## Literature Review\n\n"
            "Beta sentence about theory.\n\n"
            "## Conclusion\n\n"
            "Gamma sentence about limits."
        )
        protected, headings = protect_training_headings(source)
        # Simulate aggressive teacher rewrite of body only; keep tokens intact.
        arbitrary = (
            "[[[HEADING_0]]]\n\n"
            "Completely different prose block one with extra clauses and hedges.\n\n"
            "[[[HEADING_1]]]\n\n"
            "Completely different prose block two expanding length substantially.\n\n"
            "[[[HEADING_2]]]\n\n"
            "Completely different prose block three with a longer wrap-up."
        )
        restored = restore_training_headings(arbitrary, headings)
        assert _heading_lines(restored) == [
            "## Introduction",
            "## Literature Review",
            "## Conclusion",
        ]
        assert "Alpha sentence" not in restored
        assert "Completely different prose block one" in restored
        assert "Completely different prose block three" in restored

    def test_h_missing_token_fails_closed(self):
        source = "## Introduction\n\nBody.\n\n## Conclusion\n\nEnd."
        protected, headings = protect_training_headings(source)
        broken = protected.replace("[[[HEADING_1]]]", "MISSING")
        with pytest.raises(HeadingRestoreError, match="HEADING_RESTORE_FAILED"):
            restore_training_headings(broken, headings)

    def test_h_mangled_token_loose_match_still_restores(self):
        source = "## Introduction\n\nBody text.\n\n## Conclusion\n\nEnd text."
        _, headings = protect_training_headings(source)
        mangled = (
            "[[HEADING_0]]\n\n"
            "Rewritten body text.\n\n"
            "[HEADING_1]\n\n"
            "Rewritten end text."
        )
        restored = restore_training_headings(mangled, headings)
        assert _heading_lines(restored) == ["## Introduction", "## Conclusion"]
        assert "Rewritten body text." in restored

    def test_h_swapped_or_dropped_all_tokens_fails_closed(self):
        source = "## Introduction\n\nBody.\n\n## Conclusion\n\nEnd."
        _, headings = protect_training_headings(source)
        with pytest.raises(HeadingRestoreError, match="HEADING_RESTORE_FAILED"):
            restore_training_headings(
                "Fully rewritten text with no placeholders at all.",
                headings,
            )