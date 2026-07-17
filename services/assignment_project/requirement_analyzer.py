"""Requirement analyzer interface and Gemini implementation."""

from __future__ import annotations

import json
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from formatter.document_io import extract_text_from_document_bytes
from services.check_requirements import parse_word_count_spec
from services.assignment_pipeline.models import utc_now
from services.assignment_llm import (
    STAGE_REQUIREMENT_ANALYSIS,
    assignment_generate_json,
    assignment_llm_model,
)
from services.assignment_project.models import (
    Project,
    ProjectFile,
    ProjectFileType,
    RequirementFormatting,
    RequirementJSON,
    RubricCriterion,
)


@dataclass
class AnalyzerInput:
    project: Project
    files: list[ProjectFile]
    requirement: RequirementJSON


class RequirementAnalyzer(Protocol):
    """Contract for requirement extraction."""

    def analyze(self, payload: AnalyzerInput) -> RequirementJSON:
        ...


class GeminiRequirementAnalyzer:
    """Requirement analyzer — uses Claude for assignment when configured."""

    VERSION = assignment_llm_model(STAGE_REQUIREMENT_ANALYSIS)
    _INVALID_JSON_RETRIES = 2

    def analyze(self, payload: AnalyzerInput) -> RequirementJSON:
        project = payload.project
        base = payload.requirement
        sections = _collect_source_text(payload.files)
        system_prompt = _requirement_system_prompt()
        user_prompt = _requirement_user_prompt(project, sections)

        last_error = "LLM did not return a valid Requirement JSON object"
        for attempt in range(self._INVALID_JSON_RETRIES + 1):
            raw, diagnostics = assignment_generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                stage=STAGE_REQUIREMENT_ANALYSIS,
            )
            if raw is None:
                last_error = str(diagnostics.get("error_message") or diagnostics.get("failure_reason") or last_error)
                continue
            try:
                normalized = _normalize_requirement_json(raw)
            except ValueError as exc:
                last_error = str(exc)
                continue
            # Safety net only: if Gemini left word_count null, recover from the brief text.
            # Never overwrite a non-null Gemini value — each assignment has its own limit.
            if normalized.get("word_count") is None:
                local_word_count = _extract_word_count_from_sources(sections)
                if local_word_count is not None:
                    normalized["word_count"] = local_word_count
                    normalized["missing_information"] = [
                        item
                        for item in normalized.get("missing_information", [])
                        if "word count" not in item.lower()
                    ]
            # Fill missing per-section budgets from brief text (e.g. "Introduction – 100 words").
            local_budgets = _extract_section_word_budgets_from_sources(sections)
            merged_budgets = dict(normalized.get("section_word_budgets") or {})
            for title, words in local_budgets.items():
                if title not in merged_budgets:
                    merged_budgets[title] = words
            # Also parse budgets embedded in required_sections strings.
            for section in normalized.get("required_sections") or []:
                title, words = _parse_section_word_budget(str(section))
                if words is not None and title:
                    merged_budgets.setdefault(title, words)
            normalized["section_word_budgets"] = merged_budgets
            return RequirementJSON(
                id=base.id,
                project_id=base.project_id,
                assignment_type=normalized.get("assignment_type"),
                title=normalized.get("title"),
                word_count=normalized.get("word_count"),
                citation_style=normalized.get("citation_style"),
                required_sections=normalized.get("required_sections", []),
                section_word_budgets=normalized.get("section_word_budgets") or {},
                rubric=[RubricCriterion.from_dict(item) for item in normalized.get("rubric", [])],
                learning_outcomes=normalized.get("learning_outcomes", []),
                minimum_sources=normalized.get("minimum_sources"),
                formatting=RequirementFormatting.from_dict(normalized.get("formatting")),
                deadline=normalized.get("deadline"),
                difficulty=normalized.get("difficulty"),
                missing_information=normalized.get("missing_information", []),
                analyzer_version=self.VERSION,
                analyzed_at=utc_now(),
            )
        raise ValueError(f"Requirement analysis failed after JSON retries: {last_error}")


def normalize_file_type(value: str) -> ProjectFileType | None:
    raw = value.strip().lower().replace(" ", "_").replace("/", "_")
    aliases = {
        "assignment_brief": ProjectFileType.ASSIGNMENT_BRIEF,
        "brief": ProjectFileType.ASSIGNMENT_BRIEF,
        "rubric": ProjectFileType.RUBRIC,
        "lecture_slides": ProjectFileType.LECTURE_SLIDES,
        "slides": ProjectFileType.LECTURE_SLIDES,
        "reading_material": ProjectFileType.READING_MATERIAL,
        "reading_materials": ProjectFileType.READING_MATERIAL,
        "sample_assignment": ProjectFileType.SAMPLE_ASSIGNMENT,
        "professor_notes": ProjectFileType.PROFESSOR_NOTES,
        "additional_file": ProjectFileType.ADDITIONAL_FILE,
        "additional_files_materials": ProjectFileType.ADDITIONAL_FILE,
    }
    if raw in aliases:
        return aliases[raw]
    try:
        return ProjectFileType(raw)
    except ValueError:
        return None


