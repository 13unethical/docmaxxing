# DESIGN_AUDIT_1_PAGES

Аудит шаблонов `templates/` и их связи с Flask-роутами через `render_template()` (только `app.py`).  
Дата среза: 2026-08-13. Код не менялся.

Легенда доступа:

- **публичная** — без `@login_required` / `@email_verified_required` / `@admin_required`
- **залогиненные** — `@economy_auth.login_required`
- **залогиненные + verified email** — `@economy_auth.email_verified_required` (редирект на логин/verify, если нет)
- **admin** — `@economy_auth.admin_required`

| путь к шаблону | какой роут(ы) его рендерит | extends/include какие шаблоны | 1 фраза: что это за страница | публичная / только для залогиненных |
|---|---|---|---|---|
| `templates/base.html` | — (base) | include: `_site_footer.html`, `_register_wall.html` | Корневой layout сайта (shell, nav, footer). | партиал/base |
| `templates/tools_base.html` | — (base) | extends: `base.html` | Layout для tool-страниц (humanizer, assignment, turnitin, workspace). | партиал/base |
| `templates/workspace_base.html` | — (не используется) | include: `_site_footer.html`, `_register_wall.html` | Отдельный старый/альтернативный layout workspace (standalone HTML). | партиал/base (мёртвый) |
| `templates/info/base.html` | — (base) | extends: `base.html`; include: `info/_toc.html` | Layout info-hub (TOC + карточка политики/справки). | партиал/base |
| `templates/info/_toc.html` | — (partial) | — | Боковое оглавление info-страниц. | партиал |
| `templates/_site_footer.html` | — (partial) | — | Общий футер сайта. | партиал |
| `templates/_register_wall.html` | — (partial) | — | Модалка/стена регистрации для гостей. | партиал |
| `templates/_tutorial_btn.html` | — (не include’ится) | — | Переиспользуемая кнопка Tutorial (документирована в комментарии). | партиал (мёртвый) |
| `templates/index.html` | `GET /` (`index`) — только если `FORMATTER_V2_ENABLED` выключен | extends: `base.html` | Legacy Format UI (V1). | публичная |
| `templates/format_v2.html` | `GET /` (`index`) при V2; `GET /format-v2` (`format_v2_page`) | extends: `base.html` | Formatter V2: загрузка, стили, smartform, chat. | публичная |
| `templates/check.html` | — (не рендерится; `/check` → `soon.html`) | extends: `base.html` | Academic Check — сверка документа с брифом. | мёртвый page-шаблон |
| `templates/soon.html` | `GET /check` (`check`); `GET /presentation` (`presentation`) | extends: `base.html` | Заглушка «SOON…» для отключённых разделов. | публичная |
| `templates/workspace.html` | `GET /workspace` (`workspace`) | extends: `tools_base.html` | Document workspace: редактор, humanize, cite, comments. | залогиненные + verified email |
| `templates/editor.html` | — (не рендерится; `/editor` → redirect `/workspace`) | extends: `tools_base.html` | Legacy TipTap editor placeholder (Phase 2). | мёртвый page-шаблон |
| `templates/humanizer.html` | `GET /humanizer` (`humanizer`) | extends: `tools_base.html` | Standalone Humanizer (StealthWriter). | залогиненные + verified email |
| `templates/assignment.html` | `GET /assignment` (`assignment`) | extends: `tools_base.html` | Assignment pipeline UI (brief → write → deliver). | залогиненные + verified email |
| `templates/turnitin.html` | `GET /turnitin` (`turnitin`) | extends: `tools_base.html` | Turnitin / integrity reports UI. | залогиненные + verified email |
| `templates/pricing.html` | `GET /pricing` (`pricing`) | extends: `base.html` | Пакеты монет / checkout. | публичная |
| `templates/earn.html` | `GET /earn` (`earn_share`) | extends: `base.html` | Referral Earn & Share. | залогиненные |
| `templates/login.html` | `GET|POST /login` (`login`) | extends: `base.html` | Вход в аккаунт. | публичная |
| `templates/register.html` | `GET|POST /register` (`register`) | extends: `base.html` | Регистрация. | публичная |
| `templates/verify_email.html` | `GET|POST /verify-email/code`, `/verify-email/notice` (`verify_email_code`) | extends: `base.html` | Подтверждение email (OTP / notice). | залогиненные |
| `templates/account.html` | `GET|POST /account` (`account`) | extends: `base.html` | Настройки профиля и пароля. | залогиненные |
| `templates/admin.html` | `GET /admin` (`admin_panel`) | extends: `base.html` | Админка: пользователи, лимиты, аналитика. | admin |
| `templates/admin_dataset_stats.html` | `GET /admin/dataset-stats` (`admin_dataset_stats_page`) | extends: `base.html` | Админ-статистика ML dataset. | admin |
| `templates/legal.html` | — (не рендерится; `/legal*` → redirect на info-страницы) | extends: `base.html` | Старый монолит legal/about/FAQ/changelog. | мёртвый page-шаблон |
| `templates/info/account.html` | `GET /account-info` (`account_info`) | extends: `info/base.html` | Info: аккаунт / как устроен кабинет. | публичная |
| `templates/info/credits.html` | `GET /credits` (`credits`) | extends: `info/base.html` | Info: что такое кредиты. | публичная |
| `templates/info/about.html` | `GET /about` (`about`) | extends: `info/base.html` | Info: About Us. | публичная |
| `templates/info/privacy.html` | `GET /privacy` (`privacy`) | extends: `info/base.html` | Info: Privacy Policy. | публичная |
| `templates/info/terms.html` | `GET /terms` (`terms`) | extends: `info/base.html` | Info: Terms of Service. | публичная |
| `templates/info/disclaimer.html` | `GET /disclaimer` (`disclaimer`) | extends: `info/base.html` | Info: Disclaimer. | публичная |
| `templates/info/payment.html` | `GET /payment-policy` (`payment_policy`) | extends: `info/base.html` | Info: Payment Policy. | публичная |
| `templates/info/delivery.html` | `GET /delivery-policy` (`delivery_policy`) | extends: `info/base.html` | Info: Delivery Policy. | публичная |
| `templates/info/refund.html` | `GET /refund-policy` (`refund_policy`) | extends: `info/base.html` | Info: Refund Policy. | публичная |
| `templates/info/contact.html` | `GET /contact` (`contact`) | extends: `info/base.html` | Info: Contact. | публичная |
| `templates/info/faq.html` | `GET /faq` (`faq`) | extends: `info/base.html` | Info: FAQ. | публичная |
| `templates/info/changelog.html` | `GET /changelog` (`changelog`) | extends: `info/base.html` | Info: Changelog. | публичная |

