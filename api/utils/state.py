# NyxFan/api/utils/state.py
"""
In-memory runtime state for NyxFan.
These are simple module-level dicts that live for the life of the process.
"""

# Track the latest dashboard message(s) we sent per Telegram user so we can delete/replace.
# chat_id -> [message_id, ...]
ALL_DASH_MSGS: dict[int, list[int]] = {}

# Human-readable display name we last saw for each Telegram user.
# chat_id -> username/full_name/str(chat_id)
USER_DISP: dict[int, str] = {}

__all__ = ["ALL_DASH_MSGS", "USER_DISP"]
