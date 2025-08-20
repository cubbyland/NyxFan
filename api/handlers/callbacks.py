# NyxFan/api/handlers/callbacks.py
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from api.utils.io import read_queue, write_queue
from api.utils.helpers import (
    USER_DISP, ALL_DASH_MSGS, build_dashboard, fan_bot, FAN_BOT_USERNAME
)
from shared.fan_registry import get_telegram_id


async def show_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles 'View All' → sends all pending alerts to the fan."""
    await update.callback_query.answer()
    tg = update.effective_user.id
    msg = update.callback_query.message

    queue = read_queue()
    alerts = [
        c for c in queue
        if c["type"] in ("relay", "subchg")
        and get_telegram_id(str(c["nyx_id"])) == tg
    ]

    if not alerts:
        await msg.reply_text("🔔 No pending alerts.")
        return

    for c in alerts:
        out = (
            f"🆕 New post from *{c['creator']}*:\n{c['title']}\n{c['url']}"
            if c["type"] == "relay"
            else f"💲 Price update by *{c['creator']}*:\n{c['old_price']} → {c['new_price']}"
        )
        await msg.reply_text(out, parse_mode="Markdown")

    remaining = [
        c for c in queue
        if not (
            c["type"] in ("relay", "subchg")
            and get_telegram_id(str(c["nyx_id"])) == tg
        )
    ]
    write_queue(remaining)

    try:
        await msg.delete()
    except Exception:
        pass

    new_text, new_kb = build_dashboard(tg)
    new_msg = await context.bot.send_message(
        chat_id=tg,
        text=new_text,
        parse_mode="Markdown",
        reply_markup=new_kb,
    )
    ALL_DASH_MSGS[tg] = [new_msg.message_id]


async def show_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles digest preview (not tied to queue flush)."""
    await update.callback_query.answer()
    tg = update.effective_user.id
    msg = update.callback_query.message

    queue = read_queue()
    alerts = [
        c for c in queue
        if c["type"] in ("relay", "subchg")
        and get_telegram_id(str(c["nyx_id"])) == tg
    ]

    if not alerts:
        await msg.reply_text("🔔 No pending alerts.")
        return

    for c in alerts:
        out = (
            f"🆕 New post from *{c['creator']}*:\n{c['title']}\n{c['url']}"
            if c["type"] == "relay"
            else f"💲 Price update by *{c['creator']}*:\n{c['old_price']} → {c['new_price']}"
        )
        await msg.reply_text(out, parse_mode="Markdown")

    try:
        await msg.delete()
    except Exception:
        pass


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles 'Settings' button."""
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("⚙️ Settings are not yet configurable.")
