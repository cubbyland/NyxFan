# NyxFan/api/utils/__init__.py
"""
Utilities for NyxFan:
- env        → Application + config (BOT_USERNAME, INBOX_URL, PROFILE_URL)
- helpers    → queue I/O + simple in-memory state + shared registry re-exports
- dashboard  → dashboard text + keyboard builder
"""

from .env import app, BOT_USERNAME, INBOX_URL, PROFILE_URL
from .helpers import (
    QUEUE_PATH,
    read_queue, write_queue,
    register_user, get_telegram_id,
    ALL_DASH_MSGS, USER_DISP,
)
from .dashboard import build_dashboard

__all__ = [
    # env
    "app", "BOT_USERNAME", "INBOX_URL", "PROFILE_URL",
    # helpers
    "QUEUE_PATH", "read_queue", "write_queue",
    "register_user", "get_telegram_id",
    "ALL_DASH_MSGS", "USER_DISP",
    # dashboard
    "build_dashboard",
]
