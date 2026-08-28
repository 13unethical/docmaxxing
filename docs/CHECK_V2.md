# Academic Check V2 — как устроена проверка

**Дата:** 2026-08-28  
**Статус:** код готов, UI на `/check` закрыт `soon.html` до деплоя. API `POST /api/check-document` работает.

---

## 1. Точки входа

| Компонент | Путь | Назначение |
|-----------|------|------------|
| Страница (gated) | `GET /check` | `soon.html` — пункт меню виден, страница закрыта |
| Проверка | `POST /api/check-document` | Multipart: `requirements`, `pasted_text`, `document_type`, опционально `file` (.docx/.pdf), `parsed_requirements` (JSON) |
| Парсинг брифа (UI) | `POST /api/extract-requirements` | Gemini + fallback для полей брифа |
| Шаблон / клиент | `templates/check.html`, `static/check.js`, `static/check_report.js` | Полный UI, подключается при открытии `/check` |

Оркестрация: `services/document_checker.py` → `check_document()` → `services/check_pipeline.py` → `run_check_pipeline()`.

---

## 2. Поток данных

```
Бриф (текст / parsed JSON)     Документ (paste / .docx / .pdf)
         │                              │
         ▼                              ▼
 normalize_requirements()      extract_document_model()  ← formatter_v2
         │                              │
         └──────────┬───────────────────┘
                    ▼
         extract_document_metrics()     ← Python, без LLM
                    ▼
         validate_all_requirements()    ← Python, детерминированно
                    ▼
         compute_readiness_score()      ← взвешенный балл
         validations_to_categories()
         build_action_plan()
                    ▼
         explain_check_results()        ← Gemini (опционально) или локальный текст
```

**Structure recovery** (`analyze_structure_recovery` в `document_checker.py`) считается параллельно для панели «outline coverage» и **не входит** в readiness score.

---

## 3. Что делает Python, что делает Gemini

### Python (всегда)

| Модуль | Роль |
|--------|------|
| `check_requirements.py` | Бриф → `StructuredRequirements` (regex + поля из `parse_requirements_for_check` / `parsed_requirements`) |
| `check_structure.py` | `DocumentModel` через `formatter_v2` (Word styles или эвристики) |
| `check_text.py` | Разбиение на абзацы, подсчёт слов |
| `check_citations.py` | Режим цитирования, сопоставление списка литературы с текстом |
| `check_metrics.py` | Метрики: слова, секции, шрифт, баланс секций, длина абзацев, аналитические абзацы без цитат |
| `check_validator.py` | Каждая проверка → `required` / `detected` / `completion` (0–1) / `status` |
| `check_scoring.py` | Итоговый балл, категории, action plan, список «не проверялось» |
| `document_checker.py` | Сборка ответа API, structure analysis |

### Gemini (опционально)

| Место | Роль |
|-------|------|
| `check_explanation.py` → `explain_check_results()` | 2–3 предложения summary + до 4 `major_risks` **по уже посчитанным validations**. Балл **не меняет**. |
| `requirements_parser.py` (через `/api/extract-requirements`) | Парсинг брифа в UI до нажатия «Check» |
| `ai_structure_recovery.py` | Только если в документе нет заголовков (outline panel) |

Если `GOOGLE_API_KEY` / `GEMINI_API_KEY` нет — explanation строится локально (`source: "local"`).

Фильтры explanation: запрет выдумывать числа, в режиме без брифа — запрет claims про соответствие требованиям.

---

## 4. Проверки и веса

Взвешенный балл считается только по проверкам с `weight > 0` и статусом **не** из: `SKIP`, `NOT_APPLICABLE`, `NOT_CHECKED`, `CANNOT_VERIFY`.

### 4.1. Из брифа (включаются при наличии полей)

| ID | Label | Weight | Когда включается | Completion / пороги |
|----|-------|--------|------------------|---------------------|
| `word_count` | Word count | **25** | `word_min` и/или `word_max` в брифе | В диапазоне → 1.0; ниже min → `wc/min`; выше max → штраф до 0.5 |
| `sections` | Required sections | **20** | `required_sections` не пуст | `present/total`; секция = заголовок + ≥30 слов тела (References: ≥1 запись) |
| `references` | References | **15** | `peer_reviewed_refs` или `references_required` | `min(1, detected/target)`; без секции References → 0 |
| `in_text_citations` | In-text citations | **15** | стиль цитирования / refs / references_required | См. §5; `CANNOT_VERIFY` → **исключается из балла** |
| `formatting` | Formatting | **10** | font / size / spacing / page numbers в брифе | Доля совпавших правил; без .docx поля = «Unknown» |

### 4.2. Всегда (brief-less heuristics)

| ID | Label | Weight | Completion / пороги |
|----|-------|--------|---------------------|
| `academic_style` | Academic structure | **4** | 0.55×developed_sections/4 + 0.45×body_paras/8; cap 0.6 если <2 секций или <4 абзацев |
| `bibliography` | Reference list | **8** | Только если нет проверки `references` из брифа: ≥5 → 1.0; ≥1 → 0.55; иначе 0 |
| `in_text_presence` | In-text citations present | **8** | ≥5 hits → 1.0; ≥1 → 0.5; иначе 0 |
| `section_balance` | Section length balance | **7** | Одна секция >50% текста → FAIL; >40% → PARTIAL (0.7); ≤1 developed section → 0.15 |
| `analytical_citation_coverage` | Citations in analytical paragraphs | **7** | См. §6 |
| `paragraph_length` | Paragraph length | **6** | PASS: ≤5% абзацев >250 слов и avg ≤160; PARTIAL: ≤20% и avg ≤220 |

