"""CSL-JSON subset used by Formatter V2."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CSLType = Literal[
    "article-journal",
    "book",
    "chapter",
    "webpage",
    "thesis",
    "report",
    "paper-conference",
]


class CSLName(BaseModel):
    """One personal or literal name in CSL-JSON."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    family: str | None = None
    given: str | None = None
    literal: str | None = None


class CSLDate(BaseModel):
    """CSL date object (``issued``, ``accessed``, …)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    date_parts: list[list[int]] | None = Field(default=None, alias="date-parts")
    literal: str | None = None
    raw: str | None = None


class TextFragment(BaseModel):
    """One run of styled text produced by the citation renderer."""

    model_config = ConfigDict(extra="forbid")

    text: str
    italic: bool = False
    bold: bool = False
    small_caps: bool = False


class CSLItem(BaseModel):
    """Subset of CSL-JSON needed for academic bibliographies.

    Extra keys from Crossref / doi.org / Open Library are ignored, not rejected.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    type: CSLType
    title: str | None = None
    container_title: str | None = Field(default=None, alias="container-title")
    author: list[CSLName] | None = None
    editor: list[CSLName] | None = None
    issued: CSLDate | None = None
    volume: str | None = None
    issue: str | None = None
    page: str | None = None
    publisher: str | None = None
    publisher_place: str | None = Field(default=None, alias="publisher-place")
    DOI: str | None = None
    URL: str | None = None
    accessed: CSLDate | None = None
    edition: str | None = None
    ISBN: str | None = None
    # Injected by our renderer when citeproc-py skips year-suffix disambiguation.
    year_suffix: str | None = Field(default=None, alias="year-suffix")
