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


def test_titles_and_headings_of_any_level_stay_verbatim():
    blocks = [
        "# Artificial Intelligence: Its Impact on Modern Society",
        "### Ethical Concerns",
        "Artificial Intelligence and the Future of Work",
        PARA,
        "AI is changing how people work.",
    ]
    assert plan_chunks("\n\n".join(blocks), "\n\n", chunk_words=1) == [
        (blocks[0], False),
        (blocks[1], False),
        (blocks[2], False),
        (PARA, True),
        (blocks[4], True),
    ]


def test_paragraphs_hard_wrapped_by_a_pdf_are_joined_and_rewritten():
    page_one = (
        "Streaming platforms and digital entertainment ecosystems occupy a central position in shaping\n"
        "contemporary global culture, acting as primary arbiters of which stories reach audiences\n"
        "and which remain invisible.\n"
        "Methodology\n"
        "This audit compares two platforms over a two-week window in October and records how each\n"
        "one presents diverse social groups across new series, films and promotional banners on its"
    )
    page_two = (
        "home page, along with the metadata that describes them in the catalogue and in the\n"
        "recommendation rows shown to new subscribers."
    )
    address = "Jane Doe\nDepartment of History\nOctober 2026"
    bullets = "- first point of the list here\n- second point of the list here"
    table = "Term | Definition\nPitch | How high or low a sound is, as heard by the listener."
    lines = page_one.split("\n")
    body = "\n\n".join([page_one, page_two, address, bullets, table])
    assert plan_chunks(body, "\n\n", chunk_words=1) == [
        (" ".join(lines[:3]), True),
        ("Methodology", False),
        (" ".join(lines[4:] + page_two.split("\n")), True),
        (address, False),
        (bullets, False),
        (table, False),
    ]


def test_a_short_first_line_that_runs_on_is_not_taken_for_a_heading():
    block = (
        "Trade among the five Central Asian countries has nearly\n"
        "doubled in five years. For farmers, drivers, shopkeepers and graduates, it\n"
        "brings real chances and real risks."
    )
    assert plan_chunks(block + "\n\n" + PARA, "\n\n", chunk_words=1) == [
        (" ".join(block.split("\n")), True),
        (PARA, True),
    ]


def test_references_inside_a_wrapped_page_are_kept_verbatim():
    head, tail = PARA.split(" Researchers")
    tail = "Researchers" + tail
    page = (
        f"{head}\n{tail}\n"
        "References\n"
        "Crenshaw, K. (1989). Demarginalizing the intersection of race and sex. University of Chicago Legal Forum."
    )
    def rewrite_every_word(text: str) -> str:
        return "\n\n".join(" ".join(f"x{w}" for w in p.split()) for p in text.split("\n\n"))

    out = StudentTextHumanizer(_config(), complete_fn=rewrite_every_word).humanize(page + "\n\n" + PARA)
    assert out.startswith("xThe xstudy")
    assert out.endswith("References\n\nCrenshaw, K. (1989). Demarginalizing the intersection of race and sex. "
                        "University of Chicago Legal Forum.\n\n" + PARA)


def test_a_plain_references_list_stays_in_place_up_to_the_next_section():
    entry = "Smith, J. (2020). Remote work and the modern office. Journal of Work, 1(2), 3-4."
    url_entry = "WHO (2021). Remote work guidance. https://who.int/remote"
    body = "\n\n".join([PARA, "References:", entry, url_entry, "Appendix A", PARA])
    assert sh.split_plain_references(body, "\n\n") == (
        PARA, f"References:\n\n{entry}\n\n{url_entry}", f"Appendix A\n\n{PARA}"
    )
    out = StudentTextHumanizer(_config(chunk_words=1), complete_fn=_rewrite).humanize(body)
    assert out.split("\n\n")[1:5] == ["References:", entry, url_entry, "Appendix A"]
    assert out.count("The paper explores") == 2


def test_a_heading_on_the_line_above_its_paragraph_is_split_off():
    assert plan_chunks(f"Introduction\n{PARA}", "\n\n", chunk_words=1) == [("Introduction", False), (PARA, True)]


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


