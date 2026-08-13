# STATES_AUDIT.md

Инвентаризация пустых состояний, нехватки кредитов и ошибок по UI.  
**Код не менялся.** Дата: 2026-08-13.

Цель унификации (референс из дизайна):

1. **Empty** — пунктирный блок: иконка, заголовок, одна строка, CTA (+ бейдж цены), мелкая подпись.
2. **Not enough credits** — предупреждение (не ошибка): нужно / есть, кнопка Top up.
3. **Error** — заголовок, объяснение, Retry; честно про списание кредитов.

---

## A. Пустые состояния

| Страница / зона | Файл(ы) | Как выглядит сейчас | Текст |
|---|---|---|---|
| Sidebar history (Assignment, signed out) | `templates/base.html`, `static/app-shell.js`, `static/style.css` `.app-sidebar-history-empty` | Однострочный `<p>` в сайдбаре | `Sign in to see history.` |
| Sidebar history (Assignment, empty) | то же | то же | `No assignments yet.` |
| Sidebar history (другие tools) | то же | то же | `No history yet.` |
| Sidebar history (ошибка загрузки) | `static/app-shell.js` | то же (как empty) | `Could not load history.` |
| Assignment chat `/assignment` | `templates/assignment.html`, `static/assignment-page.js`, `static/tools.css` `.asg-chat-empty*` | Центрированный empty в чате | **Title:** `Ready when you are` · **Lede:** `Attach your brief and materials to get a price.` |
| Assignment revision chat | `static/tools.css` `.asg-revchat-thread:empty::before` | CSS `::before` | `Chat opens here after delivery. Describe any edits — small wording fixes or larger structural changes.` |
| Turnitin `/turnitin` — нет отчётов | `templates/turnitin.html` `.tt-empty-zero*`, `static/turnitin-page.js` | Пунктирный hero (уже близок к целевому) | `Check your first document` · `Get a similarity report and an AI score — the same checks your university runs.` · CTA `Submit files` + cost · `DOC, DOCX, PDF, or TXT` |
| Turnitin — поиск ничего не нашёл | `templates/turnitin.html` `[data-tt-empty]`, `static/turnitin-page.js` | Текст под таблицей `.tt-table-empty` | `No reports match your search.` |
| Earn `/earn` — рефералы | `templates/earn.html`, `static/earn-page.js`, `static/earn.css` `.earn-refs-empty` | Текст в списке | `No referrals yet. Share your link to get started.` |
| Earn — депозиты реферала | `static/earn-page.js`, `.earn-ref-history-empty` | Мелкий текст под раскрытием | `No deposits yet.` |
| Format v2 — история правок | `templates/format_v2.html`, `static/format_v2.js` | `#v2_chat_history_empty` | `Edits will show up here.` |
| Format v2 — нет файла | `templates/format_v2.html` `.v2-drop-placeholder` | Dropzone placeholder | `Drop a DOCX or paste your text` · `Click to choose a file` |
| Workspace editor | `static/workspace.css` `.ws-page:empty::before` | CSS placeholder | `Start writing…` |
| Workspace comments | `templates/workspace.html`, `static/workspace/workspace-app.js` | `.ws-empty-note` | `No comments yet.` |
| Workspace citations | `static/workspace/workspace-app.js` | `.ws-empty-note` | `No results — try another query.` · `Searching…` · `Create a free account to search citations.` · `Search failed — try again.` · mock: `Showing sample results (search backend offline).` |
| Workspace landing (до документа) | `templates/workspace.html` | Dropzone | `Drop file to insert` · `DOCX — opens in the editor…` |
| Support chat (shell) | `static/support-chat.js`, `static/style.css` `.support-chat-empty` | Empty в панели чата | Signed out: `Sign in to chat with support.` · Signed in: `Send a message — we reply here from Telegram.` |
| Humanizer input | `templates/humanizer.html`, `static/humanizer.css` | `:empty::before` | `Paste your text here...` |
| Check `/check` — до запуска | `templates/check.html`, `static/check.js` | `#check_parser_empty` / `.card-hint` | `Run Check to detect formatting requirements from your brief.` |
| Check — панели результатов | `static/check.js` | `.check-empty-item`, `.structure-empty`, `.card-hint`, `.check-all-clear` | Много вариантов, напр.: `Top issues will appear after analysis.` · `Nothing to show.` · `No citation notes.` · `No action steps — requirements appear met.` · `No critical issues detected.` · `No issues flagged — great work on these checks.` (и др.) |
| Home / Format preview | `static/preview.js` | `.preview-diff-empty` | `Updating preview…` · `Adjust settings to see highlighted changes.` |
| Editor | `templates/editor.html`, `static/tools.css` | `:empty::before` / `data-placeholder` | `Start writing or open a draft from Format…` |
| Admin `/admin` | `templates/admin.html`, `static/admin-page.js`, `.adm-empty` | Однострочный empty | `No paid purchases yet.` · `No country data yet (filled from Paddle billing address).` · `No pending withdrawals.` · `No users found.` · `No ledger entries yet.` · `No purchases yet.` · `No usage events yet.` |
| Admin dataset | `templates/admin_dataset_stats.html` | `.adm-muted` в таблице | `No samples yet.` (×2) |
| Account `/account` | `templates/account.html` | — | **Нет empty-list секций** (только профиль/пароль) |
| Login | `templates/login.html` | `.auth-alt` (не empty-state) | `No account yet?` |

