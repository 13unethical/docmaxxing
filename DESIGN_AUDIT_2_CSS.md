# DESIGN_AUDIT_2_CSS

Аудит стилей проекта (только чтение). Срез: 2026-08-13.  
Область: `static/*.css` + inline в `templates/**/*.html`.  
Исключены: `venv/`, `browser_profiles/`, сторонние расширения Chrome.

---

## 1. CSS-файлы и где подключаются

| файл | размер | подключение | охват |
|---|---:|---|---|
| `static/style.css` | ~106 KB / 5770 строк | глобально в `templates/base.html`; также в мёртвом `templates/workspace_base.html` | Почти все страницы через `extends "base.html"` / `tools_base` / `info/base` |
| `static/tools.css` | ~53 KB / 2913 строк | `templates/tools_base.html` (`head_extra`) | Humanizer, Assignment, Turnitin, Workspace, Editor (наследует tools_base) |
| `static/workspace.css` | ~27 KB / 741 строк | локально в `templates/workspace.html`; также в `workspace_base.html` | Только workspace |
| `static/humanizer.css` | ~13 KB / 683 строк | локально в `templates/humanizer.html` | Только humanizer |
| `static/earn.css` | ~14 KB / 774 строк | локально в `templates/earn.html` | Только earn |
| `static/admin.css` | ~13 KB / 786 строк | локально в `templates/admin.html`, `templates/admin_dataset_stats.html` | Admin |
| `static/tour.css` | ~4.6 KB / 249 строк | **нигде не `<link>`’ится** | Файл есть, ссылок в templates/js/py нет |

### Внешние шрифты (не локальный CSS)

| источник | где |
|---|---|
| Google Fonts `Inter` (400–700) | `templates/humanizer.html` |
| Google Fonts `Inter` (400–800) | `templates/workspace.html` |

### Цепочка наследования → `style.css`

Все page-шаблоны, кроме партиалов (`_*.html`, `info/_toc.html`) и standalone `workspace_base.html`, получают `style.css` через `base.html`.

Дополнительно page-specific CSS накладывается только там, где указано в таблице выше.

---

## 2. Inline `<style>` и `style=""`

| шаблон | `<style>` блоков | `style="..."` атрибутов (примерно) |
|---|---:|---:|
| `templates/format_v2.html` | **1** (~356 строк: V2 layout/spacing) | **9** |
| `templates/earn.html` | 0 | 2 |
| `templates/check.html` | 0 | 1 |
| `templates/admin_dataset_stats.html` | 0 | 1 |
| `templates/verify_email.html` | 0 | 1 |
| остальные шаблоны | 0 | 0 |

Итого: **1** крупный inline `<style>` (format_v2), **~14** inline `style=` атрибутов в 5 шаблонах.  
Основная масса стилей — в CSS-файлах.

---

## 3. Уникальные цвета (по частоте)

Подсчёт по `static/*.css` + inline в templates.  
Короткие hex нормализованы (`#fff` → `#ffffff`).  
Отдельно: много `color-mix(...)` (**128** вхождений) и **22** уникальных `oklch(...)` (в основном токены в `style.css`) — ниже не развёрнуты построчно.

### Hex (94 уникальных; топ по частоте)

