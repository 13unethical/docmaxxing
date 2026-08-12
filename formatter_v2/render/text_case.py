"""Academic title-case for headings (not ``str.title()``)."""

from __future__ import annotations

import re

# Articles, coordinating conjunctions, and short prepositions stay lowercase
# unless they are the first/last word or follow a colon.
_MINOR_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "but",
        "or",
        "nor",
        "for",
        "yet",
        "so",
        "as",
        "at",
        "by",
        "in",
        "of",
        "off",
        "on",
        "per",
        "to",
        "up",
        "via",
        "with",
        "from",
        "into",
        "onto",
        "over",
        "than",
        "that",
        "upon",
    }
)


def _alpha_core(token: str) -> str:
    return "".join(ch for ch in token if ch.isalpha()).casefold()


def _has_internal_capital(token: str) -> bool:
    """True when a non-initial letter is already uppercase (IPCC, McDonald, RCP4.5)."""
    seen_letter = False
    for ch in token:
        if not ch.isalpha():
            continue
        if not seen_letter:
            seen_letter = True
            continue
        if ch.isupper():
            return True
    return False


def _capitalize_word(token: str) -> str:
    """Capitalise the first letter; lower the rest. Apostrophes stay intact (Don't)."""
    chars = list(token)
    seen_letter = False
    for i, ch in enumerate(chars):
        if not ch.isalpha():
            continue
        if not seen_letter:
            chars[i] = ch.upper()
            seen_letter = True
        else:
            chars[i] = ch.lower()
    return "".join(chars)


def _lowercase_word(token: str) -> str:
    return "".join(ch.lower() if ch.isalpha() else ch for ch in token)


def _transform_token(token: str, *, force_cap: bool) -> str:
    if not token:
        return token
    if _has_internal_capital(token):
        return token

    # Hyphenated compounds: capitalise each segment (well-being → Well-Being).
    if "-" in token:
        return "-".join(
            (
                part
                if not part or _has_internal_capital(part)
                else _capitalize_word(part)
            )
            for part in token.split("-")
        )

    core = _alpha_core(token)
    is_minor = core in _MINOR_WORDS
    if force_cap or not is_minor:
        return _capitalize_word(token)
    return _lowercase_word(token)


def _title_case_words(text: str) -> str:
    words = text.split(" ")
    result: list[str] = []
    force_next = False
    last_index = len(words) - 1

    for index, word in enumerate(words):
        if word == "":
            result.append(word)
            continue

        force_cap = index == 0 or index == last_index or force_next
        force_next = word.rstrip(".,;!?").endswith(":")

        result.append(_transform_token(word, force_cap=force_cap))

    return " ".join(result)


# "2.1 …", "2. …", "VII. …", "IV …" — stripped before first/last-word rules.
_LEADING_SECTION_NUMBER_RE = re.compile(
    r"^(?P<num>(?:\d+(?:\.\d+)+|\d+|[IVXLCDM]+)[.)]?)\s+",
    re.IGNORECASE,
)


def academic_title_case(text: str) -> str:
    """Title case for academic headings.

    Minor words stay lowercase unless first/last or after a colon.
    Hyphenated parts are capitalised separately. Existing internal capitals
    (abbreviations, camel-ish names) are left unchanged. Apostrophes are
    preserved (``don't`` → ``Don't``, never ``Don'T``).

    A leading section number (``2.1``, ``VII.``) is kept verbatim and does
    not count as the first word.
    """
    if not text:
        return text

    match = _LEADING_SECTION_NUMBER_RE.match(text)
    if match:
        return match.group(0) + _title_case_words(text[match.end() :])
    return _title_case_words(text)
