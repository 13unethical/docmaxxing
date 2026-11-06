"""Copy shared by public pages and their JSON-LD.

FAQ answers are written as small HTML snippets. The page renders the snippet and the
FAQPage JSON-LD uses the same snippet with tags stripped, so both always say the same thing.
"""

from __future__ import annotations

import html
import re
from typing import Any

FaqItem = tuple[str, str]  # (question, answer HTML)

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def plain_text(snippet: str) -> str:
    return _SPACE.sub(" ", html.unescape(_TAG.sub("", snippet))).strip()


def _costs() -> dict[str, int]:
    from services.economy.pricing import FEATURE_COSTS, WELCOME_BONUS

    return {
        "humanize": int(FEATURE_COSTS["humanize"]),
        "turnitin": int(FEATURE_COSTS["turnitin"]),
        "slides_base": int(FEATURE_COSTS["presentation"]),
        "slides_per": int(FEATURE_COSTS["presentation_slide"]),
        "welcome": int(WELCOME_BONUS),
    }


def _pro_humanize_per_day() -> int:
    from services.economy.plans import PLANS

    return int(PLANS["pro"]["free"]["humanize"][1])


def site_faq_sections() -> list[tuple[str, list[FaqItem]]]:
    """The /faq page, grouped by topic."""
    c = _costs()
    return [
        (
            "Getting started",
            [
                (
                    "Do I need an account?",
                    "No for the basics: you can format documents and try the AI Humanizer as a guest. "
                    "An account is needed to save history, buy credits, run longer humanizer jobs, "
                    "and use the AI check, Assignment, Workspace, Slides and Earn &amp; Share.",
                ),
                (
                    "Where do I buy credits?",
                    'Read the <a href="/credits">Credits</a> guide, then open '
                    '<a href="/pricing">Pricing</a>. Checkout uses Lemon Squeezy. '
                    "Guests are asked to register before checkout.",
                ),
                (
                    "What are welcome credits?",
                    f"New accounts receive <strong>{c['welcome']}</strong> welcome credits. Signing up "
                    "with a referral link also grants <strong>+100</strong> referral bonus credits.",
                ),
            ],
        ),
        (
            "Format",
            [
                (
                    "What files can I upload?",
                    "Paste text or upload DOCX, PDF, TXT or an image of your brief, as shown on the Format page.",
                ),
                (
                    "Which styles are supported?",
                    "Harvard, APA 7, MLA 9, Chicago and IEEE presets, plus custom font, size, spacing, "
                    "margins, cover page, references and citations.",
                ),
                ("Does Format cost credits?", "No. Formatting is free."),
            ],
        ),
        (
            "Humanizer",
            [
                (
                    "What does the Humanizer do?",
                    "It rewrites stiff, AI-sounding prose so it reads like natural writing: varied "
                    "sentence length, plainer word choice, fewer stock phrases. Headings and reference "
                    "lists stay in place. It runs on our own fine-tuned rewriting model together with "
                    "a partner rewriting engine.",
                ),
                (
                    "Can I use it for free?",
                    'Yes. Short texts can be humanized for free every day, with or without an account; '
                    'the current limits are shown next to the Humanize button on the '
                    '<a href="/humanizer">AI Humanizer</a> page.',
                ),
                (
                    "Why might an AI detector still flag my text?",
                    "Detectors are statistical and often disagree with each other, and they sometimes "
                    "flag text written entirely by people. Read the result, edit it in your own voice, "
                    "and check the final document with the tool your school uses.",
                ),
                (
                    "What does a paid run cost?",
                    f"<strong>{c['humanize']} credits</strong> per run once your free runs are used. "
                    "Users with Pro referral status get 10% off paid runs.",
                ),
            ],
        ),
        (
            "Workspace and Slides",
            [
                (
                    "What is Workspace?",
                    "A document editor inside DocMaxxing. Write or paste your paper, humanize a selected "
                    "passage, review suggested changes before accepting them, and export a DOCX.",
                ),
                (
                    "What does Slides do?",
                    "Slides turns a topic or your paper into a presentation. Pick a template, review the "
                    "slides, and download a PowerPoint file. A deck costs "
                    f"<strong>{c['slides_base']} credits</strong> plus <strong>{c['slides_per']}</strong> "
                    "per slide, title slide included; web research and photos are included.",
                ),
            ],
        ),
        (
            "Assignment",
            [
                (
                    "How does Assignment work?",
                    "Upload your brief, review the price and pay once. DocMaxxing then researches, plans, "
                    "writes the sections, adds citations, formats the document, reviews it against the "
                    "brief and delivers a ZIP.",
                ),
                (
                    "How strict is the word count?",
                    "Targets use a ±10% band (for example, 1,200 words means 1,080–1,320). "
                    "Text over the band is trimmed.",
                ),
                (
                    "The download says ready but nothing downloads. What now?",
                    "Press Download again; the package is rebuilt on each request. "
                    "Hard-refresh the page if it looks stale.",
                ),
            ],
        ),
        (
            "AI check",
            [
                (
                    "Is this official Turnitin?",
                    "We provide Turnitin-style similarity and AI reports through configured providers. "
                    "Your institution's Turnitin setup can still give different numbers.",
                ),
                (
                    "What does an AI check cost?",
                    f"<strong>{c['turnitin']} credits</strong> per check. Earn &amp; Share milestones "
                    "can award free detailed reports.",
                ),
            ],
        ),
        (
            "Work Review (Academic Check)",
            [
                (
                    "What does Work Review do?",
                    "Paste your assignment brief and draft, or upload DOCX/PDF, to get a readiness score, "
                    "missing requirements and an action plan.",
                ),
                ("Do I need credits?", "No — Work Review (Academic Check) does not spend credits."),
            ],
        ),
        (
            "Plans and Earn &amp; Share",
            [
                (
                    "Are there monthly plans?",
                    "Yes. Basic, Pro and Max are 30-day passes that add credits and include free "
                    f"generations; Pro, for example, includes {_pro_humanize_per_day()} humanizer runs a "
                    'day. Details are on <a href="/pricing">Pricing</a>.',
                ),
                (
                    "How does referral cashback work?",
                    "When someone you referred makes a deposit, you earn <strong>40%</strong> of that "
                    "amount in your referral balance. Convert it to credits at <strong>1.2×</strong> or "
                    "request a withdrawal from <strong>$50</strong>.",
                ),
            ],
        ),
        (
            "Billing",
            [
                (
                    "Who processes payment?",
                    "Lemon Squeezy handles card and wallet payments as the merchant of record.",
                ),
                (
                    "Can I get a refund?",
                    "All purchases are final. You can cancel a plan at any time and it stays active until "
                    "the end of the paid period. Credits for failed actions return to your balance "
                    'automatically. See the <a href="/refund-policy">Refund Policy</a>.',
                ),
            ],
        ),
    ]


