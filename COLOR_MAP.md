# COLOR_MAP

Соответствие старых цветов → токены `static/tokens.css`.

- Источник: `static/*.css` (кроме `tokens.css`, `components.css`) + inline в `templates/`.
- Частоты сверены с `DESIGN_AUDIT_2_CSS.md` §3.
- Уверенность **низкая**, если: count < 3; цвет сопоставимо используется и как фон, и как текст; нет категории.

## 1. Hex → токен

| старое значение | где встречается (файлы) | сколько раз | новый токен | уверенность |
|---|---|---:|---|---|
| `#ffffff` | admin.css, earn.css, humanizer.css, style.css, tools.css, tour.css, tpl:format_v2.html, workspace.css | 50 | `--surface-1 / --text-inverse / --btn-primary-text` — часто и фон, и текст на primary; dual bg+text | низкая |
| `#2563eb` | admin.css, earn.css, style.css, tools.css, tour.css | 18 | `--accent` — и кнопка, и текст/бордер; dual bg+text | низкая |
| `#94a3b8` | earn.css, humanizer.css, style.css, tour.css | 17 | `--text-muted` | высокая |
| `#b91c1c` | admin.css, earn.css, humanizer.css, style.css, tools.css | 17 | `--danger-text` | высокая |
| `#047857` | admin.css, earn.css, style.css | 16 | `--success-text` | средняя |
| `#64748b` | earn.css, humanizer.css, style.css, tour.css | 15 | `--text-secondary` | высокая |
| `#0f172a` | earn.css, style.css, tools.css, tour.css | 14 | `--text` — изредка фон; dual bg+text | низкая |
| `#e2e8f0` | admin.css, earn.css, style.css, tools.css, tour.css | 14 | `--border` | высокая |
| `#f1f5f9` | admin.css, earn.css, style.css | 14 | `--surface-2` | высокая |
| `#f8fafc` | admin.css, earn.css, style.css, tools.css, tour.css | 12 | `--bg` — slate-50 | высокая |
| `#fafbfd` | style.css | 10 | `--bg` — фон chrome | высокая |
| `#059669` | earn.css, humanizer.css, style.css, tools.css | 9 | `--success` — emerald ≈ success; dual bg+text | низкая |
| `#d97706` | style.css, workspace.css | 9 | `--warn` | высокая |
| `#b45309` | admin.css, style.css, tools.css | 8 | `--warn` | высокая |
| `#cbd5e1` | admin.css, earn.css, style.css, tools.css, tour.css, workspace.css | 8 | `--border-strong` — dual bg+text | низкая |
| `#dc2626` | style.css, tools.css | 8 | `--danger` — dual bg+text | низкая |
| `#0f766e` | admin.css, style.css, tools.css | 7 | `--success` | средняя |
| `#16a34a` | humanizer.css, tools.css | 7 | `--success` | высокая |
| `#1e293b` | earn.css, style.css, tools.css, tour.css | 6 | `--text` — иногда фон; dual bg+text | низкая |
| `#234977` | style.css | 6 | `--accent-text` — navy brand | средняя |
| `#334155` | earn.css, tools.css, tour.css | 6 | `--text-secondary` | высокая |
| `#ecfdf5` | admin.css, earn.css, style.css | 6 | `--success-soft` | высокая |
| `#eff6ff` | admin.css, earn.css, style.css | 6 | `--accent-soft` | высокая |
| `#f59e0b` | tour.css, workspace.css | 6 | `--warn` | высокая |
| `#fef2f2` | admin.css, style.css | 6 | `--danger-soft` | высокая |
| `#000000` | style.css, tpl:format_v2.html | 5 | `—` — только тени/оверлеи | низкая |
| `#111827` | style.css, workspace.css | 5 | `--text` | высокая |
| `#a78bfa` | workspace.css | 5 | `--ai` / `--ai-border` | низкая |
| `#c4b5fd` | style.css, workspace.css | 5 | `--ai-text` / `--ai-border` | низкая |
| `#fecaca` | admin.css, style.css | 5 | `--danger-border` | высокая |
| `#fffbeb` | admin.css, style.css, workspace.css | 5 | `--warn-soft` | высокая |
| `#15803d` | admin.css, style.css, tools.css | 4 | `--success` | высокая |
| `#1d4ed8` | admin.css, earn.css, tools.css, tour.css | 4 | `--accent-hover / --accent-text` — dual bg+text | низкая |
| `#93c5fd` | admin.css, earn.css, humanizer.css, tools.css | 4 | `--accent-border` | средняя |
| `#34d399` | workspace.css | 3 | `--success-border` | средняя |
| `#3b82f6` | tools.css | 3 | `--accent (dark theme value)` | средняя |
| `#475569` | earn.css, tour.css | 3 | `--text-secondary` | высокая |
| `#86efac` | style.css, tools.css | 3 | `--success-border` | низкая |
| `#a7f3d0` | admin.css, humanizer.css, style.css | 3 | `--success-border` | низкая |
| `#c8cdd3` | style.css | 3 | `--border-strong` | низкая |
| `#f87171` | workspace.css | 3 | `--danger (dark)` | средняя |
| `#fee2e2` | admin.css, style.css | 3 | `--danger-soft` | средняя |
| `#166534` | tools.css | 2 | `--success-text` | низкая |
| `#1a1a1a` | tpl:format_v2.html | 2 | `--surface-1 (dark) / --text` | низкая |
| `#2f6fed` | tpl:format_v2.html | 2 | `--accent` | низкая |
| `#6ee7b7` | earn.css, workspace.css | 2 | `--success-border` | низкая |
| `#8a8a8a` | tpl:format_v2.html | 2 | `--text-muted` | низкая |
| `#bfdbfe` | style.css | 2 | `--accent-border` | низкая |
| `#d5dae0` | style.css | 2 | `--border-strong` | низкая |
| `#e2a100` | tpl:format_v2.html | 2 | `--warn` | низкая |
| `#eef2f7` | admin.css | 2 | `--surface-2 / --surface-3` | низкая |
| `#f3f6fb` | style.css | 2 | `--surface-2` | низкая |
| `#f9fafc` | style.css | 2 | `--bg / --surface-2` | низкая |
| `#fbbf24` | workspace.css | 2 | `--warn` | низкая |
| `#fca5a5` | style.css, workspace.css | 2 | `--danger-border` | низкая |
| `#fde68a` | style.css | 2 | `--warn-border` | низкая |
| `#fef3c7` | style.css | 2 | `--warn-soft` | низкая |
| `#0b0d10` | style.css | 1 | `--text / --bg (dark)` | низкая |
| `#111111` | style.css | 1 | `--text / --btn-primary-bg` | низкая |
| `#121417` | style.css | 1 | `--text` | низкая |
| `#22c55e` | style.css | 1 | `--success` | низкая |
| `#38bdf8` | workspace.css | 1 | `--accent` | низкая |
| `#4338ca` | style.css | 1 | `--ai-text` | низкая |
| `#555555` | tpl:format_v2.html | 1 | `--text-secondary` | низкая |
| `#5b21b6` | style.css | 1 | `--ai-text` | низкая |
| `#6b5a2e` | workspace.css | 1 | `--warn-text` | низкая |
| `#8a5a00` | tpl:format_v2.html | 1 | `--warn-text` | низкая |
| `#8b949e` | style.css | 1 | `--text-muted` | низкая |
| `#92400e` | tools.css | 1 | `--warn-text` | низкая |
| `#9aa3ad` | style.css | 1 | `--text-muted` | низкая |
| `#a23a2d` | tpl:format_v2.html | 1 | `--danger-text` | низкая |
| `#b42318` | style.css | 1 | `--danger-text` | низкая |
| `#bbf7d0` | style.css | 1 | `--success-border` | низкая |
| `#d1fae5` | style.css | 1 | `--success-soft` | низкая |
| `#dbeafe` | style.css | 1 | `--accent-soft` | низкая |
| `#dcfce7` | style.css | 1 | `--success-soft` | низкая |
| `#e0e7ff` | style.css | 1 | `--ai-soft` | низкая |
| `#e5e7eb` | style.css | 1 | `--border` | низкая |
| `#e5eaf3` | workspace.css | 1 | `--surface-3 / --border` | низкая |
| `#e7eeff` | workspace.css | 1 | `--accent-soft` | низкая |
| `#e8ecf2` | admin.css | 1 | `--surface-3 / --border` | низкая |
| `#e8edf5` | style.css | 1 | `--surface-3` | низкая |
| `#e9d5ff` | workspace.css | 1 | `--ai-soft` | низкая |
| `#ea580c` | tools.css | 1 | `--warn` | низкая |
| `#eef2f8` | workspace.css | 1 | `--surface-2` | низкая |
| `#f0fdf4` | style.css | 1 | `--success-soft` | низкая |
| `#f0fdfa` | admin.css | 1 | `--success-soft` | низкая |
| `#f1f4f8` | workspace.css | 1 | `--surface-2` | низкая |
| `#f3f4f6` | workspace.css | 1 | `--surface-2` | низкая |
| `#f5f3ff` | style.css | 1 | `--ai-soft` | низкая |
| `#f5f8ff` | workspace.css | 1 | `--accent-soft` | низкая |
| `#f8fbff` | style.css | 1 | `--accent-soft` | низкая |
| `#faf5ff` | workspace.css | 1 | `--ai-soft` | низкая |
| `#ffeeee` | tools.css | 1 | `--danger-soft` | низкая |

