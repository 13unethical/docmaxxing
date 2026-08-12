#!/usr/bin/env python3
"""Audit Formatter V2 structure extraction on real documents.

Not a test — writes human-readable reports under ``build/audit/``.
Do not commit audit outputs.

Usage:
  PYTHONPATH=. python3 scripts/audit_real_documents.py
  PYTHONPATH=. python3 scripts/audit_real_documents.py path/to/folder
  PYTHONPATH=. python3 scripts/audit_real_documents.py --input samples/real --out build/audit
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from formatter_v2.pipeline import select_extractor  # noqa: E402
from formatter_v2.profiles import load_profile  # noqa: E402
from formatter_v2.render.builder import build_document  # noqa: E402
from formatter_v2.render.document import Block  # noqa: E402
from formatter_v2.render.model import DocumentModel  # noqa: E402
from formatter_v2.resolve import resolve_format_spec  # noqa: E402
from formatter_v2.spec import ParagraphRole, StyleName, UserOverrides  # noqa: E402
from formatter_v2.structure.references import is_references_heading  # noqa: E402

STYLES: tuple[StyleName, ...] = (
    StyleName.HARVARD,
    StyleName.APA7,
    StyleName.MLA9,
    StyleName.CHICAGO17,
    StyleName.IEEE,
)

_HEADING_ROLES = frozenset(
    {
        ParagraphRole.HEADING_1,
        ParagraphRole.HEADING_2,
        ParagraphRole.HEADING_3,
        ParagraphRole.HEADING_4,
    }
)

_YEAR_IN_PARENS_RE = re.compile(r"\(\s*(?:19|20)\d{2}[a-z]?\s*\)")

_INPUT_SUFFIXES = {".docx", ".txt"}


@dataclass
class FileAudit:
    path: Path
    extractor_name: str
    total_paragraphs: int
    role_counts: Counter[str]
    body_share: float
    refs_latched: bool
    refs_heading_text: str | None
    notices_by_style: dict[str, int] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    model: DocumentModel | None = None


def _load_source(path: Path) -> object:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return path
    if suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace")
        return [line for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    raise ValueError(f"Unsupported file type: {path}")


def _iter_blocks(model: DocumentModel) -> list[Block]:
    blocks: list[Block] = []
    if model.cover is not None and model.cover.title:
        blocks.append(Block(ParagraphRole.COVER_TITLE, model.cover.title))
    blocks.extend(model.front_matter)
    blocks.extend(model.body)
    blocks.extend(model.references)
    blocks.extend(model.appendices)
    return blocks


def _block_plain_text(block: Block) -> str:
    if isinstance(block.text, str):
        return block.text
    return str(block.text)


def _role_counts(blocks: list[Block]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for block in blocks:
        counts[block.role.value] += 1
    return counts


def _refs_heading(model: DocumentModel) -> str | None:
    for block in model.references:
        if block.role == ParagraphRole.REFERENCES_HEADING:
            text = _block_plain_text(block).strip()
            return text or "(empty heading)"
    return None


def _detect_flags(
    *,
    blocks: list[Block],
    role_counts: Counter[str],
    body_share: float,
) -> list[str]:
    flags: list[str] = []
    total = len(blocks)

    if total > 0 and body_share > 0.95:
        flags.append("body_gt_95pct")

    if not any(role_counts.get(r.value, 0) for r in _HEADING_ROLES):
        flags.append("no_headings")

    has_ref_entries = role_counts.get(ParagraphRole.REFERENCES_ENTRY.value, 0) > 0
    all_text = "\n".join(_block_plain_text(b) for b in blocks)
    has_year_cite = bool(_YEAR_IN_PARENS_RE.search(all_text))
    has_refs_line = any(is_references_heading(_block_plain_text(b)) for b in blocks)
    if not has_ref_entries and (has_year_cite or has_refs_line):
        flags.append("refs_not_latched")

    body_like = [
        b
        for b in blocks
        if b.role in {ParagraphRole.BODY, ParagraphRole.BODY_FIRST}
    ]
    if body_like:
        short = sum(1 for b in body_like if len(_block_plain_text(b).strip()) < 50)
        if short / len(body_like) > 0.30:
            flags.append("many_short_paras")

    if role_counts.get(ParagraphRole.DOC_TITLE.value, 0) > 1:
        flags.append("multiple_doc_title")

    if total > 0:
        list_n = role_counts.get(ParagraphRole.LIST_BULLET.value, 0) + role_counts.get(
            ParagraphRole.LIST_NUMBER.value, 0
        )
        if list_n / total > 0.25:
            flags.append("list_heavy")

        heading_n = sum(role_counts.get(r.value, 0) for r in _HEADING_ROLES)
        body_like_n = role_counts.get(ParagraphRole.BODY.value, 0) + role_counts.get(
            ParagraphRole.BODY_FIRST.value, 0
        )
        # One heading per body paragraph (or worse) on a non-tiny doc → broken markup.
        if total > 20 and heading_n >= body_like_n:
            flags.append("implausible_headings")

    return flags


def audit_file(path: Path, out_root: Path) -> FileAudit:
    source = _load_source(path)
    extractor, extractor_name, document = select_extractor(source)
    if document is not None:
        model = extractor.extract(document)
    else:
        model = extractor.extract(source)

    blocks = _iter_blocks(model)
    role_counts = _role_counts(blocks)
    total = len(blocks)
    body_n = role_counts.get(ParagraphRole.BODY.value, 0) + role_counts.get(
        ParagraphRole.BODY_FIRST.value, 0
    )
    body_share = (body_n / total) if total else 0.0
    refs_heading = _refs_heading(model)
    flags = _detect_flags(blocks=blocks, role_counts=role_counts, body_share=body_share)

    notices_by_style: dict[str, int] = {}
    stem_dir = out_root / _safe_stem(path)

    extraction_notice_count = 0
    if extractor_name == "word_styles":
        from formatter_v2.structure.from_word_styles import implausible_heading_notices

        extraction_notice_count += len(implausible_heading_notices(model))
    from formatter_v2.structure.numbered import numbered_section_notices

    extraction_notice_count += len(numbered_section_notices(model))

    for style in STYLES:
        profile = load_profile(style)
        resolution = resolve_format_spec(profile, UserOverrides())
        notices_by_style[style.value] = len(resolution.notices) + extraction_notice_count
        if flags:
            built = build_document(model, resolution.spec)
            stem_dir.mkdir(parents=True, exist_ok=True)
            built.save(str(stem_dir / f"{style.value}.docx"))

    return FileAudit(
        path=path,
        extractor_name=extractor_name,
        total_paragraphs=total,
        role_counts=role_counts,
        body_share=body_share,
        refs_latched=refs_heading is not None,
        refs_heading_text=refs_heading,
        notices_by_style=notices_by_style,
        flags=flags,
        model=model,
    )


def _safe_stem(path: Path) -> str:
    return re.sub(r"[^\w.\-]+", "_", path.stem).strip("._") or "document"


def _format_role_distribution(counts: Counter[str]) -> str:
    if not counts:
        return "—"
    parts = [f"{role}={n}" for role, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return ", ".join(parts)


def _format_notices(notices_by_style: dict[str, int]) -> str:
    return ", ".join(f"{k}:{v}" for k, v in notices_by_style.items())


def write_report(audits: list[FileAudit], report_path: Path) -> None:
    lines: list[str] = [
        "# Formatter V2 — real-document audit",
        "",
        f"Files audited: **{len(audits)}**",
        "",
        "| File | Extractor | Paras | Body % | Refs latch | Notices/style | Role distribution | Flags |",
        "| --- | --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    for a in audits:
        refs = (
            f"yes («{a.refs_heading_text}»)"
            if a.refs_latched and a.refs_heading_text
            else ("yes" if a.refs_latched else "no")
        )
        flags = ", ".join(a.flags) if a.flags else "—"
        lines.append(
            "| {file} | {ext} | {total} | {body:.0%} | {refs} | {notices} | {roles} | {flags} |".format(
                file=a.path.name,
                ext=a.extractor_name,
                total=a.total_paragraphs,
                body=a.body_share,
                refs=refs.replace("|", "/"),
                notices=_format_notices(a.notices_by_style),
                roles=_format_role_distribution(a.role_counts).replace("|", "/"),
                flags=flags,
            )
        )

    flagged = [a for a in audits if a.flags]
    lines.extend(
        [
            "",
            "## Flag legend",
            "",
            "- `body_gt_95pct` — BODY(+BODY_FIRST) share > 95%; structure barely recognised",
            "- `no_headings` — no HEADING_1..4 at all",
            "- `refs_not_latched` — no REFERENCES_ENTRY, but year-in-parentheses cites or a References-like line present",
            "- `many_short_paras` — >30% of BODY/BODY_FIRST paragraphs shorter than 50 characters",
            "- `multiple_doc_title` — DOC_TITLE appears more than once",
            "- `list_heavy` — LIST_BULLET+LIST_NUMBER share > 25%",
            "- `implausible_headings` — doc has >20 paragraphs and heading count ≥ BODY(+BODY_FIRST)",
            "",
            f"## Summary: {len(audits) - len(flagged)} clean, {len(flagged)} flagged",
            "",
        ]
    )
    if flagged:
        lines.append("Flagged files (DOCX previews written under each stem folder):")
        lines.append("")
        for a in flagged:
            lines.append(f"- `{a.path.name}` → `{_safe_stem(a.path)}/` — {', '.join(a.flags)}")
        lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_console_summary(audits: list[FileAudit]) -> None:
    flagged = [a for a in audits if a.flags]
    clean = len(audits) - len(flagged)
    flag_freq: Counter[str] = Counter()
    for a in flagged:
        flag_freq.update(a.flags)

    print()
    print("=== Audit summary ===")
    print(f"Files: {len(audits)}  |  clean: {clean}  |  flagged: {len(flagged)}")
    if flag_freq:
        print("Most common flags:")
        for name, n in flag_freq.most_common():
            print(f"  {name}: {n}")
    else:
        print("No suspicion flags.")
    print()


def _discover_inputs(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    files = [
        p
        for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix.lower() in _INPUT_SUFFIXES and not p.name.startswith(".")
    ]
    return files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Formatter V2 on real .docx/.txt documents (not a test)."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=ROOT / "samples" / "real",
        help="Folder with .docx / .txt (default: samples/real/)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "build" / "audit",
        help="Output directory (default: build/audit)",
    )
    args = parser.parse_args()
    input_dir: Path = args.input
    out_dir: Path = args.out

    if not input_dir.exists():
        print(f"Input folder not found: {input_dir}", file=sys.stderr)
        print("Create it and drop .docx / .txt files there.", file=sys.stderr)
        return 1

    files = _discover_inputs(input_dir)
    if not files:
        print(f"No .docx or .txt files in {input_dir}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    audits: list[FileAudit] = []
    for path in files:
        print(f"Auditing {path.name} …")
        try:
            audits.append(audit_file(path, out_dir))
        except Exception as exc:  # noqa: BLE001 — keep going across files
            print(f"  ERROR: {exc}", file=sys.stderr)

    if not audits:
        print("No files audited successfully.", file=sys.stderr)
        return 1

    report_path = out_dir / "report.md"
    write_report(audits, report_path)
    print(f"Wrote {report_path}")
    print_console_summary(audits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
