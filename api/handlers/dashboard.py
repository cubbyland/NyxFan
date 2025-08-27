# NyxFan/api/handlers/dashboard.py
from __future__ import annotations

from typing import Tuple, List, Dict, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from api.utils.io import read_queue, read_notifs
from api.utils.state import USER_DISP
from api.utils.env import BOT_USERNAME
from shared.fan_registry import get_telegram_id


def _is_creator_muted(tg_id: int, creator: str) -> bool:
    data = read_notifs() or {}
    u = data.get(str(tg_id), {}) if isinstance(data, dict) else {}
    prefs = u.get(creator, {}) if isinstance(u, dict) else {}
    return bool(prefs.get("muted", False))


def build_dashboard(tg_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Build the dashboard text + inline keyboard for a given user.
    Rules:
      - Show ONLY pending alerts that would not have generated a push (muted creators).
      - Posts come from pending *relay* commands for muted creators (Fan sends them on 'View All').
      - Price updates and DMs likewise show only when the creator is muted.
    """
    disp = USER_DISP.get(tg_id, str(tg_id))
    header = f"{disp}’s Dashboard"

    queue = read_queue()

    # creator → {posts, prices, dms}
    summary: dict[str, dict[str, int]] = {}
    for c in queue:
        try:
            t = c.get("type")
            if t not in ("relay", "subchg", "dm"):
                continue
            if get_telegram_id(str(c.get("nyx_id"))) != tg_id:
                continue

            creator = str(c.get("creator", "?"))
            if not _is_creator_muted(tg_id, creator):
                # un-muted alerts should NEVER appear on the dashboard
                continue

            grp = summary.setdefault(creator, {"posts": 0, "prices": 0, "dms": 0})
            if t == "relay":
                grp["posts"] += 1
            elif t == "subchg":
                grp["prices"] += 1
            elif t == "dm":
                grp["dms"] += 1
        except Exception:
            continue

    if summary:
        lines = ["🔔 *Pending Alerts:*", ""]
        for creator, cnts in summary.items():
            parts: list[str] = []
            if cnts["posts"]:
                url = f"https://t.me/{BOT_USERNAME}?start=filter_relay_{creator}"
                parts.append(f"[{cnts['posts']} post{'s' if cnts['posts']>1 else ''}]({url})")
            if cnts["prices"]:
                url = f"https://t.me/{BOT_USERNAME}?start=filter_subchg_{creator}"
                parts.append(f"[{cnts['prices']} price update{'s' if cnts['prices']>1 else ''}]({url})")
            if cnts["dms"]:
                url = f"https://t.me/{BOT_USERNAME}?start=filter_dm_{creator}"
                parts.append(f"[{cnts['dms']} message{'s' if cnts['dms']>1 else ''}]({url})")
            if parts:
                lines.append(f"#{creator}: " + " | ".join(parts))
        body = "\n".join(lines)
    else:
        body = "🔔 No pending alerts."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("View All", callback_data="show_alerts")],
        [InlineKeyboardButton("Settings", callback_data="show_settings")],
    ])

    return f"{header}\n\n{body}", kb
