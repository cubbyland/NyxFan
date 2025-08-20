# NyxFan/api/utils/__init__.py
"""
Utilities for NyxFan:
- env        → Application + config
- errors     → minimal error handler
- io         → shared queue I/O
- state      → in-memory runtime dicts
(We intentionally do NOT import dashboard here to avoid circular imports.)
"""

from .env import app, BOT_USERNAME, INBOX_URL, PROFILE_URL
from .errors import on_error
from .io import read_queue, write_queue
from .state import ALL_DASH_MSGS, USER_DISP

__all__ = [
    "app",
    "BOT_USERNAME", "INBOX_URL", "PROFILE_URL",
    "on_error",
    "read_queue", "write_queue",
    "ALL_DASH_MSGS", "USER_DISP",
]
