"""ZeroGPT site judge parsers (no live browser)."""

from __future__ import annotations

import pytest

from services.humanizer_training.judge.zerogpt_site import (
    ZeroGPTSiteError,
    ai_frac_from_page_text,
    parse_detect_payload,
)


def test_parse_detect_payload_fake_percentage():
    assert parse_detect_payload({"success": True, "data": {"fakePercentage": 72.8}}) == pytest.approx(0.728)


def test_parse_detect_payload_already_fraction():
    assert parse_detect_payload({"ai_frac": 0.11, "fakePercentage": 11}) == pytest.approx(0.11)


def test_parse_detect_payload_denied():
    with pytest.raises(ZeroGPTSiteError):
        parse_detect_payload({"success": False, "code": 403, "message": "rate limit"})


def test_ai_frac_from_page_text_gauge():
    body = "Most of Your Text is AI/GPT Generated\n72.8% AI GPT*\nHighlighted sentences below"
    assert ai_frac_from_page_text(body) == pytest.approx(0.728)