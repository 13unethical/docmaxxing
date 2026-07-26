"""Assignment citation generation via Crossref."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from services.assignment_llm import (
    STAGE_CITATION_EXTRACT,
    assignment_generate_json,
    assignment_llm_configured,
)
from services.assignment_pipeline.models import utc_now
from services.citation_service import CitationService, CrossrefProvider
from services.writer_engine.models import count_words

_EXTRACT_SYSTEM = """Extract scholarly citation search queries from an academic draft.
Return ONLY JSON:
{"queries":[{"query":"short Crossref search string","reason":"..."}]}
Rules:
- Prefer author + year, paper titles, or distinctive theory names.
- Max 8 queries.
- Skip generic textbook phrases.
"""

_REF_HEADING_RE = re.compile(r"(?im)^\s*##\s*(references|bibliography|works cited)\s*$")


class CitationLookup(Protocol):
    def search(self, query: str, *, style: str = "APA 7", limit: int = 3) -> dict[str, Any]:
        ...


@dataclass
class CitationPack:
    id: str
    project_id: str | None
    style: str
    queries: list[str] = field(default_factory=list)
    works: list[dict[str, Any]] = field(default_factory=list)
    in_text: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    engine_version: str = "crossref-1.0"
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "style": self.style,
            "queries": list(self.queries),
            "works": list(self.works),
            "in_text": list(self.in_text),
            "references": list(self.references),
            "unresolved": list(self.unresolved),
            "engine_version": self.engine_version,
            "created_at": self.created_at,
        }


class AssignmentCitationEngine:
    VERSION = "crossref-1.0"

    def __init__(self, citation_service: CitationLookup | None = None) -> None:
        self.citations = citation_service or CitationService(CrossrefProvider())

    def generate(
        self,
        *,
        draft: dict[str, Any],
        requirement_json: dict[str, Any],
        project_id: str | None = None,
        max_queries: int = 8,
    ) -> tuple[CitationPack, dict[str, Any]]:
        style = str(
            requirement_json.get("citation_style")
            or requirement_json.get("citationStyle")
            or "APA 7"
        )
        content = str(draft.get("content") or "")
        queries = _extract_queries(content, requirement_json=requirement_json, max_queries=max_queries)

        works: list[dict[str, Any]] = []
        in_text: list[str] = []
        references: list[str] = []
        unresolved: list[str] = []
        seen_refs: set[str] = set()

        for query in queries:
            try:
                result = self.citations.search(query, style=style, limit=2)
            except Exception:  # noqa: BLE001
                unresolved.append(query)
                continue
            found = list(result.get("results") or result.get("works") or [])
            if not found:
                unresolved.append(query)
                continue
            top = found[0]
            ref = str(top.get("reference") or "").strip()
            label = str(top.get("label") or top.get("intext") or top.get("in_text") or "").strip()
            if ref and ref not in seen_refs:
                seen_refs.add(ref)
                references.append(ref)
                works.append(top)
            if label and label not in in_text:
                in_text.append(label)

        pack = CitationPack(
            id=str(uuid.uuid4()),
            project_id=project_id,
            style=style,
            queries=queries,
            works=works,
            in_text=in_text,
            references=references,
            unresolved=unresolved,
            engine_version=self.VERSION,
            created_at=utc_now().isoformat(),
        )
        updated_draft = dict(draft)
        updated_draft["content"] = _apply_references_section(content, references, style=style)
        updated_draft["total_words"] = count_words(str(updated_draft["content"]))
        updated_draft["version"] = int(draft.get("version") or 1) + 1
        updated_draft["id"] = str(uuid.uuid4())
        updated_draft["created_at"] = utc_now().isoformat()
        return pack, updated_draft


def _extract_queries(
    content: str,
    *,
    requirement_json: dict[str, Any],
    max_queries: int,
) -> list[str]:
    queries: list[str] = []
    if assignment_llm_configured(STAGE_CITATION_EXTRACT):
        data, _ = assignment_generate_json(
            system_prompt=_EXTRACT_SYSTEM,
            user_prompt=json_dumps_truncated(
                {
                    "title": requirement_json.get("title"),
                    "topic": requirement_json.get("topic") or requirement_json.get("assignment_type"),
                    "draft_excerpt": content[:12000],
                }
            ),
            temperature=0.1,
            max_retries=1,
            stage=STAGE_CITATION_EXTRACT,
        )
        if isinstance(data, dict):
            for item in data.get("queries") or []:
                if isinstance(item, dict):
                    q = str(item.get("query") or "").strip()
                else:
                    q = str(item or "").strip()
                if q and q not in queries:
                    queries.append(q)
                if len(queries) >= max_queries:
                    break

    if not queries:
        queries = _heuristic_queries(content, requirement_json, max_queries=max_queries)
    return queries[:max_queries]


def _heuristic_queries(content: str, requirement_json: dict[str, Any], *, max_queries: int) -> list[str]:
    found: list[str] = []
    for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)?)\s*\((\d{4})\)", content):
        q = f"{match.group(1)} {match.group(2)}"
        if q not in found:
            found.append(q)
    title = str(requirement_json.get("title") or "").strip()
    if title and title not in found:
        found.append(title)
    topic = str(requirement_json.get("topic") or requirement_json.get("assignment_type") or "").strip()
    if topic and topic not in found:
        found.append(topic)
    return found[:max_queries]


def _apply_references_section(content: str, references: list[str], *, style: str) -> str:
    heading = _references_heading(style)
    body = content or ""
    match = _REF_HEADING_RE.search(body)
    if match:
        body = body[: match.start()].rstrip()
    if not references:
        return body
    ref_block = "\n\n## " + heading + "\n\n" + "\n\n".join(references)
    return body.rstrip() + ref_block + "\n"


def _references_heading(style: str) -> str:
    key = (style or "").upper()
    if "MLA" in key:
        return "Works Cited"
    if "HARVARD" in key:
        return "References"
    return "References"


def json_dumps_truncated(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)
