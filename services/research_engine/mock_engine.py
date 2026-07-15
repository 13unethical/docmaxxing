"""Research analyzer backed by Gemini 2.5 Pro."""

from __future__ import annotations

import json
import uuid
from typing import Any, Protocol

from services.assignment_pipeline.models import utc_now
from services.assignment_llm import STAGE_RESEARCH, assignment_generate_json, assignment_llm_model
from services.research_engine.models import (
    ResearchEngineInput,
    ResearchPlan,
    ResearchSection,
)


class ResearchEngine(Protocol):
    """Contract for research planning."""

    def build_plan(self, payload: ResearchEngineInput) -> ResearchPlan:
        ...


class ResearchAnalyzer:
    VERSION = assignment_llm_model(STAGE_RESEARCH)
    _INVALID_JSON_RETRIES = 2

    def build_plan(self, payload: ResearchEngineInput) -> ResearchPlan:
        req = payload.requirement_json
        docs = list(payload.parsed_documents)
        normalized = self._generate_research_json(req=req, docs=docs)

        assignment_type = str(req.get("assignment_type") or req.get("assignmentType") or "Essay")
        title = str(req.get("title") or _topic_from_documents(docs) or "Academic Assignment")
        word_count = int(req.get("word_count") or req.get("estimatedWordCount") or 2500)
        difficulty = str(req.get("difficulty") or req.get("estimatedDifficulty") or "★★★★☆")
        min_sources = int(req.get("minimum_sources") or req.get("minimumReferences") or 12)
        section_list = _build_sections(normalized["suggested_sections"], assignment_type, word_count)
        return ResearchPlan(
            id=str(uuid.uuid4()),
            project_id=payload.project_id,
            assignment_topic=title,
            writing_objective=f"Build an evidence-based {assignment_type.lower()} plan around the research question.",
            main_research_question=normalized["research_question"],
            research_question=normalized["research_question"],
            key_arguments=normalized["key_arguments"],
            counter_arguments=normalized["counter_arguments"],
            academic_theories=normalized["academic_theories"],
            important_keywords=normalized["important_keywords"],
            search_queries=normalized["search_queries"],
            recommended_journals=normalized["recommended_journals"],
            recommended_statistics=normalized["recommended_statistics"],
            suggested_sections=normalized["suggested_sections"],
            terminology=normalized["terminology"],
            writing_risks=normalized["writing_risks"],
            research_depth=normalized["research_depth"],
            secondary_questions=normalized["counter_arguments"][:3],
            target_audience=_target_audience(assignment_type),
            writing_tone=_writing_tone(assignment_type),
            recommended_structure=_structure_summary(section_list),
            section_list=section_list,
            required_theories=normalized["academic_theories"],
            required_concepts=normalized["terminology"],
            required_case_studies=_case_studies(assignment_type),
            required_arguments=normalized["key_arguments"],
            possible_counterarguments=normalized["counter_arguments"],
            suggested_evidence=normalized["recommended_statistics"] or _evidence(assignment_type),
            estimated_academic_sources=min_sources,
            recommended_source_types=_source_types(assignment_type) + normalized["recommended_journals"][:2],
            potential_risks=normalized["writing_risks"],
            notes_for_writer=[f"Use keyword cluster: {', '.join(normalized['important_keywords'][:6])}"],
            estimated_difficulty=difficulty,
            estimated_completion_time=_completion_time(word_count, difficulty),
            engine_version=self.VERSION,
            created_at=utc_now(),
        )

    def _generate_research_json(self, *, req: dict[str, Any], docs: list[Any]) -> dict[str, Any]:
        system_prompt = (
            "You are a research planning engine. "
            "Do NOT write essays. Do NOT fetch web data. "
            "Return strict JSON only with keys: "
            "research_question,key_arguments,counter_arguments,academic_theories,important_keywords,"
            "search_queries,recommended_journals,recommended_statistics,suggested_sections,terminology,"
            "writing_risks,research_depth. "
            "Every listed field except research_question and research_depth must be a non-empty array of strings. "
            "Do not return objects for terminology or plain text for recommended_statistics; use string arrays."
        )
        docs_text = "\n\n".join(
            f"[{getattr(doc, 'file_type', 'file')}] {getattr(doc, 'filename', '')}\n{str(getattr(doc, 'text', '')).strip()[:2500]}"
            for doc in docs
        ) or "No parsed documents provided"
        user_prompt = (
            f"Requirement JSON:\n{json.dumps(req, ensure_ascii=False)}\n\n"
            f"Parsed documents:\n{docs_text}\n\n"
            "Return only valid JSON."
        )
        last_error = "LLM returned invalid research JSON"
        for _ in range(self._INVALID_JSON_RETRIES + 1):
            raw, diagnostics = assignment_generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                stage=STAGE_RESEARCH,
            )
            if raw is None:
                last_error = str(diagnostics.get("error_message") or diagnostics.get("failure_reason") or last_error)
                continue
            if isinstance(raw, dict):
                try:
                    return _normalize_research_json(raw, req=req, docs=docs)
                except ValueError as exc:
                    last_error = str(exc)
                    continue
            last_error = "Response is not a JSON object"
        raise ValueError(f"Research analysis failed after JSON retries: {last_error}")


