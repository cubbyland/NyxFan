# api/jobs/handlers/fan_unlock_register.py

from __future__ import annotations

from typing import List, Dict, Any
from pathlib import Path
import json

# Minimal store in shared/unlock_index.json so dashboard + later delivery can use it
try:
    from api.utils.helpers import PROJECT_ROOT  # if present in your utils.helpers
    SHARED_DIR = Path(PROJECT_ROOT) / "shared"
except Exception:
    # Fallback: walk up from this file to the project root, then /shared
    SHARED_DIR = Path(__file__).resolve().parents[4] / "shared"

UNLOCK_PATH = SHARED_DIR / "unlock_index.json"


def _read_unlock() -> Dict[str, Any]:
    try:
        if UNLOCK_PATH.exists():
            return json.loads(UNLOCK_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_unlock(d: Dict[str, Any]) -> None:
    UNLOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNLOCK_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


async def handle_fan_unlock_register(queue: List[dict], new_q: List[dict], cmd: Dict[str, Any]) -> List[dict]:
    """
    FanBot-side register:
      - Persist unlock metadata/items into shared/unlock_index.json keyed by content_id.
      - No sending here; delivery happens via fan_unlock_deliver.
    """
    out: List[dict] = []

    nyx = cmd.get("nyx_id")
    cid = cmd.get("content_id")
    if not nyx or not cid:
        return out

    idx = _read_unlock()
    ent: Dict[str, Any] = idx.get(cid, {})

    # Persist metadata for dashboard + later delivery
    ent["nyx_id"] = str(nyx)
    if isinstance(cmd.get("creator"), str):
        ent["creator"] = cmd["creator"]
    if isinstance(cmd.get("title"), str):
        ent["title"] = cmd["title"]

    # Optional linkage to the teaser message (if one was sent)
    if cmd.get("teaser_msg_chat_id") is not None and cmd.get("teaser_msg_id") is not None:
        ent["teaser_msg_chat_id"] = cmd["teaser_msg_chat_id"]
        ent["teaser_msg_id"] = cmd["teaser_msg_id"]

    # Prefer pre-mirrored items; otherwise cache raw content for later
    if isinstance(cmd.get("items"), list) and cmd["items"]:
        ent["items"] = cmd["items"]
        ent.pop("content", None)
    elif "content" in cmd:
        ent["content"] = cmd["content"]

    idx[cid] = ent
    _write_unlock(idx)
    return out
