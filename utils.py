"""
utils.py — Shared decorators and request helpers used across all route blueprints.
"""
import os
from functools import wraps

from flask import flash, redirect, request, session, url_for


# ── Session helpers ───────────────────────────────────────────────────────────

def is_logged_in() -> bool:
    return session.get("logged_in") is True


def get_client_ip() -> str:
    if os.environ.get('TRUSTED_PROXY'):
        forwarded_for = request.headers.get('X-Forwarded-For', '')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


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


def staff_required(f):
    """Admit staff and admin only; reject clients and guests.

    Stays session-based on purpose: the env-var admin has no ``users`` row,
    so a DB role lookup would wrongly reject it. Reading ``session["role"]``
    keeps that account passing, exactly like ``admin_required``.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_logged_in():
            flash("Please log in.", "error")
            return redirect(url_for("auth.login", next=request.url))
        if session.get("role") not in ("staff", "admin"):
            flash("Staff access required.", "error")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated
