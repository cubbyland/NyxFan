# cubbyland-nyxfan/api/handlers/__init__.py

from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
)

from api.handlers.dashboard import show_dashboard
from api.handlers.callbacks import (
    show_alerts,
    show_digest,
    show_settings,
    show_settings_menu,
    set_daily,
    set_weekly,
    toggle_mute,
    back_to_post,
    unlock_request,
    unlock_confirm,
)


def register_handlers(application):
    """Register all command + callback handlers into the application dispatcher."""
    dp = application

    # Commands
    dp.add_handler(CommandHandler("dashboard", show_dashboard))

    # Dashboard buttons
    dp.add_handler(CallbackQueryHandler(show_alerts,   pattern="^alerts$"))
    dp.add_handler(CallbackQueryHandler(show_digest,   pattern="^digest$"))
    dp.add_handler(CallbackQueryHandler(show_settings, pattern="^settings$"))

    # Per-post settings flow
    dp.add_handler(CallbackQueryHandler(show_settings_menu, pattern=r"^settings\|.+$"))
    dp.add_handler(CallbackQueryHandler(set_daily,          pattern=r"^set_daily\|.+$"))
    dp.add_handler(CallbackQueryHandler(set_weekly,         pattern=r"^set_weekly\|.+$"))
    dp.add_handler(CallbackQueryHandler(toggle_mute,        pattern=r"^toggle_mute\|.+$"))
    dp.add_handler(CallbackQueryHandler(back_to_post,       pattern=r"^back\|.+$"))

    # Unlock flow
    dp.add_handler(CallbackQueryHandler(unlock_request,     pattern=r"^unlock(\|.+)?$"))
    dp.add_handler(CallbackQueryHandler(unlock_confirm,     pattern=r"^unlock_confirm\|.+$"))
