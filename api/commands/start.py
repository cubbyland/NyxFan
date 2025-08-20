# NyxFan/api/commands/start.py
from __future__ import annotations

import json
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes

from api.utils.env import BOT_USERNAME, INBOX_URL, PROFILE_URL
from api.utils.io import read_queue, write_queue
from api.utils.state import USER_DISP, ALL_DASH_MSGS
from api.handlers.dashboard import build_dashboard
from shared.fan_registry import register_user, get_telegram_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start entry:
      - registers fan
      - enqueues a 'joined' command so Proxy knows about the user
      - supports deep-link filters (?start=filter_<type>_<creator>)
      - sends/refreshes the dashboard
    """
    tg = update.effective_user.id
    disp = update.effective_user.username or update.effective_user.full_name or str(tg)
    register_user(tg, disp)
    USER_DISP[tg] = disp

    # Notify NyxProxy via the shared queue that this fan joined
    queue = read_queue()
    queue.append({
        "type": "joined",
        "nyx_id": str(tg),
        "display": disp
    })
    write_queue(queue)

    # Deep-link filter handling, e.g. start=filter_relay_<creator> or filter_subchg_<creator>
    if context.args:
        arg = context.args[0]
        queue = read_queue()
        kept, to_send = [], []
        for c in queue:
            try:
                if (
                    get_telegram_id(str(c["nyx_id"])) == tg
                    and c["type"] in ("relay", "subchg")
                    and arg.split("_", 2)[1] == c["type"]
                    and c["creator"] == arg.split("_", 2)[2]
                ):
                    to_send.append(c)
                else:
                    kept.append(c)
            except Exception:
                kept.append(c)
        write_queue(kept)

        for c in to_send:
            text = (
                f"🆕 New post from *{c['creator']}*:\n{c['title']}\n{c.get('url','')}".rstrip()
                if c["type"] == "relay"
                else f"💲 Price update by *{c['creator']}*:\n{c['old_price']} → {c['new_price']}"
            )
            await update.message.reply_text(text, parse_mode="Markdown")

    # Send a fresh dashboard
    text, kb = build_dashboard(tg)
    msg = await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    new_ids = [msg.message_id]

    # Delete older dashboards if we have them tracked
    for mid in ALL_DASH_MSGS.get(tg, []):
        try:
            await context.bot.delete_message(chat_id=tg, message_id=mid)
        except Exception:
            pass

    ALL_DASH_MSGS[tg] = new_ids
