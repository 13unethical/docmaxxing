"""
Document Structure Engine — canonical heading detection and structure recovery.

Single source of truth for:
- Heading / section detection (used by formatter, checker, recovery, preview rules)
- Structure recovery when headings and paragraph breaks were lost (e.g. humanizers)
"""

from __future__ import annotations

import re
from typing import Any

from docx import Document
from services.gemini_client import gemini_enabled, gemini_model

# --- Canonical heading vocabulary (shared across formatter + checker + recovery) ---

COMMON_HEADINGS = frozenset(
    {
        "introduction",
        "conclusion",
        "methods",
        "results",
        "discussion",
    }
)

REFS_HEADINGS = frozenset(
    {
        "references",
        "bibliography",
        "works cited",
    }
)


def normalize_paragraph_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


_JOURNAL_ENTRY_HEADING_RE = re.compile(
    r"^journal entry\s+\d+(?:\s*:\s*|\s+)(?=\S)",
    re.IGNORECASE,
)
_SECTION_LABEL_HEADING_RE = re.compile(
    r"^(section|part|chapter|unit|module|week|entry)\s+\d+\s*:",
    re.IGNORECASE,
)
_STANDALONE_LABEL_HEADING_RE = re.compile(
    r"^(reflection|references|bibliography|works cited|abstract|appendix)\s*:?\s*$",
    re.IGNORECASE,
)
_NUMBERED_SECTION_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s*[A-Za-z]")

_BODY_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "with",
    }
)


def _short_line_heading_like(line: str) -> bool:
    """Title-like short line, not a sentence fragment such as 'Body text for …'."""
    words = line.split()
    if len(words) > 5 or line.rstrip().endswith("."):
        return False
    if not line or not line[0].isupper():
        return False
    if {w.lower() for w in words} & _BODY_STOPWORDS:
        return False
    return True


def is_learning_journal_heading_line(line: str) -> bool:
    """Learning-journal section titles (long or short, with or without numbering)."""
    t = line.strip()
    if not t:
        return False
    norm = normalize_paragraph_text(t)
    if norm.startswith("this journal entry"):
        return True
    if norm.startswith("the students make journal entries"):
        return True
    if re.match(r"^journal entry\s+\d+", norm):
        return True
    if re.search(r"journal entry\s*[–\-—:]", t, re.IGNORECASE):
        return True
    if norm.startswith("a ") and re.search(r"\bjournal entry\b", norm):
        return True
    return False


def split_embedded_heading_paragraph(text: str) -> tuple[str, str | None]:
    """
    When a paragraph starts with a heading line and continues with body text on
    the next line, return (heading_line, body_text). Otherwise return (text, None).
    """
    stripped = text.strip()
    if "\n" not in stripped:
        return stripped, None
    first_line, rest = stripped.split("\n", 1)
    first_line = first_line.strip()
    rest = rest.strip()
    if not first_line or not rest:
        return stripped, None
    if is_heading_like(first_line) or _JOURNAL_ENTRY_HEADING_RE.match(first_line):
        return first_line, rest
    return stripped, None


def is_references_heading(text: str) -> bool:
    """True if the whole paragraph is a References / Bibliography title."""
    return normalize_paragraph_text(text) in REFS_HEADINGS


def is_heading_like(text: str) -> bool:
    """Heuristic: short standalone line that looks like a section heading."""
    t = text.strip()
    if not t:
        return False
    if (
        _JOURNAL_ENTRY_HEADING_RE.match(t)
        or _SECTION_LABEL_HEADING_RE.match(t)
        or _NUMBERED_SECTION_HEADING_RE.match(t)
        or is_learning_journal_heading_line(t)
    ):
        return True
    if _STANDALONE_LABEL_HEADING_RE.match(t):
        return True
    n = normalize_paragraph_text(t)
    if n in COMMON_HEADINGS | REFS_HEADINGS:
        return True
    words = t.split()
    if len(words) <= 8 and not t.rstrip().endswith("."):
        if t.isupper() and len(t) > 3:
            return True
        if _short_line_heading_like(t):
            return True
    return False


