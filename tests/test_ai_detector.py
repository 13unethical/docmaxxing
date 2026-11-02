"""Free AI detector: sentence windows, document score, limits and failures."""

from __future__ import annotations

import pytest

from services import ai_detector, free_humanize
from services.economy import auth as economy_auth
from services.economy import db as economy_db

URL = "/api/detector/free"

HUMAN = (
    "I walked to the library on Tuesday because the printer at home had died again. "
    "The queue was long, so I read the first chapter while I waited. "
    "By the time my pages came out, I had already changed my mind about the introduction."
)
AI = (
    "Moreover, it is important to note that effective time management plays a pivotal role in academic success. "
    "Furthermore, it enables students to navigate the multifaceted demands of university life. "
    "In conclusion, fostering these skills is essential for long-term personal and professional growth."
)


def _fake_score(texts):
    return [0.95 if "Moreover" in t or "Furthermore" in t or "In conclusion" in t else 0.05 for t in texts], "test-v1"


def test_sentences_keep_offsets_and_skip_headings_and_references():
    text = "Introduction\n" + HUMAN + "\n\nReferences\nSmith, J. (2020). A title. https://doi.org/10/x\n"
    sentences = ai_detector.split_sentences(text)
    for s in sentences:
        assert text[s.start : s.end] == s.text
    assert [s.text for s in sentences if not s.scored] == ["Introduction", "References", sentences[-1].text]
    assert sum(s.scored for s in sentences) == 3


def test_windows_cover_every_scored_sentence_with_about_110_words():
    text = " ".join([HUMAN, AI] * 4)
    sentences = ai_detector.split_sentences(text)
    spans = ai_detector.windows(sentences)
    covered = {k for a, b in spans for k in range(a, b)}
    assert covered == set(range(len(sentences)))
    assert spans[-1][1] == len(sentences)
    for a, b in spans[:-1]:
        assert sum(s.words for s in sentences[a:b]) >= ai_detector.WINDOW_WORDS


def test_document_score_is_the_share_of_flagged_words(monkeypatch):
    monkeypatch.setattr(ai_detector, "WINDOW_WORDS", 1)
    result = ai_detector.detect(HUMAN + "\n" + AI, score=_fake_score)
    assert result["model"] == "test-v1"
    flagged = [s for s in result["sentences"] if s["flagged"]]
    assert [s["text"].split()[0] for s in flagged] == ["Moreover,", "Furthermore,", "In"]
    ai_words = sum(len(s["text"].split()) for s in flagged)
    assert result["ai_percent"] == round(100 * ai_words / result["scored_words"])
    assert result["verdict"] == "mixed"


def test_short_text_is_refused():
    assert ai_detector.detect("Too short to judge.", score=_fake_score) == {"too_short": True}


@pytest.fixture()
def economy(tmp_path, monkeypatch):
    monkeypatch.setattr(economy_db, "DB_PATH", tmp_path / "economy.db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    for name in ("FREE_DETECT_GUEST_WORDS", "FREE_DETECT_GUEST_DAILY", "FREE_DETECT_USER_WORDS", "FREE_DETECT_USER_DAILY"):
        monkeypatch.delenv(name, raising=False)
    economy_db.init_db()
    calls = []

    def fake_remote(texts):
        calls.append(len(texts))
        return _fake_score(texts)

    monkeypatch.setattr(ai_detector, "_score_remote", fake_remote)
    return calls


def _client():
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


def test_guest_check_returns_highlights_and_counts_down(economy, monkeypatch):
    monkeypatch.setenv("FREE_DETECT_GUEST_DAILY", "2")
    client = _client()
    res = client.post(URL, json={"text": HUMAN + "\n" + AI})
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["success"] is True
    assert 0 <= body["ai_percent"] <= 100
    assert body["sentences"] and {"start", "end", "ai_prob", "flagged"} <= set(body["sentences"][0])
    assert body["checks_left"] == 1
    assert client.post(URL, json={"text": HUMAN + "\n" + AI}).status_code == 200
    res = client.post(URL, json={"text": HUMAN + "\n" + AI})
    assert res.status_code == 403
    assert res.get_json()["error"] == "REGISTER_REQUIRED"
    assert len(economy) == 2


def test_guest_word_limit_and_english_only(economy, monkeypatch):
    monkeypatch.setenv("FREE_DETECT_GUEST_WORDS", "20")
    res = _client().post(URL, json={"text": HUMAN + " " + AI})
    assert res.status_code == 403
    assert res.get_json()["error"] == "FREE_WORD_LIMIT"
    monkeypatch.setenv("FREE_DETECT_GUEST_WORDS", "1500")
    res = _client().post(URL, json={"text": "Это русский текст, который детектор пока не проверяет. " * 5})
    assert res.status_code == 422
    assert res.get_json()["error"] == "ENGLISH_ONLY"
    assert economy == []


def test_failed_or_too_short_checks_are_not_counted(economy, monkeypatch):
    monkeypatch.setenv("FREE_DETECT_GUEST_DAILY", "1")

    def broken(_texts):
        raise ai_detector.DetectorUnavailable("down")

    monkeypatch.setattr(ai_detector, "_score_remote", broken)
    client = _client()
    res = client.post(URL, json={"text": HUMAN + "\n" + AI})
    assert res.status_code == 503
    assert res.get_json()["error"] == "DETECTOR_UNAVAILABLE"
    monkeypatch.setattr(ai_detector, "_score_remote", _fake_score)
    assert client.post(URL, json={"text": "Too short to judge here."}).get_json()["error"] == "TOO_SHORT"
    assert client.post(URL, json={"text": HUMAN + "\n" + AI}).status_code == 200


def test_signed_in_user_gets_the_bigger_limit(economy, monkeypatch):
    monkeypatch.setenv("FREE_DETECT_GUEST_WORDS", "20")
    user = economy_auth.create_user("detect@example.com", "secret123")
    client = _client()
    with client.session_transaction() as sess:
        sess[economy_auth.SESSION_KEY] = user["id"]
    body = client.post(URL, json={"text": HUMAN + "\n" + AI}).get_json()
    assert body["success"] is True
    assert body["checks_left"] == 49
    assert free_humanize.used_today(f"detect:user:{user['id']}") == 1
