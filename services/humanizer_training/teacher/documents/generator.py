"""Deterministic document-level synthetic generator for teacher collection."""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass

from services.humanizer_training.teacher.config import LANGUAGE
from services.humanizer_training.teacher.documents.schema import SyntheticDocument
from services.humanizer_training.teacher.documents.topic_catalog import (
    DOCUMENT_TYPES_ALLOWING_REFERENCES,
    LENGTH_TARGETS,
    DocumentBrief,
    select_document_briefs,
)

_LENGTH_TARGETS = LENGTH_TARGETS

_SECTION_POOL = (
    "Introduction",
    "Background",
    "Literature Review",
    "Theoretical Framework",
    "Methodology",
    "Analysis",
    "Findings",
    "Discussion",
    "Implications",
    "Limitations",
    "Conclusion",
)


@dataclass(slots=True)
class DocumentSamplingPlan:
    document_types: dict[str, int]
    domains: dict[str, int]
    topics: dict[str, int]
    angles: dict[str, int]
    length_buckets: dict[str, int]
    with_references: int
    section_count_histogram: dict[int, int]
    combinations: list[str]


def generate_documents(
    *,
    count: int,
    seed: int,
    domain: str | None = None,
) -> tuple[list[SyntheticDocument], DocumentSamplingPlan]:
    if count <= 0:
        empty = DocumentSamplingPlan({}, {}, {}, {}, {}, 0, {}, [])
        return [], empty

    rng = random.Random(seed)
    briefs = select_document_briefs(count=count, seed=seed)
    if domain:
        # Optional hard filter for focused runs (still unique within filtered set).
        normalized = domain.strip().lower()
        filtered = [b for b in briefs if b.domain == normalized]
        if not filtered:
            raise ValueError(f"Unsupported or unused domain filter: {domain}")
        # Re-select from catalog filtered by domain if caller forces one domain.
        from services.humanizer_training.teacher.documents.topic_catalog import (
            ANGLES,
            DOCUMENT_TYPES,
            TOPICS_BY_DOMAIN,
            build_generation_prompt,
        )

        if normalized not in TOPICS_BY_DOMAIN:
            raise ValueError(f"Unsupported domain: {domain}")
        pool = []
        for topic in TOPICS_BY_DOMAIN[normalized]:
            for doc_type in DOCUMENT_TYPES:
                for angle in ANGLES:
                    pool.append((normalized, topic, doc_type, angle))
        if count > len(pool):
            raise ValueError(
                f"Requested {count} docs but domain {normalized} has only {len(pool)} combinations"
            )
        local = random.Random(seed)
        local.shuffle(pool)
        briefs = [
            DocumentBrief(
                domain=d,
                topic=t,
                document_type=dt,
                angle=a,
                seed=seed,
                index=i,
                generation_prompt=build_generation_prompt(
                    domain=d, topic=t, document_type=dt, angle=a
                ),
            )
            for i, (d, t, dt, a) in enumerate(pool[:count])
        ]

    length_specs = _allocate_length_specs(count)

    docs: list[SyntheticDocument] = []
    domain_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    topic_counts: dict[str, int] = {}
    angle_counts: dict[str, int] = {}
    length_counts = {name: 0 for name, _, _, _ in _LENGTH_TARGETS}
    section_hist: dict[int, int] = {}
    with_refs = 0
    combinations: list[str] = []

    for index, brief in enumerate(briefs):
        bucket, low, high = length_specs[index]
        target_words = int((low + high) / 2)
        jitter = rng.randint(-min(80, (high - low) // 4), min(80, (high - low) // 4))
        target_words = max(low, min(high, target_words + jitter))

        text, section_titles, refs_present = _build_document(
            rng=rng,
            brief=brief,
            target_words=target_words,
        )
        body, refs = _split_body_refs(text)
        word_count = _wc(text)
        body_wc = _wc(body)
        refs_wc = _wc(refs)
        doc_id = _document_id(
            seed=seed,
            index=index,
            domain=brief.domain,
            doc_type=brief.document_type,
            topic=brief.topic,
            angle=brief.angle,
            text=text,
        )

        docs.append(
            SyntheticDocument(
                document_id=doc_id,
                source_text=text,
                domain=brief.domain,
                document_type=brief.document_type,
                language=LANGUAGE,
                seed=seed,
                word_count=word_count,
                body_word_count=body_wc,
                references_present=refs_present,
                references_word_count=refs_wc,
                section_count=len(section_titles),
                section_titles=section_titles,
                length_bucket=bucket,
                topic=brief.topic,
                angle=brief.angle,
                generation_prompt=brief.generation_prompt,
                combination_key=brief.combination_key,
            )
        )
        domain_counts[brief.domain] = domain_counts.get(brief.domain, 0) + 1
        type_counts[brief.document_type] = type_counts.get(brief.document_type, 0) + 1
        topic_counts[brief.topic] = topic_counts.get(brief.topic, 0) + 1
        angle_counts[brief.angle] = angle_counts.get(brief.angle, 0) + 1
        length_counts[bucket] = length_counts.get(bucket, 0) + 1
        section_hist[len(section_titles)] = section_hist.get(len(section_titles), 0) + 1
        combinations.append(brief.combination_key)
        if refs_present:
            with_refs += 1

    if len(combinations) != len(set(combinations)):
        raise AssertionError("Duplicate domain/topic/type/angle combinations in one run")

    plan = DocumentSamplingPlan(
        document_types=type_counts,
        domains=domain_counts,
        topics=topic_counts,
        angles=angle_counts,
        length_buckets=length_counts,
        with_references=with_refs,
        section_count_histogram=dict(sorted(section_hist.items())),
        combinations=combinations,
    )
    return docs, plan


def summarize_document_plan(plan: DocumentSamplingPlan) -> dict:
    return {
        "document_types": dict(sorted(plan.document_types.items())),
        "domains": dict(sorted(plan.domains.items())),
        "topics": dict(sorted(plan.topics.items())),
        "angles": dict(sorted(plan.angles.items())),
        "length_buckets": dict(sorted(plan.length_buckets.items())),
        "with_references": int(plan.with_references),
        "section_count_histogram": dict(sorted(plan.section_count_histogram.items())),
        "unique_combinations": len(plan.combinations),
        "combinations_sample": list(plan.combinations[:20]),
    }


def _allocate_length_specs(count: int) -> list[tuple[str, int, int]]:
    counts = {name: 0 for name, _, _, _ in _LENGTH_TARGETS}
    remaining = count
    for name, weight, _, _ in _LENGTH_TARGETS:
        qty = int(count * weight)
        counts[name] = qty
        remaining -= qty
    order = [name for name, _, _, _ in _LENGTH_TARGETS]
    idx = 0
    while remaining > 0:
        counts[order[idx % len(order)]] += 1
        idx += 1
        remaining -= 1
    by_name = {name: (low, high) for name, _, low, high in _LENGTH_TARGETS}
    out: list[tuple[str, int, int]] = []
    for name in order:
        low, high = by_name[name]
        out.extend([(name, low, high)] * counts[name])
    return out[:count]


def _build_document(
    *,
    rng: random.Random,
    brief: DocumentBrief,
    target_words: int,
) -> tuple[str, list[str], bool]:
    section_count = rng.randint(4, 8)
    preferred = ["Introduction", "Analysis", "Discussion", "Conclusion"]
    pool = [s for s in _SECTION_POOL if s not in preferred]
    rng.shuffle(pool)
    titles: list[str] = []
    for pref in preferred:
        if len(titles) < section_count and pref not in titles:
            titles.append(pref)
    for title in pool:
        if len(titles) >= section_count:
            break
        if title not in titles:
            titles.append(title)
    titles = titles[:section_count]

    allow_refs = brief.document_type in DOCUMENT_TYPES_ALLOWING_REFERENCES
    include_refs = bool(allow_refs and rng.random() < 0.55)
    marker_plan = {
        "citation": rng.random() < 0.35,
        "number": rng.random() < 0.35,
        "year": rng.random() < 0.25,
        "percentage": rng.random() < 0.15,
        "url": rng.random() < 0.08,
    }
    refs_budget = rng.randint(120, 280) if include_refs else 0
    body_budget = max(800, target_words - refs_budget)

    per_section = max(1, body_budget // max(1, len(titles)))
    parts: list[str] = []
    for s_idx, title in enumerate(titles):
        n_paras = rng.randint(1, 6)
        section_target = (
            per_section
            if s_idx < len(titles) - 1
            else max(per_section, body_budget - _wc("\n\n".join(parts)))
        )
        section_target = max(120, section_target)
        paras = _build_section_paragraphs(
            rng=rng,
            brief=brief,
            title=title,
            n_paras=n_paras,
            target_words=section_target,
            section_index=s_idx,
            marker_plan=marker_plan if s_idx == 0 else None,
        )
        parts.append(f"## {title}\n\n" + "\n\n".join(paras))

    body = "\n\n".join(parts).strip()
    body = _fit_words(body, body_budget, rng)

    if include_refs:
        refs = _build_references(
            rng=rng,
            domain=brief.domain,
            topic=brief.topic,
            index=brief.index,
            target_words=refs_budget,
        )
        refs = _fit_words(refs, refs_budget, rng)
        text = f"{body}\n\n## References\n\n{refs}".strip()
        titles_out = titles + ["References"]
    else:
        text = body
        titles_out = titles

    if _wc(text) < target_words:
        body2, refs2 = _split_body_refs(text)
        need = target_words - _wc(refs2) - (2 if refs2 else 0)
        body2 = _fit_words(body2, max(need, _wc(body2)), rng)
        text = f"{body2}\n\n{refs2}".strip() if refs2 else body2
    elif _wc(text) > target_words and not include_refs:
        text = _fit_words(text, target_words, rng)

    # Hard cap: never intentionally leave body above 5000.
    body_final, refs_final = _split_body_refs(text)
    if _wc(body_final) > 5000:
        body_final = _fit_words(body_final, 5000, rng)
        text = f"{body_final}\n\n{refs_final}".strip() if refs_final else body_final

    return text, titles_out, include_refs


def _build_section_paragraphs(
    *,
    rng: random.Random,
    brief: DocumentBrief,
    title: str,
    n_paras: int,
    target_words: int,
    section_index: int,
    marker_plan: dict[str, bool] | None = None,
) -> list[str]:
    topic_title = brief.topic_title
    angle_title = brief.angle.replace("_", " ")
    type_label = brief.document_type_label
    domain_label = brief.domain.replace("_", " ")
    paras: list[str] = []
    per = max(40, target_words // max(1, n_paras))
    for p_idx in range(n_paras):
        base = (
            f"In the {title.lower()} section, this {type_label} develops the topic of "
            f"{topic_title} within {domain_label}, guided by the angle of {angle_title}. "
            f"The discussion remains academic in register and advances evidence carefully "
            f"rather than relying on unsupported generalization."
        )
        extras = [
            f"Concrete examples related to {topic_title} clarify how local observations "
            f"support the broader claim of the {type_label}.",
            f"The {angle_title} framing keeps competing interpretations visible without "
            f"collapsing the analysis into a single slogan.",
            "Definitions are introduced when needed, and qualifications keep the tone "
            "cautious and suitable for undergraduate assessment.",
            "Transitions clarify how this paragraph connects prior reasoning to the next "
            "stage of the document structure.",
            "Counterpoints are acknowledged briefly to avoid one-sided interpretation of "
            "the available material.",
        ]
        text = base
        while _wc(text) < per:
            text += " " + extras[(p_idx + section_index + len(text.split())) % len(extras)]
        if marker_plan and p_idx == 0:
            text = _append_planned_markers(
                text,
                marker_plan=marker_plan,
                domain=brief.domain,
                index=brief.index,
                section_index=section_index,
            )
        forbidden = ("stealthwriter", "turnitin", "humanization", "as an ai")
        low = text.lower()
        if any(tok in low for tok in forbidden):
            text = text.replace("StealthWriter", "scholarship").replace("Turnitin", "assessment")
        words = text.split()
        if len(words) > per + 40:
            words = words[: per + 40]
        paras.append(" ".join(words))
    return paras


def _append_planned_markers(
    text: str,
    *,
    marker_plan: dict[str, bool],
    domain: str,
    index: int,
    section_index: int,
) -> str:
    year = 2016 + ((index + section_index) % 9)
    number = 12 + ((index * 5 + section_index * 3) % 40)
    pct = 8 + ((index * 2) % 12)
    additions: list[str] = []
    if marker_plan.get("year"):
        additions.append(
            f"A related study from {year} provides a useful temporal reference for this claim."
        )
    if marker_plan.get("number"):
        additions.append(
            f"Approximately {number} observations in the reviewed material support this pattern."
        )
    if marker_plan.get("percentage"):
        additions.append(
            f"In several cases the reported change remains near {pct}% rather than a dramatic shift."
        )
    if marker_plan.get("citation"):
        if marker_plan.get("year"):
            additions.append(
                f"This reading is consistent with concerns noted by earlier scholars (Author, {year})."
            )
        else:
            additions.append(
                f"This reading is consistent with concerns noted in [{1 + (index % 17)}]."
            )
    if marker_plan.get("url"):
        slug = domain.replace("_", "-")
        additions.append(
            f"A contextual overview is available at https://example.org/{slug}/overview-{index}."
        )
    if not additions:
        return text
    return text + " " + " ".join(additions)


def _build_references(
    *,
    rng: random.Random,
    domain: str,
    topic: str,
    index: int,
    target_words: int,
) -> str:
    lines: list[str] = []
    author_pool = ["Nguyen", "Patel", "Okafor", "Silva", "Berg", "Kim", "Hassan", "Ivanov"]
    topic_title = topic.replace("_", " ").title()
    while _wc("\n".join(lines)) < target_words:
        author = author_pool[rng.randint(0, len(author_pool) - 1)]
        year = 2008 + rng.randint(0, 16)
        title = f"{topic_title}: evidence and interpretive limits"
        journal = "Journal of Academic Inquiry"
        lines.append(
            f"{author}, A. ({year}). {title}. {journal}, "
            f"{10 + rng.randint(1, 40)}(2), {10 + rng.randint(1, 90)}-{100 + rng.randint(1, 40)}."
        )
        if rng.random() < 0.35:
            lines.append(f"https://doi.org/10.1000/example.{index}.{len(lines)}")
    return "\n".join(lines)


def _split_body_refs(text: str) -> tuple[str, str]:
    match = re.search(r"(?im)^##\s+References\s*$", text)
    if not match:
        return text, ""
    return text[: match.start()].rstrip(), text[match.start() :].strip()


def _fit_words(text: str, target: int, rng: random.Random) -> str:
    current = _wc(text)
    if current == target:
        return text
    if current > target:
        parts = text.split("\n\n")
        while parts and _wc("\n\n".join(parts)) > target:
            last = parts[-1]
            words = last.split()
            if len(words) <= 8 and len(parts) > 1:
                parts.pop()
                continue
            overflow = _wc("\n\n".join(parts)) - target
            keep = max(1, len(words) - overflow)
            parts[-1] = " ".join(words[:keep]).rstrip()
            if not parts[-1].strip():
                parts.pop()
        return "\n\n".join(p for p in parts if p.strip()).strip()

    filler = [
        "The discussion remains organized around evidence, interpretation, and cautious implication.",
        "Further clarification is provided only when it strengthens the analytical coherence of the section.",
        "The prose maintains a formal academic register suitable for undergraduate assessment contexts.",
    ]
    parts = [text]
    while _wc("\n\n".join(parts)) < target:
        parts.append(filler[rng.randint(0, len(filler) - 1)])
    combined = "\n\n".join(parts)
    if _wc(combined) > target:
        return _fit_words(combined, target, rng)
    return combined


def _wc(text: str) -> int:
    return len([p for p in (text or "").split() if p.strip()])


def _document_id(
    *,
    seed: int,
    index: int,
    domain: str,
    doc_type: str,
    topic: str,
    angle: str,
    text: str,
) -> str:
    digest = hashlib.sha256(
        f"{seed}|{index}|{domain}|{topic}|{doc_type}|{angle}|{text}".encode("utf-8")
    ).hexdigest()
    return f"doc-{seed}-{index:05d}-{digest[:10]}"
