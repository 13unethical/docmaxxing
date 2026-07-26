"""Mock section writer — replace with Claude Opus later."""

from __future__ import annotations

from typing import Any, Protocol

from services.writer_engine.models import WriterEngineInput, WriterSection


class SectionWriter(Protocol):
    def write_section(
        self,
        *,
        section: WriterSection,
        payload: WriterEngineInput,
        revision: bool = False,
    ) -> str:
        ...


class MockSectionWriter:
    VERSION = "mock-1.0"

    def write_section(
        self,
        *,
        section: WriterSection,
        payload: WriterEngineInput,
        revision: bool = False,
    ) -> str:
        blueprint_section = _blueprint_section(payload.blueprint, section.id)
        key_points = blueprint_section.get("key_points") or []
        topic = _topic(payload)
        prefix = "[REVISED] " if revision else ""
        bullets = "\n".join(f"- {point}" for point in key_points) or "- Core argument development"
        target = max(40, int(section.estimated_words or 80))
        filler = (
            f"This mock paragraph develops the academic argument for {section.title} "
            f"within the assignment topic of {topic}. "
        )
        body_parts = [
            f"Section objective: {section.objective}",
            f"Topic context: {topic}",
            f"Planned coverage ({target} words target):",
            bullets,
            filler * max(1, target // 20),
        ]
        body = "\n\n".join(body_parts)
        words = body.split()
        if len(words) < target:
            pad = "Additional analytical detail supports the required word budget. "
            while len(body.split()) < target:
                body = body + " " + pad
        elif len(words) > int(target * 1.1) + 5:
            body = " ".join(words[: max(target, int(target * 1.1))])
        return f"{prefix}{body.strip()}"


def _topic(payload: WriterEngineInput) -> str:
    req = payload.requirement_json
    plan = payload.research_plan
    return str(
        req.get("title")
        or plan.get("assignment_topic")
        or req.get("assignment_type")
        or "Assignment"
    )


def _blueprint_section(blueprint: dict[str, Any], section_id: str) -> dict[str, Any]:
    for item in blueprint.get("sections") or []:
        if item.get("id") == section_id:
            return item
    return {}
