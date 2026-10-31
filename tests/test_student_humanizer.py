"""Our own (student model) humanizer and its routing in front of StealthWriter."""

from __future__ import annotations

import pytest

from services.humanizer_engine import student_humanizer as sh
from services.humanizer_engine.student_humanizer import (
    PROVIDER,
    StudentConfig,
    StudentHumanizerError,
    StudentTextHumanizer,
    chunk_problem,
    pick_student,
    plan_chunks,
    try_student_humanize,
)

PARA = (
    "The study examines how remote work changed productivity across 42 firms in 2021. "
    "Researchers found that output rose by 13 percent while meetings declined sharply (Smith, 2020)."
)


def _config(**overrides) -> StudentConfig:
    values = dict(url="https://student.test", api_key="k", model="humanizer-v1", share=1.0, level=8, timeout=60.0)
    values.update(overrides)
    return StudentConfig(**values)


def _rewrite(text: str) -> str:
    """Deterministic stand-in for the model: swaps words, keeps paragraph breaks."""
    swaps = {"study": "paper", "examines": "explores", "changed": "shifted", "found": "showed",
             "rose": "grew", "while": "whereas", "declined": "fell", "sharply": "steeply",
             "Researchers": "Authors", "how": "the way", "across": "in", "output": "production"}
    return "\n\n".join(" ".join(swaps.get(w, w) for w in p.split()) for p in text.split("\n\n"))


def test_plan_chunks_groups_prose_and_keeps_structure_verbatim():
    body = "\n\n".join(["## Introduction", PARA, PARA, "- a list item", "[[FIGURE: map | Map]]", PARA])
    pieces = plan_chunks(body, "\n\n")
    assert pieces == [
        ("## Introduction", False),
        (f"{PARA}\n\n{PARA}", True),
        ("- a list item", False),
        ("[[FIGURE: map | Map]]", False),
        (PARA, True),
    ]


def test_plan_chunks_splits_long_prose_at_paragraph_breaks():
    body = "\n\n".join([PARA] * 30)
    chunks = [text for text, rewrite in plan_chunks(body, "\n\n") if rewrite]
    assert len(chunks) > 1
    assert all(len(c.split()) <= sh.CHUNK_WORDS for c in chunks)
    assert sum(c.count(PARA) for c in chunks) == 30


def test_plan_chunks_can_send_each_paragraph_alone():
    body = "\n\n".join([PARA] * 3)
    assert plan_chunks(body, "\n\n", chunk_words=1) == [(PARA, True)] * 3


def test_chunk_problem_rejects_broken_rewrites():
    two = f"{PARA}\n\n{PARA}"
    assert chunk_problem(two, _rewrite(two)) is None
    assert chunk_problem(two, "") == "EMPTY"
    assert chunk_problem(two, _rewrite(PARA) + " " + _rewrite(PARA)) == "PARAGRAPHS_CHANGED"
    assert chunk_problem(two, "## Heading\n\n" + _rewrite(two)) == "EXTRA_MARKUP"
    assert chunk_problem(two, "Short.\n\nShort.") == "LENGTH_RATIO"
    assert chunk_problem(two, two) == "UNCHANGED"


def test_humanize_rewrites_prose_and_keeps_headings_lists_and_references():
    text = "\n\n".join(["## Introduction", PARA, "- keep this bullet", "## Discussion", PARA,
                        "## References", "Smith, J. (2020). Remote work. Journal, 1(2), 3-4."])
    out = StudentTextHumanizer(_config(), complete_fn=_rewrite).humanize(text)
    assert "## Introduction" in out and "## Discussion" in out
    assert "- keep this bullet" in out
    assert "Smith, J. (2020). Remote work. Journal, 1(2), 3-4." in out
    assert "The paper explores" in out
    assert "The study examines" not in out


