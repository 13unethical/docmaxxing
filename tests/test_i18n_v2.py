"""User-facing Formatter V2 copy must be English."""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path
from unittest.mock import MagicMock

from formatter_v2.chat.edit import chat_edit, load_system_instruction
from formatter_v2.chat.summary import summarize_override_changes
from formatter_v2.profiles import load_profile
from formatter_v2.render.document import Block
from formatter_v2.render.model import DocumentModel
from formatter_v2.resolve import resolve_format_spec
from formatter_v2.spec import (
    Alignment,
    CoverPage,
    Margins,
    ParagraphRole,
    StyleName,
    UserOverrides,
)
from formatter_v2.structure.document_kind import DocumentKind, kind_notices
from formatter_v2.structure.from_word_styles import (
    apply_style_plausibility_overrides,
    implausible_heading_notices,
)
from formatter_v2.structure.numbered import numbered_section_notices
from formatter_v2.structure.text_integrity import integrity_notices

ROOT = Path(__file__).resolve().parents[1]
CYRILLIC_WORD = re.compile(r"[А-Яа-яЁё]{2,}")
_FSTRING_TYPES = {
    getattr(tokenize, name)
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END")
    if hasattr(tokenize, name)
}


def _strip_html_comments(text: str) -> str:
    text = re.sub(r"\{#.*?#\}", "", text, flags=re.S)
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*?$", "", text, flags=re.M)


def _python_non_comment_source(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    out: list[str] = []
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING:
            raw = tok.string.lstrip("rRuUbB")
            if raw.startswith(('"""', "'''")):
                continue
            out.append(tok.string)
            continue
        if tok.type in _FSTRING_TYPES:
            out.append(tok.string)
    return "\n".join(out)


def _assert_no_cyrillic_words(label: str, text: str) -> None:
    match = CYRILLIC_WORD.search(text)
    assert match is None, f"{label}: found Cyrillic {match.group(0)!r}"


def test_no_cyrillic_in_user_facing_strings() -> None:
    html = _strip_html_comments(
        (ROOT / "templates" / "format_v2.html").read_text(encoding="utf-8")
    )
    _assert_no_cyrillic_words("templates/format_v2.html", html)

    js = _strip_js_comments((ROOT / "static" / "format_v2.js").read_text(encoding="utf-8"))
    _assert_no_cyrillic_words("static/format_v2.js", js)

    for path in sorted((ROOT / "formatter_v2").rglob("*.py")):
        scanned = _python_non_comment_source(path)
        _assert_no_cyrillic_words(str(path.relative_to(ROOT)), scanned)


def test_notices_are_in_english() -> None:
    apa = resolve_format_spec(
        load_profile(StyleName.APA7),
        UserOverrides(alignment=Alignment.JUSTIFY, heading_size_pt=16.0),
    )
    mla = resolve_format_spec(
        load_profile(StyleName.MLA9),
        UserOverrides(cover_page=CoverPage(enabled=True, title="My Essay")),
    )
    ieee = resolve_format_spec(
        load_profile(StyleName.IEEE),
        UserOverrides(margins=Margins(top_in=1.0, bottom_in=1.0, left_in=1.0, right_in=1.0)),
    )
    chicago = resolve_format_spec(
        load_profile(StyleName.CHICAGO17),
        UserOverrides(line_spacing=1.5),
    )

    long_heading = Block(ParagraphRole.HEADING_1, ("A" * 210) + ".")
    _, remap_notices = apply_style_plausibility_overrides(
        DocumentModel(body=[long_heading, Block(ParagraphRole.BODY, "Body text.")])
    )
    heading_notices = implausible_heading_notices(
        DocumentModel(
            body=[Block(ParagraphRole.HEADING_1, f"Section {i}") for i in range(15)]
            + [Block(ParagraphRole.BODY, f"Body {i}.") for i in range(10)]
        )
    )
    numbered = numbered_section_notices(
        DocumentModel(
            body=[Block(ParagraphRole.HEADING_1, f"{i}. Section {i}") for i in range(1, 6)]
        )
    )

    notices = [
        *apa.notices,
        *mla.notices,
        *ieee.notices,
        *chicago.notices,
        *integrity_notices(10, 100),
        *kind_notices(DocumentKind.SLIDE_SCRIPT),
        *remap_notices,
        *heading_notices,
        *numbered,
    ]
    assert notices
    joined = " ".join(n.message for n in notices)
    _assert_no_cyrillic_words("notices", joined)
    assert "departure from the style" in joined
    assert "left alignment" in joined
    assert "cover page" in joined
    assert "Reclassified" in joined
    assert "manual section numbering" in joined
    assert "slide script" in joined
    assert "lookalike" in joined


def test_chat_summary_is_in_english() -> None:
    before = UserOverrides(line_spacing=2.0, margins=Margins.preset("normal"))
    after = UserOverrides(
        line_spacing=1.5,
        margins=Margins(top_in=1.25, bottom_in=1.25, left_in=1.25, right_in=1.25),
        first_line_indent=True,
    )
    summary = summarize_override_changes(before, after)
    _assert_no_cyrillic_words("chat summary", summary)
    assert "line spacing 2.0 → 1.5" in summary
    assert 'margins 1" → 1.25"' in summary
    assert "first-line indent" in summary
    assert "on" in summary

    client = MagicMock()
    client.generate.side_effect = TimeoutError("deadline")
    result = chat_edit("make spacing 1.5", UserOverrides(), "apa7", client)
    rejected = " ".join(result["rejected"])
    _assert_no_cyrillic_words("chat timeout", rejected)
    assert "timed out" in rejected.lower()

    instruction = load_system_instruction()
    assert "in English" in instruction
    assert "user's language" not in instruction
