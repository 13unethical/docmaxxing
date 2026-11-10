"""Patch 3F: free (pre-payment) Gemini/Claude calls are bounded by one server-side allowance.

Every test runs with the provider clients' HTTP layer replaced by ``FakeProvider``. A call the
test forbids raises ``ForbiddenProviderCall`` (a BaseException, so no ``except Exception`` in the
app can swallow it) and fails the test immediately. A call made inside a free scope without a
reserved grant fails the same way.
"""

from __future__ import annotations

import io
import json as _json
import multiprocessing
import re
import threading
from types import SimpleNamespace

import pytest
import requests
from docx import Document

from services import free_ai_quota, free_humanize
from services.assignment_project.requirement_analyzer import GeminiRequirementAnalyzer
from services.assignment_project.service import ProjectService
from services.assignment_project.store import ProjectStore
from services.economy import db as economy_db
from services.writer_engine import WriterEngineService
from services.writer_engine.mock_reviewer import MockSectionReviewer
from tests.test_assignment_project import _StubBlueprintService, _StubResearchService
from tests.test_security_paid_pipelines import _client, _signed_in, _user, economy  # noqa: F401
from tests.test_security_refund_integrity import (  # noqa: F401
    _SwitchWriter,
    _paid_project,
    _url,
    refund_app,
)

_QUOTA_ENV = sorted(
    {
        name
        for p in free_ai_quota.POOLS.values()
        for name in (p.rate_env, p.user_env, p.guest_env, p.guest_ip_env, p.max_chars_env)
        if name
    }
)


class ForbiddenProviderCall(BaseException):
    pass


class _Response:
    def __init__(self, status: int, payload: dict):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload
        self.text = _json.dumps(payload)

    def json(self):
        return self._payload


def _answer(system: str, user: str) -> dict:
    if "recovering academic document structure" in system:
        n = int(re.search(r"for these (\d+) paragraphs", user).group(1))
        return {
            "document_type": "essay",
            "document_type_confidence": 0.9,
            "sections": [
                {"title": "Introduction", "heading_text": "Introduction", "confidence": 0.9,
                 "paragraph_indices": [1], "insert_heading": True},
                {"title": "Discussion", "heading_text": "Discussion", "confidence": 0.8,
                 "paragraph_indices": list(range(2, n)), "insert_heading": True},
                {"title": "Conclusion", "heading_text": "Conclusion", "confidence": 0.9,
                 "paragraph_indices": [n], "insert_heading": True},
            ],
        }
    if "explain academic document check results" in system:
        return {"summary": "Add the missing sections first.", "major_risks": []}
    if "formatting and submission requirements" in system:
        return {"font_family": "Arial", "font_size": 12, "spacing": 2.0, "citation_style": "APA",
                "required_sections": [], "confidence_score": 0.9}
    if "requirement-analysis engine" in system:
        return {
            "assignment_type": "Essay", "title": "Energy policy", "word_count": 1000, "citation_style": "APA",
            "required_sections": ["Introduction", "Conclusion"], "section_word_budgets": {}, "rubric": [],
            "learning_outcomes": [], "minimum_sources": 3, "formatting": {}, "missing_information": [],
        }
    return {"ok": True}


