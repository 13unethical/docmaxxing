# DESIGN_AUDIT_3 — JS / DOM Contract

Аудит контракта между JS, HTML и Flask для полного редизайна вёрстки.
**Только чтение.** Этот файл — карта того, что нельзя переименовывать без синхронного обновления JS/Python.

- Дата: 2026-08-13
- JS-файлов: `38`
- Шаблонов: `38`
- Inline `<script>` (без `src`): `7`
- Записей селекторов: `672`

> `$("…")` в `format_v2.js` — хелпер `getElementById`; в `assignment-page.js` / `project-ux.js` — `root.querySelector`.
> Атрибуты вида `data-foo` без `=` в HTML тоже индексируются (boolean attributes).
> Селекторы с `${…}` — dynamic (runtime).

## 1. Селекторы JS → файл → шаблон

### `static/admin-page.js`

Подключается из: `templates/admin.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-adm-admin-toggle]` | closest | создаётся в JS (innerHTML/template), не в templates |
| `[data-adm-balance-form]` | closest | создаётся в JS (innerHTML/template), не в templates |
| `[data-adm-delete]` | closest | создаётся в JS (innerHTML/template), не в templates |
| `[data-adm-ledger]` | closest | создаётся в JS (innerHTML/template), не в templates |
| `[data-adm-purchases]` | closest | создаётся в JS (innerHTML/template), не в templates |
| `[data-adm-usage]` | closest | создаётся в JS (innerHTML/template), не в templates |
| `[data-adm-withdrawal-approve]` | closest | создаётся в JS (innerHTML/template), не в templates |
| `[data-adm-withdrawal-reject]` | closest | создаётся в JS (innerHTML/template), не в templates |
| `[data-adm-analytics-refresh]` | querySelector | `templates/admin.html` |
| `[data-adm-analytics-status]` | querySelector | `templates/admin.html` |
| `[data-adm-auto-enabled]` | querySelector | `templates/admin.html` |
| `[data-adm-auto-min]` | querySelector | `templates/admin.html` |
| `[data-adm-auto-time]` | querySelector | `templates/admin.html` |
| `[data-adm-balance-input]` | querySelector | создаётся в JS (innerHTML/template), не в templates |
| `[data-adm-body]` | querySelector | `templates/admin.html` |
| `[data-adm-dataset-assignment]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-dataset-refresh]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-dataset-standalone]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-dataset-status]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-dataset-total]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-dataset-workspace]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-detector-auto]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-detector-manual]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-detector-total]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-discount-live]` | querySelector | `templates/admin.html` |
| `[data-adm-empty]` | querySelector | `templates/admin.html` |
| `[data-adm-kpi-avg-credits]` | querySelector | `templates/admin.html` |
| `[data-adm-kpi-avg-purchase]` | querySelector | `templates/admin.html` |
| `[data-adm-kpi-feature]` | querySelector | `templates/admin.html` |
| `[data-adm-kpi-revenue]` | querySelector | `templates/admin.html` |
| `[data-adm-kpi-sold]` | querySelector | `templates/admin.html` |
| `[data-adm-kpi-used]` | querySelector | `templates/admin.html` |
| `[data-adm-ledger-balance]` | querySelector | `templates/admin.html` |
| `[data-adm-ledger-body]` | querySelector | `templates/admin.html` |
| `[data-adm-ledger-close]` | querySelector | `templates/admin.html` |
| `[data-adm-ledger-count]` | querySelector | `templates/admin.html` |
| `[data-adm-ledger-empty]` | querySelector | `templates/admin.html` |
| `[data-adm-ledger-overlay]` | querySelector | `templates/admin.html` |
| `[data-adm-ledger-status]` | querySelector | `templates/admin.html` |
| `[data-adm-ledger-subtitle]` | querySelector | `templates/admin.html` |
| `[data-adm-promo-active]` | querySelector | `templates/admin.html` |
| `[data-adm-promo-form]` | querySelector | `templates/admin.html` |
| `[data-adm-promo-limit]` | querySelector | `templates/admin.html` |
| `[data-adm-promo-percent]` | querySelector | `templates/admin.html` |
| `[data-adm-purchases-body]` | querySelector | `templates/admin.html` |
| `[data-adm-purchases-close]` | querySelector | `templates/admin.html` |
| `[data-adm-purchases-count]` | querySelector | `templates/admin.html` |
| `[data-adm-purchases-empty]` | querySelector | `templates/admin.html` |
| `[data-adm-purchases-overlay]` | querySelector | `templates/admin.html` |
| `[data-adm-purchases-status]` | querySelector | `templates/admin.html` |
| `[data-adm-purchases-subtitle]` | querySelector | `templates/admin.html` |
| `[data-adm-search]` | querySelector | `templates/admin.html` |
| `[data-adm-stats]` | querySelector | `templates/admin.html` |
| `[data-adm-status]` | querySelector | `templates/admin.html` |
| `[data-adm-today-date]` | querySelector | `templates/admin.html` |
| `[data-adm-today-humanizer-limit]` | querySelector | `templates/admin.html` |
| `[data-adm-today-humanizer-used]` | querySelector | `templates/admin.html` |
| `[data-adm-today-humanizer]` | querySelector | `templates/admin.html` |
| `[data-adm-today-refresh]` | querySelector | `templates/admin.html` |
| `[data-adm-today-status]` | querySelector | `templates/admin.html` |
| `[data-adm-today-turnitin]` | querySelector | `templates/admin.html` |
| `[data-adm-top-countries-empty]` | querySelector | `templates/admin.html` |
| `[data-adm-top-countries]` | querySelector | `templates/admin.html` |
| `[data-adm-top-customers-empty]` | querySelector | `templates/admin.html` |
| `[data-adm-top-customers]` | querySelector | `templates/admin.html` |
| `[data-adm-total-users]` | querySelector | `templates/admin.html` |
| `[data-adm-turnitin-balance]` | querySelector | `templates/admin.html` |
| `[data-adm-usage-body]` | querySelector | `templates/admin.html` |
| `[data-adm-usage-close]` | querySelector | `templates/admin.html` |
| `[data-adm-usage-count]` | querySelector | `templates/admin.html` |
| `[data-adm-usage-empty]` | querySelector | `templates/admin.html` |
| `[data-adm-usage-overlay]` | querySelector | `templates/admin.html` |
| `[data-adm-usage-status]` | querySelector | `templates/admin.html` |
| `[data-adm-usage-subtitle]` | querySelector | `templates/admin.html` |
| `[data-adm-withdrawals-body]` | querySelector | `templates/admin.html` |
| `[data-adm-withdrawals-empty]` | querySelector | `templates/admin.html` |
| `[data-adm-withdrawals-refresh]` | querySelector | `templates/admin.html` |
| `[data-adm-withdrawals-status]` | querySelector | `templates/admin.html` |
| `[data-admin-page]` | querySelector | `templates/admin.html` |

### `static/app-shell.js`

Подключается из: `templates/base.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-sidebar-brand]` | closest | `templates/base.html` |
| `[data-sidebar-close]` | closest | `templates/base.html` |
| `[data-sidebar-collapse]` | closest | `templates/base.html` |
| `[data-sidebar-toggle]` | closest | `templates/base.html` |
| `[data-tool-new-chat], [data-asg-new-chat]` | closest | `templates/base.html` |
| `.app-sidebar-backdrop` | querySelector | `templates/base.html` |
| `[data-sidebar-brand]` | querySelector | `templates/base.html` |
| `[data-sidebar-collapse]` | querySelector | `templates/base.html` |
| `[data-sidebar-toggle]` | querySelector | `templates/base.html` |
| `[data-tool-history-list]` | querySelector | `templates/base.html` |
| `[data-tool-history]` | querySelector | `templates/base.html` |
| `[data-sidebar-close]` | querySelectorAll | `templates/base.html` |

### `static/assignment-page.js`

Подключается из: `templates/assignment.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-asg-analyze]` | $() → querySelector/getElementById | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-attach]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-chat-scroll]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-chips]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-complete-download-secondary]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-complete-download]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-complete]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-composer-form]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-continue]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-drop-overlay]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-empty]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-files]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-note]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-page-error]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-price-breakdown]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-production-fill]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-production-pct]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-production]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-revchat-form]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-revchat-input]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-revchat-meta]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-revchat-thread]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-send]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-summary-coins]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-thread]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-wizard-back]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-wizard-card]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-wizard-error]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-wizard-primary]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-wizard-status]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-wizard]` | $() → querySelector/getElementById | `templates/assignment.html` |
| `[data-asg-thread-download]` | closest | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-thread-pay]` | closest | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `.app-shell-main` | querySelector | `templates/base.html` |
| `.asg-wizard-actions` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-thread-download]` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-thread-pay]` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-assignment-page]` | querySelector | `templates/assignment.html` |
| `[data-kind="' + kind + '"]` | querySelector | создаётся в JS (innerHTML/template), не в templates |
| `[data-kind="complete"]` | querySelector | создаётся в JS (innerHTML/template), не в templates |
| `[data-kind="status"]` | querySelector | создаётся в JS (innerHTML/template), не в templates |
| `input[name="asg_priority"]:checked` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-attach],[data-asg-send],[data-asg-note],[data-asg-files]` | querySelectorAll | `templates/assignment.html` |
| `[data-asg-chip-remove]` | querySelectorAll | создаётся в JS (innerHTML/template), не в templates |
| `[data-asg-send],[data-asg-note]` | querySelectorAll | `templates/assignment.html` |
| `[data-kind="' + kind + '"]` | querySelectorAll | создаётся в JS (innerHTML/template), не в templates |
| `[data-kind="production"]` | querySelectorAll | создаётся в JS (innerHTML/template), не в templates |
| `[data-kind="rev-msg"]` | querySelectorAll | создаётся в JS (innerHTML/template), не в templates |
| `.app-shell-main` | quoted selector (helper) | `templates/base.html` |
| `.asg-wizard-actions` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-analysis-status]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-analyze]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-attach]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-chat-scroll]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-chip-remove]` | quoted selector (helper) | создаётся в JS (innerHTML/template), не в templates |
| `[data-asg-chips]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-complete-download-secondary]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-complete-download]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-complete]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-composer-form]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-continue]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-drop-overlay]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-empty]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-files]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-note]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-page-error]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-price-breakdown]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-production-fill]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-production-pct]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-production]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-revchat-form]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-revchat-input]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-revchat-meta]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-revchat-thread]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-send]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-coins]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-deadline]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-difficulty]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-eta-row]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-eta]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-total]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-type]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-words]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-thread-download]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-thread-pay]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-thread]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-wizard-back]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-wizard-card]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-wizard-error]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-wizard-primary]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-wizard-status]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-wizard]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-assignment-page]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-kind="' + kind + '"]` | quoted selector (helper) | создаётся в JS (innerHTML/template), не в templates |
| `[data-kind="complete"]` | quoted selector (helper) | создаётся в JS (innerHTML/template), не в templates |
| `[data-kind="production"]` | quoted selector (helper) | создаётся в JS (innerHTML/template), не в templates |
| `[data-kind="rev-msg"]` | quoted selector (helper) | создаётся в JS (innerHTML/template), не в templates |
| `[data-kind="status"]` | quoted selector (helper) | создаётся в JS (innerHTML/template), не в templates |

### `static/assignment/project-ux.js`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-asg-overall-progress-bar]` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-project-header]` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-overall-progress-bar]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-overall-progress]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-project-eta]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-project-header]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-project-name]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-project-stage]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-project-started]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-project-status]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-project-updated]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-summary-citation]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-summary-completion]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-summary-deadline]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-difficulty]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-price]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-summary-sources]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-asg-summary-total]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-type]` | quoted selector (helper) | `templates/assignment.html` |
| `[data-asg-summary-words]` | quoted selector (helper) | `templates/assignment.html` |

### `static/auth-modal.js`

