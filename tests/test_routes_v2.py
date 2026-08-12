"""Routes and API contracts for Formatter V2 UI."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from formatter_v2.resolve import ResolutionNotice
from formatter_v2.spec import UserOverrides
from formatter_v2.web_api import (
    encode_notices_header,
    parse_user_overrides_from_form,
)


def _client():
    from app import app
    from formatter_v2.document_store import reset_document_store

    app.config["TESTING"] = True
    reset_document_store(root=Path(tempfile.mkdtemp()))
    return app.test_client()


def _download_docx(client, document_id: str):
    return client.get(f"/api/format-v2/download/{document_id}")


def _extract_sync_style_chip_selection(js: str) -> str:
    match = re.search(
        r"function syncStyleChipSelection\(style\) \{[\s\S]*?\n  \}",
        js,
    )
    assert match, "syncStyleChipSelection must exist in format_v2.js"
    return match.group(0)


def _js_path() -> Path:
    return Path(__file__).resolve().parents[1] / "static" / "format_v2.js"


def _read_js() -> str:
    return _js_path().read_text(encoding="utf-8")


def test_format_v2_page_404_when_flag_disabled() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "0"}, clear=False):
        res = _client().get("/format-v2")
        assert res.status_code == 404


def test_format_v2_page_renders_when_flag_enabled() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        res = _client().get("/format-v2")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "Harvard (Cite Them Right)" in html
        assert "Your document" in html
        assert "Citation &amp; layout style" in html
        assert ">Format</button>" in html
        assert "format_v2.js" in html


def test_home_format_tab_uses_v2_when_flag_enabled() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        res = _client().get("/")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "format_v2.js" in html
        assert "Harvard (Cite Them Right)" in html
        assert 'id="format_btn"' not in html


def test_home_format_tab_uses_v1_when_flag_disabled() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "0"}, clear=False):
        res = _client().get("/")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "format_v2.js" not in html
        assert 'id="format_btn"' in html


def test_form_has_single_style_control() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        html = _client().get("/format-v2").get_data(as_text=True)
    assert html.count('data-v2-style-control') == 1
    assert html.count('data-v2-style="harvard"') == 1
    assert html.count('data-v2-style="apa7"') == 1
    assert html.count('data-v2-style="mla9"') == 1
    assert html.count('data-v2-style="chicago17"') == 1
    assert html.count('data-v2-style="ieee"') == 1


def test_no_separate_citation_style_in_main_form() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        html = _client().get("/format-v2").get_data(as_text=True)
    assert "citation_style_format" not in html
    assert "citation_style_citations" not in html
    main, _sep, expert = html.partition('id="v2-style-settings"')
    assert 'id="v2_citation_style_override"' not in main
    assert 'id="v2_citation_style_override"' in expert


def test_all_five_styles_present_including_chicago_and_ieee() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        html = _client().get("/format-v2").get_data(as_text=True)
    for label in (
        "Harvard",
        "APA 7",
        "MLA 9",
        "Chicago 17",
        "IEEE",
        "Cite Them Right",
    ):
        assert label in html
    for style in ("harvard", "apa7", "mla9", "chicago17", "ieee"):
        assert f'data-v2-style="{style}"' in html


def test_style_change_fetches_profile_defaults() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        html = _client().get("/format-v2").get_data(as_text=True)
        client = _client()
        for style in ("harvard", "apa7", "mla9", "chicago17", "ieee"):
            res = client.get(f"/api/format-v2/profile/{style}")
            assert res.status_code == 200, style
            data = res.get_json()
            assert "form" in data
            assert "font_family" in data["form"]
    assert "/api/format-v2/profile/" in html or "format_v2.js" in html
    js_path = Path(__file__).resolve().parents[1] / "static" / "format_v2.js"
    js = js_path.read_text(encoding="utf-8")
    assert 'fetch("/api/format-v2/profile/"' in js
    assert "applyFormDefaults" in js


def test_untouched_fields_absent_from_overrides() -> None:
    """Empty / omitted overrides JSON must resolve to an empty UserOverrides."""
    assert parse_user_overrides_from_form({}).model_dump(exclude_none=True) == {}
    assert parse_user_overrides_from_form({"overrides": ""}).model_dump(exclude_none=True) == {}
    assert parse_user_overrides_from_form({"overrides": "{}"}).model_dump(exclude_none=True) == {}

    import formatter_v2.pipeline as pipeline_mod

    captured: list[UserOverrides] = []
    real_fmt = pipeline_mod.format_document_v2

    def _capture(source, overrides, style):
        captured.append(overrides)
        return real_fmt(source, overrides, style)

    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        with patch.object(pipeline_mod, "format_document_v2", side_effect=_capture):
            res = _client().post(
                "/api/format-v2",
                data={
                    "pasted_text": "Introduction\n\nBody paragraph about coastal risk.\n",
                    "format_style": "harvard",
                },
            )
    assert res.status_code == 200
    assert captured
    assert captured[0].model_dump(exclude_none=True) == {}


def test_heading_size_not_in_default_visible_fields() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        html = _client().get("/format-v2").get_data(as_text=True)
    assert 'id="v2_heading_size_pt"' in html
    assert 'value="">— profile default —</option>' in html
    main, _sep, style_settings = html.partition('id="v2-style-settings"')
    assert "heading_size" not in main.lower()
    assert "v2_heading_size_pt" in style_settings
    assert 'id="heading_size_pt"' not in html


def test_profile_endpoint_returns_all_five_styles() -> None:
    styles = ("harvard", "apa7", "mla9", "chicago17", "ieee")
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        client = _client()
        for style in styles:
            res = client.get(f"/api/format-v2/profile/{style}")
            assert res.status_code == 200, style
            data = res.get_json()
            assert data["name"] == style
            assert "form" in data
            assert "font_family" in data["form"]
            assert "profile" in data
        harvard = client.get("/api/format-v2/profile/harvard").get_json()
        assert harvard["display_name"] == "Harvard (Cite Them Right)"


def test_profile_endpoint_returns_line_spacing_for_all_styles() -> None:
    styles = ("harvard", "apa7", "mla9", "chicago17", "ieee")
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        client = _client()
        for style in styles:
            data = client.get(f"/api/format-v2/profile/{style}").get_json()
            spacing = data["form"]["line_spacing"]
            assert spacing > 0, style
            assert spacing in (1.0, 1.5, 2.0), style


def test_apa_profile_line_spacing_is_two() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        data = _client().get("/api/format-v2/profile/apa7").get_json()
    assert data["form"]["line_spacing"] == 2.0
    assert data["form"]["page_size"] == "a4"


def test_profile_page_sizes_default_to_a4_except_ieee() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        client = _client()
        for style in ("harvard", "apa7", "mla9", "chicago17"):
            data = client.get(f"/api/format-v2/profile/{style}").get_json()
            assert data["form"]["page_size"] == "a4", style
        ieee = client.get("/api/format-v2/profile/ieee").get_json()
        assert ieee["form"]["page_size"] == "letter"


def test_profile_cover_title_not_prefilled_with_assignment() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        for style in ("harvard", "apa7"):
            data = _client().get(f"/api/format-v2/profile/{style}").get_json()
            assert data["form"]["cover_page"]["title"] == "", style


def test_format_v2_ui_has_compact_advanced_rows() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        html = _client().get("/format-v2").get_data(as_text=True)
    assert "Advanced" in html
    assert "Дополнительно — свёрнуто" not in html
    assert 'placeholder="Paper title"' in html
    assert 'class="v2-advanced-row"' in html


def test_extract_requirements_v2_returns_overrides_and_evidence() -> None:
    mock_extracted = MagicMock()
    mock_extracted.style = None
    mock_extracted.warnings = []
    mock_extracted.unsupported = []

    prefill = MagicMock()
    prefill.overrides = UserOverrides(font_size_pt=12, line_spacing=2.0)
    prefill.evidence_by_field = {
        "font_size_pt": "12 pt",
        "line_spacing": "double (2.0)",
    }

    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        with (
            patch(
                "formatter_v2.smartform.extract_requirements",
                return_value=mock_extracted,
            ),
            patch(
                "formatter_v2.smartform.to_user_overrides",
                return_value=prefill,
            ),
        ):
            res = _client().post(
                "/api/extract-requirements-v2",
                data={
                    "requirements_text": (
                        "Font: Times New Roman, 12 pt.\nLine spacing: double."
                    ),
                    "format_style": "apa7",
                },
            )

    assert res.status_code == 200
    data = res.get_json()
    assert data["overrides"]["font_size_pt"] == 12
    assert data["overrides"]["line_spacing"] == 2.0
    assert data["evidence_by_field"]["font_size_pt"] == "12 pt"
    assert "line_spacing" in data["evidence_by_field"]


def test_untouched_form_fields_are_not_sent_as_overrides() -> None:
    test_untouched_fields_absent_from_overrides()


def test_notices_reach_the_client() -> None:
    client = _client()
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        res = client.post(
            "/api/format-v2",
            data={
                "pasted_text": "Introduction\n\nBody about sensors and margins.\n",
                "format_style": "ieee",
                "overrides": json.dumps(
                    {
                        "margins": {
                            "top_in": 1.5,
                            "bottom_in": 1.5,
                            "left_in": 1.5,
                            "right_in": 1.5,
                        }
                    }
                ),
            },
        )
    assert res.status_code == 200
    assert res.is_json
    data = res.get_json()
    assert data["notices"]
    assert any(n.get("field") == "margins" for n in data["notices"])
    assert any(n.get("severity") == "deviation" for n in data["notices"])
    doc = _download_docx(client, data["document_id"])
    assert doc.status_code == 200
    assert doc.data[:2] == b"PK"


def test_encode_notices_header_roundtrip_unicode() -> None:
    original = [
        ResolutionNotice(
            field="alignment",
            severity="deviation",
            message="APA 7 предписывает выравнивание по левому краю.",
        )
    ]
    encoded = encode_notices_header(original)
    assert encoded.isascii()
    from formatter_v2.web_api import decode_notices_header

    decoded = decode_notices_header(encoded)
    assert decoded[0]["message"] == original[0].message


def test_chat_response_includes_summary_for_successful_edit() -> None:
    from formatter_v2.pipeline import FormatV2Result

    client = _client()
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        with (
            patch(
                "formatter_v2.chat.apply.apply_chat_edit",
                return_value=(
                    UserOverrides(line_spacing=1.5),
                    "line spacing 2.0 → 1.5",
                    [],
                ),
            ),
            patch(
                "formatter_v2.pipeline.format_document_v2",
                return_value=FormatV2Result(
                    docx_bytes=b"PK\x03\x04fake",
                    notices=[],
                    extractor_name="word_styles",
                ),
            ),
        ):
            res = client.post(
                "/api/format-v2/chat",
                data={
                    "pasted_text": "Introduction\n\nBody text.\n",
                    "format_style": "apa7",
                    "message": "Сделай интервал 1.5",
                    "overrides": "{}",
                },
            )
    assert res.status_code == 200
    assert res.is_json
    data = res.get_json()
    assert data["summary"] == "line spacing 2.0 → 1.5"
    assert data["overrides"]["line_spacing"] == 1.5
    doc = _download_docx(client, data["document_id"])
    assert doc.status_code == 200
    assert doc.data == b"PK\x03\x04fake"


def test_chat_response_includes_rejection_text() -> None:
    from formatter_v2.chat.apply import RejectedItem
    from formatter_v2.pipeline import FormatV2Result

    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        with (
            patch(
                "formatter_v2.chat.apply.apply_chat_edit",
                return_value=(
                    UserOverrides(),
                    "",
                    [RejectedItem(request="сделай красиво", reason="неконкретный запрос")],
                ),
            ),
            patch(
                "formatter_v2.pipeline.format_document_v2",
                return_value=FormatV2Result(
                    docx_bytes=b"PK\x03\x04fake",
                    notices=[],
                    extractor_name="word_styles",
                ),
            ),
        ):
            res = _client().post(
                "/api/format-v2/chat",
                data={
                    "pasted_text": "Introduction\n\nBody text.\n",
                    "format_style": "harvard",
                    "message": "Сделай красиво",
                    "overrides": "{}",
                },
            )
    assert res.status_code == 200
    assert res.is_json
    rejected = res.get_json()["rejected"]
    assert rejected
    assert rejected[0]["request"] == "сделай красиво"
    assert "неконкретный" in rejected[0]["reason"]


def test_response_metadata_survives_cyrillic_without_encoding() -> None:
    from formatter_v2.pipeline import FormatV2Result
    from formatter_v2.resolve import ResolutionNotice

    client = _client()
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        with (
            patch(
                "formatter_v2.chat.apply.apply_chat_edit",
                return_value=(
                    UserOverrides(line_spacing=1.5),
                    "line spacing 2.0 → 1.5",
                    [],
                ),
            ),
            patch(
                "formatter_v2.pipeline.format_document_v2",
                return_value=FormatV2Result(
                    docx_bytes=b"PK\x03\x04fake",
                    notices=[
                        ResolutionNotice(
                            field="line_spacing",
                            severity="info",
                            message="Harvard uses 1.5 spacing by default.",
                        )
                    ],
                    extractor_name="word_styles",
                ),
            ),
        ):
            res = client.post(
                "/api/format-v2/chat",
                data={
                    "pasted_text": "Introduction\n\nBody text.\n",
                    "format_style": "harvard",
                    "message": "сделай интервал 1.5",
                    "overrides": "{}",
                },
            )
    assert res.status_code == 200
    assert res.is_json
    data = res.get_json()
    assert data["summary"] == "line spacing 2.0 → 1.5"
    assert "1.5 spacing" in data["notices"][0]["message"]
    assert res.headers.get("X-Format-Chat-Summary") is None
    assert res.headers.get("X-Format-Notices") is None
    doc = _download_docx(client, data["document_id"])
    assert doc.status_code == 200
    assert doc.data == b"PK\x03\x04fake"


def test_chat_history_element_present_after_formatting() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        html = _client().get("/format-v2").get_data(as_text=True)
    assert 'id="v2_chat_history"' in html
    assert 'id="v2_chat_history_wrap"' in html
    assert "Edit history" in html
    panel_start = html.index('id="v2_chat_panel"')
    panel_html = html[panel_start:]
    assert 'id="v2_chat_history_wrap"' in panel_html
    assert 'id="v2_chat_history_empty"' in panel_html


def test_format_v2_init_defines_dom_helper_before_use() -> None:
    js = _read_js()
    assert re.search(r"function\s+\$\s*\(", js)
    assert js.index("function $(") < js.index("function init()")
    assert "[format-v2] init failed:" in js


def test_style_chip_selection_is_exclusive() -> None:
    if shutil.which("node") is None:
        import pytest

        pytest.skip("node is required for JS chip selection test")

    js = _read_js()
    fn = _extract_sync_style_chip_selection(js)
    script = """