def _n(value: int) -> str:
    return f"{value:,}"


def _n_ru(value: int) -> str:
    return f"{value:,}".replace(",", "\u00a0")


def free_limits_context() -> dict[str, Any]:
    """Free humanizer limits as display strings for landing pages."""
    from services.free_humanize import limits

    lim = limits()
    return {
        "guest_words": lim.guest_words,
        "guest_daily": lim.guest_daily,
        "user_words": lim.user_words,
        "user_daily": lim.user_daily,
        "max_words": lim.max_words,
        "guest_words_s": _n(lim.guest_words),
        "user_words_s": _n(lim.user_words),
        "max_words_s": _n(lim.max_words),
        "guest_daily_s": _times_en(lim.guest_daily),
        "user_daily_s": _times_en(lim.user_daily),
        "guest_words_ru": _n_ru(lim.guest_words),
        "user_words_ru": _n_ru(lim.user_words),
        "max_words_ru": _n_ru(lim.max_words),
        "guest_daily_ru": _times_ru(lim.guest_daily),
        "user_daily_ru": _times_ru(lim.user_daily),
    }


def _times_ru(n: int) -> str:
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} раза"
    return f"{n} раз"


def _times_en(n: int) -> str:
    return "once" if n == 1 else ("twice" if n == 2 else f"{n} times")


