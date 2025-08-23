# cubbyland-nyxfan/api/handlers/callbacks.py
from __future__ import annotations

from typing import Tuple, List, Dict, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

from api.utils.io import read_queue, write_queue, read_notifs, write_notifs
from api.utils.state import ORIG_CAPTION, ALL_DASH_MSGS
from api.utils.env import BOT_USERNAME
from api.handlers.dashboard import build_dashboard
from shared.fan_registry import get_telegram_id


# ───────────────────────────── helpers ─────────────────────────────

def _relay_keyboard(creator: str, content_id: str | None = None) -> InlineKeyboardMarkup:
    """
    Inline keyboard shown under the teaser post sent to the fan.
    """
    unlock_cb = f"unlock|{content_id}" if content_id else "unlock"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Settings", callback_data=f"settings|{creator}"),
            InlineKeyboardButton("Unlock",   callback_data=unlock_cb),
        ]
    ])


def _kb_settings_only(creator: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Settings", callback_data=f"settings|{creator}")]])


def _kb_settings_unlock(creator: str, content_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Settings", callback_data=f"settings|{creator}"),
        InlineKeyboardButton("Unlock",   callback_data=f"unlock|{content_id}")
    ]])


def _kb_confirm(content_id: str) -> InlineKeyboardMarkup:
    # Back (left), Confirm (right)
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Back",    callback_data=f"unlock_back|{content_id}"),
        InlineKeyboardButton("Confirm", callback_data=f"unlock_confirm|{content_id}"),
    ]])



def _extract_creator_from_caption(caption: str | None) -> str | None:
    """
    We format captions like: "🔥 New post from #<creator>:\n\n<title>"
    Try to pull #<creator> back out for settings/unlock flows.
    """
    if not caption:
        return None
    try:
        s = caption.split("from #", 1)[1]
        return s.split(":", 1)[0].strip()
    except Exception:
        return None


def _looks_file_id(s: str) -> bool:
    return isinstance(s, str) and len(s) > 20 and not s.startswith(("http://", "https://"))


async def _send_relay_from_cmd(msg, cmd: dict) -> None:
    """
    Fan-side 'View All' sender for a single RELAY item.
    Requirements:
      - Use ONLY Telegram file_ids (Fan-scoped preferred, but any file_id attempt quietly).
      - Try photo → animation → video → document.
      - If nothing usable, DO NOTHING (no fan-visible text fallback).
    """
    creator = cmd.get("creator", "?")
    title   = cmd.get("title", "")
    caption = f"🔥 New post from #{creator}:\n\n{title}"
    content_id = cmd.get("content_id") or cmd.get("id") or cmd.get("cid")

    # Check common keys for a file_id
    def _fid() -> str | None:
        for k in [
            "file_id", "image", "photo",
            "animation", "video", "document",
            "image_file_id", "media_file_id",
            "video_file_id", "animation_file_id", "document_file_id",
            "teaser", "teaser_file_id",
        ]:
            v = cmd.get(k)
            if isinstance(v, str) and _looks_file_id(v):
                return v
        return None

    fid = _fid()
    if not fid:
        return

    # Try in order; if wrong kind, Telegram raises → silently try next
    try:
        await msg.reply_photo(photo=fid, caption=caption, reply_markup=_relay_keyboard(creator, content_id))
        return
    except Exception:
        pass
    try:
        await msg.reply_animation(animation=fid, caption=caption, reply_markup=_relay_keyboard(creator, content_id))
        return
    except Exception:
        pass
    try:
        await msg.reply_video(video=fid, caption=caption, reply_markup=_relay_keyboard(creator, content_id))
        return
    except Exception:
        pass
    try:
        await msg.reply_document(document=fid, caption=caption, reply_markup=_relay_keyboard(creator, content_id))
        return
    except Exception:
        pass
    # No fan-visible fallback.


def _get_user_prefs(tg_id: int, creator: str) -> dict:
    """
    Fan-side read of per-creator prefs (mode/muted).
    File shape maintained by Proxy & Fan sides:
      {
        "<tg_id>": {
          "<creator>": { "mode": "immediate|daily|weekly", "muted": bool }
        }
      }
    """
    data = read_notifs()
    user = data.get(str(tg_id), {}) if isinstance(data, dict) else {}
    prefs = user.get(creator, {}) if isinstance(user, dict) else {}
    if not isinstance(prefs, dict):
        prefs = {}
    prefs.setdefault("mode", "immediate")
    prefs.setdefault("muted", False)
    return prefs


