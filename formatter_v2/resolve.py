"""
Formatter V2 — резолвер настроек.

Единственное место в кодовой базе, где значения складываются вместе.
Больше нигде формат меняться не должен: слой вёрстки получает готовый
FormatSpec и применяет его буквально.

Три принципа, каждый из которых чинит конкретный баг V1:

1. ПРОПОРЦИОНАЛЬНОЕ МАСШТАБИРОВАНИЕ РАЗМЕРОВ.
   Профиль задаёт соотношения, а не абсолютные величины. Смена размера тела
   двигает остальные роли пропорционально, сохраняя типографскую иерархию.
   V1 ставил один размер на все роли (style_engine.py:251) и убивал иерархию.

2. РАСПРОСТРАНЕНИЕ ТОЛЬКО ПО СОВПАДЕНИЮ С ТЕЛОМ.
   Переопределение интервала/выравнивания применяется лишь к тем ролям,
   где значение в профиле совпадает со значением тела. Роль, отличающаяся
   намеренно (одинарная библиография Chicago, двойные заголовки APA),
   остаётся нетронутой. V1 переписывал всё безусловно (style_engine.py:262).

3. ПРЕДУПРЕЖДЕНИЯ ВМЕСТО ЗАПРЕТОВ.
   Пользователь вправе отступить от стандарта, но обязан об этом узнать.
   Резолвер возвращает список отступлений для показа в UI.
"""

from __future__ import annotations

import copy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from formatter_v2.spec import (
    AbbreviationList,
    Alignment,
    AppendixConfig,
    CleanupConfig,
    FormatSpec,
    Margins,
    ParagraphRole,
    StructureConfig,
    StyleName,
    StyleProfile,
    TableOfContents,
    TypographySpec,
    UserOverrides,
)

# --------------------------------------------------------------------------
# Дефолты блоков FormatSpec (читаемее, чем model_fields[].default_factory)
# --------------------------------------------------------------------------

DEFAULT_TOC = TableOfContents()
DEFAULT_ABBREVIATIONS = AbbreviationList()
DEFAULT_APPENDICES = AppendixConfig()
DEFAULT_STRUCTURE = StructureConfig()
DEFAULT_CLEANUP = CleanupConfig()

# --------------------------------------------------------------------------
# Группы ролей
# --------------------------------------------------------------------------

BODY_ROLES: frozenset[ParagraphRole] = frozenset(
    {ParagraphRole.BODY, ParagraphRole.BODY_FIRST}
)

HEADING_ROLES: tuple[ParagraphRole, ...] = (
    ParagraphRole.HEADING_1,
    ParagraphRole.HEADING_2,
    ParagraphRole.HEADING_3,
    ParagraphRole.HEADING_4,
)

# Стили, где стандарт требует одинакового кегля у заголовков и тела.
UNIFORM_HEADING_SIZE_STYLES: frozenset[StyleName] = frozenset(
    {StyleName.APA7, StyleName.MLA9}
)

# Стили с жёстко предписанными полями страницы.
FIXED_MARGIN_STYLES: frozenset[StyleName] = frozenset({StyleName.IEEE})

MIN_FONT_PT = 6.0
MAX_FONT_PT = 48.0


# --------------------------------------------------------------------------
# Результат
# --------------------------------------------------------------------------


class ResolutionNotice(BaseModel):
    """Отступление от стандарта или последствие переопределения.
    Показывается пользователю рядом с соответствующим полем формы."""

    model_config = ConfigDict(extra="forbid")

    field: str
    message: str
    severity: Literal["info", "deviation"] = "deviation"


class ResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec: FormatSpec
    notices: list[ResolutionNotice] = Field(default_factory=list)

    @property
    def has_deviations(self) -> bool:
        return any(n.severity == "deviation" for n in self.notices)


# --------------------------------------------------------------------------
# Вспомогательные операции над ролями
# --------------------------------------------------------------------------


def _round_half_point(value: float) -> float:
    """Word работает с шагом в полпункта. 12.83 -> 13.0, 12.4 -> 12.5."""
    return round(value * 2.0) / 2.0


def _clamp_font(value: float) -> float:
    return max(MIN_FONT_PT, min(MAX_FONT_PT, value))


def _scale_font_sizes(
    roles: dict[ParagraphRole, TypographySpec],
    old_body_size: float,
    new_body_size: float,
) -> None:
    """Принцип 1. Двигает все роли пропорционально изменению тела.

    Harvard: тело 12 -> 11, H1 14 -> 14 * (11/12) = 12.83 -> 13.0
    APA:     тело 12 -> 11, H1 12 -> 12 * (11/12) = 11.0  (иерархии нет, и не должно быть)
    """
    if old_body_size <= 0 or old_body_size == new_body_size:
        return

    ratio = new_body_size / old_body_size
    for spec in roles.values():
        spec.font_size_pt = _clamp_font(_round_half_point(spec.font_size_pt * ratio))