def _requirement_system_prompt() -> str:
    return (
        "You are an academic requirement-analysis engine. "
        "Do not write essays or content drafts. "
        "Return one strict JSON object only, no markdown, no code fences, no commentary. "
        "Required top-level keys: assignment_type, title, word_count, citation_style, "
        "required_sections, section_word_budgets, rubric, learning_outcomes, minimum_sources, "
        "formatting, deadline, difficulty, missing_information. "
        "word_count and minimum_sources must be integers or null; never use descriptive text for them. "
        "WORD COUNT RULES (critical): "
        "1) Search the entire brief, tables, notes, and rubric for any word/page length limit. "
        "2) Exact limit like '2000 words' or 'approx. 1500 words' → word_count = that integer. "
        "3) Range like '500-550 words', '1800–2200 words', 'between 1000 and 1200 words' "
        "→ word_count = the UPPER bound of the range (550, 2200, 1200). "
        "4) Only set word_count to null if no numeric length limit appears anywhere; "
        "then list 'word count' in missing_information. "
        "Do not invent a default length. Do not use essay-length defaults. "
        "SECTION WORD BUDGETS (critical): "
        "If the brief assigns per-section limits like 'Introduction – 100 words', "
        "'Journal Entry 1 – 200 words', 'Reflection – 300 words', put them in "
        "section_word_budgets as an object mapping short section title → integer "
        '(example: {"Introduction": 100, "Journal Entry 1": 200, "Reflection": 300}). '
        "Cover page, title page, and References usually have no body word budget — omit them "
        "or set 0. Do not invent section budgets. "
        "REQUIRED SECTIONS: use only section titles stated in the brief "
        "(e.g. Introduction, Journal Entry 1, Reflection, Reference List). "
        "Do not invent generic essay sections when the brief lists specific ones. "
        "The formatting field must be an object with keys: font_family, font_size, "
        "line_spacing, margins, alignment. "
        "Rubric must be an array of objects with keys: criterion, weight, description."
    )


def _requirement_user_prompt(project: Project, sections: dict[str, str]) -> str:
    metadata = {
        "project_title": project.title,
        "project_note": project.note,
        "project_deadline": project.deadline.isoformat() if project.deadline else None,
        "project_university": project.university,
    }
    return (
        "Analyze assignment requirements from all provided materials.\n\n"
        f"PROJECT_METADATA:\n{json.dumps(metadata, ensure_ascii=False)}\n\n"
        f"ASSIGNMENT_BRIEF:\n{sections['assignment_brief']}\n\n"
        f"RUBRIC:\n{sections['rubric']}\n\n"
        f"LECTURE_NOTES:\n{sections['lecture_notes']}\n\n"
        f"UPLOADED_FILES:\n{sections['uploaded_files']}\n\n"
        "Extract only explicit requirements. Prefer assignment brief and rubric over lecture notes. "
        "Find the stated word/length limit carefully (including wording inside tables). "
        "For a range, put the upper bound in word_count as an integer. "
        "Also extract per-section word limits into section_word_budgets when stated "
        "(Introduction 100, journal entries 200, reflection 300, etc.). "
        "If a field is not stated, set it to null or []/{} and list it in missing_information. "
        "Keep required_sections as ordered section titles exactly as the brief lists them. "
        "Return only valid JSON with the required structure."
    )


