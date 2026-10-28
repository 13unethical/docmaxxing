import json

from services.humanizer_training.section_sft import (
    build_section_sft,
    section_pairs,
    split_for,
    split_sections,
    system_prompt,
)


def _para(seed: str, n: int = 60) -> str:
    return " ".join(f"{seed}{i}" for i in range(n)) + "."


def _rewrite(text: str) -> str:
    return " ".join(f"r{w}" for w in text.split())


def _doc(doc_id: str, *, level: int = 6, titles=("Introduction", "Analysis", "Conclusion"), **over):
    sections = [(t, _para(f"{t.lower()}{doc_id}")) for t in titles]
    source = "\n\n".join(f"## {t}\n\n{body}" for t, body in sections)
    source += "\n\n## References\n\nSmith, J. (2020). A book. Press."
    teacher = "\n\n".join(f"## {t}\n\n{_rewrite(body)}" for t, body in sections)
    teacher += "\n\n## References\n\nSmith, J. (2020). A book. Press."
    doc = {
        "document_id": doc_id,
        "status": "accepted",
        "source_kind": "claude_pool",
        "source_writer": "gemini-3.5-flash",
        "teacher_model": "Legacy 5.1",
        "teacher_level": level,
        "teacher_meta": {"selection_verified": True, "verified_model": "Legacy 5.1", "verified_level": level},
        "source_text": source,
        "teacher_text": teacher,
    }
    doc.update(over)
    return doc


def _write_run(root, docs, name="batch-000001"):
    run = root / "data/humanizer_training/bulk/2026-10-26" / name
    run.mkdir(parents=True)
    (run / "documents.jsonl").write_text("".join(json.dumps(d) + "\n" for d in docs))


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_split_sections_and_level_prompt():
    body = "## A\n\nfirst\n\n## B\n\nsecond"
    assert split_sections(body) == [("A", "first"), ("B", "second")]
    assert "Rewrite strength: 4/10." in system_prompt(4)


def test_builds_level_conditioned_section_examples(tmp_path):
    _write_run(tmp_path, [_doc("d1", level=4), _doc("d2", level=10)])
    out = tmp_path / "out"
    manifest = build_section_sft(root=tmp_path, output_dir=out)

    assert manifest["documents_used"] == 2
    assert sum(manifest["examples"].values()) == 6
    assert manifest["examples_by_level"] == {"10": 3, "4": 3}
    rows = []
    for name in ("train", "val", "test"):
        rows += _rows(out / f"{name}.jsonl")
    first = rows[0]["messages"]
    assert [m["role"] for m in first] == ["system", "user", "assistant"]
    assert "##" not in first[1]["content"] and "References" not in first[1]["content"]
    assert first[2]["content"].startswith("r")
    meta = _rows(out / "examples_meta.jsonl")
    assert {m["writer"] for m in meta} == {"gemini-3.5-flash"}


def test_rejects_unverified_template_and_mismatched_documents(tmp_path):
    bad_level = _doc("d1")
    bad_level["teacher_meta"]["verified_level"] = 8
    differ = _doc("d4")
    differ["teacher_text"] = differ["teacher_text"].replace("## Analysis", "## Discussion")
    _write_run(
        tmp_path,
        [bad_level, _doc("d2", source_kind="template"), _doc("d3", status="rejected"), differ, _doc("d5"), _doc("d5")],
    )
    manifest = build_section_sft(root=tmp_path, output_dir=tmp_path / "out")
    assert manifest["documents_used"] == 1
    assert manifest["document_rejects"] == {
        "LEVEL_NOT_VERIFIED": 1,
        "TEMPLATE_SOURCE": 1,
        "NOT_ACCEPTED": 1,
        "HEADINGS_DIFFER": 1,
        "DUPLICATE_DOCUMENT": 1,
    }


def test_section_filters_drop_unchanged_and_bad_ratio(tmp_path):
    doc = _doc("d1")
    src_intro = _para("introductiond1")
    doc["teacher_text"] = doc["teacher_text"].replace(_rewrite(src_intro), src_intro)
    doc["teacher_text"] = doc["teacher_text"].replace(_rewrite(_para("analysisd1")), "rshort text only.")
    _write_run(tmp_path, [doc])
    manifest = build_section_sft(root=tmp_path, output_dir=tmp_path / "out")
    assert manifest["section_rejects"] == {"UNCHANGED": 1, "LENGTH_RATIO": 1}
    assert sum(manifest["examples"].values()) == 1


def test_sections_with_merged_paragraphs_are_dropped(tmp_path):
    doc = _doc("d1", titles=("Introduction",))
    body = _para("aa") + "\n\n" + _para("bb")
    doc["source_text"] = f"## Introduction\n\n{body}"
    doc["teacher_text"] = f"## Introduction\n\n{_rewrite(body)}"
    _write_run(tmp_path, [doc])
    manifest = build_section_sft(root=tmp_path, output_dir=tmp_path / "out")
    assert manifest["section_rejects"] == {"PARAGRAPHS_MERGED": 1}


def test_long_sections_chunk_on_matching_paragraphs():
    paras = [_para(f"p{i}", 250) for i in range(4)]
    source = "\n\n".join(paras)
    target = "\n\n".join(_rewrite(p) for p in paras)
    chunks, why = section_pairs(source, target)
    assert why is None
    assert len(chunks) == 2
    assert all(len(s.split()) <= 600 for s, _ in chunks)
    assert chunks[0][1] == "\n\n".join(_rewrite(p) for p in paras[:2])

    chunks, why = section_pairs(source, _rewrite(source))
    assert len(chunks) == 1 and why is None

    longer = source + "\n\n" + _para("p9", 250)
    chunks, why = section_pairs(longer, _rewrite(longer))
    assert chunks == [] and why == "LONG_SECTION_UNALIGNED"


def test_split_is_stable_per_document():
    assert split_for("doc-1") == split_for("doc-1")
    splits = [split_for(f"doc-{i}") for i in range(2000)]
    assert 0.85 < splits.count("train") / 2000 < 0.95
    assert splits.count("test") > 40