| count | color |
|---:|---|
| 50 | `#ffffff` |
| 18 | `#2563eb` |
| 17 | `#b91c1c` |
| 17 | `#94a3b8` |
| 16 | `#047857` |
| 15 | `#64748b` |
| 14 | `#e2e8f0` |
| 14 | `#f1f5f9` |
| 14 | `#0f172a` |
| 12 | `#f8fafc` |
| 10 | `#fafbfd` |
| 9 | `#059669` |
| 9 | `#d97706` |
| 8 | `#cbd5e1` |
| 8 | `#b45309` |
| 8 | `#dc2626` |
| 7 | `#0f766e` |
| 7 | `#16a34a` |
| 6 | `#eff6ff` |
| 6 | `#fef2f2` |
| 6 | `#ecfdf5` |
| 6 | `#1e293b` |
| 6 | `#334155` |
| 6 | `#234977` |
| 6 | `#f59e0b` |
| 5 | `#fecaca` |
| 5 | `#fffbeb` |
| 5 | `#000000` |
| 5 | `#c4b5fd` |
| 5 | `#111827` |
| 5 | `#a78bfa` |
| 4 | `#93c5fd` |
| 4 | `#1d4ed8` |
| 4 | `#15803d` |
| 3 | `#fee2e2`, `#a7f3d0`, `#475569`, `#c8cdd3`, `#86efac`, `#3b82f6`, `#34d399`, `#f87171` |
| 2 | `#eef2f7`, `#6ee7b7`, `#d5dae0`, `#f9fafc`, `#fde68a`, `#bfdbfe`, `#fef3c7`, `#f3f6fb`, `#fca5a5`, `#166534`, `#fbbf24`, `#2f6fed`, `#e2a100`, `#1a1a1a`, `#8a8a8a` |
| 1 | `#e8ecf2`, `#f0fdfa`, `#121417`, `#9aa3ad`, `#8b949e`, `#0b0d10`, `#bbf7d0`, `#f0fdf4`, `#d1fae5`, `#e0e7ff`, `#4338ca`, `#e5e7eb`, `#f8fbff`, `#dbeafe`, `#e8edf5`, `#111111`, `#f5f3ff`, `#5b21b6`, `#b42318`, `#dcfce7`, `#22c55e`, `#92400e`, `#ea580c`, `#ffeeee`, `#38bdf8`, `#e9d5ff`, `#faf5ff`, `#f1f4f8`, `#f3f4f6`, `#e5eaf3`, `#f5f8ff`, `#eef2f8`, `#e7eeff`, `#6b5a2e`, `#8a5a00`, `#555555`, `#a23a2d` |

### rgba/rgb (34 уникальных)

| count | value |
|---:|---|
| 4 | `rgba(15,23,42,0.04)` |
| 4 | `rgba(15,23,42,0.06)` |
| 3 | `rgba(37,99,235,0.12)` |
| 3 | `rgba(37,99,235,0.35)` |
| 3 | `rgba(0,0,0,0.04)` |
| 3 | `rgba(15,23,42,0.55)` |
| 2 | `rgba(15,23,42,0.35)`, `rgba(15,23,42,0.45)`, `rgba(0,0,0,0.06)`, `rgba(0,0,0,0.35)`, `rgba(255,255,255,0.06)`, `rgba(15,23,42,0.08)` |
| 1 | остальные ~22 значения (тени/оверлеи на базе slate/blue/black/white) |

### hsl/hsla (23 уникальных; в основном токены `:root`)

| count | value |
|---:|---|
| 4 | `hsl(300 0% 4%)` |
| 2 | `hsl(300 50% 100%)` |
| 1 | `hsl(0 0% 90%)`, `hsl(300 0% 95%)`, `hsl(0 0% 50%)`, `hsl(340 0% 62%)`, `hsl(208 74% 28%)`, `hsl(38 100% 17%)`, `hsl(9 21% 41%)`, `hsl(52 23% 34%)`, `hsl(147 19% 36%)`, `hsl(217 22% 41%)`, `hsl(0 0% 100%)`, `hsl(0 0% 98%)`, `hsl(336 0% 1%)`, `hsl(0 0% 9%)`, `hsl(330 0% 39%)`, `hsl(0 0% 28%)`, `hsl(300 0% 18%)`, `hsl(9 26% 64%)`, `hsl(52 19% 57%)`, `hsl(146 17% 59%)`, `hsl(217 28% 65%)` |

Палитра по смыслу: slate/blue (`#0f172a`, `#2563eb`, `#234977`), success green, danger red, amber warning; много одноразовых оттенков в feature CSS (workspace/humanizer/earn).