Подключается из: `templates/base.html`, `templates/workspace_base.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `.app-sidebar-footer` | quoted selector (helper) | `templates/base.html` |
| `.app-topbar-account` | quoted selector (helper) | `templates/base.html` |
| `.dm-auth-modal` | quoted selector (helper) | `templates/_register_wall.html` |
| `.dm-auth-submit` | quoted selector (helper) | `templates/_register_wall.html` |
| `.nav-account` | quoted selector (helper) | `templates/base.html` |
| `[data-auth-backdrop]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-auth-close]` | quoted selector (helper) | `templates/_register_wall.html` |
| `[data-auth-error]` | quoted selector (helper) | `templates/_register_wall.html` |
| `[data-auth-form]` | quoted selector (helper) | `templates/_register_wall.html` |
| `[data-auth-layer]` | quoted selector (helper) | `templates/_register_wall.html` |
| `[data-auth-reason]` | quoted selector (helper) | `templates/_register_wall.html` |
| `[data-auth-tab]` | quoted selector (helper) | `templates/_register_wall.html` |
| `[data-auth-title]` | quoted selector (helper) | `templates/_register_wall.html` |

### `static/check.js`

Подключается из: `templates/check.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `#apply_detected_requirements_btn` | $() as getElementById | `templates/check.html` |
| `#check_action_plan` | $() as getElementById | `templates/check.html` |
| `#check_categories_list` | $() as getElementById | `templates/check.html` |
| `#check_citation_list` | $() as getElementById | `templates/check.html` |
| `#check_compliance_list` | $() as getElementById | `templates/check.html` |
| `#check_compliance_text` | $() as getElementById | `templates/check.html` |
| `#check_doc_type` | $() as getElementById | `templates/check.html` |
| `#check_document_btn` | $() as getElementById | `templates/check.html` |
| `#check_file` | $() as getElementById | `templates/check.html` |
| `#check_fix_first` | $() as getElementById | `templates/check.html` |
| `#check_issues_list` | $() as getElementById | `templates/check.html` |
| `#check_needs_list` | $() as getElementById | `templates/check.html` |
| `#check_next_steps` | $() as getElementById | `templates/check.html` |
| `#check_parser_empty` | $() as getElementById | `templates/check.html` |
| `#check_pasted_text` | $() as getElementById | `templates/check.html` |
| `#check_positives_list` | $() as getElementById | `templates/check.html` |
| `#check_requirements` | $() as getElementById | `templates/check.html` |
| `#check_requirements_file` | $() as getElementById | `templates/check.html` |
| `#check_results` | $() as getElementById | `templates/check.html` |
| `#check_score_ring` | $() as getElementById | `templates/check.html` |
| `#check_score_value` | $() as getElementById | `templates/check.html` |
| `#check_status` | $() as getElementById | `templates/check.html` |
| `#check_summary` | $() as getElementById | `templates/check.html` |
| `#check_top_problems` | $() as getElementById | `templates/check.html` |
| `#check_validations_list` | $() as getElementById | `templates/check.html` |
| `#check_verdict` | $() as getElementById | `templates/check.html` |
| `#detected_requirements_card` | $() as getElementById | `templates/check.html` |
| `#detected_requirements_list` | $() as getElementById | `templates/check.html` |
| `#detected_requirements_summary` | $() as getElementById | `templates/check.html` |
| `#structure_detected_sections` | $() as getElementById | `templates/check.html` |
| `#structure_heading_issues` | $() as getElementById | `templates/check.html` |
| `#structure_health_score` | $() as getElementById | `templates/check.html` |
| `#structure_missing_sections` | $() as getElementById | `templates/check.html` |
| `#structure_paragraph_issues` | $() as getElementById | `templates/check.html` |
| `#structure_recovery_meta` | $() as getElementById | `templates/check.html` |
| `#structure_suggestions` | $() as getElementById | `templates/check.html` |
| `#structure_tree` | $() as getElementById | `templates/check.html` |
| `.check-analysis-panel` | querySelectorAll | `templates/check.html` |
| `.check-analysis-tab` | querySelectorAll | `templates/check.html` |

### `static/common.js`

Подключается из: `templates/base.html`, `templates/workspace_base.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `#alignment` | $() as getElementById | `templates/index.html` |
| `#auto_headings` | $() as getElementById | `templates/index.html` |
| `#auto_justify_refs` | $() as getElementById | `templates/index.html` |
| `#clean_extra_linebreaks` | $() as getElementById | `templates/index.html` |
| `#clean_extra_spaces` | $() as getElementById | `templates/index.html` |
| `#document_type` | $() as getElementById | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `#first_line_indent` | $() as getElementById | `templates/index.html` |
| `#font_family` | $() as getElementById | `templates/index.html` |
| `#font_size` | $() as getElementById | `templates/index.html` |
| `#format_style` | $() as getElementById | `templates/index.html` |
| `#heading_all_caps` | $() as getElementById | `templates/index.html` |
| `#line_spacing` | $() as getElementById | `templates/index.html` |
| `#margin_preset` | $() as getElementById | `templates/index.html` |
| `#page_number_position` | $() as getElementById | `templates/index.html` |
| `#requirement_headings` | $() as getElementById | `templates/index.html` |
| `#requirements_text` | $() as getElementById | `templates/index.html` |
| `#space_after_pt` | $() as getElementById | `templates/index.html` |
| `#space_before_pt` | $() as getElementById | `templates/index.html` |
| `[data-theme-set]` | closest | `templates/base.html` |
| `[data-theme-toggle]` | closest | `templates/base.html` |
| `[data-user-menu-toggle]` | closest | `templates/base.html` |
| `[data-user-menu]` | closest | `templates/base.html` |
| `#cover_file` | getElementById | `templates/index.html` |
| `#format_btn` | getElementById | `templates/index.html` |
| `#format_status` | getElementById | `templates/index.html` |
| `#requirements_text` | getElementById | `templates/index.html` |
| `.theme-toggle-icon--moon` | querySelector | `templates/base.html` |
| `.theme-toggle-icon--sun` | querySelector | `templates/base.html` |
| `[data-user-menu-panel]` | querySelector | `templates/base.html` |
| `[data-user-menu-toggle]` | querySelector | `templates/base.html` |
| `[data-coin-balance]` | querySelectorAll | `templates/base.html`, `templates/workspace.html` |
| `[data-theme-set]` | querySelectorAll | `templates/base.html` |
| `[data-theme-toggle]` | querySelectorAll | `templates/base.html` |
| `[data-user-menu].is-open` | querySelectorAll | `templates/base.html` |

### `static/earn-page.js`

Подключается из: `templates/earn.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `.earn-ref` | closest | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-earn-ref-toggle]` | closest | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `.earn-ref-history` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-earn-balance]` | querySelector | `templates/earn.html` |
| `[data-earn-code]` | querySelector | `templates/earn.html` |
| `[data-earn-convert]` | querySelector | `templates/earn.html` |
| `[data-earn-copy]` | querySelector | `templates/earn.html` |
| `[data-earn-free-tt]` | querySelector | `templates/earn.html` |
| `[data-earn-link]` | querySelector | `templates/earn.html` |
| `[data-earn-page]` | querySelector | `templates/earn.html` |
| `[data-earn-pro-badge]` | querySelector | `templates/earn.html` |
| `[data-earn-progress-bar]` | querySelector | `templates/earn.html` |
| `[data-earn-progress-fill]` | querySelector | `templates/earn.html` |
| `[data-earn-qualifying]` | querySelector | `templates/earn.html` |
| `[data-earn-refs-count]` | querySelector | `templates/earn.html` |
| `[data-earn-refs-empty]` | querySelector | `templates/earn.html` |
| `[data-earn-refs]` | querySelector | `templates/earn.html` |
| `[data-earn-status]` | querySelector | `templates/earn.html` |
| `[data-earn-steps]` | querySelector | `templates/earn.html` |
| `[data-earn-total-refs]` | querySelector | `templates/earn.html` |
| `[data-earn-withdraw-amount]` | querySelector | `templates/earn.html` |
| `[data-earn-withdraw-form]` | querySelector | `templates/earn.html` |
| `[data-earn-withdraw-modal]` | querySelector | `templates/earn.html` |
| `[data-earn-withdraw-wallet]` | querySelector | `templates/earn.html` |
| `[data-earn-withdraw]` | querySelector | `templates/earn.html` |
| `[data-earn-withdraw-close]` | querySelectorAll | `templates/earn.html` |

### `static/editor-page.js`

Подключается из: `templates/editor.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `#editor_save_status` | getElementById | `templates/editor.html` |
| `#editor_stats` | getElementById | `templates/editor.html` |
| `#editor_surface` | getElementById | `templates/editor.html` |

### `static/format_v2.js`

