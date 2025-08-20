# NyxFan/api/utils/io.py

import json
from pathlib import Path

# Resolve the path to the repo root (which contains `shared/`)
# This file lives at: <NyxFan>/api/utils/io.py
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parents[2]          # -> <NyxFan>
REPO_ROOT    = PROJECT_ROOT.parents[0]   # -> repo root that contains `shared/`

# Path to the shared queue file used by both bots
QUEUE_PATH = REPO_ROOT / "shared" / "command_queue.json"


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
