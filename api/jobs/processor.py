# NyxFan/api/jobs/processor.py

import json
from io import BytesIO
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from api.utils.io import read_queue, write_queue
from api.utils.helpers import fan_bot, FAN_BOT_USERNAME
from shared.fan_registry import get_telegram_id

# Track last digest message IDs per user
LAST_DIGEST: dict[str, dict[str, int]] = {}


async def process_proxy_commands(context: ContextTypes.DEFAULT_TYPE):
    """
    Fan-side queue processor.
    Handles:
      - DMs
      - Relay posts
      - Subscription changes
      - Daily / weekly digests
    """
    queue = read_queue()
    new_q = []

    for cmd in queue:
        nyx = cmd.get("nyx_id")
        tg = get_telegram_id(str(nyx))

        if not tg:
            new_q.append(cmd)
            continue

        t = cmd.get("type")

        # --- Direct Messages ---
        if t == "dm":
            text = f"✉️ DM from *{cmd['creator']}*:\n{cmd['message']}"
            await fan_bot.send_message(chat_id=tg, text=text, parse_mode="Markdown")
            print(f"[DM SENT] {tg}: {text}")
            continue

        # --- Relay posts ---
        if t == "relay":
            image_hex = cmd.get("image")
            try:
                if image_hex:
                    image_bytes = bytes.fromhex(image_hex)
                    bio = BytesIO(image_bytes)
                    bio.name = "post.jpg"

                    await fan_bot.send_photo(
                        chat_id=tg,
                        photo=bio,
                        caption=f"🔥 New post from #{cmd['creator']}:\n\n{cmd['title']}"
                    )
                    print(f"[RELAY SENT] to {tg}")
                else:
                    raise ValueError("No image data found.")
            except Exception as e:
                print(f"❌ Failed to send relay photo to {tg}: {e}")
                new_q.append(cmd)
                continue
            continue

        # --- Subscription price changes ---
        if t == "subchg":
            new_q.append(cmd)
            continue

        # --- Digests ---
        if t in ("digest_daily", "digest_weekly"):
            key = "daily" if t == "digest_daily" else "weekly"
            proxy_chat_id = cmd.get("proxy_chat_id")
            pending = [c for c in new_q if c["nyx_id"] == nyx and c["type"] in ("relay", "subchg")]
            if not pending:
                if proxy_chat_id:
                    await context.bot.send_message(
                        chat_id=proxy_chat_id,
                        text=f"ℹ️ No pending alerts for fan #{nyx}. Digest skipped."
                    )
                continue

            last_id = LAST_DIGEST.get(nyx, {}).get(key)
            if last_id:
                try:
                    await fan_bot.delete_message(chat_id=tg, message_id=last_id)
                except BadRequest:
                    pass

            summary = {}
            for c in pending:
                grp = summary.setdefault(c["creator"], {"posts": 0, "prices": 0})
                if c["type"] == "relay":
                    grp["posts"] += 1
                else:
                    grp["prices"] += 1

            lines = [("🔔 Today’s updates:" if key == "daily" else "🔔 This week’s updates:"), ""]
            for creator, cnts in summary.items():
                parts = []
                if cnts["posts"]:
                    url = f"https://t.me/{FAN_BOT_USERNAME}?start=filter_relay_{creator}"
                    parts.append(f"[{cnts['posts']} new post{'s' if cnts['posts'] > 1 else ''}]({url})")
                if cnts["prices"]:
                    url = f"https://t.me/{FAN_BOT_USERNAME}?start=filter_subchg_{creator}"
                    parts.append(f"[{cnts['prices']} price change{'s' if cnts['prices'] > 1 else ''}]({url})")
                lines.append(f"#{creator}: " + " | ".join(parts))

            msg = await fan_bot.send_message(
                chat_id=tg,
                text="\n".join(lines),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("View All", callback_data="show_alerts")],
                    [InlineKeyboardButton("Settings", callback_data="show_settings")]
                ])
            )
            LAST_DIGEST.setdefault(nyx, {})[key] = msg.message_id
            continue

        # Default: keep unrecognized jobs
        new_q.append(cmd)

    write_queue(new_q)
    print(f"[NyxFan] [processor] done. remaining in queue: {len(new_q)}")