## 2. rgba/rgb → токен

| старое значение | где встречается (файлы) | сколько раз | новый токен | уверенность |
|---|---|---:|---|---|
| `rgba(15,23,42,0.04)` | admin.css, earn.css, style.css, tools.css | 4 | `--shadow-1` — мягкая тень | средняя |
| `rgba(15,23,42,0.06)` | style.css, tools.css | 4 | `--shadow-1` — мягкая тень | средняя |
| `rgba(0,0,0,0.04)` | style.css | 3 | `--shadow-1` | средняя |
| `rgba(15,23,42,0.55)` | style.css, workspace.css | 3 | `--overlay` | средняя |
| `rgba(37,99,235,0.12)` | admin.css, earn.css, workspace.css | 3 | `--accent (+ alpha) / focus` | средняя |
| `rgba(37,99,235,0.35)` | style.css, tools.css | 3 | `--accent (+ alpha) / focus` | средняя |
| `rgba(0,0,0,0.06)` | style.css | 2 | `--shadow-1` | низкая |
| `rgba(0,0,0,0.35)` | style.css | 2 | `--overlay` | низкая |
| `rgba(15,23,42,0.08)` | style.css, tools.css | 2 | `--shadow-1` — мягкая тень | низкая |
| `rgba(15,23,42,0.35)` | admin.css, style.css | 2 | `--overlay` | низкая |
| `rgba(15,23,42,0.45)` | earn.css, tour.css | 2 | `--overlay` | низкая |
| `rgba(255,255,255,0.06)` | style.css, tools.css | 2 | `--text-inverse (+ alpha)` | низкая |
| `rgba(0,0,0,0.08)` | style.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(0,0,0,0.2)` | workspace.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(0,0,0,0.28)` | style.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(0,0,0,0.3)` | workspace.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(0,0,0,0.45)` | style.css | 1 | `--overlay` | низкая |
| `rgba(0,0,0,0.55)` | tour.css | 1 | `--overlay` | низкая |
| `rgba(15,23,42,0.03)` | tools.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(15,23,42,0.15)` | admin.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(15,23,42,0.18)` | earn.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(15,23,42,0.22)` | style.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(15,23,42,0.32)` | tour.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(15,23,42,0.5)` | tour.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(16,24,40,0.1)` | workspace.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(217,119,6,0.25)` | workspace.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(255,255,255,0.08)` | style.css | 1 | `--text-inverse (+ alpha)` | низкая |
| `rgba(255,255,255,0.14)` | style.css | 1 | `--text-inverse (+ alpha)` | низкая |
| `rgba(255,255,255,0.28)` | style.css | 1 | `--text-inverse (+ alpha)` | низкая |
| `rgba(37,99,235,0.15)` | earn.css | 1 | `--accent (+ alpha) / focus` | низкая |
| `rgba(37,99,235,0.25)` | style.css | 1 | `--accent (+ alpha) / focus` | низкая |
| `rgba(37,99,235,0.9)` | workspace.css | 1 | `--accent (+ alpha) / focus` | низкая |
| `rgba(59,130,246,0.15)` | tools.css | 1 | `—` — alpha — вручную | низкая |
| `rgba(59,130,246,0.35)` | tools.css | 1 | `—` — alpha — вручную | низкая |

