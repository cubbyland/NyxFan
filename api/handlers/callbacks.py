# cubbyland-nyxfan/api/handlers/callbacks.py

from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from api.utils.io import read_queue, write_queue, read_notifs, write_notifs
from api.utils.state import USER_DISP, ALL_DASH_MSGS, ORIG_CAPTION
from api.handlers.dashboard import build_dashboard
from shared.fan_registry import get_telegram_id


# ───────────────────────────────────────────────
# Helpers to render the same post component used by Proxy
# ───────────────────────────────────────────────
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

async def _send_relay_from_queue(update_msg, tg: int, cmd: dict):
    creator = cmd.get("creator", "?")
    title   = cmd.get("title", "")
    img     = cmd.get("image") or cmd.get("image_hex") or cmd.get("file_id")

    # If it's a TG file_id, send directly
    if isinstance(img, str) and _looks_file_id(img):
        await update_msg.reply_photo(
            photo=img,
            caption=f"🔥 New post from #{creator}:\n\n{title}",
            reply_markup=_relay_keyboard(creator),
        )
        return

    # If it's hex → bytes
    if isinstance(img, str) and _looks_hex(img):
        try:
            b = bytes.fromhex(img)
            bio = BytesIO(b)
            bio.name = "post.jpg"
            await update_msg.reply_photo(
                photo=bio,
                caption=f"🔥 New post from #{creator}:\n\n{title}",
                reply_markup=_relay_keyboard(creator),
            )
            return
        except Exception:
            pass

    # Fallback to text if image can't be resolved
    await update_msg.reply_text(
        f"🆕 New post from *#{creator}*:\n{title}",
        parse_mode="Markdown",
        reply_markup=_relay_keyboard(creator),
    )


# ───────────────────────────────────────────────
# Dashboard handlers (expanded: handle relay + subchg + dm, and send real cards)
# ───────────────────────────────────────────────
async def show_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    tg = update.effective_user.id
    msg = update.callback_query.message

    queue = read_queue()
    alerts = [
        c for c in queue
        if isinstance(c, dict)
        and c.get("type") in ("relay", "subchg", "dm")
        and get_telegram_id(str(c.get("nyx_id"))) == tg
    ]

    if not alerts:
        # 1) Tell the user
        await msg.reply_text("🔔 No pending alerts.")
        # 2) Capture old dashboards BEFORE sending the new one
        old_ids = ALL_DASH_MSGS.get(tg, [])
        # 3) Send a fresh dashboard at the bottom
        new_text, new_kb = build_dashboard(tg)
        new_msg = await context.bot.send_message(
            chat_id=tg,
            text=new_text,
            parse_mode="Markdown",
            reply_markup=new_kb,
        )
        ALL_DASH_MSGS[tg] = [new_msg.message_id]
        # 4) Now delete the old dashboards so the new one stays at the bottom
        for mid in old_ids:
            try:
                await context.bot.delete_message(chat_id=tg, message_id=mid)
            except Exception:
                pass
    else:
        # Have alerts → send them, then purge and rebuild dashboard (existing order OK)
        for c in alerts:
            t = c.get("type")
            if t == "relay":
                await _send_relay_from_queue(msg, tg, c)
            elif t == "dm":
                await msg.reply_text(
                    f"✉️ DM from *#{c.get('creator','?')}*:\n{c.get('message','')}",
                    parse_mode="Markdown"
                )
            else:  # subchg
                await msg.reply_text(
                    f"💲 Price update by *#{c.get('creator','?')}*:\n{c.get('old_price','?')} → {c.get('new_price','?')}",
                    parse_mode="Markdown"
                )

        remaining = [
            c for c in queue
            if not (
                isinstance(c, dict)
                and c.get("type") in ("relay", "subchg", "dm")
                and get_telegram_id(str(c.get("nyx_id"))) == tg
            )
        ]
        write_queue(remaining)

        # Delete old dashboards first (existing behavior), then send new
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

    # remove the "View All" button message
    try:
        await msg.delete()
    except Exception:
        pass


async def show_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    tg = update.effective_user.id
    msg = update.callback_query.message

    queue = read_queue()
    alerts = [
        c for c in queue
        if isinstance(c, dict)
        and c.get("type") in ("relay", "subchg", "dm")
        and get_telegram_id(str(c.get("nyx_id"))) == tg
    ]

    if not alerts:
        await msg.reply_text("🔔 No pending alerts.")
    else:
        for c in alerts:
            t = c.get("type")
            if t == "relay":
                await _send_relay_from_queue(msg, tg, c)
            elif t == "dm":
                await msg.reply_text(
                    f"✉️ DM from *#{c.get('creator','?')}*:\n{c.get('message','')}",
                    parse_mode="Markdown"
                )
            else:
                await msg.reply_text(
                    f"💲 Price update by *#{c.get('creator','?')}*:\n{c.get('old_price','?')} → {c.get('new_price','?')}",
                    parse_mode="Markdown"
                )

    try:
        await msg.delete()
    except Exception:
        pass


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("⚙️ Settings are not yet configurable.")
    # keep dashboard behavior identical to original (no extra push here)


# ───────────────────────────────────────────────
# Per-post Settings panel (edits the photo caption only) — original logic kept
# ───────────────────────────────────────────────
def _safe_notifs_store() -> dict:
    """Always return a dict, never a list/None/etc."""
    data = read_notifs()
    return data if isinstance(data, dict) else {}