Подключается из: `templates/format_v2.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `#v2_abbr_enabled` | $() as getElementById | `templates/format_v2.html` |
| `#v2_abbr_entries` | $() as getElementById | `templates/format_v2.html` |
| `#v2_alignment` | $() as getElementById | `templates/format_v2.html` |
| `#v2_appendices_enabled` | $() as getElementById | `templates/format_v2.html` |
| `#v2_appendices_lettered` | $() as getElementById | `templates/format_v2.html` |
| `#v2_captions_enabled` | $() as getElementById | `templates/format_v2.html` |
| `#v2_chat_history` | $() as getElementById | `templates/format_v2.html` |
| `#v2_chat_history_empty` | $() as getElementById | `templates/format_v2.html` |
| `#v2_chat_history_wrap` | $() as getElementById | `templates/format_v2.html` |
| `#v2_chat_message` | $() as getElementById | `templates/format_v2.html` |
| `#v2_chat_panel` | $() as getElementById | `templates/format_v2.html` |
| `#v2_chat_pending` | $() as getElementById | `templates/format_v2.html` |
| `#v2_chat_rejected` | $() as getElementById | `templates/format_v2.html` |
| `#v2_chat_send` | $() as getElementById | `templates/format_v2.html` |
| `#v2_chat_summary` | $() as getElementById | `templates/format_v2.html` |
| `#v2_chat_undo` | $() as getElementById | `templates/format_v2.html` |
| `#v2_citation_style_override` | $() as getElementById | `templates/format_v2.html` |
| `#v2_cover_course` | $() as getElementById | `templates/format_v2.html` |
| `#v2_cover_date` | $() as getElementById | `templates/format_v2.html` |
| `#v2_cover_enabled` | $() as getElementById | `templates/format_v2.html` |
| `#v2_cover_lecturer` | $() as getElementById | `templates/format_v2.html` |
| `#v2_cover_student` | $() as getElementById | `templates/format_v2.html` |
| `#v2_cover_title` | $() as getElementById | `templates/format_v2.html` |
| `#v2_download_latest` | $() as getElementById | `templates/format_v2.html` |
| `#v2_drop_placeholder` | $() as getElementById | `templates/format_v2.html` |
| `#v2_expected_sections` | $() as getElementById | `templates/format_v2.html` |
| `#v2_figure_position` | $() as getElementById | `templates/format_v2.html` |
| `#v2_file` | $() as getElementById | `templates/format_v2.html` |
| `#v2_file_name` | $() as getElementById | `templates/format_v2.html` |
| `#v2_first_line_indent` | $() as getElementById | `templates/format_v2.html` |
| `#v2_font_family` | $() as getElementById | `templates/format_v2.html` |
| `#v2_font_size` | $() as getElementById | `templates/format_v2.html` |
| `#v2_format_btn` | $() as getElementById | `templates/format_v2.html` |
| `#v2_format_status` | $() as getElementById | `templates/format_v2.html` |
| `#v2_format_style` | $() as getElementById | `templates/format_v2.html` |
| `#v2_heading_size_pt` | $() as getElementById | `templates/format_v2.html` |
| `#v2_line_spacing` | $() as getElementById | `templates/format_v2.html` |
| `#v2_margin_preset` | $() as getElementById | `templates/format_v2.html` |
| `#v2_notices` | $() as getElementById | `templates/format_v2.html` |
| `#v2_notices_list` | $() as getElementById | `templates/format_v2.html` |
| `#v2_page_number_position` | $() as getElementById | `templates/format_v2.html` |
| `#v2_page_preview` | $() as getElementById | `templates/format_v2.html` |
| `#v2_page_preview_inner` | $() as getElementById | `templates/format_v2.html` |
| `#v2_page_size` | $() as getElementById | `templates/format_v2.html` |
| `#v2_parse_btn` | $() as getElementById | `templates/format_v2.html` |
| `#v2_pasted_text` | $() as getElementById | `templates/format_v2.html` |
| `#v2_preview_cover` | $() as getElementById | `templates/format_v2.html` |
| `#v2_preview_pagenum` | $() as getElementById | `templates/format_v2.html` |
| `#v2_preview_summary` | $() as getElementById | `templates/format_v2.html` |
| `#v2_profile_summary` | $() as getElementById | `templates/format_v2.html` |
| `#v2_refs_enabled` | $() as getElementById | `templates/format_v2.html` |
| `#v2_refs_heading` | $() as getElementById | `templates/format_v2.html` |
| `#v2_refs_new_page` | $() as getElementById | `templates/format_v2.html` |
| `#v2_refs_numbered` | $() as getElementById | `templates/format_v2.html` |
| `#v2_requirements_status` | $() as getElementById | `templates/format_v2.html` |
| `#v2_requirements_text` | $() as getElementById | `templates/format_v2.html` |
| `#v2_style_hint` | $() as getElementById | `templates/format_v2.html` |
| `#v2_table_position` | $() as getElementById | `templates/format_v2.html` |
| `#v2_toc_enabled` | $() as getElementById | `templates/format_v2.html` |
| `#v2_toc_field_based` | $() as getElementById | `templates/format_v2.html` |
| `#v2_toc_max_depth` | $() as getElementById | `templates/format_v2.html` |
| `[data-format-v2]` | querySelector | `templates/format_v2.html` |
| `[data-v2-doc-card]` | querySelector | `templates/format_v2.html` |
| `[data-v2-doc-panel="paste"]` | querySelector | `templates/format_v2.html` |
| `[data-v2-doc-segment]` | querySelector | `templates/format_v2.html` |
| `[data-v2-drop-zone]` | querySelector | `templates/format_v2.html` |
| `[data-v2-zone-overlay]` | querySelector | `templates/format_v2.html` |
| `.v2-page-preview__line` | querySelectorAll | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-evidence-for="' + key + '"]` | querySelectorAll | `templates/format_v2.html` |
| `[data-evidence-for]` | querySelectorAll | `templates/format_v2.html` |
| `[data-v2-depends-on]` | querySelectorAll | `templates/format_v2.html` |
| `[data-v2-doc-source]` | querySelectorAll | `templates/format_v2.html` |
| `[data-v2-field]` | querySelectorAll | `templates/format_v2.html` |
| `[data-v2-style]` | querySelectorAll | `templates/format_v2.html` |
| `[data-v2-toggle]` | querySelectorAll | `templates/format_v2.html` |
| `input, select, textarea, button` | querySelectorAll | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `.v2-page-preview__line` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-evidence-for="' + key + '"]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-evidence-for]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-format-v2]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-v2-depends-on]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-v2-doc-card]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-v2-doc-panel="paste"]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-v2-doc-segment]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-v2-doc-source]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-v2-drop-zone]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-v2-field]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-v2-style]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-v2-toggle]` | quoted selector (helper) | `templates/format_v2.html` |
| `[data-v2-zone-overlay]` | quoted selector (helper) | `templates/format_v2.html` |

### `static/home.js`

Подключается из: `templates/index.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `#analyze_requirements_btn` | $() as getElementById | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `#citations_count` | $() as getElementById | `templates/index.html` |
| `#citations_preview_list` | $() as getElementById | `templates/index.html` |
| `#citations_status` | $() as getElementById | `templates/index.html` |
| `#cover_file` | $() as getElementById | `templates/index.html` |
| `#cover_file_status` | $() as getElementById | `templates/index.html` |
| `#file` | $() as getElementById | `templates/index.html` |
| `#format_btn` | $() as getElementById | `templates/index.html` |
| `#format_status` | $() as getElementById | `templates/index.html` |
| `#format_style` | $() as getElementById | `templates/index.html` |
| `#generate_citations_btn` | $() as getElementById | `templates/index.html` |
| `#generate_references_btn` | $() as getElementById | `templates/index.html` |
| `#home_preview_section` | $() as getElementById | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `#home_workspace_cta` | $() as getElementById | `templates/index.html` |
| `#include_cover_page` | $() as getElementById | `templates/index.html` |
| `#pasted_text` | $() as getElementById | `templates/index.html` |
| `#preview_changes_btn` | $() as getElementById | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `#references_count` | $() as getElementById | `templates/index.html` |
| `#references_preview_list` | $() as getElementById | `templates/index.html` |
| `#references_status` | $() as getElementById | `templates/index.html` |
| `#requirements_attach` | $() as getElementById | `templates/index.html` |
| `#requirements_attach_btn` | $() as getElementById | `templates/index.html` |
| `#requirements_status` | $() as getElementById | `templates/index.html` |
| `#requirements_text` | $() as getElementById | `templates/index.html` |
| `[data-home-drop-zone]` | closest | `templates/index.html` |
| `.app-shell-main` | querySelector | `templates/base.html` |
| `.home-cover-card` | querySelector | `templates/index.html` |
| `[data-home-brief-card]` | querySelector | `templates/index.html` |
| `[data-home-brief-segment]` | querySelector | `templates/index.html` |
| `[data-home-doc-card]` | querySelector | `templates/index.html` |
| `[data-home-doc-segment]` | querySelector | `templates/index.html` |
| `[data-home-zone-overlay]` | querySelector | `templates/index.html` |
| `[data-tour='format-page'], .home-layout` | querySelector | `templates/index.html` |
| `input[name='reference_source']:checked` | querySelector | `templates/index.html` |
| `.text-settings-card .preset-chip` | querySelectorAll | `templates/index.html` |
| `[data-citation-style-select]` | querySelectorAll | `templates/index.html` |
| `[data-home-brief-source]` | querySelectorAll | `templates/index.html` |
| `[data-home-doc-panel]` | querySelectorAll | `templates/index.html` |
| `[data-home-doc-source]` | querySelectorAll | `templates/index.html` |
| `[data-home-drop-zone]` | querySelectorAll | `templates/index.html` |

### `static/humanizer-page.js`

Подключается из: `templates/humanizer.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-humanizer-page]` | $() → querySelector/getElementById | `templates/humanizer.html` |
| `.app-shell-main` | querySelector | `templates/base.html` |
| `.app-shell-main` | quoted selector (helper) | `templates/base.html` |
| `[data-humanizer-page]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-clear]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-copy-icon]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-copy-label]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-copy]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-drop-overlay]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-error-msg]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-error]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-file]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-font]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-format]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-input]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-loading]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-out-words]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-output]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-paste-focus]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-result]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-run-icon]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-run-label]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-run-spinner]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-run]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-segment]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-source]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-stage]` | quoted selector (helper) | `templates/humanizer.html` |
| `[data-hz-wordcount]` | quoted selector (helper) | `templates/humanizer.html` |

### `static/preview.js`

Подключается из: `templates/index.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-preview-after]` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-preview-before]` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-preview-diff]` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |

### `static/pricing.js`

Подключается из: `templates/pricing.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-topup-status]` | querySelector | `templates/pricing.html` |
| `[data-topup]` | querySelectorAll | `templates/pricing.html` |

### `static/support-chat.js`

Подключается из: `templates/base.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `#support_chat_layer` | getElementById | `templates/base.html` |
| `#support_chat_message` | getElementById | `templates/base.html` |
| `#support_chat_send` | getElementById | `templates/base.html` |
| `#support_chat_status` | getElementById | `templates/base.html` |
| `#support_chat_thread` | getElementById | `templates/base.html` |
| `#support_chat_toggle` | getElementById | `templates/base.html` |
| `[data-support-empty]` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-support-close]` | querySelectorAll | `templates/base.html` |

### `static/tour.js`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-dm-tour-page]` | $() → querySelector/getElementById | `templates/assignment.html`, `templates/check.html`, `templates/humanizer.html`, `templates/index.html`, `templates/turnitin.html` |
| `[data-dm-tour]` | $() → querySelector/getElementById | создаётся в JS (innerHTML/template), не в templates |
| `[data-dm-tutorial]` | querySelectorAll | `templates/_tutorial_btn.html` |
| `[data-dm-tour-back]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-dm-tour-backdrop]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-dm-tour-body]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-dm-tour-card]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-dm-tour-close]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-dm-tour-next]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-dm-tour-page]` | quoted selector (helper) | `templates/assignment.html`, `templates/check.html`, `templates/humanizer.html`, `templates/index.html`, `templates/turnitin.html` |
| `[data-dm-tour-progress]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-dm-tour-spot]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-dm-tour-title]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-dm-tour]` | quoted selector (helper) | создаётся в JS (innerHTML/template), не в templates |
| `[data-dm-tutorial]` | quoted selector (helper) | `templates/_tutorial_btn.html` |

### `static/turnitin-page.js`

Подключается из: `templates/turnitin.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-tt-delete]` | closest | создаётся в JS (innerHTML/template), не в templates |
| `[data-tt-download]` | closest | создаётся в JS (innerHTML/template), не в templates |
| `[data-tt-get-highlights]` | closest | создаётся в JS (innerHTML/template), не в templates |
| `.app-shell-main` | querySelector | `templates/base.html` |
| `[data-coin-balance]` | querySelector | `templates/base.html`, `templates/workspace.html` |
| `[data-tt-credits]` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-tt-drop-overlay]` | querySelector | `templates/turnitin.html` |
| `[data-tt-empty]` | querySelector | `templates/turnitin.html` |
| `[data-tt-file]` | querySelector | `templates/turnitin.html` |
| `[data-tt-filename]` | querySelector | `templates/turnitin.html` |
| `[data-tt-reports-body]` | querySelector | `templates/turnitin.html` |
| `[data-tt-search]` | querySelector | `templates/turnitin.html` |
| `[data-tt-submit-status]` | querySelector | `templates/turnitin.html` |
| `[data-tt-submit]` | querySelector | `templates/turnitin.html` |
| `[data-turnitin-page]` | querySelector | `templates/turnitin.html` |
| `[data-coin-balance]` | querySelectorAll | `templates/base.html`, `templates/workspace.html` |
| `[data-tt-opt]` | querySelectorAll | `templates/turnitin.html` |

### `static/ui.js`

Подключается из: `templates/base.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `#app_toast_container` | getElementById | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |

### `static/workspace.js`

Подключается из: `templates/index.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-workspace]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `#workspace_coin_count` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `#workspace_doc_title` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `#workspace_editor` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `#workspace_save_status` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `#workspace_stats` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-workspace]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-panel]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-tab]` | quoted selector (helper) | `templates/workspace.html` |

### `static/workspace/workspace-app.js`

