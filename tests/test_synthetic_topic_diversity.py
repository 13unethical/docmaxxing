"""Unit tests for synthetic topic catalog + diverse document briefs (no browser)."""

from __future__ import annotations

from services.humanizer_training.teacher.documents.generator import (
    generate_documents,
    summarize_document_plan,
)
from services.humanizer_training.teacher.documents.topic_catalog import (
    ANGLES,
    DOCUMENT_TYPES,
    DOCUMENT_TYPE_LABELS,
    DOMAINS,
    LENGTH_TARGETS,
    TOPICS_BY_DOMAIN,
    assert_no_duplicate_combinations,
    catalog_stats,
    select_document_briefs,
)


def test_catalog_counts_and_valid_types():
    stats = catalog_stats()
    assert stats["domains"] == 14
    assert stats["topics"] == 70  # 14 domains × 5 topics
    assert stats["document_types"] == 7
    assert stats["angles"] == 12
    assert stats["unique_combinations"] == 70 * 7 * 12
    assert set(DOMAINS) == set(TOPICS_BY_DOMAIN)
    for domain in DOMAINS:
        assert len(TOPICS_BY_DOMAIN[domain]) >= 4
    for dt in DOCUMENT_TYPES:
        assert dt in DOCUMENT_TYPE_LABELS
        assert "essay" in DOCUMENT_TYPE_LABELS[dt] or "report" in DOCUMENT_TYPE_LABELS[dt] or "analysis" in DOCUMENT_TYPE_LABELS[dt] or "discussion" in DOCUMENT_TYPE_LABELS[dt]


def test_deterministic_selection_same_seed():
    a = select_document_briefs(count=20, seed=4242)
    b = select_document_briefs(count=20, seed=4242)
    assert [x.combination_key for x in a] == [x.combination_key for x in b]
    assert [x.generation_prompt for x in a] == [x.generation_prompt for x in b]


def test_different_samples_different_combinations():
    briefs = select_document_briefs(count=40, seed=77)
    assert_no_duplicate_combinations(briefs)
    keys = [b.combination_key for b in briefs]
    assert len(keys) == len(set(keys))
    # Consecutive samples differ
    for i in range(1, len(briefs)):
        assert briefs[i].combination_key != briefs[i - 1].combination_key


def test_topic_domain_diversity_in_selection():
    briefs = select_document_briefs(count=50, seed=909)
    domains = {b.domain for b in briefs}
    topics = {b.topic for b in briefs}
    types = {b.document_type for b in briefs}
    angles = {b.angle for b in briefs}
    assert len(domains) >= 8
    assert len(topics) >= 15
    assert len(types) >= 5
    assert len(angles) >= 6
    assert domains.issubset(set(DOMAINS))
    assert types.issubset(set(DOCUMENT_TYPES))
    assert angles.issubset(set(ANGLES))


def test_word_count_target_configuration():
    assert LENGTH_TARGETS[0] == ("4500_5000", 0.90, 4500, 5000)
    assert LENGTH_TARGETS[1] == ("3000_4500", 0.10, 3000, 4500)
    docs, plan = generate_documents(count=20, seed=501)
    assert plan.length_buckets["4500_5000"] == 18
    assert plan.length_buckets["3000_4500"] == 2
    assert all(d.word_count <= 5000 for d in docs)
    assert all(d.body_word_count <= 5000 for d in docs)


def test_generated_metadata_written_correctly():
    docs, plan = generate_documents(count=10, seed=333)
    assert len(plan.combinations) == 10
    assert len(set(plan.combinations)) == 10
    summary = summarize_document_plan(plan)
    assert summary["unique_combinations"] == 10
    for d in docs:
        assert d.domain in DOMAINS
        assert d.topic in TOPICS_BY_DOMAIN[d.domain]
        assert d.document_type in DOCUMENT_TYPES
        assert d.angle in ANGLES
        assert d.combination_key == f"{d.domain}|{d.topic}|{d.document_type}|{d.angle}"
        assert d.generation_prompt
        assert "StealthWriter" not in d.generation_prompt
        assert "Turnitin" not in d.source_text
        assert "humanization" not in d.source_text.lower()
        assert "## " in d.source_text


def test_example_ten_sequential_combinations_for_report():
    briefs = select_document_briefs(count=10, seed=560904)
    combos = [
        {
            "domain": b.domain,
            "topic": b.topic,
            "document_type": b.document_type,
            "angle": b.angle,
        }
        for b in briefs
    ]
    assert len(combos) == 10
    assert len({(c["domain"], c["topic"], c["document_type"], c["angle"]) for c in combos}) == 10
    # Stable snapshot for the final report (seed fixed).
    assert combos[0]["domain"] in DOMAINS
