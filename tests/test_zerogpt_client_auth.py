"""Tests for ZeroGPT client auth mode selection."""

from __future__ import annotations

from services.zerogpt_business.client import ZeroGPTClient, ZeroGPTConfig, ZeroGPTError, _is_jwt_like


def test_uuid_api_key_is_not_treated_as_jwt():
    assert not _is_jwt_like("4d977d55-c2e3-4b83-a270-a55e4112cfc0")


def test_jwt_like_token_detected():
    assert _is_jwt_like("aaa.bbb.ccc")


def test_business_api_adds_api_key_header():
    client = ZeroGPTClient(
        ZeroGPTConfig(
            base_url="https://api.zerogpt.com",
            api_key="0d623181-d39b-4bdf-a495-d13dbf01ed03",
            email="user@example.com",
            password="secret",
            detect_path="/api/detect/detectText",
            humanize_path="/api/transform/humanize",
            paraphrase_path="/api/transform/rephrase",
            advanced_paraphrase_path="/api/transform/paraphrase",
            text_field="input_text",
        )
    )
    client._jwt_token = "jwt.token.here"
    headers = client._auth_headers()
    assert headers["ApiKey"] == "0d623181-d39b-4bdf-a495-d13dbf01ed03"
    assert headers["Authorization"] == "Bearer jwt.token.here"


def test_business_api_does_not_use_uuid_as_bearer_only():
    client = ZeroGPTClient(
        ZeroGPTConfig(
            base_url="https://api.zerogpt.com",
            api_key="4d977d55-c2e3-4b83-a270-a55e4112cfc0",
            email="user@example.com",
            password="secret",
            detect_path="/api/detect/detectText",
            humanize_path="/api/transform/humanize",
            paraphrase_path="/api/transform/rephrase",
            advanced_paraphrase_path="/api/transform/paraphrase",
            text_field="input_text",
        )
    )
    assert not client._uses_api_key_bearer()


def test_developer_api_rejects_uuid_api_key():
    client = ZeroGPTClient(
        ZeroGPTConfig(
            base_url="https://api.zerogpt.org",
            api_key="4d977d55-c2e3-4b83-a270-a55e4112cfc0",
            email="",
            password="",
            detect_path="/api/v1/developer/ai-detection",
            humanize_path="/api/v1/developer/humanize",
            paraphrase_path="/api/v1/developer/paraphrase",
            advanced_paraphrase_path="/api/v1/developer/advanced-paraphrase",
            text_field="text",
        )
    )
    assert not client._uses_api_key_bearer()
    try:
        client._validate_config()
        raised = False
    except ZeroGPTError:
        raised = True
    assert raised


def test_developer_api_accepts_zgpt_sk_key():
    client = ZeroGPTClient(
        ZeroGPTConfig(
            base_url="https://api.zerogpt.org",
            api_key="zgpt_sk_live_abc123",
            email="",
            password="",
            detect_path="/api/v1/developer/ai-detection",
            humanize_path="/api/v1/developer/humanize",
            paraphrase_path="/api/v1/developer/paraphrase",
            advanced_paraphrase_path="/api/v1/developer/advanced-paraphrase",
            text_field="text",
        )
    )
    assert client._uses_api_key_bearer()