class FakeProvider:
    """Stands in for ``requests.post`` of the Gemini and Claude clients."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.forbid = False
        self.fail = False

    def __call__(self, url, params=None, headers=None, json=None, timeout=None, **_kw):
        if "googleapis.com" not in url and "anthropic.com" not in url:
            raise requests.exceptions.ConnectionError("network disabled in tests")
        grant = free_ai_quota.active()
        self.calls.append({"url": url, "pool": grant.pool.name if grant else None, "body": _json.dumps(json)})
        if self.forbid:
            raise ForbiddenProviderCall(url)
        if grant is not None and grant.state != free_ai_quota.RESERVED:
            raise ForbiddenProviderCall(f"provider call under an unreserved grant ({grant.state})")
        if self.fail:
            return _Response(400, {"error": {"message": "API key AIzaLEAKED not valid (/srv/app/secret.py)"}})
        if "anthropic.com" in url:
            user = json["messages"][0]["content"]
            text = _json.dumps(_answer(json["system"], user if isinstance(user, str) else ""))
            return _Response(200, {"content": [{"type": "text", "text": text}]})
        system = json["systemInstruction"]["parts"][0]["text"]
        user = json["contents"][0]["parts"][0]["text"]
        return _Response(200, {"candidates": [{"content": {"parts": [{"text": _json.dumps(_answer(system, user))}]}}]})

    def count(self, pool: str | None = None) -> int:
        return sum(1 for c in self.calls if pool is None or c["pool"] == pool)


@pytest.fixture()
def provider(economy, monkeypatch):  # noqa: F811
    for name in _QUOTA_ENV + ["FREE_HUMANIZE_GUEST_DAILY", "FORMATTER_V2_ENABLED", "STRUCTURE_RECOVERY_DEBUG",
                              "ANTHROPIC_API_KEY", "Claude_API_Key", "GEMINI_API_KEY", "INTERNAL_TOOLS_ENABLED"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "offline-test-key")
    fake = FakeProvider()
    monkeypatch.setattr(requests, "post", fake)
    return fake


def _prose(n: int = 6, words: int = 1) -> str:
    filler = " ".join(["The evidence is weighed carefully against municipal budget constraints."] * words)
    return "\n\n".join(
        f"In part {i} of this essay, renewable energy adoption in coastal cities is examined in relation "
        f"to grid stability and public opinion, drawing on survey evidence (Smith, 2020). {filler}"
        for i in range(1, n + 1)
    )


def _merged_headings(n: int = 6) -> str:
    """Prose whose section labels were glued into paragraphs, so /api/format must rebuild structure."""
    parts = _prose(n).split("\n\n")
    parts[0] = "Introduction " + parts[0]
    parts[-1] = "Conclusion " + parts[-1]
    return "\n\n".join(parts)


def _structure(client, text=None, headers=None):
    return client.post("/api/structure-recovery", data={"pasted_text": text or _prose()}, headers=headers or {})


def _format(client, text=None, **fields):
    data = {"pasted_text": text or _merged_headings(), "auto_headings": "on"}
    data.update(fields)
    return client.post("/api/format", data={k: v for k, v in data.items() if v is not None})


def _check(client, text=None):
    return client.post(
        "/api/check-document",
        data={"pasted_text": text or _prose(), "document_type": "essay",
              "requirements": "Write an essay with an introduction and a conclusion."},
    )


def _preview(client, text=None, settings=None):
    return client.post(
        "/api/preview-formatted",
        json={"text": text or _merged_headings(), "settings": settings or {"auto_headings": True}},
    )


def _used(subject: str) -> int:
    return free_humanize.used_today(subject)


def _reservation_ids() -> list[str]:
    with economy_db.connect() as conn:
        free_ai_quota._ensure_schema(conn)
        return [r["id"] for r in conn.execute("SELECT id FROM free_ai_reservations").fetchall()]


def _docx_text(res) -> list[tuple[str, str]]:
    doc = Document(io.BytesIO(res.data))
    return [(p.style.name, p.text) for p in doc.paragraphs if p.text.strip()]


# ------------------------------------------------------------------- 1. anonymous structure recovery


def test_anonymous_structure_recovery_is_bounded(provider):
    guest = _client()
    results = [_structure(guest) for _ in range(4)]
    assert [r.status_code for r in results] == [200, 200, 200, 200]
    assert [r.get_json()["recovery_mode"] for r in results] == ["ai_reconstructed"] * 3 + ["reconstructed"]
    assert provider.count("document") == 3
    refused = results[-1].get_json()["ai_quota"]
    assert refused == {"status": "skipped", "reason": "FREE_LIMIT_REACHED", "register_required": True}

    fresh_cookies = _client()
    again = _structure(fresh_cookies)
    assert again.status_code == 200 and again.get_json()["recovery_mode"] == "reconstructed"
    assert provider.count("document") == 3


# ------------------------------------------------------------------- 2. registered users


def test_registered_users_have_separate_bounded_allowances(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_USER_DAILY", "2")
    alice = _user("alice@example.com")
    bob = _user("bob@example.com")
    a, b = _signed_in(_client(), alice), _signed_in(_client(), bob)

    assert [_structure(a).get_json()["ai_powered"] for _ in range(3)] == [True, True, False]
    assert [_structure(b).get_json()["ai_powered"] for _ in range(3)] == [True, True, False]
    assert provider.count("document") == 4
    assert _used(f"docai:user:{alice['id']}") == 2 and _used(f"docai:user:{bob['id']}") == 2
    assert _structure(a).get_json()["ai_quota"]["register_required"] is False


def test_unverified_accounts_are_metered_as_guests(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_USER_DAILY", "50")
    monkeypatch.setenv("FREE_DOC_AI_GUEST_IP_DAILY", "1")
    first = _signed_in(_client(), _user("burner1@example.com", verified=False))
    second = _signed_in(_client(), _user("burner2@example.com", verified=False))
    assert _structure(first).get_json()["ai_powered"] is True
    assert _structure(first).get_json()["ai_powered"] is False
    assert _structure(second).get_json()["ai_powered"] is False  # a new unverified account adds nothing
    assert provider.count("document") == 1


# ------------------------------------------------------------------- 3. switching routes


def test_structure_format_check_and_preview_share_one_document_allowance(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_GUEST_DAILY", "2")
    monkeypatch.setenv("FREE_DOC_AI_GUEST_IP_DAILY", "2")
    guest = _client()
    assert _structure(guest).get_json()["ai_powered"] is True
    formatted = _format(guest)
    assert formatted.status_code == 200 and formatted.data[:2] == b"PK"
    assert "X-AI-Quota" not in formatted.headers
    assert provider.count("document") == 2

    provider.forbid = True
    checked = _check(guest)
    assert checked.status_code == 200
    assert checked.get_json()["ai_quota"]["reason"] == "FREE_LIMIT_REACHED"
    assert _structure(guest).get_json()["ai_powered"] is False
    assert _format(guest).headers["X-AI-Quota"] == "FREE_LIMIT_REACHED"
    for _ in range(5):
        assert _preview(guest).status_code == 200
    assert provider.count("document") == 2


def test_one_check_request_spends_one_unit_for_both_ai_steps(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_GUEST_DAILY", "1")
    guest = _client()
    res = _check(guest)
    assert res.status_code == 200
    assert provider.count("document") == 2  # structure + explanation under one reservation
    assert len(_reservation_ids()) == 1


def test_v1_and_v2_brief_parsing_share_the_brief_allowance(provider, monkeypatch):
    from formatter_v2 import smartform as smartform_mod
    from formatter_v2.spec import UserOverrides

    def extract_via_provider(brief, client):
        client.generate(system_instruction="v2 brief", user_message=brief, temperature=0.0,
                        response_mime_type="application/json", response_schema={}, timeout_s=10)
        return SimpleNamespace(style=None, warnings=[], unsupported=[])

    monkeypatch.setattr(smartform_mod, "extract_requirements", extract_via_provider)
    monkeypatch.setattr(smartform_mod, "to_user_overrides",
                        lambda e, p: SimpleNamespace(overrides=UserOverrides(font_size_pt=12), evidence_by_field={}))
    monkeypatch.setenv("FORMATTER_V2_ENABLED", "1")
    monkeypatch.setenv("SMARTFORM_GUEST_DAILY", "2")
    guest = _client()
    brief = "Times New Roman, 12 pt, double spaced, APA references."
    v1 = guest.post("/parse-requirements", json={"text": brief})
    assert v1.get_json()["requirements"]["ai_provider"] == "gemini"
    v2 = guest.post("/api/extract-requirements-v2", data={"requirements_text": brief})
    assert v2.status_code == 200
    provider.forbid = True
    v1_again = guest.post("/api/extract-requirements", data={"requirements_text": brief})
    assert v1_again.status_code == 200
    assert v1_again.get_json()["requirements"]["ai_provider"] == "local"
    assert v1_again.get_json()["ai_quota"]["reason"] == "FREE_LIMIT_REACHED"
    assert guest.post("/api/extract-requirements-v2", data={"requirements_text": brief}).status_code == 403
    assert provider.count("brief") == 2


# ------------------------------------------------------------------- 4. auto_headings variants


@pytest.mark.parametrize(
    "fields",
    [
        {"auto_headings": None},
        {"auto_headings": "false"},
        {"auto_headings": "0"},
        {"auto_headings": "off"},
        {"auto_headings": "maybe"},
        {"auto_headings": None, "requirement_headings": "on", "requirements_text": "Sections: Introduction, Conclusion"},
    ],
)
def test_format_without_auto_headings_never_reaches_the_provider(provider, fields):
    provider.forbid = True
    res = _format(_client(), **fields)
    assert res.status_code == 200 and res.data[:2] == b"PK"
    assert provider.count() == 0
    assert _reservation_ids() == []


@pytest.mark.parametrize(
    "settings",
    [{"auto_headings": True}, {"auto_headings": "on"}, {"auto_headings": "true", "requirement_headings": True}],
)
def test_preview_never_reaches_the_provider_whatever_the_settings(provider, settings):
    provider.forbid = True
    for _ in range(10):
        res = _preview(_client(), settings=settings)
        assert res.status_code == 200 and res.get_json()["html"]
    assert provider.count() == 0 and _reservation_ids() == []


def test_auto_headings_cannot_force_ai_once_the_allowance_is_spent(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_GUEST_DAILY", "1")
    guest = _client()
    assert "X-AI-Quota" not in _format(guest).headers
    provider.forbid = True
    for variant in ("on", "true", "1", "yes", "TRUE"):
        res = _format(guest, auto_headings=variant)
        assert res.status_code == 200 and res.headers["X-AI-Quota"] == "FREE_LIMIT_REACHED"
    multi = guest.post("/api/format", data={"pasted_text": _merged_headings(), "auto_headings": ["on", "on", "on"]})
    assert multi.status_code == 200 and multi.headers["X-AI-Quota"] == "FREE_LIMIT_REACHED"
    assert provider.count("document") == 1


# ------------------------------------------------------------------- 5. analyze_requirements


@pytest.fixture()
def analyze_app(provider, tmp_path, monkeypatch):
    import app as app_mod

    service = ProjectService(
        store=ProjectStore(root=tmp_path / "projects"),
        pipeline=app_mod.assignment_pipeline,
        analyzer=GeminiRequirementAnalyzer(),
        research=_StubResearchService(),  # type: ignore[arg-type]
        blueprint=_StubBlueprintService(),  # type: ignore[arg-type]
        writer=WriterEngineService(writer=_SwitchWriter(), reviewer=MockSectionReviewer()),
        delivery=app_mod.delivery_engine,
    )
    monkeypatch.setattr(app_mod, "project_service", service)
    monkeypatch.setattr(app_mod, "PROJECT_STORAGE_ROOT", tmp_path / "projects")
    return SimpleNamespace(app=app_mod, service=service)


def _project(env, owner) -> str:
    bundle = env.service.create_project(
        user_id=str(owner["id"]),
        files=[{"file_type": "assignment_brief", "original_filename": "brief.pdf"}],
    )
    return bundle.project.id


FORGED = {"paid": True, "payment_confirmed": True, "plan": "pro", "credits": 10_000, "quota": 999,
          "user_id": 1, "used_today": 0, "unlimited": True}


def test_direct_analyze_requirements_is_bounded_and_ignores_forged_entitlements(analyze_app, provider, monkeypatch):
    monkeypatch.setenv("ASSIGNMENT_ANALYZE_USER_DAILY", "2")
    owner = _user("student@example.com")
    client = _signed_in(_client(), owner)
    project_id = _project(analyze_app, owner)
    codes = [client.post(_url(project_id, "analyze-requirements"), json=FORGED).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert provider.count("analyze") == 2
    refused = client.post(_url(project_id, "analyze-requirements"), json=FORGED,
                          headers={"X-User-Plan": "pro", "X-Paid": "true"})
    assert refused.status_code == 429 and refused.get_json()["error"] == "FREE_LIMIT_REACHED"
    assert provider.count("analyze") == 2

    other_project = _project(analyze_app, owner)
    assert client.post(_url(other_project, "analyze-requirements")).status_code == 429  # per user, not per project
    assert provider.count("analyze") == 2


def test_analyze_requirements_needs_a_verified_owner(analyze_app, provider):
    provider.forbid = True
    owner = _user("owner@example.com")
    project_id = _project(analyze_app, owner)
    assert _client().post(_url(project_id, "analyze-requirements")).status_code == 401
    unverified = _signed_in(_client(), _user("new@example.com", verified=False))
    assert unverified.post(_url(project_id, "analyze-requirements")).status_code == 403
    stranger = _signed_in(_client(), _user("stranger@example.com"))
    assert stranger.post(_url(project_id, "analyze-requirements")).status_code in (403, 404)
    assert _client().get("/api/debug/section-review/" + project_id).status_code == 404
    assert provider.count() == 0 and _reservation_ids() == []


def test_analyze_requirements_through_claude_uses_the_same_allowance(analyze_app, provider, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-test-key")
    monkeypatch.setenv("ASSIGNMENT_ANALYZE_USER_DAILY", "1")
    owner = _user("student@example.com")
    client = _signed_in(_client(), owner)
    project_id = _project(analyze_app, owner)
    assert client.post(_url(project_id, "analyze-requirements")).status_code == 200
    assert client.post(_url(project_id, "analyze-requirements")).status_code == 429
    assert provider.count("analyze") == 1 and "anthropic.com" in provider.calls[0]["url"]


def test_unpaid_projects_still_cannot_start_paid_stages(analyze_app, provider):
    owner = _user("student@example.com")
    client = _signed_in(_client(), owner)
    project_id = _project(analyze_app, owner)
    assert client.post(_url(project_id, "analyze-requirements"), json=FORGED).status_code == 200
    provider.forbid = True
    for step in ("research", "blueprint"):
        res = client.post(_url(project_id, step), json=FORGED)
        assert res.status_code >= 400 and "payment" in res.get_json()["error"].lower(), (step, res.status_code)
    assert provider.count("analyze") == 1


# ------------------------------------------------------------------- 6./7. identity forgery and headers


def test_forged_identity_fields_and_cookies_are_ignored(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_GUEST_DAILY", "1")
    monkeypatch.setenv("FREE_DOC_AI_GUEST_IP_DAILY", "1")
    monkeypatch.setenv("FREE_DOC_AI_USER_DAILY", "1")
    guest = _client()
    forged = {"pasted_text": _prose(), "user_id": "1", "plan": "pro", "paid": "true", "quota": "999",
              "free_ai_reservation": "x" * 32, "email_verified": "true"}
    first = guest.post("/api/structure-recovery", data=forged, headers={"X-User-Id": "1", "X-Plan": "pro"})
    second = guest.post("/api/structure-recovery", data=forged, headers={"X-User-Id": "1", "X-Plan": "pro"})
    assert first.get_json()["ai_powered"] is True and second.get_json()["ai_powered"] is False
    guest.set_cookie("session", "forged.session.cookie")
    assert _structure(guest).get_json()["ai_powered"] is False

    alice = _user("alice@example.com")
    bob = _user("bob@example.com")
    a = _signed_in(_client(), alice)
    assert a.post("/api/structure-recovery", data={**forged, "user_id": str(bob["id"])}).get_json()["ai_powered"] is True
    assert _used(f"docai:user:{alice['id']}") == 1 and _used(f"docai:user:{bob['id']}") == 0
    assert a.post("/api/structure-recovery", data={**forged, "user_id": str(bob["id"])}).get_json()["ai_powered"] is False
    assert provider.count("document") == 2


def test_spoofed_forwarding_headers_do_not_reset_guest_limits(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_GUEST_DAILY", "100")
    monkeypatch.setenv("FREE_DOC_AI_GUEST_IP_DAILY", "2")
    monkeypatch.setenv("FREE_DOC_AI_RATE_PER_MIN", "0")
    real_hop = "203.0.113.7"  # what nginx appends; everything before it is client-supplied
    outcomes = []
    for n in range(6):
        headers = {
            "X-Forwarded-For": f"198.51.100.{n}, 10.0.0.{n}, {real_hop}",
            "CF-Connecting-IP": f"192.0.2.{n}",
            "True-Client-IP": f"192.0.2.{n}",
            "Forwarded": f"for=192.0.2.{n}",
        }
        outcomes.append(_structure(_client(), headers=headers).get_json()["ai_powered"])
    assert outcomes == [True, True, False, False, False, False]
    assert provider.count("document") == 2


# ------------------------------------------------------------------- 8./9. size and shape before the provider


def test_oversized_input_never_reaches_the_provider(analyze_app, provider, monkeypatch):
    provider.forbid = True
    guest = _client()
    from services.document_checker import MAX_TEXT_CHARS

    assert _structure(guest, text="word " * (MAX_TEXT_CHARS // 5 + 10)).status_code == 400
    assert _preview(guest, text="x" * (MAX_TEXT_CHARS + 1)).status_code == 400
    assert guest.post("/parse-requirements", json={"text": "x" * (MAX_TEXT_CHARS + 1)}).status_code == 400

    monkeypatch.setenv("FREE_DOC_AI_MAX_CHARS", "500")
    long_doc = _merged_headings(n=6)
    res = _structure(guest, text=long_doc)
    assert res.status_code == 200 and res.get_json()["ai_quota"]["reason"] == "INPUT_TOO_LONG"
    assert _format(guest, text=long_doc).headers["X-AI-Quota"] == "INPUT_TOO_LONG"
    assert _check(guest, text=long_doc).get_json()["ai_quota"]["reason"] == "INPUT_TOO_LONG"

    monkeypatch.setenv("SMARTFORM_BRIEF_MAX_CHARS", "40")
    brief = guest.post("/api/extract-requirements", data={"requirements_text": "Use Arial 12 pt and APA style for references."})
    assert brief.get_json()["requirements"]["ai_provider"] == "local"
    assert brief.get_json()["ai_quota"]["reason"] == "INPUT_TOO_LONG"
    monkeypatch.setenv("FORMATTER_V2_ENABLED", "1")
    v2 = guest.post("/api/extract-requirements-v2", data={"requirements_text": "y" * 41})
    assert v2.status_code == 400 and v2.get_json()["error"] == "BRIEF_TOO_LONG"
    monkeypatch.setenv("FORMAT_CHAT_MAX_CHARS", "10")
    chat = _signed_in(_client(), _user("chat@example.com")).post(
        "/api/format-v2/chat", data={"pasted_text": "Body.", "message": "m" * 11, "overrides": "{}"})
    assert chat.status_code == 400 and chat.get_json()["error"] == "MESSAGE_TOO_LONG"

    monkeypatch.setenv("ASSIGNMENT_ANALYZE_MAX_CHARS", "100")
    owner = _user("student@example.com")
    project_id = _project(analyze_app, owner)
    refused = _signed_in(_client(), owner).post(_url(project_id, "analyze-requirements"))
    assert refused.status_code == 400 and refused.get_json()["error"] == "INPUT_TOO_LONG"

    assert provider.count() == 0 and _reservation_ids() == []


def test_check_explanation_is_size_capped_too(provider, monkeypatch):
    # validation rows can quote whole paragraphs, so the explanation prompt is capped like the document
    res = _check(_client(), text=_merged_headings(n=6))
    assert res.status_code == 200 and provider.count("document") == 2
    assert "renewable energy adoption" in provider.calls[-1]["body"]

    provider.forbid = True
    monkeypatch.setenv("FREE_DOC_AI_MAX_CHARS", "500")
    res = _check(_client(), text=_merged_headings(n=6))
    assert res.status_code == 200
    assert res.get_json()["ai_quota"]["reason"] == "INPUT_TOO_LONG"
    assert res.get_json()["meta"]["compliance_analysis"]["summary"]
    assert len(_reservation_ids()) == 1


def test_malformed_input_is_rejected_before_the_provider(provider):
    provider.forbid = True
    guest = _client()
    assert guest.post("/api/preview-formatted", json=["text"]).status_code == 400
    assert guest.post("/api/preview-formatted", json={"text": ["a", "b"]}).status_code == 400
    assert guest.post("/api/preview-formatted", json={"text": _prose(), "settings": ["auto_headings"]}).status_code == 400
    assert guest.post("/api/preview-formatted", json={"text": _prose(), "settings": {"auto_headings": True},
                                                      "document_type": {"x": 1}}).status_code in (200, 400)
    assert guest.post("/parse-requirements", json=["text"]).status_code == 400
    assert guest.post("/parse-requirements", json={"text": 12345}).status_code == 400
    assert guest.post("/parse-requirements", data="not json", content_type="application/json").status_code == 400
    bad_type = guest.post("/api/structure-recovery",
                          data={"file": (io.BytesIO(b"MZ\x90\x00"), "payload.exe")}, content_type="multipart/form-data")
    assert bad_type.status_code == 400
    empty = guest.post("/api/structure-recovery",
                       data={"file": (io.BytesIO(b""), "empty.docx")}, content_type="multipart/form-data")
    assert empty.status_code == 400
    corrupt = guest.post("/api/structure-recovery",
                         data={"file": (io.BytesIO(b"PK\x03\x04garbage"), "broken.docx")}, content_type="multipart/form-data")
    assert corrupt.status_code == 400
    assert guest.post("/api/structure-recovery", data={"pasted_text": "   "}).status_code == 400
    assert guest.post("/api/check-document", data={"pasted_text": ""}).status_code == 400
    assert provider.count() == 0 and _reservation_ids() == []


# ------------------------------------------------------------------- 10. provider-level traps


def test_free_ai_helpers_skip_the_provider_without_a_scope_inside_a_request(provider):
    import app as app_mod
    from services import gemini_client
    from services.check_explanation import explain_check_results
    from services.document_structure_engine import recover_structure
    from services.requirements_parser import parse_requirements

    provider.forbid = True
    with app_mod.app.test_request_context("/api/some-new-route", method="POST"):
        assert recover_structure(text=_prose())["recovery_mode"] == "reconstructed"
        assert parse_requirements("Arial 12 pt, APA.")["ai_provider"] == "local"
        explained = explain_check_results(requirements="x", validations=[], readiness_score=50,
                                          metrics={"word_count": 100}, document_type="essay")
        assert explained["source"] == "local"

        denied = free_ai_quota.Grant("document", rate_key="t", subjects=[], guest=True,
                                     refusal=free_ai_quota.FREE_LIMIT_REACHED)
        with free_ai_quota.scope(denied):
            data, diag = gemini_client.generate_json(system_prompt="s", user_prompt="u")
            text, tdiag = gemini_client.generate_text(system_prompt="s", content="u")
        assert data is None and diag["failure_reason"] == "quota"
        assert text is None and tdiag["failure_reason"] == "quota"
    assert provider.count() == 0


def test_provider_refuses_inside_a_scope_until_the_grant_is_reserved(provider, monkeypatch):
    from services import claude_client, gemini_client

    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-test-key")
    grant = free_ai_quota.grant_for("document", user_id=None, email_verified=False,
                                    guest_subject="guest:trap", guest_ip_subject="guest-ip:trap")
    monkeypatch.setenv("FREE_DOC_AI_GUEST_DAILY", "1")
    with free_ai_quota.scope(grant):
        assert gemini_client.generate_json(system_prompt="s", user_prompt="u")[0] == {"ok": True}
        assert claude_client.generate_json(system_prompt="s", user_prompt="u")[0] == {"ok": True}
    assert grant.provider_calls == 2 and _used("docai:guest:trap") == 1  # nested calls share one unit
    second = free_ai_quota.grant_for("document", user_id=None, email_verified=False,
                                     guest_subject="guest:trap", guest_ip_subject="guest-ip:trap")
    provider.forbid = True
    with free_ai_quota.scope(second):
        assert gemini_client.generate_json(system_prompt="s", user_prompt="u")[1]["failure_reason"] == "quota"
        assert claude_client.generate_reply(system_prompt="s", content="u")[1]["failure_reason"] == "quota"
        assert claude_client.generate_with_web_search(system_prompt="s", user_prompt="u")[2]["failure_reason"] == "quota"
    assert provider.count() == 2


# ------------------------------------------------------------------- 11./12. concurrency


def test_concurrent_requests_cannot_exceed_the_allowance(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_USER_DAILY", "3")
    monkeypatch.setenv("FREE_DOC_AI_RATE_PER_MIN", "0")
    user = _user("racer@example.com")
    clients = [_signed_in(_client(), user) for _ in range(12)]
    barrier = threading.Barrier(len(clients))
    results: list[bool] = []
    lock = threading.Lock()

    def hit(client):
        barrier.wait()
        powered = _structure(client).get_json()["ai_powered"]
        with lock:
            results.append(powered)

    threads = [threading.Thread(target=hit, args=(c,)) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert len(results) == 12 and results.count(True) == 3
    assert provider.count("document") == 3
    assert _used(f"docai:user:{user['id']}") == 3


def _child_acquire(queue, pool, user_id, attempts):
    won = 0
    for _ in range(attempts):
        grant = free_ai_quota.grant_for(pool, user_id=user_id, email_verified=True,
                                        guest_subject=None, guest_ip_subject=None)
        won += int(grant.acquire())
    queue.put(won)


def _run_children(target, args_list):
    ctx = multiprocessing.get_context("fork")
    queue = ctx.Queue()
    procs = [ctx.Process(target=target, args=(queue, *args)) for args in args_list]
    for p in procs:
        p.start()
    results = [queue.get(timeout=60) for _ in procs]
    for p in procs:
        p.join(30)
        assert p.exitcode == 0
    return results


def test_worker_processes_share_the_daily_allowance(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_USER_DAILY", "7")
    monkeypatch.setenv("FREE_DOC_AI_RATE_PER_MIN", "0")
    results = _run_children(_child_acquire, [("document", 41, 5)] * 4)
    assert sum(results) == 7
    assert _used("docai:user:41") == 7 and len(_reservation_ids()) == 7


def test_worker_processes_share_the_per_minute_limit(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_USER_DAILY", "1000")
    monkeypatch.setenv("FREE_DOC_AI_RATE_PER_MIN", "5")
    results = _run_children(_child_acquire, [("document", 42, 4)] * 4)
    assert sum(results) == 5


def _child_requests(queue, attempts):
    before = len(requests.post.calls)
    for _ in range(attempts):
        _structure(_client())
    queue.put(len(requests.post.calls) - before)


def test_forked_app_workers_share_guest_limits_end_to_end(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_GUEST_DAILY", "100")
    monkeypatch.setenv("FREE_DOC_AI_GUEST_IP_DAILY", "4")
    monkeypatch.setenv("FREE_DOC_AI_RATE_PER_MIN", "0")
    results = _run_children(_child_requests, [(3,)] * 4)
    assert sum(results) == 4


# ------------------------------------------------------------------- 13. provider failure


def test_provider_failure_keeps_the_unit_and_hides_provider_errors(provider, monkeypatch):
    monkeypatch.setenv("FREE_DOC_AI_GUEST_DAILY", "2")
    provider.fail = True
    guest = _client()
    failed = [_structure(guest) for _ in range(2)]
    for res in failed:
        assert res.status_code == 503
        body = res.get_data(as_text=True)
        assert "AIza" not in body and "/srv/" not in body and "error_message" not in body
    calls_after_failures = provider.count("document")
    assert calls_after_failures >= 2
    third = _structure(guest)
    assert third.status_code == 200 and third.get_json()["ai_powered"] is False
    assert provider.count("document") == calls_after_failures  # no third round of provider calls


def test_brief_v2_provider_failure_is_not_refunded_but_pre_provider_failure_is(provider, monkeypatch):
    from formatter_v2 import smartform as smartform_mod

    monkeypatch.setenv("FORMATTER_V2_ENABLED", "1")
    owner = _user("student@example.com")
    client = _signed_in(_client(), owner)

    def extract_via_provider(brief, gemini):
        gemini.generate(system_instruction="v2 brief", user_message=brief, temperature=0.0,
                        response_mime_type="application/json", response_schema={}, timeout_s=10)
        raise AssertionError("unreachable")

    monkeypatch.setattr(smartform_mod, "extract_requirements", extract_via_provider)
    provider.fail = True
    res = client.post("/api/extract-requirements-v2", data={"requirements_text": "Arial 12."})
    assert res.status_code == 502 and "AIza" not in res.get_data(as_text=True)
    assert _used(f"brief:user:{owner['id']}") == 1

    def fails_before_provider(brief, gemini):
        raise RuntimeError("parser bug")

    monkeypatch.setattr(smartform_mod, "extract_requirements", fails_before_provider)
    assert client.post("/api/extract-requirements-v2", data={"requirements_text": "Arial 12."}).status_code == 502
    assert _used(f"brief:user:{owner['id']}") == 1


# ------------------------------------------------------------------- 14. reservations


def test_reservations_release_once_and_only_their_own_units(provider):
    first = free_ai_quota.grant_for("document", user_id=77, email_verified=True, guest_subject=None, guest_ip_subject=None)
    second = free_ai_quota.grant_for("document", user_id=77, email_verified=True, guest_subject=None, guest_ip_subject=None)
    assert first.id != second.id and len(first.id) == 32
    assert first.acquire() and second.acquire()
    assert _used("docai:user:77") == 2

    assert first.release_if_unused() is True
    assert first.release_if_unused() is False
    assert free_ai_quota._set_status(first.id, free_ai_quota.RELEASED) is False
    assert _used("docai:user:77") == 1
    assert free_ai_quota.reservation_status(second.id) == free_ai_quota.RESERVED

    second.note_provider_call()
    assert second.release_if_unused() is False  # the provider was contacted
    second.finish()
    assert free_ai_quota._set_status(second.id, free_ai_quota.RELEASED) is False
    assert _used("docai:user:77") == 1
    assert free_ai_quota._set_status("not-a-reservation", free_ai_quota.RELEASED) is False


def _child_release(queue, reservation_id):
    queue.put(free_ai_quota._set_status(reservation_id, free_ai_quota.RELEASED))


def test_parallel_processes_cannot_double_release(provider):
    keep = free_ai_quota.grant_for("document", user_id=78, email_verified=True, guest_subject=None, guest_ip_subject=None)
    target = free_ai_quota.grant_for("document", user_id=78, email_verified=True, guest_subject=None, guest_ip_subject=None)
    assert keep.acquire() and target.acquire()
    results = _run_children(_child_release, [(target.id,)] * 4)
    assert sorted(results) == [False, False, False, True]
    assert _used("docai:user:78") == 1


def test_reservation_ids_never_leave_the_server(provider):
    guest = _client()
    responses = [_structure(guest), _check(guest), _format(guest)]
    ids = _reservation_ids()
    assert ids
    for res in responses:
        blob = res.get_data(as_text=False)
        headers = " ".join(f"{k}:{v}" for k, v in res.headers.items())
        for rid in ids:
            assert rid.encode() not in blob and rid not in headers


# ------------------------------------------------------------------- 15. paid workflows


def test_paid_workflow_runs_without_any_free_allowance(refund_app, provider, monkeypatch):
    for name in ("FREE_DOC_AI_USER_DAILY", "ASSIGNMENT_ANALYZE_USER_DAILY", "SMARTFORM_USER_DAILY", "FORMAT_CHAT_USER_DAILY"):
        monkeypatch.setenv(name, "0")
    owner = _user("payer@example.com")
    project_id, coins = _paid_project(refund_app, owner)
    client = _signed_in(_client(), owner)
    assert client.post(_url(project_id, "research")).status_code == 200
    assert client.post(_url(project_id, "blueprint")).status_code == 200
    assert _reservation_ids() == []

    from services import gemini_client

    with refund_app.app.app.test_request_context(_url(project_id, "writer/advance"), method="POST"):
        data, _diag = gemini_client.generate_json(system_prompt="paid stage", user_prompt="u")
    assert data == {"ok": True} and provider.count(None) == 1  # paid pipeline calls are not metered here


# ------------------------------------------------------------------- 16. non-AI formatting


def test_non_ai_formatting_works_without_gemini_or_allowance(provider, monkeypatch):
    provider.forbid = True
    for name in ("FREE_DOC_AI_GUEST_DAILY", "FREE_DOC_AI_GUEST_IP_DAILY"):
        monkeypatch.setenv(name, "0")
    guest = _client()
    formatted = _format(guest)
    assert formatted.status_code == 200 and formatted.data[:2] == b"PK" and _docx_text(formatted)
    assert formatted.headers["X-AI-Quota"] == "FREE_LIMIT_REACHED"
    assert _preview(guest).get_json()["html"]
    checked = _check(guest).get_json()
    assert "error" not in checked and checked["meta"]["compliance_analysis"]["summary"]
    assert _structure(guest).get_json()["recovery_mode"] == "reconstructed"

    monkeypatch.delenv("GOOGLE_API_KEY")
    plain = _format(_client())
    assert plain.status_code == 200 and "X-AI-Quota" not in plain.headers
    assert provider.count() == 0 and _reservation_ids() == []


# ------------------------------------------------------------------- 17. feature flags


def test_disabled_flags_and_missing_keys_never_reach_the_provider(provider, monkeypatch):
    provider.forbid = True
    user = _signed_in(_client(), _user("student@example.com"))
    monkeypatch.setenv("FORMATTER_V2_ENABLED", "0")
    assert user.post("/api/extract-requirements-v2", data={"requirements_text": "Arial"}).status_code == 404
    assert user.post("/api/format-v2/chat", data={"pasted_text": "Body.", "message": "1.5"}).status_code == 404
    monkeypatch.delenv("GOOGLE_API_KEY")
    assert _structure(user).get_json()["recovery_mode"] == "reconstructed"
    assert user.post("/parse-requirements", json={"text": "Arial 12 pt"}).get_json()["mock"] is True
    assert provider.count() == 0 and _reservation_ids() == []


def test_format_chat_is_verified_only_and_bounded(provider, monkeypatch):
    from formatter_v2.chat import apply as chat_apply
    from formatter_v2 import pipeline as v2_pipeline
    from formatter_v2.pipeline import FormatV2Result
    from formatter_v2.spec import UserOverrides

    def edit_via_provider(message, overrides, style, client):
        client.generate(system_instruction="chat", user_message=message, temperature=0.0,
                        response_mime_type="application/json", response_schema={}, timeout_s=10)
        return UserOverrides(line_spacing=1.5), "line spacing → 1.5", []

    monkeypatch.setattr(chat_apply, "apply_chat_edit", edit_via_provider)
    monkeypatch.setattr(v2_pipeline, "format_document_v2",
                        lambda *a, **k: FormatV2Result(docx_bytes=b"PK\x03\x04fake", notices=[], extractor_name="word_styles"))
    monkeypatch.setenv("FORMATTER_V2_ENABLED", "1")
    monkeypatch.setenv("FORMAT_CHAT_USER_DAILY", "1")
    form = {"pasted_text": "Body text.", "message": "1.5 spacing", "overrides": "{}", "format_style": "apa7"}
    assert _client().post("/api/format-v2/chat", data=form).status_code == 403
    unverified = _signed_in(_client(), _user("new@example.com", verified=False))
    res = unverified.post("/api/format-v2/chat", data=form)
    assert res.status_code == 403 and res.get_json()["error"] == "EMAIL_NOT_VERIFIED"
    verified = _signed_in(_client(), _user("student@example.com"))
    assert verified.post("/api/format-v2/chat", data=form).status_code == 200
    again = verified.post("/api/format-v2/chat", data=form)
    assert again.status_code == 429 and again.get_json()["error"] == "FREE_LIMIT_REACHED"
    assert provider.count("format_chat") == 1


# ------------------------------------------------------------------- 18. Formatter V2 brief limits unchanged


@pytest.fixture()
def v2_brief(provider, monkeypatch):
    from formatter_v2 import smartform as smartform_mod
    from formatter_v2.spec import UserOverrides

    calls: list[str] = []

    def fake_extract(brief, client):
        calls.append("extract")
        return SimpleNamespace(style=None, warnings=[], unsupported=[])

    monkeypatch.setattr(smartform_mod, "extract_requirements", fake_extract)
    monkeypatch.setattr(smartform_mod, "to_user_overrides",
                        lambda e, p: SimpleNamespace(overrides=UserOverrides(font_size_pt=12), evidence_by_field={}))
    monkeypatch.setenv("FORMATTER_V2_ENABLED", "1")
    return calls


BRIEF = {"requirements_text": "Font: Times New Roman, 12 pt.", "format_style": "apa7"}


def test_v2_brief_defaults_for_verified_users(v2_brief, monkeypatch):
    monkeypatch.setenv("SMARTFORM_RATE_PER_MIN", "0")
    user = _user("student@example.com")
    client = _signed_in(_client(), user)
    codes = [client.post("/api/extract-requirements-v2", data=BRIEF).status_code for _ in range(21)]
    assert codes == [200] * 20 + [429]
    last = client.post("/api/extract-requirements-v2", data=BRIEF).get_json()
    assert last["error"] == "FREE_LIMIT_REACHED"
    assert last["message"] == "You have used today’s brief readings. Fill the settings in by hand or come back tomorrow."
    assert _used(f"brief:user:{user['id']}") == 20


def test_v2_brief_defaults_for_guests(v2_brief, monkeypatch):
    monkeypatch.setenv("SMARTFORM_RATE_PER_MIN", "0")
    guest = _client()
    codes = [guest.post("/api/extract-requirements-v2", data=BRIEF).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 403]
    body = guest.post("/api/extract-requirements-v2", data=BRIEF).get_json()
    assert body["error"] == "REGISTER_REQUIRED" and body["reason"] == "FREE_LIMIT_REACHED"
    assert body["message"] == "You have used today’s free brief readings. Create a free account to read more briefs."
    fresh = [_client().post("/api/extract-requirements-v2", data=BRIEF).status_code for _ in range(8)]
    assert fresh == [200] * 7 + [403]  # 10 per IP per day, whatever the cookies


def test_v2_brief_rate_limit_and_size_cap_defaults(v2_brief):
    client = _signed_in(_client(), _user("student@example.com"))
    codes = [client.post("/api/extract-requirements-v2", data=BRIEF).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]
    limited = client.post("/api/extract-requirements-v2", data=BRIEF)
    assert limited.get_json()["error"] == "RATE_LIMITED" and limited.headers["Retry-After"] == "60"
    too_long = client.post("/api/extract-requirements-v2", data={**BRIEF, "requirements_text": "x" * 30_001})
    assert too_long.status_code == 400 and too_long.get_json()["error"] == "BRIEF_TOO_LONG"
    assert len(v2_brief) == 5
