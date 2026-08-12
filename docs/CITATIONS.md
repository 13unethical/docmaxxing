# Formatter V2 — Citation styles (CSL)

Citation rendering uses [citeproc-py](https://github.com/brechtm/citeproc-py) and
vendored [Citation Style Language](https://citationstyles.org/) style files.

## Vendored CSL files

Location: `formatter_v2/citations/csl/`

| Our `StyleName` | Vendored file | Upstream id |
|---|---|---|
| `apa7` | `apa.csl` | `apa` (APA Style 7th edition) |
| `mla9` | `modern-language-association.csl` | `modern-language-association` (MLA Handbook 9th edition) |
| `chicago17` | `chicago-notes-bibliography-17th-edition.csl` | `chicago-notes-bibliography-17th-edition` |
| `ieee` | `ieee.csl` | `ieee` |
| `harvard` | `harvard-cite-them-right.csl` | `harvard-cite-them-right` (Cite Them Right 12th edition) |

Locale: `locales-en-US.xml`

### Name mismatches vs the brief

The brief asked for `chicago-note-bibliography`. That exact filename **does not
exist** in [citation-style-language/styles](https://github.com/citation-style-language/styles).
Closest matches upstream:

- `chicago-notes-bibliography.csl` — current default, **CMOS 18th** notes & bibliography
- `chicago-notes-bibliography-17th-edition.csl` — **CMOS 17th** notes & bibliography

We vendored **`chicago-notes-bibliography-17th-edition.csl`** because our product
style is `StyleName.CHICAGO17`.

All other requested names (`apa`, `modern-language-association`, `ieee`,
`harvard-cite-them-right`) matched upstream exactly.

## Source revisions

Pinned at vendor time (UTC dates from GitHub `master`):

| Repository | Commit | Date |
|---|---|---|
| `citation-style-language/styles` | `d17b5135c5b38f9ffadd0c3ec257f6892ba07f6e` | 2026-08-11 |
| `citation-style-language/locales` | `85588e7e9769549cf4167bf8eac338df30a6cf21` | 2026-08-07 |

Re-vendor by re-downloading the five `.csl` files and `locales-en-US.xml` from
those repositories and updating the commit SHAs in this document.

## Site footer attribution (CC BY-SA)

Use this line in the site footer (or About) when CSL styles are shipped:

> Citation styles © [Citation Style Language](https://citationstyles.org/)
> contributors, licensed under
> [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).

Short form:

> CSL styles: CC BY-SA 3.0 (citationstyles.org)
