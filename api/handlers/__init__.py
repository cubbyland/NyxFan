# NyxFan/api/handlers/__init__.py
"""
Handler registration for NyxFan.
Exposes:
- register_handlers → attaches commands and callback query handlers
"""

from telegram.ext import CommandHandler, CallbackQueryHandler

# Import callback functions at module load (safe; no circular with commands)
from .callbacks import (
    show_alerts,
    show_digest,
    show_settings,
    show_settings_menu,
    set_daily,
    set_weekly,
    toggle_mute,
    back_to_post,
)
from .error_handler import setup_error_handler

__all__ = [
    "show_alerts",
    "show_digest",
    "show_settings",
    "setup_error_handler",
    "register_handlers",
]


def register_handlers(app):
    """
    Register all handlers (commands + callbacks) for NyxFan.
    Mirrors the wiring from the original single-file index.py.
    """
    # Import /start inside the function to avoid circular import with commands.start
    from api.commands import start

    # Command handlers
    app.add_handler(CommandHandler("start", start))

    # Dashboard callbacks (original patterns)
    app.add_handler(CallbackQueryHandler(show_alerts, pattern="^show_alerts$"))
    app.add_handler(CallbackQueryHandler(show_digest, pattern="^view_digest$"))
    app.add_handler(CallbackQueryHandler(show_settings, pattern="^show_settings$"))

    # Per-post Settings menu callbacks
    app.add_handler(CallbackQueryHandler(show_settings_menu, pattern=r"^settings\|.+$"))
    app.add_handler(CallbackQueryHandler(set_daily,          pattern=r"^set_daily\|.+$"))
    app.add_handler(CallbackQueryHandler(set_weekly,         pattern=r"^set_weekly\|.+$"))
    app.add_handler(CallbackQueryHandler(toggle_mute,        pattern=r"^toggle_mute\|.+$"))
    app.add_handler(CallbackQueryHandler(back_to_post,       pattern=r"^back\|.+$"))

    # Error handler
    setup_error_handler(app)
