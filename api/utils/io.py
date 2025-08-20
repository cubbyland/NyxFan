# cubbyland-nyxfan/api/utils/io.py

import json
from pathlib import Path

# Resolve the path to the repo root (which contains `shared/`)
# This file lives at: <NyxFan>/api/utils/io.py
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parents[2]          # -> <NyxFan>
REPO_ROOT    = PROJECT_ROOT.parents[0]   # -> repo root that contains `shared/`

# Paths shared by both bots
QUEUE_PATH = REPO_ROOT / "shared" / "command_queue.json"
NOTIF_PATH = REPO_ROOT / "shared" / "fan_notifications.json"  # per-fan, per-creator prefs


def _write_text_atomic(path: Path, text: str):
    # Make sure the directory exists before writing
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def read_queue():
    try:
        return json.loads(QUEUE_PATH.read_text())
    except Exception:
        # If file doesn't exist or is unreadable, treat as empty queue
        return []


def write_queue(q):
    _write_text_atomic(QUEUE_PATH, json.dumps(q, indent=2))


# --- per-fan, per-creator notification prefs ---
def read_notifs() -> dict:
    """
    Returns a dict mapping:
      {
        "<tg_id>": {
          "<creator>": { "mode": "immediate|daily|weekly", "muted": bool }
        }
      }
    Any non-dict on disk (e.g., legacy []) is treated as {}.
    """
    try:
        data = json.loads(NOTIF_PATH.read_text())
        if isinstance(data, dict):
            return data
        # auto-heal: legacy content like [] → {}
        return {}
    except Exception:
        return {}


def write_notifs(data: dict) -> None:
    if not isinstance(data, dict):
        data = {}
    _write_text_atomic(NOTIF_PATH, json.dumps(data, indent=2))
