# План удаления Formatter V1 (`formatter/`, `styles/`)

Снимок на 2026-08-12. Ничего не удалено — только инвентаризация потребителей.

**Уже на V2:** стадия Assignment (`services/assignment_formatting/`) — `FormatJob` / `format_document_full` там больше нет.

**Ещё на V1:** публичная страница `/` (`templates/index.html` + `static/common.js`) бьёт в `POST /api/format`. V2 UI (`/format-v2`) за флагом `FORMATTER_V2_ENABLED` и **не** заменяет этот путь.

`from citeproc import formatter` в `formatter_v2/citations/renderer.py` — чужой пакет, к V1 не относится.

---

## 1. Живые вызовы из продакшн-кода

### 1.1 Ядро вёрстки V1 — держит весь `formatter/` + `styles/`

Пока `/api/format` и `/api/preview-formatted` живы, удалять пайплайн нельзя.

| Место | Что вызывает |
|---|---|
| `app.py` | `parse_job` → `FormatJob`; `POST /api/format` → `reconstruct_document_before_format`, `format_document_full`, `prepend_cover_*`, `append_references_section`; `POST /api/preview-formatted` → `build_formatted_preview_html` |
| `static/common.js` | `fetch("/api/format")` — основной Format на проде |
| `static/preview.js` | `fetch("/api/preview-formatted")` |
| `templates/index.html` | UI этого пути |

Цепочка внутри пакета (только V1-вёрстка):

- `formatter/pipeline.py` (`format_document_full`)
- `formatter/format_job.py`
- `formatter/style_engine.py` → **`styles/`** (`load_profile`, `normalize_style_id`, профили harvard/apa7/mla9/chicago17/ieee)
- `formatter/paragraph_style.py`, `formatter/page_numbers.py`
- `formatter/document_reconstruction.py`, `formatter/heading_plan.py`, `formatter/structure_rebuild.py`
- `formatter/requirement_headings.py` (ещё `extract_format_section_labels` из `app.py`)
- `formatter/markdown_cleanup.py`, `formatter/cover_page.py`, `formatter/references_section.py`, `formatter/preview_html.py`

`styles/` снаружи `formatter/` в продакшне **никто не импортирует**. Пакет жив только как бэкенд V1 `style_engine`.

### 1.2 Утилиты в `formatter/`, которые **не** являются пайплайном вёрстки

Их нельзя выкинуть вместе с `FormatJob`: ими пользуются Check, Assignment (анализ брифа), Research, Turnitin, загрузка файлов.

| Модуль / символ | Кто зовёт |
|---|---|
| `formatter.document_io.extract_text_from_document_bytes` | `app.py` (`/api/extract-document` и соседние загрузки), `services/assignment_project/requirement_analyzer.py`, `services/research_engine/parsed_documents.py`, `services/turnitin_service/service.py` |
| `formatter.document_io.build_document_from_upload` / `build_document_from_inputs` / `is_supported_document_upload` | `app.py` (`/api/format` и extract) |
| `formatter.headings.COMMON_HEADINGS`, `REFS_HEADINGS`, `normalize_paragraph_text` | `services/document_checker.py`, `services/document_analyzer.py`, `services/check_metrics.py`, `services/check_validator.py` |

`formatter/text_cleaning.py` тянется из `document_io` и `requirement_headings` — тоже живой, пока живы эти утилиты.

### 1.3 Скрипты (не HTTP, но реальные вызовы V1)

| Скрипт | Зачем |
|---|---|
| `scripts/compare_v1_v2.py` | сравнивает `format_document_full` и `format_document_v2` |
| `scripts/pre_commit_five_doc_check.py` | гоняет V1 `FormatJob` + cover/refs/headings |

`scripts/audit_real_documents.py` уже на V2.

---

## 2. Вызовы только из тестов V1

Эти файлы импортируют `formatter` / `styles` и проверяют старый пайплайн. После переключения `/api/format` их либо переписывают на V2, либо удаляют пачкой с V1.

