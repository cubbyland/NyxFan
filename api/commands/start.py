# cubbyland-nyxfan/api/commands/start.py
from __future__ import annotations

from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from api.utils.io import read_queue, write_queue
from api.utils.state import USER_DISP, ALL_DASH_MSGS
from api.handlers.dashboard import build_dashboard
from shared.fan_registry import register_user, get_telegram_id


def _relay_keyboard(creator: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Settings", callback_data=f"settings|{creator}"),
         InlineKeyboardButton("Unlock",   callback_data="unlock")]
    ])

def _looks_hex(s: str) -> bool:
    if not isinstance(s, str) or len(s) % 2 != 0:
        return False
    try:
        int(s, 16)
        return True
    except Exception:
        return False

def _looks_file_id(s: str) -> bool:
    return isinstance(s, str) and len(s) > 40 and s.startswith(("AgAC", "BQAC", "CAAC", "DQAC", "EAAC", "GAAC", "IAAC"))

async def _send_relay_from_queue(bot_msg, cmd: dict):
    creator = cmd.get("creator", "?")
    title   = cmd.get("title", "")
    img     = cmd.get("image") or cmd.get("image_hex") or cmd.get("file_id")

    if isinstance(img, str) and _looks_file_id(img):
        await bot_msg.reply_photo(
            photo=img,
            caption=f"🔥 New post from #{creator}:\n\n{title}",
            reply_markup=_relay_keyboard(creator),
        )
        return

    if isinstance(img, str) and _looks_hex(img):
        try:
            b = bytes.fromhex(img)
            bio = BytesIO(b); bio.name = "post.jpg"
            await bot_msg.reply_photo(
                photo=bio,
                caption=f"🔥 New post from #{creator}:\n\n{title}",
                reply_markup=_relay_keyboard(creator),
            )
            return
        except Exception:
            pass

    await bot_msg.reply_text(
        f"🆕 New post from #*{creator}*:\n{title}",
        parse_mode="Markdown",
        reply_markup=_relay_keyboard(creator),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start entry:
      - registers fan
      - enqueues a 'joined' command so Proxy knows about the user (informational)
      - supports deep-link filters (?start=filter_<type>_<creator>)
      - sends/refreshes the dashboard
    """
    tg = update.effective_user.id
    disp = update.effective_user.username or update.effective_user.full_name or str(tg)
    register_user(tg, disp)
    USER_DISP[tg] = disp

    # (Informational) Let Proxy know this fan exists
    queue = read_queue()
    queue.append({"type": "joined", "nyx_id": str(tg), "display": disp})
    write_queue(queue)

    # Deep-link filter handling
    if context.args:
        arg = context.args[0]
        queue = read_queue()
        kept, to_send = [], []
        for c in queue:
            try:
                if (
                    get_telegram_id(str(c.get("nyx_id"))) == tg
                    and c.get("type") in ("relay", "subchg", "dm")
                    and len(arg.split("_", 2)) == 3
                    and arg.split("_", 2)[1] == c["type"]
                    and c.get("creator") == arg.split("_", 2)[2]
                ):
                    to_send.append(c)
                else:
                    kept.append(c)
            except Exception:
                kept.append(c)
        write_queue(kept)

        for c in to_send:
            t = c.get("type")
            if t == "relay":
                await _send_relay_from_queue(update.message, c)
            elif t == "dm":
                await update.message.reply_text(
                    f"✉️ DM from *{c.get('creator','?')}*:\n{c.get('message','')}",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"💲 Price update by *{c.get('creator','?')}*:\n{c.get('old_price','?')} → {c.get('new_price','?')}",
                    parse_mode="Markdown"
                )

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