def detect_heading_level(
    text: str,
    auto_detect: bool,
    *,
    is_first_nonempty: bool = False,
    requirement_labels: frozenset[str] | None = None,
) -> int:
    """
    Return 0 = body; 1 = document title; 2 = major section; 3 = subsection.
    """
    if not auto_detect:
        return 0

    stripped = text.strip()
    if not stripped:
        return 0

    first_line = stripped.split("\n", 1)[0].strip()
    has_embedded_body = "\n" in stripped and bool(stripped.split("\n", 1)[1].strip())
    check = first_line if has_embedded_body else stripped

    if _JOURNAL_ENTRY_HEADING_RE.match(check) or _SECTION_LABEL_HEADING_RE.match(check):
        return 2
    if is_learning_journal_heading_line(check):
        return 2
    if _NUMBERED_SECTION_HEADING_RE.match(check):
        return 2
    if _STANDALONE_LABEL_HEADING_RE.match(check):
        return 2

    normalized = normalize_paragraph_text(check)

    if requirement_labels and normalized in requirement_labels:
        return 2
    if requirement_labels:
        for label in requirement_labels:
            if normalized == label or normalized.replace("-", " ") == label.replace("-", " "):
                return 2

    if is_first_nonempty and not has_embedded_body:
        words = stripped.split()
        if (
            len(words) >= 6
            and not stripped.rstrip().endswith(".")
            and normalized not in COMMON_HEADINGS
            and normalized not in REFS_HEADINGS
        ):
            return 1

    if normalized in COMMON_HEADINGS or normalized in REFS_HEADINGS:
        return 2

    letters = [c for c in check if c.isalpha()]
    if letters and check == check.upper():
        return 2

    words = check.split()
    if _short_line_heading_like(check):
        return 3

    return 0


def heading_style_label(text: str) -> str:
    stripped = text.strip()
    if re.match(r"^\d+(\.\d+)*\s+", stripped):
        return "numbered"
    if stripped.isupper():
        return "all caps"
    if stripped.endswith(":"):
        return "colon"
    words = stripped.split()
    if words and sum(1 for w in words if w[:1].isupper()) >= max(1, len(words) - 1):
        return "title case"
    return "sentence case"


def infer_assignment_title(paragraphs: list[str]) -> str:
    """Best-effort title from the opening paragraph for cover pages."""
    for idx, paragraph in enumerate(paragraphs):
        stripped = paragraph.strip()
        if not stripped:
            continue
        if detect_heading_level(stripped, True, is_first_nonempty=idx == 0) == 1:
            return stripped[:200]
        words = stripped.split()
        if 3 <= len(words) <= 22 and not stripped.rstrip().endswith("."):
            return stripped[:200]
        break
    return ""