def test_short_piece_returned_verbatim_is_kept_but_a_long_one_still_fails():
    short = "Revenue grew by 13 percent in 2021."
    long_para = " ".join([PARA] * 3)

    def echo_short(chunk: str) -> str:
        return chunk if chunk == short else _rewrite(chunk)

    out = StudentTextHumanizer(_config(), complete_fn=echo_short).humanize(f"{PARA}\n\n{short}")
    assert out == f"{_rewrite(PARA)}\n\n{short}"
    with pytest.raises(StudentHumanizerError, match="UNCHANGED"):
        StudentTextHumanizer(_config(), complete_fn=lambda c: c).humanize(long_para)


def test_single_spaced_pdf_text_is_unwrapped_and_its_references_kept_line_by_line():
    text = (
        "Introduction\n"
        "Streaming platforms and digital entertainment ecosystems occupy a central position in shaping\n"
        "contemporary global culture, acting as primary arbiters of which stories reach audiences\n"
        "and which remain invisible.\n"
        "This audit compares two platforms over a two-week window in October and records how each\n"
        "one presents diverse social groups across new series, films and promotional banners.\n"
        "References\n"
        "1. Smith J. (2020) Remote work and the modern office. Journal of Work, 1(2),\n"
        "3-4."
    )
    lines = text.split("\n")
    assert sh.normalize_wrapped(text) == "\n\n".join([
        "Introduction", " ".join(lines[1:4]), " ".join(lines[4:6]), "References", "\n".join(lines[7:]),
    ])
    one_paragraph_per_line = f"{PARA}\n{PARA}"
    assert sh.normalize_wrapped(one_paragraph_per_line) == one_paragraph_per_line


def test_lightly_edited_paragraph_keeps_the_most_changed_attempt():
    light = PARA.replace("study", "paper")
    lighter = PARA.replace("study", "paper").replace("sharply", "steeply")
    outputs = iter([light, PARA, lighter])
    out = StudentTextHumanizer(_config(), complete_fn=lambda _c: next(outputs)).humanize(PARA)
    assert out == lighter


def test_paragraph_split_in_two_by_the_model_is_joined_back():
    first, second = _rewrite(PARA).split(". ", 1)
    out = StudentTextHumanizer(_config(), complete_fn=lambda _c: f"{first}.\n\n{second}").humanize(PARA)
    assert out == _rewrite(PARA)


def test_multi_paragraph_chunk_must_keep_its_paragraph_count():
    text = f"{PARA}\n\n{PARA}"
    engine = StudentTextHumanizer(_config(chunk_words=sh.CHUNK_WORDS), complete_fn=lambda c: _rewrite(c).replace("\n\n", " "))
    with pytest.raises(StudentHumanizerError, match="PARAGRAPHS_CHANGED"):
        engine.humanize(text)


def test_best_of_n_keeps_the_most_rewritten_variant_that_keeps_the_numbers():
    light = PARA.replace("study", "paper")
    heavy_but_lost_number = _rewrite(PARA).replace("42", "many")
    heavy = _rewrite(PARA)
    outputs = iter([light, heavy_but_lost_number, heavy, "", light])
    engine = StudentTextHumanizer(_config(candidates=5), complete_fn=lambda _c: next(outputs))
    assert engine.humanize(PARA) == heavy


def test_surprise_pick_prefers_the_least_predictable_variant():
    a, b = sh.Candidate("text a 42", -0.4), sh.Candidate("text b 42", -1.3)
    lost = sh.Candidate("text c", -2.0)
    assert sh.pick_candidate("source 42", [a, b, lost], "surprise") == b


def test_parse_sampling():
    assert sh.parse_sampling("1.0:4, 1.2:4") == ((1.0, 4), (1.2, 4))
    assert sh.parse_sampling("x:2,0.9:99,") == ((0.9, sh.MAX_CANDIDATES),)
    assert sh.parse_sampling("") == ()


def _variants(n):
    return [_rewrite(PARA).replace("paper", f"paper{i}") for i in range(n)]


def test_detector_pick_keeps_the_variant_scored_least_ai():
    outputs = iter(_variants(4))
    probs = {v: p for v, p in zip(_variants(4), [0.9, 0.2, 0.05, 0.6])}
    engine = StudentTextHumanizer(
        _config(candidates=4, pick="detector", refine_above=0.5),
        complete_fn=lambda _c: next(outputs),
        score_fn=lambda texts: [probs[t] for t in texts],
    )
    assert engine.humanize(PARA) == _variants(4)[2]