def humanizer_en_faq() -> list[FaqItem]:
    f = free_limits_context()
    c = _costs()
    return [
        (
            "Is the AI humanizer really free?",
            f"Yes. Without an account you can humanize up to {f['guest_words_s']} words, "
            f"{_times_en(f['guest_daily'])} a day. A free account raises that to {f['user_words_s']} words, "
            f"{_times_en(f['user_daily'])} a day. Longer texts and extra runs cost {c['humanize']} credits each — "
            'see <a href="/pricing">Pricing</a>.',
        ),
        (
            "Do I need to sign up?",
            "No. You can run the humanizer right on this page. An account gives you a higher free limit, "
            "saved history and the full document editor.",
        ),
        (
            "What does “humanize AI text” mean?",
            "It means rewriting text produced by a language model so it reads the way a person writes: "
            "less predictable phrasing, sentences of different lengths, fewer filler transitions. "
            "The meaning should stay the same.",
        ),
        (
            "Will the result pass AI detectors?",
            "We don’t promise any detector score, and you should be wary of anyone who does. Detectors are "
            "statistical, they often disagree with each other, and they sometimes flag text written entirely "
            "by people. Our goal is natural, readable writing — review the result and follow your "
            "institution’s rules.",
        ),
        (
            "Will it change my meaning or citations?",
            "It shouldn’t. The humanizer aims to keep your argument, numbers and in-text citations, and it "
            "leaves headings and reference lists untouched. Any automatic rewrite can miss a nuance, so read "
            "the output before you use it.",
        ),
        (
            "Which languages does it support?",
            "English only for now. Russian and other languages are not supported yet.",
        ),
        (
            "How long can my text be?",
            f"Free runs take up to {f['guest_words_s']} words without an account and {f['user_words_s']} words "
            f"with one. Paid runs handle up to {f['max_words_s']} words at a time.",
        ),
        (
            "Is it OK to use a humanizer for university work?",
            "That depends on your course. Many universities allow AI help for brainstorming or editing but ask "
            "you to say so. Use the humanizer to improve how your own draft reads, cite your sources, and check "
            "your school’s AI policy.",
        ),
        (
            "How is this different from a paraphrasing tool?",
            "Most paraphrasers swap words for synonyms, which often makes text sound stranger. The humanizer "
            "rewrites whole sentences and paragraphs, changing rhythm and structure while keeping the point.",
        ),
        (
            "What if I don’t like the result?",
            "Edit it by hand or run it again. If a free run fails on our side, it doesn’t count toward your "
            "daily limit.",
        ),
    ]


def humanizer_ru_faq() -> list[FaqItem]:
    f = free_limits_context()
    c = _costs()
    return [
        (
            "Что такое хуманайзер?",
            "Это инструмент, который переписывает текст, созданный нейросетью, так, чтобы он читался как "
            "написанный человеком: без шаблонных связок, с предложениями разной длины и более простыми словами. "
            "Смысл при этом сохраняется.",
        ),
        (
            "Хуманайзер правда бесплатный?",
            f"Да. Без регистрации можно обработать до {f['guest_words_ru']} слов {f['guest_daily_ru']} в день, "
            f"с бесплатным аккаунтом — до {f['user_words_ru']} слов {f['user_daily_ru']} в день. Тексты длиннее "
            f"и дополнительные запуски стоят {c['humanize']} кредитов — подробности на странице "
            '<a href="/pricing">цен</a>.',
        ),
        (
            "Можно ли очеловечить русский текст?",
            "Пока нет. Русскоязычный движок в разработке, и мы не хотим выдавать за него простую замену слов. "
            "Сейчас хуманайзер работает с английскими текстами.",
        ),
        (
            "Нужна ли регистрация?",
            "Нет, английский текст можно обработать прямо на этой странице. Аккаунт даёт больший бесплатный "
            "лимит, историю и полноценный редактор документов.",
        ),
        (
            "Текст точно пройдёт проверку на ИИ?",
            "Мы не обещаем никаких процентов в детекторах — и советуем насторожиться, если кто-то обещает. "
            "Детекторы работают на статистике, часто расходятся между собой и иногда помечают тексты, "
            "полностью написанные людьми. Наша цель — естественный, читаемый текст. Перечитайте результат и "
            "следуйте правилам своего вуза.",
        ),
        (
            "Не исказит ли хуманайзер смысл и ссылки?",
            "Не должен: хуманайзер старается сохранить аргументы, цифры и ссылки в тексте, а заголовки и "
            "список литературы не трогает. Но любая автоматическая правка может упустить нюанс, поэтому "
            "перечитайте результат перед использованием.",
        ),
        (
            "Какой длины текст можно обработать?",
            f"Бесплатно — до {f['guest_words_ru']} слов без аккаунта и до {f['user_words_ru']} слов с аккаунтом. "
            f"Платный запуск обрабатывает до {f['max_words_ru']} слов за раз.",
        ),
        (
            "Можно ли пользоваться хуманайзером для учёбы?",
            "Зависит от правил вашего курса. Многие вузы разрешают помощь ИИ при подготовке и редактуре, но "
            "просят об этом сообщать. Используйте хуманайзер, чтобы улучшить собственный черновик, указывайте "
            "источники и уточните правила своего вуза.",
        ),
        (
            "Чем хуманайзер отличается от синонимайзера?",
            "Синонимайзер меняет слова на синонимы, и текст часто становится только страннее. Хуманайзер "
            "переписывает предложения и абзацы целиком: меняет ритм и построение фраз, но сохраняет мысль.",
        ),
    ]


