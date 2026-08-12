#!/usr/bin/env python3
"""Manual preview: build a FULL document in all five styles → DOCX / PDF / PNG.

Not a test. Requires optional tools:
  - soffice (LibreOffice) for DOCX → PDF
  - pdftoppm (poppler-utils) for PDF → PNG
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from formatter_v2.fixtures.sample_full_document import sample_full_document  # noqa: E402
from formatter_v2.profiles import load_profile  # noqa: E402
from formatter_v2.render.builder import build_document  # noqa: E402
from formatter_v2.resolve import resolve_format_spec  # noqa: E402
from formatter_v2.spec import (  # noqa: E402
    AbbreviationList,
    AppendixConfig,
    CoverPage,
    StyleName,
    TableOfContents,
    UserOverrides,
)

STYLES = (
    StyleName.HARVARD,
    StyleName.APA7,
    StyleName.MLA9,
    StyleName.CHICAGO17,
    StyleName.IEEE,
)


def _preview_overrides(style: StyleName) -> UserOverrides:
    """Turn on every optional part for a rich preview document."""
    return UserOverrides(
        cover_page=CoverPage(
            enabled=style != StyleName.MLA9,
            title="Climate Adaptation in Coastal Cities",
        ),
        table_of_contents=TableOfContents(
            enabled=True,
            max_depth=3,
            heading_text="Table of Contents",
        ),
        abbreviations=AbbreviationList(
            enabled=True,
            heading_text="List of Abbreviations",
            entries={
                "IPCC": "Intergovernmental Panel on Climate Change",
                "SLR": "Sea-Level Rise",
            },
        ),
        appendices=AppendixConfig(
            enabled=True,
            lettered=True,
            page_break_before_each=True,
        ),
    )


def _which(name: str) -> str | None:
    return shutil.which(name)


def _convert_pdf(docx_path: Path, out_dir: Path) -> Path | None:
    soffice = _which("soffice") or _which("libreoffice")
    if not soffice:
        print(
            "skip PDF: LibreOffice not found (install soffice/libreoffice to enable DOCX→PDF).",
            file=sys.stderr,
        )
        return None
    subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(docx_path),
        ],
        check=True,
        capture_output=True,
    )
    pdf = out_dir / (docx_path.stem + ".pdf")
    return pdf if pdf.exists() else None


def _convert_png(pdf_path: Path, out_dir: Path) -> None:
    pdftoppm = _which("pdftoppm")
    if not pdftoppm:
        print(
            "skip PNG: pdftoppm not found (install poppler-utils to enable PDF→PNG).",
            file=sys.stderr,
        )
        return
    prefix = out_dir / pdf_path.stem
    subprocess.run(
        [pdftoppm, "-png", "-r", "150", str(pdf_path), str(prefix)],
        check=True,
        capture_output=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Formatter V2 full-document previews")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "build" / "preview",
        help="Output directory (default: build/preview)",
    )
    parser.add_argument("--no-pdf", action="store_true", help="Skip LibreOffice PDF conversion")
    parser.add_argument("--no-png", action="store_true", help="Skip pdftoppm PNG conversion")
    args = parser.parse_args()

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    for style in STYLES:
        profile = load_profile(style)
        spec = resolve_format_spec(profile, _preview_overrides(style)).spec
        model = sample_full_document(spec)
        doc = build_document(model, spec)
        docx_path = out_dir / f"full_{style.value}.docx"
        doc.save(docx_path)
        print(f"wrote {docx_path}")

        if args.no_pdf:
            continue
        try:
            pdf = _convert_pdf(docx_path, out_dir)
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"skip PDF for {style.value}: {exc}", file=sys.stderr)
            continue
        if pdf is None:
            continue
        print(f"wrote {pdf}")
        if args.no_png:
            continue
        try:
            _convert_png(pdf, out_dir)
            print(f"wrote {pdf.stem}-*.png (if pdftoppm available)")
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"skip PNG for {style.value}: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
