"""Generic Browser Automation Platform.

Long-lived browser infrastructure shared by every provider. The browser is
started once and kept alive like a connection pool; providers only request pages.
"""

from services.browser.browser_pool import BrowserConnection, BrowserPool
from services.browser.browser_service import BrowserService, get_browser_service
from services.browser.chrome_launcher import ChromeLauncher
from services.browser.page_manager import PageManager
from services.browser.session_store import SessionStore

__all__ = [
    "BrowserConnection",
    "BrowserPool",
    "BrowserService",
    "ChromeLauncher",
    "PageManager",
    "SessionStore",
    "get_browser_service",
]
