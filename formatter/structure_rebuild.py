"""
Rebuild a Word document from AI / heuristic structure recovery output.

Inserts section headings and restores paragraph boundaries before formatting.
Returns per-paragraph heading assignments that are the source of truth for AI levels.
"""

from __future__ import annotations

from docx import Document

from formatter.heading_plan import ParagraphHeadingAssignment, StructureApplyResult
from formatter.headings import normalize_paragraph_text, split_embedded_heading_paragraph


def _clear_document_body(doc: Document) -> None:
    body = doc.element.body
    for child in list(body):
        body.remove(child)


def _node_heading_level(node: dict) -> int:
    raw = node.get("level")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return max(1, min(3, raw))
    if isinstance(raw, float):
        return max(1, min(3, int(raw)))
    title = str(node.get("title") or "").strip().lower()
    return 1 if title == "title" else 2


def _node_confidence(node: dict) -> float | None:
    try:
        return float(node.get("confidence"))
    except (TypeError, ValueError):
        return None


def _assignment_source(node: dict) -> str:
    src = str(node.get("source") or "").strip().lower()
    if src in {"ai", "ai_inferred"}:
        return "ai"
    return src or "none"


def rebuild_document_from_recovery(doc: Document, recovery: dict) -> StructureApplyResult | None:
    """
    Replace document paragraphs with structure-aware content and return heading assignments
    aligned to the rebuilt paragraph list (one entry per paragraph).
    """
    paragraphs: list[str] = list(recovery.get("paragraphs") or [])
    structure_tree: list[dict] = list(recovery.get("structure_tree") or [])
    if not paragraphs or not structure_tree:
        return None

    ai_powered = bool(recovery.get("ai_powered"))
    recovery_mode = str(recovery.get("recovery_mode") or "")

    used: set[int] = set()
    ordered_blocks: list[dict[str, int | str | float | None]] = []

    for node in structure_tree:
        indices = node.get("paragraph_indices") or []
        heading_text = (node.get("heading_text") or node.get("title") or "").strip()
        title_norm = normalize_paragraph_text(node.get("title") or "")
        insert_heading = bool(
            node.get(
                "insert_heading",
                title_norm not in {"title", "preamble"},
            )
        )
        skip_first: int | None = None
        synthetic_heading_inserted = False
        node_level = _node_heading_level(node)
        is_ai_node = ai_powered and _assignment_source(node) == "ai"

        first_idx: int | None = None
        for raw in indices:
            try:
                first_idx = int(raw)
                break
            except (TypeError, ValueError):
                continue
        first_matches_heading = (
            first_idx is not None
            and 1 <= first_idx <= len(paragraphs)
            and heading_text
            and normalize_paragraph_text(paragraphs[first_idx - 1])
            == normalize_paragraph_text(heading_text)
        )

        if insert_heading and heading_text and title_norm not in {"title", "preamble"}:
            if first_matches_heading:
                ordered_blocks.append(
                    {
                        "kind": "heading",
                        "text": paragraphs[first_idx - 1].strip(),
                        "level": node_level if is_ai_node else None,
                        "source": "ai" if is_ai_node else "none",
                        "confidence": _node_confidence(node) if is_ai_node else None,
                    }
                )
                skip_first = first_idx
            else:
                ordered_blocks.append(
                    {
                        "kind": "heading",
                        "text": heading_text,
                        "level": node_level if is_ai_node else None,
                        "source": "ai" if is_ai_node else "none",
                        "confidence": _node_confidence(node) if is_ai_node else None,
                    }
                )
                synthetic_heading_inserted = True
        elif (
            first_matches_heading
            and title_norm not in {"title", "preamble"}
            and first_idx is not None
        ):
            ordered_blocks.append(
                {
                    "kind": "heading",
                    "text": paragraphs[first_idx - 1].strip(),
                    "level": node_level if is_ai_node else None,
                    "source": "ai" if is_ai_node else "none",
                    "confidence": _node_confidence(node) if is_ai_node else None,
                }
            )
            skip_first = first_idx

        for idx in indices:
            try:
                pi = int(idx)
            except (TypeError, ValueError):
                continue
            if pi < 1 or pi > len(paragraphs) or pi in used:
                continue
            if skip_first is not None and pi == skip_first:
                used.add(pi)
                continue
            used.add(pi)
            text = paragraphs[pi - 1].strip()
            if not text:
                continue
            heading_part, body_part = split_embedded_heading_paragraph(text)
            if heading_part and body_part:
                if synthetic_heading_inserted:
                    text = body_part
                elif skip_first is None or pi != skip_first:
                    ordered_blocks.append(
                        {
                            "kind": "heading",
                            "text": heading_part,
                            "level": node_level if is_ai_node else None,
                            "source": "ai" if is_ai_node else "none",
                            "confidence": _node_confidence(node) if is_ai_node else None,
                        }
                    )
                    text = body_part
            is_title_para = False
            if title_norm in {"title", "preamble"} and indices:
                try:
                    is_title_para = pi == int(indices[0])
                except (TypeError, ValueError):
                    is_title_para = False
            if is_ai_node and is_title_para:
                ordered_blocks.append(
                    {
                        "kind": "body",
                        "text": text,
                        "level": node_level,
                        "source": "ai",
                        "confidence": _node_confidence(node),
                    }
                )
            else:
                ordered_blocks.append(
                    {
                        "kind": "body",
                        "text": text,
                        "level": None,
                        "source": "none",
                        "confidence": None,
                    }
                )

    for idx, text in enumerate(paragraphs, start=1):
        if idx not in used and text.strip():
            ordered_blocks.append(
                {
                    "kind": "body",
                    "text": text.strip(),
                    "level": None,
                    "source": "none",
                    "confidence": None,
                }
            )

    _clear_document_body(doc)
    assignments: list[ParagraphHeadingAssignment] = []
    for block in ordered_blocks:
        text = str(block.get("text") or "")
        level_raw = block.get("level")
        level = int(level_raw) if isinstance(level_raw, int) else None
        source = str(block.get("source") or "none")
        conf_raw = block.get("confidence")
        confidence = float(conf_raw) if isinstance(conf_raw, (int, float)) else None
        doc.add_paragraph(text)
        assignments.append(
            ParagraphHeadingAssignment(
                text=text,
                level=level,
                source=source,
                confidence=confidence,
            )
        )

    return StructureApplyResult(
        assignments=assignments,
        recovery_mode=recovery_mode,
        ai_powered=ai_powered,
    )