## 3. hsl/hsla → токен

В основном старый `:root` / `[data-theme]` в `style.css`.

| старое значение | где встречается (файлы) | сколько раз | новый токен | уверенность |
|---|---|---:|---|---|
| `hsl(300 0% 4%)` | style.css | 4 | `--bg (dark)` | средняя |
| `hsl(300 50% 100%)` | style.css | 2 | `--bg / --surface-1` | низкая |
| `hsl(0 0% 100%)` | style.css | 1 | `--surface-1` | низкая |
| `hsl(0 0% 28%)` | style.css | 1 | `--border-strong (dark)` | низкая |
| `hsl(0 0% 50%)` | style.css | 1 | `--text-muted` | низкая |
| `hsl(0 0% 9%)` | style.css | 1 | `--surface-1 (dark)` | низкая |
| `hsl(0 0% 90%)` | style.css | 1 | `--surface-3 / --border` | низкая |
| `hsl(0 0% 98%)` | style.css | 1 | `--bg` | низкая |
| `hsl(146 17% 59%)` | style.css | 1 | `--success (dark)` | низкая |
| `hsl(147 19% 36%)` | style.css | 1 | `--success` | низкая |
| `hsl(208 74% 28%)` | style.css | 1 | `--accent` | низкая |
| `hsl(217 22% 41%)` | style.css | 1 | `--accent-text` | низкая |
| `hsl(217 28% 65%)` | style.css | 1 | `--accent (dark)` | низкая |
| `hsl(300 0% 18%)` | style.css | 1 | `--border (dark)` | низкая |
| `hsl(300 0% 95%)` | style.css | 1 | `--surface-2` | низкая |
| `hsl(330 0% 39%)` | style.css | 1 | `--text-muted (dark)` | низкая |
| `hsl(336 0% 1%)` | style.css | 1 | `--bg (dark)` | низкая |
| `hsl(340 0% 62%)` | style.css | 1 | `--text-secondary` | низкая |
| `hsl(38 100% 17%)` | style.css | 1 | `— (старый highlight)` | низкая |
| `hsl(52 19% 57%)` | style.css | 1 | `--warn (dark)` | низкая |
| `hsl(52 23% 34%)` | style.css | 1 | `--warn` | низкая |
| `hsl(9 21% 41%)` | style.css | 1 | `--danger` | низкая |
| `hsl(9 26% 64%)` | style.css | 1 | `--danger (dark)` | низкая |