def home_faq() -> list[FaqItem]:
    f = free_limits_context()
    d = detector_limits_context()
    t = LANDING_TRY
    return [
        (
            "What is DocMaxxing?",
            "A set of writing tools for students in one place: a free AI detector, an AI humanizer, a free "
            "essay formatter, a Turnitin check, a document editor, a slide maker and assignment help.",
        ),
        (
            "Which tools are free?",
            f"The AI detector, the humanizer and formatting. On this page you get {t['free_runs']} free AI checks "
            f"and {t['free_runs']} free humanizer runs a day, up to {t['max_words_s']} words each, no account "
            f"needed. A free account gives you {d['user_daily']} AI checks a day of up to {d['user_words_s']} words "
            f"and {f['user_daily']} humanizer runs a day of up to {f['user_words_s']} words.",
        ),
        (
            "Do I need an account?",
            "Not to try the AI detector, the humanizer or the formatter. An account keeps your history, raises "
            "the free limits and unlocks the editor, slides, the Turnitin check and assignment help.",
        ),
        (
            "How do credits work?",
            'Paid tools spend credits. New accounts get welcome credits, and you can buy plans or one-time '
            'credit packs. See <a href="/credits">how credits work</a> and <a href="/pricing">Pricing</a>.',
        ),
        (
            "Which citation styles does the formatter support?",
            "APA 7, MLA 9, Harvard, Chicago and IEEE, with control over fonts, spacing, margins, the cover page "
            "and the reference list.",
        ),
        (
            "Does the humanizer guarantee a low AI score?",
            "No. Detectors are statistical and inconsistent, and nobody can honestly guarantee a score. "
            "The humanizer focuses on making text read naturally; you should still review and edit it.",
        ),
        (
            "Can I use DocMaxxing in Russian?",
            "Not yet. The site and the humanizer work in English; Russian text is not supported yet.",
        ),
        (
            "How do I get help?",
            'Email <a href="mailto:support@docmaxxing.com">support@docmaxxing.com</a> or use the chat button in '
            'the app. More answers are in the <a href="/faq">FAQ</a>.',
        ),
    ]


def ai_detector_faq() -> list[FaqItem]:
    d = detector_limits_context()
    t = LANDING_TRY
    c = _costs()
    return [
        (
            "Is the AI detector free?",
            f"Yes. Without an account you get {t['free_runs']} checks a day of up to {t['max_words_s']} words "
            f"each. A free account gives you {d['user_daily']} checks a day of up to {d['user_words_s']} words. "
            "No card needed.",
        ),
        (
            "How does the AI detector work?",
            "It scores your text sentence by sentence with a model trained on essays written by students and "
            "by AI tools, then shows the overall AI score and highlights the sentences that look AI-written.",
        ),
        (
            "How accurate is it?",
            "We tune it against real Turnitin reports, so its scores usually land close to what Turnitin shows. "
            "Still, every AI detector is statistical and can be wrong, including on text written entirely by a "
            "person. Treat the score as a hint, not a verdict.",
        ),
        (
            "Is it the same as Turnitin?",
            "No. It is our own detector. If you need the real Turnitin AI and similarity report, use the "
            f"Turnitin check in the app ({c['turnitin']} credits per document).",
        ),
        (
            "What can I do if part of my text is flagged?",
            "Rewrite the flagged sentences in your own words, or run them through the humanizer on this page "
            "and read the result before you use it. Then check again.",
        ),
        (
            "Which languages does it support?",
            "English only for now.",
        ),
        (
            "Do you keep my text?",
            "We use it only to run the check. We don’t publish it or share it with your university. See the "
            '<a href="/privacy">Privacy Policy</a>.',
        ),
    ]


