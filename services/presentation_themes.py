"""Slide themes shared by the .pptx renderer and the in-browser preview.

A theme is a palette + fonts on top of a *design*: the composition of the cover, slide headers,
chrome and photo treatment. Designs are implemented in both presentation_generator.py and
static/presentation.{js,css}.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

CATEGORIES = (
    ("academic", "Academic"),
    ("work", "Work"),
    ("finance", "Finance"),
    ("promotion", "Promotion"),
    ("consulting", "Consulting"),
)

DESIGNS = ("classic", "magazine", "diagonal", "editorial", "fullbleed", "lineart")

# PowerPoint font name -> CSS stack used by the browser preview.
_WEB_FONTS = {
    "Georgia": 'Georgia, "Source Serif 4", serif',
    "Cambria": 'Cambria, Georgia, serif',
    "Garamond": 'Garamond, "EB Garamond", Georgia, serif',
    "Calibri": 'Calibri, "Segoe UI", "Helvetica Neue", Arial, sans-serif',
    "Arial": 'Arial, "Helvetica Neue", sans-serif',
    "Arial Black": '"Arial Black", "Arial Bold", Gadget, sans-serif',
    "Trebuchet MS": '"Trebuchet MS", "Segoe UI", sans-serif',
}

# Glyph width relative to the renderer's default heading estimate, and line height in em.
_FONT_WIDTH = {"Arial Black": 1.32}
_FONT_LINE = {"Arial Black": 1.42}


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    category: str
    sample_title: str
    # Content slides
    bg: str
    ink: str
    muted: str
    accent: str
    col_heading: str
    pale: str
    # Cover + closing slides
    cover_bg: str
    cover_ink: str
    cover_muted: str
    cover_accent: str
    heading_font: str
    body_font: str
    heading_upper: bool = False
    design: str = "classic"
    # Color part of the cover title in the accent: "lead" (first words), "tail" (last words) or "".
    title_accent: str = ""
    heading_bold: bool = True
    # File in static/presentation/samples/ shown on the gallery thumbnail.
    sample_image: str = ""

    @property
    def heading_width(self) -> float:
        return _FONT_WIDTH.get(self.heading_font, 1.0)

    @property
    def heading_line(self) -> float:
        return _FONT_LINE.get(self.heading_font, 1.2)

    def to_client(self) -> dict:
        data = asdict(self)
        data["web_heading_font"] = _WEB_FONTS.get(self.heading_font, "serif")
        data["web_body_font"] = _WEB_FONTS.get(self.body_font, "sans-serif")
        return data


THEMES: dict[str, Theme] = {
    t.id: t
    for t in (
        # --- Academic ---
        Theme(
            id="docmaxxing",
            name="DocMaxxing Blue",
            category="academic",
            sample_title="Renewable Energy in Central Asia",
            bg="FFFFFF",
            ink="0F172A",
            muted="475569",
            accent="2563EB",
            col_heading="1D4ED8",
            pale="EFF6FF",
            cover_bg="2563EB",
            cover_ink="FFFFFF",
            cover_muted="DBEAFE",
            cover_accent="93C5FD",
            heading_font="Georgia",
            body_font="Calibri",
            sample_image="mountains",
        ),
        Theme(
            id="paper",
            name="Paper White Courseware",
            category="academic",
            sample_title="Forest Ecosystems and Carbon Storage",
            bg="FFFFFF",
            ink="1F2937",
            muted="6B7280",
            accent="2F855A",
            col_heading="22543D",
            pale="EEF3EC",
            cover_bg="FFFFFF",
            cover_ink="1F2937",
            cover_muted="6B7280",
            cover_accent="2F855A",
            heading_font="Georgia",
            body_font="Calibri",
            design="lineart",
            heading_bold=False,
            sample_image="forest",
        ),
        Theme(
            id="blueline",
            name="Blue Line Courseware",
            category="academic",
            sample_title="Introduction to Research Methods",
            bg="FFFFFF",
            ink="0F172A",
            muted="64748B",
            accent="2563EB",
            col_heading="1E40AF",
            pale="EFF4FF",
            cover_bg="F8FAFF",
            cover_ink="0F172A",
            cover_muted="64748B",
            cover_accent="2563EB",
            heading_font="Trebuchet MS",
            body_font="Calibri",
            design="lineart",
            sample_image="lecture",
        ),
        Theme(
            id="teal",
            name="Teal Academic Defense",
            category="academic",
            sample_title="Remote Sensing of Wetland Change",
            bg="FFFFFF",
            ink="0F2A2E",
            muted="4B6366",
            accent="0F766E",
            col_heading="115E59",
            pale="E6F4F2",
            cover_bg="0F3D3A",
            cover_ink="F0FDFA",
            cover_muted="99F6E4",
            cover_accent="2DD4BF",
            heading_font="Cambria",
            body_font="Calibri",
            sample_image="lab",
        ),
        Theme(
            id="marine",
            name="Marine Blue Research",
            category="academic",
            sample_title="Coastal Bird Migration Patterns",
            bg="F5F9FC",
            ink="0B2239",
            muted="51677D",
            accent="0369A1",
            col_heading="075985",
            pale="E0EEF7",
            cover_bg="0B2239",
            cover_ink="FFFFFF",
            cover_muted="BAD7EA",
            cover_accent="38BDF8",
            heading_font="Georgia",
            body_font="Calibri",
            design="magazine",
            title_accent="tail",
            sample_image="coast",
        ),
        # --- Work ---
        Theme(
            id="sky",
            name="Deep Blue Atlas",
            category="work",
            sample_title="Mountain Tourism Development Plan",
            bg="FFFFFF",
            ink="0B2545",
            muted="4A6382",
            accent="1D4ED8",
            col_heading="1E3A8A",
            pale="E8F0FE",
            cover_bg="0B2545",
            cover_ink="FFFFFF",
            cover_muted="BFDBFE",
            cover_accent="60A5FA",
            heading_font="Arial Black",
            body_font="Calibri",
            heading_upper=True,
            design="magazine",
            title_accent="tail",
            sample_image="mountains",
        ),
        Theme(
            id="clay",
            name="Warm Clay Works",
            category="work",
            sample_title="Opening a Neighborhood Coffee Shop",
            bg="FAF5EF",
            ink="3B2A20",
            muted="7C6A5D",
            accent="C2410C",
            col_heading="9A3412",
            pale="F3E6DA",
            cover_bg="FAF5EF",
            cover_ink="3B2A20",
            cover_muted="7C6A5D",
            cover_accent="C2410C",
            heading_font="Georgia",
            body_font="Calibri",
            design="editorial",
            title_accent="lead",
            sample_image="cafe",
        ),
        Theme(
            id="rice",
            name="Rice Paper Annual",
            category="work",
            sample_title="Library Services Annual Review",
            bg="F7F3EA",
            ink="2A2722",
            muted="77705F",
            accent="8C6D3F",
            col_heading="6B5230",
            pale="EDE6D6",
            cover_bg="F7F3EA",
            cover_ink="2A2722",
            cover_muted="77705F",
            cover_accent="8C6D3F",
            heading_font="Georgia",
            body_font="Calibri",
            design="editorial",
            title_accent="tail",
            heading_bold=False,
            sample_image="library",
        ),
        # --- Finance ---
        Theme(
            id="midnight",
            name="Black Gold Ledger",
            category="finance",
            sample_title="Quarterly Investment Review",
            bg="0F172A",
            ink="F8FAFC",
            muted="94A3B8",
            accent="D4A657",
            col_heading="E9C77B",
            pale="1E293B",
            cover_bg="0B1120",
            cover_ink="F8FAFC",
            cover_muted="CBD5E1",
            cover_accent="D4A657",
            heading_font="Georgia",
            body_font="Calibri",
            design="diagonal",
            sample_image="skyline",
        ),
        Theme(
            id="ebony",
            name="Ebony Ledger",
            category="finance",
            sample_title="Manufacturing Capacity Outlook",
            bg="FFFFFF",
            ink="1C1917",
            muted="57534E",
            accent="B45309",
            col_heading="92400E",
            pale="F5F0EA",
            cover_bg="1C1917",
            cover_ink="FAFAF9",
            cover_muted="D6D3D1",
            cover_accent="D97706",
            heading_font="Arial Black",
            body_font="Arial",
            heading_upper=True,
            design="diagonal",
            title_accent="tail",
            sample_image="factory",
        ),
        Theme(
            id="jade",
            name="Warm Jade Annual Report",
            category="finance",
            sample_title="Sustainable Forestry Fund Report",
            bg="F7F5EE",
            ink="1E2A26",
            muted="5F6B66",
            accent="0F766E",
            col_heading="115E59",
            pale="E7EEE8",
            cover_bg="F7F5EE",
            cover_ink="1E2A26",
            cover_muted="5F6B66",
            cover_accent="0F766E",
            heading_font="Georgia",
            body_font="Calibri",
            design="editorial",
            title_accent="lead",
            sample_image="forest",
        ),
        Theme(
            id="wine",
            name="Wine Red Data",
            category="finance",
            sample_title="Urban Real Estate Market Brief",
            bg="FFFFFF",
            ink="2B1416",
            muted="6F5457",
            accent="9F1239",
            col_heading="881337",
            pale="FBEFF2",
            cover_bg="4C0519",
            cover_ink="FFF1F2",
            cover_muted="FECDD3",
            cover_accent="FB7185",
            heading_font="Georgia",
            body_font="Calibri",
            design="magazine",
            title_accent="tail",
            sample_image="skyline",
        ),
        # --- Promotion ---
        Theme(
            id="pitch",
            name="Red-Black Business",
            category="promotion",
            sample_title="Turn One Visit Into Four Seasons",
            bg="111111",
            ink="FFFFFF",
            muted="A3A3A3",
            accent="E11D48",
            col_heading="FB7185",
            pale="1F1F1F",
            cover_bg="111111",
            cover_ink="FFFFFF",
            cover_muted="D4D4D4",
            cover_accent="E11D48",
            heading_font="Arial Black",
            body_font="Arial",
            heading_upper=True,
            design="diagonal",
            title_accent="tail",
            sample_image="night",
        ),
        Theme(
            id="violet",
            name="Electric Night",
            category="promotion",
            sample_title="Urban Soundscape Trends 2026",
            bg="0E0B1F",
            ink="F5F3FF",
            muted="A5A0C8",
            accent="8B5CF6",
            col_heading="C4B5FD",
            pale="1C1736",
            cover_bg="2E1065",
            cover_ink="FFFFFF",
            cover_muted="DDD6FE",
            cover_accent="A78BFA",
            heading_font="Arial Black",
            body_font="Calibri",
            heading_upper=True,
            design="fullbleed",
            sample_image="night",
        ),
        Theme(
            id="silk",
            name="Silk Yellow Magazine",
            category="promotion",
            sample_title="Slow Mornings: A Café Lifestyle Guide",
            bg="FFFCF0",
            ink="1C1917",
            muted="6B6358",
            accent="CA8A04",
            col_heading="A16207",
            pale="FBF1CF",
            cover_bg="FDF6DA",
            cover_ink="1C1917",
            cover_muted="6B6358",
            cover_accent="CA8A04",
            heading_font="Georgia",
            body_font="Calibri",
            heading_upper=True,
            design="magazine",
            title_accent="tail",
            sample_image="cafe",
        ),
        Theme(
            id="moon",
            name="Moon White Imagery",
            category="promotion",
            sample_title="Alpine Winter Travel Collection",
            bg="FFFFFF",
            ink="111827",
            muted="6B7280",
            accent="111827",
            col_heading="111827",
            pale="F3F4F6",
            cover_bg="111827",
            cover_ink="FFFFFF",
            cover_muted="E5E7EB",
            cover_accent="FFFFFF",
            heading_font="Arial Black",
            body_font="Arial",
            heading_upper=True,
            design="fullbleed",
            sample_image="mountains",
        ),
        # --- Consulting ---
        Theme(
            id="honey",
            name="Honey Orange Memo",
            category="consulting",
            sample_title="Coastal Tourism Due Diligence Memo",
            bg="FFFBF2",
            ink="2B2118",
            muted="7A6650",
            accent="EA580C",
            col_heading="C2410C",
            pale="FDEBD3",
            cover_bg="FFFBF2",
            cover_ink="2B2118",
            cover_muted="7A6650",
            cover_accent="EA580C",
            heading_font="Georgia",
            body_font="Calibri",
            design="editorial",
            title_accent="tail",
            sample_image="coast",
        ),
        Theme(
            id="indigo",
            name="Indigo Due Diligence",
            category="consulting",
            sample_title="Laboratory Network Expansion Review",
            bg="FFFFFF",
            ink="1E1B4B",
            muted="5B5A7A",
            accent="4F46E5",
            col_heading="3730A3",
            pale="EEF0FF",
            cover_bg="1E1B4B",
            cover_ink="FFFFFF",
            cover_muted="C7D2FE",
            cover_accent="818CF8",
            heading_font="Trebuchet MS",
            body_font="Calibri",
            design="lineart",
            sample_image="lab",
        ),
        Theme(
            id="pine",
            name="Pine Green Strategy",
            category="consulting",
            sample_title="Five-Year Land Use Strategy",
            bg="0F1F1A",
            ink="ECFDF5",
            muted="9DB8AD",
            accent="34D399",
            col_heading="6EE7B7",
            pale="17302A",
            cover_bg="0B1A15",
            cover_ink="FFFFFF",
            cover_muted="D1FAE5",
            cover_accent="34D399",
            heading_font="Georgia",
            body_font="Calibri",
            design="fullbleed",
            sample_image="forest",
        ),
    )
}

DEFAULT_THEME = "docmaxxing"


def get_theme(theme_id: str | None) -> Theme:
    return THEMES.get(str(theme_id or "").strip().lower(), THEMES[DEFAULT_THEME])


def themes_for_client() -> list[dict]:
    return [t.to_client() for t in THEMES.values()]


def accent_split(text: str, mode: str) -> list[tuple[str, bool]]:
    """Split a title into (segment, is_accent) parts; mirrored by accentSplit() in presentation.js."""
    words = text.split()
    if mode not in ("lead", "tail") or len(words) < 2:
        return [(text, False)]
    k = min(3, max(1, len(words) // 3))
    if mode == "lead":
        return [(" ".join(words[:k]) + " ", True), (" ".join(words[k:]), False)]
    return [(" ".join(words[:-k]) + " ", False), (" ".join(words[-k:]), True)]
