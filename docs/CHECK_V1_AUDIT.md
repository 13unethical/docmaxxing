# Аудит Academic Check (V1)

**Дата:** 2026-08-17  
**Режим:** только чтение кодовой базы, без изменений.  
**Цель:** зафиксировать текущую реализацию `/check` и `/api/check-document` перед новой версией.

---

## 1. Карта файлов и зависимостей

### 1.1. HTTP-слой

| Компонент | Файл | Строки | Назначение |
|-----------|------|--------|------------|
| Страница UI (заблокирована) | `app.py` → `check()` | 1805–1812 | `GET /check` отдаёт `soon.html`, **не** `check.html` |
| API проверки | `app.py` → `api_check_document()` | 5679–5755 | `POST /api/check-document`, без логина, бесплатно (комментарий 5739) |
| Парсинг брифа для Check UI | `app.py` → `api_extract_requirements()` | 5467–5509 | `POST /api/extract-requirements` (multipart) |
| Парсинг брифа (JSON, Home) | `app.py` → `parse_requirements_view()` | 5391–5411 | `POST /parse-requirements` — **не** вызывается из `check.js` |
| Извлечение текста документа | `app.py` | 5648–5676 | `POST /api/extract-document` — через `FormatterCommon.bindDocumentUploadExtract` |
| Structure recovery (отдельный API) | `app.py` → `api_structure_recovery()` | 5758–5818 | `POST /api/structure-recovery` — **не** вызывается из `check.js`; structure приходит внутри check |

### 1.2. Оркестрация проверки

| Модуль | Роль |
|--------|------|
| `services/document_checker.py` → `check_document()` | 1189–1307 | Точка входа: параграфы, structure recovery, pipeline, сбор ответа |
| `services/check_pipeline.py` → `run_check_pipeline()` | 23–79 | requirements → metrics → validation → score → explanation |
| `services/check_requirements.py` | — | Нормализация брифа в `StructuredRequirements` |
| `services/check_metrics.py` | — | Извлечение метрик документа (детерминированно) |
| `services/check_validator.py` | — | Сравнение требований с метриками |
| `services/check_scoring.py` | — | Взвешенный score, categories, action plan, issues |
| `services/check_explanation.py` | — | Текстовое объяснение (Gemini или локальный fallback) |

### 1.3. Structure recovery (внутри check)

| Модуль | Роль |
|--------|------|
| `services/document_checker.py` → `analyze_structure_recovery()` | 498–659 | Health score структуры, missing sections, paragraph/heading issues |
| `services/document_structure_engine.py` → `recover_structure()` | 1247+ | Сохранение или восстановление дерева секций |
| `services/ai_structure_recovery.py` | — | Gemini multi-phase, если заголовков нет |

### 1.4. Парсинг требований

| Модуль | Роль |
|--------|------|
| `services/requirements_parser.py` → `parse_requirements()` | 160–216 | LLM (Gemini) + fallback `_strict_requirements_from_text` |
| `services/document_checker.py` → `parse_requirements_for_check()` | 286–389 | Локальные regex/heuristics (используется в `normalize_requirements`) |

### 1.5. Legacy / вспомогательные

| Модуль | Роль |
|--------|------|
| `services/document_analyzer.py` → `analyze_document()` | 141–380 | Старые rule-based checks; вызывается из `check_metrics` как `legacy_issues` |
| `services/document_checker.py` → `_run_content_checks()` | 752–1186 | **Мёртвый код** — не вызывается из `check_document` |
| `services/document_checker.py` → `_gemini_insights()` | 114–211 | **Мёртвый код** — не вызывается |

### 1.6. UI

| Файл | Статус |
|------|--------|
| `templates/check.html` | Полный UI существует, но **нигде не рендерится** (см. §6) |
| `static/check.js` | Клиент: extract requirements → check-document → отрисовка |
| `templates/soon.html` | То, что реально видит пользователь на `/check` |

### 1.7. Тесты