Подключается из: `templates/workspace.html`, `templates/workspace_base.html`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `.ws-doc-scroll` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-cmd-block]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-ai-apply]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-charcount]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-cite-query]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-cite-results]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-cite-scan]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-cite-search]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-cite-style]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-comment-add]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-comment-input]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-comment-quote]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-comments-list]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-detect]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-doc-title]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-dropzone]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-editor-surface]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-editor]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-floatbar]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-hl-toggle]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-humanize-run]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-import-input]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-landing]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-progress-bar]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-progress]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-recent-words]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-saved]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-toast]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-tour-back]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-tour-backdrop]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-tour-card]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-tour-close]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-tour-next]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-tour-spot]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-tour]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `[data-ws-wordcount]` | $() → querySelector/getElementById | `templates/workspace.html` |
| `.ws-ai-highlight` | closest | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `.ws-mark` | closest | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-workspace]` | querySelector | `templates/workspace.html` |
| `[data-ws-refs]` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-coin-balance]` | querySelectorAll | `templates/base.html`, `templates/workspace.html` |
| `.doc` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `.ws-ai-highlight` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `.ws-doc-scroll` | quoted selector (helper) | `templates/workspace.html` |
| `.ws-mark` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-cmd-block]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-cmd="' + c + '"]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-cmd]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-coin-balance]` | quoted selector (helper) | `templates/base.html`, `templates/workspace.html` |
| `[data-workspace]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-ai-action]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-ai-apply]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-back]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-charcount]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-cite-insert]` | quoted selector (helper) | создаётся в JS (innerHTML/template), не в templates |
| `[data-ws-cite-query]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-cite-ref]` | quoted selector (helper) | создаётся в JS (innerHTML/template), не в templates |
| `[data-ws-cite-results]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-cite-scan]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-cite-search]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-cite-style]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-comment-add]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-comment-input]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-comment-quote]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-comments-list]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-detect]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-doc-title]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-dropzone]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-editor-surface]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-editor]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-export]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-fb="' + c + '"]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-fb]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-flagged-parts]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-flagged-words]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-floatbar]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-history-btn]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-hl-index]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-hl-next]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-hl-prev]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-hl-toggle]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-humanize-run]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-import-input]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-landing]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-mark-all-ai]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-mark]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-new-blank]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-open-sample]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-open-turnitin]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-panel]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-pending-cost]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-pending-count]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-pending-words]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-progress-bar]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-progress]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-recent-words]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-refs]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-ws-saved]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-share]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-tab]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-toast]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-topup]` | quoted selector (helper) | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `[data-ws-tour-back]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-tour-backdrop]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-tour-body]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-tour-card]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-tour-close]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-tour-next]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-tour-progress]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-tour-spot]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-tour-title]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-tour]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-unmark-all]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-unmark]` | quoted selector (helper) | `templates/workspace.html` |
| `[data-ws-wordcount]` | quoted selector (helper) | `templates/workspace.html` |

### `templates/account.html#inline`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-avatar-form]` | querySelector | `templates/account.html` |
| `[data-avatar-status]` | querySelector | `templates/account.html` |

### `templates/admin_dataset_stats.html#inline`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-adm-dataset-assignment]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-dataset-page]` | querySelector | `templates/admin_dataset_stats.html` |
| `[data-adm-dataset-refresh]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-dataset-standalone]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-dataset-status]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-dataset-total]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-dataset-workspace]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-detector-auto]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-detector-manual]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-detector-samples]` | querySelector | `templates/admin_dataset_stats.html` |
| `[data-adm-detector-total]` | querySelector | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `[data-adm-humanizer-samples]` | querySelector | `templates/admin_dataset_stats.html` |

### `templates/register.html#inline`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `[data-dm-fingerprint]` | querySelector | `templates/register.html` |
| `[data-dm-register-form]` | querySelector | `templates/register.html` |
| `button[type="submit"]` | querySelector | ⚠️ не найден в `templates/` (динамический / мёртвый / другой слой) |
| `input[name="password"]` | querySelector | `templates/_register_wall.html`, `templates/login.html`, `templates/register.html` |
| `input[name="password_confirm"]` | querySelector | `templates/_register_wall.html`, `templates/register.html` |

### `templates/verify_email.html#inline`

| Селектор / цель | Метод | Шаблон(ы) элемента |
|---|---|---|
| `.auth-otp-input` | querySelector | `templates/verify_email.html` |

### JS без DOM-селекторов (API / engines)

Эти файлы не ищут элементы через `getElementById` / `querySelector` / `$()` с литералами. При редизайне вёрстки их трогать не нужно (кроме косвенных `data-*`/`id`, если появятся позже).

- `static/assignment-templates.js` ← `templates/index.html`
- `static/assignment/ai-detection-engine.js`
- `static/assignment/blueprint-engine.js`
- `static/assignment/delivery-engine.js`
- `static/assignment/event-bus.js`
- `static/assignment/humanizer-engine.js`
- `static/assignment/pipeline-manager.js`
- `static/assignment/requirement-analyzer.js`
- `static/assignment/research-engine.js`
- `static/assignment/reviewer-engine.js`
- `static/assignment/revision-engine.js`
- `static/assignment/writer-engine.js`
- `static/device-fingerprint.js` ← `templates/base.html`, `templates/register.html`
- `static/tool-history.js` ← `templates/base.html`
- `static/tools-nav.js`
- `static/tour-catalog.js`
- `static/workspace/mock-services.js` ← `templates/workspace.html`, `templates/workspace_base.html`
- `static/workspace/tour-steps.js` ← `templates/workspace.html`, `templates/workspace_base.html`

## 2. `name=` полей, которые читает Flask

Источник: `request.form` / `form.get` / `_truthy(form, …)` / `request.args` / `request.files` / `request.values` (без venv).

> Часть ключей (`refunded`, `chargebacked`, Gumroad payload) приходит с вебхуков, не из UI-форм — в таблице помечены как «webhook / нет в HTML». Их всё равно нельзя ломать на бэкенде.

### 2.1 `request.form` / `form.get`

| name | Python | Шаблоны (`name=`) |
|---|---|---|
| `action` | `app.py` | `templates/account.html`, `templates/verify_email.html` |
| `alignment` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `assignment_brief` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `auto_headings` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `auto_justify_refs` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `chargebacked` | `services/economy/gumroad_gateway.py` | — (FormData из JS / webhook / нет в HTML) |
| `citation_style` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `clean_extra_linebreaks` | `app.py`, `formatter_v2/web_api.py` | — (FormData из JS / webhook / нет в HTML) |
| `clean_extra_spaces` | `app.py`, `formatter_v2/web_api.py` | — (FormData из JS / webhook / нет в HTML) |
| `code` | `app.py` | `templates/verify_email.html` |
| `confirm_password` | `app.py` | `templates/account.html` |
| `cover_assignment_title` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `cover_lecturer` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `cover_module` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `cover_student_id` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `cover_student_name` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `cover_submission_date` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `cover_university` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `current_password` | `app.py` | `templates/account.html` |
| `deadline` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `device_fingerprint` | `app.py` | `templates/register.html` |
| `document_type` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `email` | `app.py` | `templates/_register_wall.html`, `templates/login.html`, `templates/register.html` |
| `exclude_bibliography` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `exclude_quotes` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `first_line_indent` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `font_family` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `font_size` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `format_style` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `heading_all_caps` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `heading_size_pt` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `include_cover_page` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `lecture_notes` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `line_spacing` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `margin_preset` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `message` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `name` | `app.py` | `templates/_register_wall.html`, `templates/account.html`, `templates/register.html` |
| `new_password` | `app.py` | `templates/account.html` |
| `note` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `overrides` | `formatter_v2/web_api.py` | — (FormData из JS / webhook / нет в HTML) |
| `page_number_position` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `parsed_requirements` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `password` | `app.py` | `templates/_register_wall.html`, `templates/login.html`, `templates/register.html` |
| `password_confirm` | `app.py` | `templates/_register_wall.html`, `templates/register.html` |
| `pasted_text` | `app.py`, `formatter_v2/web_api.py` | — (FormData из JS / webhook / нет в HTML) |
| `ref` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `references` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `referral_code` | `app.py` | `templates/register.html` |
| `refunded` | `services/economy/gumroad_gateway.py` | — (FormData из JS / webhook / нет в HTML) |
| `requirement_headings` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `requirements` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `requirements_text` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `rubric` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `space_after_pt` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `space_before_pt` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `structure_recovery_debug` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `style` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `style_preset` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `title` | `app.py` | — (FormData из JS / webhook / нет в HTML) |
| `verification_code` | `app.py` | — (FormData из JS / webhook / нет в HTML) |

Поля cover page (`parse_cover_page`): `cover_assignment_title`, `cover_lecturer`, `cover_module`, `cover_student_id`, `cover_student_name`, `cover_submission_date`, `cover_university`.

Поля `parse_job`: `font_family`, `font_size`, `line_spacing`, `alignment`, `page_number_position`, `margin_preset`, `space_before_pt`, `space_after_pt`, `format_style`, `style_preset`, `citation_style`, `first_line_indent`, `auto_headings`, `heading_all_caps`, `auto_justify_refs`, `requirement_headings`, `heading_size_pt`, `include_cover_page`.

### 2.2 `request.args`

| name | Python |
|---|---|
| `after_id` | `app.py` |
| `feature` | `app.py` |
| `limit` | `app.py` |
| `offset` | `app.py` |
| `q` | `app.py` |
| `search` | `app.py` |
| `secret` | `app.py` |
| `status` | `app.py` |
| `top` | `app.py` |

### 2.3 `request.files`

| name | Python | Шаблоны |
|---|---|---|
| `avatar` | `app.py` | `templates/account.html` |
| `cover_file` | `app.py` | — |
| `file` | `app.py` | — |
| `files` | `app.py` | — |
| `image` | `app.py` | — |

### 2.4 `request.values` (form или query)

| name | Python |
|---|---|
| `next` | `app.py` |
| `ref` | `app.py` |
| `referral_code` | `app.py` |

## 3. `data-*` атрибуты, которые читает / пишет JS

Объединение: `.dataset.*`, `get/set/hasAttribute("data-…")`, селекторы `[data-…]`, и `data-*=` в JS-строках.

