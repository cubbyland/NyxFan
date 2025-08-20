# NyxFan/api/utils/env.py
from pathlib import Path
import os
import sys
from dotenv import load_dotenv
from telegram.ext import Application

# Ensure both the NyxFan project root (that contains `api/`) AND the
# repository root (that contains `shared/`) are importable.
# env.py lives at: <NyxFan>/api/utils/env.py
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parents[2]          # -> <NyxFan>
REPO_ROOT    = PROJECT_ROOT.parents[0]   # -> repo root that should contain `shared/`

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load .env from <NyxFan>/.env (same as original single-file setup)
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# Read required Fan bot config
BOT_TOKEN    = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")

# Optional URLs with sane defaults (kept even though current dashboard omits them)
INBOX_URL   = os.getenv("INBOX_URL", "https://example.com/inbox")
PROFILE_URL = os.getenv("PROFILE_URL", "https://example.com/profile")

if not BOT_TOKEN or not BOT_USERNAME:
    raise RuntimeError("Missing required .env vars for NyxFan: BOT_TOKEN and BOT_USERNAME")

# Build the Telegram Application (default request; Fan bot is lightweight)
app = Application.builder().token(BOT_TOKEN).build()

__all__ = [
    "app",
    "BOT_TOKEN",
    "BOT_USERNAME",
    "INBOX_URL",
    "PROFILE_URL",
]
