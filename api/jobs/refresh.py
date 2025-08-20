# NyxFan/api/jobs/refresh.py
"""
Fan-side background consumer: processes only 'dash_refresh' pokes.
Matches original behavior: edit dashboard inline if it exists; never push new.
"""

from telegram.ext import ContextTypes
from telegram.error import BadRequest

from api.utils.io import read_queue, write_queue
from api.utils.state import ALL_DASH_MSGS
from api.handlers.dashboard import build_dashboard
from shared.fan_registry import get_telegram_id


async def _edit_dashboard_if_exists(context: ContextTypes.DEFAULT_TYPE, tg: int) -> bool:
    """Background-safe update: edit existing dashboard only (no new message)."""
    mids = ALL_DASH_MSGS.get(tg, [])
    mid = mids[-1] if mids else None
    if not mid:
        return False
    text, kb = build_dashboard(tg)
    try:
        await context.bot.edit_message_text(
            chat_id=tg, message_id=mid,
            text=text, parse_mode="Markdown", reply_markup=kb
        )
        return True
    except BadRequest:
        return False


async def process_fan_queue(context: ContextTypes.DEFAULT_TYPE):
    queue = read_queue()
    new_q = []
    for cmd in queue:
        t = cmd.get("type")
        tg = get_telegram_id(str(cmd.get("nyx_id")))
        if not tg:
            new_q.append(cmd)
            continue

        if t == "dash_refresh":
            # Background-safe: edit existing dashboard only; if none, skip (avoid push).
            await _edit_dashboard_if_exists(context, tg)
            # Do not requeue this poke.
            continue

        # Leave all other items untouched for Proxy (or future handling)
        new_q.append(cmd)

    write_queue(new_q)
