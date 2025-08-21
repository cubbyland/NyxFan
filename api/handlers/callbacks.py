# cubbyland-nyxfan/api/handlers/callbacks.py

from io import BytesIO
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes

from api.utils.io import read_queue, write_queue, read_notifs, write_notifs
from api.utils.state import USER_DISP, ALL_DASH_MSGS, ORIG_CAPTION
from api.handlers.dashboard import build_dashboard
from shared.fan_registry import get_telegram_id


# ───────────────────────────────────────────────
# Unlock payload cache (filled by fan refresh worker via `unlock_register`)
# key: content_id (str) → payload (any structure your proxy enqueued)
# ───────────────────────────────────────────────
UNLOCK_STORE: dict[str, dict] = {}


# ───────────────────────────────────────────────
# Helpers to render the same post component used by Proxy
# ───────────────────────────────────────────────
def _relay_keyboard(creator: str, content_id: Optional[str] = None) -> InlineKeyboardMarkup:
    """
    If a content_id is known, bake it into Unlock callback so we can confirm & deliver.
    Fallback to plain 'unlock' if not present (older relays).
    """
    unlock_cb = f"unlock|{content_id}" if content_id else "unlock"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Settings", callback_data=f"settings|{creator}"),
         InlineKeyboardButton("Unlock",   callback_data=unlock_cb)]
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
    content_id = cmd.get("content_id")  # OPTIONAL

    # If it's a TG file_id, send directly
    if isinstance(img, str) and _looks_file_id(img):
        await update_msg.reply_photo(
            photo=img,
            caption=f"🔥 New post from #{creator}:\n\n{title}",
            reply_markup=_relay_keyboard(creator, content_id),
        )
        return

    # If it's hex → bytes
    if isinstance(img, str) and _looks_hex(img):
        try:
            b = bytes.fromhex(img)
            bio = BytesIO(b); bio.name = "post.jpg"
            await update_msg.reply_photo(
                photo=bio,
                caption=f"🔥 New post from #{creator}:\n\n{title}",
                reply_markup=_relay_keyboard(creator, content_id),
            )
            return
        except Exception as e:
            err = f"hex->bytes failed: {e!r}"
    else:
        err = "unusable image payload (no valid file_id/hex)"

    # ── MEDIA FAILED: report to Proxy; DO NOT send a fallback to the fan ──
    try:
        q = read_queue()
        q.append({
            "type": "proxy_alert",
            "nyx_id": str(tg),
            "source": "fan/_send_relay_from_queue",
            "reason": "relay_media_unresolved",
            "creator": creator,
            "title": title,
            "original_cmd": cmd,
            "error": err,
        })
        write_queue(q)
    except Exception:
        # never leak errors to the fan
        pass


