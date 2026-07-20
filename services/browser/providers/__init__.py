"""Browser Automation Platform providers.

Each provider knows only its own page, selectors, buttons, and workflow.
Browser lifecycle is owned entirely by BrowserService.
"""

from services.browser.providers.base import Provider
from services.browser.providers.plagdetect import PlagDetectProvider
from services.browser.providers.stealthwriter import StealthWriterProvider

__all__ = ["Provider", "StealthWriterProvider", "PlagDetectProvider"]
