"""
routes/progress.py — Polling-based progress endpoint.

SSE (Server-Sent Events) kills gunicorn sync workers because they hold
the connection open.  Instead, the frontend polls /progress/status every
600ms — each request is instant and stateless.
"""
from flask import Blueprint, jsonify, session

progress_bp = Blueprint("progress", __name__)

# In-memory store: username → {"pct": 0-100, "msg": "", "done": False}
_jobs: dict[str, dict] = {}


def update_progress(session_id: str, pct: int, msg: str = "", done: bool = False):
    """Called from import services to report progress."""
    _jobs[session_id] = {"pct": int(pct), "msg": msg, "done": bool(done)}


def get_session_id() -> str:
    return session.get("username", session.get("_id", "anon"))


@progress_bp.route("/progress/status")
def progress_status():
    """Instant poll — returns current job state, never blocks."""
    sid = get_session_id()
    job = _jobs.get(sid, {"pct": 0, "msg": "", "done": False})
    if job.get("done"):
        _jobs.pop(sid, None)
    return jsonify(job)