def _propagate_where_matches_body(
    roles: dict[ParagraphRole, TypographySpec],
    attribute: str,
    profile_body_value: object,
    new_value: object,
) -> list[ParagraphRole]:
    """Принцип 2. Меняет атрибут только там, где профиль совпадал с телом.

    Chicago, интервал 2.0 -> 1.5:
        BODY 2.0 == 2.0 -> становится 1.5
        REFERENCES_ENTRY 1.0 != 2.0 -> остаётся 1.0 (намеренная одинарность)
        BLOCK_QUOTE 1.0 != 2.0 -> остаётся 1.0

    Возвращает список ролей, которых изменение НЕ коснулось, — для notices.
    """
    untouched: list[ParagraphRole] = []
    for role, spec in roles.items():
        if getattr(spec, attribute) == profile_body_value:
            setattr(spec, attribute, new_value)
        else:
            untouched.append(role)
    return untouched


def _apply_first_line_indent(
    roles: dict[ParagraphRole, TypographySpec],
    enabled: bool,
    fallback_indent: float = 0.5,
) -> None:
    """Красная строка касается только абзацев тела.
    Списки, цитаты и подписи имеют собственную логику отступов."""
    for role in BODY_ROLES:
        spec = roles.get(role)
        if spec is None:
            continue
        if enabled:
            if spec.hanging_indent_in > 0:
                spec.hanging_indent_in = 0.0
            spec.first_line_indent_in = spec.first_line_indent_in or fallback_indent
        else:
            spec.first_line_indent_in = 0.0


def _scale_heading_sizes(
    roles: dict[ParagraphRole, TypographySpec],
    new_h1_size: float,
) -> None:
    """Экспертный override размера заголовков.
    H1 получает заданное значение, H2-H4 масштабируются пропорционально,
    чтобы иерархия не схлопнулась."""
    h1 = roles.get(ParagraphRole.HEADING_1)
    if h1 is None or h1.font_size_pt <= 0:
        return

    ratio = new_h1_size / h1.font_size_pt
    for role in HEADING_ROLES:
        spec = roles.get(role)
        if spec is not None:
            spec.font_size_pt = _clamp_font(_round_half_point(spec.font_size_pt * ratio))


# --------------------------------------------------------------------------
# Главная функция
# --------------------------------------------------------------------------


