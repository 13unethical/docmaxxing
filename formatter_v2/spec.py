"""
Formatter V2 — эталонная схема настроек форматирования.

Три модели, три разные роли:

  ExtractedRequirements  — что вернула Gemini Flash из брифа. Все поля Optional.
                           None означает "в брифе про это не сказано", а НЕ "значение по умолчанию".
  StyleProfile           — эталон стиля (Harvard / APA7 / MLA9 / Chicago17 / IEEE).
                           Чистые данные из официальных руководств. LLM сюда не пишет никогда.
  FormatSpec             — итоговая резолвленная спека. Все поля заполнены.
                           Единственный объект, который видит слой вёрстки на python-docx.

Порядок сборки:
    StyleProfile -> предзаполнение формы из ExtractedRequirements -> правки пользователя
    -> FormatSpec -> python-docx

Пользователь всегда главнее брифа: бриф только предзаполняет форму.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "2.0.0"


# ============================================================================
# Перечисления
# ============================================================================


class StyleName(str, Enum):
    """Один стиль задаёт И вёрстку, И оформление цитат. В V1 это были два
    независимых поля (format_style / citation_style), из-за чего пользователь
    мог получить вёрстку IEEE со ссылками APA. Схлопнуто намеренно."""

    HARVARD = "harvard"
    APA7 = "apa7"
    MLA9 = "mla9"
    CHICAGO17 = "chicago17"
    IEEE = "ieee"
    CUSTOM = "custom"


class FontFamily(str, Enum):
    TIMES_NEW_ROMAN = "Times New Roman"
    ARIAL = "Arial"
    CALIBRI = "Calibri"
    CAMBRIA = "Cambria"
    GEORGIA = "Georgia"
    VERDANA = "Verdana"
    TAHOMA = "Tahoma"


class Alignment(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


class PageSize(str, Enum):
    A4 = "a4"
    LETTER = "letter"


class PageNumberPosition(str, Enum):
    """Все шесть позиций. В V1 bottom_center существовал в Assignment,
    но отсутствовал в whitelist формы — из-за этого молча превращался в bottom_right."""

    NONE = "none"
    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"


class NumberFormat(str, Enum):
    ARABIC = "arabic"  # 1, 2, 3
    ROMAN_LOWER = "roman_lower"  # i, ii, iii — обычно для front matter
    ROMAN_UPPER = "roman_upper"


class TextCase(str, Enum):
    PRESERVE = "preserve"
    TITLE_CASE = "title_case"
    SENTENCE_CASE = "sentence_case"
    UPPER = "upper"


class ParagraphRole(str, Enum):
    """Роль абзаца в документе. Слой вёрстки не знает про "стили" —
    он знает только роли и берёт для каждой TypographySpec из FormatSpec.roles.

    Слой восстановления структуры (классификатор) возвращает именно эти значения."""

    DOC_TITLE = "doc_title"
    SUBTITLE = "subtitle"
    ABSTRACT_HEADING = "abstract_heading"
    ABSTRACT = "abstract"
    KEYWORDS = "keywords"

    HEADING_1 = "heading_1"
    HEADING_2 = "heading_2"
    HEADING_3 = "heading_3"
    HEADING_4 = "heading_4"

    BODY = "body"
    BODY_FIRST = "body_first"  # первый абзац после заголовка (часто без красной строки)
    BLOCK_QUOTE = "block_quote"
    LIST_BULLET = "list_bullet"
    LIST_NUMBER = "list_number"

    TABLE_CAPTION = "table_caption"
    TABLE_HEADER = "table_header"
    TABLE_CELL = "table_cell"
    FIGURE_CAPTION = "figure_caption"

    TOC_HEADING = "toc_heading"
    TOC_ENTRY = "toc_entry"
    ABBREVIATION_ENTRY = "abbreviation_entry"

    APPENDIX_HEADING = "appendix_heading"

    REFERENCES_HEADING = "references_heading"
    REFERENCES_ENTRY = "references_entry"
    FOOTNOTE = "footnote"

    COVER_TITLE = "cover_title"
    COVER_FIELD = "cover_field"


class DocumentType(str, Enum):
    ESSAY = "essay"
    REPORT = "report"
    RESEARCH_PROPOSAL = "research_proposal"
    DISSERTATION = "dissertation"
    LITERATURE_REVIEW = "literature_review"
    CASE_STUDY = "case_study"
    REFLECTIVE_JOURNAL = "reflective_journal"
    LAB_REPORT = "lab_report"
    GENERIC = "generic"


class InTextMode(str, Enum):
    PARENTHETICAL = "parenthetical"  # (Smith, 2020)
    NARRATIVE = "narrative"  # Smith (2020)
    NUMERIC = "numeric"  # [1]
    FOOTNOTE = "footnote"  # Chicago notes-bibliography


class ReferenceSort(str, Enum):
    ALPHABETICAL = "alphabetical"
    ORDER_OF_APPEARANCE = "order_of_appearance"


class StructureMode(str, Enum):
    PRESERVE = "preserve"  # в документе уже есть Word-стили заголовков — не трогаем
    HEURISTIC = "heuristic"  # детерминированные правила
    CLASSIFIER = "classifier"  # обученный классификатор (DeBERTa, позже)
    AI = "ai"  # Gemini как последний резерв


# ============================================================================
# Базовые блоки
# ============================================================================

Inches = Annotated[float, Field(ge=0.0, le=3.0)]
Points = Annotated[float, Field(ge=0.0, le=144.0)]
FontSize = Annotated[float, Field(ge=6.0, le=48.0)]
Spacing = Annotated[float, Field(ge=1.0, le=3.0)]


class StrictModel(BaseModel):
    """extra="forbid" критичен: если Gemini придумает лишний ключ,
    валидация упадёт громко, а не проглотит мусор молча."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class TypographySpec(StrictModel):
    """Полное описание внешнего вида одной роли абзаца.
    Именно это применяет python-docx — больше ему знать ничего не нужно."""

    font_family: FontFamily = FontFamily.TIMES_NEW_ROMAN
    font_size_pt: FontSize = 12.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    text_case: TextCase = TextCase.PRESERVE
    small_caps: bool = False

    alignment: Alignment = Alignment.LEFT
    line_spacing: Spacing = 1.5
    space_before_pt: Points = 0.0
    space_after_pt: Points = 0.0

    first_line_indent_in: Inches = 0.0
    left_indent_in: Inches = 0.0
    right_indent_in: Inches = 0.0
    hanging_indent_in: Inches = 0.0

    keep_with_next: bool = False
    page_break_before: bool = False
    widow_control: bool = True

    @model_validator(mode="after")
    def _no_conflicting_indents(self) -> TypographySpec:
        if self.first_line_indent_in > 0 and self.hanging_indent_in > 0:
            raise ValueError(
                "first_line_indent_in и hanging_indent_in взаимоисключающие: "
                "первая строка не может быть одновременно сдвинута вправо и влево"
            )
        return self

    @model_validator(mode="after")
    def _no_small_caps_with_upper(self) -> TypographySpec:
        if self.small_caps and self.text_case == TextCase.UPPER:
            raise ValueError(
                "small_caps и text_case=UPPER взаимоисключающие: "
                "капитель и принудительные прописные нельзя применять вместе"
            )
        return self


