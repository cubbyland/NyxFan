# NyxFan/api/utils/helpers.py

import json
import sys
from pathlib import Path
from dotenv import load_dotenv
from api.utils.env import app
from telegram import Bot

# Make the repository root (that contains `shared/`) importable.
# This file lives at: <NyxFan>/api/utils/helpers.py
ROOT = Path(__file__).resolve().parents[2]      # -> NyxFan/
PROJECT_ROOT = ROOT.parents[0]        

fan_bot: Bot = app.bot           # directory that should contain `shared/`

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load env from <NyxFan>/.env so fan bot can run standalone if needed.
load_dotenv(dotenv_path=ROOT / ".env")

# Shared modules (live at <PROJECT_ROOT>/shared)
from shared.fan_registry import register_user, get_telegram_id  # re-export

# Paths used by NyxFan to read/write the cross-app queue
QUEUE_PATH = PROJECT_ROOT / "shared" / "command_queue.json"

# In-memory state used by the fan bot
ALL_DASH_MSGS: dict[int, list[int]] = {}
USER_DISP: dict[int, str] = {}


def _write_text_atomic(path: Path, text: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def read_queue() -> list:
    try:
        return json.loads(QUEUE_PATH.read_text())
    except Exception:
        return []

def write_queue(q: list) -> None:
    _write_text_atomic(QUEUE_PATH, json.dumps(q, indent=2))

def alert_admin(text: str): 
    print(f"[NyxFan ALERT] {text}")