| Файл | Покрытие |
|------|----------|
| `tests/test_check_pipeline.py` | Pipeline, scoring, `check_document` end-to-end |
| `tests/test_ai_structure_recovery*.py` | AI structure recovery (косвенно для Check) |
| `tests/test_structure_recovery_engine.py` | Engine structure (косвенно) |
| `tests/test_recover_structure_ai_failure.py` | Ошибки AI recovery |

**НЕ НАЙДЕНО:** интеграционных тестов HTTP `POST /api/check-document` или E2E `check.js`.

---

## 2. Поток выполнения (как работает сейчас)

```
check.js
  ├─ (optional) POST /api/extract-requirements  → parse_requirements() [LLM]
  └─ POST /api/check-document
       └─ check_document()
            ├─ analyze_structure_recovery()  [deterministic + optional LLM]
            └─ run_check_pipeline()
                 ├─ normalize_requirements()   [heuristics + optional parsed_payload]
                 ├─ extract_document_metrics() [deterministic]
                 ├─ validate_all_requirements() [deterministic]
                 ├─ compute_readiness_score()  [formula]
                 └─ explain_check_results()    [optional LLM, не меняет score]
```

---

## 3. Проверки: что, как, где, что возвращается

### 3.1. Активный pipeline (`check_validator.validate_all_requirements`)

Все проверки **детерминированные**. Каждая возвращает объект validation с полями:  
`id`, `label`, `weight`, `required`, `detected`, `completion` (0–1), `completion_pct`, `status` (`PASS`/`FAIL`/`PARTIAL`/`NEEDS_CONFIRMATION`/`SKIP`), `priority`, `confidence`, `category`, `details`, `fix`, `points_earned`, `points_possible`.

| ID | Что проверяется | Метод | Вес | Файл:строки | В UI |
|----|-----------------|-------|-----|-------------|------|
| `word_count` | Лимит слов min/max из брифа vs `metrics.word_count` | Пропорция: ниже min → `wc/min`; выше max → штраф | 25 | `check_validator.py:118–154` | Compliance tab, issue cards |
| `word_count` (ambiguous) | Бриф с низкой уверенностью в word count | `NEEDS_CONFIRMATION`, completion=1.0 | 25 | `check_validator.py:139–154` | Compliance (badge «NEEDS_CONFIRMATION») |
| `sections` | Обязательные секции vs `metrics.detected_sections` | `present/total` | 20 | `check_validator.py:156–184` | Compliance + checklist в details |
| `references` | Число peer-reviewed refs / наличие секции | `min(1, detected/target)` | 15 | `check_validator.py:186–212` | Citation tab, Compliance |
| `in_text_citations` | Стиль цитирования + in-text count + APA refs format | Ratio in-text; для APA усреднение с `apa_reference_format_ok` | 15 | `check_validator.py:214–248` | Citation tab, Compliance |
| `formatting` | Font, size, line spacing, page numbers (только .docx) | Доля совпадений among checked items; без docx → `NEEDS_CONFIRMATION` 50% | 10 | `check_validator.py:250–304` | Compliance |
| `grammar` | «Grammar signals»: double spaces, много коротких абзацев | `1 - signals*0.15` | 10 | `check_validator.py:306–321` | Compliance |
| `academic_style` | Headings + body paragraphs | `(headings/3)*0.5 + (body/5)*0.5` | 5 | `check_validator.py:323–339` | Compliance |
| `body_paragraphs` | Явное «N body paragraphs» в брифе | `detected/required`, **weight=0** | 0 | `check_validator.py:341–357` | Compliance (фильтр `weight` в JS — **может не показываться**) |

**Пользователю через issues:** `check_scoring.validations_to_issues()` (107–128) конвертирует FAIL/PARTIAL в карточки с `title`, `message`, `severity`, `fix`, `location` (всегда `throughout document`).

**Пользователю через positives/needs:** `document_checker._positives_and_needs()` (701–731) — эвристики по параграфам, headings, refs, word count.

### 3.2. Structure recovery (`analyze_structure_recovery`)

Отдельная оценка **Structure Health Score** (не входит в readiness score).

