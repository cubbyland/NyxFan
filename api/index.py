import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.error import BadRequest

# allow shared imports
sys.path.append(str(Path(__file__).resolve().parents[2]))
from shared.fan_registry import register_user, get_telegram_id

# load config
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

BOT_TOKEN    = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
INBOX_URL    = os.getenv("INBOX_URL", "https://example.com/inbox")
PROFILE_URL  = os.getenv("PROFILE_URL", "https://example.com/profile")

if not BOT_TOKEN or not BOT_USERNAME:
    raise RuntimeError("BOT_TOKEN and BOT_USERNAME must be set in .env")

app        = Application.builder().token(BOT_TOKEN).build()
QUEUE_PATH = Path(__file__).resolve().parents[2] / "shared" / "command_queue.json"

ALL_DASH_MSGS: dict[int, list[int]] = {}
USER_DISP:     dict[int, str]       = {}

def read_queue() -> list:
    try:
        return json.loads(QUEUE_PATH.read_text())
    except:
        return []

def write_queue(q: list) -> None:
    QUEUE_PATH.write_text(json.dumps(q, indent=2))

def build_dashboard(tg_id: int) -> tuple[str, InlineKeyboardMarkup]:
    disp   = USER_DISP.get(tg_id, str(tg_id))
    header = f"{disp}’s Dashboard"
    queue  = read_queue()
    summary: dict[str, dict[str, int]] = {}

    for c in queue:
        if c["type"] not in ("relay", "subchg"):
            continue
        if get_telegram_id(str(c["nyx_id"])) != tg_id:
            continue
        grp = summary.setdefault(c["creator"], {"posts": 0, "prices": 0})
        if c["type"] == "relay":
            grp["posts"] += 1
        else:
            grp["prices"] += 1

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
            lines.append(f"#{creator}: " + " | ".join(parts))
        body = "\n".join(lines)
    else:
        body = "🔔 No pending alerts."

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("View All", callback_data="show_alerts"),
            InlineKeyboardButton("Inbox", url=INBOX_URL),
        ],
        [
            InlineKeyboardButton("Profile", url=PROFILE_URL),
            InlineKeyboardButton("Settings", callback_data="show_settings"),
        ],
    ])
    return f"{header}\n\n{body}", kb

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg   = update.effective_user.id
    disp = update.effective_user.username or update.effective_user.full_name or str(tg)
    register_user(tg, disp)
    USER_DISP[tg] = disp

    # notify proxy bot about the join
    queue = read_queue()
    queue.append({
        "type": "joined",
        "nyx_id": str(tg),
        "display": disp
    })
    write_queue(queue)

    # deep-link filters...
    if context.args:
        arg = context.args[0]
        queue = read_queue()
        kept, to_send = [], []
        for c in queue:
            if (
                get_telegram_id(str(c["nyx_id"])) == tg
                and c["type"] in ("relay","subchg")
                and arg.split("_",2)[1] == c["type"]
                and c["creator"] == arg.split("_",2)[2]
            ):
                to_send.append(c)
            else:
                kept.append(c)
        write_queue(kept)
        for c in to_send:
            text = (
                f"🆕 New post from *{c['creator']}*:\n{c['title']}\n{c['url']}"
                if c["type"] == "relay"
                else f"💲 Price update by *{c['creator']}*:\n{c['old_price']} → {c['new_price']}"
            )
            await update.message.reply_text(text, parse_mode="Markdown")

    # send fresh dashboard first
    text, kb = build_dashboard(tg)
    msg = await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    new_ids = [msg.message_id]

    # then delete old dashboards
    for mid in ALL_DASH_MSGS.get(tg, []):
        try:
            await context.bot.delete_message(chat_id=tg, message_id=mid)
        except BadRequest:
            pass

    ALL_DASH_MSGS[tg] = new_ids

async def process_proxy_commands(context: ContextTypes.DEFAULT_TYPE):
    queue = read_queue()
    new_q = []

    for cmd in queue:
        nyx = cmd.get("nyx_id")
        tg = get_telegram_id(str(nyx))

        if not tg:
            new_q.append(cmd)
            continue

        t = cmd.get("type")

        if t == "dm":
            text = f"✉️ DM from *{cmd['creator']}*:\n{cmd['message']}"
            await fan_bot.send_message(chat_id=tg, text=text, parse_mode="Markdown")
            print(f"[DM SENT] {tg}: {text}")
            continue

        if t == "relay":
            image_hex = cmd.get("image")
            try:
                if image_hex:
                    from io import BytesIO
                    image_bytes = bytes.fromhex(image_hex)
                    image_file = BytesIO(image_bytes)
                    image_file.name = "post.jpg"

                    await fan_bot.send_photo(
                        chat_id=tg,
                        photo=image_file,
                        caption=f"🔥 New post from {cmd['creator']}:\n\n{cmd['title']}"
                    )
                    print(f"[RELAY SENT] to {tg}")
                else:
                    raise ValueError("No image data found.")
            except Exception as e:
                print(f"❌ Failed to send relay photo to {tg}: {e}")
                new_q.append(cmd)
                continue

            continue

        if t == "subchg":
            new_q.append(cmd)
            continue

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

        new_q.append(cmd)

    write_queue(new_q)
    print(f"[QUEUE FLUSHED] Remaining entries: {len(new_q)}")

async def show_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    tg   = update.effective_user.id
    msg  = update.callback_query.message

    queue  = read_queue()
    alerts = [
        c for c in queue
        if c["type"] in ("relay", "subchg")
        and get_telegram_id(str(c["nyx_id"])) == tg
    ]

    if not alerts:
        await msg.reply_text("🔔 No pending alerts.")
        return

    for c in alerts:
        out = (
            f"🆕 New post from *{c['creator']}*:\n{c['title']}\n{c['url']}"
            if c["type"] == "relay"
            else f"💲 Price update by *{c['creator']}*:\n{c['old_price']} → {c['new_price']}"
        )
        await msg.reply_text(out, parse_mode="Markdown")

    remaining = [
        c for c in queue
        if not (
            c["type"] in ("relay", "subchg")
            and get_telegram_id(str(c["nyx_id"])) == tg
        )
    ]
    write_queue(remaining)

    try:
        await msg.delete()
    except:
        pass

    new_text, new_kb = build_dashboard(tg)
    new_msg = await context.bot.send_message(
        chat_id=tg,
        text=new_text,
        parse_mode="Markdown",
        reply_markup=new_kb
    )
    ALL_DASH_MSGS[tg] = [new_msg.message_id]

async def show_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    tg  = update.effective_user.id
    msg = update.callback_query.message

    queue  = read_queue()
    alerts = [
        c for c in queue
        if c["type"] in ("relay", "subchg")
        and get_telegram_id(str(c["nyx_id"])) == tg
    ]

    if not alerts:
        await msg.reply_text("🔔 No pending alerts.")
        return

    for c in alerts:
        out = (
            f"🆕 New post from *{c['creator']}*:\n{c['title']}\n{c['url']}"
            if c["type"] == "relay"
            else f"💲 Price update by *{c['creator']}*:\n{c['old_price']} → {c['new_price']}"
        )
        await msg.reply_text(out, parse_mode="Markdown")

    try:
        await msg.delete()
    except:
        pass

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("⚙️ Settings are not yet configurable.")

# handlers & schedule
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(show_alerts, pattern="^show_alerts$"))
app.add_handler(CallbackQueryHandler(show_digest, pattern="^view_digest$"))
app.add_handler(CallbackQueryHandler(show_settings, pattern="^show_settings$"))

print("🤖 NyxFanBot is live.")
app.run_polling()