def test_detector_pick_prefers_variants_that_keep_the_numbers():
    lost = _rewrite(PARA).replace("42", "many")
    kept = _rewrite(PARA)
    outputs = iter([lost, kept])
    engine = StudentTextHumanizer(
        _config(candidates=2, pick="detector"),
        complete_fn=lambda _c: next(outputs),
        score_fn=lambda texts: [0.0 if t == lost else 0.4 for t in texts],
    )
    assert engine.humanize(PARA) == kept


def test_detector_pick_refines_still_flagged_chunks():
    outputs = iter(_variants(6))
    probs = dict(zip(_variants(6), [0.9, 0.8, 0.7, 0.6, 0.1, 0.95]))
    calls = []

    def score(texts):
        calls.append(len(texts))
        return [probs[t] for t in texts]

    engine = StudentTextHumanizer(
        _config(sampling=((1.0, 2),), pick="detector", refine_above=0.3, refine_sampling=((1.0, 2), (1.2, 2))),
        complete_fn=lambda _c: next(outputs),
        score_fn=score,
    )
    assert engine.humanize(PARA) == _variants(6)[4]
    assert calls == [2, 4]


def test_detector_pick_skips_refine_when_already_clean():
    outputs = iter(_variants(2))
    calls = []

    def score(texts):
        calls.append(len(texts))
        return [0.1, 0.2]

    engine = StudentTextHumanizer(
        _config(candidates=2, pick="detector", refine_sampling=((1.0, 4),)),
        complete_fn=lambda _c: next(outputs),
        score_fn=score,
    )
    assert engine.humanize(PARA) == _variants(2)[0]
    assert calls == [2]


def test_detector_pick_falls_back_to_most_rewritten_when_detector_is_down():
    light = PARA.replace("study", "paper")
    heavy = _rewrite(PARA)
    outputs = iter([light, heavy])

    def down(texts):
        raise RuntimeError("detector down")

    engine = StudentTextHumanizer(_config(candidates=2, pick="detector"), complete_fn=lambda _c: next(outputs), score_fn=down)
    assert engine.humanize(PARA) == heavy


def test_conclusion_pieces_follow_heading_opener_or_last_paragraph():
    body = [("Intro text here. It goes on.", True), ("Conclusion", True), ("Wrap up. Done.", True),
            ("Another wrap. End.", True), ("References", False)]
    assert sh.conclusion_pieces(body) == {2, 3}
    assert sh.conclusion_pieces([("First point. More.", True), ("In conclusion, it works.", True)]) == {1}
    assert sh.conclusion_pieces([("First point. More.", True), ("Second point. More.", True)]) == {1}


def test_conclusion_gets_extra_variants_even_when_already_clean():
    first, last = PARA, PARA.replace("study", "survey")
    calls = []

    def complete(content):
        return _rewrite(content)

    def score(texts):
        calls.append(len(texts))
        return [0.1] * len(texts)

    engine = StudentTextHumanizer(
        _config(candidates=2, pick="detector", chunk_words=1, refine_sampling=((1.0, 4),),
                conclusion_sampling=((1.2, 3),)),
        complete_fn=complete,
        score_fn=score,
    )
    engine.max_workers = 1
    engine.humanize(f"{first}\n\n{last}")
    assert calls == [2, 2, 3]


def _ai_if_moreover(texts):
    return [0.95 if "Moreover" in t else 0.05 for t in texts]


def test_document_pick_rewrites_only_the_chunks_the_whole_text_check_flags(monkeypatch):
    from services import ai_detector

    monkeypatch.setattr(ai_detector, "WINDOW_WORDS", 1)
    paras = [PARA, PARA.replace("42", "57"), PARA.replace("42", "99")]
    seen = []

    def complete(chunk):
        seen.append(chunk)
        return ("Moreover, " if "57" in chunk and seen.count(chunk) == 1 else "") + _rewrite(chunk)

    engine = StudentTextHumanizer(_config(chunk_words=1, pick="document"), complete_fn=complete, score_fn=_ai_if_moreover)
    out = engine.humanize("\n\n".join(paras))
    assert out.split("\n\n") == [_rewrite(p) for p in paras]
    assert sorted(seen) == sorted([paras[0], paras[1], paras[1], paras[2]])