| Проверка | Детерминированно / LLM | Что возвращается | Файл:строки |
|----------|------------------------|------------------|-------------|
| Восстановление дерева секций | LLM если нет headings (`recover_structure` → `ai_structure_recovery`); иначе preserved tree | `structure_tree`, `detected_sections`, `recovery_mode` | `document_structure_engine.py:1247+`, `document_checker.py:507–525` |
| Missing sections | Детерминированно: expected vs detected | `missing_sections[]` | `document_checker.py:530–531` |
| Large text block (>260 words) | Детерминированно | `paragraph_issues[]` | `document_checker.py:539–553` |
| Possible missing breaks (>140 words, ≥6 sentences) | Детерминированно | `paragraph_issues[]` | `document_checker.py:554–564` |
| Merged paragraphs (мало ¶, много текста) | Детерминированно | `paragraph_issues[]` | `document_checker.py:566–576` |
| Mixed heading styles | Детерминированно | `heading_issues[]` | `document_checker.py:578–589` |
| Missing / too few headings | Детерминированно | `heading_issues[]` | `document_checker.py:591–606` |
| Word heading style inconsistent (.docx) | Детерминированно | `heading_issues[]` | `document_checker.py:608–627` |
| **Structure health score** | **Формула:** 100 − min(45, missing×12) − min(35, para_issues×10) − min(25, heading×10) − 4 | `health_score` 0–100 | `document_checker.py:636–642` |

**UI:** вкладка «Structure Recovery» — `static/check.js:513–619`.

### 3.3. Метрики (`extract_document_metrics`)

| Метрика | Как считается | Файл:строки |
|---------|---------------|-------------|
| `word_count` | Regex слов | `document_checker.py:219–220` (via import) |
| `in_text_citations` | Regex `_IN_TEXT_CITATION` | `check_metrics.py:103` |
| `reference_entries` | Строки после refs heading с year/doi/etc. | `check_metrics.py:30–45` |
| `detected_sections` | Из `structure_tree` или heading-like paragraphs | `check_metrics.py:107–113` |
| Font/spacing/page numbers | Из .docx через `document_analyzer` helpers | `check_metrics.py:52–88` |
| `grammar_signal_count` | Double space + много коротких абзацев | `check_metrics.py:118–123` |
| `legacy_issues` | `analyze_document()` — старые checks | `check_metrics.py:116, 146` |

**НЕ отображается в UI:** `meta.metrics.legacy_issues`, `priorities`, `gemini_diagnostics` (поля есть в JSON, `check.js` их не читает).

### 3.4. Legacy `_run_content_checks` (не используется в prod flow)

Функция **не вызывается** из `check_document`, но содержит ~20 эвристических проверок по категориям `requirements_match`, `structure`, `headings`, `paragraphing`, `references`, `spacing_layout`, `clarity_organization` (`document_checker.py:752–1186`).  
Раньше это был основной checker; заменён pipeline v2. **Для V2 — кандидат на удаление**, часть логики дублирует validator/metrics.

### 3.5. Legacy `analyze_document` (частично жив)

Вызывается только для `legacy_issues` в metrics. Проверки (`document_analyzer.py:171–378`):

- missing references / incomplete refs list  
- missing introduction / conclusion  
- thin structure (<3 paragraphs)  
- (.docx) font mismatch, font size, line spacing, alignment, first-line indent, page numbers, heading styles, paragraph spacing  

**Не попадает в issue cards** текущего UI напрямую.

---

## 4. Промпты к LLM (дословно из кода)

> Промпт в `docs/prompts/requirements_extraction_prompt.md` относится к **Formatter V2 / smartform**, **не** к Academic Check V1. В Check используются промпты ниже.

### 4.1. Парсинг брифа — `services/requirements_parser.py:168–194`