## 4. Без токена — что добавить в `tokens.css`

| старое значение | файлы | сколько раз | почему | предложить |
|---|---|---:|---|---|
| `#000000` | style.css, tpl:format_v2.html | 5 | не заливка UI, только shadow/overlay | уже `--shadow-*` / `--overlay` |

> Violet/AI (`#a78bfa`, `#c4b5fd`, `#5b21b6`, …) и soft (`#e0e7ff`, `#f5f3ff`, …) закрыты токенами `--ai*`. Sky `#38bdf8` → `--accent`. Teal `#047857` / `#0f766e` / `#f0fdfa` → `--success*`. Отдельные `--info` / `--teal` **не** добавляем.

### Почти подходит — стоит расширить палитру

| старое | сейчас | проблема | предложение |
|---|---|---|---|
| `#fafbfd` | `--bg` | чуть холоднее `#FAFAF9` | ок как `--bg`, опционально `--bg-subtle` |
| `#234977` | `--accent-text` | navy ≠ `#1D4ED8` | принять как brand / `--accent-text` |

### Добавлено в `tokens.css` (`--ai*`)

```css
/* light */
--ai:        #7C3AED;
--ai-text:   #5B21B6;
--ai-soft:   #F4F1FE;
--ai-border: #C9BAF8;

/* dark */
--ai:        #A78BFA;
--ai-text:   #C4B5FD;
--ai-soft:   #241B3D;
--ai-border: #4A3A78;
```

