"""RU/UZ public SSR page copy and path map for SEO localization.

Body strings are marked ``[REVIEW]`` so marketing can edit student-facing wording
before launch. English remains the default at unprefixed URLs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from services.seo import PublicPage

# Keep paths as literals to avoid an import cycle with services.seo.
OG_IMAGE_DETECTOR = "/static/og/ai-detector.webp"
OG_IMAGE_HUMANIZER = "/static/og/ai-humanizer.webp"
OG_IMAGE_FORMATTER = "/static/og/formatter.webp"
OG_IMAGE_DEFAULT = "/static/og/home.webp"
MEDIA_DETECTOR_HIGHLIGHTS = "/static/media/ai-detector-sentence-highlights.webp"
MEDIA_DETECTOR_SCORE = "/static/media/ai-detector-overall-score.webp"
MEDIA_HUMANIZER_RESULT = "/static/media/ai-humanizer-result-panel.webp"
MEDIA_HUMANIZER_COMPARE = "/static/media/ai-humanizer-before-after.webp"
MEDIA_FORMATTER_PREVIEW = "/static/media/essay-formatter-apa-preview.webp"
MEDIA_FORMATTER_SETTINGS = "/static/media/essay-formatter-style-settings.webp"

LOCALES = ("en", "ru", "uz")
LOCALE_PREFIXES = ("ru", "uz")

# Canonical slug set for marketing SSR pages (never /app).
PAGE_KEYS = ("home", "ai-detector", "humanizer", "formatter", "pricing", "faq", "about")

# en path ↔ locale path
EN_PATHS: dict[str, str] = {
    "home": "/",
    "ai-detector": "/ai-detector",
    "humanizer": "/humanizer",
    "formatter": "/formatter",
    "pricing": "/pricing",
    "faq": "/faq",
    "about": "/about",
}


def locale_path(lang: str, key: str) -> str:
    """Path for a page key in ``en`` / ``ru`` / ``uz``."""
    if lang == "en":
        return EN_PATHS[key]
    if key == "home":
        return f"/{lang}"
    return f"/{lang}/{key}"


def alternates_for(key: str) -> dict[str, str]:
    return {lang: locale_path(lang, key) for lang in LOCALES}


def page_key_for_path(path: str) -> str | None:
    """Map a request path to a PAGE_KEYS entry, or None."""
    path = (path or "/").rstrip("/") or "/"
    for key, en in EN_PATHS.items():
        if path == en:
            return key
    for lang in LOCALE_PREFIXES:
        if path == f"/{lang}":
            return "home"
        for key in PAGE_KEYS:
            if key == "home":
                continue
            if path == f"/{lang}/{key}":
                return key
    return None


def sibling_path(path: str, target_lang: str) -> str | None:
    """Same page in another language, or None if path is not a localized marketing page."""
    key = page_key_for_path(path)
    if key is None:
        return None
    return locale_path(target_lang, key)


@dataclass(frozen=True)
class LocaleCopy:
    """Renderable marketing copy for one localized page (beyond PublicPage meta)."""

    lede: str
    sections: tuple[dict[str, Any], ...] = ()
    show_tool: bool = False
    review_note: str = "[REVIEW]"


def _r(text: str) -> str:
    """Mark copy for human review without breaking layout."""
    return f"{text} [REVIEW]"


# --- FAQs (plain text for JSON-LD + visible list) ---

_RU_HUMANIZER_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("Это проверка на ИИ или хуманайзер?"),
        _r(
            "Хуманайзер переписывает текст, чтобы он звучал естественнее. Отдельно есть "
            "бесплатная проверка на ИИ — она показывает, какие фразы выглядят как нейросеть."
        ),
    ),
        (
        _r("Поможет ли это против Turnitin и проверки на ИИ?"),
        _r(
            "Мы настраиваем инструменты на реальных отчётах Turnitin, но ни один сервис не "
            "даёт гарантий по проценту ИИ. Используйте как черновик и всегда перечитывайте сами."
        ),
    ),
    (
        _r("Сколько слов можно бесплатно?"),
        _r(
            "Короткие тексты — без регистрации (лимит на экране). С аккаунтом лимит выше. "
            "Длинные работы и Turnitin-отчёты — за кредиты."
        ),
    ),
)

_UZ_HUMANIZER_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("Bu AI matn tekshirishmi yoki humanizermi?"),
        _r(
            "Humanizer matnni tabiiyroq qilib qayta yozadi. Alohida bepul AI detector "
            "qaysi jumlalar sun'iy ko‘rinishini ko‘rsatadi."
        ),
    ),
    (
        _r("Turnitin / antiplagiat uchun yordam beradimi?"),
        _r(
            "Asboblar real Turnitin hisobotlari asosida sozlangan, lekin hech kim 0% AI "
            "kafolatlamaydi. Qoralama sifatida ishlating va o‘zingiz qayta o‘qing."
        ),
    ),
    (
        _r("Bepul limit qancha?"),
        _r(
            "Qisqa matnlar — ro‘yxatdan o‘tmasdan (ekrandagi limit). Akkount bilan limit "
            "yuqoriroq. Uzun ishlar va Turnitin — kreditlar bilan."
        ),
    ),
)

_RU_DETECTOR_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("Чем это отличается от GPTZero?"),
        _r(
            "Наш детектор заточен под студенческие эссе и разметку в стиле Turnitin: "
            "общий балл и подсветка предложений, без лишнего шума."
        ),
    ),
    (
        _r("Нужна ли регистрация?"),
        _r("Короткую проверку можно сделать без аккаунта. Для истории и длинных текстов — войдите."),
    ),
)

_UZ_DETECTOR_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("GPTZero dan nima farqi?"),
        _r(
            "Bizning detector talaba insholari va Turnitin uslubidagi belgilashga moslashgan: "
            "umumiy ball va jumlalarni ajratib ko‘rsatadi."
        ),
    ),
    (
        _r("Ro‘yxatdan o‘tish kerakmi?"),
        _r("Qisqa tekshiruvni akkountsiz qilish mumkin. Tarix va uzun matnlar uchun kiring."),
    ),
)

_RU_HOME_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("С чего начать студенту из СНГ?"),
        _r(
            "Сначала проверка на ИИ, потом хуманайзер проблемных абзацев, затем бесплатное "
            "оформление APA/MLA/Harvard — и снова быстрый чек перед сдачей."
        ),
    ),
    *_RU_HUMANIZER_FAQ[:1],
)

_UZ_HOME_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("O‘zbekiston / MDH talabasi qayerdan boshlasın?"),
        _r(
            "Avval AI matn tekshirish, keyin muammoli qismlarni humanizer, so‘ng bepul "
            "APA/MLA formatlash — topshirishdan oldin yana tezkor tekshiruv."
        ),
    ),
    *_UZ_HUMANIZER_FAQ[:1],
)

_RU_FORMATTER_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("Какие стили оформления есть?"),
        _r("APA 7, MLA 9, Harvard, Chicago и IEEE: шрифт, поля, интервал, титул и список литературы."),
    ),
    (
        _r("Это бесплатно?"),
        _r("Да — оформление реферата и курсовой в выбранном стиле без оплаты."),
    ),
)

_UZ_FORMATTER_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("Qaysi stillar bor?"),
        _r("APA 7, MLA 9, Harvard, Chicago va IEEE: shrift, maydon, interval, titulli sahifa va adabiyotlar."),
    ),
    (
        _r("Bepulmi?"),
        _r("Ha — referat / kurs ishini tanlangan uslubda formatlash bepul."),
    ),
)

_RU_PRICING_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("Что бесплатно?"),
        _r("Оформление всегда бесплатно. Короткие запуски хуманайзера и детектора — по дневному лимиту."),
    ),
    (
        _r("За что списываются кредиты?"),
        _r("Длинный humanize, Turnitin-отчёты, слайды и assignment helper — по тарифу на странице цен."),
    ),
)

_UZ_PRICING_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("Nima bepul?"),
        _r("Formatlash har doim bepul. Qisqa humanizer va detector — kunlik limit bilan."),
    ),
    (
        _r("Kredit nima uchun?"),
        _r("Uzun humanize, Turnitin hisobotlari, slaydlar va assignment helper — narxlar sahifasiga qarang."),
    ),
)

_RU_FAQ_EXTRA: tuple[tuple[str, str], ...] = (
    (
        _r("Есть ли русский движок хуманайзера?"),
        _r(
            "Сейчас лучше всего работает английский текст (типичные эссе в зарубежных вузах). "
            "Русский интерфейс уже здесь; полный RU-движок развиваем."
        ),
    ),
    (
        _r("Как связаться с поддержкой?"),
        _r("support@docmaxxing.com или WhatsApp/Telegram в подвале сайта. Часы: Пн–Пт 9:00–18:00 (GMT+5)."),
    ),
)

_UZ_FAQ_EXTRA: tuple[tuple[str, str], ...] = (
    (
        _r("O‘zbek / rus humanizer bormi?"),
        _r(
            "Hozir eng yaxshi natija — inglizcha akademik matnlar uchun. Interfeys o‘zbekcha; "
            "to‘liq mahalliy engine ustida ishlayapmiz."
        ),
    ),
    (
        _r("Yordam bilan qanday bog‘lanaman?"),
        _r("support@docmaxxing.com yoki sayt pastidagi WhatsApp/Telegram. Ish vaqti: Du–Ju 9:00–18:00 (GMT+5)."),
    ),
)

_RU_ABOUT_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("Кто делает DocMaxxing?"),
        _r(
            "Команда из Узбекистана: делаем инструменты для студентов — проверка на ИИ, "
            "хуманайзер, оформление и помощь с заданиями в одном месте."
        ),
    ),
)

_UZ_ABOUT_FAQ: tuple[tuple[str, str], ...] = (
    (
        _r("DocMaxxing kim?"),
        _r(
            "O‘zbekistondagi jamoa: talabalar uchun AI tekshiruv, humanizer, formatlash "
            "va topshiriq yordamini bitta joyda beramiz."
        ),
    ),
)


LOCALE_FAQS: dict[str, dict[str, tuple[tuple[str, str], ...]]] = {
    "ru": {
        "home": _RU_HOME_FAQ,
        "humanizer": _RU_HUMANIZER_FAQ,
        "ai-detector": _RU_DETECTOR_FAQ,
        "formatter": _RU_FORMATTER_FAQ,
        "pricing": _RU_PRICING_FAQ,
        "faq": _RU_HUMANIZER_FAQ + _RU_DETECTOR_FAQ + _RU_PRICING_FAQ + _RU_FAQ_EXTRA,
        "about": _RU_ABOUT_FAQ,
    },
    "uz": {
        "home": _UZ_HOME_FAQ,
        "humanizer": _UZ_HUMANIZER_FAQ,
        "ai-detector": _UZ_DETECTOR_FAQ,
        "formatter": _UZ_FORMATTER_FAQ,
        "pricing": _UZ_PRICING_FAQ,
        "faq": _UZ_HUMANIZER_FAQ + _UZ_DETECTOR_FAQ + _UZ_PRICING_FAQ + _UZ_FAQ_EXTRA,
        "about": _UZ_ABOUT_FAQ,
    },
}


_TOOL_IMAGES: dict[str, tuple[str, ...]] = {
    "home": (MEDIA_HUMANIZER_RESULT, MEDIA_DETECTOR_HIGHLIGHTS, MEDIA_FORMATTER_PREVIEW),
    "ai-detector": (MEDIA_DETECTOR_HIGHLIGHTS, MEDIA_DETECTOR_SCORE),
    "humanizer": (MEDIA_HUMANIZER_RESULT, MEDIA_HUMANIZER_COMPARE),
    "formatter": (MEDIA_FORMATTER_PREVIEW, MEDIA_FORMATTER_SETTINGS),
}


def _meta(
    *,
    key: str,
    lang: str,
    title: str,
    description: str,
    h1: str,
    breadcrumb: str | None,
    keywords: tuple[str, ...],
    og_image: str | None = None,
    software_app: bool = False,
    lede: str | None = None,
) -> "PublicPage":
    from services.seo import PublicPage

    from services.seo import og_image_path_for

    path = locale_path(lang, key)
    return PublicPage(
        path=path,
        title=title,
        description=description,
        lang=lang,
        h1=h1,
        lede=lede,
        keywords=keywords,
        og_image=og_image or og_image_path_for(path),
        breadcrumb=breadcrumb,
        sources=("templates/landing/locale_page.html", "services/seo_i18n.py"),
        software_app=software_app,
        alternates=alternates_for(key),
        in_sitemap=True,
        images=_TOOL_IMAGES.get(key, ()),
    )


def build_localized_public_pages() -> tuple["PublicPage", ...]:
    """All /ru and /uz PublicPage entries (EN stays in seo._PAGES)."""
    from services.seo import PublicPage  # noqa: F401 — used via _meta

    pages: list[PublicPage] = []

    # --- Russian ---
    pages.append(
        _meta(
            key="home",
            lang="ru",
            # REVIEW: title/description
            title="Проверка на ИИ и хуманайзер для студентов | DocMaxxing",
            description=(
                "Бесплатная проверка текста на ИИ, хуманайзер и оформление реферата APA/MLA. "
                "Для студентов из СНГ — без сложной регистрации на короткий черновик."
            ),
            h1=_r("Проверка на ИИ, хуманайзер и оформление работ"),
            breadcrumb=None,
            keywords=(
                "проверка на ИИ",
                "хуманайзер",
                "оформление реферата",
                "Turnitin ИИ",
                "детектор ИИ",
            ),
            software_app=True,
            lede=_r(
                "Вставьте черновик после ChatGPT: увидите, что похоже на нейросеть, "
                "перепишете естественнее и оформите по ГОСТ-стилю вуза — APA, MLA или Harvard."
            ),
        )
    )
    pages.append(
        _meta(
            key="ai-detector",
            lang="ru",
            # REVIEW: title/description
            title="Проверка на ИИ бесплатно — детектор для эссе | DocMaxxing",
            description=(
                "Онлайн-проверка текста на искусственный интеллект: балл и подсветка предложений. "
                "Заточено под студенческие работы и отчёты в духе Turnitin."
            ),
            h1=_r("Проверка на ИИ — бесплатный детектор"),
            breadcrumb=_r("Проверка на ИИ"),
            keywords=("проверка на ИИ", "детектор ИИ", "нейросеть проверка текста", "Turnitin ИИ"),
            og_image=OG_IMAGE_DETECTOR,
            software_app=True,
            lede=_r(
                "Вставьте эссе и получите оценку «насколько текст похож на ИИ» плюс список "
                "сомнительных предложений — без регистрации на короткий объём."
            ),
        )
    )
    pages.append(
        _meta(
            key="humanizer",
            lang="ru",
            # REVIEW: title/description
            title="Хуманайзер текста — убрать стиль нейросети | DocMaxxing",
            description=(
                "Хуманайзер AI: перепишите текст ChatGPT так, чтобы он звучал по-человечески. "
                "Смысл, цифры и цитаты сохраняются. Короткие тексты — бесплатно."
            ),
            h1=_r("Хуманайзер текста — сделать текст естественным"),
            breadcrumb=_r("Хуманайзер"),
            keywords=("хуманайзер", "очеловечить текст", "убрать ИИ из текста", "AI humanizer"),
            og_image=OG_IMAGE_HUMANIZER,
            software_app=True,
            lede=_r(
                "Не «синонимайзер», а переписывание под студенческий стиль: меньше шаблонных "
                "оборотов, те же факты и ссылки."
            ),
        )
    )
    pages.append(
        _meta(
            key="formatter",
            lang="ru",
            # REVIEW: title/description
            title="Оформление реферата APA, MLA, Harvard онлайн | DocMaxxing",
            description=(
                "Бесплатное оформление курсовой и эссе: поля, шрифт, интервал, титул и список "
                "литературы для APA 7, MLA 9, Harvard, Chicago и IEEE."
            ),
            h1=_r("Оформление работ — APA, MLA, Harvard"),
            breadcrumb=_r("Оформление"),
            keywords=("оформление реферата", "APA оформление", "MLA", "Harvard referencing"),
            software_app=True,
            lede=_r("Загрузите DOCX или вставьте текст — получите файл, готовый к сдаче по стилю вуза."),
        )
    )
    pages.append(
        _meta(
            key="pricing",
            lang="ru",
            # REVIEW: title/description
            title="Цены DocMaxxing — бесплатные лимиты и кредиты",
            description=(
                "Что бесплатно: оформление и короткие проверки/хуманайзер. Планы и пакеты "
                "кредитов — для Turnitin и длинных текстов. Без скрытых платежей."
            ),
            h1=_r("Цены и бесплатные лимиты"),
            breadcrumb=_r("Цены"),
            keywords=("цены DocMaxxing", "кредиты", "бесплатный хуманайзер"),
            lede=_r("Сначала используйте бесплатные лимиты; кредиты — только когда нужен Turnitin или длинный humanize."),
        )
    )
    pages.append(
        _meta(
            key="faq",
            lang="ru",
            # REVIEW: title/description
            title="FAQ — проверка на ИИ, хуманайзер, кредиты | DocMaxxing",
            description=(
                "Частые вопросы студентов: проверка на ИИ, лимиты хуманайзера, оформление, "
                "кредиты, Turnitin и возвраты."
            ),
            h1=_r("Вопросы и ответы"),
            breadcrumb="FAQ",
            keywords=("FAQ DocMaxxing", "проверка на ИИ вопросы"),
            lede=_r("Коротко о том, как пользоваться проверкой на ИИ, хуманайзером и бесплатным оформлением."),
        )
    )
    pages.append(
        _meta(
            key="about",
            lang="ru",
            # REVIEW: title/description
            title="О DocMaxxing — инструменты для студентов",
            description=(
                "Кто мы: команда из Узбекистана. Делаем проверку на ИИ, хуманайзер, оформление "
                "и помощь с заданиями для студентов СНГ и зарубежных вузов."
            ),
            h1=_r("О DocMaxxing"),
            breadcrumb=_r("О нас"),
            keywords=("DocMaxxing", "о сервисе"),
            lede=_r("Пишем для студентов, которые сдают работы на английском и хотят честный черновик без хаоса вкладок."),
        )
    )

    # --- Uzbek (Latin) ---
    pages.append(
        _meta(
            key="home",
            lang="uz",
            # REVIEW: title/description
            title="AI matn tekshirish va humanizer | DocMaxxing",
            description=(
                "Bepul AI detector, AI humanizer va APA/MLA formatlash. O‘zbekiston va MDH "
                "talabalari uchun — qisqa qoralama akkountsiz."
            ),
            h1=_r("AI tekshiruv, humanizer va referat formatlash"),
            breadcrumb=None,
            keywords=(
                "AI matn tekshirish",
                "antiplagiat",
                "AI humanizer",
                "referat formatlash",
                "Turnitin AI",
            ),
            software_app=True,
            lede=_r(
                "ChatGPT dan keyingi qoralamani joylashtiring: AI ga o‘xshash joylarni ko‘ring, "
                "tabiiyroq qayta yozing va APA/MLA/Harvard bo‘yicha formatlang."
            ),
        )
    )
    pages.append(
        _meta(
            key="ai-detector",
            lang="uz",
            # REVIEW: title/description
            title="AI matn tekshirish bepul — essay detector | DocMaxxing",
            description=(
                "Onlayn AI detector: ball va jumlalarni belgilash. Talaba ishlari va Turnitin "
                "uslubidagi hisobotlarga moslashtirilgan."
            ),
            h1=_r("AI matn tekshirish — bepul detector"),
            breadcrumb=_r("AI tekshiruv"),
            keywords=("AI matn tekshirish", "AI detector", "antiplagiat AI", "Turnitin"),
            og_image=OG_IMAGE_DETECTOR,
            software_app=True,
            lede=_r(
                "Inshoni joylashtiring — AI ga o‘xshashlik balli va shubhali jumlalar ro‘yxatini oling. "
                "Qisqa hajm uchun ro‘yxatdan o‘tish shart emas."
            ),
        )
    )
    pages.append(
        _meta(
            key="humanizer",
            lang="uz",
            # REVIEW: title/description
            title="AI humanizer onlayn — matnni tabiiy qilish | DocMaxxing",
            description=(
                "AI humanizer: ChatGPT matnini odamdek yangilang. Ma’no, raqamlar va iqtiboslar "
                "saqlanadi. Qisqa matnlar bepul."
            ),
            h1=_r("AI humanizer — matnni tabiiy qilish"),
            breadcrumb=_r("Humanizer"),
            keywords=("AI humanizer", "matnni odamlashtirish", "ChatGPT qayta yozish"),
            og_image=OG_IMAGE_HUMANIZER,
            software_app=True,
            lede=_r(
                "Oddiy sinonim almashtirish emas — talaba uslubiga yaqin qayta yozish: shablon "
                "iboralarni kamaytiramiz, faktlarni saqlaymiz."
            ),
        )
    )
    pages.append(
        _meta(
            key="formatter",
            lang="uz",
            # REVIEW: title/description
            title="Referat formatlash APA, MLA, Harvard | DocMaxxing",
            description=(
                "Bepul kurs / referat formatlash: shrift, maydon, interval, titulli sahifa va "
                "adabiyotlar — APA 7, MLA 9, Harvard, Chicago, IEEE."
            ),
            h1=_r("Referat formatlash — APA, MLA, Harvard"),
            breadcrumb=_r("Formatlash"),
            keywords=("referat formatlash", "APA", "MLA", "Harvard"),
            software_app=True,
            lede=_r("DOCX yuklang yoki matn joylashtiring — universitet uslubiga mos fayl oling."),
        )
    )
    pages.append(
        _meta(
            key="pricing",
            lang="uz",
            # REVIEW: title/description
            title="DocMaxxing narxlari — bepul limit va kreditlar",
            description=(
                "Bepul: formatlash va qisqa detector/humanizer. Turnitin va uzun matnlar uchun "
                "tariflar va kredit paketlari. Yashirin to‘lovlarsiz."
            ),
            h1=_r("Narxlar va bepul limitlar"),
            breadcrumb=_r("Narxlar"),
            keywords=("DocMaxxing narx", "kreditlar", "bepul humanizer"),
            lede=_r("Avval bepul limitdan foydalaning; kredit — Turnitin yoki uzun humanize kerak bo‘lganda."),
        )
    )
    pages.append(
        _meta(
            key="faq",
            lang="uz",
            # REVIEW: title/description
            title="FAQ — AI tekshiruv, humanizer, kreditlar | DocMaxxing",
            description=(
                "Talabalar savollari: antiplagiat va AI, humanizer limitlari, formatlash, "
                "kreditlar, Turnitin va qaytarishlar."
            ),
            h1=_r("Savol-javoblar"),
            breadcrumb="FAQ",
            keywords=("DocMaxxing FAQ", "AI matn tekshirish savollar"),
            lede=_r("AI tekshiruv, humanizer va bepul formatlash haqida qisqa javoblar."),
        )
    )
    pages.append(
        _meta(
            key="about",
            lang="uz",
            # REVIEW: title/description
            title="DocMaxxing haqida — talabalar uchun asboblar",
            description=(
                "Biz kim: O‘zbekistondagi jamoa. AI tekshiruv, humanizer, formatlash va "
                "topshiriq yordamini MDH va xorijiy universitet talabalari uchun qilamiz."
            ),
            h1=_r("DocMaxxing haqida"),
            breadcrumb=_r("Biz haqimizda"),
            keywords=("DocMaxxing", "haqida"),
            lede=_r("Inglizcha topshiriq topshiradigan talabalar uchun — bitta joyda tekshiruv va qoralama."),
        )
    )
    return tuple(pages)


def locale_copy_for(path: str) -> LocaleCopy | None:
    """Extra body sections for locale SSR template."""
    key = page_key_for_path(path)
    if key is None:
        return None
    path_n = (path or "/").rstrip("/") or "/"
    lang = "ru" if path_n == "/ru" or path_n.startswith("/ru/") else "uz" if path_n == "/uz" or path_n.startswith("/uz/") else None
    if lang is None:
        return None
    page = next((p for p in build_localized_public_pages() if p.path == locale_path(lang, key)), None)
    if page is None:
        return None
    faqs = LOCALE_FAQS.get(lang, {}).get(key, ())
    sections: list[dict[str, Any]] = []
    if key == "home":
        if lang == "ru":
            sections.append(
                {
                    "type": "cards",
                    "title": _r("Инструменты под сдачу"),
                    "lede": _r("От проверки на ИИ до оформления — без прыжков между десятью сайтами."),
                    "items": [
                        {
                            "title": _r("Проверка на ИИ"),
                            "text": _r("Балл и подсветка предложений — понять, что переписать."),
                            "href": locale_path(lang, "ai-detector"),
                            "cta": _r("Проверить текст →"),
                        },
                        {
                            "title": _r("Хуманайзер"),
                            "text": _r("Сделать черновик естественнее, сохранив смысл и цитаты."),
                            "href": locale_path(lang, "humanizer"),
                            "cta": _r("Очеловечить →"),
                        },
                        {
                            "title": _r("Оформление"),
                            "text": _r("APA, MLA, Harvard — поля, титул, список литературы."),
                            "href": locale_path(lang, "formatter"),
                            "cta": _r("Оформить →"),
                        },
                    ],
                }
            )
        else:
            sections.append(
                {
                    "type": "cards",
                    "title": _r("Topshiriq uchun asboblar"),
                    "lede": _r("AI tekshiruvdan formatlashgacha — o‘nlab saytlar orasida sakramasdan."),
                    "items": [
                        {
                            "title": _r("AI matn tekshirish"),
                            "text": _r("Ball va jumlalarni belgilash — nima qayta yozishni biling."),
                            "href": locale_path(lang, "ai-detector"),
                            "cta": _r("Tekshirish →"),
                        },
                        {
                            "title": _r("Humanizer"),
                            "text": _r("Qoralamani tabiiyroq qiling, ma’no va iqtiboslarni saqlang."),
                            "href": locale_path(lang, "humanizer"),
                            "cta": _r("Humanize →"),
                        },
                        {
                            "title": _r("Formatlash"),
                            "text": _r("APA, MLA, Harvard — maydon, titul, adabiyotlar."),
                            "href": locale_path(lang, "formatter"),
                            "cta": _r("Formatlash →"),
                        },
                    ],
                }
            )
    if faqs:
        sections.append({"type": "faq", "title": _r("Частые вопросы") if lang == "ru" else _r("Ko‘p so‘raladigan savollar"), "items": faqs})
    show_tool = key in {"home", "humanizer"}
    return LocaleCopy(lede=page.lede or "", sections=tuple(sections), show_tool=show_tool)


def apply_en_alternates(pages: dict[str, "PublicPage"]) -> dict[str, "PublicPage"]:
    """Return a new PUBLIC_PAGES-like dict with EN alternates filled for marketing pages."""
    from services.seo import PublicPage

    out: dict[str, PublicPage] = dict(pages)
    for key, en_path in EN_PATHS.items():
        page = out.get(en_path)
        if page is None:
            continue
        alts = alternates_for(key)
        out[en_path] = PublicPage(
            path=page.path,
            title=page.title,
            description=page.description,
            lang=page.lang,
            h1=page.h1,
            lede=page.lede,
            keywords=page.keywords,
            og_image=page.og_image,
            breadcrumb=page.breadcrumb,
            sources=page.sources,
            software_app=page.software_app,
            alternates=alts,
            in_sitemap=page.in_sitemap,
            images=page.images,
        )
    return out


LANG_SWITCH_LABELS = {
    "en": "English",
    "ru": "Русский",
    "uz": "O‘zbekcha",
}


def lang_switch_links(path: str) -> list[dict[str, str]]:
    """Plain ``<a href>`` targets for the header/footer language switcher (no JS redirect)."""
    key = page_key_for_path(path)
    links: list[dict[str, str]] = []
    for lang in LOCALES:
        href = locale_path(lang, key) if key else ("/" if lang == "en" else f"/{lang}")
        links.append({"lang": lang, "label": LANG_SWITCH_LABELS[lang], "href": href})
    return links
