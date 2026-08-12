"""Apply FormattedText (citation fragments) onto a python-docx paragraph."""

from __future__ import annotations

from docx.text.paragraph import Paragraph

from formatter_v2.citations.models import TextFragment
from formatter_v2.citations.renderer import FormattedText


def apply_formatted_text(paragraph: Paragraph, fragments: FormattedText) -> None:
    """Append one run per fragment. Paragraph style owns base typography;
    runs only override italic / bold / small caps.
    """
    # Clear any empty run left by add_paragraph().
    for run in list(paragraph.runs):
        run._element.getparent().remove(run._element)

    for fragment in fragments:
        if not fragment.text:
            continue
        run = paragraph.add_run(fragment.text)
        if fragment.italic:
            run.italic = True
        if fragment.bold:
            run.bold = True
        if fragment.small_caps:
            run.font.small_caps = True


def is_formatted_text(value: object) -> bool:
    return isinstance(value, list) and (
        not value or all(isinstance(part, TextFragment) for part in value)
    )
