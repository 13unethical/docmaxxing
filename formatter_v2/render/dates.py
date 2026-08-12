"""Cover-page / identity-block date formatting by academic style."""

from __future__ import annotations

from datetime import date
from typing import Literal

DateFormatName = Literal["month_day_year", "day_month_year"]


def format_cover_date(
    value: date,
    date_format: DateFormatName = "day_month_year",
) -> str:
    """Format a cover/MLA identity date.

    APA / IEEE → ``May 15, 2026`` (month_day_year)
    MLA / Harvard / Chicago → ``15 May 2026`` (day_month_year)
    """
    month = value.strftime("%B")
    if date_format == "month_day_year":
        return f"{month} {value.day}, {value.year}"
    return f"{value.day} {month} {value.year}"
