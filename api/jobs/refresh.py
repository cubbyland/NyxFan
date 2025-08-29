# NyxFan/api/jobs/refresh.py
"""
Fan-side background consumer: processes only 'dash_refresh' pokes.
Matches original behavior: edit dashboard inline if it exists; never push new.
"""

from telegram.ext import ContextTypes
from telegram.error import BadRequest

from api.utils.io import read_queue, write_queue
from api.utils.state import ALL_DASH_MSGS
from api.handlers.dashboard import build_dashboard
from shared.fan_registry import get_telegram_id


def _resolve_tg_from_any(nyx_or_tg) -> int | None:
    """
    Accept either a canonical NYX ID (string) or a raw Telegram user id.
    1) Try NYX→TG via registry
    2) Fallback: if it's a numeric string that looks like a TG id, use it directly
    """
    tg = get_telegram_id(str(nyx_or_tg))
    if tg:
        return tg
    s = str(nyx_or_tg or "").strip()
    if s.isdigit() and len(s) >= 9:  # typical TG user-id length
        try:
            return int(s)
        except Exception:
            return None
    return None


async def _edit_dashboard_if_exists(context: ContextTypes.DEFAULT_TYPE, tg: int) -> bool:
    """Background-safe update: edit existing dashboard only (no new message)."""
    mids = ALL_DASH_MSGS.get(tg, [])
    mid = mids[-1] if mids else None
    if not mid:
        return False
    text, kb = build_dashboard(tg)

    # Make header show the user's display (username/full name) instead of numeric id
    try:
        chat = await context.bot.get_chat(tg)
        disp_parts = [getattr(chat, "username", None)]
        if not disp_parts[0]:
            name = " ".join(x for x in [getattr(chat, "first_name", None), getattr(chat, "last_name", None)] if x)
            disp = name.strip() if name else str(tg)
        else:
            disp = disp_parts[0]
        # Replace common header forms
        text = (
            text.replace(f"{tg}’s Dashboard", f"{disp}’s Dashboard")
                .replace(f"{tg}'s Dashboard", f"{disp}'s Dashboard")
                .replace(str(tg), disp)
        )
    except Exception:
        pass

    try:
        await context.bot.edit_message_text(
            chat_id=tg, message_id=mid,
            text=text, parse_mode="Markdown", reply_markup=kb
        )
        return True
    except BadRequest:
        return False


async def process_fan_queue(context: ContextTypes.DEFAULT_TYPE):
    queue = read_queue()
    new_q = []
    for cmd in queue:
        t = cmd.get("type")
        # Only handle dash_refresh here; everything else stays in the queue
        if t != "dash_refresh":
            new_q.append(cmd)
            continue

        tg = _resolve_tg_from_any(cmd.get("nyx_id"))
        if not tg:
            # Can't map yet; keep it so it can be retried on a later tick
            new_q.append(cmd)
            continue

        # Background-safe: edit existing dashboard only; if none, skip (avoid push).
        await _edit_dashboard_if_exists(context, tg)
        # Do not requeue this poke.

    write_queue(new_q)
