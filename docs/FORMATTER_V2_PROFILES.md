# Formatter V2 Profiles — итоговые значения

Источник: `docs/FORMATTER_V2_STYLE_REFERENCE.md`.  
Файлы: `formatter_v2/profiles/{apa7,mla9,chicago17,ieee,harvard}.py`.

## Сводная матрица (как в референсе)

| | APA 7 | MLA 9 | Chicago 17 | IEEE | Harvard [H] |
|---|---|---|---|---|---|
| Интервал тела | 2.0 | 2.0 | 2.0 | 1.0 | 1.5 |
| Интервал заголовков | 2.0 | 2.0 | 2.0 | 1.0 | 1.5 |
| Интервал библиографии | 2.0 | 2.0 | **1.0 + space_after 12** | 1.0 | 1.5 |
| Выравнивание тела | left | left | left | justify | justify |
| Красная строка | 0.5 | 0.5 | 0.5 | 0.2 | нет (0) |
| Размер тела | 12 | 12 | 12 | **10** | 12 |
| Размер заголовков | **12 (все)** | 12 | 12 | 10 | 12–16 |
| Номера страниц | top_right | top_right | top_right | bottom_center | bottom_center |
| Титульник нумеруется | **да** (`skip_first_page=False`) | н/п | нет | нет | нет |
| Титульный лист | да | **нет** | да | нет | да |
| Заголовок списка | References | Works Cited | Bibliography | References | References |
| Заголовок списка bold | да | **нет** | да | upper≈small caps | да |
| Заголовок списка align | center | center | center | center | left |
| Сортировка | alphabetical | alphabetical | alphabetical | **ORDER_OF_APPEARANCE** | alphabetical |
| Нумерация списка | нет | нет | нет | **да** | нет |
| Hanging indent | 0.5 | 0.5 | 0.5 | **0.25** | 0.5 |
| Подпись таблицы | above | above | above | above | above |
| Подпись рисунка | **above** | below | below | below | below |
| et al. порог | 3 | 3 | 4 | n/a (numeric) | 4 |
| In-text | parenthetical | parenthetical | footnote | numeric | parenthetical |

## APA 7 — ключевые роли

| Роль | size | bold/italic | align | LS | indent |
|------|------|-------------|-------|-----|--------|
| DOC_TITLE / HEADING_1 | 12 | bold, title_case | center | 2.0 | — |
| HEADING_2 | 12 | bold, title_case | left | 2.0 | — |
| HEADING_3 | 12 | bold italic, title_case | left | 2.0 | — |
| HEADING_4 | 12 | bold, title_case | left | 2.0 | left 0.5 |
| BODY | 12 | — | left | 2.0 | first 0.5 |
| ABSTRACT | 12 | — | left | 2.0 | **no** first |
| REFERENCES_ENTRY | 12 | — | left | 2.0 | hanging 0.5 |
| Captions | table **above**, figure **above** | | | | |

## MLA 9

| Роль | notes |
|------|-------|
| DOC_TITLE | 12, **not bold**, center, LS 2.0 |
| REFERENCES_HEADING | Works Cited, **not bold**, center |
| cover_page.enabled | **False** |
| Captions | table above, figure **below** |

## Chicago 17

| Роль | notes |
|------|-------|
| BODY | LS 2.0, first 0.5 |
| BLOCK_QUOTE / FOOTNOTE | LS **1.0** |
| REFERENCES_ENTRY | LS **1.0**, space_after **12**, hanging 0.5 |
| heading_text | Bibliography |
| citations | FOOTNOTE, et_al 4 |

## IEEE

| Роль | notes |
|------|-------|
| Margins | 0.75 / 1.0 / **0.625** / **0.625** |
| BODY | 10pt, justify, first 0.2 |
| DOC_TITLE | 24pt, not bold |
| REFERENCES_ENTRY | 8pt, hanging **0.25**, ORDER_OF_APPEARANCE, numbered |
| page numbers | bottom_center |
| cover | disabled |

## Harvard (Cite Them Right) [H]

| Роль | notes |
|------|-------|
| BODY | justify, LS 1.5, space_after 12, **no** first-line |
| DOC_TITLE | 16 bold |
| HEADING_1 | 14 bold, 18/6 |
| REFERENCES_HEADING | 14 bold, **left** |
| REFERENCES_ENTRY | hanging 0.5, LS 1.5 |
| et_al | 4+ |
| display_name | «Harvard (Cite Them Right)» |

## Расхождения со старыми `styles/*.py` (V1)

Референс **побеждает**. Список для ревью — то, что в V1 профилях было иначе:

### APA (`styles/apa7.py` → референс)
1. DOC_TITLE / HEADING_1 size **16 → 12**
2. HEADING_2/3 size совпадал 12, но V1 title spacing after 24pt → референс **0/0**
3. COVER title font 16 → референс **12**
4. Figure caption position: V1 не задавал; референс **above** (не below)
5. `skip_first_page`: в V1 не было; референс **False**

### MLA (`styles/mla9.py` → референс)
1. HEADING_1/2/3 в V1: все 12 not-bold left → референс: H1 bold left, H2 italic left, H3 bold **center** [C]
2. REFERENCES_HEADING: V1 **bold left** → референс **not bold, center**
3. DOC_TITLE: V1 без bold — совпадает
4. Cover: V1 CoverPageSpec default существовал → референс **cover disabled**
5. Heading spacing 18/6 в V1 → референс **0/0**

### Chicago (`styles/chicago17.py` → референс)
1. BODY LS **1.5 → 2.0**
2. DOC_TITLE / HEADING_1 size **14 → 12**; HEADING_2 **13 → 12**
3. REFERENCES_ENTRY LS **1.5 → 1.0** + space_after **6 → 12**
4. Heading spacing academic 0/24, 18/6 → референс **0/0** для title/headings
5. Caption roles не было → заданы 1.0 spacing above/below

### IEEE (`styles/ieee.py` → референс)
1. DOC_TITLE: V1 **bold** → референс **не bold**
2. BODY first_line: V1 `None`/0 → референс **0.2**
3. HEADING spacing: V1 academic 18/6 etc. → референс **12/6, 6/3**
4. REFERENCES_ENTRY size **10 → 8**, hanging **0 → 0.25**
5. Page numbers: V1 `none` → референс **bottom_center** [C]
6. TABLE/FIGURE captions: не было → 8pt above/below
7. Sort: ранее в V2 черновике стоял alphabetical → референс **ORDER_OF_APPEARANCE**

### Harvard (`styles/harvard.py` → референс house)
1. HEADING_1 size V1 **16 → 14**; H3 V1 **14 italic → 12 bold italic**
2. BODY: V1 first_line none + justify 1.5 space_after 12 — **в целом совпадает** с house
3. REFERENCES_HEADING: V1 = heading 16 → референс **14 left**
4. REFERENCES_ENTRY hanging: V1 **0** (не задан) → house **0.5**
5. Page numbers: V1 none → house **bottom_center**
6. display_name: «Harvard» → «Harvard (Cite Them Right)»

### Общие V1 баги (не переносятся)
- Overlay `line_spacing=1.0` на все заголовки
- `margin_preset` поверх IEEE
- Hardcoded hanging 0.5 для всех стилей из FormatJob
- IEEE in-text литерал `"[1]"`

## Ограничения схемы (не значения референса)

- `TypographySpec` пока без `small_caps` — IEEE/APA multi-run caption styling помечены комментариями; для IEEE H1 используется `text_case=upper` как приближение [H].
- APA HEADING_4 «врезанный» абзац — ограничение V2.0 (отдельный run), отмечено в референсе.