class Margins(StrictModel):
    top_in: Inches = 1.0
    bottom_in: Inches = 1.0
    left_in: Inches = 1.0
    right_in: Inches = 1.0

    @classmethod
    def preset(cls, name: Literal["normal", "narrow", "wide"]) -> Margins:
        value = {"normal": 1.0, "narrow": 0.5, "wide": 1.5}[name]
        return cls(top_in=value, bottom_in=value, left_in=value, right_in=value)


class PageSetup(StrictModel):
    size: PageSize = PageSize.A4
    margins: Margins = Field(default_factory=Margins)
    mirror_margins: bool = False  # для печатных работ с переплётом
    binding_offset_in: Inches = 0.0


class PageNumbering(StrictModel):
    position: PageNumberPosition = PageNumberPosition.NONE
    number_format: NumberFormat = NumberFormat.ARABIC
    start_at: int = Field(default=1, ge=1)
    skip_first_page: bool = True  # титульник обычно не нумеруется
    restart_after_front_matter: bool = False
    include_total: bool = False  # "3 of 12"


# ============================================================================
# Разделы документа
# ============================================================================


class CoverPageField(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(default="", max_length=300)
    show_label: bool = True


class CoverPage(StrictModel):
    """В V1 это было два несвязанных пути (форма и загрузка файла),
    плюс мёртвый CoverPageSpec в профилях. Здесь один объект."""

    enabled: bool = False
    mode: Literal["form", "uploaded_file"] = "form"

    title: str = Field(default="", max_length=300)
    subtitle: str = Field(default="", max_length=300)
    student_name: str = Field(default="", max_length=150)
    student_id: str = Field(default="", max_length=60)
    university: str = Field(default="", max_length=200)
    faculty: str = Field(default="", max_length=200)
    course: str = Field(default="", max_length=200)
    module_code: str = Field(default="", max_length=60)
    module_title: str = Field(default="", max_length=200)
    lecturer: str = Field(default="", max_length=150)
    submission_date: date | None = None
    word_count: int | None = Field(default=None, ge=0)

    extra_fields: list[CoverPageField] = Field(default_factory=list, max_length=10)

    top_spacer_lines: int = Field(default=5, ge=0, le=20)
    page_break_after: bool = True

    @model_validator(mode="after")
    def _title_required_when_enabled(self) -> CoverPage:
        if self.enabled and self.mode == "form" and not self.title.strip():
            raise ValueError("Титульный лист включён, но заголовок работы пустой")
        return self


class TableOfContents(StrictModel):
    enabled: bool = False
    heading_text: str = "Table of Contents"
    max_depth: int = Field(default=3, ge=1, le=4)
    show_page_numbers: bool = True
    dot_leaders: bool = True
    page_break_after: bool = True
    # Default False: static heading list (Google Docs / Pages don't refresh Word fields).
    field_based: bool = False


class AbbreviationList(StrictModel):
    enabled: bool = False
    heading_text: str = "List of Abbreviations"
    entries: dict[str, str] = Field(default_factory=dict)
    sort_alphabetically: bool = True
    page_break_after: bool = True


class CaptionConfig(StrictModel):
    enabled: bool = True
    table_position: Literal["above", "below"] = "above"
    figure_position: Literal["above", "below"] = "below"
    table_label: str = "Table"
    figure_label: str = "Figure"
    separator: str = ". "  # "Table 1. Sample distribution"
    auto_number: bool = True
    number_by_chapter: bool = False  # "Table 2.1"
    two_line: bool = False  # APA: bold "Table N" + italic title on next line


class AppendixConfig(StrictModel):
    enabled: bool = False
    heading_prefix: str = "Appendix"
    lettered: bool = True  # Appendix A, B, C — иначе Appendix 1, 2, 3
    page_break_before_each: bool = True
    exclude_from_toc: bool = False


class CitationConfig(StrictModel):
    """Стиль наследуется от FormatSpec.style. Отдельное поле оставлено только
    как экспертный override — по умолчанию None, то есть "как основной стиль"."""

    style_override: StyleName | None = None
    default_in_text_mode: InTextMode = InTextMode.PARENTHETICAL
    include_page_numbers: bool = True
    use_ampersand: bool = False  # (Smith & Jones) vs (Smith and Jones)
    et_al_threshold: int = Field(default=3, ge=2, le=8)
    disambiguate_same_year: bool = True  # 2020a, 2020b


class ReferencesConfig(StrictModel):
    enabled: bool = True
    heading_text: str = "References"  # Works Cited для MLA, Bibliography для Chicago
    on_new_page: bool = True
    sort: ReferenceSort = ReferenceSort.ALPHABETICAL
    numbered: bool = False  # IEEE
    max_entries: int = Field(default=200, ge=0, le=500)


class CleanupConfig(StrictModel):
    """Бывшие "special rules" из V1. Не DSL, просто явные флаги."""

    collapse_extra_spaces: bool = True
    collapse_extra_linebreaks: bool = True
    strip_markdown: bool = True  # #, **, * — следы LLM-вывода
    normalize_quotes: bool = True  # "" -> “”
    normalize_dashes: bool = True  # -- -> —
    normalize_ellipsis: bool = True
    trim_trailing_whitespace: bool = True
    remove_empty_paragraphs: bool = True
    fix_spacing_after_punctuation: bool = True


class StructureConfig(StrictModel):
    mode: StructureMode = StructureMode.HEURISTIC
    document_type: DocumentType = DocumentType.GENERIC
    expected_sections: list[str] = Field(default_factory=list, max_length=30)
    heading_case: TextCase = TextCase.PRESERVE
    max_heading_depth: int = Field(default=3, ge=1, le=4)
    number_headings: bool = False  # 1., 1.1, 1.1.1
    allow_ai_fallback: bool = True

    @field_validator("expected_sections")
    @classmethod
    def _strip_sections(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()]


# ============================================================================
# Итоговая спека
# ============================================================================


class FormatSpec(StrictModel):
    """Полностью резолвленная спека. Всё заполнено, ничего не Optional.
    Если объект собрался — документ гарантированно сверстается.

    Слой вёрстки принимает только это и ничего больше не спрашивает."""

    schema_version: Literal["2.0.0"] = SCHEMA_VERSION
    style: StyleName = StyleName.HARVARD
    language: Literal["en"] = "en"
    date_format: Literal["month_day_year", "day_month_year"] = "day_month_year"

    page: PageSetup = Field(default_factory=PageSetup)
    page_numbering: PageNumbering = Field(default_factory=PageNumbering)
    roles: dict[ParagraphRole, TypographySpec] = Field(default_factory=dict)

    cover_page: CoverPage = Field(default_factory=CoverPage)
    table_of_contents: TableOfContents = Field(default_factory=TableOfContents)
    abbreviations: AbbreviationList = Field(default_factory=AbbreviationList)
    captions: CaptionConfig = Field(default_factory=CaptionConfig)
    appendices: AppendixConfig = Field(default_factory=AppendixConfig)

    citations: CitationConfig = Field(default_factory=CitationConfig)
    references: ReferencesConfig = Field(default_factory=ReferencesConfig)

    structure: StructureConfig = Field(default_factory=StructureConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)

    @model_validator(mode="after")
    def _all_roles_present(self) -> FormatSpec:
        missing = [r.value for r in ParagraphRole if r not in self.roles]
        if missing:
            raise ValueError(
                "FormatSpec должен покрывать все роли абзацев. Не заполнены: "
                + ", ".join(missing)
            )
        return self

    def typography(self, role: ParagraphRole) -> TypographySpec:
        return self.roles[role]

    @property
    def effective_citation_style(self) -> StyleName:
        return self.citations.style_override or self.style


class StyleProfile(StrictModel):
    """Эталон стиля из официального руководства. Задаёт дефолты,
    поверх которых ложатся правки пользователя. Только данные, без логики."""

    name: StyleName
    display_name: str
    source_manual: str  # "Publication Manual of the APA, 7th ed."
    page: PageSetup
    page_numbering: PageNumbering
    roles: dict[ParagraphRole, TypographySpec]
    citations: CitationConfig
    references: ReferencesConfig
    captions: CaptionConfig
    cover_page: CoverPage = Field(default_factory=CoverPage)
    # Cover / MLA identity date display: "May 15, 2026" vs "15 May 2026"
    date_format: Literal["month_day_year", "day_month_year"] = "day_month_year"


# ============================================================================
# Слой 1 — то, что возвращает Gemini Flash
# ============================================================================


class ExtractedRequirements(StrictModel):
    """Выход Gemini Flash при разборе брифа преподавателя.

    Все поля Optional. None = "в брифе про это не сказано".
    Модель НЕ подставляет значения по умолчанию — это работа StyleProfile.
    Ничего из этого не применяется напрямую: результат только предзаполняет форму,
    финальное слово всегда за пользователем.
    """

    style: StyleName | None = None
    document_type: DocumentType | None = None

    font_family: FontFamily | None = None
    font_size_pt: FontSize | None = None
    line_spacing: Spacing | None = None
    alignment: Alignment | None = None
    first_line_indent: bool | None = None

    margins_in: Margins | None = None
    page_size: PageSize | None = None
    page_number_position: PageNumberPosition | None = None

    word_count_min: int | None = Field(default=None, ge=0)
    word_count_max: int | None = Field(default=None, ge=0)
    deadline: date | None = None

    required_sections: list[str] = Field(default_factory=list, max_length=30)
    min_references: int | None = Field(default=None, ge=0)
    max_references: int | None = Field(default=None, ge=0)

    requires_cover_page: bool | None = None
    requires_toc: bool | None = None
    requires_abstract: bool | None = None
    requires_appendices: bool | None = None

    evidence: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Имя поля -> дословная цитата из брифа, обосновавшая значение. "
            "Показывается пользователю и используется для отладки промпта."
        ),
    )
    unsupported: list[str] = Field(
        default_factory=list,
        description="Найденные в брифе требования, которые сервис пока не умеет (напр. OSCOLA).",
    )
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _counts_consistent(self) -> ExtractedRequirements:
        if (
            self.word_count_min is not None
            and self.word_count_max is not None
            and self.word_count_min > self.word_count_max
        ):
            raise ValueError("word_count_min больше word_count_max")
        if (
            self.min_references is not None
            and self.max_references is not None
            and self.min_references > self.max_references
        ):
            raise ValueError("min_references больше max_references")
        return self

    def is_empty(self) -> bool:
        """Если бриф не содержал ни одного требования — не показываем
        пользователю пустое предзаполнение, оставляем дефолты стиля."""
        payload = self.model_dump(
            exclude={"evidence", "unsupported", "warnings"},
            exclude_none=True,
            exclude_defaults=True,
        )
        return not payload


# ============================================================================
# Контракт резолвера (реализация — formatter_v2/resolve.py)
# ============================================================================


class UserOverrides(StrictModel):
    """Что пришло из формы. Все поля Optional: заполнено только то,
    что пользователь реально видел и подтвердил."""

    style: StyleName | None = None
    font_family: FontFamily | None = None
    font_size_pt: FontSize | None = None
    line_spacing: Spacing | None = None
    alignment: Alignment | None = None
    first_line_indent: bool | None = None
    margins: Margins | None = None
    page_size: PageSize | None = None
    page_numbering: PageNumbering | None = None
    heading_case: TextCase | None = None
    heading_size_pt: FontSize | None = None

    cover_page: CoverPage | None = None
    table_of_contents: TableOfContents | None = None
    abbreviations: AbbreviationList | None = None
    appendices: AppendixConfig | None = None
    captions: CaptionConfig | None = None
    citations: CitationConfig | None = None
    references: ReferencesConfig | None = None
    structure: StructureConfig | None = None
    cleanup: CleanupConfig | None = None
