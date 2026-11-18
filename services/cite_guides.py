"""Pilot programmatic pages: How to cite [source] in [style].

Only the top-10 source×style pairs from ``seo/keyword-map.csv`` are published.
Citation examples and formulas come from Formatter V2 CSL rendering
(``formatter_v2.citations``), not invented copy.
"""

from __future__ import annotations

import csv
import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from formatter_v2.citations.models import CSLItem
from formatter_v2.citations.renderer import (
    CSL_STYLE_FOR_STYLE_NAME,
    formatted_text_plain,
    render_bibliography,
    render_citation,
)
from formatter_v2.spec import StyleName
from services.seo import PublicPage, ROBOTS_NOINDEX, SITE_URL, canonical_url

REPO_ROOT = Path(__file__).resolve().parents[1]
KEYWORD_MAP_PATH = REPO_ROOT / "seo" / "keyword-map.csv"
PILOT_LIMIT = 10

STYLE_META: dict[str, dict[str, str]] = {
    "apa7": {
        "label": "APA 7",
        "api_style": "APA",
        "list_name": "References",
        "style_name": StyleName.APA7.value,
    },
    "mla9": {
        "label": "MLA 9",
        "api_style": "MLA",
        "list_name": "Works Cited",
        "style_name": StyleName.MLA9.value,
    },
    "harvard": {
        "label": "Harvard",
        "api_style": "Harvard",
        "list_name": "Reference list",
        "style_name": StyleName.HARVARD.value,
    },
    "chicago17": {
        "label": "Chicago 17",
        "api_style": "Chicago",
        "list_name": "Bibliography",
        "style_name": StyleName.CHICAGO17.value,
    },
    "ieee": {
        "label": "IEEE",
        "api_style": "IEEE",
        "list_name": "References",
        "style_name": StyleName.IEEE.value,
    },
}

SOURCE_META: dict[str, dict[str, str]] = {
    "website": {
        "label": "website",
        "label_title": "a website",
        "csl_type": "webpage",
        "form_mode": "url",
        "form_placeholder": "https://example.org/article",
        "form_hint": "Paste the page URL — we fetch metadata and format the reference.",
    },
    "youtube-video": {
        "label": "YouTube video",
        "label_title": "a YouTube video",
        "csl_type": "webpage",
        "form_mode": "url",
        "form_placeholder": "https://www.youtube.com/watch?v=…",
        "form_hint": "Paste the YouTube watch URL. We treat it as a webpage with YouTube as the container (CSL type webpage).",
    },
    "book": {
        "label": "book",
        "label_title": "a book",
        "csl_type": "book",
        "form_mode": "isbn",
        "form_placeholder": "9780143127550",
        "form_hint": "Enter an ISBN — we resolve it via Open Library and format the reference.",
    },
    "journal-article": {
        "label": "journal article",
        "label_title": "a journal article",
        "csl_type": "article-journal",
        "form_mode": "doi",
        "form_placeholder": "10.1038/nature14539",
        "form_hint": "Paste a DOI — we pull Crossref/doi.org CSL-JSON and format the reference.",
    },
}


def _item(data: dict[str, Any]) -> CSLItem:
    return CSLItem.model_validate(data)


def _plain_bib(item: CSLItem, style: StyleName) -> str:
    return formatted_text_plain(render_bibliography([item], style)[0])


def _plain_cite(item: CSLItem, style: StyleName) -> str:
    mode = "note" if style == StyleName.CHICAGO17 else "in_text"
    return formatted_text_plain(render_citation([item.id], style, mode, items=[item]))


def _style_enum(slug: str) -> StyleName:
    return StyleName(STYLE_META[slug]["style_name"])