def test_humanize_keeps_single_newline_paragraphs():
    text = f"{PARA}\n{PARA}"
    out = StudentTextHumanizer(_config(), complete_fn=_rewrite).humanize(text)
    assert out.count("\n") == 1
    assert "\n\n" not in out


def test_bad_chunk_is_retried_then_raises():
    calls = []

    def merge_paragraphs(chunk: str) -> str:
        calls.append(chunk)
        return _rewrite(chunk).replace("\n\n", " ")

    engine = StudentTextHumanizer(_config(), complete_fn=merge_paragraphs)
    with pytest.raises(StudentHumanizerError):
        engine.humanize(f"{PARA}\n\n{PARA}")
    assert len(calls) == sh.ATTEMPTS


def test_flaky_chunk_recovers_on_retry():
    outputs = iter(["", _rewrite(PARA)])
    out = StudentTextHumanizer(_config(), complete_fn=lambda _c: next(outputs)).humanize(PARA)
    assert out.startswith("The paper explores")


def test_pick_student_respects_share_and_configuration():
    assert pick_student(_config(share=0.1), rng=lambda: 0.05)
    assert not pick_student(_config(share=0.1), rng=lambda: 0.5)
    assert not pick_student(_config(share=0.0), rng=lambda: 0.0)
    assert not pick_student(_config(url=""), rng=lambda: 0.0)


def test_try_student_humanize_falls_back_on_failure_and_non_english():
    ok = StudentTextHumanizer(_config(), complete_fn=_rewrite)
    result = try_student_humanize(PARA, humanizer=ok)
    assert result["provider"] == PROVIDER
    assert result["humanized_text"].startswith("The paper explores")

    broken = StudentTextHumanizer(_config(), complete_fn=lambda _c: "")
    assert try_student_humanize(PARA, humanizer=broken) is None

    russian = "Исследование показывает, как удалённая работа изменила продуктивность компаний в 2021 году."
    assert try_student_humanize(russian, humanizer=ok) is None

    off = StudentTextHumanizer(_config(share=0.0), complete_fn=_rewrite)
    assert try_student_humanize(PARA, humanizer=off) is None


def test_cold_model_falls_back_without_waiting(monkeypatch):
    probes, posts = [], []

    def slow_boot(url, *, headers, timeout):
        probes.append((url, timeout))
        raise sh.requests.Timeout("booting")

    monkeypatch.setattr(sh.requests, "get", slow_boot)
    monkeypatch.setattr(sh.requests, "post", lambda *a, **k: posts.append(a))
    assert try_student_humanize(PARA, humanizer=StudentTextHumanizer(_config())) is None
    assert probes == [("https://student.test/v1/models", 3.0)]
    assert posts == []


def test_requests_use_the_trained_prompt_and_sampling(monkeypatch):
    sent = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": _rewrite(PARA)}}]}

    def fake_post(url, *, headers, json, timeout):
        sent.update(url=url, headers=headers, body=json)
        return _Resp()

    monkeypatch.setattr(sh.requests, "post", fake_post)
    StudentTextHumanizer(_config()).humanize(PARA)
    body = sent["body"]
    assert sent["url"] == "https://student.test/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer k"
    assert body["model"] == "humanizer-v1"
    assert body["temperature"] == 1.0 and body["top_p"] == 0.9
    assert body["messages"][0]["content"].endswith("Rewrite strength: 8/10.")
    assert body["messages"][1]["content"] == PARA
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


def test_routed_requests_are_logged_with_outcome_and_speed(tmp_path, monkeypatch):
    import json

    log_path = tmp_path / "events.jsonl"
    cfg = _config(events_log=str(log_path))
    try_student_humanize(PARA, humanizer=StudentTextHumanizer(cfg, complete_fn=_rewrite))
    try_student_humanize(PARA, humanizer=StudentTextHumanizer(cfg, complete_fn=lambda _c: ""))
    monkeypatch.setattr(sh.requests, "get", lambda *a, **k: (_ for _ in ()).throw(sh.requests.Timeout("boot")))
    try_student_humanize(PARA, humanizer=StudentTextHumanizer(cfg))

    rows = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [r["outcome"] for r in rows] == ["served", "failed", "cold"]
    assert rows[0]["words"] == len(PARA.split()) and rows[0]["elapsed"] >= 0
    assert "Chunk rejected" in rows[1]["error"]


