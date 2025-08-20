# NyxFan/api/handlers/error_handler.py
from telegram.ext import ContextTypes


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Keep it minimal; print exception to console
    print(f"[ERROR] {context.error!r}")


def setup_error_handler(app):
    """
    Attach a single error handler to the Application.
    """
    app.add_error_handler(_on_error)
