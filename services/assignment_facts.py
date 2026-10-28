"""Web-verified statistics (national statistics office, regulators, OECD...) for analytical reports.

One Claude web-search call per project gathers a few current figures about the case's
country and industry. The writer gets them as citable facts, and the citation engine
gets the matching works as pre-verified references, so a PESTLE cites real data instead
of vague claims.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

FACTS_ARTIFACT = "verified_facts"
_MAX_FACTS = 6
_MAX_SEARCHES = 4
_MATERIALS_CHARS = 12000
_WANTED_RE = re.compile(
    r"\b(?:PESTLE|PESTEL|PEST|STEEPLE|external environment|macro-?environment|market analysis|industry analysis)\b",
    re.I,
)

_SYSTEM = """You gather current, verifiable statistics for a student's business report.
Read the assignment materials, identify the case's country and industry, then search the web for
{max_facts} or fewer figures the report's external analysis can use (e.g. market size or growth,
energy prices, inflation or interest rates, government targets or grants, regulation).

Rules:
- Every figure must concern the company's own products or services, its customers or its market as
  the materials describe them. A scheme or statistic for products the company does not sell (e.g. a
  heat-pump grant for a solar and battery installer) is not relevant — leave it out.
- Only official or authoritative sources of the case's country (its statistics office, government
  departments, regulators, official certification bodies) or international bodies (OECD, IEA, World
  Bank). Never another country's government, a blog, a company marketing page or a market-research
  vendor's teaser page.
- Each figure must appear on a page you found; copy it exactly with its unit and currency symbol
  (e.g. "£2.7 billion") and keep its period/date.
- Prefer the latest available data. No forecasts presented as facts.
- One figure per item; at most one item per page.
- "organisation" is the single organisation that published the page at "url" (never one the page
  merely quotes), written in full without an acronym in brackets.
- A "Legal" item must be a binding law, regulation, mandatory standard or certification requirement;
  a target or a grant is "Political".

