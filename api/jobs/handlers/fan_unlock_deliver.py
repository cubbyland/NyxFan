# api/jobs/handlers/fan_unlock_deliver.py

from __future__ import annotations

from typing import List, Dict, Any
from pathlib import Path
import json

from api.utils.helpers import fan_bot

# thanks caption (fallback if support module not present)
try:
    from api.jobs.support.captions import thanks_caption as _thanks_caption
except Exception:
    def _thanks_caption(title: str | None, creator: str | None) -> str:
        t = (title or "").strip() or "this post"
        c = (creator or "").lstrip("#").strip() or "creator"
        return f"Thank you for your purchase of {t} by {c}\n#{c}"

# resolve tg from nyx
try:
    from api.jobs.support.resolve import resolve_tg_from_any as _resolve_tg
except Exception:
    from shared.fan_registry import get_telegram_id as _get_telegram
    def _resolve_tg(nyx_or_tg):
        s = str(nyx_or_tg or "").strip()
        if s.isdigit() and len(s) >= 9:
            try:
                return int(s)
            except Exception:
                return None
        return _get_telegram(str(nyx_or_tg))

# unlock store
try:
    from api.utils.helpers import PROJECT_ROOT
    SHARED_DIR = Path(PROJECT_ROOT) / "shared"
except Exception:
    SHARED_DIR = Path(__file__).resolve().parents[4] / "shared"
UNLOCK_PATH = SHARED_DIR / "unlock_index.json"


def _read_unlock() -> Dict[str, Any]:
    try:
        if UNLOCK_PATH.exists():
            return json.loads(UNLOCK_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_unlock(d: Dict[str, Any]) -> None:
    UNLOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNLOCK_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


async def handle_fan_unlock_deliver(queue: List[dict], new_q: List[dict], cmd: Dict[str, Any]) -> List[dict]:
    """
    FanBot delivery:
      - Figures out chat/teaser linkage.
      - Sends each item with a thank-you caption.
      - Works even when no teaser exists (fresh messages).
    """
    out: List[dict] = []

    nyx = cmd.get("nyx_id")
    if not nyx:
        return out
    tg = _resolve_tg(nyx)
    if not tg:
        return out

    cid = cmd.get("content_id")
    idx = _read_unlock()
    ent = idx.get(cid, {}) if cid else {}

    # prefer items passed in; else look them up from the store
    items = cmd.get("items")
    if not isinstance(items, list) or not items:
        items = ent.get("items", [])

    if not items:
        # nothing to send; bail quietly
        return out

    # teaser linkage if available (reply threading)
    chat_id = cmd.get("teaser_msg_chat_id", ent.get("teaser_msg_chat_id"))
    msg_id = cmd.get("teaser_msg_id", ent.get("teaser_msg_id"))

    # caption
    cap = _thanks_caption(ent.get("title") or cmd.get("title"), ent.get("creator") or cmd.get("creator"))

    # deliver
    for it in items:
        kind = (it.get("kind") or "").lower()
        fid = it.get("file_id")
        if not isinstance(fid, str) or len(fid) < 10:
            continue
        if kind == "photo":
            await fan_bot.send_photo(chat_id=tg, photo=fid, caption=cap, reply_to_message_id=msg_id if chat_id else None)
        elif kind == "animation":
            await fan_bot.send_animation(chat_id=tg, animation=fid, caption=cap, reply_to_message_id=msg_id if chat_id else None)
        elif kind == "video":
            await fan_bot.send_video(chat_id=tg, video=fid, caption=cap, reply_to_message_id=msg_id if chat_id else None, supports_streaming=True)
        else:
            await fan_bot.send_document(chat_id=tg, document=fid, caption=cap, reply_to_message_id=msg_id if chat_id else None)

    # mark delivered in the store (optional, useful for dashboard)
    if cid:
        ent["delivered"] = True
        idx[cid] = ent
        _write_unlock(idx)

    return out