### 4.3. Информационные (не в балле)

| ID | Weight | Статус |
|----|--------|--------|
| `sections_observed` | 0 | `NOT_CHECKED` — список найденных заголовков, если в брифе секции не заданы |
| `body_paragraphs` | 0 | Если в брифе указано число body paragraphs |

**Максимальная сумма весов** при полном брифе + все эвристики: 25+20+15+15+10+4+8+8+7+7+6 = **125** (нормализация по фактически применённым весам).

---

## 5. Цитирование (`check_citations.py`)

### Режим

1. **numeric** — большинство строк списка вида `[1]` или `1. Author…`
2. **author_year** — большинство строк с фамилией + годом
3. **unknown** → `verifiable: false`, статус `CANNOT_VERIFY`, **не штрафует балл**

### Сопоставление

- **Numeric:** номера в тексте `[1]`, `(1)` ↔ номера в списке
- **Author-year:** `(Smith, 2020)`, `Smith (2020)` ↔ записи bibliography

### Completion `in_text_citations` (из брифа)

| Условие | completion | status |
|---------|------------|--------|
| Все listed cited, нет missing | 1.0 | PASS |
| `matched / (listed + missing)` ≥ 0.85, нет дыр | 1.0 | PASS |
| ≥ 0.4 | partial | PARTIAL |
| Иначе | ниже | FAIL |

---

## 6. Пороги покрытия (ключевые)

### Аналитические абзацы с цитатами (`analytical_citation_coverage`)

Аналитические секции: заголовки с hints (`analysis`, `discussion`, `literature`, …), исключая intro/conclusion/methods/references.

| Доля аналитических абзацев **без** цитаты | completion | status |
|-------------------------------------------|------------|--------|
| 0 аналитических абзацев | 0.35 | PARTIAL |
| ≤ 35% | 1.0 | PASS |
| ≤ 70% | 0.55 | PARTIAL |
| > 70% | `1 - share` | FAIL |

### Баланс секций (`section_balance`)

- Developed section = секция с ≥30 словами (кроме references/appendix/abstract)
- FAIL если одна секция ≥65% слов; PARTIAL если ≥50%

### Длина абзацев (`paragraph_length`)

- Измеряются абзацы ≥20 слов
- PASS: `share_over_250 ≤ 0.05` и `avg ≤ 160`
- PARTIAL: `share ≤ 0.2` и `avg ≤ 220`

### Секции из брифа

- Заголовок без тела (<30 слов) **не засчитывается**
- References: нужна ≥1 bibliographic entry

---

## 7. Формула балла

```text
readiness_score = round( Σ(weight_i × completion_i) / Σ(weight_i) × 100 )
```

`completion_i ∈ [0, 1]` — доля выполнения проверки.

### Вердикт (`score_to_verdict`)

| Балл | Verdict |
|------|---------|
| ≥ 85 | Excellent |
| ≥ 70 | Good |
| ≥ 50 | Needs improvement |
| < 50 | Major issues |

### Категории UI (среднее completion×100 по проверкам категории)

| Ключ | Label |
|------|-------|
| `requirements_match` | Requirements match |
| `structure` | Structure |
| `formatting` | Formatting |
| `references` | References / citations |
| `clarity_organization` | Clarity of organization |

Категория без активных проверок → `NOT_CHECKED`, `score: null`.

### Action plan

До 6 шагов с `fix` из validations, сортировка по `weight × (1 - completion)` (потенциальный прирост балла). Шаги с gain < 0.5 п.п. отбрасываются.

---

## 8. Режим без брифа

- Проверки из §4.1 не запускаются (кроме косвенных через пустой structured)
- Работают эвристики §4.2 + `sections_observed` (наблюдение)
- Gemini explanation: **no-brief mode** — без claims про word limit / rubric
- `meta.has_assignment_brief` в ответе API

---

## 9. Структура документа

`check_structure.py` использует тот же выбор экстрактора, что `formatter_v2`:

- `.docx` с размеченными стилями → extractor по стилям Word
- Иначе → эвристики по тексту / списку абзацев

Метрики секций: `body_word_count`, `reference_entries`, canonical title через `heading_label_without_number`.

---

## 10. Тесты

| Файл | Что покрывает |
|------|----------------|
| `tests/test_check_pipeline.py` | Pipeline, scoring, brief-less, sections_observed |
| `tests/test_check_citations.py` | Numeric / author-year / cannot verify |
| `tests/test_check_ui.py` | UI-related expectations |

Фикстуры: `tests/fixtures/test_essay_styled.docx`, `test_essay_styled_minimal.docx`.

Ручной аудит реальных файлов: `samples/real/` (в `.gitignore`, не в репозитории).

---

## 11. Файлы (карта)

```
services/
  document_checker.py      # API entry, structure recovery
  check_pipeline.py        # orchestration
  check_requirements.py    # StructuredRequirements
  check_metrics.py         # metrics
  check_validator.py       # validations + weights
  check_scoring.py         # score, categories, action plan
  check_explanation.py     # Gemini / local summary
  check_structure.py       # formatter_v2 DocumentModel
  check_citations.py       # citation matching
  check_text.py            # paragraphs, word count
static/check.js            # wizard UI
static/check_report.js     # report rendering
templates/check.html
```

---

## 12. Деплой

1. Убедиться, что `GOOGLE_API_KEY` задан (для explanation и extract-requirements).
2. В `app.py` заменить `soon.html` на `check.html` в `check()`.
3. Убрать Academic Check из «Coming soon» в `about.html` / `faq.html`.
4. Прогнать `pytest tests/test_check_pipeline.py tests/test_check_citations.py tests/test_check_ui.py`.
