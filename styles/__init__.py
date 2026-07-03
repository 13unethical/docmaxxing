"""
Formatting style registry — load profiles by id.

Adding a new academic style only requires a new module that exposes profile().
"""

from __future__ import annotations

from styles.profile import FormattingProfile

_PROFILE_LOADERS: dict[str, str] = {
    "harvard": "styles.harvard",
    "apa7": "styles.apa7",
    "apa": "styles.apa7",
    "mla9": "styles.mla9",
    "mla": "styles.mla9",
    "chicago17": "styles.chicago17",
    "chicago": "styles.chicago17",
    "ieee": "styles.ieee",
}

_ALIASES = {
    "harvard": "harvard",
    "apa": "apa7",
    "apa7": "apa7",
    "mla": "mla9",
    "mla9": "mla9",
    "chicago": "chicago17",
    "chicago17": "chicago17",
    "ieee": "ieee",
}


def normalize_style_id(raw: str | None) -> str:
    key = (raw or "harvard").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    if key in _ALIASES:
        return _ALIASES[key]
    if key.endswith("7") and key[:-1] in _ALIASES:
        return _ALIASES.get(key[:-1], key)
    return key if key in _PROFILE_LOADERS else "harvard"


def load_profile(style_id: str | None) -> FormattingProfile:
    """Return the formatting profile for a style id (falls back to Harvard)."""
    normalized = normalize_style_id(style_id)
    module_path = _PROFILE_LOADERS.get(normalized, "styles.harvard")
    import importlib

    module = importlib.import_module(module_path)
    return module.profile()


def list_profile_ids() -> list[str]:
    return sorted({normalize_style_id(k) for k in _PROFILE_LOADERS})