Return ONLY JSON, no prose:
{{"case_country":"United Kingdom","facts":[{{"fact":"one sentence stating the figure",
"organisation":"Office for National Statistics","publisher_country":"United Kingdom","year":"2024",
"title":"exact page or report title","url":"https://...","factor":"Economic",
"product":"which of the company's products or customers this concerns"}}]}}
"publisher_country" is "International" for international bodies. "factor" is the PESTLE factor the
figure informs (Political, Economic, Social, Technological, Legal, Environmental).
"""

_GOVERNMENT_ORG_RE = re.compile(
    r"(?i)\b(?:department|ministry|office|government|agency|authority|commission|council|parliament|"
    r"treasury|regulator|ofgem|hm\b)"
)
_INTERNATIONAL = {"international", "global", "worldwide", "europe", "european union", "eu"}


def facts_wanted(materials: str) -> bool:
    return bool(_WANTED_RE.search(materials or ""))


def gather_verified_facts(
    materials: str,
    *,
    search: Callable[..., tuple[str | None, list[dict[str, str]], dict[str, Any]]] | None = None,
) -> list[dict[str, str]]:
    """Facts whose URL was returned by the web search; empty when search is unavailable."""
    from services.assignment_citations import _is_retail_url, _url_backed_by_sources

    if search is None:
        from services.claude_client import generate_with_web_search as search
    text, sources, _diag = search(
        system_prompt=_SYSTEM.format(max_facts=_MAX_FACTS),
        user_prompt="ASSIGNMENT MATERIALS:\n" + (materials or "")[:_MATERIALS_CHARS],
        max_searches=_MAX_SEARCHES,
        max_tokens=3000,
    )
    if not text:
        return []
    raw = text[text.find("{") : text.rfind("}") + 1]
    try:
        data = json.loads(raw)
        items = data.get("facts") or []
        case_country = str(data.get("case_country") or "").strip().lower()
    except (ValueError, AttributeError):
        return []
    facts: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        fact = {k: str(item.get(k) or "").strip() for k in ("fact", "organisation", "year", "title", "url", "factor")}
        if not all(fact[k] for k in ("fact", "organisation", "title", "url")):
            continue
        if not re.match(r"^(?:19|20)\d{2}$", fact["year"]) or not re.search(r"\d", fact["fact"]):
            continue
        fact["organisation"] = re.sub(r"\s*\([A-Z]{2,10}\)\s*$", "", fact["organisation"])
        if "/" in fact["organisation"] or re.search(r"(?i)\b(?:cited|quoted) (?:via|in|by)\b", fact["title"]):
            continue
        url = fact["url"]
        if not url.startswith("http") or _is_retail_url(url) or url in seen_urls:
            continue
        if not _url_backed_by_sources(url, fact["title"], sources):
            continue
        publisher_country = str(item.get("publisher_country") or "").strip().lower()
        if case_country and publisher_country and publisher_country not in _INTERNATIONAL | {case_country}:
            continue
        if not _published_by(fact["organisation"], url):
            continue
        seen_urls.add(url)
        facts.append(fact)
        if len(facts) >= _MAX_FACTS:
            break
    return facts


def _published_by(organisation: str, url: str) -> bool:
    """The page's site belongs to the organisation credited with the figure.

    Government bodies share national portals (gov.uk), so a government organisation on a
    government domain counts; anything else needs its name or acronym in the domain.
    """
    from services.assignment_citations import _acronym, _domain

    domain = _domain(url)
    if not domain:
        return False
    labels = re.split(r"[.\-]", domain)
    if _GOVERNMENT_ORG_RE.search(organisation) and ("gov" in labels or "gouv" in labels or "europa" in labels):
        return True
    org = organisation.lower()
    acronym = _acronym(org)
    if acronym and len(acronym) >= 2 and any(label.startswith(acronym) for label in labels):
        return True
    words = [w for w in re.findall(r"[a-z]{4,}", org) if w not in {"department", "office", "national", "limited"}]
    squashed = domain.replace(".", "").replace("-", "")
    return bool(words) and any(w in squashed for w in words)


def facts_as_works(facts: list[dict[str, str]], *, style: str) -> list[dict[str, Any]]:
    """Reference-ready works for the citation engine (organisation as author, with access date)."""
    from services.assignment_pipeline.models import utc_now
    from services.citation_service.models import Work
    from services.citation_service.service import _format_reference, _intext, _label, _normalize_style

    _label_style, style_key = _normalize_style(style)
    works: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for fact in facts:
        key = (fact["organisation"], fact["year"], fact["title"])
        if key in seen:
            continue
        seen.add(key)
        # Trailing comma keeps an organisation name whole in the reference formatter.
        work = Work(title=fact["title"], authors=[fact["organisation"].rstrip(",") + ","], year=fact["year"], url=fact["url"])
        reference = _format_reference(work, style_key)
        if style_key == "Harvard":
            reference += f" (Accessed: {utc_now():%-d %B %Y})."
        works.append(
            {
                **work.to_dict(),
                "intext": _intext(work, style_key),
                "reference": reference,
                "label": _label(work),
                "verified_via": "web_facts",
            }
        )
    return works


def facts_material(facts: list[dict[str, str]], *, style: str = "Harvard") -> str:
    """Block appended to the writer's materials."""
    if not facts:
        return ""
    works = {(w["title"], w["year"]): w for w in facts_as_works(facts, style=style)}
    lines = [
        "VERIFIED CURRENT DATA (found by web search; use 1-2 of these where they strengthen the analysis,",
        "quote figures exactly and cite them exactly as shown; do not cite them for anything else):",
    ]
    for fact in facts:
        work = works.get((fact["title"], fact["year"])) or {}
        cite = str(work.get("intext") or f"({fact['organisation']}, {fact['year']})")
        factor = f"[{fact['factor']}] " if fact.get("factor") else ""
        lines.append(f"- {factor}{fact['fact']} {cite}")
    return "\n".join(lines)