| data-* | JS | Шаблоны |
|---|---|---|
| `data-adm-admin-toggle` | `static/admin-page.js` | ставит JS |
| `data-adm-analytics-refresh` | — (только селектор) | `templates/admin.html` |
| `data-adm-analytics-status` | — (только селектор) | `templates/admin.html` |
| `data-adm-auto-enabled` | — (только селектор) | `templates/admin.html` |
| `data-adm-auto-min` | — (только селектор) | `templates/admin.html` |
| `data-adm-auto-time` | — (только селектор) | `templates/admin.html` |
| `data-adm-balance-form` | `static/admin-page.js` | ставит JS |
| `data-adm-balance-input` | `static/admin-page.js` | ставит JS |
| `data-adm-body` | — (только селектор) | `templates/admin.html` |
| `data-adm-dataset-assignment` | — (только селектор) | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `data-adm-dataset-page` | — (только селектор) | `templates/admin_dataset_stats.html` |
| `data-adm-dataset-refresh` | — (только селектор) | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `data-adm-dataset-standalone` | — (только селектор) | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `data-adm-dataset-status` | — (только селектор) | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `data-adm-dataset-total` | — (только селектор) | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `data-adm-dataset-workspace` | — (только селектор) | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `data-adm-delete` | `static/admin-page.js` | ставит JS |
| `data-adm-delete-email` | `static/admin-page.js` | ставит JS |
| `data-adm-detector-auto` | — (только селектор) | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `data-adm-detector-manual` | — (только селектор) | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `data-adm-detector-samples` | — (только селектор) | `templates/admin_dataset_stats.html` |
| `data-adm-detector-total` | — (только селектор) | `templates/admin.html`, `templates/admin_dataset_stats.html` |
| `data-adm-discount-live` | — (только селектор) | `templates/admin.html` |
| `data-adm-empty` | — (только селектор) | `templates/admin.html` |
| `data-adm-humanizer-samples` | — (только селектор) | `templates/admin_dataset_stats.html` |
| `data-adm-kpi-avg-credits` | — (только селектор) | `templates/admin.html` |
| `data-adm-kpi-avg-purchase` | — (только селектор) | `templates/admin.html` |
| `data-adm-kpi-feature` | — (только селектор) | `templates/admin.html` |
| `data-adm-kpi-revenue` | — (только селектор) | `templates/admin.html` |
| `data-adm-kpi-sold` | — (только селектор) | `templates/admin.html` |
| `data-adm-kpi-used` | — (только селектор) | `templates/admin.html` |
| `data-adm-ledger` | `static/admin-page.js` | ставит JS |
| `data-adm-ledger-balance` | — (только селектор) | `templates/admin.html` |
| `data-adm-ledger-body` | — (только селектор) | `templates/admin.html` |
| `data-adm-ledger-close` | — (только селектор) | `templates/admin.html` |
| `data-adm-ledger-count` | — (только селектор) | `templates/admin.html` |
| `data-adm-ledger-empty` | — (только селектор) | `templates/admin.html` |
| `data-adm-ledger-overlay` | — (только селектор) | `templates/admin.html` |
| `data-adm-ledger-status` | — (только селектор) | `templates/admin.html` |
| `data-adm-ledger-subtitle` | — (только селектор) | `templates/admin.html` |
| `data-adm-promo-active` | — (только селектор) | `templates/admin.html` |
| `data-adm-promo-form` | — (только селектор) | `templates/admin.html` |
| `data-adm-promo-limit` | — (только селектор) | `templates/admin.html` |
| `data-adm-promo-percent` | — (только селектор) | `templates/admin.html` |
| `data-adm-purchases` | `static/admin-page.js` | ставит JS |
| `data-adm-purchases-body` | — (только селектор) | `templates/admin.html` |
| `data-adm-purchases-close` | — (только селектор) | `templates/admin.html` |
| `data-adm-purchases-count` | — (только селектор) | `templates/admin.html` |
| `data-adm-purchases-empty` | — (только селектор) | `templates/admin.html` |
| `data-adm-purchases-overlay` | — (только селектор) | `templates/admin.html` |
| `data-adm-purchases-status` | — (только селектор) | `templates/admin.html` |
| `data-adm-purchases-subtitle` | — (только селектор) | `templates/admin.html` |
| `data-adm-row` | `static/admin-page.js` | ставит JS |
| `data-adm-search` | — (только селектор) | `templates/admin.html` |
| `data-adm-stats` | — (только селектор) | `templates/admin.html` |
| `data-adm-status` | — (только селектор) | `templates/admin.html` |
| `data-adm-today-date` | — (только селектор) | `templates/admin.html` |
| `data-adm-today-humanizer` | — (только селектор) | `templates/admin.html` |
| `data-adm-today-humanizer-limit` | — (только селектор) | `templates/admin.html` |
| `data-adm-today-humanizer-used` | — (только селектор) | `templates/admin.html` |
| `data-adm-today-refresh` | — (только селектор) | `templates/admin.html` |
| `data-adm-today-status` | — (только селектор) | `templates/admin.html` |
| `data-adm-today-turnitin` | — (только селектор) | `templates/admin.html` |
| `data-adm-top-countries` | — (только селектор) | `templates/admin.html` |
| `data-adm-top-countries-empty` | — (только селектор) | `templates/admin.html` |
| `data-adm-top-customers` | — (только селектор) | `templates/admin.html` |
| `data-adm-top-customers-empty` | — (только селектор) | `templates/admin.html` |
| `data-adm-total-users` | — (только селектор) | `templates/admin.html` |
| `data-adm-turnitin-balance` | — (только селектор) | `templates/admin.html` |
| `data-adm-usage` | `static/admin-page.js` | ставит JS |
| `data-adm-usage-body` | — (только селектор) | `templates/admin.html` |
| `data-adm-usage-close` | — (только селектор) | `templates/admin.html` |
| `data-adm-usage-count` | — (только селектор) | `templates/admin.html` |
| `data-adm-usage-empty` | — (только селектор) | `templates/admin.html` |
| `data-adm-usage-overlay` | — (только селектор) | `templates/admin.html` |
| `data-adm-usage-status` | — (только селектор) | `templates/admin.html` |
| `data-adm-usage-subtitle` | — (только селектор) | `templates/admin.html` |
| `data-adm-withdrawal-approve` | `static/admin-page.js` | ставит JS |
| `data-adm-withdrawal-reject` | `static/admin-page.js` | ставит JS |
| `data-adm-withdrawal-row` | `static/admin-page.js` | ставит JS |
| `data-adm-withdrawals-body` | — (только селектор) | `templates/admin.html` |
| `data-adm-withdrawals-empty` | — (только селектор) | `templates/admin.html` |
| `data-adm-withdrawals-refresh` | — (только селектор) | `templates/admin.html` |
| `data-adm-withdrawals-status` | — (только селектор) | `templates/admin.html` |
| `data-admin-page` | — (только селектор) | `templates/admin.html` |
| `data-ai-part` | `static/workspace/mock-services.js`, `static/workspace/workspace-app.js` | ставит JS |
| `data-analysis-panel` | `static/check.js` | `templates/check.html` |
| `data-analysis-tab` | `static/check.js` | `templates/check.html` |
| `data-asg-analysis-status` | — (только селектор) | `templates/assignment.html` |
| `data-asg-analyze` | — (только селектор) | — |
| `data-asg-attach` | — (только селектор) | `templates/assignment.html` |
| `data-asg-chat-scroll` | — (только селектор) | `templates/assignment.html` |
| `data-asg-chip-remove` | `static/assignment-page.js` | ставит JS |
| `data-asg-chips` | — (только селектор) | `templates/assignment.html` |
| `data-asg-complete` | — (только селектор) | `templates/assignment.html` |
| `data-asg-complete-download` | — (только селектор) | `templates/assignment.html` |
| `data-asg-complete-download-secondary` | — (только селектор) | `templates/assignment.html` |
| `data-asg-composer-form` | — (только селектор) | `templates/assignment.html` |
| `data-asg-continue` | — (только селектор) | `templates/assignment.html` |
| `data-asg-drop-overlay` | — (только селектор) | `templates/assignment.html` |
| `data-asg-empty` | — (только селектор) | `templates/assignment.html` |
| `data-asg-files` | — (только селектор) | `templates/assignment.html` |
| `data-asg-new-chat` | — (только селектор) | — |
| `data-asg-note` | — (только селектор) | `templates/assignment.html` |
| `data-asg-overall-progress` | — (только селектор) | — |
| `data-asg-overall-progress-bar` | — (только селектор) | — |
| `data-asg-page-error` | — (только селектор) | `templates/assignment.html` |
| `data-asg-price-breakdown` | — (только селектор) | `templates/assignment.html` |
| `data-asg-production` | — (только селектор) | `templates/assignment.html` |
| `data-asg-production-fill` | — (только селектор) | `templates/assignment.html` |
| `data-asg-production-pct` | — (только селектор) | `templates/assignment.html` |
| `data-asg-project-eta` | — (только селектор) | — |
| `data-asg-project-header` | — (только селектор) | — |
| `data-asg-project-name` | — (только селектор) | — |
| `data-asg-project-stage` | — (только селектор) | — |
| `data-asg-project-started` | — (только селектор) | — |
| `data-asg-project-status` | — (только селектор) | — |
| `data-asg-project-updated` | — (только селектор) | — |
| `data-asg-revchat-form` | — (только селектор) | `templates/assignment.html` |
| `data-asg-revchat-input` | — (только селектор) | `templates/assignment.html` |
| `data-asg-revchat-meta` | — (только селектор) | `templates/assignment.html` |
| `data-asg-revchat-thread` | — (только селектор) | `templates/assignment.html` |
| `data-asg-send` | — (только селектор) | `templates/assignment.html` |
| `data-asg-summary-citation` | — (только селектор) | — |
| `data-asg-summary-coins` | — (только селектор) | `templates/assignment.html` |
| `data-asg-summary-completion` | — (только селектор) | — |
| `data-asg-summary-deadline` | — (только селектор) | `templates/assignment.html` |
| `data-asg-summary-difficulty` | — (только селектор) | `templates/assignment.html` |
| `data-asg-summary-eta` | — (только селектор) | `templates/assignment.html` |
| `data-asg-summary-eta-row` | — (только селектор) | `templates/assignment.html` |
| `data-asg-summary-price` | — (только селектор) | — |
| `data-asg-summary-sources` | — (только селектор) | — |
| `data-asg-summary-total` | — (только селектор) | `templates/assignment.html` |
| `data-asg-summary-type` | — (только селектор) | `templates/assignment.html` |
| `data-asg-summary-words` | — (только селектор) | `templates/assignment.html` |
| `data-asg-thread` | — (только селектор) | `templates/assignment.html` |
| `data-asg-thread-download` | — (только селектор) | — |
| `data-asg-thread-pay` | — (только селектор) | — |
| `data-asg-wizard` | — (только селектор) | `templates/assignment.html` |
| `data-asg-wizard-back` | — (только селектор) | `templates/assignment.html` |
| `data-asg-wizard-card` | — (только селектор) | `templates/assignment.html` |
| `data-asg-wizard-error` | — (только селектор) | `templates/assignment.html` |
| `data-asg-wizard-primary` | — (только селектор) | `templates/assignment.html` |
| `data-asg-wizard-status` | — (только селектор) | `templates/assignment.html` |
| `data-assignment-page` | — (только селектор) | `templates/assignment.html` |
| `data-auth-backdrop` | — (только селектор) | — |
| `data-auth-close` | — (только селектор) | `templates/_register_wall.html` |
| `data-auth-error` | — (только селектор) | `templates/_register_wall.html` |
| `data-auth-form` | `static/auth-modal.js` | `templates/_register_wall.html` |
| `data-auth-layer` | — (только селектор) | `templates/_register_wall.html` |
| `data-auth-reason` | — (только селектор) | `templates/_register_wall.html` |
| `data-auth-tab` | `static/auth-modal.js` | `templates/_register_wall.html` |
| `data-auth-title` | — (только селектор) | `templates/_register_wall.html` |
| `data-avatar-form` | — (только селектор) | `templates/account.html` |
| `data-avatar-status` | — (только селектор) | `templates/account.html` |
| `data-citation-style-select` | — (только селектор) | `templates/index.html` |
| `data-cmd` | `static/workspace/workspace-app.js` | `templates/workspace.html` |
| `data-cmd-block` | — (только селектор) | `templates/workspace.html` |
| `data-coin-balance` | `static/turnitin-page.js` | `templates/base.html`, `templates/workspace.html` |
| `data-default-label` | `static/assignment-page.js` | — |
| `data-dm-fingerprint` | — (только селектор) | `templates/register.html` |
| `data-dm-register-form` | — (только селектор) | `templates/register.html` |
| `data-dm-tour` | `static/tour.js` | ставит JS |
| `data-dm-tour-back` | — (только селектор) | — |
| `data-dm-tour-backdrop` | — (только селектор) | — |
| `data-dm-tour-body` | — (только селектор) | — |
| `data-dm-tour-card` | — (только селектор) | — |
| `data-dm-tour-close` | — (только селектор) | — |
| `data-dm-tour-next` | — (только селектор) | — |
| `data-dm-tour-page` | `static/tour.js` | `templates/assignment.html`, `templates/check.html`, `templates/humanizer.html`, `templates/index.html`, `templates/turnitin.html` |
| `data-dm-tour-progress` | — (только селектор) | — |
| `data-dm-tour-spot` | — (только селектор) | — |
| `data-dm-tour-title` | — (только селектор) | — |
| `data-dm-tutorial` | — (только селектор) | `templates/_tutorial_btn.html` |
| `data-earn-balance` | — (только селектор) | `templates/earn.html` |
| `data-earn-code` | — (только селектор) | `templates/earn.html` |
| `data-earn-convert` | — (только селектор) | `templates/earn.html` |
| `data-earn-copy` | — (только селектор) | `templates/earn.html` |
| `data-earn-free-tt` | — (только селектор) | `templates/earn.html` |
| `data-earn-link` | — (только селектор) | `templates/earn.html` |
| `data-earn-page` | — (только селектор) | `templates/earn.html` |
| `data-earn-pro-badge` | — (только селектор) | `templates/earn.html` |
| `data-earn-progress-bar` | — (только селектор) | `templates/earn.html` |
| `data-earn-progress-fill` | — (только селектор) | `templates/earn.html` |
| `data-earn-qualifying` | — (только селектор) | `templates/earn.html` |
| `data-earn-ref` | `static/earn-page.js` | ставит JS |
| `data-earn-ref-toggle` | — (только селектор) | — |
| `data-earn-refs` | — (только селектор) | `templates/earn.html` |
| `data-earn-refs-count` | — (только селектор) | `templates/earn.html` |
| `data-earn-refs-empty` | — (только селектор) | `templates/earn.html` |
| `data-earn-status` | — (только селектор) | `templates/earn.html` |
| `data-earn-steps` | — (только селектор) | `templates/earn.html` |
| `data-earn-total-refs` | — (только селектор) | `templates/earn.html` |
| `data-earn-withdraw` | — (только селектор) | `templates/earn.html` |
| `data-earn-withdraw-amount` | — (только селектор) | `templates/earn.html` |
| `data-earn-withdraw-close` | — (только селектор) | `templates/earn.html` |
| `data-earn-withdraw-form` | — (только селектор) | `templates/earn.html` |
| `data-earn-withdraw-modal` | — (только селектор) | `templates/earn.html` |
| `data-earn-withdraw-wallet` | — (только селектор) | `templates/earn.html` |
| `data-evidence-for` | `static/format_v2.js` | `templates/format_v2.html` |
| `data-force-disabled` | `static/assignment-page.js` | — |
| `data-format-v2` | — (только селектор) | `templates/format_v2.html` |
| `data-home-brief-card` | — (только селектор) | `templates/index.html` |
| `data-home-brief-segment` | — (только селектор) | `templates/index.html` |
| `data-home-brief-source` | `static/home.js` | `templates/index.html` |
| `data-home-doc-card` | — (только селектор) | `templates/index.html` |
| `data-home-doc-panel` | `static/home.js` | `templates/index.html` |
| `data-home-doc-segment` | — (только селектор) | `templates/index.html` |
| `data-home-doc-source` | `static/home.js` | `templates/index.html` |
| `data-home-drop-zone` | `static/home.js` | `templates/index.html` |
| `data-home-zone-overlay` | — (только селектор) | `templates/index.html` |
| `data-humanizer-page` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-clear` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-copy` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-copy-icon` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-copy-label` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-drop-overlay` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-error` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-error-msg` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-file` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-font` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-format` | `static/humanizer-page.js` | `templates/humanizer.html` |
| `data-hz-input` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-loading` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-out-words` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-output` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-paste-focus` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-result` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-run` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-run-icon` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-run-label` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-run-spinner` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-segment` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-source` | `static/humanizer-page.js` | `templates/humanizer.html` |
| `data-hz-stage` | — (только селектор) | `templates/humanizer.html` |
| `data-hz-wordcount` | — (только селектор) | `templates/humanizer.html` |
| `data-kind` | `static/assignment-page.js` | ставит JS |
| `data-mark-id` | `static/workspace/workspace-app.js` | — |
| `data-msg-id` | `static/support-chat.js` | — |
| `data-orig-text` | `static/ui.js` | — |
| `data-pinned` | `static/workspace/workspace-app.js` | — |
| `data-preset` | `static/home.js` | `templates/index.html` |
| `data-preview-after` | — (только селектор) | — |
| `data-preview-before` | — (только селектор) | — |
| `data-preview-diff` | — (только селектор) | — |
| `data-quote` | `static/workspace/workspace-app.js` | — |
| `data-sidebar-brand` | — (только селектор) | `templates/base.html` |
| `data-sidebar-close` | — (только селектор) | `templates/base.html` |
| `data-sidebar-collapse` | — (только селектор) | `templates/base.html` |
| `data-sidebar-toggle` | — (только селектор) | `templates/base.html` |
| `data-stage` | `static/humanizer-page.js` | `templates/humanizer.html` |
| `data-support-close` | — (только селектор) | `templates/base.html` |
| `data-support-empty` | `static/support-chat.js` | — |
| `data-theme` | `static/common.js`, `templates/base.html#inline` | — |
| `data-theme-delegated` | `static/common.js` | — |
| `data-theme-set` | `static/auth-modal.js`, `static/common.js` | `templates/base.html` |
| `data-theme-toggle` | — (только селектор) | `templates/base.html` |
| `data-tool` | `static/app-shell.js` | `templates/base.html` |
| `data-tool-history` | — (только селектор) | `templates/base.html` |
| `data-tool-history-list` | — (только селектор) | `templates/base.html` |
| `data-tool-new-chat` | — (только селектор) | `templates/base.html` |
| `data-topup` | `static/pricing.js` | `templates/pricing.html` |
| `data-topup-status` | — (только селектор) | `templates/pricing.html` |
| `data-tour` | `static/home.js`, `static/tour-catalog.js`, `static/workspace/tour-steps.js` | `templates/assignment.html`, `templates/check.html`, `templates/humanizer.html`, `templates/index.html`, `templates/turnitin.html`, `templates/workspace.html` |
| `data-tt-cost` | `static/turnitin-page.js` | `templates/turnitin.html` |
| `data-tt-credits` | — (только селектор) | — |
| `data-tt-delete` | `static/turnitin-page.js` | ставит JS |
| `data-tt-download` | `static/turnitin-page.js` | ставит JS |
| `data-tt-drop-overlay` | — (только селектор) | `templates/turnitin.html` |
| `data-tt-empty` | — (только селектор) | `templates/turnitin.html` |
| `data-tt-file` | — (только селектор) | `templates/turnitin.html` |
| `data-tt-filename` | — (только селектор) | `templates/turnitin.html` |
| `data-tt-get-highlights` | `static/turnitin-page.js` | ставит JS |
| `data-tt-kind` | `static/turnitin-page.js` | ставит JS |
| `data-tt-opt` | `static/turnitin-page.js` | `templates/turnitin.html` |
| `data-tt-reports-body` | — (только селектор) | `templates/turnitin.html` |
| `data-tt-row` | `static/turnitin-page.js` | ставит JS |
| `data-tt-search` | — (только селектор) | `templates/turnitin.html` |
| `data-tt-submit` | — (только селектор) | `templates/turnitin.html` |
| `data-tt-submit-status` | — (только селектор) | `templates/turnitin.html` |
| `data-turnitin-page` | — (только селектор) | `templates/turnitin.html` |
| `data-user-menu` | — (только селектор) | `templates/base.html` |
| `data-user-menu-panel` | — (только селектор) | `templates/base.html` |
| `data-user-menu-toggle` | — (только селектор) | `templates/base.html` |
| `data-v2-depends-on` | `static/format_v2.js` | `templates/format_v2.html` |
| `data-v2-doc-card` | — (только селектор) | `templates/format_v2.html` |
| `data-v2-doc-panel` | `static/format_v2.js` | `templates/format_v2.html` |
| `data-v2-doc-segment` | — (только селектор) | `templates/format_v2.html` |
| `data-v2-doc-source` | `static/format_v2.js` | `templates/format_v2.html` |
| `data-v2-drop-zone` | — (только селектор) | `templates/format_v2.html` |
| `data-v2-field` | `static/format_v2.js` | `templates/format_v2.html` |
| `data-v2-style` | `static/format_v2.js` | `templates/format_v2.html` |
| `data-v2-toggle` | — (только селектор) | `templates/format_v2.html` |
| `data-v2-zone-overlay` | — (только селектор) | `templates/format_v2.html` |
| `data-workspace` | — (только селектор) | `templates/workspace.html` |
| `data-ws-ai-action` | `static/workspace/workspace-app.js` | `templates/workspace.html` |
| `data-ws-ai-apply` | — (только селектор) | `templates/workspace.html` |
| `data-ws-back` | — (только селектор) | `templates/workspace.html` |
| `data-ws-charcount` | — (только селектор) | `templates/workspace.html` |
| `data-ws-cite-insert` | `static/workspace/workspace-app.js` | ставит JS |
| `data-ws-cite-query` | — (только селектор) | `templates/workspace.html` |
| `data-ws-cite-ref` | `static/workspace/workspace-app.js` | ставит JS |
| `data-ws-cite-results` | — (только селектор) | `templates/workspace.html` |
| `data-ws-cite-scan` | — (только селектор) | `templates/workspace.html` |
| `data-ws-cite-search` | — (только селектор) | `templates/workspace.html` |
| `data-ws-cite-style` | — (только селектор) | `templates/workspace.html` |
| `data-ws-comment-add` | — (только селектор) | `templates/workspace.html` |
| `data-ws-comment-input` | — (только селектор) | `templates/workspace.html` |
| `data-ws-comment-quote` | — (только селектор) | `templates/workspace.html` |
| `data-ws-comments-list` | — (только селектор) | `templates/workspace.html` |
| `data-ws-detect` | — (только селектор) | `templates/workspace.html` |
| `data-ws-doc-title` | — (только селектор) | `templates/workspace.html` |
| `data-ws-dropzone` | — (только селектор) | `templates/workspace.html` |
| `data-ws-editor` | — (только селектор) | `templates/workspace.html` |
| `data-ws-editor-surface` | — (только селектор) | `templates/workspace.html` |
| `data-ws-export` | — (только селектор) | `templates/workspace.html` |
| `data-ws-fb` | `static/workspace/workspace-app.js` | `templates/workspace.html` |
| `data-ws-flagged-parts` | — (только селектор) | `templates/workspace.html` |
| `data-ws-flagged-words` | — (только селектор) | `templates/workspace.html` |
| `data-ws-floatbar` | — (только селектор) | `templates/workspace.html` |
| `data-ws-history-btn` | — (только селектор) | `templates/workspace.html` |
| `data-ws-hl-index` | — (только селектор) | `templates/workspace.html` |
| `data-ws-hl-next` | — (только селектор) | `templates/workspace.html` |
| `data-ws-hl-prev` | — (только селектор) | `templates/workspace.html` |
| `data-ws-hl-toggle` | — (только селектор) | `templates/workspace.html` |
| `data-ws-humanize-run` | — (только селектор) | `templates/workspace.html` |
| `data-ws-import-input` | — (только селектор) | `templates/workspace.html` |
| `data-ws-landing` | — (только селектор) | `templates/workspace.html` |
| `data-ws-mark` | — (только селектор) | `templates/workspace.html` |
| `data-ws-mark-all-ai` | — (только селектор) | `templates/workspace.html` |
| `data-ws-new-blank` | — (только селектор) | `templates/workspace.html` |
| `data-ws-open-sample` | — (только селектор) | `templates/workspace.html` |
| `data-ws-open-turnitin` | — (только селектор) | `templates/workspace.html` |
| `data-ws-panel` | `static/workspace.js`, `static/workspace/workspace-app.js` | `templates/workspace.html` |
| `data-ws-pending-cost` | — (только селектор) | `templates/workspace.html` |
| `data-ws-pending-count` | — (только селектор) | `templates/workspace.html` |
| `data-ws-pending-words` | — (только селектор) | `templates/workspace.html` |
| `data-ws-progress` | — (только селектор) | `templates/workspace.html` |
| `data-ws-progress-bar` | — (только селектор) | `templates/workspace.html` |
| `data-ws-recent-words` | — (только селектор) | `templates/workspace.html` |
| `data-ws-refs` | `static/workspace/workspace-app.js` | — |
| `data-ws-saved` | — (только селектор) | `templates/workspace.html` |
| `data-ws-share` | — (только селектор) | `templates/workspace.html` |
| `data-ws-tab` | `static/workspace.js`, `static/workspace/workspace-app.js` | `templates/workspace.html` |
| `data-ws-toast` | — (только селектор) | `templates/workspace.html` |
| `data-ws-topup` | — (только селектор) | — |
| `data-ws-tour` | — (только селектор) | `templates/workspace.html` |
| `data-ws-tour-back` | — (только селектор) | `templates/workspace.html` |
| `data-ws-tour-backdrop` | — (только селектор) | `templates/workspace.html` |
| `data-ws-tour-body` | — (только селектор) | `templates/workspace.html` |
| `data-ws-tour-card` | — (только селектор) | `templates/workspace.html` |
| `data-ws-tour-close` | — (только селектор) | `templates/workspace.html` |
| `data-ws-tour-next` | — (только селектор) | `templates/workspace.html` |
| `data-ws-tour-progress` | — (только селектор) | `templates/workspace.html` |
| `data-ws-tour-spot` | — (только селектор) | `templates/workspace.html` |
| `data-ws-tour-title` | — (только селектор) | `templates/workspace.html` |
| `data-ws-unmark` | — (только селектор) | `templates/workspace.html` |
| `data-ws-unmark-all` | — (только селектор) | `templates/workspace.html` |
| `data-ws-wordcount` | — (только селектор) | `templates/workspace.html` |