**system_prompt:**
```
You are an assistant that extracts only academic document formatting and submission requirements from raw assignment briefs, OCR, emails, rubrics, or assessment guides.

Return ONE JSON object only, no markdown. Use these keys exactly:
- citation_style: string or null — one of: "APA", "MLA", "Harvard", "Chicago", "IEEE", "Vancouver", "OSCOLA", or another named style if explicitly given
- font_family: string or null — a common font name if stated or clearly implied, else null
- font_size: integer or null — point size (e.g. 12), else null
- spacing: number or string or null — use 2.0 for "double spaced", 1.5 for 1.5, 1.15 for 1.15, 1.0 for single; null if not stated
- margins: string or null — short description (e.g. "1 inch all sides", "2.54 cm", "normal"); null if not stated
- word_count: string or null — exact word count/range/limit only if explicitly stated
- required_sections: array of strings — document sections explicitly required for the submitted document, not rubric criteria
- cover_page_required: boolean or null — true/false only if explicitly stated
- page_numbers_required: boolean or null — true/false only if explicitly stated
- references_required: boolean or null — true/false only if explicitly stated
- submission_format: string or null — file/output format only if explicitly stated, such as PDF or DOCX
- confidence_score: number — 0 to 1 for confidence in extracted formatting requirements

You may also include these backwards-compatible keys when explicitly stated: line_spacing, alignment, headings, page_numbers.

Rules:
- Prioritize precision over recall. Leave fields null/empty if unsure.
- Do not guess numbers or styles that are not stated or strongly implied by context.
- Ignore learning outcomes, assessment criteria, marking rubrics, academic integrity policies, plagiarism warnings, university regulations, and general academic advice.
- Do not treat rubric headings like "knowledge", "analysis", "argument", or grade-band descriptors as required document sections.
- Phrases like "double-spacing", "double spaced", "double-spaced" → spacing 2.0
- "Times New Roman, 12 pt" → font_family "Times New Roman", font_size 12
- If only a citation style is named, set citation_style and references_required true only when references/citations are requested.
- Output valid JSON only.
```

**user_content** (шаблон, `requirements_parser.py:196–200`):
```
Extract formatting requirements from the following text. Respond with the JSON object only.

---
{text}
---
```

Fallback без LLM: `_strict_requirements_from_text()` — **детерминированный**, `requirements_parser.py:69+`.

### 4.2. Объяснение результатов — `services/check_explanation.py:48–57`

**system_prompt:**
```
You explain academic document check results to a student.

You receive PRE-COMPUTED validation results and a readiness score. You must NOT change, recalculate, or contradict the score.

Return JSON only with keys:
- summary: 2-3 sentences explaining the biggest gaps and what to fix first
- action_plan_narrative: array of 3-5 short actionable strings ordered by impact
- major_risks: array of up to 4 short risk strings if submission now would likely fail grading

Be direct. Reference the supplied metrics. Do not invent requirements not in the data.
```

**user_prompt** (шаблон, `check_explanation.py:59–67`):
```
Document type: {document_type}
Readiness score (fixed): {readiness_score}/100
Word count: {metrics.word_count}

Requirements excerpt:
{requirements[:4000]}

Validation results:
- {label}: required=..., detected=..., completion=...%, status=..., weight=...
```

### 4.3. Structure recovery — `services/ai_structure_recovery.py`

**STRUCTURE_SYSTEM_PROMPT** (строки 33–57):
```
You are an expert at recovering academic document structure from humanized or flattened text where headings and paragraph breaks were removed.

You receive numbered paragraphs from a student academic document. Infer logical structure from topic shifts, discourse cues, citation patterns, and genre conventions — not keyword matching alone.

Return ONE JSON object only (no markdown) with these keys:

- document_type: one of essay, report, research_paper, literature_review, case_study, reflection, learning_journal, dissertation_chapter, thesis_chapter, other
- document_type_confidence: number 0-1
- sections: array of section objects, each with:
  - title: canonical section label (e.g. Introduction, Literature Review, Methodology, Results, Discussion, Reflection, Conclusion, References, Title, Main Body)
  - heading_text: heading to insert in Word (usually same as title; for Title use the inferred document title string)
  - confidence: number 0-1 for this section boundary
  - paragraph_indices: array of 1-based integers referring to the ORIGINAL numbered paragraphs included in this section (every body paragraph exactly once)
  - insert_heading: boolean — true if a Word heading line should be inserted before this section (false for Title when the title is already the first paragraph)
- paragraph_splits: optional array for merged paragraphs — each { "index": 1-based paragraph number, "segments": ["...", "..."] } when one original paragraph clearly contains multiple ideas that should be separate paragraphs
- NEVER use paragraph_splits to break a single sentence. NEVER create a segment that is only a function word (are, the, as, of, in, …). Preserve sentence integrity.

Rules:
- Every original paragraph index must appear in exactly one section (except when paragraph_splits replaces an index with multiple segments).
- Identify title, introduction, body sections appropriate to document_type, conclusion, and references when present.
- References: citation-list paragraphs at the end (Author, Year patterns).
- Do not invent content; only reorganize and label structure.
- Prefer more sections with moderate confidence over one large undifferentiated body.
- If explicit headings already exist as standalone short lines, set insert_heading false for those sections.
```

