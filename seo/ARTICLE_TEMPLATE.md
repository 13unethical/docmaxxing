# Blog article template (DocMaxxing)

Copy into `content/blog/<slug>.md`. Fill every `TODO` before setting `draft: false`.
H2 headings should mirror the sub-questions for this keyword in `seo/keyword-map.csv`
(column such as `subquestions` / `h2` — one H2 per row item).

```markdown
---
title: TODO — question or clear claim (also the H1)
seo_title: TODO — ≤60 chars, primary keyword near the front
description: TODO — ≤155 chars; answer the query in one or two sentences
date: YYYY-MM-DD
updated: YYYY-MM-DD
author: TODO — real byline (person or “DocMaxxing Editorial”)
lang: en
slug: TODO-kebab-case
# alternate: /ru/blog/same-topic-ru
draft: true
og_image: /static/og/home.webp
primary_keyword: TODO — exact phrase from keyword-map.csv
---

<!-- Lead: answer the search question in the first 2–3 sentences. No throat-clearing. -->

TODO — Direct answer in sentence 1. One clarifying sentence. Optional third sentence
with what the reader will get from the rest of the page. Link one relevant tool if it
helps (e.g. [AI humanizer](/humanizer) or [AI detector](/ai-detector)).

## TODO — H2 from keyword-map.csv sub-question 1

TODO — body. Prefer short paragraphs. Cite Turnitin / GPTZero / vendor docs with a
full URL on first claim.

<!-- Screenshot slot -->
> **Screenshot — TODO-AMAL:** describe the UI state to capture.
> File: `static/blog/<slug>/01-….png` · Alt: “…”

## TODO — H2 from keyword-map.csv sub-question 2

TODO — body.

<!-- Own data / experiment slot -->
> **Own data — TODO-AMAL:** what you measured (n=, tool, date). Table or 2–3 bullets.
> Do not invent numbers — leave this marker until the run is done.

## TODO — H2 from keyword-map.csv sub-question 3

TODO — body.

## TODO — optional extra H2 (only if in the keyword map)

TODO — body.

## Frequently asked questions

### TODO — FAQ question 1 (also a People-Also-Ask phrasing)

TODO — 2–4 sentence answer. Match the visible text if you later add FAQ JSON-LD.

### TODO — FAQ question 2

TODO — answer.

### TODO — FAQ question 3

TODO — answer.

### TODO — FAQ question 4

TODO — answer.

<!-- Add FAQ 5–6 only when they cover a real PAA / keyword-map gap. -->

## Related reading and tools

- [TODO related article 1](/blog/…)
- [TODO related article 2](/blog/…)
- [TODO related article 3](/blog/…) — optional third
- Tool: [TODO — Humanizer / AI detector / Formatter](/humanizer)

## Sources

- TODO — Turnitin / GPTZero / APA / study — full https URL
```

## Rules baked into this template

1. **Answer first.** The lead is the snippet Google and readers see.
2. **H2 = map.** Do not invent sections that are not in `seo/keyword-map.csv` for this keyword unless SERP gaps demand it (note why in the PR).
3. **TODO-AMAL** marks screenshots and first-party data only Amal can finish. A post with any `TODO-AMAL` must stay `draft: true` — tests block publish.
4. **No detector promises.** Never write that text will “100% pass Turnitin”, is “undetectable”, or “guaranteed 0% AI”.
5. **Keyword density.** Primary keyword (and close variants) stay under ~2% of body words.
6. **FAQ 4–6.** Visible on the page; keep answers honest and sourced when they cite vendors.