_LANDING_FAQS = {
    "/": home_faq,
    "/ai-detector": ai_detector_faq,
    "/humanizer": humanizer_en_faq,
    "/ru/humanizer": humanizer_ru_faq,
}

# Free tries on the app landing's detector / humanizer box for visitors without an account
# (sent to the app in the boot data, so the page and the box show the same numbers).
LANDING_TRY = {"free_runs": 3, "max_words": 1000, "max_words_s": _n(1000)}


def detector_limits_context() -> dict[str, Any]:
    from services.ai_detector import limits

    lim = limits()
    return {"user_daily": lim.user_daily, "user_words_s": _n(lim.user_words)}


# The app landing at "/", "/ai-detector" and "/humanizer": which tab of the free box opens first,
# the hero title (the page's <h1>) and an "about" block shown under the box.
_TOOL_LANDINGS: dict[str, dict[str, Any]] = {
    "/": {
        "tab": "detect",
        "hero": "Check your text for AI",
        "about_title": "Free AI detector and humanizer for students",
        "about": (
            ("Check for AI before you submit",
             "Paste your essay and get an AI score in seconds, with the sentences that look AI-written "
             "highlighted. No account needed."),
            ("Humanize the flagged parts",
             "Rewrite stiff, AI-sounding sentences so they read like you wrote them, keeping your argument, "
             "numbers and citations."),
            ("Format and submit",
             "Apply APA, MLA, Harvard or Chicago to the whole document for free, then run a Turnitin check if "
             "you want the real report."),
        ),
    },
    "/ai-detector": {
        "tab": "detect",
        "hero": "Free AI Detector",
        "about_title": "Check your essay for AI, free",
        "about": (
            ("Sentence-level highlights",
             "See which sentences look AI-written, not just one number for the whole text."),
            ("Tuned on real Turnitin reports",
             "We compare our scores with Turnitin results on student essays and retrain the detector, so the "
             "score is a useful preview before you submit."),
            ("Fix what’s flagged in one click",
             "Send the flagged text to the humanizer, read the result, and check again."),
        ),
    },
    "/humanizer": {
        "tab": "humanize",
        "hero": "Free AI Humanizer",
        "about_title": "Turn AI drafts into natural writing",
        "about": (
            ("Rewrites, not synonyms",
             "The humanizer rewrites whole sentences and paragraphs, changing rhythm and structure while keeping "
             "your point."),
            ("Keeps your meaning and citations",
             "Numbers, in-text citations, headings and reference lists stay as they are."),
            ("Check the result right away",
             "Switch to the AI detector tab and see how the new version scores."),
        ),
    },
}


def tool_landing(path: str) -> dict[str, Any] | None:
    """What the app landing shows at ``path`` (None if the path is not one of its pages)."""
    page = _TOOL_LANDINGS.get(path)
    if page is None:
        return None
    return {
        "path": path,
        "tab": page["tab"],
        "hero": page["hero"],
        "aboutTitle": page["about_title"],
        "about": [list(item) for item in page["about"]],
        "faq": [list(item) for item in faq_items_for_path(path) or []],
        "freeRuns": LANDING_TRY["free_runs"],
        "maxWords": LANDING_TRY["max_words"],
    }


def faq_items_for_path(path: str) -> list[FaqItem] | None:
    """Question + answer HTML for the page at ``path`` (None if it has no FAQ)."""
    if path == "/faq":
        return [item for _, items in site_faq_sections() for item in items]
    builder = _LANDING_FAQS.get(path)
    return builder() if builder else None


def faq_for_path(path: str) -> list[tuple[str, str]] | None:
    """FAQ as plain text pairs for JSON-LD."""
    items = faq_items_for_path(path)
    if not items:
        return None
    return [(plain_text(q), plain_text(a)) for q, a in items]