**CLASSIFY_SYSTEM_PROMPT** (59–65):
```
You classify student academic documents from paragraph previews.

Return ONE JSON object only:
- document_type: one of essay, report, research_paper, literature_review, case_study, reflection, learning_journal, dissertation_chapter, thesis_chapter, other
- document_type_confidence: number 0-1

Use genre cues, citation patterns, section-like openings, and assignment style — not keyword matching alone.
```

**HEADINGS_SYSTEM_PROMPT** (67–81):
```
You identify section heading lines in humanized academic documents.

You receive numbered paragraphs (possibly a batch). Find every paragraph that begins or contains a section heading.

Return ONE JSON object only:
- candidates: array of objects, each with:
  - paragraph_index: 1-based integer
  - heading_text: exact heading text to use in Word (include entry titles like "Journal Entry 1: ...")
  - level: integer 1-3 (title=1, major sections=2, subsections=3)
  - confidence: number 0-1

Rules:
- Headings may be embedded at the start of a longer paragraph.
- Include title lines, journal entry headings, reflection, references, introduction, etc.
- Do not invent headings not supported by the paragraph text.
```

**HIERARCHY_SYSTEM_PROMPT** (83–99):
```
You assign every numbered paragraph to academic sections using confirmed heading candidates.

Return ONE JSON object only:
- sections: array of section objects, each with:
  - title: canonical section label
  - heading_text: heading for Word
  - confidence: number 0-1
  - paragraph_indices: 1-based integers for paragraphs in this section (each paragraph in your batch exactly once)
  - insert_heading: boolean
  - level: optional integer 1-3
- paragraph_splits: optional array of { "index": int, "segments": [strings] }

Rules:
- Use the provided document_type and heading candidates.
- Every paragraph index in the batch must appear in exactly one section.
- Do not invent content; only group and label.
- Prefer meaningful sections over one undifferentiated block.
```

### 4.4. Мёртвый промпт `_gemini_insights` — `document_checker.py:140–147`

```
You analyze academic document quality and return strict JSON.

Return keys exactly:
- document_classification: object with document_type (essay|report|literature_review|research_paper|case_study|reflection|learning_journal|dissertation_chapter|thesis_chapter|other), confidence (0-1), rationale (short string)
- compliance_analysis: object with summary (short string), alignment_level (high|medium|low), major_risks (array of short strings)
- formatting_recommendations: array of concise actionable strings (max 6)

Use the supplied local analyzer context; do not invent unsupported facts.
```

**Не используется** в текущем `check_document`.

---

## 5. Формат ответа API `POST /api/check-document`

### 5.1. Успех (200)

Корневой объект JSON (см. `document_checker.py:1277–1307`):

| Поле | Тип | Описание |
|------|-----|----------|
| `score` | int 0–100 | Readiness score (формула, §6) |
| `verdict` | string | `Excellent` / `Good` / `Needs improvement` / `Major issues` |
| `summary` | string | Из `explain_check_results` или локальный fallback |
| `categories` | object | Ключ → `{ score: int, label: string }` (5 категорий) |
| `positives` | string[] | До 5 строк |
| `needs_work` | string[] | До 6 строк |
| `issues` | object[] | Карточки: `category`, `severity`, `title`, `message`, `fix`, `location`, `penalty`, optional `validation_id` |
| `next_steps` | string[] | Из action_plan + narrative |
| `structure_analysis` | object | §5.2 |
| `validations` | object[] | Полный список validation (§3.1) |
| `action_plan` | object[] | `{ step_number, title, action, estimated_improvement, priority }` |
| `priorities` | object | `{ critical: string[], medium: string[], low: string[] }` — **не в UI** |
| `gemini_diagnostics` | object \| null | **не в UI** |
| `meta` | object | §5.3 |

