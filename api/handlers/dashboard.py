# cubbyland-nyxfan/api/handlers/dashboard.py
from typing import Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from api.utils.io import read_queue
from api.utils.state import USER_DISP
from api.utils.env import BOT_USERNAME
from shared.fan_registry import get_telegram_id


def build_dashboard(tg_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Build the dashboard text + inline keyboard for a given Telegram user id.
      - shows pending counts grouped by creator
      - shows posts, price updates, and DMs
      - buttons: "View All" and "Settings"
    """
    disp = USER_DISP.get(tg_id, str(tg_id))
    header = f"{disp}’s Dashboard"
    queue = read_queue()

    # creator → {posts, prices, dms}
    summary: dict[str, dict[str, int]] = {}
    for c in queue:
        if c.get("type") not in ("relay", "subchg", "dm"):
            continue
        if get_telegram_id(str(c.get("nyx_id"))) != tg_id:
            continue
        creator = c.get("creator", "?")
        grp = summary.setdefault(creator, {"posts": 0, "prices": 0, "dms": 0})
        if c["type"] == "relay":
            grp["posts"] += 1
        elif c["type"] == "subchg":
            grp["prices"] += 1
        elif c["type"] == "dm":
            grp["dms"] += 1

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
            lines.append(f"#{creator}: " + " | ".join(parts))
        body = "\n".join(lines)
    else:
        body = "🔔 No pending alerts."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("View All", callback_data="show_alerts")],
        [InlineKeyboardButton("Settings", callback_data="show_settings")],
    ])
    return f"{header}\n\n{body}", kb