### CSS без живой разметки
| Класс | Файл | Заметка |
|---|---|---|
| `.asg-history-panel-empty` | `static/tools.css` | Нет matching markup |
| `.ref-empty-state` | `static/style.css` | Нет matching markup |

---

## B. Нехватка кредитов

| Страница / фича | Файл | Как показывается | Текст |
|---|---|---|---|
| API debit (общий) | `app.py` | JSON `402` | `Not enough credits. This requires {required} credits; you have {balance}.` · `error: INSUFFICIENT_COINS` |
| Assignment pay (API) | `app.py` | JSON `402` | `Not enough coins. This project costs {required}; you have {balance}.` |
| Assignment UI | `static/assignment-page.js` | `.asg-page-error` + bubble через `fail()` | Берёт **`payload.error`**, не `message` → часто голый **`INSUFFICIENT_COINS`** |
| Turnitin submit (server) | `static/turnitin-page.js` | `.tt-submit-status` | Server `message` или `Not enough coins. Buy coins to continue.` |
| Turnitin pre-check (client) | `static/turnitin-page.js` | `.tt-submit-status` | `Not enough coins. Need {needed}, have {credits}.` |
| Humanizer | `static/humanizer-page.js` | `.hz-error` / `.hz-error-panel` | `(message \|\| "Not enough coins.") + " Add coins on the Pricing page."` |
| Workspace Detect AI | `static/workspace/workspace-app.js` | Toast `.ws-toast` | API `message` или `Not enough credits. Top up to continue.` |
| Workspace Humanize | то же | Toast | API `message` или `Not enough credits.` / `… Top up to continue.` |
| Workspace citations | то же | Toast | API `message` или `Not enough credits. This requires 2 credits.` |
| Nav / sidebar | `templates/base.html`, `static/auth-modal.js` | Ссылка Top up (не алерт) | Title `Top up credits` · action `Top up` |
| Wallet (internal) | `services/economy/wallet.py` | Может утечь как `str(exc)` | `Insufficient credits: need {required}, have {balance}` |
| Earn convert | `services/economy/referral.py`, `static/earn-page.js` | `.earn-status` | Client: `No referral balance to convert.` · Server: `Insufficient referral balance. You have $X.` |

**Нет единого warn-компонента** с двумя числами + кнопкой Top up (как в макете).

---

## C. Ошибки (сеть / сервер / внешние сервисы)

