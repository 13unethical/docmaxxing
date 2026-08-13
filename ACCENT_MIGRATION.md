# Accent migration — navy → bright blue

**Статус:** только анализ. Код не менялся. Ждём подтверждения.

## Целевые значения

| Роль | Светлая | Тёмная |
|------|---------|--------|
| Акцент (действие) | `#2F7FE0` | `#3B8BEE` |
| Наведение | `#1F6BC7` | `#63A5F2` |
| Мягкая заливка | `#E7F0FD` | `#12294A` |
| Граница мягкой заливки | `#BBD6F7` | `#1E4272` |
| Текст (не акцент) | `#111827` | `#EAEEF3` |

## Контекст: два источника правды

Сейчас параллельно живут:

1. **`static/tokens.css`** — уже яркий синий акцент (`#2563EB` / `#3B82F6`), текст почти чёрный (`#141414` / `#F2F2F0`).
2. **`static/style.css`** — **перебивает** `--text` на navy `#234977` и задаёт legacy `--primary` как тёмно-синий `hsl(208 74% 28%)` ≈ navy (в dark `--primary` уже `#ffffff`).

Именно из‑за п.2 заголовки и body-текст на большинстве страниц сейчас navy, а не near-black из токенов.

Близкие navy, попавшие в обзор:

| Значение | Где задано | ≈ |
|----------|------------|---|
| `#234977` | `style.css` `--text`, active top-nav | brand navy |
| `color-mix(#234977 68%, #94a3b8)` | `style.css` `--text-muted` | muted navy |
| `hsl(208 74% 28%)` / `oklch(0.4 0.1 250)` | `style.css` `--primary` (light) | navy CTA |

Уже яркие синие (`#2563EB`, `#1D4ED8`, `#3B82F6`, soft `#E7EFFD` / `#BFD4FA` и т.п.) — это **текущий** акцент действия; их тоже нужно сдвинуть на новые hex (группа «действие»).

---

## Группа A — ДЕЙСТВИЕ

Заменять на новый акцент / hover / soft / soft-border (или токены `--accent*`).

### A1. Токены (источник правды для акцента)

| Файл | Что | Сейчас (light → dark) |
|------|-----|------------------------|
| `static/tokens.css` | `--accent` | `#2563EB` → `#3B82F6` |
| `static/tokens.css` | `--accent-hover` | `#1D4ED8` → `#60A5FA` |
| `static/tokens.css` | `--accent-text` | `#1D4ED8` → `#7CB0FF` |
| `static/tokens.css` | `--accent-soft` | `#E7EFFD` → `#13294D` |
| `static/tokens.css` | `--accent-border` | `#BFD4FA` → `#1F3E70` |

Потребители токенов (менятся сами после обновления токенов, хардкода нет):

| Файл | Селекторы / роль |
|------|------------------|
| `static/tokens.css` | `a`, `:focus-visible`, selection |
| `static/components.css` | `.dm-chip.is-active`, focus chip/input, `.dm-dropzone` active, `.dm-alert--info`, `.dm-badge--accent`, `accent-color` |
| `static/format_v2.css` | активный сегмент, drop-active, overlay, evidence/accent UI |
| `static/style.css` | всё с `var(--accent)` / `--accent-hover` / `--accent-soft` / `--accent-muted` (ссылки, вкладки, FAB-ховеры, auth CTA, support chat primary и т.д.) |

### A2. Hardcoded яркий синий (обновить hex → новые значения)

| Файл | Строки (≈) | Селектор / место | Роль |
|------|------------|------------------|------|
| `static/tour.css` | 21–41, 198–204, 246–247 | tour highlight, primary tour btn | кнопка / фокус / рамка |
| `static/earn.css` | 143, 175, 181, 349, 388–390, 462 | earn primary btn, progress, selected card | кнопка / выбор |
| `static/admin.css` | 521–522, 655–656 | admin info/link chips | ссылка / акцент-бейдж |
| `static/tools.css` | 93, 107, 115, 1807, 2725–2726 | tool accents, `.asg-wizard-progress-item.is-current`, file pill | прогресс / иконка-акцент |
| `templates/_register_wall.html` | 7–8 | SVG logo stroke `#2563eb` | бренд-иконка (действие/бренд) |
| `templates/workspace.html` | 16 | SVG stroke `#2563eb` | иконка инструмента |
| `templates/assignment.html` | 10 | SVG fill `#3b82f6` | декоративная иконка карточки |

### A3. Legacy navy как **действие** (`#234977` / `--primary`)