const buttons = [
  { style: "harvard", active: true },
  { style: "chicago17", active: true },
  { style: "apa7", active: false },
];
const document = {
  querySelectorAll() {
    return buttons.map(function (b) {
      return {
        getAttribute(name) {
          return name === "data-v2-style" ? b.style : null;
        },
        classList: {
          toggle(cls, on) {
            if (cls === "is-active") b.active = !!on;
          },
        },
      };
    });
  },
};
""" + fn + """
syncStyleChipSelection("chicago17");
const active = buttons.filter(function (b) { return b.active; }).map(function (b) { return b.style; });
if (active.length !== 1 || active[0] !== "chicago17") {
  console.error(JSON.stringify({ active: active }));
  process.exit(2);
}
"""
    proc = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_format_v2_response_is_json_with_document_id() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        res = _client().post(
            "/api/format-v2",
            data={
                "pasted_text": "Introduction\n\nBody paragraph about coastal risk.\n",
                "format_style": "harvard",
            },
        )
    assert res.status_code == 200
    assert res.is_json
    data = res.get_json()
    assert isinstance(data.get("document_id"), str)
    assert data["document_id"]
    assert "summary" in data
    assert "rejected" in data
    assert "notices" in data
    assert "overrides" in data


def test_download_endpoint_returns_docx_for_valid_id() -> None:
    client = _client()
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        res = client.post(
            "/api/format-v2",
            data={
                "pasted_text": "Introduction\n\nBody paragraph about sensors.\n",
                "format_style": "ieee",
            },
        )
    assert res.status_code == 200
    document_id = res.get_json()["document_id"]
    doc = _download_docx(client, document_id)
    assert doc.status_code == 200
    assert doc.data[:2] == b"PK"
    assert (
        doc.mimetype
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_download_endpoint_404_for_unknown_id() -> None:
    with patch.dict("os.environ", {"FORMATTER_V2_ENABLED": "1"}, clear=False):
        res = _download_docx(_client(), "00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


def test_no_remaining_references_to_x_format_headers_in_js() -> None:
    js = _read_js()
    assert not re.search(r"X-Format-", js)
    assert "decodeSummaryHeader" not in js
    assert "decodeNoticesHeader" not in js
    assert "handleDocxResponse" not in js


def test_history_renders_each_applied_edit() -> None:
    js_path = Path(__file__).resolve().parents[1] / "static" / "format_v2.js"
    js = js_path.read_text(encoding="utf-8")
    send_start = js.index("async function sendChatEdit")
    send_end = js.index("async function undoChatEdit")
    send_body = js[send_start:send_end]
    assert "appendChatHistoryEntry" in send_body
    assert "handleFormatJsonResponse" in js
    assert "/api/format-v2/download/" in js
    assert "showChatHistorySection" in js
