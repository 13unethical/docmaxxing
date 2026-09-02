"""Assignment citation generation via Crossref — with reference settings + cite reconcile."""

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
from services.assignment_spec.validate import count_body_words
from services.citation_service import CitationService, CrossrefProvider
from services.writer_engine.models import count_words

_EXTRACT_SYSTEM = """Extract scholarly citation search queries from an academic draft.
Return ONLY JSON:
{"queries":[{"query":"short Crossref search string","reason":"..."}]}
Rules:
- Prefer author + year exactly as cited in the draft.
- Prefer paper titles or distinctive theory names when author-year is missing.
- Skip generic textbook phrases.
"""

_RECONCILE_SYSTEM = """You reconcile an academic draft with a fixed reference list.
Return ONLY JSON:
{
  "content": "full markdown draft WITH ## section headings, WITHOUT inventing new References",
  "notes": ["what you changed"]
}

Rules:
- Keep every ## section that is not References/Bibliography/Works Cited.
- Every in-text citation must match one of the provided works (author + year).
- Replace invented or mismatched (Author, Year) with the closest provided work's in-text form.
- Do NOT invent new sources. Do NOT add a References section (caller appends it).
- Preserve meaning, structure, and complete sentences. Academic tone only.
"""

_REF_HEADING_RE = re.compile(r"(?im)^\s*##\s*(references|bibliography|works cited)\s*$")
_CLAIMED_CITE_RE = re.compile(
    r"\b([A-Z][A-Za-z''\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z''\-]+)?(?:\s+et\s+al\.?)?)\s*\((\d{4}[a-z]?)\)"
)


_INSERT_CITES_SYSTEM = """You insert a FEW additional in-text citations into an academic draft
using ONLY the provided allowed works. Return ONLY JSON:
{
  "content": "full markdown WITH ## headings, WITHOUT a References section",
  "notes": ["where you cited"]
}

Rules:
- Use ONLY the exact in_text forms from allowed_in_text / works.
- Insert cites where claims need scholarly support — do not invent sources.
- Do NOT add unused bibliography entries (caller builds References from used cites).
- Keep meaning, structure, and complete sentences. Do not rewrite the whole essay.
- Prefer adding up to target_additional new citation occurrences if natural; fewer is OK.
"""


class CitationLookup(Protocol):
    def search(self, query: str, *, style: str = "APA 7", limit: int = 3) -> dict[str, Any]:
        ...


@dataclass
class ReferenceSettings:
    """How the bibliography must be built and formatted."""

    style: str = "APA 7"
    minimum_sources: int = 0
    maximum_sources: int = 25
    heading: str = "References"
    on_new_page: bool = True
    hanging_indent_inches: float = 0.5
    sort_alphabetically: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "minimum_sources": self.minimum_sources,
            "maximum_sources": self.maximum_sources,
            "heading": self.heading,
            "on_new_page": self.on_new_page,
            "hanging_indent_inches": self.hanging_indent_inches,
            "sort_alphabetically": self.sort_alphabetically,
        }

    @classmethod
    def from_requirement(cls, requirement_json: dict[str, Any]) -> ReferenceSettings:
        style = str(
            requirement_json.get("citation_style")
            or requirement_json.get("citationStyle")
            or "APA 7"
        )
        fmt = requirement_json.get("formatting") if isinstance(requirement_json.get("formatting"), dict) else {}
        refs_cfg = requirement_json.get("references") if isinstance(requirement_json.get("references"), dict) else {}
        if not refs_cfg and isinstance(fmt.get("references"), dict):
            refs_cfg = fmt["references"]

        min_sources = requirement_json.get("minimum_sources")
        if min_sources is None:
            min_sources = refs_cfg.get("minimum_sources")
        try:
            min_sources_i = max(0, int(min_sources or 0))
        except (TypeError, ValueError):
            min_sources_i = 0

        max_sources = refs_cfg.get("maximum_sources", requirement_json.get("maximum_sources", 25))
        try:
            max_sources_i = max(min_sources_i or 1, int(max_sources or 25))
        except (TypeError, ValueError):
            max_sources_i = 25

        hanging = refs_cfg.get("hanging_indent_inches", fmt.get("hanging_indent_inches"))
        if hanging is None:
            hanging = 0.5 if "harvard" not in style.lower() else 0.5
        try:
            hanging_f = float(hanging)
        except (TypeError, ValueError):
            hanging_f = 0.5

        on_new_page = refs_cfg.get("on_new_page")
        if on_new_page is None:
            on_new_page = fmt.get("references_on_new_page", True)

        heading = str(refs_cfg.get("heading") or _references_heading(style))
        sort_alpha = bool(refs_cfg.get("sort_alphabetically", True))

        return cls(
            style=style,
            minimum_sources=min_sources_i,
            maximum_sources=max_sources_i,
            heading=heading,
            on_new_page=bool(on_new_page),
            hanging_indent_inches=hanging_f,
            sort_alphabetically=sort_alpha,
        )


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
    settings: dict[str, Any] = field(default_factory=dict)
    engine_version: str = "crossref-2.0"
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
            "settings": dict(self.settings),
            "engine_version": self.engine_version,
            "created_at": self.created_at,
        }