# ───────────────────────────────────────────────
# Dashboard handlers (expanded: handle relay + subchg + dm, and send real cards)
# ───────────────────────────────────────────────
# paste this full function over your existing one
async def show_alerts(update, context):
    """
    Callback: "View All"
    - Consume ONLY this user's pending items (relay/subchg/dm) from the shared queue
    - Send each item exactly once
    - THEN post a fresh dashboard at the bottom and delete the old dashboard(s)
      so the dashboard stays anchored without triggering a push notification.
    """
    # Localized imports to avoid any top-level circulars
    from io import BytesIO
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.error import BadRequest
    from api.utils.io import read_queue, write_queue
    from api.handlers.dashboard import build_dashboard
    from api.utils.state import ALL_DASH_MSGS
    from shared.fan_registry import get_telegram_id

    cq = update.callback_query
    await cq.answer()
    tg = cq.from_user.id

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

    def _relay_keyboard(creator: str, content_id: str | None = None) -> InlineKeyboardMarkup:
        unlock_cb = f"unlock|{content_id}" if content_id else "unlock|none"
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Settings", callback_data=f"settings|{creator}"),
             InlineKeyboardButton("Unlock",   callback_data=unlock_cb)]
        ])

    # ---- Consume this user's items from the shared queue (one-shot semantics)
    queue = read_queue()
    mine: list[dict] = []
    kept: list[dict] = []

    for c in queue:
        try:
            t = c.get("type")
            if t not in ("relay", "subchg", "dm"):
                kept.append(c)
                continue
            nyx = c.get("nyx_id")
            if get_telegram_id(str(nyx)) != tg:
                kept.append(c)
                continue
            # This item belongs to this user → consume now
            mine.append(c)
        except Exception:
            # Defensive: if anything odd, don't drop it
            kept.append(c)

    # Write back the kept items; consumed ones are removed from disk
    write_queue(kept)

    # ---- Send each consumed item exactly once (in-order)
    for c in mine:
        t = c.get("type")
        creator = c.get("creator", "?")

        if t == "dm":
            msg = f"✉️ DM from *#{creator}*:\n{c.get('message','')}"
            await context.bot.send_message(chat_id=tg, text=msg, parse_mode="Markdown")
            continue

        if t == "subchg":
            oldp = c.get("old_price", "?")
            newp = c.get("new_price", "?")
            msg = f"💲 Price update by *#{creator}*:\n{oldp} → {newp}"
            await context.bot.send_message(chat_id=tg, text=msg, parse_mode="Markdown")
            continue

        if t == "relay":
            title = c.get("title", "")
            caption = f"🔥 New post from #{creator}:\n\n{title}"
            content_id = c.get("content_id")
            img = c.get("file_id") or c.get("image") or c.get("image_hex")

            # Prefer Telegram file_id if present
            if isinstance(img, str) and _looks_file_id(img):
                await context.bot.send_photo(
                    chat_id=tg,
                    photo=img,
                    caption=caption,
                    reply_markup=_relay_keyboard(creator, content_id),
                )
                continue

            # Hex bytes fallback
            if isinstance(img, str) and _looks_hex(img):
                try:
                    bio = BytesIO(bytes.fromhex(img))
                    bio.name = "post.jpg"
                    await context.bot.send_photo(
                        chat_id=tg,
                        photo=bio,
                        caption=caption,
                        reply_markup=_relay_keyboard(creator, content_id),
                    )
                    continue
                except Exception:
                    pass

            # Final text fallback
            await context.bot.send_message(
                chat_id=tg,
                text=caption,
                reply_markup=_relay_keyboard(creator, content_id),
            )

    # ---- Post a fresh dashboard at the bottom (no push; user initiated via callback)
    text, kb = build_dashboard(tg)
    new_msg = await context.bot.send_message(chat_id=tg, text=text, parse_mode="Markdown", reply_markup=kb)

    # Delete any older dashboard messages to keep the thread clean
    old_ids = ALL_DASH_MSGS.get(tg, [])
    for mid in old_ids:
        try:
            await context.bot.delete_message(chat_id=tg, message_id=mid)
        except BadRequest:
            pass
        except Exception:
            pass

    # Track the latest dashboard message id
    ALL_DASH_MSGS[tg] = [new_msg.message_id]

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
# Unlock flow (confirmation → deliver)
# ───────────────────────────────────────────────
def _cap_key(chat_id: int, msg_id: int) -> str:
    return f"{chat_id}:{msg_id}"

def _confirm_keyboard(creator: str, content_id: Optional[str]) -> InlineKeyboardMarkup:
    if content_id:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm", callback_data=f"unlock_confirm|{content_id}")],
            [InlineKeyboardButton("⬅ Back",    callback_data=f"back|{creator}")]
        ])
    # No content id known → only back
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back", callback_data=f"back|{creator}")]
    ])

