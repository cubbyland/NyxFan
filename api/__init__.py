# NyxFan/api/__init__.py
"""
NyxFan API package.

Exposes subpackages:
- commands  → command registration & setup (/start, deep-link handling)
- handlers  → Telegram callback query handlers (dashboard, alerts, settings)
- jobs      → background job scheduling / processors
- utils     → helpers, I/O, environment, dashboard builder
"""

from . import commands, handlers, jobs, utils

__all__ = [
    "commands",
    "handlers",
    "jobs",
    "utils",
]