class MockResearchEngine(ResearchAnalyzer):
    """Backwards-compatible alias; now uses real Gemini analyzer."""


def _topic_from_documents(docs: list[Any]) -> str | None:
    for doc in docs:
        if getattr(doc, "file_type", "") == "assignment_brief" and getattr(doc, "text", ""):
            first_line = doc.text.strip().splitlines()[0][:120]
            return first_line.strip() or None
    return None


def _writing_objective(assignment_type: str, topic: str) -> str:
    return (
        f"Produce a rigorous {assignment_type.lower()} that critically examines {topic.lower()} "
        "using academic evidence, clear structure, and evaluative argumentation."
    )


def _main_question(assignment_type: str, topic: str) -> str:
    if assignment_type == "Case Study":
        return f"How should {topic.lower()} be analysed to produce actionable recommendations?"
    if assignment_type == "Literature Review":
        return f"What does current scholarship reveal about {topic.lower()}, and where are the key gaps?"
    return f"To what extent does existing evidence support current understanding of {topic.lower()}?"


def _secondary_questions(assignment_type: str, topic: str) -> list[str]:
    base = [
        f"Which theoretical frameworks best explain key dimensions of {topic.lower()}?",
        "What methodological limitations appear in the available literature?",
        "How do competing perspectives change the interpretation of findings?",
    ]
    if assignment_type == "Case Study":
        base.append("What contextual factors most influence outcomes in this case?")
    return base


def _section_blueprints(assignment_type: str) -> list[tuple[str, str, str, float]]:
    if assignment_type == "Literature Review":
        return [
            ("Introduction", "Open the review and define scope.", "Introduce the topic and research question.", 0.1),
            ("Thematic Review", "Synthesise literature by theme.", "Organise scholarship into coherent themes.", 0.55),
            ("Critical Discussion", "Evaluate debates and gaps.", "Compare theories and evaluate evidence.", 0.2),
            ("Conclusion", "Summarise implications.", "Answer the research question.", 0.1),
            ("References", "List cited works.", "Demonstrate scholarly grounding.", 0.05),
        ]
    if assignment_type == "Case Study":
        return [
            ("Introduction", "Frame the case and aim.", "Introduce the topic and research question.", 0.1),
            ("Background", "Establish context.", "Explain the setting and key stakeholders.", 0.15),
            ("Case Analysis", "Apply theory to evidence.", "Compare theories and evaluate evidence.", 0.45),
            ("Recommendations", "Propose evidence-based actions.", "Translate analysis into practical guidance.", 0.15),
            ("Conclusion", "Answer the research question.", "Synthesise findings and limits.", 0.1),
            ("References", "List cited works.", "Support claims with academic sources.", 0.05),
        ]
    return [
        ("Introduction", "Set scope and thesis direction.", "Introduce the topic and research question.", 0.1),
        ("Literature Review", "Survey relevant scholarship.", "Map existing research and debates.", 0.25),
        ("Methodology", "Explain analytical approach.", "Clarify how the argument will be developed.", 0.1),
        ("Critical Analysis", "Develop the core argument.", "Compare theories and evaluate evidence.", 0.35),
        ("Conclusion", "Resolve the research question.", "Answer the research question.", 0.12),
        ("References", "Document sources.", "Meet citation requirements.", 0.08),
    ]


