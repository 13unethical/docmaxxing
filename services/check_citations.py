"""Match bibliography entries to in-text citations by number or surname+year."""

from __future__ import annotations

import re
from typing import Any

_UNICODE_SPACE_RE = re.compile(r"[\u00a0\u202f\u2007\u2009\u2008\u2002\u2003\u2004\u2005\u2006\u200a\ufeff]+")
_YEAR_TOKEN = r"(?:19|20)\d{2}[a-z]?|n\.d\.?"
_YEAR_RE = re.compile(rf"({_YEAR_TOKEN})", re.I)
_PAREN_YEAR_RE = re.compile(rf"\(({_YEAR_TOKEN})\)", re.I)
_YEAR_RANGE_RE = re.compile(r"(?:19|20)\d{2}\s*[–-]\s*(?:19|20)\d{2}")
_PAGE_SUFFIX_RE = re.compile(r",\s*pp?\.\s*\d+(?:\s*[–-]\s*\d+)?\s*$", re.I)
_NAME = r"[A-Z][A-Za-z'’\-]+"
_NARRATIVE_RE = re.compile(
    rf"\b(({_NAME}(?:\s+{_NAME}){{0,3}})(?:\s+(?:et\s+al\.?|&|and)\s+{_NAME})?)\s+\(({_YEAR_TOKEN})\)"
)
_NUM_REF_LINE_RE = re.compile(r"^\s*(?:\[(?P<bracket>\d+)\]|(?P<dot>\d+)\.)\s+\S")
_BRACKET_CITE_RE = re.compile(r"\[(\d+(?:\s*[,;–-]\s*\d+)*)\]")
_PAREN_NUM_CITE_RE = re.compile(r"\((\d+(?:\s*[,;–-]\s*\d+)*)\)")
_CITE_PREFIX_RE = re.compile(r"^(?:see(?:\s+also)?|cf\.?|e\.g\.?|eg)\s+", re.I)
_AUTHOR_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "the",
        "this",
        "that",
        "these",
        "those",
        "table",
        "figure",
        "fig",
        "chapter",
        "section",
        "page",
        "pages",
        "pp",
        "vol",
        "year",
        "years",
        "between",
        "during",
        "after",
        "before",
        "from",
        "with",
        "for",
        "see",
        "also",
    }
)


def fold_citation_text(text: str) -> str:
    """Normalise non-breaking spaces so 'World Bank' and 'n.d.' still parse."""
    return _UNICODE_SPACE_RE.sub(" ", text or "")


def _norm_year(token: str) -> str:
    value = (token or "").strip().lower()
    value = re.sub(r"\s+", "", value)
    if value.startswith("n.d"):
        return "n.d"
    return value.rstrip(".")


def _clean_author_chunk(chunk: str) -> str:
    text = fold_citation_text(chunk)
    text = re.sub(r"\bet\s+al\.?", " ", text, flags=re.I)
    text = text.replace("&", " and ")
    return re.sub(r"\s+", " ", text).strip(" ,;.")


def surnames_from_author_phrase(phrase: str) -> list[str]:
    """Extract comparable author keys from an in-text or reference author string."""
    cleaned = _clean_author_chunk(phrase)
    if not cleaned:
        return []
    people = re.split(r"\s+and\s+|;\s+", cleaned, flags=re.I)
    surnames: list[str] = []
    for person in people:
        person = person.strip(" ,")
        if not person:
            continue
        if "," in person:
            candidate = person.split(",", 1)[0].strip().lower()
            if _usable_surname(candidate):
                surnames.append(candidate)
            continue
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’\-]*", person) if w.lower() not in {"and"}]
        if not words:
            continue
        if words[0].lower() in _AUTHOR_STOPWORDS:
            continue
        caps = [w for w in re.findall(r"[A-Za-z][A-Za-z'’\-]*", person) if w.lower() != "and"]
        if len(words) >= 2 and caps and all(w[:1].isupper() for w in caps):
            joined = " ".join(w.lower() for w in words)
            if _usable_surname(words[0].lower()):
                surnames.append(joined)
        elif _usable_surname(words[0].lower()):
            surnames.append(words[0].lower())
    return surnames


