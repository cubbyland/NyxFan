# NyxFan/api/utils/io.py

import json
from pathlib import Path

# Path to the shared queue file
QUEUE_PATH = Path(__file__).resolve().parents[2] / "shared" / "command_queue.json"

def _write_text_atomic(path: Path, text: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)

def read_queue():
    try:
        return json.loads(QUEUE_PATH.read_text())
    except Exception:
        return []

def write_queue(q):
    _write_text_atomic(QUEUE_PATH, json.dumps(q, indent=2))