### Shell / auth
| Зона | Файл | Тип | Текст |
|---|---|---|---|
| Auth modal | `static/auth-modal.js` | Inline `[data-auth-error]` | `Passwords do not match.` · `Something went wrong. Please try again.` · `Network error. Please try again.` · API `error` |
| Support chat | `static/support-chat.js` | Status | `Please sign in…` · `Could not read server response.` · `Something went wrong.` · `Could not send — check your connection or try again.` |
| Copy | `static/ui.js` | Toast | `Nothing to copy.` · `Could not copy.` |
| Login/register | `app.py` + templates | `.auth-error` | `Incorrect email or password.` · `An account with this email already exists…` · иногда `str(exc)` |

### Format / Home
| Зона | Файл | Тип | Текст |
|---|---|---|---|
| Format (legacy/common) | `static/common.js` | `#format_status` | `Something went wrong.` · `Server error (N).` · `Unexpected response from server.` · `Network error — is the Flask server running on port 5000?` · ошибки extract файла |
| Format v2 | `static/format_v2.js` | Status + chat error | `Timed out after 30s…` · `Could not apply the edit…` · `Network error — is the server running?` · `Could not parse the brief.` · download/profile errors |
| Home uploads | `static/home.js` | Status | `Could not extract text from brief.` · `Could not read file.` · `Request failed.` · `Network or server error.` |

### Humanizer / StealthWriter
| Зона | Файл | Тип | Текст |
|---|---|---|---|
| Humanizer | `static/humanizer-page.js` | `.hz-error` | `Humanizer API not found…` · `Server returned an invalid response (HTTP N).` · `StealthWriter is not logged in on the server…` · `StealthWriter did not rewrite the text (daily limit or same output).` · `payload.message \|\| payload.error \|\| "HTTP N"` |
| Workspace Humanize | `static/workspace/workspace-app.js` | Toast | `StealthWriter login required…` · `StealthWriter returned no change…` · `Humanize failed: …` |
| Workspace Detect | то же | Toast | `Detector unavailable (…) — sample highlights shown.` |

### Turnitin / PlagDetect
| Зона | Файл | Тип | Текст |
|---|---|---|---|
| Submit | `static/turnitin-page.js` | `.tt-submit-status` | `Queued. Checking on PlagDetect…` · `N queued, M failed.` · `Submission failed…` · `Network error. Please try again.` · API `error`/`message` |
| Highlights | то же | Status | `Could not request AI Highlights.` · API `error` (может быть код) |
| Backend → UI | `services/browser/providers/plagdetect.py` | JSON | `Timed out waiting for PlagDetect results.` · `PlagDetect session is not logged in…` · `LOGIN_REQUIRED` · `STALE_PAGE` + Playwright message (напр. browser closed) |

### Assignment
| Зона | Файл | Тип | Текст |
|---|---|---|---|
| Generic | `static/assignment-page.js` | Alert + bubble | `Something went wrong. Please try again.` или `err.message` |
| Network / timeout | то же | Thrown → `fail()` | `This AI step timed out. Please click Retry.` · `Network error. Please check your connection and retry.` · `This AI step can take a few minutes…` (504) · `Server error (N)…` |
| Domain | то же | Thrown | `Attach at least one file…` · `Payment could not be confirmed…` · `* took too long…` · `Writing stalled…` |
| Soft validation | то же | **Без UI** | Soft-fail не через `showError` |

### Check / Pricing / Earn / Account / Admin
| Зона | Файл | Тип | Текст |
|---|---|---|---|
| Check | `static/check.js` | Status | `Check failed.` · `Invalid server response.` · `Network error. Please try again.` |
| Pricing | `static/pricing.js` | Status | `Could not open checkout…` · `Checkout failed…` · `Network error. Please try again.` · config/auth messages |
| Earn | `static/earn-page.js` | Status | `Could not load referral data.` · `Network error.` · `Conversion failed.` · `Withdrawal failed.` |
| Account avatar | `templates/account.html` | Inline | `Upload failed` · `Save failed` |
| Admin | `static/admin-page.js` | Status lines | `Failed to load …` · `Network error…` · `Could not set balance.` и т.д. |

---

## D. Проблемные места (техническое / пусто / тишина)

