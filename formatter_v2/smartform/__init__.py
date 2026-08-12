"""Smart form — Gemini brief extraction for Formatter V2 (prefill only)."""

from formatter_v2.smartform.extract import (
    PROMPT_VERSION,
    build_response_schema,
    extract_requirements,
)
from formatter_v2.smartform.postprocess import postprocess_extraction
from formatter_v2.smartform.prefill import PrefillResult, to_user_overrides

__all__ = [
    "PROMPT_VERSION",
    "PrefillResult",
    "build_response_schema",
    "extract_requirements",
    "postprocess_extraction",
    "to_user_overrides",
]
