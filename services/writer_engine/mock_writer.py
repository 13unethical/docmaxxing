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
        return (
            f"{prefix}## {section.title}\n\n"
            f"Section objective: {section.objective}\n"
            f"Topic context: {topic}\n\n"
            f"Planned coverage ({section.estimated_words} words target):\n"
            f"{bullets}\n\n"
            f"[Mock section output — generated in isolation for {section.title} only. "
            f"Claude Opus will replace this stub with full prose.]"
        )


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