## 4. CSS-классы состояния (`classList`)

Классы, которыми JS управляет UI-состоянием.

| Класс | Операции | В templates? |
|---|---|---|
| `adm-status--err` | toggle:1 | нет / runtime |
| `adm-status--error` | toggle:8 | нет / runtime |
| `app-sidebar-backdrop` | contains:1 | да |
| `asg-bubble` | contains:1 | нет / runtime |
| `asg-bubble--card` | add:8 | нет / runtime |
| `asg-bubble--user` | contains:1 | нет / runtime |
| `asg-page--production` | remove:2 | нет / runtime |
| `bar-high` | add:2 | нет / runtime |
| `bar-low` | add:4 | нет / runtime |
| `bar-mid` | add:4 | нет / runtime |
| `hidden` | add:6, contains:4, remove:10, toggle:2 | да |
| `hz-reveal` | add:2, remove:4 | нет / runtime |
| `is-active` | add:2, remove:2, toggle:16 | да |
| `is-copied` | add:2, remove:2 | нет / runtime |
| `is-current` | add:2, remove:2 | нет / runtime |
| `is-disabled` | toggle:1 | нет / runtime |
| `is-drag` | add:2, remove:2 | нет / runtime |
| `is-dragging-files` | toggle:5 | нет / runtime |
| `is-drop-active` | remove:2, toggle:2 | нет / runtime |
| `is-error` | toggle:1 | нет / runtime |
| `is-hidden` | remove:2 | да |
| `is-loading` | add:2, remove:2, toggle:1 | нет / runtime |
| `is-on` | contains:1, toggle:1 | да |
| `is-open` | add:2, contains:1, remove:4, toggle:2 | нет / runtime |
| `is-upload` | toggle:4 | нет / runtime |
| `is-visible` | add:4, contains:1, remove:4 | нет / runtime |
| `is-warn` | toggle:2 | нет / runtime |
| `score-high` | add:2, remove:2 | нет / runtime |
| `score-low` | add:2, remove:1 | нет / runtime |
| `score-mid` | add:2, remove:1, replace-to:1 | нет / runtime |
| `sidebar-collapsed` | contains:2, remove:2, toggle:1 | нет / runtime |
| `sidebar-open` | add:2, contains:1, remove:2 | нет / runtime |
| `structure-high` | add:2, remove:2 | нет / runtime |
| `structure-low` | add:2, remove:1 | нет / runtime |
| `structure-mid` | add:2, remove:1, replace-to:1 | нет / runtime |
| `support-chat-open` | add:2, remove:2 | нет / runtime |
| `v2-chat-summary--error` | add:2, remove:2 | нет / runtime |
| `v2-page-preview__line--indent` | add:2 | нет / runtime |
| `ws-ai-highlight` | contains:1, remove:2 | нет / runtime |
| `ws-hl-hidden` | toggle:1 | нет / runtime |
| `ws-humanized-failed` | add:6 | нет / runtime |
| `ws-mark` | add:2, contains:2, remove:2 | нет / runtime |

