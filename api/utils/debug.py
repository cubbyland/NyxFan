# cubbyland-nyxfan/api/utils/debug.py
from __future__ import annotations
from collections import Counter
from typing import Any, Dict, List

from api.utils.io import read_queue

def log_queue(tag: str) -> None:
    """
    Print a compact snapshot of the shared queue from the NyxFan process's POV.
    """
    try:
        q: List[Dict[str, Any]] = read_queue()
        types = Counter()
        for c in q:
            if isinstance(c, dict):
                types[c.get("type") or "<?>"] += 1
            else:
                types["<?>"] += 1
        print(f"[NyxFan] [{tag}] queue_len={len(q)} types={dict(types)}")
    except Exception as e:
        print(f"[NyxFan] [{tag}] queue_snapshot_error={e!r}")