| Файл | Что покрывает |
|---|---|
| `tests/conftest.py` | хелпер `format_document_full` + reconstruction — общий для V1-тестов |
| `tests/test_heading_format.py` | `FormatJob` + `format_document_full` |
| `tests/test_heading_spacing.py` | `FormatJob`, `styles.profile`, `formatter.heading_spacing` |
| `tests/test_style_engine.py` | `FormatJob`, `styles.load_profile`, `format_document_full` |
| `tests/test_structural_headings.py` | reconstruction + `format_document_full` |
| `tests/test_document_reconstruction.py` | reconstruction + `FormatJob` |
| `tests/test_heading_detector.py` | `reconstruct_blocks` / `reconstruct_document_before_format` |
| `tests/test_requirement_headings.py` | `requirement_headings` + `FormatJob` |
| `tests/test_markdown_and_title_fixes.py` | markdown_cleanup, preview_html, `FormatJob` |
| `tests/test_cover_page.py` | `formatter.cover_page` |
| `tests/test_ai_heading_plan.py` | heading_plan, structure_rebuild, `format_document_full` |
| `tests/test_ai_structure_recovery.py` | structure_rebuild + `format_document_full` |
| `tests/test_structure_regression_cases.py` | reconstruction + `format_document_full` |

Тесты `tests/test_*v2.py`, `test_routes_v2.py`, `test_chat_edit.py`, `test_assignment_formatting_v2.py` к V1 не относятся.

`tests/test_assignment_spec.py` больше не импортирует `FormatJob` (только `_docx_from_markdown` / `_overrides_from_requirement`).

---

## 3. Мёртвые импорты и модули

Не «неиспользуемый import в файле», а **код V1, на который нет продакшн-потребителя**.

| Что | Почему мертво |
|---|---|
| `formatter/layout.py` (`apply_margin_preset`) | ни один модуль не импортирует. Поля в V1 идут через `style_engine._apply_margin_preset` |
| `formatter/heading_spacing.py` | не импортируется пайплайном. Прод использует `style_engine.resolve_contextual_spacing`. Единственный внешний импорт — `tests/test_heading_spacing.py` |

В `app.py` все импорты из `formatter` используются маршрутами `/api/format` и `/api/preview-formatted` — мёртвых импортов там нет.

`styles/` не мёртв, пока жив §1.1.

---

## 4. Что можно удалить сразу / после флага / отдельной работой

### Можно удалить сразу (не ломает прод)

- `formatter/layout.py`
- `formatter/heading_spacing.py` **вместе с** тестами, которые на него завязаны (`test_heading_spacing.py` частично — функции `resolve_paragraph_spacing`; интеграционные тесты через `format_document_full` трогать рано)

Это косметика. На объём V1 почти не влияет.

### Нельзя удалять, пока `/api/format` — дефолт для `/`

Переключение флага `FORMATTER_V2_ENABLED` **само по себе ничего не отключает**: флаг открывает `/format-v2`, старый `/api/format` продолжает обслуживать главную страницу.

Чтобы снять §1.1, нужна **отдельная работа по маршруту**, не только флаг:

1. Перевести `POST /api/format` и `POST /api/preview-formatted` (и `static/common.js` / `preview.js`) на `format_document_v2`, либо сделать `/` = `/format-v2` и выключить старые эндпоинты.
2. После этого удалить пакетом:
   - `formatter/pipeline.py`, `format_job.py`, `style_engine.py`, `paragraph_style.py`, `page_numbers.py`
   - `formatter/preview_html.py`, `cover_page.py`, `references_section.py`
   - `formatter/document_reconstruction.py`, `heading_plan.py`, `structure_rebuild.py`, `markdown_cleanup.py`
   - весь пакет `styles/`
   - V1-тесты из §2 и скрипты `compare_v1_v2.py`, `pre_commit_five_doc_check.py` (или переписать на V2)

### Требует отдельной работы (не удалять с пайплайном)

Вынести из `formatter/` в нейтральное место (`services/document_io.py`, `services/heading_labels.py` и т.п.), иначе Check / Assignment analyzer / Research / Turnitin сломаются:

- `formatter/document_io.py` (+ зависимость `text_cleaning.py`)
- константы и `normalize_paragraph_text` из `formatter/headings.py` (Check)

`requirement_headings.extract_format_section_labels` сегодня нужен `/api/format`; после перевода формата на V2 — либо встроить в V2 structure, либо оставить как утилиту брифа.

Cover page и список литературы на V1 вшиты в `/api/format` (`prepend_cover_*`, `append_references_section`). В V2 это уже `CoverPage` / citations в `formatter_v2`. Перенос UI главной страницы должен явно закрыть эти два шага, иначе пользователи `/` потеряют титул и блок ссылок.

---

## 5. Рекомендуемый порядок

1. Удалить только `layout.py` (и по желанию `heading_spacing.py`) — нулевой риск для прода.
2. Переключить главную Format-страницу на V2 (это и есть «флаг» в смысле продукта, не текущий `FORMATTER_V2_ENABLED`).
3. Вынести `document_io` + heading-константы из пакета `formatter/`.
4. Удалить остаток `formatter/` (кроме вынесенного) и весь `styles/`, плюс тесты §2.