| Файл | Селектор | Сейчас | Почему «действие» |
|------|----------|--------|-------------------|
| `static/style.css` | `.top-nav .nav-link.is-active` | `background/border: #234977` | активный пункт меню |
| `static/style.css` | `:root` / oklch `--primary` (light) | `hsl(208…)` / `oklch(0.4 0.1 250)` | токен кнопок/фокуса |
| `static/style.css` | `--accent-muted: color-mix(… var(--primary) …)` | soft от primary | мягкая заливка при hover/active |
| `static/style.css` | `.cta` | `background: var(--primary)` | главная кнопка |
| `static/style.css` | `.btn-secondary` | border/color `--primary` | вторичная кнопка (outline) |
| `static/style.css` | `.support-chat-fab` | `background: var(--primary)` | FAB |
| `static/style.css` | `.nav-auth-cta` | `background: var(--primary)` | CTA в nav |
| `static/style.css` | `.acct-btn` | `background: var(--primary)` | кнопка аккаунта |
| `static/style.css` | `.pricing-plan-btn--primary` | `background: var(--primary)` | primary pricing |
| `static/style.css` | `.dm-auth-submit` | `background: var(--primary)` | submit в auth modal |
| `static/style.css` | `.preset-chip:hover` / `.is-active` | border/color `--primary` | выбранный чип |
| `static/style.css` | `.home-layout` drop-zone active | border/bg mix `--primary` | активный drop |
| `static/style.css` | input/textarea focus (legacy), `.acct-field input:focus` | outline/border `--primary` | фокус поля |
| `static/style.css` | `.app-nav-link.is-active` | bg/color mix `--primary` | **активный пункт сайдбара** |
| `static/style.css` | `.check-analysis-tab.is-active`, `.ref-tab.is-active`, `.workspace-tab.is-active`, `.dm-auth-tab.is-active`, `.home-doc-segment-btn.is-active` | accent/primary | активная вкладка / сегмент |
| `static/style.css` | `.info-toc-link.is-active` | `color: var(--primary)` | активный пункт TOC |
| `static/style.css` | `.pricing-plan` highlight / featured border | mix `--primary` | выделенный план (выбор) |

---

## Группа B — ТЕКСТ

Не делать ярко-синими. Светлая → `#111827`, тёмная → `#EAEEF3` (muted — отдельным near-gray, не accent).

### B1. Определения navy-текста

| Файл | Что | Сейчас | Предложение |
|------|-----|--------|-------------|
| `static/style.css` | `--text` (light, ×2: hsl + oklch block) | `#234977` | `#111827` |
| `static/style.css` | `--text-muted` (light, ×2) | `color-mix(#234977 68%, #94a3b8)` | mix от `#111827` (или существующий slate muted) |
| `static/style.css` | `--text` (dark) | `#ffffff` | `#EAEEF3` (по ТЗ) |
| `static/tokens.css` | `--text` light | `#141414` | выровнять на `#111827` |
| `static/tokens.css` | `--text` dark | `#F2F2F0` | выровнять на `#EAEEF3` |

### B2. Потребители `--text` как обычный текст / заголовки

Меняются сами после смены токена (не на акцент):

| Файл | Примеры |
|------|---------|
| `static/style.css` | `body`, `h1–h3`, `.nav-brand`, `.top-nav .nav-link`, `.card-title`, формы, лейблы, pricing titles/amounts, sidebar brand, auth titles/labels, большинство `color: var(--text)` |
| `static/tokens.css` | базовый `body { color: var(--text) }` |
| `static/components.css` | `.dm-card__title`, `.dm-label` (частично secondary), текст кнопок secondary и т.п. |

**Важно:** не трогать эти места отдельно ярким синим — только смена значения `--text`.

### B3. Особый случай — toast

| Файл | Селектор | Сейчас | Заметка |
|------|----------|--------|---------|
| `static/style.css` | `.toast { background: var(--text) }` | заливка цветом текста | После смены `--text` на near-black toast станет near-black — это ок как нейтральный UI, **не** акцент. |

---

## Группа C — СПОРНЫЕ / уточнить

| Место | Сейчас | Вопрос |
|-------|--------|--------|
| `style.css` `.settings-summary-icon { color: var(--primary) }` | navy icon | Акцент иконки в summary **или** нейтральный текст `#111827`? |
| `style.css` `.pricing-plan-badge { color: var(--primary) }` | navy badge text | Акцент (метка «Popular») **или** текст? → склоняюсь к **действию/акценту** |
| `style.css` `.btn-secondary` | outline `--primary` | Явно кнопка → **действие** (уже в A3) |
| Soft `#eff6ff` в `style.css` / `admin.css` / `earn.css` | старый Tailwind blue-50 | Близко к soft-fill; заменить на `#E7F0FD` / `--accent-soft`? |
| `humanizer.css` / `admin.css` `#93c5fd` | светло-голубой | Декор/бордер; обновлять под новую палитру soft или оставить? |
| Logo SVG `#2563eb` в шаблонах | бренд | Менять на `#2F7FE0` вместе с акцентом? |
| Dark `--primary: #ffffff` в `style.css` | inverted CTA | Не navy; при миграции primary-кнопок решить: оставить inverted white **или** перевести на `#3B8BEE` как auth CTA |

---

## Рекомендуемый порядок правок (после подтверждения)

1. Обновить `tokens.css`: `--accent*` + выровнять `--text` на `#111827` / `#EAEEF3`.
2. В `style.css`: `--text` / `--text-muted` ← текст; `--primary` (light) ← новый акцент **или** постепенно увести кнопки на `--accent`.
3. Заменить hardcoded `#234977` в `.top-nav .nav-link.is-active` на `var(--accent)`.
4. Пройти hardcoded `#2563eb` / `#1d4ed8` / soft в `tour`, `earn`, `admin`, `tools`, templates.
5. Не трогать отдельные `color: var(--text)` у заголовков — только токен.

---

## Чего в коде нет (для ясности)

- Отдельных `h1 { color: #234977 }` — заголовки берут цвет через `var(--text)`.
- Navy в `format_v2.css` / `components.css` как hex — только через токены.

---

**Жду подтверждения:** можно ли править по схеме выше, и как закрыть группу C (особенно icon summary, `#eff6ff`, dark primary white vs blue).
