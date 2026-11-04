"""Human-written targets for the humanizer: pre-AI conclusions paired with an AI rewrite of them.

Conclusion sections come from CC BY / CC0 open-access articles published before ChatGPT (Europe PMC,
2012–2021); every record keeps its PMCID, journal, year and license for attribution. A chatbot
(GPT, Gemini or Claude) rewrites each conclusion the way it would write it for a student, and the
humanizer learns the way back: AI rewrite -> the original human text.
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Iterator

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
DEFAULT_OUT = Path("data/humanizer_training/human_pairs/conclusions.jsonl")
LICENSES = ("cc by", "cc0")
TOPICS = (
    "education", "students", "teachers", "learning", "social", "society", "economic", "policy",
    "psychology", "behavior", "environmental", "sustainability", "climate", "management", "business",
    "community", "media", "technology", "public health", "nursing", "culture", "gender", "urban",
)
DEFAULT_WRITER_MIX = "openai:gpt-4o-mini:2,openai:gpt-4o:1,gemini:gemini-3.5-flash:2,claude:claude-sonnet-4-6:1"
MIN_WORDS, MAX_WORDS, MAX_PARAGRAPHS = 80, 450, 4
RATIO_RANGE = (0.7, 1.5)
TEST_SHARE = 10  # percent

_CONCLUSION_TITLE = re.compile(
    r"^\s*(?:[\dIVX]+\.?\s*)*(?:conclusions?|concluding remarks|summary and conclusions?|conclusions? and "
    r"(?:implications|recommendations|future (?:work|directions)))\s*$",
    re.IGNORECASE,
)
_DROP_TAGS = {"xref", "fig", "table-wrap", "inline-formula", "disp-formula", "supplementary-material", "fn"}
_LEFTOVER_CITATION = re.compile(r"\s*[\[(]\s*(?:[,;–\-]\s*)*[\])]")
_YEARLESS_CITATION = re.compile(r"\s*\([^()]*,\s*[;)](?:[^()]*\))?")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:])")
_CITATION_TRACE = re.compile(r"\bet al\b|\(\s*[,;]|[,;]\s*\)")
_NON_PROSE = re.compile(r"\b(Figure|Fig\.|Table|Supplementary|funding|author contributions)\b", re.IGNORECASE)


def split_of(key: str) -> str:
    return "test" if int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 100 < TEST_SHARE else "train"


def search_query(topics: tuple[str, ...] = TOPICS, years: tuple[int, int] = (2012, 2021)) -> str:
    titles = " OR ".join(f'TITLE:"{t}"' for t in topics)
    return (
        '(LICENSE:"cc by" OR LICENSE:"cc0") AND OPEN_ACCESS:y AND HAS_FT:y AND IN_EPMC:y '
        f"AND PUB_YEAR:[{years[0]} TO {years[1]}] AND ({titles})"
    )


def search(limit: int, *, get: Callable[..., Any], query: str | None = None) -> Iterator[dict[str, Any]]:
    """Article records with an exactly CC BY / CC0 license (``cc by-nc`` etc. are skipped)."""
    cursor, seen = "*", 0
    while seen < limit:
        page = get(SEARCH_URL, params={"query": query or search_query(), "format": "json", "resultType": "core",
                                       "pageSize": 1000, "cursorMark": cursor}).json()
        results = page.get("resultList", {}).get("result", [])
        for r in results:
            if (r.get("license") or "").lower() in LICENSES and r.get("pmcid"):
                seen += 1
                yield {
                    "pmcid": r["pmcid"],
                    "license": r["license"].lower(),
                    "journal": ((r.get("journalInfo") or {}).get("journal") or {}).get("title", ""),
                    "year": r.get("pubYear"),
                    "title": r.get("title", ""),
                }
                if seen >= limit:
                    return
        nxt = page.get("nextCursorMark")
        if not results or not nxt or nxt == cursor:
            return
        cursor = nxt


def _visible_text(el: ET.Element) -> str:
    parts = [el.text or ""]
    for child in el:
        if child.tag not in _DROP_TAGS:
            parts.append(_visible_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _paragraph_text(p: ET.Element) -> str:
    text = " ".join(_visible_text(p).split())
    text = _YEARLESS_CITATION.sub("", text)
    for _ in range(2):
        text = _LEFTOVER_CITATION.sub("", text)
    return _SPACE_BEFORE_PUNCT.sub(r"\1", text).strip()


def conclusion_paragraphs(xml: str) -> list[str]:
    """Paragraphs of the article's conclusion section (body only, not the abstract)."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    body = root.find(".//body")
    if body is None:
        return []
    for sec in body.iter("sec"):
        title = sec.find("title")
        if title is not None and _CONCLUSION_TITLE.match("".join(title.itertext())):
            return [t for t in (_paragraph_text(p) for p in sec.iter("p")) if t]
    return []


def usable_conclusion(paragraphs: list[str]) -> str | None:
    text = "\n\n".join(paragraphs)
    words = len(text.split())
    if not paragraphs or len(paragraphs) > MAX_PARAGRAPHS or not MIN_WORDS <= words <= MAX_WORDS:
        return None
    if _NON_PROSE.search(text) or _CITATION_TRACE.search(text) or sum(c.isascii() for c in text) < 0.97 * len(text):
        return None
    if any(not p[:1].isupper() or not p.rstrip().endswith((".", "!", "?")) for p in paragraphs):
        return None
    return text


def ai_prompt(text: str) -> str:
    n = len([p for p in text.split("\n\n") if p.strip()])
    return (
        "Rewrite this conclusion for a college essay in your own words. Keep every point and fact, about the "
        f"same length ({len(text.split())} words) and exactly {n} paragraph{'s' if n > 1 else ''}. "
        "Plain text only: no title, no lists, no comments.\n\n" + text
    )


def ai_problem(human: str, ai: str) -> str | None:
    if not ai.strip():
        return "EMPTY"
    if re.search(r"(?m)^\s*(#|\*\*|[-*•]\s)", ai):
        return "MARKDOWN"
    if len([p for p in ai.split("\n\n") if p.strip()]) != len([p for p in human.split("\n\n") if p.strip()]):
        return "PARAGRAPHS"
    ratio = len(ai.split()) / max(1, len(human.split()))
    if not RATIO_RANGE[0] <= ratio <= RATIO_RANGE[1]:
        return "LENGTH"
    return None


def sft_example(pair: dict[str, Any], level: int = 10) -> dict[str, Any]:
    from services.humanizer_training.section_sft import system_prompt

    return {"messages": [
        {"role": "system", "content": system_prompt(level)},
        {"role": "user", "content": pair["ai"]},
        {"role": "assistant", "content": pair["human"]},
    ]}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
