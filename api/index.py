# NyxFan/api/index.py
"""
NyxFan entrypoint.

Wires together:
- utils.env        → builds `app`
- utils.errors     → global error handler
- handlers.*       → /start and UI callbacks
- jobs.refresh     → background job to process dash refresh pings (ONLY)
"""

# --- Import path bootstrap: ensure the directory that CONTAINS 'api/' is on sys.path
from pathlib import Path
import sys as _sys
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[1]  # the directory that contains the 'api' package
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))
# --- end bootstrap

from api.utils.env import app
from api.utils.errors import on_error
from api.handlers import register_handlers
from api.jobs.refresh import process_fan_queue
from api.jobs.processor_fan import process_fan_jobs

# Error handler
app.add_error_handler(on_error)

# Register all bot handlers (commands + callbacks)
register_handlers(app)

# Fan-side background consumer (only dash_refresh edits)
print("[NyxFan] scheduling fan dash_refresh worker…")
app.job_queue.run_repeating(
    process_fan_queue,
    interval=3.0,
    first=2.0,
    name="fan_dash_refresh",
    job_kwargs={
        "max_instances": 1,
        "coalesce": True,
        "misfire_grace_time": 60,
    },
)
print("[NyxFan] fan dash_refresh worker scheduled.")

print("[NyxFan] scheduling fan consumer…")
app.job_queue.run_repeating(
    process_fan_jobs,
    interval=3.5,
    first=1.0,
    name="fan_consumer",
    job_kwargs={"max_instances": 1, "coalesce": True, "misfire_grace_time": 60},
)
print("[NyxFan] fan consumer scheduled.")

if __name__ == "__main__":
    print("🤖  NyxFan is live. (polling)")
    app.run_polling()