def _usable_surname(value: str) -> bool:
    key = (value or "").strip().lower()
    if len(key) < 2 or key in _AUTHOR_STOPWORDS:
        return False
    return bool(re.fullmatch(r"[a-z][a-z'’\-]*(?: [a-z][a-z'’\-]*)*", key))


def parse_reference_entry(line: str) -> dict[str, Any] | None:
    raw = fold_citation_text(line).strip()
    if not raw:
        return None
    stripped = _NUM_REF_LINE_RE.sub("", raw, count=1).strip() or raw
    year_m = _PAREN_YEAR_RE.search(stripped)
    if year_m:
        year = _norm_year(year_m.group(1))
        author_part = stripped[: year_m.start()]
    else:
        year_m = re.search(rf"\b({_YEAR_TOKEN})\b", stripped, re.I)
        if not year_m:
            return None
        year = _norm_year(year_m.group(1))
        author_part = stripped[: year_m.start()]
    surnames = surnames_from_author_phrase(author_part)
    if not surnames:
        return None
    return {
        "surnames": surnames,
        "year": year,
        "raw": raw,
        "label": _source_label(surnames, year),
    }


def parse_numbered_reference(line: str) -> dict[str, Any] | None:
    raw = fold_citation_text(line).strip()
    match = _NUM_REF_LINE_RE.match(raw)
    if not match:
        return None
    number = int(match.group("bracket") or match.group("dot"))
    return {
        "number": number,
        "raw": raw,
        "label": f"[{number}]",
    }


def _author_year_chunk(author_part: str) -> str | None:
    chunk = _CITE_PREFIX_RE.sub("", fold_citation_text(author_part).strip(" ,;"))
    if not chunk:
        return None
    if len(chunk.split()) > 6:
        return None
    first = re.match(rf"^{_NAME}", chunk)
    if not first:
        return None
    if first.group(0).lower() in _AUTHOR_STOPWORDS:
        return None
    return chunk


def parse_in_text_citations(text: str) -> list[dict[str, Any]]:
    """Unique author-year in-text citations (parenthetical and narrative)."""
    text = fold_citation_text(text)
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(surnames: list[str], year: str, raw: str) -> None:
        if not surnames or not year:
            return
        key = ("|".join(sorted(surnames)), year)
        if key in seen:
            return
        seen.add(key)
        found.append(
            {
                "surnames": surnames,
                "year": year,
                "raw": raw.strip(),
                "label": _source_label(surnames, year),
            }
        )

    for m in re.finditer(r"\(([^)]{2,200})\)", text or ""):
        inner = m.group(1)
        stripped_ranges = _YEAR_RANGE_RE.sub(" ", inner)
        if _YEAR_RANGE_RE.search(inner) and not _YEAR_RE.search(stripped_ranges):
            continue
        if not _YEAR_RE.search(inner):
            continue
        for part in re.split(r";", inner):
            part = _PAGE_SUFFIX_RE.sub("", part).strip()
            if _YEAR_RANGE_RE.search(part):
                continue
            year_m = _YEAR_RE.search(part)
            if not year_m:
                continue
            after = part[year_m.end() :]
            if after.lstrip().startswith(("-", "–")):
                continue
            year = _norm_year(year_m.group(1))
            author_chunk = _author_year_chunk(part[: year_m.start()])
            if not author_chunk:
                continue
            surnames = surnames_from_author_phrase(author_chunk)
            add(surnames, year, part)

    for m in _NARRATIVE_RE.finditer(text or ""):
        surnames = surnames_from_author_phrase(m.group(1))
        year = _norm_year(m.group(3))
        add(surnames, year, m.group(0))

    return found


