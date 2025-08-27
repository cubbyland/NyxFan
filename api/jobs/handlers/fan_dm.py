from __future__ import annotations
from typing import List, Dict, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from api.utils.helpers import fan_bot
from api.utils.io import read_notifs
from shared.fan_registry import get_telegram_id

def _prefs(tg_id: int, creator: str) -> dict:
    d = read_notifs() or {}
    return (d.get(str(tg_id), {}) or {}).get(creator, {"mode":"immediate","muted":False}) or {"mode":"immediate","muted":False}

def _kb(creator: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Settings", callback_data=f"settings|{creator}")]])

def _resolve_tg(nyx_or_tg) -> int | None:
    tg = get_telegram_id(str(nyx_or_tg))
    if tg: return tg
    s = str(nyx_or_tg or "")
    if s.isdigit() and len(s) >= 9:
        try: return int(s)
        except Exception: return None
    return None

async def handle_fan_dm(queue: List[dict], new_q: List[dict], cmd: Dict[str, Any]) -> List[dict]:
    out: List[dict] = []
    nyx = cmd.get("nyx_id")
    tg  = _resolve_tg(nyx)
    if not tg:  # can't route yet
        return out

    creator = cmd.get("creator", "?")
    text    = (cmd.get("message") or "").strip()

    if _prefs(int(tg), creator).get("muted", False):
        # do NOT push; let dashboard show it
        out.append({"type":"dash_refresh", "nyx_id": nyx})
        return out

    cap = f"✉️ DM from *#{creator}*:\n{text}" if text else f"✉️ DM from *#{creator}*"
    try:
        await fan_bot.send_message(chat_id=tg, text=cap, parse_mode="Markdown", reply_markup=_kb(creator))
    except Exception:
        pass

    # Optional: deliver any media items (same caption)
    for it in (cmd.get("items") or []):
        kind = (it.get("kind") or "").lower()
        fid  = it.get("file_id")
        if not isinstance(fid, str) or len(fid) < 10: continue
        try:
            if kind == "photo":
                await fan_bot.send_photo(chat_id=tg, photo=fid, caption=cap)
            elif kind == "animation":
                await fan_bot.send_animation(chat_id=tg, animation=fid, caption=cap)
            elif kind == "video":
                await fan_bot.send_video(chat_id=tg, video=fid, caption=cap, supports_streaming=True)
            else:
                await fan_bot.send_document(chat_id=tg, document=fid, caption=cap)
        except Exception:
            pass
    return out