def _collect_source_text(files: list[ProjectFile]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {
        "assignment_brief": [],
        "rubric": [],
        "lecture_notes": [],
        "uploaded_files": [],
    }
    for file in files:
        snippet = _extract_file_text(file)
        line = f"[{file.file_type.value}] {file.original_filename}\n{snippet}".strip()
        grouped["uploaded_files"].append(line)
        if file.file_type == ProjectFileType.ASSIGNMENT_BRIEF:
            grouped["assignment_brief"].append(line)
        elif file.file_type == ProjectFileType.RUBRIC:
            grouped["rubric"].append(line)
        elif file.file_type in {ProjectFileType.LECTURE_SLIDES, ProjectFileType.PROFESSOR_NOTES}:
            grouped["lecture_notes"].append(line)
    return {
        "assignment_brief": "\n\n".join(grouped["assignment_brief"]) or "Not provided",
        "rubric": "\n\n".join(grouped["rubric"]) or "Not provided",
        "lecture_notes": "\n\n".join(grouped["lecture_notes"]) or "Not provided",
        "uploaded_files": "\n\n".join(grouped["uploaded_files"]) or "Not provided",
    }


def _extract_file_text(file: ProjectFile) -> str:
    path = Path(file.storage_path)
    if not path.exists() or not path.is_file():
        return "(file content unavailable in storage; using metadata only)"
    suffix = path.suffix.lower()
    try:
        raw = path.read_bytes()
    except OSError:
        return "(unable to read file content)"
    try:
        if suffix in {".txt", ".md"}:
            text = raw.decode("utf-8", errors="replace")
        elif suffix in {".docx", ".pdf"}:
            text = extract_text_from_document_bytes(raw, file.original_filename)
        else:
            text = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return "(failed to parse file content)"
    normalized = " ".join(text.replace("\r", "\n").split())
    return normalized[:12000] if normalized else "(empty file content)"


def _extract_word_count_from_sources(sections: dict[str, str]) -> int | None:
    text = "\n".join(sections.values())
    word_min, word_max, confidence = parse_word_count_spec(text)
    # Accept approximate/"about N words" (confidence ~0.55) as well as exact ranges.
    if confidence < 0.5:
        return None
    if word_max is not None:
        return int(word_max)
    if word_min is not None:
        return int(word_min)
    return None


_SECTION_BUDGET_LINE = re.compile(
    r"(?P<title>Introduction|Journal Entry\s*\d+|Reflection|Conclusion|"
    r"Body(?:\s+paragraph)?\s*\d*|Literature Review|Discussion|Methodology|"
    r"Findings|Critical Analysis|Abstract|Analysis)"
    r"(?:\s*\([^)]*\))?"
    r".{0,160}?"
    r"[–\-]\s*(?P<words>\d{2,4})\s*words?\b",
    re.I,
)

_SECTION_BUDGET_INLINE = re.compile(
    r"(?P<title>.+?)\s*(?:[–\-]\s*|\()\s*(?P<words>\d{2,4})\s*words?\s*\)?\s*$",
    re.I,
)


def _parse_section_word_budget(text: str) -> tuple[str, int | None]:
    """Return (short title, budget) from a required-section string."""
    raw = str(text or "").strip()
    if not raw:
        return "", None
    title = raw.split(":", 1)[0].strip() if ":" in raw else raw
    # Prefer trailing "– N words" / "(N words)" on the full string.
    match = _SECTION_BUDGET_INLINE.search(raw)
    words = int(match.group("words")) if match else None
    if words is not None and match:
        # Title may include the budget suffix — strip it.
        title = re.sub(
            r"\s*(?:[–\-]\s*|\()\s*\d{2,4}\s*words?\s*\)?\s*$",
            "",
            title,
            flags=re.I,
        ).strip() or title
    if ":" in title:
        title = title.split(":", 1)[0].strip()
    return title, words


def _extract_section_word_budgets_from_sources(sections: dict[str, str]) -> dict[str, int]:
    text = "\n".join(sections.values())
    budgets: dict[str, int] = {}
    for match in _SECTION_BUDGET_LINE.finditer(text):
        title = re.sub(r"\s+", " ", match.group("title")).strip()
        words = int(match.group("words"))
        if title and words > 0:
            budgets[title] = words
    return budgets


def _coerce_section_word_budgets(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        title = str(key).strip()
        if not title:
            continue
        try:
            words = int(value)
        except (TypeError, ValueError):
            continue
        if words >= 0:
            out[title] = words
    return out


def _coerce_word_count_value(word_count: Any) -> int | None:
    """Turn Gemini word_count (int, '2000', '500-550', 'about 1500 words') into an int."""
    if word_count is None or isinstance(word_count, bool):
        return None
    if isinstance(word_count, int):
        return word_count
    if isinstance(word_count, float) and word_count.is_integer():
        return int(word_count)
    if isinstance(word_count, str):
        stripped = word_count.strip()
        if not stripped:
            return None
        if stripped.isdigit():
            return int(stripped)
        # Bare range from Gemini: "500-550" / "1800–2200"
        bare = re.fullmatch(r"(\d{1,5})\s*[-–]\s*(\d{1,5})", stripped)
        if bare:
            return int(bare.group(2))
        probe = stripped if re.search(r"words?", stripped, re.I) else f"{stripped} words"
        wmin, wmax, confidence = parse_word_count_spec(probe)
        if confidence >= 0.5:
            if wmax is not None:
                return int(wmax)
            if wmin is not None:
                return int(wmin)
        return None
    try:
        return int(word_count)
    except (TypeError, ValueError):
        return None


def _normalize_requirement_json(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("LLM response is not a JSON object")

    def pick(*keys: str):
        for key in keys:
            if key in raw:
                return raw[key]
        return None

    assignment_type = pick("assignment_type", "assignmentType")
    title = pick("title")
    word_count = pick("word_count", "wordCount")
    citation_style = pick("citation_style", "citationStyle")
    required_sections = pick("required_sections", "requiredSections")
    section_word_budgets = pick("section_word_budgets", "sectionWordBudgets")
    rubric = pick("rubric")
    learning_outcomes = pick("learning_outcomes", "learningOutcomes")
    minimum_sources = pick("minimum_sources", "minimumSources")
    formatting = pick("formatting")
    deadline = pick("deadline")
    difficulty = pick("difficulty")
    missing_information = pick("missing_information", "missingInformation")

    if not isinstance(required_sections, list):
        raise ValueError("required_sections must be an array")
    if not isinstance(rubric, list):
        raise ValueError("rubric must be an array")
    if not isinstance(learning_outcomes, list):
        raise ValueError("learning_outcomes must be an array")
    if formatting is None or not isinstance(formatting, dict):
        raise ValueError("formatting must be an object")
    if not isinstance(missing_information, list):
        raise ValueError("missing_information must be an array")

    wc_int = _coerce_word_count_value(word_count)
    if word_count is not None and wc_int is None:
        raise ValueError("word_count must be an integer")
    min_sources_int = None
    if minimum_sources is not None:
        if isinstance(minimum_sources, bool):
            raise ValueError("minimum_sources must be an integer")
        if isinstance(minimum_sources, int):
            min_sources_int = minimum_sources
        elif isinstance(minimum_sources, float) and minimum_sources.is_integer():
            min_sources_int = int(minimum_sources)
        elif isinstance(minimum_sources, str):
            stripped = minimum_sources.strip()
            if stripped.isdigit():
                min_sources_int = int(stripped)
        else:
            try:
                min_sources_int = int(minimum_sources)
            except (TypeError, ValueError) as exc:
                raise ValueError("minimum_sources must be an integer") from exc

    normalized_rubric: list[dict[str, str]] = []
    for item in rubric:
        if not isinstance(item, dict):
            continue
        normalized_rubric.append(
            {
                "criterion": str(item.get("criterion") or ""),
                "weight": str(item.get("weight") or ""),
                "description": str(item.get("description") or ""),
            }
        )

    normalized_sections, budgets_from_sections = _normalize_required_sections_with_budgets(required_sections)
    budgets = _coerce_section_word_budgets(section_word_budgets)
    for title, words in budgets_from_sections.items():
        budgets.setdefault(title, words)

    return {
        "assignment_type": str(assignment_type) if assignment_type is not None else None,
        "title": str(title) if title is not None else None,
        "word_count": wc_int,
        "citation_style": str(citation_style) if citation_style is not None else None,
        "required_sections": normalized_sections,
        "section_word_budgets": budgets,
        "rubric": normalized_rubric,
        "learning_outcomes": [str(v) for v in learning_outcomes if str(v).strip()],
        "minimum_sources": min_sources_int,
        "formatting": {
            "font_family": formatting.get("font_family"),
            "font_size": formatting.get("font_size"),
            "line_spacing": formatting.get("line_spacing"),
            "margins": formatting.get("margins"),
            "alignment": formatting.get("alignment"),
        },
        "deadline": str(deadline) if deadline not in (None, "") else None,
        "difficulty": str(difficulty) if difficulty not in (None, "") else None,
        "missing_information": [str(v) for v in missing_information if str(v).strip()],
    }


def _normalize_required_sections_with_budgets(raw_sections: list[Any]) -> tuple[list[str], dict[str, int]]:
    sections: list[str] = []
    budgets: dict[str, int] = {}
    for item in raw_sections:
        value = item
        if isinstance(item, str) and item.strip().startswith("{"):
            try:
                parsed = ast.literal_eval(item)
                if isinstance(parsed, dict):
                    value = parsed
            except (SyntaxError, ValueError):
                value = item
        if isinstance(value, dict):
            title = str(
                value.get("section_name")
                or value.get("section")
                or value.get("title")
                or value.get("name")
                or ""
            ).strip()
            detail = str(value.get("content") or value.get("description") or "").strip()
            text = f"{title}: {detail}" if title and detail else title
            budget_raw = value.get("word_count") or value.get("estimated_words") or value.get("words")
            if budget_raw is not None and title:
                try:
                    budgets[title.split(":", 1)[0].strip()] = int(budget_raw)
                except (TypeError, ValueError):
                    pass
        else:
            text = str(value).strip()
        if not text:
            continue
        short_title, parsed_budget = _parse_section_word_budget(text)
        if parsed_budget is not None and short_title:
            budgets.setdefault(short_title, parsed_budget)
        sections.append(text)
    return sections, budgets


def _normalize_required_sections(raw_sections: list[Any]) -> list[str]:
    sections, _budgets = _normalize_required_sections_with_budgets(raw_sections)
    return sections
