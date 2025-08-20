# NyxFan/api/utils/errors.py
from telegram.ext import ContextTypes

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Minimal: print to console
    print(f"[NyxFan ERROR] {context.error!r}")