def test_document_pick_keeps_the_current_text_when_rewrites_are_no_better(monkeypatch):
    from services import ai_detector

    monkeypatch.setattr(ai_detector, "WINDOW_WORDS", 1)
    first = "Moreover, " + _rewrite(PARA)
    worse = "Moreover, furthermore, " + _rewrite(PARA)
    outputs = iter([first, worse, worse, worse])

    def score(texts):
        return [0.99 if "furthermore" in t else 0.9 if "Moreover" in t else 0.05 for t in texts]

    engine = StudentTextHumanizer(_config(pick="document", doc_rounds=3), complete_fn=lambda _c: next(outputs), score_fn=score)
    assert engine.humanize(PARA) == first


def test_document_pick_returns_the_first_pass_when_the_detector_is_down():
    def down(texts):
        raise RuntimeError("detector down")

    engine = StudentTextHumanizer(_config(pick="document"), complete_fn=_rewrite, score_fn=down)
    assert engine.humanize(PARA) == _rewrite(PARA)


def test_sampling_plan_sends_one_request_per_temperature(monkeypatch):
    sent = []

    class _Resp:
        status_code = 200

        def __init__(self, n):
            self.n = n

        def json(self):
            return {"choices": [{"message": {"content": f"v{i}"}} for i in range(self.n)]}

    def fake_post(url, headers, json, timeout):
        sent.append((json["temperature"], json["n"]))
        return _Resp(json["n"])

    monkeypatch.setattr(sh.requests, "post", fake_post)
    engine = StudentTextHumanizer(_config(sampling=((1.0, 3), (1.2, 2))))
    assert len(engine._candidates(PARA)) == 5
    assert sorted(sent) == [(1.0, 3), (1.2, 2)]


def test_sampling_plan_survives_one_failed_temperature(monkeypatch):
    class _Resp:
        def __init__(self, ok):
            self.status_code = 200 if ok else 500
            self.text = "boom"

        def json(self):
            return {"choices": [{"message": {"content": "v"}}]}

    monkeypatch.setattr(sh.requests, "post", lambda url, headers, json, timeout: _Resp(json["temperature"] == 1.0))
    engine = StudentTextHumanizer(_config(sampling=((1.0, 1), (1.2, 1))))
    assert [c.text for c in engine._candidates(PARA)] == ["v"]


def test_student_config_reads_detector_settings(monkeypatch):
    monkeypatch.setenv("HUMANIZER_STUDENT_PICK", "detector")
    monkeypatch.setenv("HUMANIZER_STUDENT_SAMPLING", "1.0:4,1.2:4")
    monkeypatch.setenv("HUMANIZER_STUDENT_REFINE_SAMPLING", "1.0:12,1.2:12")
    monkeypatch.setenv("HUMANIZER_STUDENT_REFINE_ABOVE", "0.25")
    monkeypatch.setenv("HUMANIZER_STUDENT_DOC_ROUNDS", "2")
    monkeypatch.setenv("HUMANIZER_STUDENT_DOC_BUDGET", "30")
    cfg = sh.student_config()
    assert cfg.pick == "detector"
    assert cfg.sampling_plan == ((1.0, 4), (1.2, 4))
    assert cfg.refine_sampling == ((1.0, 12), (1.2, 12))
    assert cfg.refine_above == 0.25
    assert (cfg.doc_rounds, cfg.doc_budget) == (2, 30.0)


def test_candidates_are_read_from_every_choice_with_logprobs(monkeypatch):
    sent = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {"message": {"content": "one"}, "logprobs": {"content": [{"logprob": -1.0}, {"logprob": -3.0}]}},
                    {"message": {"content": "two"}, "logprobs": None},
                ]
            }

    def fake_post(url, headers, json, timeout):
        sent.update(json)
        return _Resp()

    monkeypatch.setattr(sh.requests, "post", fake_post)
    engine = StudentTextHumanizer(_config(candidates=2, pick="surprise", temperature=1.2))
    assert engine._candidates(PARA) == [sh.Candidate("one", -2.0), sh.Candidate("two", 0.0)]
    assert (sent["n"], sent["logprobs"], sent["temperature"]) == (2, True, 1.2)


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