---

## 4. Typography

### `font-family` (уникальные стеки)

| count | stack |
|---:|---|
| 5 | `inherit` |
| 4 | `"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` |
| 2 | `"Times New Roman", Times, serif` |
| 2 | `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace` |
| 2 | `ui-monospace, SFMono-Regular, Menlo, monospace` |
| 1 | `"Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif` |

UI-шрифт по умолчанию — **Inter** (+ system fallback). Serif — для превью академического текста. Mono — код/ID/ledger.

### `font-weight` (уникальные)

| count | value |
|---:|---|
| 90 | `700` |
| 86 | `600` |
| 39 | `650` |
| 16 | `500` |
| 15 | `800` |
| 14 | `750` |
| 8 | `550` |
| 6 | `400` |
| 1 | `bold`, `inherit`, `300`, `700 !important`, `450` |

Доминируют **600/700**; есть нестандартные веса `650/750/550/450` (variable-font friendly, но без явной variable Inter axis в CSS).

### `font-size` (уникальные, по частоте; ~76 значений)

Самые частые: `0.9rem` (50), `0.82rem` (43), `0.88rem` (42), `0.95rem` (36), `0.85rem` (33), `0.8rem` (31), `0.78rem` (28), `0.92rem` (25), `0.72rem` (19), `1.05rem` (17), `0.875rem` (12), `0.68rem` (10), `0.75rem` (9), `1rem` / `1.35rem` / `0.84rem` (по 8).

Также встречаются: `px`/`pt` (`9px`, `12pt`, `16pt`), много `clamp(...)` для заголовков, единичные `em`/`!important`.

Вывод: шкала размеров **не сведена к токенам** — много близких rem-значений.

---

## 5. `border-radius` и `box-shadow`

### `border-radius` (37 уникальных)

| count | value |
|---:|---|
| 57 | `999px` (пиллы) |
| 40 | `var(--radius-sm)` |
| 34 | `10px` |
| 27 | `8px` |
| 20 | `12px` |
| 11 | `14px` |
| 11 | `50%` |
| 7 | `16px` |
| 6 | `6px`, `var(--radius)` |
| 5 | `3px` |
| ≤4 | `0.65rem`, `7px`, `inherit`, `0.5rem`, `0.9rem`, `2px`, `9px`, `var(--hz-radius-card)`, `0.55rem`, `0.75rem`, `18px`, `5px`, асимметричные углы, `var(--hz-radius-editor)`, `var(--ws-radius)`, `0`, `4px`, … |

Токены есть (`--radius`, `--radius-sm`), но рядом много «сырых» px/rem.

### `box-shadow` (46 уникальных)

| count | value |
|---:|---|
| 22 | `none` |
| 22 | `var(--shadow)` |
| 3 | `var(--hz-shadow)`, `var(--ws-shadow)` |
| 2 | focus ring `0 0 0 3px color-mix(... primary ...)`, soft card shadows |
| 1 | ~35 остальных (focus rings, dark overlays `9999px`, hover shadows, inset) |

---

## 6. CSS-переменные (`--*`)

### Глобальные / shared (в основном `style.css` `:root` и `[data-theme="dark"]`)

Spacing: `--space-1` … `--space-11`  
Colors: `--bg-dark`, `--bg`, `--bg-light`, `--text`, `--text-muted`, `--highlight`, `--border`, `--border-muted`, `--primary`, `--secondary`, `--danger`, `--warning`, `--success`, `--info`  
Effects: `--shadow`, `--radius`, `--radius-sm`  
Layout: `--container-max`, `--max`, `--page-pad-x`, `--page-pad-y`, `--content-gap`, `--split-layout`, `--app-sidebar-w`  
Aliases: `--bg0`, `--bg1`, `--surface`, `--muted`, `--line`, `--accent`, `--accent-hover`, `--accent-muted`, `--success-bg`, `--success-line`, `--error-bg`, `--error-line`, `--on-primary`, `--on-secondary`, `--cta-text`  
Pricing leftovers: `--gumroad`, `--gumroad-primary`, `--copy`