class AssignmentCitationEngine:
    VERSION = "crossref-2.0"

    def __init__(self, citation_service: CitationLookup | None = None) -> None:
        self.citations = citation_service or CitationService(CrossrefProvider())

    def generate(
        self,
        *,
        draft: dict[str, Any],
        requirement_json: dict[str, Any],
        project_id: str | None = None,
        max_queries: int | None = None,
    ) -> tuple[CitationPack, dict[str, Any]]:
        settings = ReferenceSettings.from_requirement(requirement_json)
        content = str(draft.get("content") or "")
        query_cap = max_queries or max(settings.maximum_sources, settings.minimum_sources, 8)

        # 1) Prefer cites already claimed in the draft — so refs match the prose.
        claimed = _extract_claimed_cites(content)
        queries = list(claimed)
        for q in _extract_queries(content, requirement_json=requirement_json, max_queries=query_cap):
            if q not in queries:
                queries.append(q)
            if len(queries) >= query_cap:
                break

        works: list[dict[str, Any]] = []
        in_text: list[str] = []
        references: list[str] = []
        unresolved: list[str] = []
        seen_refs: set[str] = set()

        for query in queries:
            if len(references) >= settings.maximum_sources:
                break
            work = self._lookup(query, style=settings.style)
            if not work:
                unresolved.append(query)
                continue
            ref = str(work.get("reference") or "").strip()
            label = str(work.get("label") or work.get("intext") or work.get("in_text") or "").strip()
            if ref and ref not in seen_refs:
                seen_refs.add(ref)
                references.append(ref)
                works.append(work)
            if label and label not in in_text:
                in_text.append(label)

        # Grow toward minimum by inserting real in-text cites (never pad unused refs).
        body = _strip_references_section(content)
        if settings.minimum_sources and len(works) < settings.minimum_sources:
            body, works, references, in_text, queries = self._expand_used_citations(
                body,
                works=works,
                references=references,
                in_text=in_text,
                queries=queries,
                settings=settings,
                requirement_json=requirement_json,
                seen_refs=seen_refs,
            )

        # Reconcile claimed author-years to verified works, then keep cited-only refs.
        body = _reconcile_body_with_works(body, works=works, in_text=in_text, style=settings.style)
        works, references, in_text = _filter_cited_only(body, works=works, references=references)

        if settings.sort_alphabetically and references:
            n = min(len(references), len(works))
            paired = sorted(
                [(references[i], works[i]) for i in range(n)],
                key=lambda row: row[0].lower(),
            )
            references = [r for r, _ in paired]
            works = [w for _, w in paired]
            in_text = []
            for work in works:
                label = str(work.get("label") or work.get("intext") or work.get("in_text") or "").strip()
                if label and label not in in_text:
                    in_text.append(label)

        pack = CitationPack(
            id=str(uuid.uuid4()),
            project_id=project_id,
            style=settings.style,
            queries=queries,
            works=works,
            in_text=in_text,
            references=references,
            unresolved=unresolved,
            settings={
                **settings.to_dict(),
                "used_sources": len(references),
                "sources_below_minimum": bool(
                    settings.minimum_sources and len(references) < settings.minimum_sources
                ),
            },
            engine_version=self.VERSION,
            created_at=utc_now().isoformat(),
        )
        updated_draft = dict(draft)
        updated_draft["content"] = _apply_references_section(
            body,
            references,
            heading=settings.heading,
            on_new_page=settings.on_new_page,
        )
        updated_draft["total_words"] = count_body_words(str(updated_draft["content"]))
        updated_draft["document_words"] = count_words(str(updated_draft["content"]))
        updated_draft["version"] = int(draft.get("version") or 1) + 1
        updated_draft["id"] = str(uuid.uuid4())
        updated_draft["created_at"] = utc_now().isoformat()
        updated_draft["reference_settings"] = settings.to_dict()
        return pack, updated_draft

    def _expand_used_citations(
        self,
        body: str,
        *,
        works: list[dict[str, Any]],
        references: list[str],
        in_text: list[str],
        queries: list[str],
        settings: ReferenceSettings,
        requirement_json: dict[str, Any],
        seen_refs: set[str],
    ) -> tuple[str, list[dict[str, Any]], list[str], list[str], list[str]]:
        """Lookup more verified works and insert their cites into body when natural."""
        need = max(0, settings.minimum_sources - len(works))
        if need <= 0:
            return body, works, references, in_text, queries

        for query in _fill_queries(requirement_json, body):
            if len(works) >= settings.minimum_sources or len(works) >= settings.maximum_sources:
                break
            if query in queries:
                continue
            work = self._lookup(query, style=settings.style)
            if not work:
                continue
            ref = str(work.get("reference") or "").strip()
            label = str(work.get("label") or work.get("intext") or work.get("in_text") or "").strip()
            if not ref or ref in seen_refs or not label:
                continue
            # Only keep if we can place the cite in the body.
            placed = _try_insert_cite(body, label)
            if not placed:
                continue
            body = placed
            seen_refs.add(ref)
            references.append(ref)
            works.append(work)
            queries.append(query)
            if label not in in_text:
                in_text.append(label)

        # Optional LLM pass: insert more from the already-verified pool only.
        still_need = max(0, settings.minimum_sources - _count_used_cites(body, works))
        if still_need > 0 and works:
            body = _llm_insert_allowed_cites(
                body,
                works=works,
                in_text=in_text,
                style=settings.style,
                target_additional=min(still_need, 8),
            )
        return body, works, references, in_text, queries

    def _lookup(self, query: str, *, style: str) -> dict[str, Any] | None:
        try:
            result = self.citations.search(query, style=style, limit=2)
        except Exception:  # noqa: BLE001
            return None
        found = list(result.get("results") or result.get("works") or [])
        return found[0] if found else None