def _build_sections(
    required_sections: list[str],
    assignment_type: str,
    word_count: int,
) -> list[ResearchSection]:
    blueprints = _section_blueprints(assignment_type)
    if required_sections:
        weights = _weights_for_required(required_sections, word_count)
        return [
            ResearchSection(
                title=title,
                description=f"Planned section aligned to assignment brief: {title}.",
                purpose=purpose,
                estimated_words=words,
            )
            for title, _, purpose, words in weights
        ]

    sections: list[ResearchSection] = []
    for title, description, purpose, ratio in blueprints:
        sections.append(
            ResearchSection(
                title=title,
                description=description,
                purpose=purpose,
                estimated_words=max(80, int(word_count * ratio)),
            )
        )
    return sections


def _weights_for_required(
    required_sections: list[str],
    word_count: int,
) -> list[tuple[str, str, str, int]]:
    body_sections = [s for s in required_sections if s.lower() != "references"]
    ref_words = 0 if "references" not in [s.lower() for s in required_sections] else max(0, int(word_count * 0.05))
    allocatable = max(word_count - ref_words, 0)
    per_section = int(allocatable / max(len(body_sections), 1))
    rows: list[tuple[str, str, str, int]] = []
    for section in required_sections:
        if section.lower() == "references":
            rows.append((section, "Reference list.", "Demonstrate scholarly grounding.", ref_words or 120))
        elif section.lower() == "introduction":
            rows.append((section, "Opening section.", "Introduce the topic and research question.", min(220, per_section)))
        elif "conclusion" in section.lower():
            rows.append((section, "Closing section.", "Answer the research question.", min(220, per_section)))
        elif "analysis" in section.lower() or "review" in section.lower():
            rows.append((section, "Core analytical section.", "Compare theories and evaluate evidence.", per_section + 120))
        else:
            rows.append((section, "Supporting section.", "Develop a key part of the argument.", per_section))
    return rows


def _structure_summary(sections: list[ResearchSection]) -> str:
    return " → ".join(section.title for section in sections)


def _target_audience(assignment_type: str) -> str:
    if assignment_type == "Case Study":
        return "University assessors and professional readers expecting applied analysis"
    return "Academic assessors familiar with discipline conventions"


def _writing_tone(assignment_type: str) -> str:
    if assignment_type == "Reflection":
        return "Reflective yet analytical, first-person where appropriate"
    return "Formal, objective, and evidence-led academic prose"


def _theories(assignment_type: str, docs: list[Any]) -> list[str]:
    theories = ["Stakeholder theory", "Institutional theory", "Resource-based view"]
    if _doc_mentions(docs, "sustainability"):
        theories.append("Triple bottom line framework")
    if assignment_type == "Literature Review":
        theories = ["Thematic synthesis", "Critical discourse analysis", "Socio-technical transitions theory"]
    return theories


def _concepts(assignment_type: str, docs: list[Any]) -> list[str]:
    concepts = ["Critical evaluation", "Evidence weighting", "Conceptual framing"]
    if assignment_type == "Case Study":
        concepts.extend(["Contextual analysis", "Problem diagnosis"])
    return concepts


def _case_studies(assignment_type: str) -> list[str]:
    if assignment_type != "Case Study":
        return ["Use comparative examples only where they strengthen argument"]
    return ["Primary case organisation", "Benchmark comparator case", "Industry best-practice example"]


def _arguments(assignment_type: str, topic: str) -> list[str]:
    return [
        f"Current approaches to {topic.lower()} are insufficiently evidence-based",
        "Theoretical frameworks should be integrated rather than listed descriptively",
        "Implications for practice or policy must follow from analysis",
    ]


def _counterarguments(assignment_type: str, topic: str) -> list[str]:
    return [
        "Limited high-quality empirical studies may weaken generalisability",
        "Alternative interpretations of the same evidence may be plausible",
        f"Context-specific constraints may limit transferability of conclusions about {topic.lower()}",
    ]


def _evidence(assignment_type: str) -> list[str]:
    base = ["Peer-reviewed journal articles", "Government or institutional reports", "Recent meta-analyses"]
    if assignment_type == "Case Study":
        base.append("Primary organisational documents and credible industry data")
    return base


def _source_types(assignment_type: str) -> list[str]:
    types = ["Peer-reviewed journals", "Academic books", "Official reports"]
    if assignment_type == "Literature Review":
        types.append("Systematic review papers")
    return types