### Admin (`admin.css`)

`--outline`, `--blue`, `--save`, `--ledger`, `--purchases`, `--usage`, `--delete`, `--approve`, `--reject` (+ переопределения `--primary/--secondary/...`)

### Workspace (`workspace.css`)

`--ws-bg`, `--ws-surface`, `--ws-border`, `--ws-border-strong`, `--ws-text`, `--ws-muted`, `--ws-faint`, `--ws-primary`, `--ws-primary-hover`, `--ws-amber`, `--ws-amber-soft`, `--ws-purple`, `--ws-violet`, `--ws-green`, `--ws-red`, `--ws-radius`, `--ws-shadow`, `--ws-ease`

### Humanizer (`humanizer.css`)

`--hz-bg`, `--hz-card`, `--hz-card-border`, `--hz-border`, `--hz-primary`, `--hz-primary-hover`, `--hz-muted`, `--hz-text`, `--hz-radius-card`, `--hz-radius-editor`, `--hz-shadow`, `--hz-shadow-hover`, `--hz-ease`

### Используется, но не определено в CSS-файлах

В inline `<style>` `format_v2.html`: `--v2-line-gap`, `--v2-line-width`, `--v2-line-offset` (локальные для V2).

**Итого определено ~94 имени переменных** (часть дублируется light/dark). Параллельные неймспейсы `--`, `--ws-*`, `--hz-*`, admin overrides — единой design-token системы нет.

---

## 7. Повторяющиеся UI-компоненты (по классам в шаблонах)

Подсчёт: сколько **шаблонов** содержат класс (не число DOM-узлов).

### Кнопки

| классы | # шаблонов | где |
|---|---:|---|
| `btn-secondary` | 5 | check, editor, format_v2, index, soon |
| `adm-btn`, `adm-btn--ghost` | 2 | admin, admin_dataset_stats |
| `home-doc-segment-btn` | 2 | format_v2, index |
| feature-кнопки (`earn-btn*`, `pricing-plan-btn*`, `ws-btn*`, `hz-icon-btn`, `hz-segment-btn`, `acct-btn`, `info-btn*`, `auth-resend-btn`, `btn-check`, `dm-tutorial-btn*`, …) | 1 каждый | свои страницы |

Паттерн: общего `btn` / `btn-primary` почти нет в разметке; вместо этого **префиксные семейства** (`adm-`, `earn-`, `ws-`, `hz-`, `pricing-`).

### Карточки

| классы | # шаблонов |
|---|---:|
| `card` | 6 (check, format_v2, index, login, register, verify_email) |
| `auth-card` | 3 |
| `card-title` | 3 |
| `adm-card` | 2 |
| `card-hint` | 2 |
| `home-input-card` | 2 |
| остальные (`acct-card`, `earn-card*`, `check-*-card`, `ws-landing-card`, …) | 1 |

### Инпуты / поля

| классы | # шаблонов |
|---|---:|
| `field`, `label` | 3 |
| `auth-field`, `auth-label` | 3 |
| `field-row` | 2 |
| page-specific (`acct-field`, `earn-field`, `asg-chat-input`, `dm-auth-input`, `auth-otp-input`, `check-select`, …) | 1 |

### Табы

| классы | # шаблонов |
|---|---:|
| `dm-auth-tabs` / `dm-auth-tab` | 1 (`_register_wall`) |
| `ws-tabs` / `ws-tab` | 1 (workspace) |
| `check-analysis-tabs` / `check-analysis-tab` | 1 (check) |

### Модалки / оверлеи

