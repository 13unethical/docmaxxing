"""Blueprint analyzer using Gemini 2.5 Pro."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Protocol

from services.assignment_pipeline.models import utc_now
from services.assignment_llm import STAGE_BLUEPRINT, assignment_generate_json, assignment_llm_model
from services.blueprint_engine.models import (
    Blueprint,
    BlueprintEngineInput,
    BlueprintSection,
    SectionCompletionStatus,
    WordDistributionEntry,
)


class BlueprintEngine(Protocol):
    def build_blueprint(self, payload: BlueprintEngineInput) -> Blueprint:
        ...


class BlueprintAnalyzer:
    VERSION = assignment_llm_model(STAGE_BLUEPRINT)
    _INVALID_JSON_RETRIES = 2

    def build_blueprint(self, payload: BlueprintEngineInput) -> Blueprint:
        req = payload.requirement_json
        plan = payload.research_plan
        normalized = self._generate_blueprint_json(req=req, plan=plan)

        citation_style = str(req.get("citation_style") or req.get("citationStyle") or "APA 7")
        # Prefer the brief's word_count; never invent a fixed essay length.
        total_words = int(
            req.get("word_count")
            or req.get("estimatedWordCount")
            or _sum_section_words(plan)
            or 0
        )
        if total_words <= 0:
            total_words = max(400, _sum_section_words(plan) or 800)
        tone = str(normalized.get("academic_tone") or plan.get("writing_tone") or plan.get("writingTone") or "Formal academic prose")
        theories = list(plan.get("required_theories") or plan.get("requiredTheories") or [])
        section_specs = list(plan.get("section_list") or plan.get("sectionList") or [])
        if not section_specs:
            section_specs = [
                {"title": title, "purpose": normalized["section_purposes"].get(title, _default_objective(title))}
                for title in normalized["document_structure"]
            ]

        sections = [_build_section(spec, idx, theories, citation_style, total_words) for idx, spec in enumerate(section_specs)]
        if not sections:
            sections = _default_sections(total_words, theories, citation_style)
        sections = _apply_total_word_budget(sections, total_words)
        for i, section in enumerate(sections):
            section.transition_from_previous = _transition_from(
                sections[i - 1].title if i > 0 else None, section.title
            )
            section.transition_to_next = _transition_to(
                section.title, sections[i + 1].title if i + 1 < len(sections) else None
            )

        word_distribution = [
            WordDistributionEntry(title=section.title, estimated_words=section.estimated_words) for section in sections
        ]
        writing_queue = [
            section.title
            for section in sections
            if not _is_structural_section(section.title) and section.estimated_words > 0
        ]
        writing_order = [
            section.id
            for section in sections
            if not _is_structural_section(section.title) and section.estimated_words > 0
        ]

        critical_locations = [s.title for s in sections if _is_critical_section(s.title)]
        comparison_locations = [s.title for s in sections if _is_comparison_section(s.title)]
        counter_locations = [s.title for s in sections if _is_counter_section(s.title)]
        conclusion_goals = _conclusion_goals(plan)

        return Blueprint(
            id=str(uuid.uuid4()),
            project_id=payload.project_id,
            total_target_words=sum(entry.estimated_words for entry in word_distribution),
            total_target_sections=len(sections),
            writing_order=writing_order,
            transition_rules=_transition_rules(sections),
            citation_strategy=_citation_strategy(citation_style, plan),
            academic_tone=tone,
            document_structure=normalized["document_structure"],
            section_purposes=normalized["section_purposes"],
            target_word_distribution=[
                WordDistributionEntry(title=entry["title"], estimated_words=entry["estimated_words"])
                for entry in normalized["target_word_distribution"]
            ],
            argument_flow=normalized["argument_flow"],
            evidence_plan=normalized["evidence_plan"],
            citation_plan=normalized["citation_plan"],
            transition_plan=normalized["transition_plan"],
            writing_style=normalized["writing_style"],
            critical_discussion_points=normalized["critical_discussion_points"],
            forbidden_topics=normalized["forbidden_topics"],
            risk_points=normalized["risk_points"],
            critical_analysis_locations=critical_locations,
            comparison_locations=comparison_locations,
            counterargument_locations=counter_locations,
            conclusion_goals=conclusion_goals,
            sections=sections,
            word_distribution=word_distribution,
            writing_queue=writing_queue,
            estimated_completion_time=str(
                plan.get("estimated_completion_time") or plan.get("estimatedCompletionTime") or "8–11 hours"
            ),
            engine_version=self.VERSION,
            created_at=utc_now(),
        )

    def _generate_blueprint_json(self, *, req: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
        system_prompt = (
            "You are a blueprint planning engine. Do NOT write essays. "
            "Return strict JSON only with keys: document_structure,section_purposes,target_word_distribution,"
            "argument_flow,evidence_plan,citation_plan,transition_plan,academic_tone,writing_style,"
            "critical_discussion_points,forbidden_topics,risk_points. "
            "argument_flow,evidence_plan,citation_plan,transition_plan,critical_discussion_points,"
            "forbidden_topics,risk_points must be non-empty arrays of strings. "
            "document_structure must be an array of section title strings. "
            "target_word_distribution must be an array of objects with title and estimated_words."
        )
        user_prompt = (
            f"Requirement JSON:\n{json.dumps(req, ensure_ascii=False)}\n\n"
            f"Research JSON:\n{json.dumps(plan, ensure_ascii=False)}\n\n"
            "Return only valid JSON."
        )
        last_error = "LLM returned invalid blueprint JSON"
        for _ in range(self._INVALID_JSON_RETRIES + 1):
            raw, diagnostics = assignment_generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                stage=STAGE_BLUEPRINT,
            )
            if raw is None:
                last_error = str(diagnostics.get("error_message") or diagnostics.get("failure_reason") or last_error)
                continue
            if isinstance(raw, dict):
                try:
                    return _normalize_blueprint_json(raw, req=req, plan=plan)
                except ValueError as exc:
                    last_error = str(exc)
                    continue
            last_error = "Response is not a JSON object"
        raise ValueError(f"Blueprint generation failed after JSON retries: {last_error}")


class MockBlueprintEngine(BlueprintAnalyzer):
    """Backwards-compatible alias now powered by Gemini analyzer."""


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "section"


def _sum_section_words(plan: dict[str, Any]) -> int:
    sections = plan.get("section_list") or plan.get("sectionList") or []
    return sum(int(item.get("estimated_words") or item.get("estimatedWords") or 0) for item in sections)


def _build_section(
    spec: dict[str, Any],
    index: int,
    theories: list[str],
    citation_style: str,
    total_words: int,
) -> BlueprintSection:
    title = str(spec.get("title") or f"Section {index + 1}")
    objective = str(spec.get("purpose") or spec.get("objective") or _default_objective(title))
    words = int(spec.get("estimated_words") or spec.get("estimatedWords") or max(50, total_words // 5))
    key_points = _key_points_for(title)

    return BlueprintSection(
        id=_slug(title),
        title=title,
        objective=objective,
        estimated_words=words,
        key_points=key_points,
        required_arguments=_arguments_for(title, objective),
        required_evidence=_evidence_for(title),
        required_theories=theories[:2] if title.lower() != "references" else [],
        transition_from_previous="",
        transition_to_next="",
        citation_target=_citation_target(title, words),
        completion_status=SectionCompletionStatus.PENDING,
    )


def _default_sections(total_words: int, theories: list[str], citation_style: str) -> list[BlueprintSection]:
    specs = [
        ("Introduction", "Introduce the research question.", 0.1),
        ("Literature Review", "Map existing scholarship.", 0.22),
        ("Critical Analysis", "Compare theories and evaluate evidence.", 0.34),
        ("Discussion", "Synthesise implications.", 0.18),
        ("Conclusion", "Answer the research question.", 0.1),
        ("References", "Document sources.", 0.06),
    ]
    sections: list[BlueprintSection] = []
    for idx, (title, objective, ratio) in enumerate(specs):
        words = max(80, int(total_words * ratio))
        sections.append(
            BlueprintSection(
                id=_slug(title),
                title=title,
                objective=objective,
                estimated_words=words,
                key_points=_key_points_for(title),
                required_arguments=_arguments_for(title, objective),
                required_evidence=_evidence_for(title),
                required_theories=theories[:2] if title.lower() != "references" else [],
                transition_from_previous="",
                transition_to_next="",
                citation_target=_citation_target(title, words),
            )
        )
    for i, section in enumerate(sections):
        section.transition_from_previous = _transition_from(
            sections[i - 1].title if i > 0 else None, section.title
        )
        section.transition_to_next = _transition_to(
            section.title, sections[i + 1].title if i + 1 < len(sections) else None
        )
    return sections


def _is_structural_section(title: str) -> bool:
    lower = title.lower().strip()
    needles = (
        "reference",
        "bibliograph",
        "cover page",
        "title page",
        "table of contents",
        "acknowledgement",
        "acknowledgment",
        "appendix",
        "appendices",
    )
    if any(n in lower for n in needles):
        return True
    return lower in {"cover", "contents", "toc"}


def _apply_total_word_budget(sections: list[BlueprintSection], total_words: int) -> list[BlueprintSection]:
    writable = [
        section
        for section in sections
        if not _is_structural_section(section.title)
    ]
    if not writable or total_words <= 0:
        for section in sections:
            if _is_structural_section(section.title):
                section.estimated_words = 0
                section.citation_target = 0
        return sections
    current = sum(max(section.estimated_words, 0) for section in writable)
    if current <= 0:
        base = total_words // len(writable)
        for section in writable:
            section.estimated_words = base
    else:
        allocated = 0
        for section in writable[:-1]:
            words = max(40, int(total_words * (section.estimated_words / current)))
            section.estimated_words = words
            allocated += words
        writable[-1].estimated_words = max(40, total_words - allocated)
    for section in sections:
        if _is_structural_section(section.title):
            section.estimated_words = 0
            section.citation_target = 0
        else:
            section.citation_target = _citation_target(section.title, section.estimated_words)
    return sections


def _default_objective(title: str) -> str:
    lower = title.lower()
    if "introduction" in lower:
        return "Introduce the research question."
    if "conclusion" in lower:
        return "Answer the research question."
    if "analysis" in lower or "review" in lower:
        return "Compare theories and evaluate evidence."
    if "reference" in lower:
        return "Document all cited sources."
    return "Develop this section according to the research plan."


def _key_points_for(title: str) -> list[str]:
    lower = title.lower()
    if "introduction" in lower:
        return ["Background", "Thesis Statement", "Scope"]
    if "literature" in lower or "review" in lower:
        return ["Theme mapping", "Key debates", "Research gap"]
    if "analysis" in lower:
        return ["Advantages", "Disadvantages", "Evidence", "Counterargument"]
    if "discussion" in lower:
        return ["Synthesis", "Implications", "Limitations"]
    if "conclusion" in lower:
        return ["Direct answer", "Summary of argument", "Final implication"]
    if "reference" in lower:
        return ["Complete source list", "Consistent formatting"]
    if "methodology" in lower:
        return ["Approach", "Justification", "Limitations"]
    return ["Core claim", "Supporting logic", "Link to research question"]


def _arguments_for(title: str, objective: str) -> list[str]:
    return [
        f"Advance the section objective: {objective}",
        f"Maintain argumentative progression within {title}",
        "Integrate evidence rather than describe it",
    ]


def _evidence_for(title: str) -> list[str]:
    lower = title.lower()
    if "reference" in lower:
        return ["All cited works from preceding sections"]
    if "analysis" in lower or "review" in lower:
        return ["Peer-reviewed studies", "Comparative examples", "Data or policy documents"]
    return ["At least one peer-reviewed source", "One supporting example or statistic"]


def _citation_target(title: str, words: int) -> int:
    lower = title.lower()
    if "reference" in lower:
        return 0
    if "introduction" in lower:
        return max(2, words // 90)
    if "analysis" in lower or "review" in lower:
        return max(4, words // 70)
    return max(1, words // 110)


def _transition_from(previous: str | None, current: str) -> str:
    if not previous:
        return "Open the assignment and establish relevance immediately."
    return f"Bridge from {previous} by signalling how {current} extends the argument."


def _transition_to(current: str, nxt: str | None) -> str:
    if not nxt:
        return "Close the section with a sentence that reinforces the research question."
    return f"End {current} with a forward link that prepares the reader for {nxt}."


def _transition_rules(sections: list[BlueprintSection]) -> list[str]:
    return [
        "Each section must open with a signpost linking to the previous section.",
        "Avoid repeating the same source-led opening sentence across sections.",
        "Use explicit comparative language in analysis sections (however, whereas, in contrast).",
        "Conclusion must not introduce new sources or new major claims.",
    ]


def _citation_strategy(citation_style: str, plan: dict[str, Any]) -> str:
    sources = plan.get("estimated_academic_sources") or plan.get("estimatedAcademicSources") or 12
    return (
        f"Use {citation_style} throughout. Target approximately {sources} academic sources. "
        "Integrate citations inside analytical sentences, not as isolated lists."
    )


def _conclusion_goals(plan: dict[str, Any]) -> list[str]:
    question = plan.get("main_research_question") or plan.get("mainResearchQuestion") or ""
    goals = [
        "Answer the main research question directly in the first conclusion paragraph.",
        "Summarise the strongest evaluative findings without adding new evidence.",
        "State one limitation and one implication for future research or practice.",
    ]
    if question:
        goals.insert(0, f"Resolve: {question}")
    return goals


def _is_critical_section(title: str) -> bool:
    lower = title.lower()
    return "analysis" in lower or "discussion" in lower or "review" in lower


def _is_comparison_section(title: str) -> bool:
    lower = title.lower()
    return "analysis" in lower or "review" in lower or "discussion" in lower


def _is_counter_section(title: str) -> bool:
    lower = title.lower()
    return "analysis" in lower or "discussion" in lower


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            if isinstance(item, dict):
                items.extend(_coerce_string_list(item))
            else:
                text = str(item).strip()
                if text:
                    items.append(text)
        return items
    if isinstance(value, dict):
        return [
            f"{str(key).strip()}: {str(val).strip()}"
            for key, val in value.items()
            if str(key).strip() and str(val).strip()
        ]
    text = str(value).strip()
    return [text] if text else []


def _coerce_document_structure(value: Any) -> list[str]:
    if not isinstance(value, list):
        return _coerce_string_list(value)
    sections: list[str] = []
    for item in value:
        if isinstance(item, dict):
            title = str(item.get("section_title") or item.get("title") or "").strip()
            description = str(item.get("section_description") or item.get("description") or "").strip()
            if title and description:
                sections.append(f"{title}: {description}")
            elif title:
                sections.append(title)
        else:
            text = str(item).strip()
            if text:
                sections.append(text)
    return sections


def _coerce_word_distribution(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        rows: list[dict[str, Any]] = []
        for title, words in value.items():
            title_text = str(title).strip()
            if not title_text or title_text.lower() == "total":
                continue
            try:
                estimated_words = int(words)
            except (TypeError, ValueError):
                estimated_words = 0
            rows.append({"title": title_text, "estimated_words": max(0, estimated_words)})
        return rows
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("section_title") or "").strip()
        if not title:
            continue
        try:
            words = int(item.get("estimated_words") or item.get("estimatedWords") or 0)
        except (TypeError, ValueError):
            words = 0
        rows.append({"title": title, "estimated_words": max(0, words)})
    return rows


def _coerce_risk_points(value: Any) -> list[str]:
    if not isinstance(value, list):
        return _coerce_string_list(value)
    risks: list[str] = []
    for item in value:
        if isinstance(item, dict):
            risk = str(item.get("risk") or item.get("title") or "").strip()
            mitigation = str(item.get("mitigation") or item.get("description") or "").strip()
            if risk and mitigation:
                risks.append(f"{risk}: {mitigation}")
            elif risk:
                risks.append(risk)
        else:
            text = str(item).strip()
            if text:
                risks.append(text)
    return risks


def _default_blueprint_lists(req: dict[str, Any], plan: dict[str, Any]) -> dict[str, list[str]]:
    sections = [
        str(item.get("title") or "").strip()
        for item in (plan.get("section_list") or plan.get("sectionList") or [])
        if str(item.get("title") or "").strip()
    ]
    question = str(plan.get("main_research_question") or plan.get("mainResearchQuestion") or req.get("title") or "the assignment")
    return {
        "argument_flow": [
            f"Open with the research question: {question}",
            "Develop each section in the order defined by the assignment brief",
            "Conclude by answering the research question directly",
        ],
        "evidence_plan": [
            "Use lecture and seminar material in every analytical section",
            "Support claims with peer-reviewed academic sources",
        ],
        "citation_plan": [
            f"Apply {req.get('citation_style') or req.get('citationStyle') or 'APA 7'} consistently",
            "Integrate citations inside analytical sentences",
        ],
        "transition_plan": [
            "Signpost each section opening with a link to the previous section",
            "End analytical sections with a forward link to the next section",
        ],
    }


def _normalize_blueprint_json(raw: dict[str, Any], *, req: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    purposes_raw = raw.get("section_purposes")
    purposes: dict[str, str] = {}
    if isinstance(purposes_raw, dict):
        purposes = {str(k): str(v) for k, v in purposes_raw.items() if str(k).strip() and str(v).strip()}

    structure = _coerce_document_structure(raw.get("document_structure"))
    if not purposes and structure:
        purposes = {title.split(":", 1)[0].strip(): title for title in structure if title.strip()}

    target_distribution = _coerce_word_distribution(raw.get("target_word_distribution"))
    if not target_distribution and structure:
        per_section = max(
            80,
            int(req.get("word_count") or req.get("estimatedWordCount") or _sum_section_words(plan) or 800)
            // max(len(structure), 1),
        )
        target_distribution = [
            {"title": title.split(":", 1)[0].strip(), "estimated_words": per_section}
            for title in structure
            if title.strip() and "reference" not in title.lower()
        ]

    defaults = _default_blueprint_lists(req, plan)
    normalized = {
        "document_structure": structure,
        "section_purposes": purposes,
        "target_word_distribution": target_distribution,
        "argument_flow": _coerce_string_list(raw.get("argument_flow")),
        "evidence_plan": _coerce_string_list(raw.get("evidence_plan")),
        "citation_plan": _coerce_string_list(raw.get("citation_plan")),
        "transition_plan": _coerce_string_list(raw.get("transition_plan")),
        "academic_tone": str(raw.get("academic_tone") or "").strip() or "Formal academic prose",
        "writing_style": str(raw.get("writing_style") or "").strip() or "Analytical academic style",
        "critical_discussion_points": _coerce_string_list(raw.get("critical_discussion_points")),
        "forbidden_topics": _coerce_string_list(raw.get("forbidden_topics")),
        "risk_points": _coerce_risk_points(raw.get("risk_points")),
    }

    for key, fallback in defaults.items():
        if not normalized[key]:
            normalized[key] = fallback
    if not normalized["critical_discussion_points"]:
        normalized["critical_discussion_points"] = [
            "Compare competing interpretations instead of summarizing sources",
            "Evaluate limitations of the chosen historical framework",
        ]
    if not normalized["risk_points"]:
        normalized["risk_points"] = list(plan.get("writing_risks") or plan.get("potential_risks") or [])[:4] or [
            "Avoid descriptive summary without critical evaluation",
        ]

    required_lists = [
        "document_structure",
        "argument_flow",
        "evidence_plan",
        "citation_plan",
        "transition_plan",
        "critical_discussion_points",
        "risk_points",
    ]
    missing = [name for name in required_lists if not normalized[name]]
    if missing:
        raise ValueError(f"Blueprint JSON missing required non-empty arrays: {', '.join(missing)}")
    if not normalized["section_purposes"]:
        raise ValueError("Blueprint JSON missing section_purposes object")
    if not normalized["target_word_distribution"]:
        raise ValueError("Blueprint JSON missing target_word_distribution entries")
    return normalized