def _set_user_prefs(tg_id: int, creator: str, **changes) -> dict:
    data = read_notifs()
    if not isinstance(data, dict):
        data = {}
    user = data.setdefault(str(tg_id), {})
    if not isinstance(user, dict):
        user = {}
        data[str(tg_id)] = user
    prefs = user.setdefault(creator, {})
    if not isinstance(prefs, dict):
        prefs = {}
        user[creator] = prefs
    prefs.update(changes)
    write_notifs(data)
    return prefs


# ───────────────────────────── callbacks ─────────────────────────────

async def show_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    On dashboard → 'View All'
    - Send all pending RELAYs and DMs for this user
    - Then re-post a fresh dashboard AT THE BOTTOM and delete the old dashboard
      (so dashboard is always the last message; no push notification since the user is in-session)
    """
    qd = update.callback_query
    await qd.answer()
    user_tg = qd.from_user.id

    # NEW: refresh display name from callback user so restarts don’t lose it
    from api.utils.state import USER_DISP
    disp = qd.from_user.username or qd.from_user.full_name or str(user_tg)
    USER_DISP[user_tg] = disp

    # 1) Gather and send items
    queue = read_queue()
    pending: List[dict] = []
    kept: List[dict] = []
    for c in queue:
        try:
            if (
                isinstance(c, dict)
                and c.get("type") in ("relay", "dm", "subchg")
                and get_telegram_id(str(c.get("nyx_id"))) == user_tg
            ):
                pending.append(c)
            else:
                kept.append(c)
        except Exception:
            kept.append(c)

    # Send RELAYs (media) and DMs as individual messages under the dashboard
    for c in pending:
        t = c.get("type")
        try:
            if t == "relay":
                await _send_relay_from_cmd(qd.message, c)
            elif t == "dm":
                await qd.message.reply_text(
                    f"✉️ DM from *{c.get('creator','?')}*:\n{c.get('message','')}",
                    parse_mode="Markdown",
                )
            elif t == "subchg":
                await qd.message.reply_text(
                    f"💲 Price update by *{c.get('creator','?')}*:\n{c.get('old_price','?')} → {c.get('new_price','?')}",
                    parse_mode="Markdown",
                )
        except Exception:
            # no fan-face errors; just skip on failure
            pass

    # Persist queue *as-is* (we don't consume those items here; Proxy demotes on mute and handles delivery)
    # If you DO want to consume them, uncomment next line:
    # write_queue(kept)

    # 2) Re-post dashboard at bottom, delete previous dashboard(s)
    text, kb = build_dashboard(user_tg)
    try:
        new_dash = await qd.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        new_ids = [new_dash.message_id]

        # delete older dashboards
        for mid in ALL_DASH_MSGS.get(user_tg, []):
            try:
                await context.bot.delete_message(chat_id=user_tg, message_id=mid)
            except Exception:
                pass
        ALL_DASH_MSGS[user_tg] = new_ids
    except Exception:
        pass


async def show_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Minimal: just rebuild the dashboard (digests are handled via Proxy/Fan jobs).
    """
    qd = update.callback_query
    await qd.answer()
    user_tg = qd.from_user.id

    # NEW: refresh display name
    from api.utils.state import USER_DISP
    disp = qd.from_user.username or qd.from_user.full_name or str(user_tg)
    USER_DISP[user_tg] = disp

    text, kb = build_dashboard(user_tg)

    try:
        await qd.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        # If edit fails (e.g., non-text), just send a new dashboard and delete old if tracked
        try:
            msg = await qd.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
            for mid in ALL_DASH_MSGS.get(user_tg, []):
                try:
                    await context.bot.delete_message(chat_id=user_tg, message_id=mid)
                except Exception:
                    pass
            ALL_DASH_MSGS[user_tg] = [msg.message_id]
        except Exception:
            pass


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dashboard-level 'Settings' (general help).
    Per-creator settings are handled from the post's inline 'Settings' button → show_settings_menu.
    """
    qd = update.callback_query
    await qd.answer()
    try:
        await qd.message.reply_text(
            "Per-post settings are available from the inline *Settings* button under each post. "
            "There you can mute a creator or switch to daily/weekly digests.",
            parse_mode="Markdown",
        )
    except Exception:
        pass


async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Per-post 'Settings' button → edit that message's caption into a settings menu
    with buttons for Daily / Weekly / Toggle Mute / Back.
    """
    qd = update.callback_query
    await qd.answer()
    data = qd.data or ""
    parts = data.split("|", 1)
    if len(parts) != 2:
        return
    creator = parts[1]

    msg = qd.message
    chat_id, mid = msg.chat_id, msg.message_id

    # store original caption for 'Back'
    ORIG_CAPTION[f"{chat_id}:{mid}"] = (msg.caption or "").strip()

    tg = update.effective_user.id
    prefs = _get_user_prefs(tg, creator)
    mode = prefs.get("mode", "immediate")
    muted = prefs.get("muted", False)

    lines = [
        f"⚙️ Settings for *#{creator}*",
        "",
        f"- Delivery: *{mode}*",
        f"- Muted: *{'Yes' if muted else 'No'}*",
        "",
        "Choose an option below:",
    ]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Daily",   callback_data=f"set_daily|{creator}"),
         InlineKeyboardButton("Weekly",  callback_data=f"set_weekly|{creator}")],
        [InlineKeyboardButton("Toggle Mute", callback_data=f"toggle_mute|{creator}")],
        [InlineKeyboardButton("Back",    callback_data=f"back|{creator}")],
    ])

    try:
        await context.bot.edit_message_caption(
            chat_id=chat_id, message_id=mid,
            caption="\n".join(lines),
            reply_markup=kb, parse_mode="Markdown",
        )
    except Exception:
        pass