## 5. `oklch()` — разобрать вручную

> Эти значения **надо разобрать вручную**. Почти все — старые токены в `style.css` `:root`.

| значение | файлы | сколько раз |
|---|---|---:|
| `oklch(0 0 0)` | style.css | 2 |
| `oklch(1 0 250)` | style.css | 2 |
| `oklch(0.1 0 250)` | style.css | 1 |
| `oklch(0.15 0 250)` | style.css | 1 |
| `oklch(0.2 0 250)` | style.css | 1 |
| `oklch(0.3 0 250)` | style.css | 1 |
| `oklch(0.4 0 250)` | style.css | 1 |
| `oklch(0.4 0.1 250)` | style.css | 1 |
| `oklch(0.4 0.1 70)` | style.css | 1 |
| `oklch(0.5 0 250)` | style.css | 1 |
| `oklch(0.5 0.05 100)` | style.css | 1 |
| `oklch(0.5 0.05 160)` | style.css | 1 |
| `oklch(0.5 0.05 260)` | style.css | 1 |
| `oklch(0.5 0.05 30)` | style.css | 1 |
| `oklch(0.6 0 250)` | style.css | 1 |
| `oklch(0.7 0 250)` | style.css | 1 |
| `oklch(0.7 0.05 100)` | style.css | 1 |
| `oklch(0.7 0.05 160)` | style.css | 1 |
| `oklch(0.7 0.05 260)` | style.css | 1 |
| `oklch(0.7 0.05 30)` | style.css | 1 |
| `oklch(0.92 0 250)` | style.css | 1 |
| `oklch(0.96 0 250)` | style.css | 1 |

Черновик (проверить в `style.css`): светлые `oklch(0.92…1 …)` → `--bg`/`--surface-*`; нейтрали `oklch(0.1…0.6 0 250)` → `--text*`/`--border*`; `oklch(0.5|0.7 0.05 30/100/160/260)` → `--danger`/`--warn`/`--success`/`--info`; `oklch(0 0 0)` → тени / primary button.

## 6. `color-mix()` — разобрать вручную

> Эти значения **надо разобрать вручную**. После замены баз (`--primary`→`--accent`, `--border-muted`→`--border`, …) многие mix станут `--*-soft` или `--shadow-*`.

