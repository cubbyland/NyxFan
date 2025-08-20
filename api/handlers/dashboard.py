# NyxFan/api/utils/dashboard.py

from typing import Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .helpers import read_queue, get_telegram_id, USER_DISP


def build_dashboard(
    tg_id: int,
    bot_username: str,
    inbox_url: str,
    profile_url: str,
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Build the dashboard text + inline keyboard for a given Telegram user id.
    """
    disp = USER_DISP.get(tg_id, str(tg_id))
    header = f"{disp}’s Dashboard"
    queue = read_queue()

    # creator → {posts, prices}
    summary: dict[str, dict[str, int]] = {}
    for c in queue:
        if c.get("type") not in ("relay", "subchg"):
            continue
        if get_telegram_id(str(c.get("nyx_id"))) != tg_id:
            continue
        creator = c.get("creator", "?")
        grp = summary.setdefault(creator, {"posts": 0, "prices": 0})
        if c["type"] == "relay":
            grp["posts"] += 1
        else:
            grp["prices"] += 1

    if summary:
        lines = ["🔔 *Pending Alerts:*", ""]
        for creator, cnts in summary.items():
            parts: list[str] = []
            if cnts["posts"]:
                url = f"https://t.me/{bot_username}?start=filter_relay_{creator}"
                parts.append(f"[{cnts['posts']} post{'s' if cnts['posts']>1 else ''}]({url})")
            if cnts["prices"]:
                url = f"https://t.me/{bot_username}?start=filter_subchg_{creator}"
                parts.append(f"[{cnts['prices']} price update{'s' if cnts['prices']>1 else ''}]({url})")
            lines.append(f"#{creator}: " + " | ".join(parts))
        body = "\n".join(lines)
    else:
        body = "🔔 No pending alerts."

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("View All", callback_data="show_alerts"),
            InlineKeyboardButton("Inbox", url=inbox_url),
        ],
        [
            InlineKeyboardButton("Profile", url=profile_url),
            InlineKeyboardButton("Settings", callback_data="show_settings"),
        ],
    ])
    return f"{header}\n\n{body}", kb
