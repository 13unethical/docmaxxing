"""Deterministic heading detection — identify the heading FIRST, then format.

This module is the single source of truth for splitting embedded headings out of
merged paragraphs. It deliberately avoids word-walking heuristics that absorb the
first sentence into the heading or promote stopwords (are / the / as) to headings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Isolated tokens that must NEVER become headings on their own.
_NEVER_HEADING_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "because",
        "but",
        "by",
        "for",
        "from",
        "however",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "so",
        "than",
        "that",
        "the",
        "then",
        "this",
        "to",
        "was",
        "were",
        "with",
    }
)

# Labeled academic section prefixes (title comes after ':' or as the rest of the line).
_LABELED_PREFIX_RE = re.compile(
    r"^(?P<label>"
    r"(?:Journal\s+Entry|Body\s+Paragraph|Section|Part|Chapter|Unit|Module|Week|Entry)"
    r"\s+\d+"
    r")\s*:\s*(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# Standalone labels that may be glued to body with an optional period separator.
_STANDALONE_LABEL_RE = re.compile(
    r"^(?P<label>"
    r"Reflection|References|Bibliography|Works\s+Cited|Introduction|Conclusion|"
    r"Abstract|Appendix|Discussion|Methods|Results|Literature\s+Review|"
    r"Executive\s+Summary|Concluding\s+Paragraph|Learning\s+Outcomes"
    r")\s*(?P<sep>\.|\s+)\s*(?P<body>[A-Z“\"‘'].+)$",
    re.IGNORECASE | re.DOTALL,
)

# Sentence boundary after a heading title: period, then whitespace, then a capital.
# Excludes common abbreviation dots via a lookbehind check in code.
_SENTENCE_BOUNDARY_RE = re.compile(r"\.(?:\s+)(?=[A-Z“\"‘'])")

# Known abbreviations / initials that should not end a heading title.
_ABBREV_BEFORE_PERIOD = re.compile(
    r"(?:"
    r"\b(?:eq|al|etc|vs|vol|pp|fig|ed|eds|dr|mr|mrs|ms|prof|approx|dept|univ)"
    r"|(?:\b[A-Z])"  # single-letter initial: J. Smith
    r"|(?:\b(?:et)\s+al)"
    r")$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class HeadingSplit:
    """Result of peeling a heading from a possibly-merged paragraph."""

    heading: str
    body: str | None
    level: int = 2


class HeadingDetector:
    """Identify headings first; never invent headings from random words."""

    @staticmethod
    def _strip_md_hashes(text: str) -> str:
        t = (text or "").strip()
        m = re.match(r"^#{1,6}\s+(.*)$", t)
        return m.group(1).strip() if m else t

    @staticmethod
    def collapse_soft_linebreaks(text: str) -> str:
        """Turn soft wraps inside a paragraph into spaces (preserve sentence integrity)."""
        return re.sub(r"[ \t]*\n[ \t]*", " ", (text or "")).strip()

    def split_embedded(self, text: str) -> HeadingSplit | None:
        """If ``text`` begins with a heading glued to body, return the split.

        Returns ``None`` when the paragraph is not an embedded heading+body pair.
        """
        stripped = (text or "").strip()
        if not stripped:
            return None

        # Soft wraps (Word line breaks / wrapped draft lines) are NOT structure.
        # Only keep a newline when the first line is a true heading-only title.
        if "\n" in stripped:
            first, rest = stripped.split("\n", 1)
            first_clean = self._strip_md_hashes(first.strip())
            rest_clean = rest.strip()
            if (
                first_clean
                and rest_clean
                and self.is_heading_only_line(first_clean)
                and not self.is_forbidden_heading(first_clean)
            ):
                level = self.detect_level(first_clean) or 2
                # Collapse further soft wraps inside the body.
                body = self._ensure_capital_start(self.collapse_soft_linebreaks(rest_clean))
                return HeadingSplit(heading=first_clean.rstrip("."), body=body, level=level)
            stripped = self.collapse_soft_linebreaks(stripped)

        # Single-line markdown heading prefix: "## References Smith…"
        hash_m = re.match(r"^#{1,6}\s+(.*)$", stripped, re.DOTALL)
        if hash_m:
            stripped = hash_m.group(1).strip()

        labeled = self._split_labeled_heading(stripped)
        if labeled is not None:
            return labeled

        standalone = self._split_standalone_label(stripped)
        if standalone is not None:
            return standalone

        return None

    def is_heading_only_line(self, text: str) -> bool:
        """True only when the line is a heading with no glued first sentence."""
        t = self._strip_md_hashes((text or "").strip())
        if not t or self.is_forbidden_heading(t):
            return False

        # Standalone academic labels (optional trailing period).
        if re.match(
            r"^(?:Reflection|References|Bibliography|Works\s+Cited|Introduction|Conclusion|"
            r"Abstract|Appendix|Discussion|Methods|Results|Literature\s+Review|"
            r"Executive\s+Summary|Concluding\s+Paragraph|Learning\s+Outcomes)\s*\.?$",
            t,
            re.I,
        ):
            return True

        m = _LABELED_PREFIX_RE.match(t)
        if m:
            rest = (m.group("rest") or "").strip()
            if not rest:
                return True
            # Glued body after the title ⇒ not heading-only.
            if self._find_title_body_boundary(rest) is not None:
                return False
            if self._find_space_merged_boundary(rest) is not None:
                return False
            # Title phrase only (keep period that ends the title).
            return len(rest.split()) <= 16

        if re.match(r"^\d+(?:\.\d+)*\.?\s+[A-Za-z].+$", t):
            # Numbered heading without a following prose sentence.
            if _SENTENCE_BOUNDARY_RE.search(t) and len(t.split()) > 12:
                return False
            return len(t.split()) <= 14

        words = t.split()
        if len(words) <= 8 and not t.endswith(".") and t[:1].isupper():
            if t.isupper() and len(t) > 3:
                return True
            if not ({w.lower().strip(".,;:") for w in words} & _NEVER_HEADING_WORDS):
                titleish = sum(1 for w in words if w[:1].isupper() or w.isdigit())
                return titleish >= max(1, len(words) - 1)
        return False

    def is_heading_line(self, text: str) -> bool:
        """True when the whole line is a heading (no glued body)."""
        return self.is_heading_only_line(text)

    def is_forbidden_heading(self, text: str) -> bool:
        """Reject isolated function words and other non-headings."""
        t = (text or "").strip().strip(".:;,—–-")
        if not t:
            return True
        words = t.split()
        if len(words) == 1 and words[0].lower() in _NEVER_HEADING_WORDS:
            return True
        if len(words) <= 2 and all(w.lower() in _NEVER_HEADING_WORDS for w in words):
            return True
        return False

    def detect_level(
        self,
        text: str,
        *,
        auto_detect: bool = True,
        is_first_nonempty: bool = False,
    ) -> int:
        """Return 0 = body, 1 = title, 2 = major section, 3 = subsection."""
        if not auto_detect:
            return 0
        t = (text or "").strip()
        if not t or self.is_forbidden_heading(t):
            return 0

        # Prefer embedded split: only the heading portion decides the level.
        split = self.split_embedded(t)
        check = split.heading if split and split.body else t

        if self.is_forbidden_heading(check):
            return 0
        if re.match(
            r"^(?:Journal\s+Entry|Body\s+Paragraph|Section|Part|Chapter|Unit|Module|Week|Entry)\s+\d+",
            check,
            re.I,
        ):
            return 2
        if re.match(
            r"^(?:Reflection|References|Bibliography|Works\s+Cited|Introduction|Conclusion|"
            r"Abstract|Appendix|Discussion|Methods|Results|Literature\s+Review|"
            r"Executive\s+Summary|Concluding\s+Paragraph)\s*\.?$",
            check,
            re.I,
        ):
            return 2
        if re.match(r"^\d+(?:\.\d+)*\.?\s+[A-Za-z]", check):
            return 2
        if is_first_nonempty and len(check.split()) >= 2 and check[:1].isupper() and not check.endswith("."):
            # Document title candidate — allow long titles with quoted subtitles.
            if len(check.split()) <= 40 and ". " not in check:
                return 1
        if self.is_heading_line(check) and len(check.split()) <= 5:
            return 3
        return 0

    # ------------------------------------------------------------------ internals

    def _split_labeled_heading(self, stripped: str) -> HeadingSplit | None:
        m = _LABELED_PREFIX_RE.match(stripped)
        if not m:
            return None
        label = m.group("label").strip()
        # Preserve original label casing from the source span.
        label = stripped[: m.start("rest")].split(":", 1)[0].strip()
        rest = m.group("rest").strip()
        if not rest:
            return HeadingSplit(heading=f"{label}:", body=None, level=2)

        boundary = self._find_title_body_boundary(rest)
        if boundary is None:
            # No clear body sentence — treat as heading-only when short.
            if len(rest.split()) <= 16:
                heading = f"{label}: {rest}".strip()
                if not self.is_forbidden_heading(heading):
                    return None  # whole paragraph is heading-like; caller keeps as-is
            return None

        title = rest[: boundary["title_end"]].strip()
        body = rest[boundary["body_start"] :].strip()
        if not body:
            return None
        body = self._ensure_capital_start(body)
        # Period belongs to the heading when it terminated the title.
        heading = f"{label}: {title}".strip()
        if boundary["include_period"] and not heading.endswith("."):
            heading = heading + "."
        if self.is_forbidden_heading(heading):
            return None
        return HeadingSplit(heading=heading, body=body, level=2)

    def _split_standalone_label(self, stripped: str) -> HeadingSplit | None:
        m = _STANDALONE_LABEL_RE.match(stripped)
        if not m:
            return None
        # Keep source casing for the label span.
        label = stripped[: m.start("sep")].strip().rstrip(".")
        body = m.group("body").strip()
        if not body or self.is_forbidden_heading(label):
            return None
        # Separator period is discarded — heading is the bare label.
        body = self._ensure_capital_start(body)
        return HeadingSplit(heading=label, body=body, level=2)

    def _find_title_body_boundary(self, rest: str) -> dict[str, int | bool] | None:
        """Locate where the heading title ends and the first body sentence begins."""
        # Primary rule: period that ends the title, then a capitalised sentence.
        for match in _SENTENCE_BOUNDARY_RE.finditer(rest):
            before = rest[: match.start()]
            if _ABBREV_BEFORE_PERIOD.search(before.rstrip()):
                continue
            # Avoid splitting immediately after the colon with an empty title.
            if not before.strip():
                continue
            # Title should not be a single stopword.
            title_words = before.strip().split()
            if not title_words:
                continue
            if len(title_words) == 1 and title_words[0].lower() in _NEVER_HEADING_WORDS:
                continue
            body = rest[match.end() :].strip()
            if not body or not body[:1].isupper():
                continue
            # Body after the split must look like prose, not a Title-Case subtitle.
            if self._looks_like_title_subtitle(body) and len(body.split()) <= 8 and "." not in body:
                continue
            return {
                "title_end": match.start(),  # exclude the period from title slice
                "body_start": match.end(),
                "include_period": True,
            }

        # Fallback: space-merged title + sentence with no period between them
        # (e.g. "Week 1 Today I learned…"). Require prose after the pivot word.
        return self._find_space_merged_boundary(rest)

    def _find_space_merged_boundary(self, rest: str) -> dict[str, int | bool] | None:
        words = rest.split()
        if len(words) < 4:
            return None
        # Walk candidates: a sentence-case word whose following tokens are mostly lowercase.
        # Reject ALL-CAPS acronyms (AI, RBV) — those belong in titles, not body starts.
        for i, word in enumerate(words[:-2]):
            if i == 0:
                continue
            if not self._is_sentence_case_pivot(word):
                continue
            if word.lower().strip(".,;:") in _NEVER_HEADING_WORDS:
                continue
            following = words[i + 1 : i + 5]
            if not following:
                continue
            # Sentence-case body: the word right after the pivot is usually lowercase
            # ("Artificial intelligence…"). Title Case after the pivot ("Higher Education")
            # means we are still inside the heading title.
            nxt = following[0].strip(".,;:\"'“”‘’")
            if (
                nxt
                and nxt[:1].isupper()
                and nxt != "I"
                and not nxt.isupper()
                and nxt.lower() not in _NEVER_HEADING_WORDS
            ):
                continue
            lowerish = sum(1 for w in following if w and w[:1].islower())
            if lowerish < max(1, (len(following) + 1) // 2):
                continue
            # Preceding span must look like a finished title (mostly Title Case).
            title_words = words[:i]
            if not title_words:
                continue
            title_upper = sum(
                1
                for w in title_words
                if w[:1].isupper() or w.isdigit() or w.lower() in _NEVER_HEADING_WORDS
            )
            if title_upper < max(1, int(len(title_words) * 0.6)):
                continue
            body_start = self._nth_word_offset(rest, i)
            if body_start <= 0:
                return None
            body = rest[body_start:].strip()
            if not body or not body[:1].isupper():
                continue
            return {
                "title_end": body_start,
                "body_start": body_start,
                "include_period": False,
            }
        return None

    @staticmethod
    def _is_sentence_case_pivot(word: str) -> bool:
        """True for prose sentence starts (Today, Artificial), not acronyms (AI)."""
        token = word.strip(".,;:\"'“”‘’")
        if not token or not token[:1].isupper():
            return False
        if token == "I":
            return True
        # ALL-CAPS acronyms stay in the title.
        if len(token) >= 2 and token.isupper():
            return False
        # Prefer Ordinary sentence-case words.
        return bool(re.match(r"^[A-Z][a-z]+(?:['’][a-z]+)?$", token))

    @staticmethod
    def _nth_word_offset(text: str, index: int) -> int:
        count = 0
        for match in re.finditer(r"\S+", text):
            if count == index:
                return match.start()
            count += 1
        return -1

    @staticmethod
    def _looks_like_title_subtitle(text: str) -> bool:
        words = text.split()
        if not words:
            return False
        titled = sum(1 for w in words if w[:1].isupper() or w.isdigit())
        return titled >= max(1, int(len(words) * 0.7))

    @staticmethod
    def _ensure_capital_start(text: str) -> str:
        t = (text or "").strip()
        if not t:
            return t
        # Strip a dangling leading period left by a bad prior split.
        t = t.lstrip(".").strip()
        if not t:
            return t
        if t[:1].islower():
            return t[:1].upper() + t[1:]
        return t


# Process-wide detector used by structure engine / reconstruction.
DEFAULT_HEADING_DETECTOR = HeadingDetector()


def split_heading_from_paragraph(text: str) -> tuple[str, str | None]:
    """Compatibility wrapper: ``(heading, body|None)`` like the legacy API."""
    split = DEFAULT_HEADING_DETECTOR.split_embedded(text)
    if split is None:
        return (text or "").strip(), None
    return split.heading, split.body
