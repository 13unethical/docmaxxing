"""Topic photos for slide decks: search (Pexels or Wikimedia Commons), download, cache."""

from __future__ import annotations

import hashlib
import io
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
_UA = "DocmaxxingSlides/1.0 (presentation builder; https://docmaxxing.com)"
_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
_PEXELS_API = "https://api.pexels.com/v1/search"
_MAX_EDGE_PX = 1600
_MIN_WIDTH_PX = 640
_SEARCH_TIMEOUT_S = 12
_DOWNLOAD_TIMEOUT_S = 20
_MAX_WORKERS = 6

IMAGE_ID_RE = re.compile(r"^[a-f0-9]{20}$")
# Filenames that are almost never good slide photos.
_COMMONS_SKIP_RE = re.compile(
    r"\b(logo|icon|map|diagram|chart|graph|flag|coat of arms|seal|signature|screenshot|"
    r"portrait|headshot|minister|president|ceo|award|ceremony|presenting|inaugurat\w*|felicitat\w*)\b",
    re.I,
)
_STOPWORDS = frozenset("a an and at for from in into of on or the to with using people".split())


def _stems(text: str) -> set[str]:
    """Crude stems (first 5 letters) so 'students' matches 'student' and 'teaching' matches 'teacher'."""
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {w[:5] for w in words if w not in _STOPWORDS}


def image_dir() -> Path:
    override = (os.environ.get("PRESENTATION_IMAGE_DIR") or "").strip()
    root = Path(override).expanduser() if override else _REPO_ROOT / "data" / "presentation_images"
    return root.resolve()


def image_path(image_id: str) -> Path | None:
    """Cached JPEG for an image id, or None if the id is malformed or missing."""
    if not IMAGE_ID_RE.match(str(image_id or "")):
        return None
    path = image_dir() / f"{image_id}.jpg"
    return path if path.is_file() else None


def image_url(image_id: str) -> str:
    return f"/api/presentation/image/{image_id}"


def _pexels_key() -> str:
    return (os.environ.get("PEXELS_API_KEY") or "").strip()


def _search_pexels(query: str, http: requests.Session) -> list[dict[str, str]]:
    response = http.get(
        _PEXELS_API,
        params={"query": query, "orientation": "landscape", "per_page": 6},
        headers={"Authorization": _pexels_key(), "User-Agent": _UA},
        timeout=_SEARCH_TIMEOUT_S,
    )
    response.raise_for_status()
    hits = []
    for photo in response.json().get("photos") or []:
        src = photo.get("src") or {}
        url = str(src.get("large2x") or src.get("large") or "").strip()
        if not url:
            continue
        hits.append(
            {
                "url": url,
                "credit": f"Photo: {photo.get('photographer') or 'Unknown'} / Pexels",
                "source": str(photo.get("url") or "https://www.pexels.com"),
            }
        )
    return hits


