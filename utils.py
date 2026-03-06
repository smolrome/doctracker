"""
utils.py — Shared decorators and request helpers used across all route blueprints.
"""
from functools import wraps

from flask import flash, redirect, request, session, url_for


# ── Session helpers ───────────────────────────────────────────────────────────

def is_logged_in() -> bool:
    return session.get("logged_in") is True


def get_client_ip() -> str:
    return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.remote_addr
            or "unknown")


# ── Route decorators ──────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_logged_in():
            flash("Please log in to perform that action.", "error")
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_logged_in():
            flash("Please log in.", "error")
            return redirect(url_for("auth.login", next=request.url))
        if session.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated
