# cubbyland-nyxfan/api/handlers/dashboard.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from api.utils.state import ALL_DASH_MSGS
from api.utils.io import read_queue
from shared.fan_registry import get_telegram_id


def build_dashboard(tg_id: int):
    """
    Build the fan's dashboard text + keyboard.
    Called after alerts are flushed or when /dashboard is run.
    """
    queue = read_queue()
    alerts = [
        c for c in queue
        if isinstance(c, dict)
        and c.get("type") in ("relay", "subchg", "dm")
        and get_telegram_id(str(c.get("nyx_id"))) == tg_id
    ]
    count = len(alerts)

    text = (
        f"📊 *Dashboard*\n\n"
        f"You currently have *{count}* pending update(s).\n\n"
        "Choose an option below:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("View All", callback_data="alerts")],
        [InlineKeyboardButton("Preview Digest", callback_data="digest")],
        [InlineKeyboardButton("⚙ Settings", callback_data="settings")],
    ])

    return text, kb


async def show_dashboard(update, context):
    tg = update.effective_user.id

    text, kb = build_dashboard(tg)
    msg = await context.bot.send_message(
        chat_id=tg,
        text=text,
        parse_mode="Markdown",
        reply_markup=kb,
    )

    ALL_DASH_MSGS[tg] = [msg.message_id]
