"""Deterministic academic topic catalog for synthetic daily document generation.

Provides diverse domain/topic/document_type/angle combinations so a single
daily backfill does not repeat the same academic brief.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Domains
# ---------------------------------------------------------------------------

DOMAINS: tuple[str, ...] = (
    "economics",
    "business",
    "psychology",
    "sociology",
    "history",
    "computer_science",
    "biology",
    "education",
    "literature",
    "engineering",
    "political_science",
    "environmental_science",
    "public_health",
    "media_communication",
)

# ---------------------------------------------------------------------------
# Document types (stable ids used in metadata)
# ---------------------------------------------------------------------------

DOCUMENT_TYPES: tuple[str, ...] = (
    "argumentative_essay",
    "analytical_essay",
    "explanatory_essay",
    "academic_report",
    "comparative_analysis",
    "critical_discussion",
    "reflective_academic_essay",
)

DOCUMENT_TYPE_LABELS: dict[str, str] = {
    "argumentative_essay": "argumentative essay",
    "analytical_essay": "analytical essay",
    "explanatory_essay": "explanatory essay",
    "academic_report": "academic report",
    "comparative_analysis": "comparative analysis",
    "critical_discussion": "critical discussion",
    "reflective_academic_essay": "reflective academic essay",
}

# Types that may include a References section (others must not invent bibliographies).
DOCUMENT_TYPES_ALLOWING_REFERENCES = frozenset(
    {"academic_report", "comparative_analysis", "analytical_essay"}
)

# Length targets (source body + optional refs). Never intentionally >5000.
LENGTH_TARGETS: tuple[tuple[str, float, int, int], ...] = (
    ("4500_5000", 0.90, 4500, 5000),
    ("3000_4500", 0.10, 3000, 4500),
)

# ---------------------------------------------------------------------------
# Topics per domain (broad enough for 4000–5000-word academic prose)
# ---------------------------------------------------------------------------

TOPICS_BY_DOMAIN: dict[str, tuple[str, ...]] = {
    "economics": (
        "monetary_policy_and_inflation_control",
        "labor_markets_and_wage_dynamics",
        "international_trade_and_supply_chains",
        "fiscal_policy_and_public_debt",
        "behavioral_economics_and_consumer_choice",
    ),
    "business": (
        "strategic_management_under_uncertainty",
        "digital_transformation_in_organizations",
        "corporate_governance_and_accountability",
        "entrepreneurship_and_innovation_ecosystems",
        "sustainable_supply_chain_management",
    ),
    "psychology": (
        "cognitive_biases_in_decision_making",
        "motivation_and_self_regulation",
        "stress_resilience_and_mental_health",
        "social_influence_and_group_behavior",
        "memory_learning_and_expertise",
    ),
    "sociology": (
        "social_mobility_and_inequality",
        "urbanization_and_community_life",
        "institutions_and_collective_action",
        "migration_identity_and_belonging",
        "technology_and_everyday_social_practice",
    ),
    "history": (
        "industrialization_and_social_change",
        "empire_nation_and_decolonization",
        "revolutions_and_political_transformation",
        "war_memory_and_historical_narrative",
        "science_technology_and_modernity",
    ),
    "computer_science": (
        "algorithmic_fairness_and_accountability",
        "cybersecurity_and_trust_architectures",
        "human_computer_interaction_design",
        "distributed_systems_and_reliability",
        "machine_learning_in_practical_settings",
    ),
    "biology": (
        "cellular_signaling_and_regulation",
        "ecology_and_species_interactions",
        "genetics_and_population_variation",
        "microbiome_and_host_health",
        "evolution_and_adaptation_mechanisms",
    ),
    "education": (
        "assessment_practices_and_learning_outcomes",
        "inclusive_pedagogy_and_equity",
        "curriculum_design_and_transfer_of_learning",
        "digital_learning_environments",
        "teacher_professional_development",
    ),
    "literature": (
        "narrative_voice_and_unreliable_narration",
        "genre_conventions_and_innovation",
        "representation_identity_and_power",
        "intertextuality_and_adaptation",
        "close_reading_and_critical_interpretation",
    ),
    "engineering": (
        "design_constraints_and_trade_offs",
        "reliability_safety_and_risk_management",
        "sustainable_engineering_systems",
        "human_factors_in_technical_design",
        "infrastructure_resilience_and_maintenance",
    ),
    "political_science": (
        "democratic_institutions_and_legitimacy",
        "public_policy_implementation_gaps",
        "international_cooperation_and_conflict",
        "political_participation_and_representation",
        "governance_transparency_and_accountability",
    ),
    "environmental_science": (
        "climate_adaptation_and_mitigation",
        "biodiversity_conservation_strategies",
        "water_resource_management",
        "pollution_control_and_environmental_justice",
        "land_use_change_and_ecosystem_services",
    ),
    "public_health": (
        "prevention_strategies_and_health_promotion",
        "health_system_capacity_and_access",
        "epidemiology_of_chronic_disease",
        "community_health_interventions",
        "pandemic_preparedness_and_response",
    ),
    "media_communication": (
        "media_framing_and_public_opinion",
        "digital_platforms_and_information_ecosystems",
        "journalistic_standards_and_credibility",
        "persuasion_rhetoric_and_audience_effects",
        "misinformation_and_media_literacy",
    ),
}

# Shared analytical angles — combined with domain+topic+type for uniqueness.
ANGLES: tuple[str, ...] = (
    "compare_policy_trade_offs",
    "evaluate_competing_explanations",
    "trace_historical_or_causal_pathways",
    "assess_ethical_and_practical_implications",
    "synthesize_evidence_across_cases",
    "critique_dominant_assumptions",
    "examine_measurement_and_validity_issues",
    "map_stakeholder_incentives_and_constraints",
    "contrast_short_term_and_long_term_outcomes",
    "identify_implementation_barriers",
    "weigh_costs_benefits_and_distributional_effects",
    "situate_local_cases_in_broader_context",
)


@dataclass(frozen=True, slots=True)
class DocumentBrief:
    """One unique synthetic academic assignment brief."""

    domain: str
    topic: str
    document_type: str
    angle: str
    seed: int
    index: int
    generation_prompt: str

    @property
    def combination_key(self) -> str:
        return f"{self.domain}|{self.topic}|{self.document_type}|{self.angle}"

    @property
    def document_type_label(self) -> str:
        return DOCUMENT_TYPE_LABELS.get(self.document_type, self.document_type)

    @property
    def topic_title(self) -> str:
        return self.topic.replace("_", " ")

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["combination_key"] = self.combination_key
        payload["document_type_label"] = self.document_type_label
        payload["topic_title"] = self.topic_title
        return payload


def all_combination_keys() -> list[str]:
    keys: list[str] = []
    for domain in DOMAINS:
        for topic in TOPICS_BY_DOMAIN[domain]:
            for doc_type in DOCUMENT_TYPES:
                for angle in ANGLES:
                    keys.append(f"{domain}|{topic}|{doc_type}|{angle}")
    return keys


def catalog_stats() -> dict[str, int]:
    topic_count = sum(len(v) for v in TOPICS_BY_DOMAIN.values())
    combo = topic_count * len(DOCUMENT_TYPES) * len(ANGLES)
    return {
        "domains": len(DOMAINS),
        "topics": topic_count,
        "document_types": len(DOCUMENT_TYPES),
        "angles": len(ANGLES),
        "unique_combinations": combo,
    }


def build_generation_prompt(
    *,
    domain: str,
    topic: str,
    document_type: str,
    angle: str,
    target_words_low: int = 4000,
    target_words_high: int = 5000,
) -> str:
    """Internal academic generation template (not shown to end users)."""
    label = DOCUMENT_TYPE_LABELS.get(document_type, document_type)
    topic_title = topic.replace("_", " ")
    angle_title = angle.replace("_", " ")
    allow_refs = document_type in DOCUMENT_TYPES_ALLOWING_REFERENCES
    refs_rule = (
        "Include a short References section only if citations are woven into the body; "
        "do not invent a long bibliography for its own sake."
        if allow_refs
        else "Do NOT invent a References section or fabricated bibliography."
    )
    return (
        f"Write a {label} of approximately {target_words_low}–{target_words_high} words "
        f"in a natural academic register on the topic “{topic_title}” "
        f"(domain: {domain.replace('_', ' ')}).\n"
        f"Analytical angle: {angle_title}.\n"
        "Requirements:\n"
        "- Use several `##` section headings and a coherent multi-section structure.\n"
        "- Develop arguments or explanations appropriate to the document type.\n"
        "- Include concrete examples; where natural, mention numbers, years, or brief "
        "in-text citations without fabricating elaborate source lists.\n"
        f"- {refs_rule}\n"
        "- Do not include meta commentary about writing tools, detection systems, or machine authorship.\n"
        "- Stay within the word budget; never intentionally exceed 5000 body words."
    )


def select_document_briefs(
    *,
    count: int,
    seed: int,
) -> list[DocumentBrief]:
    """Deterministically choose unique domain/topic/type/angle briefs for one run."""
    if count <= 0:
        return []

    pool: list[tuple[str, str, str, str]] = []
    for domain in DOMAINS:
        for topic in TOPICS_BY_DOMAIN[domain]:
            for doc_type in DOCUMENT_TYPES:
                for angle in ANGLES:
                    pool.append((domain, topic, doc_type, angle))

    if count > len(pool):
        raise ValueError(
            f"Requested {count} documents but only {len(pool)} unique "
            "domain/topic/document_type/angle combinations exist"
        )

    rng = random.Random(seed)
    rng.shuffle(pool)
    pool_slice = pool[:count]

    briefs: list[DocumentBrief] = []
    seen: set[str] = set()
    for index, (domain, topic, doc_type, angle) in enumerate(pool_slice):
        key = f"{domain}|{topic}|{doc_type}|{angle}"
        if key in seen:
            raise AssertionError(f"Duplicate combination selected: {key}")
        seen.add(key)
        prompt = build_generation_prompt(
            domain=domain,
            topic=topic,
            document_type=doc_type,
            angle=angle,
        )
        briefs.append(
            DocumentBrief(
                domain=domain,
                topic=topic,
                document_type=doc_type,
                angle=angle,
                seed=seed,
                index=index,
                generation_prompt=prompt,
            )
        )
    return briefs


def assert_no_duplicate_combinations(briefs: list[DocumentBrief]) -> None:
    keys = [b.combination_key for b in briefs]
    if len(keys) != len(set(keys)):
        raise AssertionError("Duplicate topic combinations within a single run")
