"""Requirement analyzer interface and Gemini implementation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from formatter.document_io import extract_text_from_document_bytes
from services.assignment_pipeline.models import utc_now
from services.assignment_llm import assignment_generate_json, assignment_llm_model
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

    VERSION = assignment_llm_model()
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
            )
            if raw is None:
                last_error = str(diagnostics.get("error_message") or diagnostics.get("failure_reason") or last_error)
                continue
            try:
                normalized = _normalize_requirement_json(raw)
            except ValueError as exc:
                last_error = str(exc)
                continue
            return RequirementJSON(
                id=base.id,
                project_id=base.project_id,
                assignment_type=normalized.get("assignment_type"),
                title=normalized.get("title"),
                word_count=normalized.get("word_count"),
                citation_style=normalized.get("citation_style"),
                required_sections=normalized.get("required_sections", []),
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
        "required_sections, rubric, learning_outcomes, minimum_sources, formatting, deadline, "
        "difficulty, missing_information. "
        "word_count and minimum_sources must be integers or null; never use descriptive text for them. "
        "If the count is unknown, set the field to null and mention it in missing_information. "
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
    return normalized[:4000] if normalized else "(empty file content)"


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

    wc_int = None
    if word_count is not None:
        try:
            wc_int = int(word_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("word_count must be an integer") from exc
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

    return {
        "assignment_type": str(assignment_type) if assignment_type is not None else None,
        "title": str(title) if title is not None else None,
        "word_count": wc_int,
        "citation_style": str(citation_style) if citation_style is not None else None,
        "required_sections": [str(v) for v in required_sections if str(v).strip()],
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
