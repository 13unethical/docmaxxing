import json

from scripts import tt_detector_labels as labels


def _sentences(n, word="word"):
    return " ".join(f"This is sentence {i} with {word} {word} {word} {word} {word}." for i in range(n))


def test_windows_share_of_highlighted_letters():
    text = _sentences(30)
    half = len(text) // 2
    flags = [i < half for i in range(len(text))]
    rows = list(labels.windows(text, flags))
    assert len(rows) >= 2
    assert all(len(r["text"].split()) >= 40 for r in rows)
    assert rows[0]["ai_frac"] == 1.0
    assert rows[-1]["ai_frac"] == 0.0


def test_windows_skip_references():
    text = _sentences(12) + " Smith, J. (2019). Title. Retrieved from https://example.com/x."
    rows = list(labels.windows(text, [False] * len(text)))
    assert all("https://" not in r["text"] for r in rows)


def test_build_labels_each_report_once(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    for name in ("a", "b"):
        (reports / name).mkdir(parents=True)
        (reports / name / "x_ai_report.pdf").write_bytes(b"%PDF")
    calls = []

    def fake_label(folder):
        calls.append(folder.name)
        return "ok", [{"text": f"{folder.name} text", "ai_frac": 1.0, "report": folder.name, "ai": True}]

    monkeypatch.setattr(labels, "label_report", fake_label)
    out = tmp_path / "out"
    first = labels.build(reports, out)
    assert first["reports"] == 2 and first["labelled_now"] == 2 and first["windows"] == 2
    second = labels.build(reports, out)
    assert second["labelled_now"] == 0 and second["windows"] == 2
    assert calls == ["a", "b"]
    rows = [json.loads(line) for line in (out / "labels.jsonl").read_text().splitlines()]
    assert {r["report"] for r in rows} == {"a", "b"}


def test_build_skips_failed_reports(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    (reports / "bad").mkdir(parents=True)

    def boom(folder):
        raise ValueError("broken pdf")

    monkeypatch.setattr(labels, "label_report", boom)
    stats = labels.build(reports, tmp_path / "out")
    assert stats["reports"] == 0 and stats["windows"] == 0
