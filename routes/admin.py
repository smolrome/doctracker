"""
routes/admin.py — Admin-only routes: user management, activity log, invites.
"""
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services.auth import (
    create_user, delete_user, get_all_users, set_user_active,
)
from services.email import (
    generate_invite_token, get_all_tokens, send_invite_email,
)
from services.misc import audit_log, get_activity_logs
from utils import admin_required, get_client_ip
from config import ADMIN_USERNAME, MAIL_ENABLED, APP_URL

admin_bp = Blueprint("admin", __name__)


def _base_url(fallback: str = "") -> str:
    return (APP_URL or fallback).rstrip("/")


@admin_bp.route("/manage-users")
@admin_required
def manage_users():
    try:
        from services.misc import audit_log
        from utils import get_client_ip
        audit_log("admin_users_viewed", "Admin accessed user management",
                  username=session.get("username","admin"), ip=get_client_ip())
    except Exception:
        pass
    users = get_all_users()
    return render_template("manage_users.html", users=users,
                           admin_username=ADMIN_USERNAME)


@admin_bp.route("/activity-log")
@admin_required
def activity_log():
    try:
        from services.misc import audit_log
        from utils import get_client_ip
        audit_log("audit_log_viewed", "Admin accessed the audit log",
                  username=session.get("username","admin"), ip=get_client_ip())
    except Exception:
        pass
    logs = get_activity_logs()
    return render_template("activity_log.html", logs=logs)


@admin_bp.route("/send-invite", methods=["GET", "POST"])
@admin_required
def send_invite():
    result = None
    generated_link = None
    try:
        if request.method == "POST":
            to_email = request.form.get("email", "").strip()
            to_name  = request.form.get("name", "").strip()
            base     = _base_url(request.host_url.rstrip("/"))
            if not to_email:
                result = {"ok": False, "msg": "Email address is required."}
            elif MAIL_ENABLED:
                ok, token_or_err = send_invite_email(to_email, to_name, base)
                if ok:
                    generated_link = f"{base}/register?token={token_or_err}"
                    result = {"ok": True, "msg": f"Invite sent to {to_email}!"}
                else:
                    # Email failed but generate link anyway for manual sharing
                    token = generate_invite_token(to_email, to_name)
                    generated_link = f"{base}/register?token={token}"
                    result = {"ok": False,
                              "msg": f"Email failed: {token_or_err} — share link below manually."}
            else:
                token = generate_invite_token(to_email, to_name)
                generated_link = f"{base}/register?token={token}"
                result = {"ok": True,
                          "msg": f"Invite link generated for {to_email}. Share it manually.",
                          "manual": True}

        tokens = get_all_tokens()
        return render_template("send_invite.html", result=result,
                               mail_enabled=MAIL_ENABLED,
                               generated_link=generated_link,
                               tokens=tokens,
                               now=datetime.now())
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        flash(f"Error: {e}", "error")
        return redirect(url_for("admin.manage_users"))


@admin_bp.route("/delete-user/<username>", methods=["POST"])
@admin_required
def delete_user_route(username):
    if username == ADMIN_USERNAME:
        flash("Cannot delete the main admin account.", "error")
    elif username == session.get("username"):
        flash("Cannot delete your own account.", "error")
    else:
        delete_user(username)
        audit_log("user_deleted", f"deleted_user={username}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        flash(f"User '{username}' deleted.", "success")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/disable-user/<username>", methods=["POST"])
@admin_required
def disable_user_route(username):
    if username == ADMIN_USERNAME:
        flash("Cannot disable the main admin account.", "error")
    elif username == session.get("username"):
        flash("Cannot disable your own account.", "error")
    else:
        set_user_active(username, False)
        audit_log("user_disabled", f"disabled_user={username}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        flash(f"Account '{username}' has been disabled.", "success")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/enable-user/<username>", methods=["POST"])
@admin_required
def enable_user_route(username):
    set_user_active(username, True)
    audit_log("user_enabled", f"enabled_user={username}",
              username=session.get("username", "admin"),
              ip=get_client_ip())
    flash(f"Account '{username}' has been re-enabled.", "success")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/clear-database", methods=["POST"])
@admin_required
def clear_database():
    """Permanently delete all documents. Admin only. Irreversible."""
    from services.database import USE_DB, get_conn
    import os, json as _json

    username = session.get("username", "admin")
    count = 0

    try:
        if USE_DB:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) AS cnt FROM documents")
                    row = cur.fetchone()
                    count = row["cnt"] if row else 0
                    cur.execute("DELETE FROM documents")
                conn.commit()
        else:
            path = "documents.json"
            if os.path.exists(path):
                with open(path) as f:
                    docs = _json.load(f)
                count = len(docs)
                with open(path, "w") as f:
                    _json.dump([], f)

        audit_log("database_cleared",
                  f"deleted_count={count}",
                  username=username,
                  ip=get_client_ip())
        flash(f"Database cleared — {count} document(s) permanently deleted.", "success")

    except Exception as e:
        flash(f"Clear failed: {e}", "error")

    return redirect(url_for("dashboard.index"))