def _collect_numeric_tokens(inner: str, found: set[int]) -> None:
    for part in re.split(r"[,;]", inner):
        token = part.strip()
        if re.fullmatch(r"\d+", token):
            number = int(token)
            if 1900 <= number <= 2099:
                continue
            found.add(number)
            continue
        span = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", token)
        if not span:
            continue
        start_n, end_n = int(span.group(1)), int(span.group(2))
        if 1900 <= start_n <= 2099 or 1900 <= end_n <= 2099:
            continue
        lo, hi = min(start_n, end_n), max(start_n, end_n)
        found.update(range(lo, hi + 1))


def parse_numeric_citations(text: str) -> list[int]:
    """Unique citation numbers: [1], [1, 2], [1-3], and Vancouver (1)."""
    text = fold_citation_text(text)
    found: set[int] = set()
    for match in _BRACKET_CITE_RE.finditer(text or ""):
        _collect_numeric_tokens(match.group(1), found)
    for match in _PAREN_NUM_CITE_RE.finditer(text or ""):
        _collect_numeric_tokens(match.group(1), found)
    return sorted(found)


def paragraph_has_citation(text: str, *, mode: str | None = None) -> bool:
    """True if this paragraph contains at least one in-text citation."""
    if mode == "numeric":
        return bool(parse_numeric_citations(text))
    if parse_in_text_citations(text):
        return True
    if mode == "author_year":
        return False
    return bool(parse_numeric_citations(text))


def detect_citation_mode(reference_lines: list[str]) -> str:
    nonempty = [fold_citation_text(line).strip() for line in reference_lines if str(line).strip()]
    if not nonempty:
        return "unknown"
    numbered = sum(1 for line in nonempty if parse_numbered_reference(line) is not None)
    if numbered * 2 >= len(nonempty):
        return "numeric"
    author_year = sum(1 for line in nonempty if parse_reference_entry(line) is not None)
    if author_year * 2 >= len(nonempty):
        return "author_year"
    return "unknown"


def citation_matches_reference(cite: dict[str, Any], ref: dict[str, Any]) -> bool:
    if _norm_year(str(cite.get("year") or "")) != _norm_year(str(ref.get("year") or "")):
        return False
    cite_keys = {str(s).lower() for s in (cite.get("surnames") or [])}
    ref_keys = {str(s).lower() for s in (ref.get("surnames") or [])}
    if cite_keys & ref_keys:
        return True
    for left in cite_keys:
        for right in ref_keys:
            if left in right or right in left:
                return True
    return False