| значение | файлы | сколько раз |
|---|---|---:|
| `color-mix(in srgb, var(--primary)` | admin.css, humanizer.css, style.css, templates/format_v2.html, tools.css | 38 |
| `color-mix(in srgb, var(--border-muted)` | admin.css, earn.css, style.css | 18 |
| `color-mix(in srgb, var(--ws-primary)` | workspace.css | 10 |
| `color-mix(in srgb, var(--text)` | style.css, templates/format_v2.html | 6 |
| `color-mix(in srgb, var(--danger)` | style.css | 4 |
| `color-mix(in srgb, var(--success)` | style.css | 4 |
| `color-mix(in srgb, var(--warning)` | tools.css | 4 |
| `color-mix(in srgb, #234977 68%, #94a3b8)` | style.css | 2 |
| `color-mix(in srgb, #a78bfa 28%, transparent)` | workspace.css | 2 |
| `color-mix(in srgb, #ffffff 62%, #64748b)` | style.css | 2 |
| `color-mix(in srgb, var(--accent)` | templates/format_v2.html | 2 |
| `color-mix(in srgb, var(--accent, #0f766e)` | tools.css | 2 |
| `color-mix(in srgb, var(--bg)` | earn.css, tools.css | 2 |
| `color-mix(in srgb, var(--bg-dark)` | style.css, tools.css | 2 |
| `color-mix(in srgb, var(--bg-light)` | style.css, tools.css | 2 |
| `color-mix(in srgb, var(--hz-primary)` | humanizer.css | 2 |
| `color-mix(in srgb, var(--info)` | tools.css | 2 |
| `color-mix(in srgb, var(--ws-amber)` | workspace.css | 2 |
| `color-mix(in srgb, var(--ws-muted)` | workspace.css | 2 |
| `color-mix(in srgb, var(--ws-surface)` | workspace.css | 2 |
| `color-mix(in srgb, var(--ws-text)` | workspace.css | 2 |
| `color-mix(in srgb, var(--ws-violet)` | workspace.css | 2 |
| `color-mix(in srgb, #000 8%, transparent)` | templates/format_v2.html | 1 |
| `color-mix(in srgb, #059669 18%, transparent)` | earn.css | 1 |
| `color-mix(in srgb, #22c55e 22%, transparent)` | style.css | 1 |
| `color-mix(in srgb, #2563eb 16%, transparent)` | tour.css | 1 |
| `color-mix(in srgb, #2563eb 8%, #fff)` | tour.css | 1 |
| `color-mix(in srgb, #34d399 28%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #34d399 32%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #34d399 45%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #38bdf8 48%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #3b82f6 18%, var(--bg-light)` | tools.css | 1 |
| `color-mix(in srgb, #555 55%, var(--text, #1a1a1a)` | templates/format_v2.html | 1 |
| `color-mix(in srgb, #8a5a00 70%, var(--text, #1a1a1a)` | templates/format_v2.html | 1 |
| `color-mix(in srgb, #8a8a8a 12%, transparent)` | templates/format_v2.html | 1 |
| `color-mix(in srgb, #8a8a8a 28%, transparent)` | templates/format_v2.html | 1 |
| `color-mix(in srgb, #a78bfa 38%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #a78bfa 52%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #c4b5fd 65%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #e2a100 16%, transparent)` | templates/format_v2.html | 1 |
| `color-mix(in srgb, #e2a100 40%, transparent)` | templates/format_v2.html | 1 |
| `color-mix(in srgb, #f59e0b 30%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #f59e0b 44%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #f87171 28%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #f87171 32%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #f87171 50%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, #fbbf24 70%, transparent)` | workspace.css | 1 |
| `color-mix(in srgb, var(--accent, #2f6fed)` | templates/format_v2.html | 1 |
| `color-mix(in srgb, var(--hz-card)` | humanizer.css | 1 |
| `color-mix(in srgb, var(--secondary)` | workspace.css | 1 |
| `color-mix(in srgb, var(--surface)` | style.css | 1 |
| `color-mix(in srgb, var(--text-muted)` | style.css | 1 |

## 7. Шпаргалка

| роль | старые hex | новый токен |
|---|---|---|
| фон страницы | `#f8fafc`, `#fafbfd` | `--bg` |
| карточка | `#ffffff` | `--surface-1` |
| вложенный блок | `#f1f5f9` | `--surface-2` |
| hover | mix / `#e2e8f0` как заливка | `--surface-3` |
| инпут | светлые slate / mix | `--surface-inset` |
| граница | `#e2e8f0`, `#cbd5e1` | `--border`, `--border-strong` |
| текст | `#0f172a`, `#111827` | `--text` |
| подпись | `#64748b`, `#334155` | `--text-secondary` |
| muted | `#94a3b8` | `--text-muted` |
| акцент | `#2563eb`, `#1d4ed8`, `#eff6ff` | `--accent`, `--accent-hover`/`--accent-text`, `--accent-soft` |
| warn | `#d97706`, `#b45309`, `#fffbeb` | `--warn*` |
| danger | `#dc2626`, `#b91c1c`, `#fef2f2` | `--danger*` |
| success | `#15803d`, `#16a34a`, `#ecfdf5`, `#047857`, `#0f766e` | `--success*` |
| AI violet | `#a78bfa`, `#c4b5fd`, `#5b21b6`, `#e0e7ff` | `--ai`, `--ai-text`, `--ai-border`, `--ai-soft` |
