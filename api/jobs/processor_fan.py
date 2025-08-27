# NyxFan/api/jobs/processor_fan.py
from __future__ import annotations
from typing import Dict, Any, List

from api.utils.io import read_queue, write_queue
from api.jobs.handlers.fan_relay import handle_fan_relay
from api.jobs.handlers.fan_unlock_register import handle_fan_unlock_register
from api.jobs.handlers.fan_unlock_deliver import handle_fan_unlock_deliver

# new file you’ll add next:
from api.jobs.handlers.fan_dm import handle_fan_dm

async def process_fan_jobs(context) -> None:
    """
    FanBot queue worker:
      - Consume fan_* jobs (and keep muted ones for Dashboard ‘View All’)
      - Leave everything else alone (Proxy or refresh worker will handle)
    """
    q = read_queue()
    new_q: List[Dict[str, Any]] = []

    for cmd in q:
        if not isinstance(cmd, dict):
            new_q.append(cmd); continue
        t = (cmd.get("type") or "").lower()

        # Only handle fan-side jobs here
        if t == "fan_relay":
            more = await handle_fan_relay(q, new_q, cmd) or []
            new_q.extend(more)
            # If handler emitted a dash_refresh, keep original so it appears on the dashboard
            if any((isinstance(x, dict) and x.get("type") == "dash_refresh") for x in more):
                new_q.append(cmd)   # muted path → pending
            continue

        if t == "fan_unlock_register":
            new_q.extend(await handle_fan_unlock_register(q, new_q, cmd) or [])
            # do NOT keep original; registration is persisted
            continue

        if t == "fan_unlock_deliver":
            new_q.extend(await handle_fan_unlock_deliver(q, new_q, cmd) or [])
            # delivered → drop original
            continue

        if t == "fan_dm":
            more = await handle_fan_dm(q, new_q, cmd) or []
            new_q.extend(more)
            if any((isinstance(x, dict) and x.get("type") == "dash_refresh") for x in more):
                new_q.append(cmd)   # muted path → pending
            continue

        # Everything else: passthrough
        new_q.append(cmd)

    write_queue(new_q)