| классы | # шаблонов |
|---|---:|
| `dm-auth-modal` (+ register wall) | 1 partial, include из base |
| `earn-modal*` | 1 |
| drop overlays: `home-zone-drop-overlay*` | 2 (format_v2, index) |
| `asg-drop-overlay*` / `hz-drop-overlay*` / `tt-drop-overlay*` | 1 каждый |
| `adm-ledger-overlay` | 1 |

### Алерты / статусы

| классы | # шаблонов |
|---|---:|
| `auth-error` | 3 |
| `req-status` | 3 |
| `format-status`, `status`, `req-chat-status` | 2 |
| `adm-status` | 2 |
| page-specific (`asg-page-error`, `hz-error*`, `earn-status`, `pricing-status`, `v2-notices-*`, `ws-toast`, …) | 1 |

### Бейджи / пиллы / чипы

| классы | # шаблонов |
|---|---:|
| `coin-pill` (+ label) | 2 (base, workspace) |
| `preset-chip` | 2 (format_v2, index) |
| `nav-discount-badge` | 1 (base) |
| `ws-chip*`, `ws-pill*`, `acct-badge*`, `earn-badge-free`, `earn-tag*`, `pricing-plan-badge`, `hz-stage` | 1 |

### Таблицы

| классы | # шаблонов |
|---|---:|
| `adm-table*` | 2 |
| `tt-table*` | 1 (turnitin) |
| `earn-ref-history-table` (в CSS; разметка earn) | 1 |

### Тултипы / хинты

| классы | # шаблонов |
|---|---:|
| `card-hint` | 2 |
| `tt-tooltip-trigger` | 1 |
| `field-hint`, `acct-hint`, `earn-tip`, `v2-style-hint`, `v2-drop-placeholder-hint`, `info-tip-*` | 1 |

**Вывод по компонентам:** визуальный язык похож (slate/blue, пиллы, soft cards), но **переиспользуемых shared-классов мало** — каждая фича копирует свои `*-btn` / `*-card` / `*-modal`.

---

## 8. CSS/UI библиотеки

| библиотека | используется? |
|---|---|
| Bootstrap | нет |
| Tailwind | нет |
| Font Awesome / icon packs | нет (SVG inline / CSS) |
| Bulma / MUI / Chakra / Ant | нет |
| Normalize/Reset пакеты | нет отдельным файлом |

Стек: **custom CSS**, токены в `:root`, Google Fonts **Inter** на части страниц.  
Слово «material» встречается только в тексте контента (terms/assignment/turnitin tooltip), не как UI-kit.

---

## 9. Тёмная / светлая тема

| механизм | статус |
|---|---|
| `prefers-color-scheme` | **не используется** (0 совпадений) |
| `data-theme="light|dark"` на `<html>` | **да** |
| переключатель | **да**: в `base.html` — `.theme-toggle`, `.nav-theme-option[data-theme-set]`, иконки sun/moon |
| persistence | `localStorage.getItem("theme")` в `base.html` (inline script до paint) |
| покрытие dark | сильное в `style.css`; доп. overrides в `earn.css`, `admin.css`, `tour.css` |
| feature CSS | `workspace.css` / `humanizer.css` опираются на свои `--ws-*` / `--hz-*`; dark зависит от того, переопределяют ли они `[data-theme="dark"]` (частично/локально) |
| `color-scheme` | задаётся в токенах (`color-scheme: light` / dark в theme blocks) |

Итого: **ручной light/dark toggle**, без автоследования системной теме.

---

## Краткие выводы для дизайна

1. Один тяжёлый глобальный файл (`style.css`) + 5 feature CSS + **1 мёртвый** `tour.css`.  
2. Токены есть, но параллельно три неймспейса (`--`, `--ws-*`, `--hz-*`) и много hardcoded hex.  
3. Компоненты **не унифицированы** по классам — много одностраничных дублей.  
4. Typography: Inter + очень мелкая дробная rem-шкала.  
5. Тема: manual `data-theme`, без `prefers-color-scheme`.  
6. Библиотек UI нет; стили полностью самописные.
