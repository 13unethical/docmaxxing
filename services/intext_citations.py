"""Generate in-text citations, footnotes, and endnotes across common academic styles."""

from __future__ import annotations

import re
from typing import Any


def _parse_author(author: str) -> tuple[str, str]:
    """Return (family_name_for_narrative, apa_style_short)."""
    a = (author or "").strip()
    if not a:
        return "Author", "Author"
    if "," in a:
        parts = a.split(",", 1)
        family = parts[0].strip()
        return family, family
    words = a.split()
    if len(words) >= 2:
        return words[-1], words[-1]
    return a, a


def generate_intext(
    *,
    author: str,
    year: str,
    page: str | None = None,
    style: str = "APA",
    quote: bool = False,
) -> dict[str, Any]:
    st = (style or "APA").strip().upper()
    yr = (year or "n.d.").strip()
    family, _ = _parse_author(author)
    pg = (page or "").strip()
    pg_apa = f", p. {pg}" if pg else ""
    pg_mla = f" {pg}" if pg else ""

    out: dict[str, Any] = {"style": st}

    if st == "APA":
        out["parenthetical"] = f"({family}, {yr}{pg_apa})"
        out["narrative"] = f"{family} ({yr}{pg_apa})"
        if quote and pg:
            out["direct_quote"] = f"({family}, {yr}, p. {pg})"
        else:
            out["direct_quote"] = out["parenthetical"]
    elif st == "HARVARD":
        out["parenthetical"] = f"({family}, {yr}{pg_apa})"
        out["narrative"] = f"{family} ({yr})"
        out["direct_quote"] = f"({family}, {yr}{pg_apa})"
    elif st == "MLA":
        out["parenthetical"] = f"({family}{pg_mla})"
        out["narrative"] = f"{family}{pg_mla}"
        out["direct_quote"] = f"({family}{pg_mla})"
    elif st == "CHICAGO":
        num = "1"
        fn = f"{family}, *Title*, ({yr})"
        if pg:
            fn += f", {pg}"
        fn += "."
        out["footnote"] = fn
        out["endnote"] = fn
        out["parenthetical"] = f"({family} {yr}{', ' + pg if pg else ''})"
        out["narrative"] = f"{family} ({yr})"
        out["direct_quote"] = out["footnote"]
    elif st == "IEEE":
        out["parenthetical"] = "[1]"
        out["narrative"] = f"{family} [1]"
        out["direct_quote"] = "[1]"
    elif st == "VANCOUVER":
        out["parenthetical"] = "(1)"
        out["narrative"] = f"{family} (1)"
        out["direct_quote"] = f"(1, p. {pg})" if pg else "(1)"
    else:
        return generate_intext(author=author, year=year, page=page, style="APA", quote=quote)

    out["footnote"] = out.get("footnote") or _default_footnote(family, yr, pg)
    out["endnote"] = out.get("endnote") or out["footnote"]
    return out


def _default_footnote(family: str, year: str, page: str | None) -> str:
    base = f"{family}, ({year})"
    if page:
        return f"{base}, p. {page}."
    return f"{base}."