## 5. Inline `onclick` / `onchange` в HTML

**Не найдено** в `templates/`. События через `addEventListener` / делегирование в JS.

## НЕ ПЕРЕИМЕНОВЫВАТЬ

Сводный контракт. Визуальные обёртки можно менять; эти идентификаторы — API между HTML ↔ JS ↔ Flask.

### id

- `#alignment`
- `#analyze_requirements_btn`
- `#app_toast_container`
- `#apply_detected_requirements_btn`
- `#auto_headings`
- `#auto_justify_refs`
- `#check_action_plan`
- `#check_categories_list`
- `#check_citation_list`
- `#check_compliance_list`
- `#check_compliance_text`
- `#check_doc_type`
- `#check_document_btn`
- `#check_file`
- `#check_fix_first`
- `#check_issues_list`
- `#check_needs_list`
- `#check_next_steps`
- `#check_parser_empty`
- `#check_pasted_text`
- `#check_positives_list`
- `#check_requirements`
- `#check_requirements_file`
- `#check_results`
- `#check_score_ring`
- `#check_score_value`
- `#check_status`
- `#check_summary`
- `#check_top_problems`
- `#check_validations_list`
- `#check_verdict`
- `#citations_count`
- `#citations_preview_list`
- `#citations_status`
- `#clean_extra_linebreaks`
- `#clean_extra_spaces`
- `#cover_file`
- `#cover_file_status`
- `#detected_requirements_card`
- `#detected_requirements_list`
- `#detected_requirements_summary`
- `#document_type`
- `#editor_save_status`
- `#editor_stats`
- `#editor_surface`
- `#file`
- `#first_line_indent`
- `#font_family`
- `#font_size`
- `#format_btn`
- `#format_status`
- `#format_style`
- `#generate_citations_btn`
- `#generate_references_btn`
- `#heading_all_caps`
- `#home_preview_section`
- `#home_workspace_cta`
- `#include_cover_page`
- `#line_spacing`
- `#margin_preset`
- `#page_number_position`
- `#pasted_text`
- `#preview_changes_btn`
- `#references_count`
- `#references_preview_list`
- `#references_status`
- `#requirement_headings`
- `#requirements_attach`
- `#requirements_attach_btn`
- `#requirements_status`
- `#requirements_text`
- `#space_after_pt`
- `#space_before_pt`
- `#structure_detected_sections`
- `#structure_heading_issues`
- `#structure_health_score`
- `#structure_missing_sections`
- `#structure_paragraph_issues`
- `#structure_recovery_meta`
- `#structure_suggestions`
- `#structure_tree`
- `#support_chat_layer`
- `#support_chat_message`
- `#support_chat_send`
- `#support_chat_status`
- `#support_chat_thread`
- `#support_chat_toggle`
- `#v2_abbr_enabled`
- `#v2_abbr_entries`
- `#v2_alignment`
- `#v2_appendices_enabled`
- `#v2_appendices_lettered`
- `#v2_captions_enabled`
- `#v2_chat_history`
- `#v2_chat_history_empty`
- `#v2_chat_history_wrap`
- `#v2_chat_message`
- `#v2_chat_panel`
- `#v2_chat_pending`
- `#v2_chat_rejected`
- `#v2_chat_send`
- `#v2_chat_summary`
- `#v2_chat_undo`
- `#v2_citation_style_override`
- `#v2_cover_course`
- `#v2_cover_date`
- `#v2_cover_enabled`
- `#v2_cover_lecturer`
- `#v2_cover_student`
- `#v2_cover_title`
- `#v2_download_latest`
- `#v2_drop_placeholder`
- `#v2_expected_sections`
- `#v2_figure_position`
- `#v2_file`
- `#v2_file_name`
- `#v2_first_line_indent`
- `#v2_font_family`
- `#v2_font_size`
- `#v2_format_btn`
- `#v2_format_status`
- `#v2_format_style`
- `#v2_heading_size_pt`
- `#v2_line_spacing`
- `#v2_margin_preset`
- `#v2_notices`
- `#v2_notices_list`
- `#v2_page_number_position`
- `#v2_page_preview`
- `#v2_page_preview_inner`
- `#v2_page_size`
- `#v2_parse_btn`
- `#v2_pasted_text`
- `#v2_preview_cover`
- `#v2_preview_pagenum`
- `#v2_preview_summary`
- `#v2_profile_summary`
- `#v2_refs_enabled`
- `#v2_refs_heading`
- `#v2_refs_new_page`
- `#v2_refs_numbered`
- `#v2_requirements_status`
- `#v2_requirements_text`
- `#v2_style_hint`
- `#v2_table_position`
- `#v2_toc_enabled`
- `#v2_toc_field_based`
- `#v2_toc_max_depth`
- `#workspace_coin_count`
- `#workspace_doc_title`
- `#workspace_editor`
- `#workspace_save_status`
- `#workspace_stats`

### name (Flask form / files / values)

- `name="action"`
- `name="alignment"`
- `name="assignment_brief"`
- `name="auto_headings"`
- `name="auto_justify_refs"`
- `name="avatar"`
- `name="chargebacked"`
- `name="citation_style"`
- `name="clean_extra_linebreaks"`
- `name="clean_extra_spaces"`
- `name="code"`
- `name="confirm_password"`
- `name="cover_assignment_title"`
- `name="cover_file"`
- `name="cover_lecturer"`
- `name="cover_module"`
- `name="cover_student_id"`
- `name="cover_student_name"`
- `name="cover_submission_date"`
- `name="cover_university"`
- `name="current_password"`
- `name="deadline"`
- `name="device_fingerprint"`
- `name="document_type"`
- `name="email"`
- `name="exclude_bibliography"`
- `name="exclude_quotes"`
- `name="file"`
- `name="files"`
- `name="first_line_indent"`
- `name="font_family"`
- `name="font_size"`
- `name="format_style"`
- `name="heading_all_caps"`
- `name="heading_size_pt"`
- `name="image"`
- `name="include_cover_page"`
- `name="lecture_notes"`
- `name="line_spacing"`
- `name="margin_preset"`
- `name="message"`
- `name="name"`
- `name="new_password"`
- `name="next"`
- `name="note"`
- `name="overrides"`
- `name="page_number_position"`
- `name="parsed_requirements"`
- `name="password"`
- `name="password_confirm"`
- `name="pasted_text"`
- `name="ref"`
- `name="references"`
- `name="referral_code"`
- `name="refunded"`
- `name="requirement_headings"`
- `name="requirements"`
- `name="requirements_text"`
- `name="rubric"`
- `name="space_after_pt"`
- `name="space_before_pt"`
- `name="structure_recovery_debug"`
- `name="style"`
- `name="style_preset"`
- `name="title"`
- `name="verification_code"`

### query / values (`request.args` / `request.values`)

- `?after_id=` (или form field с тем же именем)
- `?feature=` (или form field с тем же именем)
- `?limit=` (или form field с тем же именем)
- `?next=` (или form field с тем же именем)
- `?offset=` (или form field с тем же именем)
- `?q=` (или form field с тем же именем)
- `?ref=` (или form field с тем же именем)
- `?referral_code=` (или form field с тем же именем)
- `?search=` (или form field с тем же именем)
- `?secret=` (или form field с тем же именем)
- `?status=` (или form field с тем же именем)
- `?top=` (или form field с тем же именем)

### data-*