def _search_commons(query: str, http: requests.Session, subject: str | None = None) -> list[dict[str, str]]:
    """Commons photos for ``query``; titles must cover enough of ``subject`` (defaults to the query)."""
    response = http.get(
        _COMMONS_API,
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6,
            "gsrlimit": 12,
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "iiextmetadatafilter": "Artist|LicenseShortName",
            "iiurlwidth": _MAX_EDGE_PX,
        },
        headers={"User-Agent": _UA},
        timeout=_SEARCH_TIMEOUT_S,
    )
    response.raise_for_status()
    pages = sorted(
        ((response.json().get("query") or {}).get("pages") or {}).values(),
        key=lambda page: page.get("index", 0),
    )
    query_stems = _stems(subject or query)
    need = max(min(2, len(query_stems)), (len(query_stems) + 1) // 2)
    ranked: list[tuple[int, bool, dict[str, str]]] = []
    for page in pages:
        title = str(page.get("title") or "")
        info = (page.get("imageinfo") or [{}])[0]
        if str(info.get("mime") or "").lower() != "image/jpeg" or _COMMONS_SKIP_RE.search(title):
            continue
        # Commons search also matches long descriptions, which drags in unrelated photos;
        # require the file title itself to mention the subject.
        overlap = len(query_stems & _stems(re.sub(r"^File:|\.\w+$", "", title)))
        if overlap < need:
            continue
        width, height = int(info.get("width") or 0), int(info.get("height") or 0)
        url = str(info.get("thumburl") or info.get("url") or "").strip()
        if not url or width < _MIN_WIDTH_PX or not height:
            continue
        meta = info.get("extmetadata") or {}
        artist = re.sub(r"<[^>]+>", "", str((meta.get("Artist") or {}).get("value") or "")).strip()
        license_name = str((meta.get("LicenseShortName") or {}).get("value") or "").strip()
        credit = "Photo: " + (artist[:80] or "Wikimedia Commons")
        if license_name:
            credit += f" ({license_name})"
        hit = {
            "url": url,
            "credit": credit + " / Wikimedia Commons",
            "source": str(info.get("descriptionurl") or ""),
        }
        ranked.append((overlap, width / height >= 1.15, hit))
    ranked.sort(key=lambda item: (-item[0], not item[1]))
    return [hit for _overlap, _landscape, hit in ranked]


def search_images(
    query: str, *, subject: str | None = None, session: requests.Session | None = None
) -> list[dict[str, str]]:
    """Candidate photos for a query, best first. Network errors yield an empty list.

    ``subject`` is the full original query when ``query`` is a shortened retry; Commons hits
    are still judged against it so a retry like "coffee shop" cannot drop the actual subject.
    """
    http = session or requests.Session()
    for provider in ([_search_pexels] if _pexels_key() else []) + [_search_commons]:
        try:
            hits = provider(query, http) if provider is _search_pexels else provider(query, http, subject)
        except Exception:  # noqa: BLE001
            continue
        if hits:
            return hits
    return []


def _store(url: str, http: requests.Session) -> str | None:
    """Download, downscale to a JPEG, and cache; returns the image id."""
    from PIL import Image

    image_id = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
    if image_path(image_id):
        return image_id
    response = http.get(url, headers={"User-Agent": _UA}, timeout=_DOWNLOAD_TIMEOUT_S)
    response.raise_for_status()
    with Image.open(io.BytesIO(response.content)) as im:
        im = im.convert("RGB")
        im.thumbnail((_MAX_EDGE_PX, _MAX_EDGE_PX))
        folder = image_dir()
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f"{image_id}.part"
        im.save(tmp, format="JPEG", quality=85, optimize=True, progressive=True)
        tmp.replace(folder / f"{image_id}.jpg")
    return image_id


def fetch_image(query: str, *, exclude: set[str] | None = None, session: requests.Session | None = None) -> dict[str, str] | None:
    """Find and cache one photo for the query; returns {id, url, credit, source} or None."""
    query = re.sub(r"\s+", " ", str(query or "")).strip()[:120]
    if len(query) < 3:
        return None
    http = session or requests.Session()
    hits = search_images(query, session=http)
    words = [w for w in query.split() if w.lower() not in _STOPWORDS]
    for shorter in (words[:3], words[-2:]):
        if hits or len(shorter) >= len(words):
            continue
        hits = search_images(" ".join(shorter), subject=query, session=http)
    for hit in hits[:4]:
        if exclude and hit["url"] in exclude:
            continue
        try:
            image_id = _store(hit["url"], http)
        except Exception:  # noqa: BLE001
            continue
        if image_id:
            if exclude is not None:
                exclude.add(hit["url"])
            return {"id": image_id, "url": image_url(image_id), "credit": hit["credit"], "source": hit["source"]}
    return None


def attach_images(deck: dict[str, Any], *, layouts: tuple[str, ...]) -> int:
    """Fill ``image`` on the cover and on slides whose layout shows a photo. Returns the count found."""
    targets: list[tuple[dict[str, Any], str, str]] = []
    if deck.get("image_query"):
        targets.append((deck, "cover_image", deck["image_query"]))
    for slide in deck.get("slides") or []:
        if slide.get("layout") in layouts and slide.get("image_query"):
            targets.append((slide, "image", slide["image_query"]))
    if not targets:
        return 0

    used: set[str] = set()
    with requests.Session() as http, ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        # Searches run in parallel; `used` only de-duplicates best-effort across workers.
        results = list(pool.map(lambda t: fetch_image(t[2], exclude=used, session=http), targets))
    found = 0
    for (owner, key, _query), image in zip(targets, results):
        if image:
            owner[key] = image
            found += 1
    return found
