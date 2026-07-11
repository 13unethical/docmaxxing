"""Tests for ZeroGPT humanizer adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.ai_provider_interfaces import HumanizedResult
from services.humanizer_engine.constants import MAX_WORDS_PER_INPUT, TRANSFORM_CHUNK_WORDS
from services.humanizer_engine.zerogpt_humanizer import (
    ZeroGPTTextHumanizer,
    count_words,
    split_text_by_word_limit,
)


def test_split_text_by_word_limit_chunks_large_input():
    text = " ".join(f"word{i}" for i in range(MAX_WORDS_PER_INPUT + 10))
    chunks = split_text_by_word_limit(text)
    assert len(chunks) == 2
    assert count_words(chunks[0]) == MAX_WORDS_PER_INPUT
    assert count_words(chunks[1]) == 10


def test_business_api_uses_zerogpt_humanizer(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = MagicMock()
    client.config.base_url = "https://api.zerogpt.com"
    humanizer = ZeroGPTTextHumanizer(client=client, mode="humanize")
    mock_provider = MagicMock()
    mock_provider.humanize.return_value = HumanizedResult(
        provider="zerogpt-humanize",
        text="humanized paragraph",
        original_words=10,
        humanized_words=10,
        processing_time=0.0,
        raw={},
    )
    humanizer._humanizer = mock_provider
    text = "This is a long enough sample paragraph for humanization testing purposes."
    result = humanizer.humanize(text, academic_tone="Academic")
    assert result == "humanized paragraph"
    mock_provider.humanize.assert_called_once()
    assert mock_provider.humanize.call_args.kwargs["tone"] == "Academic"
    assert mock_provider.humanize.call_args.kwargs["mode"] == "humanize"


def test_zerogpt_humanizer_skips_section_headers(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = MagicMock()
    client.config.base_url = "https://api.zerogpt.org"
    humanizer = ZeroGPTTextHumanizer(client=client)
    assert humanizer.humanize("## Introduction") == "## Introduction"


def test_zerogpt_humanizer_joins_chunk_outputs(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = MagicMock()
    client.config.base_url = "https://api.zerogpt.org"
    humanizer = ZeroGPTTextHumanizer(client=client)
    provider = humanizer._humanizer
    provider.humanize = MagicMock(
        side_effect=[
            HumanizedResult(
                provider="zerogpt-business",
                text="chunk-one",
                original_words=2,
                humanized_words=2,
                processing_time=0.0,
                raw={},
            ),
            HumanizedResult(
                provider="zerogpt-business",
                text="chunk-two",
                original_words=2,
                humanized_words=2,
                processing_time=0.0,
                raw={},
            ),
        ]
    )
    text = " ".join(["alpha"] * (TRANSFORM_CHUNK_WORDS + 3))
    result = humanizer.humanize(text)
    assert result == "chunk-one\n\nchunk-two"
    assert provider.humanize.call_count == 2


def test_business_humanize_request_uses_string_field():
    from services.zerogpt_business.client import ZeroGPTClient, ZeroGPTConfig

    config = ZeroGPTConfig(
        base_url="https://api.zerogpt.com",
        api_key="0d623181-d39b-4bdf-a495-d13dbf01ed03",
        email="user@example.com",
        password="secret",
        detect_path="/api/detect/detectText",
        humanize_path="/api/transform/humanize",
        paraphrase_path="/api/transform/paraphrase",
        advanced_paraphrase_path="/api/transform/paraphrase",
        text_field="input_text",
    )
    client = ZeroGPTClient(config)
    client._jwt_token = "jwt.token.here"
    with patch.object(client, "request", return_value={"success": True, "data": {}}) as mock_request:
        client.humanize("hello world " * 10, tone="Academic")
        mock_request.assert_called_once_with(
            "POST",
            "/api/transform/humanize",
            json_body={"string": "hello world " * 10, "skipRealtime": 1, "tone": "Academic"},
            timeout_s=300.0,
        )


def test_business_advanced_paraphrase_request_uses_string_field():
    from services.zerogpt_business.client import ZeroGPTClient, ZeroGPTConfig

    config = ZeroGPTConfig(
        base_url="https://api.zerogpt.com",
        api_key="0d623181-d39b-4bdf-a495-d13dbf01ed03",
        email="user@example.com",
        password="secret",
        detect_path="/api/detect/detectText",
        humanize_path="/api/transform/humanize",
        paraphrase_path="/api/transform/paraphrase",
        advanced_paraphrase_path="/api/transform/paraphrase",
        text_field="input_text",
    )
    client = ZeroGPTClient(config)
    client._jwt_token = "jwt.token.here"
    with patch.object(client, "request", return_value={"success": True, "data": {}}) as mock_request:
        client.advanced_paraphrase("hello world " * 10, tone="Academic")
        mock_request.assert_called_once_with(
            "POST",
            "/api/transform/paraphrase",
            json_body={"string": "hello world " * 10, "skipRealtime": 1, "tone": "Academic"},
            timeout_s=300.0,
        )