def resolve_format_spec(
    profile: StyleProfile,
    overrides: UserOverrides | None = None,
) -> ResolutionResult:
    """Складывает эталон стиля и правки пользователя в готовую спеку.

    Пользователь всегда главнее профиля — бриф преподавателя к этому моменту
    уже отработал, предзаполнив форму, и в резолвер не попадает.
    """
    overrides = overrides or UserOverrides()
    notices: list[ResolutionNotice] = []

    if overrides.style is not None and overrides.style != profile.name:
        raise ValueError(
            f"Profile {profile.name.value} does not match the selected style "
            f"{overrides.style.value}. Load the matching style profile before calling the resolver."
        )

    roles = copy.deepcopy(profile.roles)
    body = roles[ParagraphRole.BODY]

    # Запоминаем эталонные значения тела ДО правок — они нужны как точка
    # отсчёта для принципов 1 и 2.
    profile_body_size = body.font_size_pt
    profile_body_spacing = body.line_spacing
    profile_body_alignment = body.alignment

    # --- Шрифт: применяется ко всем ролям без исключения -------------------
    if overrides.font_family is not None:
        for spec in roles.values():
            spec.font_family = overrides.font_family

    # --- Размер: пропорционально (принцип 1) -------------------------------
    if overrides.font_size_pt is not None:
        _scale_font_sizes(roles, profile_body_size, overrides.font_size_pt)

    # --- Интервал: по совпадению с телом (принцип 2) -----------------------
    if overrides.line_spacing is not None:
        untouched = _propagate_where_matches_body(
            roles, "line_spacing", profile_body_spacing, overrides.line_spacing
        )
        preserved = [r for r in untouched if r in _NOTABLE_SPACING_ROLES]
        if preserved:
            notices.append(
                ResolutionNotice(
                    field="line_spacing",
                    severity="info",
                    message=(
                        f"{profile.display_name} uses a different line spacing for "
                        f"{', '.join(_role_label(r) for r in preserved)} — "
                        "that spacing was left unchanged."
                    ),
                )
            )

    # --- Выравнивание: по совпадению с телом (принцип 2) -------------------
    if overrides.alignment is not None:
        _propagate_where_matches_body(
            roles, "alignment", profile_body_alignment, overrides.alignment
        )
        if (
            profile.name in {StyleName.APA7, StyleName.MLA9}
            and overrides.alignment == Alignment.JUSTIFY
        ):
            notices.append(
                ResolutionNotice(
                    field="alignment",
                    message=(
                        f"{profile.display_name} requires left alignment. "
                        "Justified text is a departure from the style."
                    ),
                )
            )

    # --- Красная строка ----------------------------------------------------
    if overrides.first_line_indent is not None:
        _apply_first_line_indent(roles, overrides.first_line_indent)

    # --- Регистр заголовков ------------------------------------------------
    if overrides.heading_case is not None:
        for role in HEADING_ROLES:
            spec = roles.get(role)
            if spec is not None:
                spec.text_case = overrides.heading_case

    # --- Размер заголовков: экспертный override ----------------------------
    if overrides.heading_size_pt is not None:
        _scale_heading_sizes(roles, overrides.heading_size_pt)
        if profile.name in UNIFORM_HEADING_SIZE_STYLES:
            notices.append(
                ResolutionNotice(
                    field="heading_size_pt",
                    message=(
                        f"{profile.display_name} requires the same type size for headings "
                        "and body text. Enlarging headings is a departure from the style."
                    ),
                )
            )

    # --- Страница ----------------------------------------------------------
    page = profile.page.model_copy(deep=True)
    if overrides.margins is not None:
        if profile.name in FIXED_MARGIN_STYLES and overrides.margins != profile.page.margins:
            notices.append(
                ResolutionNotice(
                    field="margins",
                    message=(
                        f"{profile.display_name} specifies fixed margins "
                        f"({_margins_label(profile.page.margins)}). Changing them is "
                        "a departure from the style."
                    ),
                )
            )
        page.margins = overrides.margins.model_copy(deep=True)
    if overrides.page_size is not None:
        page.size = overrides.page_size

    page_numbering = (
        overrides.page_numbering.model_copy(deep=True)
        if overrides.page_numbering is not None
        else profile.page_numbering.model_copy(deep=True)
    )

    # --- Блоки: прямая замена целиком --------------------------------------
    cover_page = (
        overrides.cover_page.model_copy(deep=True)
        if overrides.cover_page is not None
        else profile.cover_page.model_copy(deep=True)
    )
    if cover_page.enabled and not profile.cover_page.enabled:
        notices.append(
            ResolutionNotice(
                field="cover_page",
                message=(
                    f"{profile.display_name} does not use a separate cover page. "
                    "Adding one is a departure from the style."
                ),
            )
        )

    references = (
        overrides.references.model_copy(deep=True)
        if overrides.references is not None
        else profile.references.model_copy(deep=True)
    )
    if references.sort != profile.references.sort:
        notices.append(
            ResolutionNotice(
                field="references.sort",
                message=(
                    f"{profile.display_name} requires references to be ordered "
                    f"{_sort_label(profile.references.sort)}."
                ),
            )
        )

    citations = (
        overrides.citations.model_copy(deep=True)
        if overrides.citations is not None
        else profile.citations.model_copy(deep=True)
    )

    spec = FormatSpec(
        style=profile.name,
        date_format=profile.date_format,
        page=page,
        page_numbering=page_numbering,
        roles=roles,
        cover_page=cover_page,
        table_of_contents=(
            overrides.table_of_contents.model_copy(deep=True)
            if overrides.table_of_contents is not None
            else DEFAULT_TOC.model_copy(deep=True)
        ),
        abbreviations=(
            overrides.abbreviations.model_copy(deep=True)
            if overrides.abbreviations is not None
            else DEFAULT_ABBREVIATIONS.model_copy(deep=True)
        ),
        captions=(
            overrides.captions.model_copy(deep=True)
            if overrides.captions is not None
            else profile.captions.model_copy(deep=True)
        ),
        appendices=(
            overrides.appendices.model_copy(deep=True)
            if overrides.appendices is not None
            else DEFAULT_APPENDICES.model_copy(deep=True)
        ),
        citations=citations,
        references=references,
        structure=(
            overrides.structure.model_copy(deep=True)
            if overrides.structure is not None
            else DEFAULT_STRUCTURE.model_copy(deep=True)
        ),
        cleanup=(
            overrides.cleanup.model_copy(deep=True)
            if overrides.cleanup is not None
            else DEFAULT_CLEANUP.model_copy(deep=True)
        ),
    )

    return ResolutionResult(spec=spec, notices=notices)


# --------------------------------------------------------------------------
# Подписи для сообщений
# --------------------------------------------------------------------------

_NOTABLE_SPACING_ROLES: frozenset[ParagraphRole] = frozenset(
    {
        ParagraphRole.REFERENCES_ENTRY,
        ParagraphRole.BLOCK_QUOTE,
        ParagraphRole.FOOTNOTE,
        ParagraphRole.TABLE_CELL,
    }
)

_ROLE_LABELS: dict[ParagraphRole, str] = {
    ParagraphRole.REFERENCES_ENTRY: "the reference list",
    ParagraphRole.BLOCK_QUOTE: "block quotations",
    ParagraphRole.FOOTNOTE: "footnotes",
    ParagraphRole.TABLE_CELL: "tables",
}


def _role_label(role: ParagraphRole) -> str:
    return _ROLE_LABELS.get(role, role.value)


def _margins_label(margins: Margins) -> str:
    return (
        f"{margins.top_in}″ / {margins.bottom_in}″ / "
        f"{margins.left_in}″ / {margins.right_in}″"
    )


def _sort_label(sort: object) -> str:
    return {
        "alphabetical": "alphabetically",
        "order_of_appearance": "in order of appearance",
    }.get(getattr(sort, "value", str(sort)), str(sort))