def _risks(req: dict[str, Any], docs: list[Any]) -> list[str]:
    risks = []
    missing = req.get("missing_information") or req.get("missingInformation") or []
    risks.extend(str(item) for item in missing[:3])
    if not docs:
        risks.append("No parsed document text available — plan relies on Requirement JSON only")
    if not req.get("word_count") and not req.get("estimatedWordCount"):
        risks.append("Word count target unclear — section allocation may need revision")
    risks.append("Writer must avoid descriptive summary without critical evaluation")
    return risks


def _writer_notes(req: dict[str, Any], docs: list[Any]) -> list[str]:
    notes = [
        "Use the section plan as the only writing blueprint — do not improvise structure.",
        "Every major claim should be traceable to a planned argument or evidence type.",
        f"Follow {req.get('citation_style') or req.get('citationStyle') or 'APA 7'} consistently.",
    ]
    if docs:
        notes.append("Ground terminology and emphasis in parsed brief and rubric text.")
    outcomes = req.get("learning_outcomes") or req.get("learningOutcomes") or []
    for outcome in outcomes[:2]:
        notes.append(f"Demonstrate learning outcome: {outcome}")
    return notes


def _completion_time(word_count: int, difficulty: str) -> str:
    hours = max(6, int(word_count / 220))
    if "★★★★★" in difficulty:
        hours += 4
    elif "★★★★" in difficulty:
        hours += 2
    return f"{hours}–{hours + 3} hours"


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


def _default_recommended_statistics(req: dict[str, Any]) -> list[str]:
    assignment_type = str(req.get("assignment_type") or req.get("assignmentType") or "Essay")
    return [
        f"Qualitative synthesis appropriate for {assignment_type.lower()} assignments",
        "Use lecture, seminar, and brief evidence rather than quantitative datasets",
    ]


def _default_terminology(normalized: dict[str, Any], req: dict[str, Any]) -> list[str]:
    keywords = normalized.get("important_keywords") or []
    if keywords:
        return [f"{keyword}: core concept for this assignment" for keyword in keywords[:5]]
    title = str(req.get("title") or "the assignment topic")
    return [
        f"Business evolution: how practices changed over time in relation to {title.lower()}",
        "Historical concept: foundational idea from marketing, digital innovation, or international business",
    ]


def _normalize_research_json(raw: dict[str, Any], *, req: dict[str, Any], docs: list[Any]) -> dict[str, Any]:
    def pick_list(name: str) -> list[str]:
        return _coerce_string_list(raw.get(name))

    research_question = str(raw.get("research_question") or "").strip()
    if not research_question:
        topic = str(req.get("title") or _topic_from_documents(docs) or "the assignment topic")
        research_question = f"What evidence-based conclusions can be drawn about {topic.lower()}?"

    normalized = {
        "research_question": research_question,
        "key_arguments": pick_list("key_arguments"),
        "counter_arguments": pick_list("counter_arguments"),
        "academic_theories": pick_list("academic_theories"),
        "important_keywords": pick_list("important_keywords"),
        "search_queries": pick_list("search_queries"),
        "recommended_journals": pick_list("recommended_journals"),
        "recommended_statistics": pick_list("recommended_statistics"),
        "suggested_sections": pick_list("suggested_sections"),
        "terminology": pick_list("terminology"),
        "writing_risks": pick_list("writing_risks"),
        "research_depth": str(raw.get("research_depth") or "").strip() or "medium",
    }

    if not normalized["recommended_statistics"]:
        normalized["recommended_statistics"] = _default_recommended_statistics(req)
    if not normalized["terminology"]:
        normalized["terminology"] = _default_terminology(normalized, req)

    required = [
        "key_arguments",
        "counter_arguments",
        "academic_theories",
        "important_keywords",
        "search_queries",
        "recommended_journals",
        "recommended_statistics",
        "suggested_sections",
        "terminology",
        "writing_risks",
    ]
    missing = [key for key in required if not normalized[key]]
    if missing:
        raise ValueError(f"Research JSON missing required non-empty arrays: {', '.join(missing)}")
    return normalized


def _doc_mentions(docs: list[Any], keyword: str) -> bool:
    keyword_lower = keyword.lower()
    return any(keyword_lower in getattr(doc, "text", "").lower() for doc in docs)