def test_warm_up_wakes_the_model_at_most_once_a_minute(monkeypatch):
    import threading

    monkeypatch.setattr(sh, "_last_warmup", float("-inf"))
    pinged = threading.Event()
    now = [1000.0]

    def ping(cfg):
        assert cfg.url == "https://student.test"
        pinged.set()

    assert sh.warm_up(_config(), clock=lambda: now[0], ping=ping)
    assert pinged.wait(2)
    now[0] += 30
    assert not sh.warm_up(_config(), clock=lambda: now[0], ping=ping)
    now[0] += 31
    assert sh.warm_up(_config(), clock=lambda: now[0], ping=ping)
    assert not sh.warm_up(_config(share=0.0), clock=lambda: now[0] + 999, ping=ping)
    assert not sh.warm_up(_config(url=""), clock=lambda: now[0] + 999, ping=ping)


def test_system_prompt_matches_training_prompt():
    from services.humanizer_training.section_sft import system_prompt as training_prompt

    assert sh.system_prompt(8) == training_prompt(8)


# --- routing in the site endpoints -------------------------------------------------------

from services.economy import auth as economy_auth  # noqa: E402
from services.economy import db as economy_db  # noqa: E402
from services.economy.wallet import WalletService  # noqa: E402
from services.veil_tokens import issue_token  # noqa: E402


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    economy_db.init_db()
    return tmp_path


def _client():
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


def _student_result():
    return {"humanized_text": "Rewritten by our model.", "elapsed_seconds": 1.5,
            "provider": PROVIDER, "engine": "docmaxxing-student-v1", "request_id": "student-abc"}


def _no_stealthwriter(monkeypatch):
    import app as app_mod

    def _boom():
        raise AssertionError("StealthWriter must not run when the student model answered")

    monkeypatch.setattr(app_mod, "ensure_engine_started", _boom)


def test_extension_humanize_uses_student_and_skips_training_log(economy, monkeypatch):
    import app as app_mod
    from services import dataset_logger

    logged = []
    monkeypatch.setattr(app_mod, "_student_humanize", lambda _t: _student_result())
    monkeypatch.setattr(dataset_logger, "log_humanization_event", lambda *a, **k: logged.append(a))
    _no_stealthwriter(monkeypatch)

    user = economy_auth.create_user("student-ext@example.com", "secret123")
    economy_auth.mark_email_verified(user["id"], user["email"])
    WalletService().set_balance(user["id"], 200)
    res = _client().post(
        "/api/extension/humanize",
        json={"text": "Please rewrite this paragraph for a human reader.", "key": issue_token(user["id"])},
    )
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["humanized_text"] == "Rewritten by our model."
    assert body["coins_charged"] > 0
    assert logged == []


def test_site_humanize_uses_student_for_guest(economy, monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod, "_student_humanize", lambda _t: _student_result())
    _no_stealthwriter(monkeypatch)

    res = _client().post(
        "/api/browser/providers/stealthwriter/humanize",
        json={"text": "Please rewrite this paragraph for a human reader."},
    )
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["success"] is True
    assert body["humanized_text"] == "Rewritten by our model."
    assert body["job_id"] == "student-abc"
    assert body["guest_trial"] is True


def test_warmup_endpoint_is_open_to_guests(economy, monkeypatch):
    calls = []
    monkeypatch.setattr(sh, "warm_up", lambda: calls.append(1) or True)

    res = _client().post("/api/humanize/warmup", json={})
    assert res.status_code == 200
    assert res.get_json() == {"success": True, "sent": True}
    assert calls == [1]
