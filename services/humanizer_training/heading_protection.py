"""Training-only markdown heading protect/restore (isolated from production browser).

Reuses the production ``[[[HEADING_N]]]`` placeholder convention from
``services.humanizer_engine.heading_utils``, but restore is **fail-closed**:
if any protected token cannot be restored reliably, raise rather than emit a
corrupted training pair.
"""

from __future__ import annotations

import re

_HEADING_LINE_RE = re.compile(r"^##\s+.+$", re.MULTILINE)
_TOKEN_EXACT = "[[[HEADING_{index}]]]"
# Loose match for provider-mangled bracket variants (same idea as production).
_LOOSE_TOKEN_TEMPLATE = r"\[+\s*\[*\s*HEADING[_\s-]*{index}\s*\]*\s*\]+"

# Production uses section-title inline recovery after restore; training restore
# intentionally skips those rewrites so original heading titles stay exact.


class HeadingRestoreError(ValueError):
    """Raised when a protected heading token cannot be restored fail-closed."""

    def __init__(self, message: str, *, index: int | None = None) -> None:
        self.index = index
        super().__init__(message)


def protect_training_headings(text: str) -> tuple[str, list[str]]:
    """Replace ``##`` heading lines with immutable ``[[[HEADING_N]]]`` placeholders.

    Same placeholder format as production ``protect_markdown_headings``.
    Returns ``(protected_text, original_heading_lines)`` in document order.
    """
    headings: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        headings.append(match.group(0).strip())
        return f"\n\n{_TOKEN_EXACT.format(index=len(headings) - 1)}\n\n"

    protected = _HEADING_LINE_RE.sub(_replace, text or "")
    protected = re.sub(r"\n{3,}", "\n\n", protected).strip()
    return protected, headings


def restore_training_headings(text: str, headings: list[str]) -> str:
    """Restore original ``##`` headings in order. Fail closed on missing tokens.

    Preserves all non-heading teacher text. Does not invent or rewrite heading
    titles — only substitutes stored originals for their placeholder tokens.
    """
    if not headings:
        return _normalize_markdown_headings(text or "")

    restored = text or ""
    for index, heading in enumerate(headings):
        token = _TOKEN_EXACT.format(index=index)
        block = f"\n\n{heading}\n\n"
        if token in restored:
            restored = restored.replace(token, block, 1)
            continue
        loose = re.compile(_LOOSE_TOKEN_TEMPLATE.format(index=index), re.I)
        restored, n = loose.subn(block, restored, count=1)
        if n != 1:
            raise HeadingRestoreError(
                f"HEADING_RESTORE_FAILED: missing or unrestorable token for index={index}",
                index=index,
            )

    for heading in headings:
        if heading not in restored:
            raise HeadingRestoreError(
                f"HEADING_RESTORE_FAILED: restored text missing original heading {heading!r}",
            )

    # Light whitespace only — do not run production inline-heading normalize,
    # which can silently rewrite titles like "## Discussion (part 1)".
    restored = re.sub(r"(?m)^(##\s+.+)\n(?!\n)", r"\1\n\n", restored)
    restored = re.sub(r"\n{3,}", "\n\n", restored)
    return restored.strip()


def _normalize_markdown_headings(text: str) -> str:
    """Whitespace-only normalize for the no-heading path.

    Intentionally omits production inline/mid-heading rewrites so training
    never silently mutates heading titles.
    """
    if not (text or "").strip():
        return text or ""
    normalized = re.sub(r"(?m)^(##\s+.+)\n(?!\n)", r"\1\n\n", text)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()