- `data-adm-admin-toggle`
- `data-adm-analytics-refresh`
- `data-adm-analytics-status`
- `data-adm-auto-enabled`
- `data-adm-auto-min`
- `data-adm-auto-time`
- `data-adm-balance-form`
- `data-adm-balance-input`
- `data-adm-body`
- `data-adm-dataset-assignment`
- `data-adm-dataset-page`
- `data-adm-dataset-refresh`
- `data-adm-dataset-standalone`
- `data-adm-dataset-status`
- `data-adm-dataset-total`
- `data-adm-dataset-workspace`
- `data-adm-delete`
- `data-adm-delete-email`
- `data-adm-detector-auto`
- `data-adm-detector-manual`
- `data-adm-detector-samples`
- `data-adm-detector-total`
- `data-adm-discount-live`
- `data-adm-empty`
- `data-adm-humanizer-samples`
- `data-adm-kpi-avg-credits`
- `data-adm-kpi-avg-purchase`
- `data-adm-kpi-feature`
- `data-adm-kpi-revenue`
- `data-adm-kpi-sold`
- `data-adm-kpi-used`
- `data-adm-ledger`
- `data-adm-ledger-balance`
- `data-adm-ledger-body`
- `data-adm-ledger-close`
- `data-adm-ledger-count`
- `data-adm-ledger-empty`
- `data-adm-ledger-overlay`
- `data-adm-ledger-status`
- `data-adm-ledger-subtitle`
- `data-adm-promo-active`
- `data-adm-promo-form`
- `data-adm-promo-limit`
- `data-adm-promo-percent`
- `data-adm-purchases`
- `data-adm-purchases-body`
- `data-adm-purchases-close`
- `data-adm-purchases-count`
- `data-adm-purchases-empty`
- `data-adm-purchases-overlay`
- `data-adm-purchases-status`
- `data-adm-purchases-subtitle`
- `data-adm-row`
- `data-adm-search`
- `data-adm-stats`
- `data-adm-status`
- `data-adm-today-date`
- `data-adm-today-humanizer`
- `data-adm-today-humanizer-limit`
- `data-adm-today-humanizer-used`
- `data-adm-today-refresh`
- `data-adm-today-status`
- `data-adm-today-turnitin`
- `data-adm-top-countries`
- `data-adm-top-countries-empty`
- `data-adm-top-customers`
- `data-adm-top-customers-empty`
- `data-adm-total-users`
- `data-adm-turnitin-balance`
- `data-adm-usage`
- `data-adm-usage-body`
- `data-adm-usage-close`
- `data-adm-usage-count`
- `data-adm-usage-empty`
- `data-adm-usage-overlay`
- `data-adm-usage-status`
- `data-adm-usage-subtitle`
- `data-adm-withdrawal-approve`
- `data-adm-withdrawal-reject`
- `data-adm-withdrawal-row`
- `data-adm-withdrawals-body`
- `data-adm-withdrawals-empty`
- `data-adm-withdrawals-refresh`
- `data-adm-withdrawals-status`
- `data-admin-page`
- `data-ai-part`
- `data-analysis-panel`
- `data-analysis-tab`
- `data-asg-analysis-status`
- `data-asg-analyze`
- `data-asg-attach`
- `data-asg-chat-scroll`
- `data-asg-chip-remove`
- `data-asg-chips`
- `data-asg-complete`
- `data-asg-complete-download`
- `data-asg-complete-download-secondary`
- `data-asg-composer-form`
- `data-asg-continue`
- `data-asg-drop-overlay`
- `data-asg-empty`
- `data-asg-files`
- `data-asg-new-chat`
- `data-asg-note`
- `data-asg-overall-progress`
- `data-asg-overall-progress-bar`
- `data-asg-page-error`
- `data-asg-price-breakdown`
- `data-asg-production`
- `data-asg-production-fill`
- `data-asg-production-pct`
- `data-asg-project-eta`
- `data-asg-project-header`
- `data-asg-project-name`
- `data-asg-project-stage`
- `data-asg-project-started`
- `data-asg-project-status`
- `data-asg-project-updated`
- `data-asg-revchat-form`
- `data-asg-revchat-input`
- `data-asg-revchat-meta`
- `data-asg-revchat-thread`
- `data-asg-send`
- `data-asg-summary-citation`
- `data-asg-summary-coins`
- `data-asg-summary-completion`
- `data-asg-summary-deadline`
- `data-asg-summary-difficulty`
- `data-asg-summary-eta`
- `data-asg-summary-eta-row`
- `data-asg-summary-price`
- `data-asg-summary-sources`
- `data-asg-summary-total`
- `data-asg-summary-type`
- `data-asg-summary-words`
- `data-asg-thread`
- `data-asg-thread-download`
- `data-asg-thread-pay`
- `data-asg-wizard`
- `data-asg-wizard-back`
- `data-asg-wizard-card`
- `data-asg-wizard-error`
- `data-asg-wizard-primary`
- `data-asg-wizard-status`
- `data-assignment-page`
- `data-auth-backdrop`
- `data-auth-close`
- `data-auth-error`
- `data-auth-form`
- `data-auth-layer`
- `data-auth-reason`
- `data-auth-tab`
- `data-auth-title`
- `data-avatar-form`
- `data-avatar-status`
- `data-citation-style-select`
- `data-cmd`
- `data-cmd-block`
- `data-coin-balance`
- `data-default-label`
- `data-dm-fingerprint`
- `data-dm-register-form`
- `data-dm-tour`
- `data-dm-tour-back`
- `data-dm-tour-backdrop`
- `data-dm-tour-body`
- `data-dm-tour-card`
- `data-dm-tour-close`
- `data-dm-tour-next`
- `data-dm-tour-page`
- `data-dm-tour-progress`
- `data-dm-tour-spot`
- `data-dm-tour-title`
- `data-dm-tutorial`
- `data-earn-balance`
- `data-earn-code`
- `data-earn-convert`
- `data-earn-copy`
- `data-earn-free-tt`
- `data-earn-link`
- `data-earn-page`
- `data-earn-pro-badge`
- `data-earn-progress-bar`
- `data-earn-progress-fill`
- `data-earn-qualifying`
- `data-earn-ref`
- `data-earn-ref-toggle`
- `data-earn-refs`
- `data-earn-refs-count`
- `data-earn-refs-empty`
- `data-earn-status`
- `data-earn-steps`
- `data-earn-total-refs`
- `data-earn-withdraw`
- `data-earn-withdraw-amount`
- `data-earn-withdraw-close`
- `data-earn-withdraw-form`
- `data-earn-withdraw-modal`
- `data-earn-withdraw-wallet`
- `data-evidence-for`
- `data-force-disabled`
- `data-format-v2`
- `data-home-brief-card`
- `data-home-brief-segment`
- `data-home-brief-source`
- `data-home-doc-card`
- `data-home-doc-panel`
- `data-home-doc-segment`
- `data-home-doc-source`
- `data-home-drop-zone`
- `data-home-zone-overlay`
- `data-humanizer-page`
- `data-hz-clear`
- `data-hz-copy`
- `data-hz-copy-icon`
- `data-hz-copy-label`
- `data-hz-drop-overlay`
- `data-hz-error`
- `data-hz-error-msg`
- `data-hz-file`
- `data-hz-font`
- `data-hz-format`
- `data-hz-input`
- `data-hz-loading`
- `data-hz-out-words`
- `data-hz-output`
- `data-hz-paste-focus`
- `data-hz-result`
- `data-hz-run`
- `data-hz-run-icon`
- `data-hz-run-label`
- `data-hz-run-spinner`
- `data-hz-segment`
- `data-hz-source`
- `data-hz-stage`
- `data-hz-wordcount`
- `data-kind`
- `data-mark-id`
- `data-msg-id`
- `data-orig-text`
- `data-pinned`
- `data-preset`
- `data-preview-after`
- `data-preview-before`
- `data-preview-diff`
- `data-quote`
- `data-sidebar-brand`
- `data-sidebar-close`
- `data-sidebar-collapse`
- `data-sidebar-toggle`
- `data-stage`
- `data-support-close`
- `data-support-empty`
- `data-theme`
- `data-theme-delegated`
- `data-theme-set`
- `data-theme-toggle`
- `data-tool`
- `data-tool-history`
- `data-tool-history-list`
- `data-tool-new-chat`
- `data-topup`
- `data-topup-status`
- `data-tour`
- `data-tt-cost`
- `data-tt-credits`
- `data-tt-delete`
- `data-tt-download`
- `data-tt-drop-overlay`
- `data-tt-empty`
- `data-tt-file`
- `data-tt-filename`
- `data-tt-get-highlights`
- `data-tt-kind`
- `data-tt-opt`
- `data-tt-reports-body`
- `data-tt-row`
- `data-tt-search`
- `data-tt-submit`
- `data-tt-submit-status`
- `data-turnitin-page`
- `data-user-menu`
- `data-user-menu-panel`
- `data-user-menu-toggle`
- `data-v2-depends-on`
- `data-v2-doc-card`
- `data-v2-doc-panel`
- `data-v2-doc-segment`
- `data-v2-doc-source`
- `data-v2-drop-zone`
- `data-v2-field`
- `data-v2-style`
- `data-v2-toggle`
- `data-v2-zone-overlay`
- `data-workspace`
- `data-ws-ai-action`
- `data-ws-ai-apply`
- `data-ws-back`
- `data-ws-charcount`
- `data-ws-cite-insert`
- `data-ws-cite-query`
- `data-ws-cite-ref`
- `data-ws-cite-results`
- `data-ws-cite-scan`
- `data-ws-cite-search`
- `data-ws-cite-style`
- `data-ws-comment-add`
- `data-ws-comment-input`
- `data-ws-comment-quote`
- `data-ws-comments-list`
- `data-ws-detect`
- `data-ws-doc-title`
- `data-ws-dropzone`
- `data-ws-editor`
- `data-ws-editor-surface`
- `data-ws-export`
- `data-ws-fb`
- `data-ws-flagged-parts`
- `data-ws-flagged-words`
- `data-ws-floatbar`
- `data-ws-history-btn`
- `data-ws-hl-index`
- `data-ws-hl-next`
- `data-ws-hl-prev`
- `data-ws-hl-toggle`
- `data-ws-humanize-run`
- `data-ws-import-input`
- `data-ws-landing`
- `data-ws-mark`
- `data-ws-mark-all-ai`
- `data-ws-new-blank`
- `data-ws-open-sample`
- `data-ws-open-turnitin`
- `data-ws-panel`
- `data-ws-pending-cost`
- `data-ws-pending-count`
- `data-ws-pending-words`
- `data-ws-progress`
- `data-ws-progress-bar`
- `data-ws-recent-words`
- `data-ws-refs`
- `data-ws-saved`
- `data-ws-share`
- `data-ws-tab`
- `data-ws-toast`
- `data-ws-topup`
- `data-ws-tour`
- `data-ws-tour-back`
- `data-ws-tour-backdrop`
- `data-ws-tour-body`
- `data-ws-tour-card`
- `data-ws-tour-close`
- `data-ws-tour-next`
- `data-ws-tour-progress`
- `data-ws-tour-spot`
- `data-ws-tour-title`
- `data-ws-unmark`
- `data-ws-unmark-all`
- `data-ws-wordcount`

### Классы-состояния

- `.adm-status--err`
- `.adm-status--error`
- `.app-sidebar-backdrop`
- `.asg-bubble`
- `.asg-bubble--card`
- `.asg-bubble--user`
- `.asg-page--production`
- `.bar-high`
- `.bar-low`
- `.bar-mid`
- `.hidden`
- `.hz-reveal`
- `.is-active`
- `.is-copied`
- `.is-current`
- `.is-disabled`
- `.is-drag`
- `.is-dragging-files`
- `.is-drop-active`
- `.is-error`
- `.is-hidden`
- `.is-loading`
- `.is-on`
- `.is-open`
- `.is-upload`
- `.is-visible`
- `.is-warn`
- `.score-high`
- `.score-low`
- `.score-mid`
- `.sidebar-collapsed`
- `.sidebar-open`
- `.structure-high`
- `.structure-low`
- `.structure-mid`
- `.support-chat-open`
- `.v2-chat-summary--error`
- `.v2-page-preview__line--indent`
- `.ws-ai-highlight`
- `.ws-hl-hidden`
- `.ws-humanized-failed`
- `.ws-mark`

### Классы в селекторах

- `.app-shell-main`
- `.app-sidebar-backdrop`
- `.app-sidebar-footer`
- `.app-topbar-account`
- `.asg-wizard-actions`
- `.auth-otp-input`
- `.check-analysis-panel`
- `.check-analysis-tab`
- `.dm-auth-modal`
- `.dm-auth-submit`
- `.doc`
- `.earn-ref`
- `.earn-ref-history`
- `.home-cover-card`
- `.home-layout`
- `.is-open`
- `.nav-account`
- `.preset-chip`
- `.text-settings-card`
- `.theme-toggle-icon--moon`
- `.theme-toggle-icon--sun`
- `.v2-page-preview__line`
- `.ws-ai-highlight`
- `.ws-doc-scroll`
- `.ws-mark`