Примечания по роутам:

- `GET /` выбирает `format_v2.html` или `index.html` через `formatter_v2_enabled()`.
- `GET /templates`, `GET /references` → redirect на `/` (шаблоны не рендерят).
- `GET /editor` → redirect на `/workspace`.
- `GET /legal`, `/legal/terms`, `/legal/privacy`, `/legal/refund` → 301 на info-страницы.
- `GET /assignments` → redirect на `/assignment`.
- Единственный Python-файл с `render_template`: `app.py`.

---

## Мёртвые page-шаблоны (ни один роут не вызывает `render_template` на них)

- `templates/check.html` — UI Academic Check сохранён, роут `/check` отдаёт `soon.html`
- `templates/editor.html` — роут `/editor` только redirect на workspace
- `templates/legal.html` — роуты `/legal*` только redirect на info-hub

---

## Base-шаблоны и партиалы (только extends/include, не конечные страницы)

**Активные base / partials:**

- `templates/base.html`
- `templates/tools_base.html`
- `templates/info/base.html`
- `templates/info/_toc.html`
- `templates/_site_footer.html`
- `templates/_register_wall.html`

**Неподключённые base / partials:**

- `templates/workspace_base.html` — никто не делает `extends "workspace_base.html"` (`workspace.html` наследует `tools_base.html`)
- `templates/_tutorial_btn.html` — нет `{% include "_tutorial_btn.html" %}` ни в одном шаблоне

---

## Email-шаблоны

Отдельных Jinja email-шаблонов в `templates/` **нет**.  
HTML письма verification собирается inline в `services/economy/email_verify.py` (`html_body = f"""..."""`), не через `render_template`.