def _org_mentions_from_references(body_text: str, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Count multi-word organisations named in the body as citations of those entries."""
    body = fold_citation_text(body_text)
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        year = str(ref.get("year") or "")
        for surname in ref.get("surnames") or []:
            key = str(surname).strip().lower()
            is_org = " " in key or key in {"unesco", "oecd", "imf", "who", "unicef", "gapminder", "tutorchase"}
            if not is_org:
                continue
            pattern = re.compile(rf"\b{re.escape(str(surname))}\b", re.I)
            if not pattern.search(body):
                continue
            sig = (key, year)
            if sig in seen:
                continue
            seen.add(sig)
            found.append(
                {
                    "surnames": [str(surname).lower()],
                    "year": year,
                    "raw": str(surname),
                    "label": _source_label([str(surname).lower()], year),
                }
            )
    return found


def match_citations(*, body_text: str, reference_lines: list[str]) -> dict[str, Any]:
    mode = detect_citation_mode(reference_lines)
    if mode == "numeric":
        return _match_numeric(body_text=body_text, reference_lines=reference_lines)
    if mode == "author_year":
        return _match_author_year(body_text=body_text, reference_lines=reference_lines)
    nonempty = [fold_citation_text(line).strip() for line in reference_lines if str(line).strip()]
    return _unverified_match(listed=len(nonempty))


def count_in_text_citation_hits(*, body_text: str, mode: str | None = None) -> int:
    """How many unique in-text citations exist, independent of the reference list."""
    if mode == "numeric":
        return len(parse_numeric_citations(body_text))
    cites = parse_in_text_citations(body_text)
    if cites:
        return len(cites)
    if mode == "author_year":
        return 0
    return len(parse_numeric_citations(body_text))


def _unverified_match(*, listed: int) -> dict[str, Any]:
    listed_word = "source" if listed == 1 else "sources"
    return {
        "mode": "unknown",
        "verifiable": False,
        "listed": listed,
        "cited": 0,
        "matched": 0,
        "uncited": [],
        "missing": [],
        "mismatches": [],
        "summary": "couldn't verify",
        "listed_label": f"{listed} {listed_word} listed",
    }


def format_citation_summary(
    *,
    listed: int,
    cited: int,
    uncited: list[Any],
    missing: list[Any],
) -> str:
    """Human explanation of the mismatch; counts-only when everything aligns."""
    parts: list[str] = []
    if missing:
        n = len(missing)
        word = "source" if n == 1 else "sources"
        parts.append(f"{n} {word} cited in text but missing from your reference list")
    if uncited:
        n = len(uncited)
        word = "source" if n == 1 else "sources"
        parts.append(f"{n} {word} listed but not cited in the text")
    if parts:
        return " · ".join(parts)
    listed_word = "source" if listed == 1 else "sources"
    return f"{listed} {listed_word} listed · {cited} cited in text"


def _match_numeric(*, body_text: str, reference_lines: list[str]) -> dict[str, Any]:
    refs = [parsed for line in reference_lines if (parsed := parse_numbered_reference(line))]
    cited_nums = parse_numeric_citations(body_text)
    listed_set = {ref["number"] for ref in refs}
    cited_set = set(cited_nums)
    uncited = [ref for ref in refs if ref["number"] not in cited_set]
    missing = [{"label": f"[{n}]", "number": n} for n in cited_nums if n not in listed_set]
    mismatches: list[str] = []
    for item in uncited:
        mismatches.append(f"Listed but not cited: {item['label']}")
    for item in missing:
        mismatches.append(f"Cited but not in the list: {item['label']}")
    listed = len(refs)
    cited = len(cited_nums)
    matched = listed - len(uncited)
    return {
        "mode": "numeric",
        "verifiable": True,
        "listed": listed,
        "cited": cited,
        "matched": matched,
        "uncited": [{"label": r["label"], "number": r["number"]} for r in uncited],
        "missing": missing,
        "mismatches": mismatches,
        "summary": format_citation_summary(listed=listed, cited=cited, uncited=uncited, missing=missing),
    }


def _match_author_year(*, body_text: str, reference_lines: list[str]) -> dict[str, Any]:
    refs = [parsed for line in reference_lines if (parsed := parse_reference_entry(line))]
    cites = parse_in_text_citations(body_text)
    cites.extend(_org_mentions_from_references(body_text, refs))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for cite in cites:
        key = ("|".join(sorted(str(s).lower() for s in (cite.get("surnames") or []))), str(cite.get("year") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cite)
    cites = deduped
    uncited = [ref for ref in refs if not any(citation_matches_reference(cite, ref) for cite in cites)]
    missing = [cite for cite in cites if not any(citation_matches_reference(cite, ref) for ref in refs)]
    listed = len(refs)
    cited = len(cites)
    matched = listed - len(uncited)
    mismatches: list[str] = []
    for item in uncited:
        mismatches.append(f"Listed but not cited: {item['label']}")
    for item in missing:
        mismatches.append(f"Cited but not in the list: {item['label']}")
    return {
        "mode": "author_year",
        "verifiable": True,
        "listed": listed,
        "cited": cited,
        "matched": matched,
        "uncited": [{"label": r["label"], "surnames": r["surnames"], "year": r["year"]} for r in uncited],
        "missing": [{"label": c["label"], "surnames": c["surnames"], "year": c["year"]} for c in missing],
        "mismatches": mismatches,
        "summary": format_citation_summary(listed=listed, cited=cited, uncited=uncited, missing=missing),
    }


def _source_label(surnames: list[str], year: str) -> str:
    if not surnames:
        return year
    pretty = [part.title() for part in surnames]
    if len(pretty) == 1:
        name = pretty[0]
    elif len(pretty) == 2:
        name = f"{pretty[0]} & {pretty[1]}"
    else:
        name = f"{pretty[0]} et al."
    return f"{name} {year}"