def _notifs_get_for(tg_id: int, creator: str) -> dict:
    data = _safe_notifs_store()
    user = data.get(str(tg_id), {})
    if not isinstance(user, dict):
        user = {}
    prefs = user.get(creator, {})
    if not isinstance(prefs, dict):
        prefs = {}
    # defaults
    prefs.setdefault("mode", "immediate")
    prefs.setdefault("muted", False)
    return prefs

def _notifs_set_for(tg_id: int, creator: str, **updates):
    data = _safe_notifs_store()
    s = data.setdefault(str(tg_id), {})
    if not isinstance(s, dict):
        s = {}
        data[str(tg_id)] = s
    prefs = s.setdefault(creator, {"mode": "immediate", "muted": False})
    if not isinstance(prefs, dict):
        prefs = {"mode": "immediate", "muted": False}
        s[creator] = prefs
    prefs.update(updates)
    write_notifs(data)

def _settings_text(creator: str, prefs: dict) -> str:
    mode = prefs.get("mode", "immediate")
    muted = prefs.get("muted", False)

    status = "🔇 *Muted*" if muted else "🔔 *Active*"
    freq = {
        "immediate": "Immediate (every post)",
        "daily": "Daily Updates",
        "weekly": "Weekly Updates",
    }.get(mode, "Immediate (every post)")

    lines = [
        f"*Notification Settings for #{creator}*",
        "",
        f"Status: {status}",
        f"Delivery: *{freq}*",
        "",
        "Daily: One bundled summary each day.",
        "Weekly: One bundled summary each week.",
        "Mute: Stop all alerts from this creator.",
    ]
    return "\n".join(lines)

def _settings_keyboard(creator: str, prefs: dict) -> InlineKeyboardMarkup:
    muted = prefs.get("muted", False)
    mute_label = "Unmute" if muted else "Mute"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back", callback_data=f"back|{creator}")],
        [InlineKeyboardButton("Daily",  callback_data=f"set_daily|{creator}"),
         InlineKeyboardButton("Weekly", callback_data=f"set_weekly|{creator}")],
        [InlineKeyboardButton(mute_label, callback_data=f"toggle_mute|{creator}")]
    ])

def _original_keyboard(creator: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Settings", callback_data=f"settings|{creator}"),
         InlineKeyboardButton("Unlock",   callback_data="unlock")]
    ])

def _cap_key(chat_id: int, msg_id: int) -> str:
    return f"{chat_id}:{msg_id}"

async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Enter settings view:
      - remember the *current* caption so we can go back later
      - edit the photo caption to a settings panel (photo stays)
    """
    q = update.callback_query
    await q.answer()

    # Payload: settings|<creator>
    try:
        _, creator = q.data.split("|", 1)
    except Exception:
        creator = "?"

    chat_id = q.message.chat_id
    msg_id  = q.message.message_id
    k = _cap_key(chat_id, msg_id)

    # Store original caption once (if not already stored)
    if k not in ORIG_CAPTION:
        ORIG_CAPTION[k] = q.message.caption or ""

    prefs = _notifs_get_for(chat_id, creator)
    text  = _settings_text(creator, prefs)
    kb    = _settings_keyboard(creator, prefs)

    try:
        await q.message.edit_caption(caption=text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        print(f"[NyxFan] settings edit failed: {e!r}")

async def set_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, creator = q.data.split("|", 1)
    chat_id = q.message.chat_id
    _notifs_set_for(chat_id, creator, mode="daily", muted=False)
    prefs = _notifs_get_for(chat_id, creator)
    await q.message.edit_caption(
        caption=_settings_text(creator, prefs),
        parse_mode="Markdown",
        reply_markup=_settings_keyboard(creator, prefs),
    )

async def set_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, creator = q.data.split("|", 1)
    chat_id = q.message.chat_id
    _notifs_set_for(chat_id, creator, mode="weekly", muted=False)
    prefs = _notifs_get_for(chat_id, creator)
    await q.message.edit_caption(
        caption=_settings_text(creator, prefs),
        parse_mode="Markdown",
        reply_markup=_settings_keyboard(creator, prefs),
    )

async def toggle_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, creator = q.data.split("|", 1)
    chat_id = q.message.chat_id
    prefs = _notifs_get_for(chat_id, creator)
    new_muted = not bool(prefs.get("muted", False))
    _notifs_set_for(chat_id, creator, muted=new_muted)
    prefs = _notifs_get_for(chat_id, creator)
    await q.message.edit_caption(
        caption=_settings_text(creator, prefs),
        parse_mode="Markdown",
        reply_markup=_settings_keyboard(creator, prefs),
    )

async def back_to_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, creator = q.data.split("|", 1)
    chat_id = q.message.chat_id
    msg_id  = q.message.message_id
    k = _cap_key(chat_id, msg_id)

    original = ORIG_CAPTION.get(k) or "🔥 New post"
    try:
        await q.message.edit_caption(
            caption=original,
            reply_markup=_original_keyboard(creator),
        )
    except Exception as e:
        print(f"[NyxFan] back edit failed: {e!r}")
    # keep ORIG_CAPTION[k] around in case user opens settings again
