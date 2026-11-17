#!/usr/bin/env python3
"""Build WebP (+ JPEG fallback) marketing assets for public SEO pages.

Creates:
  static/brand/logo.webp
  static/media/*.webp (+ .jpg fallbacks) from existing product shots
  static/og/<slug>.webp for every PublicPage and blog post (1200×630)

Does not touch /app assets under static/app2 except reading shot-*.jpg as sources.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MEDIA = ROOT / "static" / "media"
OUT_OG = ROOT / "static" / "og"
OUT_BRAND = ROOT / "static" / "brand"
LOGO_PNG = OUT_BRAND / "logo.png"
OG_SIZE = (1200, 630)
BG = (11, 11, 15)
FG = (250, 250, 252)
MUTED = (161, 161, 170)
ACCENT = (99, 102, 241)

# Drop real captures in static/media/_sources/<stem>.png (or .jpg); else fall back to app2 shots.
_SOURCE_DIR = ROOT / "static" / "media" / "_sources"
SHOT_FALLBACKS = {
    "ai-detector-sentence-highlights": ROOT / "static/app2/media/shot-check.jpg",
    "ai-detector-overall-score": ROOT / "static/app2/media/shot-dashboard.jpg",
    "ai-humanizer-result-panel": ROOT / "static/app2/media/shot-humanize.jpg",
    "ai-humanizer-before-after": ROOT / "static/app2/media/shot-humanize.jpg",
    "essay-formatter-apa-preview": ROOT / "static/app2/media/shot-format.jpg",
    "essay-formatter-style-settings": ROOT / "static/app2/media/shot-format.jpg",
}


def _shot_source(stem: str) -> Path:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = _SOURCE_DIR / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return SHOT_FALLBACKS[stem]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        path = Path(name)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for word in words[1:]:
        trial = f"{cur} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines[:5]


def save_webp_and_jpg(im: Image.Image, dest_stem: Path, *, webp_quality: int = 82, jpg_quality: int = 85) -> None:
    dest_stem.parent.mkdir(parents=True, exist_ok=True)
    rgb = im.convert("RGB")
    rgb.save(dest_stem.with_suffix(".jpg"), "JPEG", quality=jpg_quality, optimize=True)
    rgb.save(dest_stem.with_suffix(".webp"), "WEBP", quality=webp_quality, method=6)


def convert_logo() -> None:
    im = Image.open(LOGO_PNG).convert("RGBA")
    # Flatten onto brand background for opaque webp/jpg, keep PNG as source of truth for icons.
    bg = Image.new("RGBA", im.size, (*BG, 255))
    flat = Image.alpha_composite(bg, im).convert("RGB")
    flat.save(OUT_BRAND / "logo.webp", "WEBP", quality=90, method=6)
    print("wrote", OUT_BRAND / "logo.webp", flat.size, (OUT_BRAND / "logo.webp").stat().st_size)


def convert_shots() -> None:
    _SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    for name in SHOT_FALLBACKS:
        src = _shot_source(name)
        im = Image.open(src).convert("RGB")
        # Cap long edge at 1400 for landing embeds.
        max_edge = 1400
        w, h = im.size
        scale = min(1.0, max_edge / max(w, h))
        if scale < 1:
            im = im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        save_webp_and_jpg(im, OUT_MEDIA / name)
        webp = OUT_MEDIA / f"{name}.webp"
        print("wrote", webp, "from", src.relative_to(ROOT), im.size, webp.stat().st_size)


def make_og(title: str, dest: Path, *, eyebrow: str = "DocMaxxing") -> None:
    im = Image.new("RGB", OG_SIZE, BG)
    draw = ImageDraw.Draw(im)
    # Accent bar
    draw.rectangle((0, 0, 12, OG_SIZE[1]), fill=ACCENT)
    logo = Image.open(LOGO_PNG).convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS)
    im.paste(logo, (64, 56), logo)
    eyebrow_font = _font(28)
    title_font = _font(54)
    draw.text((152, 72), eyebrow, font=eyebrow_font, fill=MUTED)
    lines = _wrap(draw, title, title_font, OG_SIZE[0] - 128)
    y = 200
    for line in lines:
        draw.text((64, y), line, font=title_font, fill=FG)
        y += 66
    draw.text((64, OG_SIZE[1] - 72), "docmaxxing.com", font=_font(24), fill=MUTED)
    save_webp_and_jpg(im, dest)
    print("og", dest.with_suffix(".webp").name, dest.with_suffix(".webp").stat().st_size)


def path_to_og_stem(path: str) -> str:
    if path == "/":
        return "home"
    clean = path.strip("/").replace("/", "-")
    return re.sub(r"[^a-z0-9\-]+", "-", clean.lower()).strip("-") or "page"


def generate_all_og() -> None:
    from services.blog import published_posts
    from services.seo import PUBLIC_PAGES

    OUT_OG.mkdir(parents=True, exist_ok=True)
    for path, page in sorted(PUBLIC_PAGES.items()):
        stem = path_to_og_stem(path)
        dest = OUT_OG / stem
        if dest.with_suffix(".webp").exists():
            continue
        title = page.h1 or page.title.split("|")[0].strip()
        make_og(title, dest)

    for post in published_posts():
        stem = path_to_og_stem(post.path)
        dest = OUT_OG / stem
        if dest.with_suffix(".webp").exists():
            continue
        make_og(post.title, dest, eyebrow="DocMaxxing Blog" if post.lang == "en" else "Блог DocMaxxing")


def main() -> None:
    convert_logo()
    convert_shots()
    generate_all_og()
    print("done")


if __name__ == "__main__":
    main()
