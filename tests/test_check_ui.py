"""Tests for Academic Check report UI (check.html, check.js, check_report.js)."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK_JS = ROOT / "static" / "check.js"
CHECK_REPORT_JS = ROOT / "static" / "check_report.js"
CHECK_HTML = ROOT / "templates" / "check.html"

REMOVED_FIELDS = (
    "data.issues",
    "data.needs_work",
    "data.next_steps",
    "data.priorities",
    "data.summary",
    "data.positives",
    "health_score",
    "pickMainProblems",
    "renderIssues",
    "renderNextSteps",
)


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*?$", "", text, flags=re.M)


def _run_check_report_js(expr: str) -> dict:
    script = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({json.dumps(str(CHECK_REPORT_JS))}, 'utf8');
vm.runInThisContext(code, {{ filename: 'check_report.js' }});
const result = ({expr});
console.log(JSON.stringify(result));
"""
    proc = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout.strip())


def test_no_references_to_removed_response_fields():
    js = _strip_js_comments(CHECK_JS.read_text(encoding="utf-8"))
    for token in REMOVED_FIELDS:
        assert token not in js, f"check.js still references removed field/helper: {token}"


def test_low_coverage_hides_headline_score():
    html = CHECK_HTML.read_text(encoding="utf-8")
    js = CHECK_JS.read_text(encoding="utf-8")
    report = CHECK_REPORT_JS.read_text(encoding="utf-8")

    assert "check_not_enough_panel" in html
    assert "check_score_panel" in html
    assert "resolveLowCoverageState" in js
    assert "COVERAGE_THRESHOLD" in report
    assert "50" in report


def test_low_coverage_states_are_distinct():
    fragment = _run_check_report_js(
        "CheckReport.resolveLowCoverageState({ hasBrief: false, hasDocx: true, wordCount: 23 })"
    )
    no_brief = _run_check_report_js(
        "CheckReport.resolveLowCoverageState({ hasBrief: false, hasDocx: true, wordCount: 150 })"
    )
    no_docx = _run_check_report_js(
        "CheckReport.resolveLowCoverageState({ hasBrief: true, hasDocx: false, wordCount: 150 })"
    )
    assert fragment["kind"] == "fragment"
    assert no_brief["kind"] == "no_brief"
    assert no_docx["kind"] == "no_docx"
    assert "assignment brief" in no_brief["message"].lower()
    assert ".docx" in no_docx["message"].lower()


def test_high_coverage_shows_score_with_coverage():
    html = CHECK_HTML.read_text(encoding="utf-8")
    js = CHECK_JS.read_text(encoding="utf-8")

    assert "check_coverage_line" in html
    assert "formatCoverageLine" in js
    assert "check_document_source" in html
    assert "renderDocumentSource" in js

    line = _run_check_report_js(
        "CheckReport.formatCoverageLine(72, 6, [{id:'formatting'}])"
    )
    assert line == "72 / 100 · based on 6 of 7 checks"


def test_missing_items_sorted_by_points_lost():
    validations = [
        {"id": "word_count", "weight": 25, "points_earned": 2, "points_possible": 25, "status": "FAIL"},
        {"id": "sections", "weight": 20, "points_earned": 10, "points_possible": 20, "status": "PARTIAL"},
        {"id": "references", "weight": 15, "points_earned": 15, "points_possible": 15, "status": "PASS"},
    ]
    payload = json.dumps(validations)
    ordered = _run_check_report_js(
        f"CheckReport.sortMissingValidations({payload}).map(v => v.id)"
    )
    assert ordered == ["word_count", "sections"]


def test_not_checked_items_have_action_buttons():
    html = CHECK_HTML.read_text(encoding="utf-8")
    js = CHECK_JS.read_text(encoding="utf-8")

    assert "check_not_checked_list" in html
    assert "check-not-checked-btn" in js
    assert "notCheckedAction" in js
    assert "upload_docx" in js
    assert "add_brief" in js

    action = _run_check_report_js("CheckReport.notCheckedAction('требуется .docx')")
    assert action["action"] == "upload_docx"
    assert "docx" in action["label"].lower()


def test_detected_requirements_summary_uses_found_of_total():
    js = CHECK_JS.read_text(encoding="utf-8")
    assert "requirements found in your brief" in js
    assert "formatting requirement" not in _strip_js_comments(js)
