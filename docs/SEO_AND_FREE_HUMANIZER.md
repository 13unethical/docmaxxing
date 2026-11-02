# SEO, landings, free humanizer and blog

## Environment variables

All are optional. Add them to `.env` on the server and restart the app.

### Search-engine verification (`services/seo.py`)

Paste only the token (the `content` value), not the whole `<meta>` tag. A tag is printed
in `<head>` only when its variable is set.

| Variable | Meta tag |
| --- | --- |
| `GOOGLE_SITE_VERIFICATION` | `<meta name="google-site-verification">` |
| `YANDEX_VERIFICATION` | `<meta name="yandex-verification">` |
| `BING_SITE_VERIFICATION` | `<meta name="msvalidate.01">` |

### Free humanizer allowance (`services/free_humanize.py`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `FREE_HUMANIZE_GUEST_WORDS` | `500` | Words per free run without an account |
| `FREE_HUMANIZE_GUEST_DAILY` | `1` | Free runs per UTC day without an account (counted per IP + browser session) |
| `FREE_HUMANIZE_GUEST_IP_DAILY` | `3` | Free guest runs per UTC day from one IP across all sessions (clearing cookies doesn't add runs) |
| `FREE_HUMANIZE_USER_WORDS` | `1500` | Words per free run for a signed-in user |
| `FREE_HUMANIZE_USER_DAILY` | `10` | Free runs per UTC day for a signed-in user (counted per user id) |
| `FREE_HUMANIZE_ENGINE` | `student` | `student`: free runs use our own model only; `default`: free runs use the same routing as paid runs |
| `FREE_HUMANIZE_GUEST_RATE_PER_MIN` | `10` | Humanizer requests per minute per IP for guests (in-memory, per worker process) |
| `HUMANIZE_MAX_WORDS` | `5000` | Hard cap on words per request for every humanizer endpoint |

Rules:

- Limits are checked on the server. Counters live in the `free_humanize_usage` table of the
  economy database (created automatically; rows older than 7 days are removed).
- A free run is reserved before the engine starts and released if it fails, so failed free
  runs never count and are never charged.
- Over the free limits, signed-in users pay credits exactly as before (plan allowances,
  discounts and refunds unchanged). Users with an active plan skip the free runs and keep
  the paid routing. Guests are asked to create an account.
- The guest IP is `CF-Connecting-IP` when the request comes from a Cloudflare address,
  otherwise `X-Real-IP` set by nginx.
- Russian text is not supported yet: `/api/browser/providers/ru/humanize` answers
  `RU_NOT_SUPPORTED` (400) and the app shows a message instead of sending Cyrillic text.
  The Veil extension endpoint only gets the `HUMANIZE_MAX_WORDS` cap.

API error codes the widget and the app handle: `TOO_MANY_WORDS` (400), `FREE_WORD_LIMIT`
(403), `REGISTER_REQUIRED` with `reason: FREE_LIMIT_REACHED` (403), `FREE_ENGLISH_ONLY` (422),
`RATE_LIMITED` (429), `FREE_ENGINE_UNAVAILABLE` (503).

## Public pages

- `GUEST_LANDING_PAGES=1` turns the landing pages on. Off (the default), guests go straight
  to the app as before, `/app` is indexed with the root as canonical, and the sitemap drops
  `/humanizer`, `/pricing` and `/formatter`.
- With it on, guests get server-rendered pages on `/`, `/humanizer`, `/pricing` and `/formatter`
  (`/ru/humanizer` also renders but is on hold: noindex, not in the sitemap, not linked); signed-in users are still redirected to `/app#/...`. `?classic=1` shows the
  old pages (marked `noindex`).
- Page titles, descriptions, hreflang and breadcrumbs: `_PAGES` in `services/seo.py`.
- Landing and `/faq` FAQ text: `services/site_content.py` (the same text feeds the FAQPage
  JSON-LD, so they always match).
- Open Graph images and favicon: `python3 scripts/make_og_images.py`.

## Blog

Posts are Markdown files in `content/blog/`. See the docstring of `services/blog.py` for the
front matter fields. `draft: true` posts are never listed, linked or put in the sitemap;
admins can preview them at their URL (shown with `noindex`). To publish, set `draft: false`
(or remove the line) and deploy. `/blog` stays `noindex` and out of the sitemap until at
least one post is published.