### 5.2. `structure_analysis`

| Поле | Тип |
|------|-----|
| `health_score` | int |
| `detected_sections` | `{ title, canonical, style?, ... }[]` |
| `expected_sections` | string[] |
| `missing_sections` | string[] |
| `paragraph_issues` | object[] |
| `heading_issues` | object[] |
| `suggestions` | string[] |
| `structure_tree` | object[] |
| `headings_present` | bool |
| `recovery_mode` | string (`preserved`, `ai`, `inferred`, …) |
| `inferred_document_type` | string |
| `document_type_confidence` | float |
| `overall_confidence` | float |
| `paragraph_count` | int |

При ошибке recovery может быть `{ error, health_score: 0, ... }` (`document_checker.py:513–525`).

### 5.3. `meta`

| Поле | Тип |
|------|-----|
| `word_count` | int |
| `paragraph_count` | int |
| `document_type` | string |
| `document_classification` | `{ document_type, confidence, source }` |
| `compliance_analysis` | object \| null (из explanation) |
| `formatting_recommendations` | string[] |
| `parsed_requirements` | = `structured_requirements` |
| `structured_requirements` | object (`StructuredRequirements.to_dict()`) |
| `metrics` | object (включая `legacy_issues`) |
| `notes` | string[] (всегда `[]` в текущем коде) |

### 5.4. Ошибки

| HTTP | Тело | Причина |
|------|------|---------|
| 400 | `{ "error": "..." }` | Пустой текст, неверный файл, `result.error` |
| 500 | `{ "error": "Document check failed..." }` | Exception в `check_document` |
| 503 | `{ "error": "..." }` | PDF/OCR runtime (extract upload) |

### 5.5. Что видит пользователь на странице (`check.html` + `check.js`)

При **включённом** роуте (сейчас недоступно):

1. **Score ring** — `score`, `verdict`, `summary`  
2. **Main problems** — top 3 из `issues` / `needs_work`  
3. **Вкладки:** Parser (detected requirements), Structure Recovery, Formatting (categories, positives, needs, issues), Citation, Compliance (validations), Action Plan  
4. **Apply to Format** — сохраняет `form` из extract-requirements в localStorage и редирект на `/`  
5. **Tool history** — `DMToolHistory.push("check", ...)`

**Сейчас пользователь видит только** `soon.html` («SOON...») на `GET /check`.

---

## 6. Откуда берётся оценка

### 6.1. Readiness score (главная цифра)

**Источник:** формула, **не LLM**.

```python
# check_scoring.py:8-17
score = round(sum(weight * completion for each active validation) / sum(weights))
# Фактически: earned = Σ(weight × completion); return int(round(earned))
# при weights summing to 100 когда все checks active
```

Пороги verdict (`check_scoring.py:20–27`):

| Score | Verdict |
|-------|---------|
| ≥85 | Excellent |
| ≥70 | Good |
| ≥50 | Needs improvement |
| <50 | Major issues |

Category scores (`validations_to_categories`): среднее `completion*100` по validations в bucket — **отдельно от total score**.

### 6.2. Structure health score

**Формула** в `document_checker.py:636–642` (см. §3.2). **Не влияет** на readiness score.

### 6.3. LLM и score

- `explain_check_results` явно: «must NOT change, recalculate, or contradict the score» (`check_explanation.py:50`).  
- Парсинг брифа влияет **косвенно** (какие validations активируются), но не задаёт score напрямую.

---

## 7. Почему стоит пометка Soon / что мешает снять

| Фактор | Детали |
|--------|--------|
| **Явный gate в роуте** | `app.py:1805–1812` — `check()` рендерит `soon.html` с комментарием «temporarily gated» |
| **UI не подключён** | `templates/check.html` **ни разу** не вызывается через `render_template` в коде |
| **Документация продукта** | FAQ, changelog, credits, terms — везде указано, что Check «Soon» (`templates/info/*.html`) |
| **Функция не отключена флагом** | Нет env вроде `CHECK_ENABLED`; gate только в роуте страницы |
| **API работает** | `POST /api/check-document` доступен без auth — backend **живой** |
| **Badge в sidebar** | **НЕ НАЙДЕНО** отдельной метки «Soon» в `templates/base.html:137–142` — только ссылка «Check», ведущая на soon-page |
| **Changelog** | «temporarily gated behind the shared Soon page (code kept for later)» — `templates/info/changelog.html:12` |

