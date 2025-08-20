# NyxFan/api/handlers/__init__.py
"""
Handler registration for NyxFan.
Exposes:
- register_handlers → attaches commands and callback query handlers
"""

from .callbacks import show_alerts, show_digest, show_settings
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
    from api.commands import start
    from telegram.ext import CommandHandler, CallbackQueryHandler

    # Command handlers
    app.add_handler(CommandHandler("start", start))

    # Callback query handlers
    app.add_handler(CallbackQueryHandler(show_alerts,  pattern="^show_alerts$"))
    app.add_handler(CallbackQueryHandler(show_digest,  pattern="^view_digest$"))
    app.add_handler(CallbackQueryHandler(show_settings, pattern="^show_settings$"))

    # Error handler
    setup_error_handler(app)
