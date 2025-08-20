# NyxFan/api/handlers/callbacks.py
from telegram import Update
from telegram.ext import ContextTypes

from api.utils.io import read_queue, write_queue
from api.utils.state import USER_DISP, ALL_DASH_MSGS
from api.handlers.dashboard import build_dashboard
from shared.fan_registry import get_telegram_id


async def show_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles 'View All' → sends all pending alerts to the fan."""
    await update.callback_query.answer()
    tg = update.effective_user.id
    msg = update.callback_query.message

    queue = read_queue()
    alerts = [
        c for c in queue
        if c.get("type") in ("relay", "subchg")
        and get_telegram_id(str(c.get("nyx_id"))) == tg
    ]

    if not alerts:
        await msg.reply_text("🔔 No pending alerts.")
    else:
        for c in alerts:
            out = (
                f"🆕 New post from *{c['creator']}*:\n{c.get('title','')}\n{c.get('url','')}"
                if c["type"] == "relay"
                else f"💲 Price update by *{c['creator']}*:\n{c.get('old_price','?')} → {c.get('new_price','?')}"
            )
            await msg.reply_text(out, parse_mode="Markdown")

        # purge shown alerts for this user
        remaining = [
            c for c in queue
            if not (
                c.get("type") in ("relay", "subchg")
                and get_telegram_id(str(c.get("nyx_id"))) == tg
            )
        ]
        write_queue(remaining)

    # remove the button message
    try:
        await msg.delete()
    except Exception:
        pass

    # User interaction → re-send dashboard at bottom
    # (delete old if tracked; then send a fresh one)
    old_ids = ALL_DASH_MSGS.get(tg, [])
    for mid in old_ids:
        try:
            await context.bot.delete_message(chat_id=tg, message_id=mid)
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
        if c.get("type") in ("relay", "subchg")
        and get_telegram_id(str(c.get("nyx_id"))) == tg
    ]

    if not alerts:
        await msg.reply_text("🔔 No pending alerts.")
    else:
        for c in alerts:
            out = (
                f"🆕 New post from *{c['creator']}*:\n{c.get('title','')}\n{c.get('url','')}"
                if c["type"] == "relay"
                else f"💲 Price update by *{c['creator']}*:\n{c.get('old_price','?')} → {c.get('new_price','?')}"
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
    # keep dashboard behavior identical to original (no extra push here)
