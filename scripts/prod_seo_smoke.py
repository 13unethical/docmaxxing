#!/usr/bin/env python3
"""Post-deploy SEO smoke: curl public URLs with Googlebot UA.

Checks status, self-canonical, hreflang set, and robots meta.
Exit 1 on any failure. Usage:

  python scripts/prod_seo_smoke.py
  python scripts/prod_seo_smoke.py --base https://docmaxxing.com
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass

UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
CURL = "curl"

# Marketing locales that must be SSR 200 with hreflang + self-canonical.
LOCALE_KEYS = ("", "ai-detector", "humanizer", "formatter", "pricing", "faq", "about")
LANGS = ("en", "ru", "uz")

# Must stay noindex and out of sitemap expectations (robots only here).
NOINDEX_PATHS = (
    "/account-info",
    "/login",
    "/register",
    "/terms",
    "/privacy",
    "/delivery-policy",
    "/refund-policy",
)

INDEX_KEEP = ("/about", "/faq", "/pricing", "/contact")


@dataclass
class Row:
    path: str
    status: str
    location: str
    canonical: str
    robots: str
    hreflang: str
    ok: bool
    note: str = ""


def _path_for(lang: str, key: str) -> str:
    if lang == "en":
        return "/" if key == "" else f"/{key}"
    if key == "":
        return f"/{lang}"
    return f"/{lang}/{key}"


def fetch(base: str, path: str) -> tuple[str, str, str]:
    """Return (status, location, html) without following redirects."""
    with tempfile.NamedTemporaryFile(delete=False) as body, tempfile.NamedTemporaryFile(
        "w+", delete=False
    ) as hdr:
        body_path, hdr_path = body.name, hdr.name
    try:
        proc = subprocess.run(
            [
                CURL,
                "-sS",
                "-A",
                UA,
                "-D",
                hdr_path,
                "-o",
                body_path,
                "-w",
                "%{http_code}",
                "--max-redirs",
                "0",
                f"{base}{path}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        status = (proc.stdout or "").strip() or "000"
        headers = open(hdr_path, encoding="utf-8", errors="ignore").read()
        html = open(body_path, encoding="utf-8", errors="ignore").read()
        location = ""
        for line in headers.splitlines():
            if line.lower().startswith("location:"):
                location = line.split(":", 1)[1].strip()
        return status, location, html
    finally:
        import os

        for p in (body_path, hdr_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def parse_meta(html: str) -> tuple[str, str, str]:
    canon_m = re.search(
        r'rel=["\']canonical["\'][^>]*href=["\']([^"\']+)|href=["\']([^"\']+)["\'][^>]*rel=["\']canonical',
        html,
        re.I,
    )
    canon = (canon_m.group(1) or canon_m.group(2)) if canon_m else ""
    robots_m = re.search(
        r'name=["\']robots["\'][^>]*content=["\']([^"\']+)|content=["\']([^"\']+)["\'][^>]*name=["\']robots',
        html,
        re.I,
    )
    robots = (robots_m.group(1) or robots_m.group(2)) if robots_m else ""
    hrefs = ",".join(dict.fromkeys(re.findall(r'hreflang=["\']([^"\']+)', html, re.I)))
    return canon, robots, hrefs


def check_locale(base: str, lang: str, key: str) -> Row:
    path = _path_for(lang, key)
    status, location, html = fetch(base, path)
    canon, robots, hrefs = parse_meta(html) if status.startswith("2") else ("", "", "")
    expected_canon = base if path == "/" else f"{base}{path}"
    need = {"en", "ru", "uz", "x-default"}
    have = set(hrefs.split(",")) if hrefs else set()
    ok = True
    notes: list[str] = []
    if status != "200":
        ok = False
        notes.append(f"want 200 got {status}")
    if location:
        ok = False
        notes.append(f"redirect {location}")
    if "/app#" in (location or "") or "/app#" in html[:500]:
        ok = False
        notes.append("app-hash")
    if canon != expected_canon:
        ok = False
        notes.append(f"canon want {expected_canon}")
    if "noindex" in robots.lower():
        ok = False
        notes.append(f"robots {robots}")
    if not need <= have:
        ok = False
        notes.append(f"hreflang missing {sorted(need - have)}")
    return Row(path, status, location, canon, robots, hrefs, ok, "; ".join(notes))


def check_noindex(base: str, path: str) -> Row:
    status, location, html = fetch(base, path)
    canon, robots, hrefs = parse_meta(html) if status.startswith("2") else ("", "", "")
    ok = status == "200" and "noindex" in robots.lower()
    note = "" if ok else f"want 200+noindex got {status}/{robots}"
    return Row(path, status, location, canon, robots, hrefs, ok, note)


def check_index_keep(base: str, path: str) -> Row:
    status, location, html = fetch(base, path)
    canon, robots, hrefs = parse_meta(html) if status.startswith("2") else ("", "", "")
    expected = f"{base}{path}"
    ok = status == "200" and "noindex" not in robots.lower() and canon == expected
    note = "" if ok else f"want index+self-canon got {status}/{robots}/{canon}"
    return Row(path, status, location, canon, robots, hrefs, ok, note)


def check_sitemap(base: str) -> list[str]:
    status, _, xml = fetch(base, "/sitemap.xml")
    if not status.startswith("2"):
        return [f"sitemap status {status}"]
    locs = set(re.findall(r"<loc>([^<]+)</loc>", xml))
    errors: list[str] = []
    for lang in LANGS:
        for key in LOCALE_KEYS:
            path = _path_for(lang, key)
            url = base if path == "/" else f"{base}{path}"
            if url not in locs and not (path == "/" and base.rstrip("/") in locs):
                # home may be SITE_URL without trailing slash
                if path == "/" and base.rstrip("/") in locs:
                    continue
                errors.append(f"sitemap missing {path}")
    for path in NOINDEX_PATHS:
        url = f"{base}{path}"
        if url in locs:
            errors.append(f"sitemap should omit {path}")
    for path in INDEX_KEEP:
        if f"{base}{path}" not in locs:
            errors.append(f"sitemap missing keep {path}")
    # pricing LD
    _, _, html = fetch(base, "/pricing")
    if '"@type": "Product"' in html or '"@type":"Product"' in html:
        errors.append("/pricing JSON-LD still has Product")
    if "SoftwareApplication" not in html:
        errors.append("/pricing missing SoftwareApplication")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="https://docmaxxing.com")
    ap.add_argument("--table", action="store_true", help="print markdown table")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    rows: list[Row] = []
    for lang in LANGS:
        for key in LOCALE_KEYS:
            rows.append(check_locale(base, lang, key))
    for path in NOINDEX_PATHS:
        rows.append(check_noindex(base, path))
    for path in INDEX_KEEP:
        if path not in {r.path for r in rows}:
            rows.append(check_index_keep(base, path))

    sitemap_errs = check_sitemap(base)

    if args.table or True:
        print("| URL | status | canonical | hreflang | robots | ok |")
        print("|---|---|---|---|---|---|")
        for r in rows:
            mark = "✓" if r.ok else f"✗ {r.note}"
            print(
                f"| `{r.path}` | {r.status}"
                f"{(' → ' + r.location) if r.location else ''} | `{r.canonical}` | `{r.hreflang}` | `{r.robots}` | {mark} |"
            )

    failed = [r for r in rows if not r.ok]
    for err in sitemap_errs:
        print(f"SITEMAP/LD: {err}", file=sys.stderr)
    if failed or sitemap_errs:
        print(f"FAIL: {len(failed)} URL checks, {len(sitemap_errs)} sitemap/ld", file=sys.stderr)
        return 1
    print("OK: all SEO smoke checks passed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