def preview_heading_like(text: str, index: int) -> bool:
    """Mirror detect_heading_level for client-side HTML preview."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    if detect_heading_level(stripped, True, is_first_nonempty=index == 0) > 0:
        return True
    return is_heading_like(stripped)

DOCUMENT_TYPES = frozenset(
    {
        "essay",
        "report",
        "research_paper",
        "literature_review",
        "case_study",
        "reflection",
        "learning_journal",
        "dissertation_chapter",
        "thesis_chapter",
        "other",
    }
)

# dissertation_chapter is an alias for thesis_chapter in this codebase.
_TYPE_ALIASES = {"dissertation_chapter": "thesis_chapter"}

_IN_TEXT_CITATION = re.compile(
    r"\([A-Za-z][^)]{0,80}\d{4}[a-z]?\)|\([A-Za-z][^)]{0,80}n\.d\.\)|\[\d+\]"
)
_REFERENCE_LINE = re.compile(
    r"^[A-Z][A-Za-z'’\-]+,\s+[A-Z]\..{0,200}\(\d{4}\)|"
    r"^[A-Z][A-Za-z'’\-]+,\s+[A-Z]\..{0,120}\d{4}\.|"
    r"^\[\d+\]\s+[A-Z]"
)
_STOP_WORDS = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "have",
        "been",
        "were",
        "will",
        "would",
        "could",
        "should",
        "their",
        "there",
        "which",
        "about",
        "these",
        "those",
        "through",
        "between",
        "during",
        "after",
        "before",
        "while",
        "where",
        "when",
        "also",
        "into",
        "such",
        "than",
        "then",
        "them",
        "they",
        "more",
        "most",
        "some",
        "other",
        "only",
        "very",
        "each",
        "both",
        "because",
        "however",
        "therefore",
        "although",
        "within",
        "without",
        "using",
        "used",
        "based",
        "study",
        "research",
        "paper",
        "essay",
        "report",
    }
)

SECTION_ALIASES: dict[str, set[str]] = {
    "title": {"title"},
    "abstract": {"abstract"},
    "executive summary": {"executive summary", "summary"},
    "introduction": {"introduction", "intro"},
    "background": {"background", "context"},
    "literature review": {"literature review", "literature", "review of literature"},
    "methodology": {"methodology", "methods", "method"},
    "analysis": {"analysis", "findings"},
    "results": {"results", "findings"},
    "discussion": {"discussion"},
    "recommendations": {"recommendations", "recommendation"},
    "conclusion": {"conclusion", "conclusions"},
    "references": {"references", "reference list", "bibliography", "works cited"},
    "appendix": {"appendix", "appendices"},
    "main body": {"main body", "body"},
    "reflection": {"reflection", "reflective practice"},
    "learning journal": {"learning journal", "journal entry"},
}

SECTION_BLUEPRINTS: dict[str, list[str]] = {
    "essay": ["Title", "Introduction", "Main Body", "Conclusion", "References"],
    "report": ["Title", "Introduction", "Main Body", "Conclusion", "References"],
    "research_paper": [
        "Title",
        "Introduction",
        "Literature Review",
        "Methodology",
        "Results",
        "Discussion",
        "Conclusion",
        "References",
    ],
    "literature_review": ["Title", "Introduction", "Literature Review", "Conclusion", "References"],
    "case_study": ["Title", "Introduction", "Analysis", "Conclusion", "References"],
    "reflection": ["Title", "Introduction", "Reflection", "Conclusion"],
    "learning_journal": ["Title", "Introduction", "Reflection", "Conclusion"],
    "thesis_chapter": ["Title", "Introduction", "Main Body", "Conclusion", "References"],
    "other": ["Title", "Introduction", "Main Body", "Conclusion"],
}

SECTION_SIGNALS: dict[str, list[str]] = {
    "introduction": [
        r"\bthis (essay|report|paper|study|chapter|dissertation|thesis)\b",
        r"\bthe (aim|purpose|objective)s? of (this|the)\b",
        r"\bwill (explore|examine|discuss|investigate|analyse|analyze|outline)\b",
        r"\bthis (section|chapter) (introduces|provides|begins)\b",
        r"\bbackground to\b",
        r"\bcontext of\b",
    ],
    "literature review": [
        r"\bliterature review\b",
        r"\bprevious (studies|research|work)\b",
        r"\bbody of (literature|research)\b",
        r"\bexisting (research|literature|studies)\b",
        r"\bscholars have\b",
        r"\baccording to\b",
        r"\bnumerous studies\b",
        r"\bempirical (evidence|studies)\b",
    ],
    "methodology": [
        r"\b(methodology|methods|research design)\b",
        r"\bdata collection\b",
        r"\b(participants|respondents|sample size)\b",
        r"\b(interviews?|questionnaires?|surveys?)\b",
        r"\b(qualitative|quantitative) (approach|analysis|method)\b",
        r"\bethical approval\b",
        r"\bprocedure\b",
    ],
    "results": [
        r"\b(results?|findings?) (show|indicate|suggest|reveal|demonstrate)\b",
        r"\bthe (data|analysis) (show|reveals?|indicates?)\b",
        r"\btable \d+\b",
        r"\bfigure \d+\b",
        r"\bstatistically significant\b",
        r"\bpercent(?:age)? of\b",
    ],
    "discussion": [
        r"\b(this|these) (findings?|results?) (suggest|indicate|imply)\b",
        r"\bimplications?\b",
        r"\blimitations?\b",
        r"\bin contrast\b",
        r"\bcompared (to|with)\b",
        r"\bfuture research\b",
        r"\bhowever,\b",
    ],
    "conclusion": [
        r"\bin conclusion\b",
        r"\bto conclude\b",
        r"\bin summary\b",
        r"\boverall,\b",
        r"\bthis (essay|paper|report|study|chapter) (has|have) (shown|demonstrated|argued)\b",
        r"\bconclud(e|ing|es)\b",
    ],
    "analysis": [
        r"\bcase study\b",
        r"\bthe (case|organisation|organization|company|client)\b",
        r"\bkey (issues?|problems?|challenges?)\b",
        r"\brecommend(?:ation)?s?\b",
    ],
    "reflection": [
        r"\bi (learned|realised|realized|reflected|felt|experienced)\b",
        r"\bmy (experience|learning|practice)\b",
        r"\breflective (practice|journal|writing)\b",
        r"\blooking back\b",
        r"\bthis experience\b",
    ],
    "references": [
        r"^\s*references?\s*$",
        r"^\s*bibliography\s*$",
        r"^\s*works cited\s*$",
    ],
}

DOC_TYPE_SIGNALS: dict[str, list[str]] = {
    "research_paper": [
        r"\bmethodology\b",
        r"\bparticipants\b",
        r"\bdata collection\b",
        r"\bresults\b",
        r"\bhypothesis\b",
        r"\bempirical\b",
    ],
    "literature_review": [
        r"\bliterature review\b",
        r"\bthematic (analysis|review)\b",
        r"\bsynthesis of\b",
        r"\bbody of literature\b",
    ],
    "case_study": [
        r"\bcase study\b",
        r"\borganisation\b",
        r"\borganization\b",
        r"\bscenario\b",
        r"\bstakeholders?\b",
    ],
    "reflection": [
        r"\bi (learned|reflected|realised|realized)\b",
        r"\bmy experience\b",
        r"\breflective\b",
        r"\bpersonal (growth|development)\b",
    ],
    "learning_journal": [
        r"\blearning journal\b",
        r"\bweekly (reflection|entry)\b",
        r"\bmodule\b",
        r"\blearning outcomes?\b",
        r"\bthis week\b",
    ],
    "report": [
        r"\bexecutive summary\b",
        r"\brecommendations?\b",
        r"\bfindings\b",
        r"\breport (aims|outlines)\b",
    ],
    "thesis_chapter": [
        r"\bthis (chapter|dissertation|thesis)\b",
        r"\bdissertation\b",
        r"\bdoctoral\b",
        r"\bchapter \d+\b",
    ],
    "essay": [
        r"\bthis essay\b",
        r"\bessay (will|aims)\b",
        r"\bargument\b",
        r"\bthesis statement\b",
    ],
}


def paragraphs_from_text(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", (text or "").strip())
    return [b.strip() for b in blocks if b.strip()]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _content_words(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"\b[a-z]{4,}\b", (text or "").lower())
        if w not in _STOP_WORDS
    }


def _topic_overlap(a: str, b: str) -> float:
    wa, wb = _content_words(a), _content_words(b)
    if not wa or not wb:
        return 0.5
    return len(wa & wb) / len(wa | wb)


def _word_heading_level(paragraph) -> int | None:
    style_name = (getattr(paragraph.style, "name", "") or "").lower()
    if style_name == "title":
        return 0
    if "heading" in style_name:
        m = re.search(r"heading\s*(\d+)", style_name)
        if m:
            return int(m.group(1))
        return 1
    return None


def _paragraph_meta_from_doc(doc: Document) -> list[dict[str, Any]]:
    meta: list[dict[str, Any]] = []
    for p in doc.paragraphs:
        text = (p.text or "").strip()
        if not text:
            continue
        level = _word_heading_level(p)
        meta.append(
            {
                "text": text,
                "is_word_heading": level is not None,
                "heading_level": level,
                "is_heading_like": is_heading_like(text),
            }
        )
    return meta


def _canonical_section(label: str) -> str:
    norm = normalize_paragraph_text(label)
    for canonical, aliases in SECTION_ALIASES.items():
        if norm == canonical or norm in aliases:
            return canonical.title()
    return label.strip()[:80]


def _heading_style_label(text: str) -> str:
    stripped = text.strip()
    if re.match(r"^\d+(\.\d+)*\s+", stripped):
        return "numbered"
    if stripped.isupper():
        return "all caps"
    if stripped.endswith(":"):
        return "colon"
    words = stripped.split()
    if words and sum(1 for w in words if w[:1].isupper()) >= max(1, len(words) - 1):
        return "title case"
    return "sentence case"


def _normalize_doc_type(document_type: str | None) -> str:
    raw = (document_type or "other").lower().replace(" ", "_").replace("-", "_")
    raw = _TYPE_ALIASES.get(raw, raw)
    if raw not in DOCUMENT_TYPES:
        return "other"
    return raw


def _strong_heading_count(paragraphs: list[str]) -> int:
    count = 0
    for paragraph in paragraphs:
        norm = normalize_paragraph_text(paragraph)
        if norm in COMMON_HEADINGS | REFS_HEADINGS:
            count += 1
            continue
        if is_heading_like(paragraph) and len(paragraph.split()) <= 4:
            count += 1
    return count


def _count_heading_signals(paragraphs: list[str], meta: list[dict[str, Any]] | None) -> int:
    if meta:
        word_headings = sum(1 for m in meta if m.get("is_word_heading"))
        if word_headings >= 2:
            return word_headings
        return sum(1 for m in meta if m.get("is_heading_like") or m.get("is_word_heading"))
    return _strong_heading_count(paragraphs)


def headings_exist(
    paragraphs: list[str],
    *,
    meta: list[dict[str, Any]] | None = None,
    word_count: int | None = None,
) -> bool:
    """True when the document already has meaningful section headings."""
    wc = word_count if word_count is not None else sum(_word_count(p) for p in paragraphs)
    heading_count = _count_heading_signals(paragraphs, meta)

    if meta:
        word_headings = sum(1 for m in meta if m.get("is_word_heading"))
        if word_headings >= 2:
            return True
        if word_headings >= 1 and wc >= 20:
            return True
        heading_like = sum(1 for m in meta if m.get("is_heading_like") or m.get("is_word_heading"))
        if heading_like >= 2 and wc >= 200:
            return True
        return False

    if heading_count >= 3:
        return True
    if heading_count >= 2 and wc >= 250:
        return True
    if heading_count >= 1 and wc >= 900:
        return True
    return False


def _section_signal_scores(paragraph: str) -> dict[str, float]:
    low = paragraph.lower()
    scores: dict[str, float] = {}
    for section, patterns in SECTION_SIGNALS.items():
        hits = sum(1 for pat in patterns if re.search(pat, low, re.I))
        if hits:
            scores[section] = min(1.0, 0.35 + hits * 0.2)

    citations = len(_IN_TEXT_CITATION.findall(paragraph))
    if citations >= 2:
        scores["literature review"] = max(scores.get("literature review", 0), 0.55)
    elif citations == 1:
        scores["literature review"] = max(scores.get("literature review", 0), 0.25)

    if re.search(r"\b(i|my|we)\b", low) and re.search(
        r"\b(learned|reflected|felt|experienced|realised|realized)\b", low
    ):
        scores["reflection"] = max(scores.get("reflection", 0), 0.5)

    return scores


def _infer_document_type(paragraphs: list[str], hint: str | None) -> tuple[str, float]:
    if hint and hint != "other":
        return hint, 0.72

    joined = "\n".join(paragraphs).lower()
    scores: dict[str, float] = {}
    for doc_type, patterns in DOC_TYPE_SIGNALS.items():
        hits = sum(1 for pat in patterns if re.search(pat, joined, re.I))
        if hits:
            scores[doc_type] = hits / max(len(patterns), 1)

    citation_density = sum(len(_IN_TEXT_CITATION.findall(p)) for p in paragraphs) / max(
        len(paragraphs), 1
    )
    if citation_density >= 1.2 and scores.get("literature_review", 0) < 0.4:
        scores["literature_review"] = max(scores.get("literature_review", 0), 0.45)
    if citation_density >= 0.6 and "research_paper" not in scores:
        scores["research_paper"] = max(scores.get("research_paper", 0), 0.35)

    first_person = sum(
        1 for p in paragraphs if re.search(r"\b(i|my|we)\b", p.lower())
    ) / max(len(paragraphs), 1)
    if first_person >= 0.35:
        scores["reflection"] = max(scores.get("reflection", 0), 0.5)
        scores["learning_journal"] = max(scores.get("learning_journal", 0), 0.4)

    if not scores:
        return "essay", 0.42

    best_type = max(scores, key=scores.get)
    confidence = min(0.88, 0.38 + scores[best_type] * 0.9)
    return best_type, round(confidence, 2)


def _looks_like_title(paragraph: str) -> bool:
    words = paragraph.split()
    if not 2 <= len(words) <= 22:
        return False
    if paragraph.rstrip().endswith("."):
        return False
    if len(_IN_TEXT_CITATION.findall(paragraph)) >= 2:
        return False
    if _word_count(paragraph) > 30:
        return False
    return True


def _paragraph_is_reference_line(paragraph: str) -> bool:
    stripped = paragraph.strip()
    if not stripped:
        return False
    if _REFERENCE_LINE.search(stripped):
        return True
    if re.search(r"\(\d{4}\)", stripped) and re.search(r"[A-Z][a-z]+,\s+[A-Z]\.", stripped):
        return True
    return False


def _looks_like_reference_block(paragraphs: list[str], start_idx: int) -> bool:
    """start_idx is 0-based index into paragraphs."""
    if start_idx >= len(paragraphs):
        return False
    first = paragraphs[start_idx].strip().lower()
    if re.search(r"\b(in conclusion|to conclude|in summary)\b", first):
        return False
    tail = paragraphs[start_idx:]
    if len(tail) < 2:
        return False
    ref_like = sum(1 for p in tail if _paragraph_is_reference_line(p))
    if ref_like < 2:
        return False
    return ref_like / len(tail) >= 0.5


def _detect_title_index(paragraphs: list[str]) -> int | None:
    if not paragraphs:
        return None
    if _looks_like_title(paragraphs[0]):
        return 0
    if len(paragraphs) > 1 and _looks_like_title(paragraphs[1]):
        first = paragraphs[0].lower()
        if len(paragraphs[0].split()) <= 6 and not first.endswith("."):
            return 0
    return None


def _detect_references_start(paragraphs: list[str]) -> int | None:
    n = len(paragraphs)
    if n < 2:
        return None

    for idx in range(max(0, n - 15), n):
        label = normalize_paragraph_text(paragraphs[idx])
        if label in SECTION_ALIASES["references"]:
            return idx

    end = n - 1
    while end >= 0 and _paragraph_is_reference_line(paragraphs[end]):
        end -= 1
    refs_start = end + 1
    if refs_start >= n:
        return None

    if refs_start > 0:
        prev_signals = _section_signal_scores(paragraphs[refs_start - 1])
        if prev_signals.get("conclusion", 0) >= 0.35:
            return refs_start

    if n - refs_start >= 2:
        return refs_start
    if n - refs_start == 1 and _paragraph_is_reference_line(paragraphs[refs_start]):
        return refs_start

    search_from = max(0, int(n * 0.55))
    for idx in range(search_from, n):
        if _looks_like_reference_block(paragraphs, idx):
            return idx
    return None


def _make_node(
    *,
    title: str,
    level: int,
    confidence: float,
    source: str,
    paragraph_indices: list[int],
) -> dict[str, Any]:
    if not paragraph_indices:
        paragraph_indices = []
    start, end = (min(paragraph_indices), max(paragraph_indices)) if paragraph_indices else (None, None)
    return {
        "title": title,
        "canonical": _canonical_section(title),
        "level": level,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "source": source,
        "paragraph_indices": paragraph_indices,
        "paragraph_range": [start, end] if start is not None else None,
        "paragraph_count": len(paragraph_indices),
    }


def _build_preserved_tree(
    paragraphs: list[str],
    meta: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    tree: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for idx, paragraph in enumerate(paragraphs, start=1):
        m = meta[idx - 1] if meta and idx - 1 < len(meta) else None
        is_heading = bool(m and m.get("is_word_heading")) or is_heading_like(paragraph)
        if is_heading:
            if current:
                tree.append(current)
            level = 2
            if m and m.get("heading_level") is not None:
                level = max(1, int(m["heading_level"]) + 1)
            source = "word_heading" if m and m.get("is_word_heading") else "detected_heading"
            conf = 0.95 if source == "word_heading" else 0.82
            current = _make_node(
                title=paragraph.strip()[:100],
                level=level,
                confidence=conf,
                source=source,
                paragraph_indices=[idx],
            )
            continue

        if current is None:
            title = "Title" if idx == 1 and _looks_like_title(paragraph) else "Preamble"
            conf = 0.7 if title == "Title" else 0.45
            current = _make_node(
                title=title,
                level=1 if title == "Title" else 2,
                confidence=conf,
                source="preserved",
                paragraph_indices=[idx],
            )
        else:
            current["paragraph_indices"].append(idx)
            start, end = current["paragraph_range"] or [idx, idx]
            current["paragraph_range"] = [start, end]
            current["paragraph_count"] = len(current["paragraph_indices"])

    if current:
        tree.append(current)
    return tree


def _blueprint_for_type(doc_type: str) -> list[str]:
    return list(SECTION_BLUEPRINTS.get(doc_type, SECTION_BLUEPRINTS["other"]))


def _section_key(section_title: str) -> str:
    return normalize_paragraph_text(section_title)


def _allocate_sections(
    body_paragraphs: list[tuple[int, str]],
    blueprint: list[str],
    doc_type: str,
) -> list[dict[str, Any]]:
    """Assign body paragraphs to blueprint sections using signals and position."""
    if not body_paragraphs:
        return []

    body_sections = [s for s in blueprint if _section_key(s) not in {"title", "references"}]
    if not body_sections:
        body_sections = ["Main Body"]

    n = len(body_paragraphs)
    if n == 1:
        return [
            _make_node(
                title=body_sections[0],
                level=2,
                confidence=0.4,
                source="inferred",
                paragraph_indices=[body_paragraphs[0][0]],
            )
        ]

    boundaries: list[tuple[int, str, float]] = []
    prev_text = body_paragraphs[0][1]
    for pos, (para_idx, text) in enumerate(body_paragraphs[1:], start=1):
        overlap = _topic_overlap(prev_text, text)
        signals = _section_signal_scores(text)
        best_section = max(signals, key=signals.get) if signals else ""
        best_score = signals.get(best_section, 0) if signals else 0
        if overlap < 0.18 and _word_count(text) >= 35:
            best_score = max(best_score, 0.35)
        if best_score >= 0.35 or (overlap < 0.12 and pos > 0):
            boundaries.append((pos, best_section or "", best_score))
        prev_text = text

    section_count = len(body_sections)
    chunk = max(1, n // section_count)
    nodes: list[dict[str, Any]] = []
    assigned: list[list[int]] = [[] for _ in body_sections]

    boundary_map: dict[int, str] = {}
    for pos, section, score in boundaries:
        if section and score >= 0.4:
            boundary_map[pos] = section

    default_idx = 0
    for pos, (para_idx, text) in enumerate(body_paragraphs):
        if pos in boundary_map:
            target = boundary_map[pos]
            for i, name in enumerate(body_sections):
                if _section_key(target) == _section_key(name) or _section_key(target) in SECTION_ALIASES.get(
                    _section_key(name), {_section_key(name)}
                ):
                    default_idx = i
                    break
        elif pos > 0 and pos % chunk == 0 and default_idx < section_count - 1:
            default_idx += 1
        assigned[default_idx].append(para_idx)

        # Nudge: strong local signal can shift assignment
        signals = _section_signal_scores(text)
        if signals:
            best = max(signals, key=signals.get)
            if signals[best] >= 0.55:
                for i, name in enumerate(body_sections):
                    if _section_key(best) == _section_key(name) or _section_key(best) in SECTION_ALIASES.get(
                        _section_key(name), {_section_key(name)}
                    ):
                        if para_idx in assigned[default_idx]:
                            assigned[default_idx].remove(para_idx)
                        assigned[i].append(para_idx)
                        default_idx = i
                        break

    para_text_by_idx = {i: t for i, t in body_paragraphs}

    for name, indices in zip(body_sections, assigned):
        if not indices:
            continue
        avg_conf = 0.45
        signal_hits = 0
        key = _section_key(name)
        for para_idx in indices:
            para_text = para_text_by_idx.get(para_idx, "")
            sig = _section_signal_scores(para_text)
            if any(
                key == _section_key(k) or key in SECTION_ALIASES.get(_section_key(k), set())
                for k in sig
            ):
                signal_hits += 1
        if signal_hits:
            avg_conf = min(0.85, 0.5 + signal_hits * 0.08)
        elif len(indices) >= max(2, n // (section_count * 2)):
            avg_conf = 0.55
        nodes.append(
            _make_node(
                title=name,
                level=2,
                confidence=avg_conf,
                source="inferred",
                paragraph_indices=sorted(indices),
            )
        )

    if not nodes:
        nodes.append(
            _make_node(
                title="Main Body",
                level=2,
                confidence=0.38,
                source="inferred",
                paragraph_indices=[i for i, _ in body_paragraphs],
            )
        )
    return nodes


def _reconstruct_tree(
    paragraphs: list[str],
    doc_type: str,
) -> list[dict[str, Any]]:
    blueprint = _blueprint_for_type(doc_type)
    tree: list[dict[str, Any]] = []

    title_idx = _detect_title_index(paragraphs)
    refs_idx = _detect_references_start(paragraphs)

    used: set[int] = set()
    if title_idx is not None:
        tree.append(
            _make_node(
                title="Title",
                level=1,
                confidence=0.78 if _looks_like_title(paragraphs[title_idx]) else 0.55,
                source="inferred",
                paragraph_indices=[title_idx + 1],
            )
        )
        used.add(title_idx)

    body_start = 0 if title_idx is None else title_idx + 1
    body_end = refs_idx if refs_idx is not None else len(paragraphs)
    body_paragraphs = [
        (i + 1, paragraphs[i]) for i in range(body_start, body_end) if i not in used
    ]

    tree.extend(_allocate_sections(body_paragraphs, blueprint, doc_type))

    if refs_idx is not None:
        ref_indices = list(range(refs_idx + 1, len(paragraphs) + 1))
        conf = 0.88 if normalize_paragraph_text(paragraphs[refs_idx]) in SECTION_ALIASES["references"] else 0.72
        tree.append(
            _make_node(
                title="References",
                level=2,
                confidence=conf,
                source="inferred",
                paragraph_indices=ref_indices,
            )
        )

    return tree


def _enrich_recovery_result(result: dict[str, Any]) -> dict[str, Any]:
    """Add API-facing sections, headings, confidence_scores, and document_type."""
    tree = result.get("structure_tree") or []
    if "document_type" not in result:
        result["document_type"] = result.get("inferred_document_type")
    if "sections" not in result:
        result["sections"] = [
            {
                "title": node["title"],
                "heading_text": node.get("heading_text") or node["title"],
                "confidence": node["confidence"],
                "paragraph_indices": node.get("paragraph_indices") or [],
                "insert_heading": node.get(
                    "insert_heading",
                    normalize_paragraph_text(node.get("title") or "")
                    not in {"title", "preamble"},
                ),
            }
            for node in tree
        ]
    if "headings" not in result:
        result["headings"] = [node.get("heading_text") or node["title"] for node in tree]
    if "confidence_scores" not in result:
        result["confidence_scores"] = [node["confidence"] for node in tree]
    return result


def recover_structure(
    *,
    text: str | None = None,
    paragraphs: list[str] | None = None,
    doc: Document | None = None,
    document_type: str | None = None,
    prefer_ai: bool = True,
) -> dict[str, Any]:
    """
    Recover or preserve academic document structure.

    Returns a structure tree with per-section confidence, preserved paragraph
    list, and metadata about recovery mode.
    """
    meta: list[dict[str, Any]] | None = None
    if doc is not None:
        meta = _paragraph_meta_from_doc(doc)
        paragraphs = [m["text"] for m in meta]
    elif paragraphs is None:
        paragraphs = paragraphs_from_text(text or "")
    elif text is None:
        text = "\n\n".join(paragraphs)

    if not paragraphs:
        return {"error": "No readable text found. Paste content or upload a document."}

    wc = _word_count(text or "\n\n".join(paragraphs))
    has_headings = headings_exist(paragraphs, meta=meta, word_count=wc)
    doc_type_hint = _normalize_doc_type(document_type)

    if has_headings:
        structure_tree = _build_preserved_tree(paragraphs, meta)
        recovery_mode = "preserved"
        inferred_type = doc_type_hint if doc_type_hint != "other" else _infer_document_type(paragraphs, None)[0]
        type_confidence = 0.8
    else:
        if prefer_ai and gemini_enabled():
            try:
                from services.ai_structure_recovery import recover_structure_with_ai

                ai_result = recover_structure_with_ai(
                    text=text,
                    paragraphs=paragraphs,
                    document_type=doc_type_hint if doc_type_hint != "other" else None,
                )
                if ai_result and ai_result.get("ai_failure"):
                    failure_reason = str(ai_result.get("failure_reason") or "unavailable")
                    return {
                        "error": ai_result.get("error")
                        or f"AI structure recovery failed: {failure_reason}",
                        "ai_failure": True,
                        "failure_reason": failure_reason,
                        "recovery_mode": "ai_failed",
                        "headings_present": False,
                        "paragraphs": paragraphs,
                        "paragraph_count": len(paragraphs),
                        "word_count": wc,
                        "ai_powered": False,
                        "gemini_diagnostics": ai_result.get("gemini_diagnostics") or {},
                    }
                if ai_result and not ai_result.get("ai_failure"):
                    return _enrich_recovery_result(ai_result)
                return {
                    "error": "AI structure recovery failed: no response from Gemini",
                    "ai_failure": True,
                    "failure_reason": "unavailable",
                    "recovery_mode": "ai_failed",
                    "headings_present": False,
                    "paragraphs": paragraphs,
                    "paragraph_count": len(paragraphs),
                    "word_count": wc,
                    "ai_powered": False,
                    "gemini_diagnostics": {
                        "enabled": True,
                        "model": gemini_model(),
                        "api_call_success": False,
                        "failure_reason": "unavailable",
                    },
                }
            except Exception:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).exception("AI structure recovery unavailable")
                return {
                    "error": "AI structure recovery failed: unexpected error",
                    "ai_failure": True,
                    "failure_reason": "unavailable",
                    "recovery_mode": "ai_failed",
                    "headings_present": False,
                    "paragraphs": paragraphs,
                    "paragraph_count": len(paragraphs),
                    "word_count": wc,
                    "ai_powered": False,
                    "gemini_diagnostics": {
                        "enabled": True,
                        "model": gemini_model(),
                        "api_call_success": False,
                        "failure_reason": "unavailable",
                    },
                }

        inferred_type, type_confidence = _infer_document_type(paragraphs, doc_type_hint)
        structure_tree = _reconstruct_tree(paragraphs, inferred_type)
        recovery_mode = "reconstructed"

    section_confidences = [node["confidence"] for node in structure_tree]
    overall = round(sum(section_confidences) / len(section_confidences), 2) if section_confidences else 0.0

    return _enrich_recovery_result(
        {
            "headings_present": has_headings,
            "recovery_mode": recovery_mode,
            "inferred_document_type": inferred_type,
            "document_type_confidence": type_confidence,
            "overall_confidence": overall,
            "structure_tree": structure_tree,
            "paragraphs": paragraphs,
            "paragraph_count": len(paragraphs),
            "word_count": wc,
            "ai_powered": False,
            "gemini_diagnostics": {
                "enabled": gemini_enabled(),
                "model": gemini_model(),
                "api_call_success": False,
                "token_usage_estimate": 0,
            },
        }
    )


def structure_tree_to_detected_sections(structure_tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map structure tree nodes to legacy detected_sections format for the checker UI."""
    detected: list[dict[str, Any]] = []
    for node in structure_tree:
        indices = node.get("paragraph_indices") or []
        detected.append(
            {
                "title": node.get("title") or "Untitled",
                "canonical": node.get("canonical") or node.get("title") or "Untitled",
                "paragraph_number": indices[0] if indices else None,
                "style": node.get("source") or "inferred",
                "confidence": node.get("confidence"),
                "paragraph_range": node.get("paragraph_range"),
                "paragraph_count": node.get("paragraph_count", 0),
            }
        )
    return detected