def _extract_claimed_cites(content: str) -> list[str]:
    found: list[str] = []
    for match in _CLAIMED_CITE_RE.finditer(content or ""):
        q = f"{match.group(1)} {match.group(2)}"
        if q not in found:
            found.append(q)
    return found


def _work_cite_keys(work: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for field in ("label", "intext", "in_text"):
        val = str(work.get(field) or "").strip()
        if val:
            keys.append(val)
    ref = str(work.get("reference") or "")
    year = str(work.get("year") or "").strip()
    # Author surname from "Surname, I. (YEAR)" style refs.
    m = re.match(r"^([A-Z][A-Za-z''\-]+)", ref)
    if m and year:
        keys.append(f"{m.group(1)} ({year})")
        keys.append(f"{m.group(1)}, {year}")
    return keys


def _body_mentions_work(body: str, work: dict[str, Any]) -> bool:
    text = body or ""
    for key in _work_cite_keys(work):
        if key and key in text:
            return True
        # Author (Year) loose match
        m = re.match(r"^([A-Z][A-Za-z''\-]+)", key)
        year_m = re.search(r"(19|20)\d{2}", key)
        if m and year_m:
            author = m.group(1)
            year = year_m.group(0)
            if re.search(rf"\b{re.escape(author)}\b[^\n.]{{0,40}}\b{year}\b", text):
                return True
    return False


def _count_used_cites(body: str, works: list[dict[str, Any]]) -> int:
    return sum(1 for w in works if _body_mentions_work(body, w))


def _filter_cited_only(
    body: str,
    *,
    works: list[dict[str, Any]],
    references: list[str],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    kept_works: list[dict[str, Any]] = []
    kept_refs: list[str] = []
    in_text: list[str] = []
    n = max(len(works), len(references))
    for i in range(n):
        work = works[i] if i < len(works) else {}
        ref = references[i] if i < len(references) else str(work.get("reference") or "")
        if not work and not ref:
            continue
        if not _body_mentions_work(body, work or {"reference": ref}):
            continue
        if work:
            kept_works.append(work)
        if ref:
            kept_refs.append(ref)
        label = str(work.get("label") or work.get("intext") or work.get("in_text") or "").strip()
        if label and label not in in_text:
            in_text.append(label)
    return kept_works, kept_refs, in_text


def _try_insert_cite(body: str, label: str) -> str | None:
    """Append one parenthetical cite to a mid-section sentence if label not already present."""
    if not body or not label or label in body:
        return None
    sections = re.split(r"(?m)^(##\s+.+)$", body)
    if len(sections) < 3:
        # Single block — insert before last sentence of body.
        paras = [p for p in body.split("\n\n") if p.strip()]
        if len(paras) < 2:
            return None
        target = paras[len(paras) // 2]
        if label in target:
            return None
        updated = target.rstrip()
        if updated.endswith("."):
            updated = updated[:-1] + f" {label}."
        else:
            updated = updated + f" {label}"
        paras[len(paras) // 2] = updated
        return "\n\n".join(paras)

    # Prefer a non-References body section that is not the first heading-only chunk.
    for i in range(1, len(sections) - 1, 2):
        title = sections[i]
        chunk = sections[i + 1]
        if re.search(r"references|bibliography|works cited", title, re.I):
            continue
        if label in chunk:
            continue
        paras = [p for p in chunk.split("\n\n") if p.strip()]
        if not paras:
            continue
        idx = min(1, len(paras) - 1)
        target = paras[idx].rstrip()
        if target.endswith("."):
            paras[idx] = target[:-1] + f" {label}."
        else:
            paras[idx] = target + f" {label}"
        sections[i + 1] = "\n\n" + "\n\n".join(paras) + "\n\n"
        return "".join(sections)
    return None


def _llm_insert_allowed_cites(
    body: str,
    *,
    works: list[dict[str, Any]],
    in_text: list[str],
    style: str,
    target_additional: int,
) -> str:
    if target_additional <= 0 or not assignment_llm_configured(STAGE_CITATION_EXTRACT):
        return body
    payload = {
        "style": style,
        "target_additional": target_additional,
        "allowed_in_text": in_text,
        "works": [
            {
                "in_text": w.get("label") or w.get("intext") or w.get("in_text"),
                "reference": w.get("reference"),
                "title": w.get("title"),
                "year": w.get("year"),
            }
            for w in works
        ],
        "draft": body[:20000],
    }
    try:
        data, _ = assignment_generate_json(
            system_prompt=_INSERT_CITES_SYSTEM,
            user_prompt=json_dumps_truncated(payload),
            temperature=0.1,
            max_retries=1,
            stage=STAGE_CITATION_EXTRACT,
        )
    except Exception:  # noqa: BLE001
        return body
    if not isinstance(data, dict):
        return body
    updated = str(data.get("content") or "").strip()
    if not updated or len(updated) < max(80, int(len(body) * 0.5)):
        return body
    if body.count("## ") >= 2 and updated.count("## ") < 2:
        return body
    # Reject if any new cite forms appear that are not in allowed list.
    allowed = set(in_text)
    for match in _CLAIMED_CITE_RE.finditer(updated):
        author = match.group(1).split()[0]
        if not any(author in a for a in allowed):
            return body
    return _strip_references_section(updated)


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
                    "minimum_sources": requirement_json.get("minimum_sources"),
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


def _fill_queries(requirement_json: dict[str, Any], content: str) -> list[str]:
    out: list[str] = []
    for key in ("title", "topic", "assignment_type"):
        val = str(requirement_json.get(key) or "").strip()
        if val and val not in out:
            out.append(val)
    # Distinctive capitalized phrases as weak topic hints.
    for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", content or ""):
        phrase = match.group(1).strip()
        if phrase.lower() in {"the", "this", "these", "journal", "entry"}:
            continue
        if phrase not in out:
            out.append(phrase)
        if len(out) >= 12:
            break
    return out


def _heuristic_queries(content: str, requirement_json: dict[str, Any], *, max_queries: int) -> list[str]:
    found = _extract_claimed_cites(content)
    for extra in _fill_queries(requirement_json, content):
        if extra not in found:
            found.append(extra)
    return found[:max_queries]


def _reconcile_body_with_works(
    content: str,
    *,
    works: list[dict[str, Any]],
    in_text: list[str],
    style: str,
) -> str:
    if not works or not (content or "").strip():
        return content
    if not assignment_llm_configured(STAGE_CITATION_EXTRACT):
        return content
    payload = {
        "style": style,
        "allowed_in_text": in_text,
        "works": [
            {
                "in_text": w.get("label") or w.get("intext") or w.get("in_text"),
                "reference": w.get("reference"),
                "title": w.get("title"),
                "year": w.get("year"),
            }
            for w in works
        ],
        "draft": content[:20000],
    }
    try:
        data, _ = assignment_generate_json(
            system_prompt=_RECONCILE_SYSTEM,
            user_prompt=json_dumps_truncated(payload),
            temperature=0.1,
            max_retries=1,
            stage=STAGE_CITATION_EXTRACT,
        )
    except Exception:  # noqa: BLE001
        return content
    if not isinstance(data, dict):
        return content
    updated = str(data.get("content") or "").strip()
    if not updated or len(updated) < max(80, int(len(content) * 0.5)):
        return content
    # Never accept a reconcile that drops all section headings.
    if content.count("## ") >= 2 and updated.count("## ") < 2:
        return content
    return _strip_references_section(updated)


def _strip_references_section(content: str) -> str:
    body = content or ""
    match = _REF_HEADING_RE.search(body)
    if match:
        return body[: match.start()].rstrip()
    return body.rstrip()


def _apply_references_section(
    content: str,
    references: list[str],
    *,
    heading: str,
    on_new_page: bool = True,
) -> str:
    body = _strip_references_section(content)
    if not references:
        return body
    # Page-break hint for formatters that look for this HTML comment / marker.
    page_break = "\n\n<!-- pagebreak -->\n\n" if on_new_page else "\n\n"
    from formatter_v2.structure.references import split_concatenated_reference_entries

    entries: list[str] = []
    for item in references:
        entries.extend(split_concatenated_reference_entries(str(item)))
    if not entries:
        return body
    ref_block = page_break + "## " + heading + "\n\n" + "\n\n".join(entries)
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
