"""
routes/progress.py — Server-Sent Events progress streams.

Used by the frontend to show real progress bars instead of spinners.
Each import job stores its progress in a simple in-memory dict keyed
by session id.  Good enough for single-server Railway deployments.
"""
import json
import time
from flask import Blueprint, Response, session

progress_bp = Blueprint("progress", __name__)

# In-memory progress store: session_id → {"pct": 0-100, "msg": "", "done": False}
_jobs: dict[str, dict] = {}


def update_progress(session_id: str, pct: int, msg: str = "", done: bool = False):
    """Called from import services to push progress updates."""
    _jobs[session_id] = {"pct": pct, "msg": msg, "done": done}


def get_session_id() -> str:
    return session.get("_id", session.get("username", "anon"))


@progress_bp.route("/progress/import")
def progress_import():
    """SSE stream for Excel import progress."""
    sid = get_session_id()
    _jobs[sid] = {"pct": 0, "msg": "Starting import...", "done": False}

    def stream():
        last_pct = -1
        # Stream for up to 120 seconds
        for _ in range(1200):
            job = _jobs.get(sid, {"pct": 0, "msg": "", "done": False})
            pct  = job["pct"]
            msg  = job["msg"]
            done = job["done"]

            if pct != last_pct or done:
                last_pct = pct
                yield f"data: {json.dumps({'pct': pct, 'msg': msg, 'done': done})}\n\n"

            if done:
                _jobs.pop(sid, None)
                break

            time.sleep(0.1)

        # Fallback: close stream
        yield f"data: {json.dumps({'pct': 100, 'done': True})}\n\n"

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})
