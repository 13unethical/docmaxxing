#!/usr/bin/env python3
"""Capture full-page /check screenshots for three Academic Check scenarios."""

from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots" / "check-preview"
BASE = "http://127.0.0.1:5001/check"
DOCX = ROOT / "tests" / "fixtures" / "test_essay_styled.docx"
BRIEF_FULL = ROOT / "tests" / "fixtures" / "briefs" / "full_requirements.txt"
BRIEF_STYLE = ROOT / "tests" / "fixtures" / "briefs" / "style_and_wordcount_only.txt"


def wait_for_report(page) -> None:
    page.wait_for_selector("#check_results:not(.hidden)", timeout=120_000)
    page.wait_for_function(
        """() => {
          const results = document.getElementById('check_results');
          if (!results || results.classList.contains('hidden')) return false;
          const score = document.getElementById('check_score_panel');
          const low = document.getElementById('check_not_enough_panel');
          const empty = document.getElementById('check_empty_report');
          const scoreVisible = score && !score.classList.contains('hidden');
          const lowVisible = low && !low.classList.contains('hidden');
          const emptyVisible = empty && !empty.classList.contains('hidden');
          return scoreVisible || lowVisible || emptyVisible;
        }""",
        timeout=120_000,
    )
    time.sleep(0.5)


def prepare_page(page) -> None:
    page.goto(BASE, wait_until="networkidle")
    page.evaluate(
        """() => {
          localStorage.setItem('dm-theme', 'light');
          document.documentElement.dataset.theme = 'light';
        }"""
    )
    page.reload(wait_until="networkidle")


def clear_inputs(page) -> None:
    page.fill("#check_requirements", "")
    page.fill("#check_pasted_text", "")
    page.evaluate(
        """() => {
          const req = document.getElementById('check_requirements_file');
          const doc = document.getElementById('check_file');
          if (req) req.value = '';
          if (doc) doc.value = '';
        }"""
    )


def expand_report_sections(page) -> None:
    page.evaluate(
        """() => {
          document.querySelectorAll('details.check-ai-review').forEach(d => { d.open = true; });
        }"""
    )


def run_check(page) -> None:
    page.click("#check_document_btn")
    wait_for_report(page)
    expand_report_sections(page)
    time.sleep(0.3)


def screenshot(page, name: str) -> Path:
    path = OUT / name
    page.screenshot(path=str(path), full_page=True)
    return path


def upload_docx_only(page) -> None:
    page.set_input_files("#check_file", str(DOCX))
    page.fill("#check_pasted_text", "")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        # 1. Full brief + docx (empty textarea)
        prepare_page(page)
        clear_inputs(page)
        page.fill("#check_requirements", BRIEF_FULL.read_text(encoding="utf-8"))
        upload_docx_only(page)
        run_check(page)
        p1 = screenshot(page, "01-full-brief-and-docx.png")
        print("saved", p1)

        # 2. No brief + docx (empty textarea)
        prepare_page(page)
        clear_inputs(page)
        upload_docx_only(page)
        run_check(page)
        p2 = screenshot(page, "02-docx-no-brief.png")
        print("saved", p2)

        # 3. Style-only brief + docx (empty textarea)
        prepare_page(page)
        clear_inputs(page)
        page.fill("#check_requirements", BRIEF_STYLE.read_text(encoding="utf-8"))
        upload_docx_only(page)
        run_check(page)
        p3 = screenshot(page, "03-style-brief-and-docx.png")
        print("saved", p3)

        browser.close()


if __name__ == "__main__":
    main()
