"""Browser Automation Framework — reusable provider-based browser task execution."""

from services.browser_automation.manager import BrowserAutomationManager
from services.browser_automation.models import (
    BrowserProviderType,
    BrowserSession,
    BrowserTask,
    BrowserTaskStatus,
    ProviderHealth,
    RuntimeHealth,
    TaskResult,
)
from services.browser_automation.providers.provider import BrowserProvider
from services.browser_automation.queue import TaskQueue
from services.browser_automation.runtime import BrowserRuntime, get_shared_runtime
from services.browser_automation.session_manager import SessionManager
from services.browser_automation.storage import InMemoryStorage
from services.browser_automation.worker import TaskWorker

__all__ = [
    "BrowserAutomationManager",
    "BrowserProvider",
    "BrowserProviderType",
    "BrowserRuntime",
    "BrowserSession",
    "BrowserTask",
    "BrowserTaskStatus",
    "InMemoryStorage",
    "ProviderHealth",
    "RuntimeHealth",
    "SessionManager",
    "TaskQueue",
    "TaskResult",
    "TaskWorker",
    "get_shared_runtime",
]
