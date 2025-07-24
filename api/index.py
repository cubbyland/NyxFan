import os, sys, json
from pathlib import Path
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# allow imports from shared/
sys.path.append(str(Path(__file__).resolve().parents[2]))
from shared.fan_registry import register_user, get_telegram_id
from shared.presets import get_template

# load environment
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

app = Application.builder().token(BOT_TOKEN).build()

# register commands in Telegram menu
app.bot.set_my_commands([
    BotCommand("start",         "Onboard & toggle notifications"),
    BotCommand("menu",          "Show all commands"),
    BotCommand("subscribe",     "Subscribe to a creator"),
    BotCommand("unsubscribe",   "Unsubscribe from a creator"),
    BotCommand("subscriptions", "List your subscriptions"),
    BotCommand("silence",       "Pause all alerts"),
    BotCommand("unsilence",     "Resume alerts & show digest"),
])

# shared queue path
QUEUE_PATH = Path(__file__).resolve().parents[2] / "shared" / "command_queue.json"

# in-memory stores
USER_PREFS: dict[int, dict] = {}
MISSED_STORE: dict[int, list] = {}
PENDING_REPLY: dict[int, tuple[str,str]] = {}

def read_queue():
    try:
        return json.loads(QUEUE_PATH.read_text())
    except:
        return []

def write_queue(q):
    QUEUE_PATH.write_text(json.dumps(q, indent=2))


async def process_relay_commands(context: ContextTypes.DEFAULT_TYPE):
    queue = read_queue()
    new_q = []
    for cmd in queue:
        t = cmd.get("type")

        # relay new post
        if t == "relay":
            nyx_id   = str(cmd["nyx_id"])
            tg       = get_telegram_id(nyx_id)
            prefs    = USER_PREFS.setdefault(tg, {"silenced": False, "subscriptions": set()})
            if not tg or prefs["silenced"] or cmd["creator"] not in prefs["subscriptions"]:
                new_q.append(cmd)
                continue

            text_img = get_template(cmd["title"], cmd["creator"], cmd["title"], cmd["url"], cmd.get("image_url"))
            text, img = text_img if text_img else (f"🆕 New from *{cmd['creator']}*: {cmd['url']}", None)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("👉 View Post", url=cmd["url"])]])
            if img:
                await context.bot.send_photo(chat_id=tg, photo=img, caption=text, reply_markup=kb, parse_mode="Markdown")
            else:
                await context.bot.send_message(chat_id=tg, text=text, reply_markup=kb, parse_mode="Markdown")

        # subscription-change
        elif t == "subchg":
            creator = cmd["creator"]
            tg_list = [tg for tg,p in USER_PREFS.items() if creator in p.get("subscriptions", set())]
            for tg in tg_list:
                prefs = USER_PREFS[tg]
                if prefs["silenced"]:
                    MISSED_STORE.setdefault(tg, []).append(cmd)
                else:
                    text = (
                        f"🔔 *{creator}* changed price:\n"
                        f"• Old: `{cmd['old_price']}` → New: `{cmd['new_price']}`"
                    )
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ View", url=f"https://example.com/{creator}")]])
                    await context.bot.send_message(chat_id=tg, text=text, reply_markup=kb, parse_mode="Markdown")
        # DM alert
        elif t == "dm":
            nyx_id = str(cmd["nyx_id"])
            tg     = get_telegram_id(nyx_id)
            prefs  = USER_PREFS.setdefault(tg, {"silenced": False, "subscriptions": set()})
            if not tg or prefs["silenced"]:
                new_q.append(cmd)
                continue

            text = f"✉️ *{cmd['creator']}* — “{cmd['message']}”"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔕 Mute", callback_data=f"toggle_mute|{nyx_id}|{cmd['creator']}"),
                InlineKeyboardButton("↩️ Reply", callback_data=f"reply_dm|{nyx_id}|{cmd['creator']}")
            ]])
            await context.bot.send_message(chat_id=tg, text=text, reply_markup=kb, parse_mode="Markdown")

        else:
            new_q.append(cmd)

    write_queue(new_q)


# ─── Bot Commands ────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user.id
    display = update.effective_user.username or update.effective_user.full_name or "Unknown"
    nyx_id = register_user(tg, display)
    USER_PREFS.setdefault(tg, {"silenced": False, "subscriptions": set()})
    await update.message.reply_text(f"👋 You are NYX ID #{nyx_id}. Type /menu for commands.")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⭐ *Commands* ⭐\n"
        "/start         – onboard\n"
        "/subscribe     – subscribe to a creator\n"
        "/unsubscribe   – unsubscribe from a creator\n"
        "/subscriptions – list your subscriptions\n"
        "/silence       – pause alerts\n"
        "/unsilence     – resume alerts & show digest",
        parse_mode="Markdown"
    )

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user.id
    creator = " ".join(context.args).strip()
    prefs = USER_PREFS.setdefault(tg, {"silenced": False, "subscriptions": set()})
    prefs["subscriptions"].add(creator)
    await update.message.reply_text(f"✅ Subscribed to *{creator}*", parse_mode="Markdown")

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user.id
    creator = " ".join(context.args).strip()
    prefs = USER_PREFS.setdefault(tg, {"silenced": False, "subscriptions": set()})
    prefs["subscriptions"].discard(creator)
    await update.message.reply_text(f"🚫 Unsubscribed from *{creator}*", parse_mode="Markdown")

async def list_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user.id
    subs = USER_PREFS.setdefault(tg, {"silenced": False, "subscriptions": set()})["subscriptions"]
    if not subs:
        await update.message.reply_text("You have no subscriptions.")
    else:
        await update.message.reply_text(
            "⭐ *Your subscriptions:*  \n" + "\n".join(f"• {c}" for c in sorted(subs)),
            parse_mode="Markdown"
        )

async def silence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user.id
    USER_PREFS.setdefault(tg, {"silenced": False, "subscriptions": set()})["silenced"] = True
    await update.message.reply_text("🔇 Notifications paused. Use /unsilence to catch up.")

async def unsilence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user.id
    prefs = USER_PREFS.setdefault(tg, {"silenced": False, "subscriptions": set()})
    prefs["silenced"] = False

    missed = MISSED_STORE.pop(tg, [])
    if missed:
        lines = ["📬 *Missed Notifications*"]
        posts = [m for m in missed if m["type"] == "relay"]
        subs  = [m for m in missed if m["type"] == "subchg"]
        dms   = [m for m in missed if m["type"] == "dm"]

        if posts:
            lines.append("\n*Posts:*")
            for m in posts:
                lines.append(f"• New post from *{m['creator']}* [View]")
        if subs:
            lines.append("\n*Price Changes:*")
            for m in subs:
                lines.append(f"• *{m['creator']}*: `{m['old_price']}` → `{m['new_price']}` [View]")
        if dms:
            lines.append("\n*DMs:*")
            for m in dms:
                lines.append(f"• New DM from *{m['creator']}* [View]")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    await update.message.reply_text("🔔 Notifications resumed.")

# register handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(CommandHandler("subscribe", subscribe))
app.add_handler(CommandHandler("unsubscribe", unsubscribe))
app.add_handler(CommandHandler("subscriptions", list_subscriptions))
app.add_handler(CommandHandler("silence", silence))
app.add_handler(CommandHandler("unsilence", unsilence))
app.add_handler(CallbackQueryHandler(lambda *args, **kwargs: None))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: None))

# schedule processing
jobq = app.job_queue
jobq.run_repeating(process_relay_commands, interval=2.0, first=2.0)

print("🤖 NyxFanBot is live.")
app.run_polling()
