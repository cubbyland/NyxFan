# api/jobs/handlers/fan_relay.py

from __future__ import annotations

from typing import List, Dict, Any

from api.utils.helpers import fan_bot, alert_admin

# Preferences (shared JSON: shared/fan_notifications.json)
try:
    from api.jobs.support.prefs import get_prefs as _get_prefs
except Exception:
    # Minimal fallback
    def _get_prefs(tg_id: int, creator: str) -> dict:
        try:
            from api.utils.io import read_notifs
            data = read_notifs()
            user = data.get(str(tg_id), {}) if isinstance(data, dict) else {}
            prefs = user.get(creator, {})
            return {"mode": prefs.get("mode", "immediate"), "muted": bool(prefs.get("muted", False))}
        except Exception:
            return {"mode": "immediate", "muted": False}

# Resolve TG id from nyx_id
try:
    from api.jobs.support.resolve import resolve_tg_from_any as _resolve_tg
except Exception:
    from shared.fan_registry import get_telegram_id as _get_telegram_id
    def _resolve_tg(nyx_or_tg):
        s = str(nyx_or_tg or "").strip()
        if s.isdigit() and len(s) >= 9:
            try:
                return int(s)
            except Exception:
                return None
        return _get_telegram_id(str(nyx_or_tg))

# Inline keyboard (Settings + Unlock)
try:
    from api.jobs.support.keyboards import relay_keyboard as _relay_keyboard
except Exception:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    def _relay_keyboard(creator: str, content_id: str | None = None):
        row = [InlineKeyboardButton("Settings", callback_data=f"settings|{creator}")]
        if content_id:
            row.append(InlineKeyboardButton("Unlock", callback_data=f"unlock|{content_id}"))
        return InlineKeyboardMarkup([row])


async def handle_fan_relay(queue: List[dict], new_q: List[dict], cmd: Dict[str, Any]) -> List[dict]:
    """
    FanBot = consumer/deliverer.
    - If creator is muted for this fan: DO NOT send any chat message. Enqueue dash_refresh.
    - If not muted: send teaser to chat with Unlock keyboard.
    - In both cases, emit fan_unlock_register so FanBot can deliver unlockables later.
    """
    out: List[dict] = []

    nyx = cmd.get("nyx_id")
    if not nyx:
        return out
    tg = _resolve_tg(nyx)
    if not tg:
        return out

    creator = cmd.get("creator", "?")
    title = cmd.get("title", "")
    content_id = cmd.get("content_id") or ""
    teaser = cmd.get("teaser") or {}
    fid = teaser.get("file_id")
    kind = (teaser.get("kind") or "photo").lower()

    # prefs → muted?
    prefs = _get_prefs(int(tg), creator)
    muted = bool(prefs.get("muted", False))

    caption = f"🔥 New post from #{creator}:\n\n{title}"
    kb = _relay_keyboard(creator, content_id)

    m = None
    if not muted:
        try:
            if kind == "photo":
                m = await fan_bot.send_photo(chat_id=tg, photo=fid, caption=caption, reply_markup=kb)
            elif kind == "animation":
                m = await fan_bot.send_animation(chat_id=tg, animation=fid, caption=caption, reply_markup=kb)
            elif kind == "video":
                m = await fan_bot.send_video(chat_id=tg, video=fid, caption=caption, reply_markup=kb, supports_streaming=True)
            else:
                m = await fan_bot.send_document(chat_id=tg, document=fid, caption=caption, reply_markup=kb)
        except Exception as e:
            alert_admin(f"[fan_relay] delivery failed: {e!r}")
            out.append({
                "type": "proxy_alert",
                "nyx_id": str(nyx),
                "source": "fan/handlers.fan_relay",
                "reason": "fan_delivery_failed",
                "creator": creator,
                "title": title,
                "original_cmd": {"content_id": content_id},
                "error": str(e),
            })
            return out
    else:
        # Muted → dashboard refresh only
        out.append({"type": "dash_refresh", "nyx_id": nyx})

    # Register unlockables for later delivery (with or without teaser linkage)
    fur: Dict[str, Any] = {
        "type": "fan_unlock_register",
        "nyx_id": nyx,
        "content_id": content_id,
    }
    if isinstance(cmd.get("items"), list) and cmd["items"]:
        fur["items"] = cmd["items"]
    elif "content" in cmd:
        fur["content"] = cmd["content"]

    if m is not None:
        fur["teaser_msg_chat_id"] = tg
        fur["teaser_msg_id"] = m.message_id

    out.append(fur)
    return out
