"""Formatter V2 style profiles registry."""

from __future__ import annotations

from formatter_v2.spec import StyleName, StyleProfile


def load_profile(name: StyleName | str) -> StyleProfile:
    key = StyleName(name) if not isinstance(name, StyleName) else name
    if key == StyleName.HARVARD:
        from formatter_v2.profiles.harvard import profile
    elif key == StyleName.APA7:
        from formatter_v2.profiles.apa7 import profile
    elif key == StyleName.MLA9:
        from formatter_v2.profiles.mla9 import profile
    elif key == StyleName.CHICAGO17:
        from formatter_v2.profiles.chicago17 import profile
    elif key == StyleName.IEEE:
        from formatter_v2.profiles.ieee import profile
    else:
        raise ValueError(f"No StyleProfile for {key!r}")
    return profile()


def all_profiles() -> dict[StyleName, StyleProfile]:
    return {
        StyleName.HARVARD: load_profile(StyleName.HARVARD),
        StyleName.APA7: load_profile(StyleName.APA7),
        StyleName.MLA9: load_profile(StyleName.MLA9),
        StyleName.CHICAGO17: load_profile(StyleName.CHICAGO17),
        StyleName.IEEE: load_profile(StyleName.IEEE),
    }


__all__ = ["all_profiles", "load_profile"]