def test_rescue_waits_for_a_sleeping_model_to_boot(monkeypatch):
    probes = iter([False, False, True])
    engine = StudentTextHumanizer(_config(share=0.0), complete_fn=_rewrite)
    monkeypatch.setattr(engine, "is_warm", lambda: next(probes))
    woken = []
    monkeypatch.setattr(sh, "warm_up", lambda cfg, force=False: woken.append(force) or True)
    slept = []

    result = try_student_humanize(PARA, humanizer=engine, force=True, wait_for_boot=150, sleep=slept.append)
    assert result["provider"] == PROVIDER
    assert woken == [True]
    assert slept == [sh.BOOT_POLL_SECONDS, sh.BOOT_POLL_SECONDS]


def test_unconfigured_model_never_waits(monkeypatch):
    engine = StudentTextHumanizer(_config(url=""))
    monkeypatch.setattr(engine, "is_warm", lambda: pytest.fail("must not probe an unconfigured model"))
    assert try_student_humanize(PARA, humanizer=engine, force=True, wait_for_boot=150) is None


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
    monkeypatch.setattr(app_mod, "_student_humanize", lambda _t, **_k: _student_result())
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

    monkeypatch.setattr(app_mod, "_student_humanize", lambda _t, **_k: _student_result())
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


class _FailedJob:
    id = "sw-1"
    error_code = "LOGIN_REQUIRED"
    error = "StealthWriter session is not logged in."
    error_details = None
    is_terminal = True
    max_retries = 0

    class status:  # noqa: N801
        value = "FAILED"


def _stealthwriter_logged_out(monkeypatch):
    import app as app_mod

    class _Jobs:
        def create(self, *a, **k):
            return _FailedJob()

        def wait(self, *a, **k):
            return None

        def get(self, _id):
            return _FailedJob()

    class _Worker:
        job_timeout = 1

    monkeypatch.setattr(app_mod, "ensure_engine_started", lambda: None)
    monkeypatch.setattr(app_mod, "job_manager", _Jobs())
    monkeypatch.setattr(app_mod, "browser_worker", _Worker())
    monkeypatch.setattr(app_mod, "health_monitor", None)
    monkeypatch.setattr(app_mod, "_stealthwriter_down_until", 0.0)


def test_site_humanize_falls_back_to_student_when_stealthwriter_is_logged_out(economy, monkeypatch):
    import app as app_mod

    monkeypatch.setenv("FREE_HUMANIZE_ENGINE", "default")
    _stealthwriter_logged_out(monkeypatch)
    calls = []

    def fake_student(_text, *, rescue=False):
        calls.append(rescue)
        return _student_result() if rescue else None

    monkeypatch.setattr(app_mod, "_student_humanize", fake_student)
    payload = {"text": "Please rewrite this paragraph for a human reader."}

    res = _client().post("/api/browser/providers/stealthwriter/humanize", json=payload)
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["humanized_text"] == "Rewritten by our model."
    assert calls == [False, True]
    assert app_mod._stealthwriter_down()

    _client().post("/api/browser/providers/stealthwriter/humanize", json=payload)
    assert calls[2] is True


def test_extension_humanize_falls_back_to_student_when_stealthwriter_is_logged_out(economy, monkeypatch):
    import app as app_mod

    _stealthwriter_logged_out(monkeypatch)
    monkeypatch.setattr(
        app_mod, "_student_humanize", lambda _t, *, rescue=False: _student_result() if rescue else None
    )
    user = economy_auth.create_user("student-rescue@example.com", "secret123")
    economy_auth.mark_email_verified(user["id"], user["email"])
    WalletService().set_balance(user["id"], 200)

    res = _client().post(
        "/api/extension/humanize",
        json={"text": "Please rewrite this paragraph for a human reader.", "key": issue_token(user["id"])},
    )
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["humanized_text"] == "Rewritten by our model."


def test_regular_requests_wait_briefly_for_a_cold_model(monkeypatch):
    import app as app_mod

    seen = {}

    def fake_try(_text, **kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr(sh, "try_student_humanize", fake_try)
    assert app_mod._student_humanize("Some text.") is None
    assert seen == {"wait_for_boot": app_mod.STUDENT_COLD_WAIT_SECONDS}