| Место | В чём проблема |
|---|---|
| `static/assignment-page.js` — обработка 402 | Показывает **`INSUFFICIENT_COINS`** вместо `message` с числами |
| `static/turnitin-page.js` — highlights fail | Может показать голый **`LOGIN_REQUIRED`** / machine code |
| `static/humanizer-page.js` | Fallback `payload.error` или `HTTP {status}` |
| `static/workspace/workspace-app.js` Detect | Toast может получить сырой `error` code |
| `static/workspace/workspace-app.js` citations `.catch` | Тихий fallback на mock без явной ошибки |
| `static/turnitin-page.js` credit sync / poll `.catch(() => {})` | Тишина; баланс/статус могут устареть |
| Turnitin submit без файлов | `return` **без UI** |
| Turnitin auth cancel на submit | `failCount++` **без текста** |
| Humanizer Humanize с пустым вводом | Только focus, **нет ошибки** |
| Humanizer auth dismiss | Silent `.catch` |
| Support chat poll | Намеренно тихо на transient network |
| Assignment validation soft-fail | Не показывается пользователю |
| Assignment `setStatus` при `autoRunning` | Может **залипнуть** (как «Queued…» при уже Failed) |
| PlagDetect / StealthWriter | Часто `{"error":"LOGIN_REQUIRED"}` **без `message`** → UI показывает код |
| Worker fallback | Literal `LOGIN_REQUIRED` / `NO_CHANGE` |
| Наблюдение с продакшн-UI | После `STALE_PAGE` таблица = Failed, статус сверху всё ещё `Queued. Checking on PlagDetect…` |

---

## Карта готовности к унификации

| Тип | Где уже ближе к макету | Где дальше всего |
|---|---|---|
| Empty | Turnitin zero-state | Sidebar history, Admin `.adm-empty`, Earn one-liners, Check hints, CSS `::before` placeholders |
| Credits | Turnitin/Humanizer/Workspace (есть числа в тексте API) | Assignment (код), везде нет warn-блока + Top up |
| Error | Assignment `fail()` с Retry в чате | Toast-only (workspace), однострочные status, голые коды, silent catches |

---

## Часть 2–3 — сделано (2026-08-13)

### Компоненты
- CSS: `.dm-empty`, `.dm-credits-warn`, `.dm-state-error` (+ compact/sidebar)
- Jinja: `ui.empty_state`, `ui.credits_warn`, `ui.state_error`
- JS: `static/dm-states.js` → `window.dmStates`

### Переведено
| Место | Что |
|---|---|
| `/turnitin` | empty → `dm-empty`; search miss → compact empty; credits → `dm-credits-warn`; errors/STALE_PAGE/highlights/no-file → `dm-state-error` + Retry; сброс залипшего «Queued…» |
| `/humanizer` | credits warn; errors с human copy + detail code; empty input → error |
| `/assignment` | empty → `dm-empty`; `payload.message` вместо голого `INSUFFICIENT_COINS`; credits warn + error panel |
| `/earn` | referrals empty → `dm-empty` |
| Sidebar history | `dm-empty--sidebar` |
| Workspace Detect 402 | человеческий toast с need/have (не полный компонент — toast UX) |

### Оставлено as-is (и почему)
| Место | Почему |
|---|---|
| Admin `.adm-empty` | Операционная таблица; полный empty-hero шумит |
| Check result empties | Десятки панелей «после анализа» — не product empty, а пустые секции отчёта |
| Format/Home/preview placeholders | Dropzones / preview hints, не empty lists |
| Workspace toasts (humanize/citations) | Короткий toast уместнее панелей в узком сайдбаре; copy чуть улучшен только на Detect 402 |
| Support chat empty | Контекстный prompt чата, не empty-list |
| CSS `::before` editor/humanizer | Input placeholders, не state blocks |
| Earn «No deposits yet» | Вложенный micro-empty под строкой |
| Auth/login errors | Отдельный auth UX |
| Pricing/Admin network status lines | Admin tooling; низкий приоритет vs student flows |
| Soft-fail assignment validation | Продуктовое решение пайплайна, не user-facing error |
| Support poll silent | Намеренный anti-noise |

