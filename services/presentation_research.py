"""Web research for presentations: Claude searches, we keep its notes and the real source links."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from services.claude_client import generate_with_web_search

MAX_SEARCHES = 5
MAX_SOURCES = 8
MAX_NOTES_CHARS = 12000
MAX_CONTEXT_CHARS = 3000

_SYSTEM_PROMPT = """You research a topic so a slide deck can be built on verified facts.
Search the web, then write compact research notes in English:
- 10-15 lines, one fact per line: key definitions, current figures with their year, notable examples,
  causes and effects, open debates. Prefer recent data.
- Prefer authoritative sources: universities, peer-reviewed journals, government and international
  organisations, established media. Avoid essay mills, content farms, and forums.
- Only state numbers that appear in the sources you found.
Return the notes only: no introduction, no closing remarks, no Markdown headings."""


def source_label(source: dict[str, str]) -> str:
    """"Title — domain" for the sources slide."""
    domain = urlparse(source.get("url") or "").netloc.lower().removeprefix("www.")
    title = " ".join(str(source.get("title") or "").split())
    if title and domain:
        return f"{title} — {domain}"
    return title or domain


def research_topic(topic: str, context: str = "") -> tuple[str | None, list[dict[str, str]], dict[str, Any]]:
    """Return (notes, sources, diagnostics). ``notes`` is None when research failed."""
    prompt = f"Research this presentation topic: {topic}"
    if context:
        prompt += (
            "\n\nThe presenter attached this material; research what it needs and fill its gaps:\n"
            f"<material>\n{context[:MAX_CONTEXT_CHARS]}\n</material>"
        )
    notes, sources, diag = generate_with_web_search(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_searches=MAX_SEARCHES,
        max_tokens=3000,
    )
    if not notes:
        return None, [], diag
    return notes[:MAX_NOTES_CHARS], sources[:MAX_SOURCES], diag
