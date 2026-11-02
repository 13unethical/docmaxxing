"""Render static/og/*.png (1200x630 Open Graph cards) and static/favicon.ico.

Run from the repo root: python3 scripts/make_og_images.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
SIZE = (1200, 630)
BG = (11, 11, 15)
SURFACE = (23, 23, 28)
TEXT = (247, 247, 248)
MUTED = (161, 161, 170)
ACCENT = (47, 111, 228)

_BOLD_FONTS = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
_REGULAR_FONTS = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

CARDS = {
    "default.png": ("DocMaxxing", "AI humanizer and writing tools for students", "Humanizer · Formatter · AI check · Slides"),
    "humanizer.png": ("Free AI Humanizer", "Turn AI text into natural writing", "Paste a draft · Get readable text in seconds"),
}


def _font(candidates: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise SystemExit(f"No font found among {candidates}")


def _card(title: str, subtitle: str, footer: str) -> Image.Image:
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((40, 40, SIZE[0] - 40, SIZE[1] - 40), radius=36, fill=SURFACE)
    draw.rectangle((40, 40, 56, SIZE[1] - 40), fill=ACCENT)

    logo = Image.open(STATIC / "icon.png").convert("RGBA").resize((96, 96))
    img.paste(logo, (100, 100), logo)
    draw.text((216, 120), "DocMaxxing", font=_font(_BOLD_FONTS, 44), fill=TEXT)

    draw.text((100, 260), title, font=_font(_BOLD_FONTS, 88), fill=TEXT)
    draw.text((100, 375), subtitle, font=_font(_REGULAR_FONTS, 44), fill=MUTED)
    draw.text((100, 500), footer, font=_font(_REGULAR_FONTS, 32), fill=MUTED)
    draw.text((SIZE[0] - 100, 500), "docmaxxing.com", font=_font(_BOLD_FONTS, 32), fill=ACCENT, anchor="ra")
    return img


def main() -> None:
    out_dir = STATIC / "og"
    out_dir.mkdir(exist_ok=True)
    for name, (title, subtitle, footer) in CARDS.items():
        _card(title, subtitle, footer).save(out_dir / name, optimize=True)
    icon = Image.open(STATIC / "icon.png").convert("RGBA")
    icon.save(STATIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])


if __name__ == "__main__":
    main()