async def set_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qd = update.callback_query
    await qd.answer()
    parts = (qd.data or "").split("|", 1)
    if len(parts) != 2:
        return
    creator = parts[1]
    tg = update.effective_user.id
    prefs = _set_user_prefs(tg, creator, mode="daily")
    await _refresh_settings_menu(qd, creator, prefs)


async def set_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qd = update.callback_query
    await qd.answer()
    parts = (qd.data or "").split("|", 1)
    if len(parts) != 2:
        return
    creator = parts[1]
    tg = update.effective_user.id
    prefs = _set_user_prefs(tg, creator, mode="weekly")
    await _refresh_settings_menu(qd, creator, prefs)


async def toggle_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qd = update.callback_query
    await qd.answer()
    parts = (qd.data or "").split("|", 1)
    if len(parts) != 2:
        return
    creator = parts[1]
    tg = update.effective_user.id
    cur = _get_user_prefs(tg, creator)
    prefs = _set_user_prefs(tg, creator, muted=not cur.get("muted", False))
    await _refresh_settings_menu(qd, creator, prefs)


async def _refresh_settings_menu(qd, creator: str, prefs: dict) -> None:
    msg = qd.message
    chat_id, mid = msg.chat_id, msg.message_id
    mode = prefs.get("mode", "immediate")
    muted = prefs.get("muted", False)
    lines = [
        f"⚙️ Settings for *#{creator}*",
        "",
        f"- Delivery: *{mode}*",
        f"- Muted: *{'Yes' if muted else 'No'}*",
        "",
        "Choose an option below:",
    ]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Daily",   callback_data=f"set_daily|{creator}"),
         InlineKeyboardButton("Weekly",  callback_data=f"set_weekly|{creator}")],
        [InlineKeyboardButton("Toggle Mute", callback_data=f"toggle_mute|{creator}")],
        [InlineKeyboardButton("Back",    callback_data=f"back|{creator}")],
    ])
    try:
        await qd.edit_message_caption(caption="\n".join(lines), reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass


async def back_to_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Restore the original caption + Settings/Unlock buttons after the settings menu.
    """
    qd = update.callback_query
    await qd.answer()
    parts = (qd.data or "").split("|", 1)
    if len(parts) != 2:
        return
    creator = parts[1]

    msg = qd.message
    chat_id, mid = msg.chat_id, msg.message_id
    orig = ORIG_CAPTION.get(f"{chat_id}:{mid}", msg.caption or "")

    # Try to recover a content_id from the original caption deep-link format? Not stored there.
    # We keep Unlock button only if this post had content_id in queue; since we don't track it here,
    # default to showing both Settings and Unlock — safe for teaser posts.
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Settings", callback_data=f"settings|{creator}")],
    ])
    try:
        await context.bot.edit_message_caption(
            chat_id=chat_id, message_id=mid,
            caption=orig,
            reply_markup=kb, parse_mode="Markdown",
        )
    except Exception:
        pass


# ───────────────────────────── unlock flow ─────────────────────────────

async def unlock_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback: 'unlock' or 'unlock|<content_id>' → show confirm UI (caption edit only; media stays).
    """
    qd = update.callback_query
    await qd.answer()
    parts = (qd.data or "unlock").split("|", 1)
    content_id = parts[1] if len(parts) == 2 else None
    if not content_id:
        return  # require a content_id for purchasable content; do nothing to the fan

    msg = qd.message
    chat_id, mid = msg.chat_id, msg.message_id

    # remember original caption so Back/Confirm can restore
    ORIG_CAPTION[f"{chat_id}:{mid}"] = (msg.caption or "").strip()

    confirm_text = "Are you sure you want to purchase this for X amount?"
    try:
        await context.bot.edit_message_caption(
            chat_id=chat_id, message_id=mid,
            caption=confirm_text,
            reply_markup=_kb_confirm(content_id)
        )
    except Exception:
        pass  # no fan-facing error


async def unlock_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback: 'unlock_back|<content_id>' → restore original caption + Settings/Unlock buttons.
    """
    qd = update.callback_query
    await qd.answer()
    parts = (qd.data or "").split("|", 1)
    if len(parts) != 2:
        return
    content_id = parts[1]

    msg = qd.message
    chat_id, mid = msg.chat_id, msg.message_id

    orig = ORIG_CAPTION.get(f"{chat_id}:{mid}", msg.caption or "")
    creator = _extract_creator_from_caption(orig) or "?"

    try:
        await context.bot.edit_message_caption(
            chat_id=chat_id, message_id=mid,
            caption=orig,
            reply_markup=_kb_settings_unlock(creator, content_id)
        )
    except Exception:
        pass


# --- replace this function in NyxFan/api/handlers/callbacks.py ---
async def unlock_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User tapped 'Confirm' on the purchase prompt.
    - Revert the teaser caption back to original (Unlock removed; Settings remains).
    - Enqueue 'unlock_deliver' for Proxy with content_id and (if available) items.
    """
    query = update.callback_query
    await query.answer()

    # Parse content_id from "unlock_confirm|<content_id>"
    data = query.data or ""
    try:
        _, content_id = data.split("|", 1)
    except ValueError:
        content_id = ""

    chat_id = query.message.chat_id
    msg_id  = query.message.message_id
    tg_id   = query.from_user.id

    # Look up a matching unlock_register (if any)
    q = read_queue()
    reg = None
    for c in reversed(q):
        try:
            if (
                isinstance(c, dict)
                and c.get("type") == "unlock_register"
                and c.get("content_id") == content_id
                and c.get("teaser_msg_chat_id") == chat_id
                and c.get("teaser_msg_id") == msg_id
            ):
                reg = c
                break
        except Exception:
            pass

    # Define items safely
    items = []
    if reg and isinstance(reg.get("items"), list):
        items = reg["items"]

    # Always enqueue unlock_deliver; Proxy can resolve from register/raw if items is empty
    q.append({
        "type": "unlock_deliver",
        "nyx_id": str(tg_id),
        "teaser_msg_chat_id": chat_id,
        "teaser_msg_id": msg_id,
        "content_id": content_id,
        "items": items,
    })
    write_queue(q)

    # Revert caption (Settings-only)
    orig_key = f"{chat_id}:{msg_id}"
    caption = ORIG_CAPTION.get(orig_key) or (query.message.caption or "New post")
    creator = _extract_creator_from_caption(caption) or "?"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Settings", callback_data=f"settings|{creator}")]])
    try:
        await query.edit_message_caption(caption=caption, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass

    await query.answer("Unlocked!")