**Вывод:** снять Soon = в первую очередь **вернуть `render_template("check.html")` в `check()`** и обновить info-страницы. Технически backend и фронт (check.js) уже собраны.

**Риски при включении без доработок:**

- AI structure recovery может вернуть 503/error в `structure_analysis` на «плоских» humanized текстах без Gemini (`document_structure_engine.py:1293+`).  
- `legacy_issues` не показываются — часть .docx checks теряется.  
- Два параллельных score (readiness vs structure health) могут путать пользователя.  
- Промпт парсинга V1 слабее, чем V2 smartform (`docs/prompts/requirements_extraction_prompt.md`).

---

## 8. Переиспользование vs выброс для V2

### 8.1. Сохранить / переиспользовать

| Компонент | Почему |
|-----------|--------|
| `check_pipeline.py` orchestration | Чистое разделение: requirements → metrics → validate → score → explain |
| `check_validator.py` + `check_scoring.py` | Прозрачная формула score, тестируемая (`test_check_pipeline.py`) |
| `check_requirements.py` + `parse_requirements_for_check` | Детерминированный fallback парсинга |
| `check_metrics.py` | Измеримые метрики без LLM |
| `templates/check.html` + `static/check.js` | Готовый UX с вкладками; нужен только wire-up роута |
| `analyze_structure_recovery` + `document_structure_engine` | Полезно для humanized/flat text |
| `tests/test_check_pipeline.py` | Регрессия scoring |
| API контракт `validations[]` + `action_plan` | Хорошая основа для compliance UI |

### 8.2. Выбросить или не тащить

| Компонент | Почему |
|-----------|--------|
| `_run_content_checks()` | Мёртвый дубликат pipeline checks |
| `_gemini_insights()` | Мёртвый; перекрыт `check_explanation` |
| `_category_scores`, `_overall_score`, `_verdict` в `document_checker.py` | Старый scoring; superseded by `check_scoring.py` |
| `legacy_issues` path через `analyze_document` | Не surfaced в UI; дублирует validator |
| `requirements_parser.parse_requirements` промпт V1 | Хуже V2 smartform prompt; лучше унифицировать |
| `soon.html` gate pattern | Заменить на feature flag или удалить после launch |
| 8 категорий `CATEGORIES` / `CATEGORY_WEIGHTS` в `document_checker.py` | Legacy; UI использует 5 buckets из `check_scoring` |

### 8.3. Доработать при V2

- Единый парсер требований (V2 smartform + evidence validation).  
- Показать или удалить `legacy_issues`, `priorities`, `gemini_diagnostics`.  
- E2E тесты API + smoke UI.  
- Graceful degradation когда Gemini недоступен (structure + explanation).  
- Согласовать structure health vs readiness score в одном UX.

---

## 9. Связанные эндпоинты (не Check, но используются)

| Endpoint | Использование в Check flow |
|----------|----------------------------|
| `POST /api/extract-requirements` | `check.js:165` — перед check |
| `POST /api/extract-document` | `FormatterCommon` — автозаполнение paste из .docx/.pdf |
| `POST /parse-requirements` | Home page only (`static/home.js:933`) |
| `POST /api/structure-recovery` | Standalone; дублирует часть check |

---

## 10. Константы и лимиты

| Константа | Значение | Файл |
|-----------|----------|------|
| `MAX_TEXT_CHARS` | 200_000 | `document_checker.py:23` |
| Поддерживаемые doc types | essay, report, … other | `document_checker.py:47–59` |
| Academic Check billing | Free (no login) | `app.py:5739` |

---

*Аудит выполнен по состоянию репозитория на 2026-08-17. Все ссылки на строки — актуальны для текущего `main`/working tree.*