async def unlock_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    When user taps Unlock: swap the caption to a confirmation panel.
    Callback data formats supported:
      - "unlock"                    (no content id; older cards)
      - "unlock|<content_id>"       (preferred)
    """
    q = update.callback_query
    await q.answer()

    chat_id = q.message.chat_id
    msg_id  = q.message.message_id
    k = _cap_key(chat_id, msg_id)

    # store original caption once so Back works
    if k not in ORIG_CAPTION:
        ORIG_CAPTION[k] = q.message.caption or ""

    # extract creator from original caption if present
    creator = "?"
    cap = q.message.caption or ""
    # expects "New post from #Creator" format
    if "# " in cap:  # very defensive (unlikely)
        pass
    else:
        # cheap parse: find first '#'
        hash_idx = cap.find("#")
        if hash_idx != -1:
            # collect until whitespace or newline
            j = hash_idx + 1
            name = []
            while j < len(cap) and cap[j] not in (" ", "\n", "\t", ":", "—"):
                name.append(cap[j]); j += 1
            if name:
                creator = "".join(name)

    # parse optional content_id
    try:
        parts = q.data.split("|", 1)
        content_id = parts[1] if len(parts) == 2 else None
    except Exception:
        content_id = None

    text = (
        f"🔓 *Unlock full content from #{creator}?*\n\n"
        "You’ll receive the full drop here. Continue?"
    )
    try:
        await q.message.edit_caption(
            caption=text,
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard(creator, content_id),
        )
    except Exception as e:
        print(f"[NyxFan] unlock confirm edit failed: {e!r}")

async def unlock_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Deliver the cached unlock payload. Supports simple structures:
      { "text": "...", "images": [<hex|file_id>...] }
    Extend as needed to match your proxy's `unlock_register` payloads.
    """
    q = update.callback_query
    await q.answer()

    # extract content_id
    content_id = None
    try:
        _, content_id = q.data.split("|", 1)
    except Exception:
        pass

    if not content_id or content_id not in UNLOCK_STORE:
        await q.message.reply_text("⚠️ This content isn’t ready yet.")
        # go back to original card if we can
        try:
            orig = ORIG_CAPTION.get(_cap_key(q.message.chat_id, q.message.message_id)) or "🔥 New post"
            await q.message.edit_caption(caption=orig)
        except Exception:
            pass
        return

    payload = UNLOCK_STORE.get(content_id, {})

    # 1) Acknowledge & restore original post UI
    try:
        await q.message.edit_caption(
            caption="✅ Unlocked. Sending content…"
        )
    except Exception:
        pass

    # 2) Deliver content
    text = payload.get("text")
    images = payload.get("images") or payload.get("media") or []

    if isinstance(text, str) and text.strip():
        try:
            await context.bot.send_message(chat_id=q.message.chat_id, text=text)
        except Exception as e:
            print(f"[NyxFan] unlock text send failed: {e!r}")

    # send up to 10 images (Telegram album limit)
    sendables = []
    for item in images[:10]:
        if isinstance(item, str) and _looks_file_id(item):
            sendables.append(InputMediaPhoto(media=item))
        elif isinstance(item, str) and _looks_hex(item):
            try:
                bio = BytesIO(bytes.fromhex(item)); bio.name = "unlock.jpg"
                sendables.append(InputMediaPhoto(media=bio))
            except Exception:
                pass

    try:
        if len(sendables) == 1:
            # single item → sendPhoto
            m = sendables[0]
            await context.bot.send_photo(chat_id=q.message.chat_id, photo=m.media)
        elif len(sendables) > 1:
            # album
            await context.bot.send_media_group(chat_id=q.message.chat_id, media=sendables)
    except Exception as e:
        print(f"[NyxFan] unlock media send failed: {e!r}")

    # 3) Optional: clean up the confirmation caption back to original
    try:
        orig = ORIG_CAPTION.get(_cap_key(q.message.chat_id, q.message.message_id)) or "🔥 New post"
        await q.message.edit_caption(caption=orig)
    except Exception:
        pass

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
