"""Re-humanize only the sections an edit changed, each as a whole section.

The provider writes better on longer input, so changed sections go out complete and
together in one call; sections an edit did not touch keep their humanized prose.
"""

from __future__ import annotations

import re
from typing import Callable

from services.humanizer_engine.constants import MIN_HUMANIZE_CHARS

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"“\[])")
_HEADING_RE = re.compile(r"(?m)^##\s+.+$")


def _key(sentence: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", sentence.lower()))


def _sentences(paragraph: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT_RE.split(paragraph.strip()) if s.strip()]


def _is_prose(paragraph: str) -> bool:
    stripped = paragraph.strip()
    return bool(stripped) and not stripped.startswith(("#", "|", "[[", "<!--"))


def _prose_sentences(text: str) -> list[str]:
    return [s for p in re.split(r"\n\s*\n", text or "") if _is_prose(p) for s in _sentences(p)]


def _split_sections(body: str) -> list[tuple[str, str]]:
    """[(heading line or "", section text)] in document order."""
    parts: list[tuple[str, str]] = []
    matches = list(_HEADING_RE.finditer(body))
    if not matches or matches[0].start() > 0:
        lead = body[: matches[0].start()] if matches else body
        if lead.strip():
            parts.append(("", lead.strip()))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        parts.append((match.group(0).strip(), body[match.end() : end].strip()))
    return parts


def _changed(text: str, known: set[str]) -> bool:
    new = " ".join(s for s in _prose_sentences(text) if _key(s) not in known)
    return len(new) >= MIN_HUMANIZE_CHARS


def humanize_new_sentences(body: str, previous: str, humanize: Callable[[str], str]) -> str:
    known = {_key(s) for s in _prose_sentences(previous)}
    sections = _split_sections((body or "").strip())
    changed = [i for i, (_h, text) in enumerate(sections) if _changed(text, known)]
    if not changed:
        return (body or "").strip()

    outputs = _humanize_sections([sections[i] for i in changed], humanize)
    for i, text in zip(changed, outputs):
        sections[i] = (sections[i][0], text)
    return "\n\n".join(f"{h}\n\n{t}".strip() if h else t for h, t in sections).strip()


def _humanize_sections(sections: list[tuple[str, str]], humanize: Callable[[str], str]) -> list[str]:
    """One provider call for all changed sections; headings mark where each one ends."""
    if len(sections) == 1:
        return [_humanize_prose(sections[0][1], humanize)]
    joined = "\n\n".join(f"{h}\n\n{t}" if h else t for h, t in sections)
    result = humanize(joined) or ""
    split = _split_sections(result.strip())
    wanted = [h for h, _t in sections]
    if [h for h, _t in split] == wanted and all(t.strip() for _h, t in split):
        return [t for _h, t in split]
    return [_humanize_prose(text, humanize) for _h, text in sections]


def _humanize_prose(text: str, humanize: Callable[[str], str]) -> str:
    """A section's tables and markers stay; its prose paragraphs go out as one block."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    prose = [p for p in paragraphs if _is_prose(p)]
    if not prose:
        return text
    result = humanize("\n\n".join(prose)) or ""
    out = [p.strip() for p in re.split(r"\n\s*\n", result) if p.strip()]
    if not out:
        return text
    if len(out) != len(prose):
        # Paragraphing changed: keep non-prose blocks in place, prose as returned.
        kept = [p for p in paragraphs if not _is_prose(p)]
        return "\n\n".join(out + kept) if kept else "\n\n".join(out)
    it = iter(out)
    return "\n\n".join(next(it) if _is_prose(p) else p for p in paragraphs)