# Pair-specific fixtures so pilot pages do not share the same sample strings.
# Keys: (source_slug, style_slug) → normal / no_author / no_date CSL-JSON dicts.
_FIXTURES: dict[tuple[str, str], dict[str, dict[str, Any]]] = {
    ("website", "apa7"): {
        "normal": {
            "id": "web-apa-n",
            "type": "webpage",
            "title": "Campus counseling wait times after midterms",
            "author": [{"family":"Reyes", "given": "Marisol"}],
            "issued": {"date-parts": [[2023, 4, 12]]},
            "container-title": "Student Health Brief",
            "URL": "https://example.org/counseling-wait-times",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_author": {
            "id": "web-apa-na",
            "type": "webpage",
            "title": "About peer mentoring hours",
            "issued": {"date-parts": [[2022, 9, 1]]},
            "container-title": "Wellness Commons",
            "URL": "https://example.org/peer-mentoring",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_date": {
            "id": "web-apa-nd",
            "type": "webpage",
            "title": "Quiet-hour study protocol",
            "author": [{"family": "Kim", "given": "Hana"}],
            "container-title": "Library Practice Desk",
            "URL": "https://example.org/quiet-hour-protocol",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
    },
    ("website", "mla9"): {
        "normal": {
            "id": "web-mla-n",
            "type": "webpage",
            "title": "Reading Zora Neale Hurston aloud in seminar",
            "author": [{"family": "Okafor", "given": "Ife"}],
            "issued": {"date-parts": [[2024, 2, 3]]},
            "container-title": "Seminar Notes Weekly",
            "URL": "https://example.org/hurston-aloud",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_author": {
            "id": "web-mla-na",
            "type": "webpage",
            "title": "Archive guide to Harlem Renaissance broadsides",
            "issued": {"date-parts": [[2021, 11, 18]]},
            "container-title": "Rare Book Annex",
            "URL": "https://example.org/harlem-broadsides",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_date": {
            "id": "web-mla-nd",
            "type": "webpage",
            "title": "Close-reading worksheet for sonnets",
            "author": [{"family": "Brennan", "given": "Casey"}],
            "container-title": "Poetry Lab",
            "URL": "https://example.org/sonnet-worksheet",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
    },
    ("website", "harvard"): {
        "normal": {
            "id": "web-harv-n",
            "type": "webpage",
            "title": "Module handbook notes on fieldwork ethics",
            "author": [{"family": "Singh", "given": "Priya"}],
            "issued": {"date-parts": [[2022, 10, 5]]},
            "container-title": "School of Geography Hub",
            "URL": "https://example.org/fieldwork-ethics",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_author": {
            "id": "web-harv-na",
            "type": "webpage",
            "title": "About placement risk assessments",
            "issued": {"date-parts": [[2023, 1, 9]]},
            "container-title": "Careers & Placements",
            "URL": "https://example.org/placement-risk",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_date": {
            "id": "web-harv-nd",
            "type": "webpage",
            "title": "Referencing mini-guide for coursework",
            "author": [{"family": "Hughes", "given": "Owen"}],
            "container-title": "Academic Skills Unit",
            "URL": "https://example.org/referencing-mini-guide",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
    },
    ("website", "chicago17"): {
        "normal": {
            "id": "web-chi-n",
            "type": "webpage",
            "title": "Digitised letters from the 1848 uprisings",
            "author": [{"family": "Moretti", "given": "Elena"}],
            "issued": {"date-parts": [[2020, 7, 21]]},
            "container-title": "European History Vault",
            "URL": "https://example.org/1848-letters",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_author": {
            "id": "web-chi-na",
            "type": "webpage",
            "title": "Finding aid for consular dispatches",
            "issued": {"date-parts": [[2019, 5, 14]]},
            "container-title": "Diplomatic Papers Online",
            "URL": "https://example.org/consular-dispatches",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_date": {
            "id": "web-chi-nd",
            "type": "webpage",
            "title": "Footnote habits in undergraduate theses",
            "author": [{"family": "Adler", "given": "Jonah"}],
            "container-title": "History Writing Center",
            "URL": "https://example.org/footnote-habits",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
    },
    ("youtube-video", "apa7"): {
        "normal": {
            "id": "yt-apa-n",
            "type": "webpage",
            "title": "Sleep stages explained for psych methods",
            "author": [{"literal": "Lab Bench Lectures"}],
            "issued": {"date-parts": [[2021, 6, 8]]},
            "container-title": "YouTube",
            "URL": "https://www.youtube.com/watch?v=sleepstages01",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_author": {
            "id": "yt-apa-na",
            "type": "webpage",
            "title": "Operant conditioning in two minutes",
            "issued": {"date-parts": [[2020, 1, 15]]},
            "container-title": "YouTube",
            "URL": "https://www.youtube.com/watch?v=operant02",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_date": {
            "id": "yt-apa-nd",
            "type": "webpage",
            "title": "Designing a simple reaction-time demo",
            "author": [{"literal": "Methods Minute"}],
            "container-title": "YouTube",
            "URL": "https://www.youtube.com/watch?v=rt-demo03",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
    },
    ("youtube-video", "mla9"): {
        "normal": {
            "id": "yt-mla-n",
            "type": "webpage",
            "title": "Staging Hamlet's closet scene on a budget",
            "author": [{"literal": "Scene Shop Talk"}],
            "issued": {"date-parts": [[2022, 3, 19]]},
            "container-title": "YouTube",
            "URL": "https://www.youtube.com/watch?v=hamlet-closet",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_author": {
            "id": "yt-mla-na",
            "type": "webpage",
            "title": "Costume research for Twelfth Night",
            "issued": {"date-parts": [[2019, 8, 2]]},
            "container-title": "YouTube",
            "URL": "https://www.youtube.com/watch?v=twelfth-costumes",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
        "no_date": {
            "id": "yt-mla-nd",
            "type": "webpage",
            "title": "Mic technique for verse speaking",
            "author": [{"literal": "Voice for Stage"}],
            "container-title": "YouTube",
            "URL": "https://www.youtube.com/watch?v=verse-mic",
            "accessed": {"date-parts": [[2026, 3, 1]]},
        },
    },
    ("book", "apa7"): {
        "normal": {
            "id": "book-apa-n",
            "type": "book",
            "title": "Measuring Stress in First-Year Cohorts",
            "author": [{"family": "Delgado", "given": "Rosa"}],
            "issued": {"date-parts": [[2019]]},
            "publisher": "Campus Press",
            "publisher-place": "Chicago",
        },
        "no_author": {
            "id": "book-apa-na",
            "type": "book",
            "title": "Handbook of Peer Support Programs",
            "issued": {"date-parts": [[2018]]},
            "publisher": "Student Affairs Press",
            "publisher-place": "Denver",
        },
        "no_date": {
            "id": "book-apa-nd",
            "type": "book",
            "title": "Draft Notes on Survey Bias",
            "author": [{"family": "Whitaker", "given": "Neil"}],
            "publisher": "Methods House",
            "publisher-place": "Austin",
        },
    },
    ("book", "mla9"): {
        "normal": {
            "id": "book-mla-n",
            "type": "book",
            "title": "Margins of the Lyric: Essays on Form",
            "author": [{"family": "Quan", "given": "Mei"}],
            "issued": {"date-parts": [[2017]]},
            "publisher": "Lantern Books",
            "publisher-place": "New York",
        },
        "no_author": {
            "id": "book-mla-na",
            "type": "book",
            "title": "Anthology of Campus Folklore",
            "issued": {"date-parts": [[2016]]},
            "publisher": "Quad Press",
            "publisher-place": "Ann Arbor",
        },
        "no_date": {
            "id": "book-mla-nd",
            "type": "book",
            "title": "Unfinished Commentary on Ghazals",
            "author": [{"family": "Farooq", "given": "Sami"}],
            "publisher": "Verse Imprint",
            "publisher-place": "Toronto",
        },
    },
    ("book", "harvard"): {
        "normal": {
            "id": "book-harv-n",
            "type": "book",
            "title": "Field Methods for Undergraduate Geographers",
            "author": [{"family": "Cartwright", "given": "Helen"}],
            "issued": {"date-parts": [[2020]]},
            "publisher": "Midlands Academic",
            "publisher-place": "Birmingham",
        },
        "no_author": {
            "id": "book-harv-na",
            "type": "book",
            "title": "Guide to Dissertation Risk Forms",
            "issued": {"date-parts": [[2018]]},
            "publisher": "Faculty Publishing",
            "publisher-place": "Manchester",
        },
        "no_date": {
            "id": "book-harv-nd",
            "type": "book",
            "title": "Working Draft on Rural Transport",
            "author": [{"family": "Bolton", "given": "Grace"}],
            "publisher": "Northern Pamphlets",
            "publisher-place": "Leeds",
        },
    },
    ("journal-article", "apa7"): {
        "normal": {
            "id": "jour-apa-n",
            "type": "article-journal",
            "title": "Sleep debt and exam performance in undergraduates",
            "author": [
                {"family": "Park", "given": "Sora"},
                {"family": "Ali", "given": "Yusuf"},
            ],
            "issued": {"date-parts": [[2020]]},
            "container-title": "Journal of Campus Research",
            "volume": "14",
            "issue": "2",
            "page": "101-118",
            "DOI": "10.1234/jcr.example.14",
        },
        "no_author": {
            "id": "jour-apa-na",
            "type": "article-journal",
            "title": "Editorial: Reproducibility checklists",
            "issued": {"date-parts": [[2021]]},
            "container-title": "Methods & Mentoring",
            "volume": "3",
            "issue": "1",
            "page": "1-4",
        },
        "no_date": {
            "id": "jour-apa-nd",
            "type": "article-journal",
            "title": "Pilot data on note-taking apps",
            "author": [{"family": "Novak", "given": "Tomas"}],
            "container-title": "Learning Tools Quarterly",
            "volume": "9",
            "issue": "3",
            "page": "55-70",
        },
    },
}

# Formulas mirror element order produced by our vendored CSL files for each type.
_FORMULAS: dict[tuple[str, str], str] = {
    ("website", "apa7"): "Author, A. A. (Year, Month Day). *Title of page*. Site Name. URL",
    ("website", "mla9"): 'Author Last, First. "Title of Page." *Website Name*, Day Month Year, URL.',
    ("website", "harvard"): "Author, A. (Year) Title of page, *Site Name*. Available at: URL (Accessed: Day Month Year).",
    ("website", "chicago17"): 'Author Last, First. "Title of Page." *Website Name*, Month Day, Year. URL.',
    ("website", "ieee"): 'A. Author, "Title of page," *Site Name*. Accessed: Mon. Day, Year. [Online]. Available: URL',
    ("youtube-video", "apa7"): "Author or Channel. (Year, Month Day). *Title of video* [Video]. YouTube. URL",
    ("youtube-video", "mla9"): 'Uploader Last, First / Channel. "Title of Video." *YouTube*, Day Month Year, URL.',
    ("youtube-video", "harvard"): "Author or Channel (Year) Title of video, *YouTube*. Available at: URL (Accessed: Day Month Year).",
    ("book", "apa7"): "Author, A. A. (Year). *Title of book*. Publisher.",
    ("book", "mla9"): "Author Last, First. *Title of Book*. Publisher, Year.",
    ("book", "harvard"): "Author, A. (Year) *Title of book*. Place: Publisher.",
    ("book", "chicago17"): "Author Last, First. *Title of Book*. Place: Publisher, Year.",
    ("journal-article", "apa7"): "Author, A. A., & Author, B. B. (Year). Title of article. *Journal Name*, *volume*(issue), pages. https://doi.org/xx",
    ("journal-article", "mla9"): 'Author Last, First, and First Last. "Title of Article." *Journal Name*, vol. #, no. #, Year, pp. xx–xx, https://doi.org/xx.',
    ("journal-article", "harvard"): "Author, A. and Author, B. (Year) 'Title of article', *Journal Name*, volume(issue), pp. pages. Available at: https://doi.org/xx.",
    ("journal-article", "ieee"): 'A. Author and B. Author, "Title of article," *Journal Name*, vol. #, no. #, pp. xx–xx, Year, doi: xx.',
}


@dataclass(frozen=True)
class CiteExample:
    label: str
    bibliography: str
    in_text: str


@dataclass(frozen=True)
class CiteGuide:
    style_slug: str
    source_slug: str
    keyword: str
    volume: int
    path: str
    title: str
    description: str
    h1: str
    lede: str
    intro: str
    formula: str
    formula_note: str
    examples: tuple[CiteExample, ...]
    in_text_note: str
    mistakes: tuple[tuple[str, str], ...]
    faq: tuple[tuple[str, str], ...]
    howto_steps: tuple[str, ...]
    related_articles: tuple[tuple[str, str], ...]
    form_mode: str
    form_placeholder: str
    form_hint: str
    api_style: str
    list_name: str
    csl_file: str
    neighbor_paths: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def slug(self) -> str:
        return f"{self.style_slug}-{self.source_slug}"

    @property
    def style_label(self) -> str:
        return STYLE_META[self.style_slug]["label"]

    @property
    def source_label(self) -> str:
        return SOURCE_META[self.source_slug]["label"]


# Hand-written, pair-specific copy — keep shared boilerplate minimal so overlap stays <30%.
_COPY: dict[tuple[str, str], dict[str, Any]] = {
    ("website", "apa7"): {
        "lede": "APA 7 treats a webpage like any other source: who wrote it, when it went up, what it is called, which site hosts it, and the URL.",
        "intro": (
            "Students usually land here after a brief says “APA 7th” and the only source on the desk is a "
            "news or NGO page. APA wants the personal author when one exists; if the byline is missing, the "
            "title moves into the author slot and the date stays in parentheses. Our formatter builds that "
            "string with the vendored ``apa.csl`` file — the examples below are live renders, not hand-typed fakes."
        ),
        "formula_note": (
            "Italics apply to the page title. Site name stays roman. When the date is missing, APA prints "
            "``(n.d.)`` and often adds a retrieval date before the URL — you can see that in the no-date example."
        ),
        "in_text_note": (
            "Parenthetical form is ``(Author, Year)``. Narrative form puts the year in parentheses after the "
            "name: Reyes (2023) argued… Use ``n.d.`` when the page has no date."
        ),
        "mistakes": (
            (
                "Citing the whole site instead of the page",
                "APA only needs a reference when you quote or paraphrase a specific page. A bare homepage mention can stay as a URL in the sentence.",
            ),
            (
                "Dropping the site name when it differs from the author",
                "If Reuters publishes a piece by Makini Brice, Brice is the author and Reuters is the site name — both belong in the reference.",
            ),
            (
                "Inventing a retrieval date on a stable page",
                "APA 7 drops “Retrieved from” for most stable URLs. Add a retrieval date mainly when content is designed to change (e.g. wiki-style pages) or when no publication date exists.",
            ),
        ),
        "faq": (
            (
                "Do I italicize the website name in APA 7?",
                "No. Italicize the webpage title. The site name stays in plain text before the URL.",
            ),
            (
                "What if the author is an organization?",
                "Use the organization as the author and skip repeating it as the site name when both strings are identical.",
            ),
            (
                "Can DocMaxxing format the rest of my paper too?",
                "Yes — the free essay formatter applies APA 7 margins, spacing, headings, and a References list layout.",
            ),
        ),
        "howto_steps": (
            "Collect author, full date, page title, site name, and URL from the page you used.",
            "Arrange them in the APA 7 webpage order shown in the formula.",
            "Add a matching parenthetical or narrative citation in the sentence that uses the source.",
            "Generate or paste the entry with the form below, then run the full document through the formatter.",
        ),
        "related_articles": (
            ("/blog/kak-procitirovat-chatgpt-apa-7", "How to cite ChatGPT in APA 7"),
            ("/formatter", "Essay formatter — APA 7 profile"),
        ),
    },
    ("youtube-video", "apa7"): {
        "lede": "APA 7 cites YouTube by channel (or personal uploader), upload date, italicized video title, the platform name, and the watch URL.",
        "intro": (
            "Video evidence shows up in psychology and communication papers more than instructors admit. APA "
            "does not invent a special “YouTube type” in our engine — we store the item as CSL ``webpage`` with "
            "``container-title`` set to YouTube, then let ``apa.csl`` print the bibliography line. That matches "
            "how doi.org and Crossref often ship streaming records into CSL-JSON."
        ),
        "formula_note": (
            "Official APA examples add ``[Video]`` after the title. Our CSL render may omit the bracket label "
            "unless the item carries a genre/medium field — keep the label if your brief quotes the Publication Manual examples."
        ),
        "in_text_note": (
            "Cite the channel or uploader and the year: ``(Lab Bench Lectures, 2021)``. For a direct quote, "
            "add a timestamp in place of a page number, e.g. (Lab Bench Lectures, 2021, 1:12)."
        ),
        "mistakes": (
            (
                "Using the video title as the author when a channel exists",
                "The channel or personal uploader is the author. The title stays italicized in the reference list.",
            ),
            (
                "Linking a youtu.be short link without checking the upload date",
                "Open the watch page, confirm the date under the description, and prefer the canonical youtube.com URL.",
            ),
            (
                "Treating a YouTube essay summary as a substitute for the paper",
                "Cite the video for what the speaker said; cite the journal or book for the underlying research claim.",
            ),
        ),
        "faq": (
            (
                "Who is the author of a YouTube video in APA?",
                "The person or channel that uploaded it. If only a screen name is visible, use that screen name as a literal author.",
            ),
            (
                "How do I cite a timestamp?",
                "Put minutes and seconds in the in-text citation after the year when you quote a specific moment.",
            ),
            (
                "Does the formatter accept YouTube URLs?",
                "Yes — paste the watch URL into the generator on this page or use the citation tools inside the workspace editor.",
            ),
        ),
        "howto_steps": (
            "Copy the channel name, upload date, exact video title, and watch URL.",
            "Build the APA reference with YouTube as the platform / container.",
            "Cite author and year in the sentence; add a timestamp for quotations.",
            "Paste the URL into the generator below to verify the formatted string.",
        ),
        "related_articles": (
            ("/blog/how-ai-detectors-work", "How AI detectors work"),
            ("/formatter", "Format the whole paper in APA 7"),
        ),
    },
    ("website", "mla9"): {
        "lede": "MLA 9 puts the page title in quotation marks, italicizes the website name, and usually ends with the URL — no “https://” required in many classroom styles, though our CSL keeps the scheme when present.",
        "intro": (
            "Literature and cultural-studies briefs still dominate MLA traffic. A webpage entry follows the "
            "core MLA template (author, title of source, title of container, publication date, location). "
            "Our renders use ``modern-language-association.csl``; in-text citations are author–title when the "
            "author is named, without a year."
        ),
        "formula_note": (
            "If the site has no author, start with the page title in quotation marks. MLA often wants an access "
            "date when the page lacks a publication date — see the no-date example from our renderer."
        ),
        "in_text_note": (
            "Typical parenthetical: ``(Okafor)``. When you cite multiple works by the same author, MLA adds a "
            "shortened title: ``(Okafor, “Reading Zora Neale Hurston”)``. Our renderer includes the title when that "
            "disambiguation path is active."
        ),
        "mistakes": (
            (
                "Adding a year like APA",
                "MLA in-text citations do not carry the year. Year belongs only in the Works Cited entry.",
            ),
            (
                "Italicizing the page title",
                "Webpage titles take quotation marks; the website / container title takes italics.",
            ),
            (
                "Forgetting the container",
                "“Reuters” or “National Resilience Hub” is the container. Skipping it makes the entry look like a standalone document.",
            ),
        ),
        "faq": (
            (
                "Should the URL include https://?",
                "MLA allows omitting the protocol. Our CSL output keeps the URL as stored on the item — either form is usually accepted if consistent.",
            ),
            (
                "Where do I put the access date?",
                "After the URL when the source has no date or your instructor requires it. Our no-date example shows the Accessed line.",
            ),
            (
                "Can I format an MLA paper here?",
                "Yes. The DocMaxxing formatter includes an MLA 9 profile for body text, headers, and Works Cited layout.",
            ),
        ),
        "howto_steps": (
            "Identify author, page title, website name, date, and URL.",
            "Fill the MLA container template (source title → container → date → location).",
            "Add an author (and shortened title if needed) parenthetical in the prose.",
            "Generate the Works Cited line with the form, then format the full document.",
        ),
        "related_articles": (
            ("/formatter", "MLA 9 essay formatter"),
            ("/blog/what-is-a-good-turnitin-ai-score", "What is a good Turnitin AI score?"),
        ),
    },
    ("book", "apa7"): {
        "lede": "APA 7 book references are short: author, year, italicized title, and publisher — no place of publication for most modern books.",
        "intro": (
            "Book chapters and whole books are still the backbone of theory sections. APA 7 dropped city of "
            "publication for standard books; our ``apa.csl`` output follows that. Use ISBN lookup in the form "
            "when you have a number; otherwise type the metadata manually in the workspace cite tools."
        ),
        "formula_note": (
            "Italicize the book title. Include edition in parentheses after the title when it is not the first "
            "(e.g. ``(2nd ed.)``). DOI belongs at the end when the book has one."
        ),
        "in_text_note": (
            "``(Delgado, 2019)`` or Delgado (2019). Add a page number for quotations: ``(Delgado, 2019, p. 44)``."
        ),
        "mistakes": (
            (
                "Keeping the city before the publisher",
                "APA 6 habits die hard. APA 7 usually omits London / New York before the publisher name.",
            ),
            (
                "Citing a chapter as if it were the whole book",
                "Edited volumes need the chapter author, chapter title, editors, book title, and page range.",
            ),
            (
                "Using the copyright page year when a newer DOI edition exists",
                "Prefer the edition you actually read. Mismatched years are a common marker check.",
            ),
        ),
        "faq": (
            (
                "Do ebooks need a URL?",
                "If the book has a DOI, use it. Platform URLs are optional when the book is widely available.",
            ),
            (
                "How do I cite a book with no author?",
                "Move the title into the author position and keep the year in parentheses — see the live example below.",
            ),
            (
                "Will the formatter hang-indent my References?",
                "Yes. The APA 7 profile sets hanging indents and double spacing on the reference list.",
            ),
        ),
        "howto_steps": (
            "Capture author names, year, full title, and publisher from the title page.",
            "Apply the APA book formula (no city in most cases).",
            "Cite author–date in the text; add pages for quotations.",
            "Resolve an ISBN in the generator or paste the finished entry into your draft.",
        ),
        "related_articles": (
            ("/formatter", "APA 7 book & paper formatting"),
            ("/blog/kak-procitirovat-chatgpt-apa-7", "Citing ChatGPT in APA 7"),
        ),
    },
    ("journal-article", "apa7"): {
        "lede": "APA 7 journal entries italicize the periodical name and volume, keep the issue in parentheses (roman), then pages and DOI as a URL.",
        "intro": (
            "This is the highest-stakes academic pair in the pilot: markers know the ampersand rules by heart. "
            "Two authors take ``&`` inside parentheses; three or more collapse to ``et al.`` from the first "
            "citation in APA 7. Our tests pin that behaviour on ``apa.csl`` — the bibliography line below is "
            "the same path the workspace citation inserter uses."
        ),
        "formula_note": (
            "Article title stays roman sentence case. Journal title and volume are italic. Issue number is "
            "roman in parentheses. Prefer ``https://doi.org/…`` over “Retrieved from”."
        ),
        "in_text_note": (
            "Two authors: ``(Park & Ali, 2020)``. Three or more: ``(Park et al., 2020)``. Narrative citations "
            "spell out “and” between two names."
        ),
        "mistakes": (
            (
                "Writing “and” inside parenthetical citations",
                "Parenthetical APA uses ``&``. Narrative citations use “and”. Mixing them is an easy deduction.",
            ),
            (
                "Italicizing the article title",
                "Only the journal name (and volume) are italic. The article title is plain sentence case.",
            ),
            (
                "Omitting the DOI when Crossref provides one",
                "Paste the DOI into the generator — our pipeline already speaks CSL-JSON from doi.org.",
            ),
        ),
        "faq": (
            (
                "Issue number or not?",
                "Include the issue when each issue restarts page numbering. APA 7 still allows the issue for clarity.",
            ),
            (
                "What if the article has no DOI?",
                "End after the page range, or add a stable journal URL if that is how you accessed it.",
            ),
            (
                "Can I insert the citation into a DOCX?",
                "Use the Cite panel in Workspace after searching Crossref, or generate here and paste.",
            ),
        ),
        "howto_steps": (
            "Collect authors, year, article title, journal, volume, issue, pages, and DOI.",
            "Order them with the APA journal formula (italic journal + volume).",
            "Place an author–date citation in the sentence that relies on the article.",
            "Paste the DOI into the form to regenerate and compare.",
        ),
        "related_articles": (
            ("/formatter", "Format journal papers in APA 7"),
            ("/blog/essay-flagged-as-ai-but-i-wrote-it", "Essay flagged as AI — what to do"),
        ),
    },
    ("youtube-video", "mla9"): {
        "lede": "MLA 9 treats a YouTube upload as a source inside the YouTube container: title in quotes, *YouTube* in italics, upload date, URL.",
        "intro": (
            "Film and media modules assign streaming clips constantly. MLA wants the uploader in the Author "
            "element when a person is credited; otherwise the title leads. We again map YouTube to CSL "
            "``webpage`` + container ``YouTube`` so ``modern-language-association.csl`` can build the Works "
            "Cited line without a fictional custom type."
        ),
        "formula_note": (
            "MLA handbooks sometimes write “uploaded by Channel Name” after the container. Our CSL may place "
            "the channel in the author position instead — both are recognizable; match your instructor’s sample."
        ),
        "in_text_note": (
            "Cite the uploader or a shortened title: ``(Scene Shop Talk)``. For a quotation, MLA allows a "
            "time range: ``(Scene Shop Talk 00:01:12-00:01:18)``."
        ),
        "mistakes": (
            (
                "Putting the year in the parenthetical",
                "MLA keeps dates in Works Cited only. In-text stays author or title.",
            ),
            (
                "Calling the platform “Google” or omitting YouTube",
                "YouTube is the container title. Without it, the entry looks incomplete.",
            ),
            (
                "Citing the auto-generated transcript URL instead of the watch page",
                "Use the public watch URL students can open without extra parameters.",
            ),
        ),
        "faq": (
            (
                "Is the channel italicized?",
                "No. Italicize *YouTube*. The video title uses quotation marks.",
            ),
            (
                "What if the uploader is “uploaded by” text only?",
                "MLA allows “uploaded by Name” after the container. Our renderer prefers Name as author when present in the CSL item.",
            ),
            (
                "Can I switch the same video to APA?",
                "Yes — see the neighboring APA YouTube guide in the pilot, or change the style in the generator.",
            ),
        ),
        "howto_steps": (
            "Note uploader/channel, video title, upload date, and watch URL.",
            "Build the MLA Works Cited entry with YouTube as container.",
            "Cite author or shortened title in the paragraph (optional timestamp).",
            "Paste the URL below to regenerate the MLA string.",
        ),
        "related_articles": (
            ("/formatter", "MLA 9 formatter"),
            ("/blog/free-gptzero-alternative", "Free GPTZero alternative"),
        ),
    },
    ("website", "chicago17"): {
        "lede": "Chicago 17 notes-bibliography puts webpage details into a footnote first; the bibliography mirrors the note with periods instead of commas.",
        "intro": (
            "History briefs still ask for footnotes. Our product style ``chicago17`` maps to "
            "``chicago-notes-bibliography-17th-edition.csl``, so the “in-text” example below is actually the "
            "note form the CSL emits — long, with title and URL — not an author–date parenthesis."
        ),
        "formula_note": (
            "Bibliography: Author. “Title.” *Site*. Date. URL. Notes use commas and parentheses around "
            "publication details. If no author exists, Chicago often leads with the site name."
        ),
        "in_text_note": (
            "Insert a superscript note number in the prose. The note content is what our renderer returns for "
            "Chicago — see the example under each bibliography line."
        ),
        "mistakes": (
            (
                "Using author–date parentheses for a notes paper",
                "Chicago has two systems. Our formatter profile follows notes-bibliography; do not mix in APA-style parentheses unless the brief asks for author–date.",
            ),
            (
                "Shortening the first note too aggressively",
                "The first citation should carry full details; later notes can shorten.",
            ),
            (
                "Omitting the access date on undated pages",
                "Chicago expects “Accessed Month Day, Year” when no publication date is listed.",
            ),
        ),
        "faq": (
            (
                "Notes or author–date?",
                "This guide follows notes-bibliography (CMOS 17) because that is the CSL file we ship. Confirm your syllabus.",
            ),
            (
                "Where does the URL go?",
                "At the end of the note and bibliography entry, after the date.",
            ),
            (
                "Can the formatter lay out Chicago papers?",
                "Yes — typography, spacing, and bibliography layout ship in the Chicago 17 profile.",
            ),
        ),
        "howto_steps": (
            "Gather author, page title, site, date, and URL.",
            "Write the full footnote using Chicago punctuation.",
            "Mirror it in the bibliography with periods.",
            "Generate via URL below, then format the manuscript.",
        ),
        "related_articles": (
            ("/formatter", "Chicago 17 formatter"),
            ("/blog/how-to-bypass-turnitin-ai-detection", "Turnitin AI detection — student guide"),
        ),
    },
    ("book", "mla9"): {
        "lede": "MLA 9 book entries italicize the title, place the publisher before the year, and drop the city.",
        "intro": (
            "Compared with APA, MLA swaps the year to the end and uses a period-heavy template. Page numbers "
            "belong in the parenthetical, not the Works Cited line for a whole book. Renders below come from "
            "``modern-language-association.csl`` with CSL type ``book``."
        ),
        "formula_note": (
            "Author. *Title*. Publisher, Year. For a contribution in an anthology, add the container book and "
            "page range — that is a different CSL type (``chapter``) in our engine."
        ),
        "in_text_note": (
            "``(Quan 44)`` for a quotation. No year in the parenthetical. Title disambiguation appears when "
            "one author has multiple works on the list."
        ),
        "mistakes": (
            (
                "Putting the year after the author like APA",
                "MLA keeps the year at the end of the Works Cited entry.",
            ),
            (
                "Adding publication city",
                "MLA 9 omits the city for most books published after 1900.",
            ),
            (
                "Italicizing chapter titles",
                "Chapter titles take quotation marks; book titles take italics.",
            ),
        ),
        "faq": (
            (
                "How do I cite an ebook?",
                "Add the database or platform as a container if that is how you accessed it; otherwise the standard book template is enough.",
            ),
            (
                "What about translators?",
                "Name the translator after the title (translated by Name) when relevant.",
            ),
            (
                "Does DocMaxxing support MLA page headers?",
                "Yes — surname + page number is part of the MLA 9 formatting profile.",
            ),
        ),
        "howto_steps": (
            "Take author, title, publisher, and year from the title page.",
            "Build the Works Cited line with publisher before year.",
            "Cite author and page in the text for quotations.",
            "Use ISBN lookup below when you have a number.",
        ),
        "related_articles": (
            ("/formatter", "MLA 9 book formatting"),
            ("/blog/does-turnitin-detect-chatgpt", "Does Turnitin detect ChatGPT?"),
        ),
    },
    ("website", "harvard"): {
        "lede": "Harvard (Cite Them Right) keeps author–date in the text and spells out “Available at” plus an access date for webpages.",
        "intro": (
            "UK and Commonwealth modules often name “Harvard” without shipping a single official manual — we "
            "standardise on ``harvard-cite-them-right.csl``. Expect “no date” instead of “n.d.” and an "
            "Accessed stamp on web sources."
        ),
        "formula_note": (
            "Author, A. (Year) Title, *Site*. Available at: URL (Accessed: Day Month Year). Titles are usually "
            "roman for webpages in CTR; journal and book titles stay italic."
        ),
        "in_text_note": (
            "``(Singh, 2022)`` or Singh (2022). Missing dates become ``(Hughes, no date)`` — matching the "
            "bibliography wording from our CSL."
        ),
        "mistakes": (
            (
                "Using APA’s n.d. spelling",
                "Cite Them Right prints “no date”. Mixing n.d. into a Harvard list looks inconsistent.",
            ),
            (
                "Skipping the access date",
                "Web references in CTR almost always carry (Accessed: …).",
            ),
            (
                "Assuming every UK tutor uses the same Harvard",
                "Faculty variants exist. Our output follows Cite Them Right; check the module handbook.",
            ),
        ),
        "faq": (
            (
                "Is Harvard the same as APA?",
                "Both are author–date, but punctuation, “no date”, and access-date rules differ. Do not paste APA strings into a Harvard list.",
            ),
            (
                "Do I need https:// in Available at?",
                "Yes — include the full URL as stored.",
            ),
            (
                "Can I format a Harvard paper on DocMaxxing?",
                "Yes. The Harvard profile follows a Cite Them Right-style layout for body text and the reference list.",
            ),
        ),
        "howto_steps": (
            "Capture author, year, page title, site, URL, and access date.",
            "Apply the Cite Them Right webpage formula.",
            "Add an author–date citation in the paragraph.",
            "Generate from URL below and compare with your handbook.",
        ),
        "related_articles": (
            ("/formatter", "Harvard / Cite Them Right formatter"),
            ("/blog/kak-procitirovat-chatgpt-apa-7", "Related: citing AI tools"),
        ),
    },
    ("book", "harvard"): {
        "lede": "Harvard books keep place and publisher, italicize the title, and use author–date citations — the classic CTR pattern.",
        "intro": (
            "Unlike APA 7, Cite Them Right still likes the place of publication (London: Harbor Press). That "
            "single difference trips students who bounce between US and UK style sheets. Our examples are "
            "rendered with ``harvard-cite-them-right.csl`` and CSL type ``book``."
        ),
        "formula_note": (
            "Author, A. (Year) *Title of book*. Place: Publisher. Edition appears after the title when needed "
            "(e.g. 2nd edn)."
        ),
        "in_text_note": (
            "``(Cartwright, 2020)``; quotations take a page: ``(Cartwright, 2020, p. 44)``. Four or more authors become "
            "et al. in CTR — our Harvard tests cover that threshold."
        ),
        "mistakes": (
            (
                "Dropping the place like APA 7",
                "Harvard/CTR still expects Place: Publisher for printed books.",
            ),
            (
                "Writing “edn” vs “ed.” inconsistently",
                "Pick the handbook’s abbreviation and stick to it across the list.",
            ),
            (
                "Alphabetizing by title when an editor should lead",
                "Edited books without a chapter focus still start with the editor name in many CTR examples.",
            ),
        ),
        "faq": (
            (
                "ISBN or manual entry?",
                "ISBN lookup is fastest when Open Library has the record; otherwise enter fields manually in the workspace.",
            ),
            (
                "E-book without a place?",
                "Use the place if stated; otherwise follow your handbook’s e-book pattern and keep the year accurate.",
            ),
            (
                "Does the formatter know Harvard hanging indents?",
                "Yes — the Harvard profile sets reference-list layout separately from APA/MLA.",
            ),
        ),
        "howto_steps": (
            "Read author, year, title, place, and publisher from the title page.",
            "Format with italics on the title and Place: Publisher.",
            "Cite author–date (and page for quotes) in the text.",
            "Resolve ISBN in the form to verify the rendered string.",
        ),
        "related_articles": (
            ("/formatter", "Harvard book & essay formatting"),
            ("/blog/turnitin-ai-score-asterisk", "Turnitin AI score asterisk explained"),
        ),
    },
}


def load_keyword_map() -> list[dict[str, str]]:
    with KEYWORD_MAP_PATH.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def top_pilot_rows(limit: int = PILOT_LIMIT) -> list[dict[str, str]]:
    rows = load_keyword_map()
    supported = [
        r
        for r in rows
        if r["source_slug"] in SOURCE_META and r["style_slug"] in STYLE_META
    ]
    supported.sort(key=lambda r: int(r["monthly_volume_us"]), reverse=True)
    return supported[:limit]


def _examples_for(source_slug: str, style_slug: str) -> tuple[CiteExample, ...]:
    style = _style_enum(style_slug)
    fixtures = _FIXTURES[(source_slug, style_slug)]
    labels = (
        ("Typical entry", "normal"),
        ("No author", "no_author"),
        ("No date", "no_date"),
    )
    out: list[CiteExample] = []
    for label, key in labels:
        item = _item(fixtures[key])
        out.append(
            CiteExample(
                label=label,
                bibliography=_plain_bib(item, style),
                in_text=_plain_cite(item, style),
            )
        )
    return tuple(out)


def _build_guide(row: dict[str, str], neighbors: Sequence[tuple[str, str]]) -> CiteGuide:
    style_slug = row["style_slug"]
    source_slug = row["source_slug"]
    copy = _COPY[(source_slug, style_slug)]
    style = STYLE_META[style_slug]
    source = SOURCE_META[source_slug]
    path = f"/cite/{style_slug}-{source_slug}"
    source_title = source["label_title"]
    style_label = style["label"]
    h1 = f"How to cite {source_title} in {style_label}"
    return CiteGuide(
        style_slug=style_slug,
        source_slug=source_slug,
        keyword=row["keyword"],
        volume=int(row["monthly_volume_us"]),
        path=path,
        title=f"{h1} — Examples & Generator | DocMaxxing",
        description=(
            f"Real {style_label} examples for {source_title}: formula, typical / no-author / no-date "
            f"references, in-text citation, common mistakes, and a live generator."
        ),
        h1=h1,
        lede=copy["lede"],
        intro=copy["intro"],
        formula=_FORMULAS[(source_slug, style_slug)],
        formula_note=copy["formula_note"],
        examples=_examples_for(source_slug, style_slug),
        in_text_note=copy["in_text_note"],
        mistakes=tuple(copy["mistakes"]),
        faq=tuple(copy["faq"]),
        howto_steps=tuple(copy["howto_steps"]),
        related_articles=tuple(copy["related_articles"]),
        form_mode=source["form_mode"],
        form_placeholder=source["form_placeholder"],
        form_hint=source["form_hint"],
        api_style=style["api_style"],
        list_name=style["list_name"],
        csl_file=CSL_STYLE_FOR_STYLE_NAME[_style_enum(style_slug)],
        neighbor_paths=tuple(neighbors),
    )


@functools.lru_cache(maxsize=1)
def pilot_guides() -> tuple[CiteGuide, ...]:
    rows = top_pilot_rows()
    by_source: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_source.setdefault(row["source_slug"], []).append(row)

    guides: list[CiteGuide] = []
    for row in rows:
        neighbors: list[tuple[str, str]] = []
        for other in by_source.get(row["source_slug"], []):
            if other["style_slug"] == row["style_slug"]:
                continue
            other_style = STYLE_META[other["style_slug"]]["label"]
            neighbors.append(
                (
                    f"/cite/{other['style_slug']}-{other['source_slug']}",
                    f"Same source in {other_style}",
                )
            )
        # Other styles exist in the product but are outside this 10-page pilot — no extra URLs.
        missing = [
            STYLE_META[s]["label"]
            for s in STYLE_META
            if s not in {r["style_slug"] for r in by_source[row["source_slug"]]}
        ]
        if missing:
            neighbors.append(
                (
                    "/formatter",
                    f"Also format in {', '.join(missing)} via the essay formatter",
                )
            )
        guides.append(_build_guide(row, neighbors))
    return tuple(guides)


@functools.lru_cache(maxsize=1)
def guides_by_path() -> dict[str, CiteGuide]:
    return {g.path: g for g in pilot_guides()}


def get_guide(style_slug: str, source_slug: str) -> CiteGuide | None:
    return guides_by_path().get(f"/cite/{style_slug}-{source_slug}")


def public_page_for(guide: CiteGuide) -> PublicPage:
    return PublicPage(
        path=guide.path,
        title=guide.title,
        description=guide.description,
        h1=guide.h1,
        lede=guide.lede,
        keywords=(guide.keyword, f"cite {guide.source_label}", guide.style_label, "citation generator"),
        breadcrumb=guide.h1,
        sources=("services/cite_guides.py", "templates/landing/cite_guide.html"),
        in_sitemap=False,  # pilot stays noindex until review
    )


def howto_json_ld(guide: CiteGuide) -> dict[str, Any]:
    return {
        "@type": "HowTo",
        "name": guide.h1,
        "description": guide.description,
        "url": canonical_url(guide.path),
        "inLanguage": "en",
        "step": [
            {"@type": "HowToStep", "position": i, "name": f"Step {i}", "text": step}
            for i, step in enumerate(guide.howto_steps, start=1)
        ],
        "tool": {
            "@type": "HowToTool",
            "name": "DocMaxxing citation generator",
            "url": f"{SITE_URL}{guide.path}",
        },
    }


def body_text_for_overlap(guide: CiteGuide) -> str:
    """Plain text used for pairwise overlap checks (excludes nav/footer)."""
    parts = [
        guide.h1,
        guide.lede,
        guide.intro,
        guide.formula,
        guide.formula_note,
        guide.in_text_note,
        guide.list_name,
        guide.csl_file,
    ]
    for ex in guide.examples:
        parts.extend([ex.label, ex.bibliography, ex.in_text])
    for title, body in guide.mistakes:
        parts.extend([title, body])
    for q, a in guide.faq:
        parts.extend([q, a])
    parts.extend(guide.howto_steps)
    for href, label in guide.related_articles:
        parts.extend([href, label])
    for href, label in guide.neighbor_paths:
        parts.extend([href, label])
    return "\n".join(parts)


def pairwise_overlap_report() -> dict[str, Any]:
    """Jaccard similarity on word sets; goal: each pair < 0.30."""
    guides = list(pilot_guides())
    tokenized = {
        g.path: set(body_text_for_overlap(g).lower().split()) for g in guides
    }
    pairs: list[dict[str, Any]] = []
    worst = 0.0
    for i, a in enumerate(guides):
        for b in guides[i + 1 :]:
            ta, tb = tokenized[a.path], tokenized[b.path]
            if not ta or not tb:
                score = 0.0
            else:
                score = len(ta & tb) / len(ta | tb)
            worst = max(worst, score)
            pairs.append(
                {
                    "a": a.path,
                    "b": b.path,
                    "jaccard": round(score, 4),
                    "overlap_pct": round(score * 100, 2),
                }
            )
    pairs.sort(key=lambda p: p["jaccard"], reverse=True)
    return {
        "pair_count": len(pairs),
        "worst_overlap_pct": round(worst * 100, 2),
        "passes_goal": worst < 0.30,
        "goal_pct": 30,
        "pairs": pairs,
    }
