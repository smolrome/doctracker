"""
routes/admin.py — Admin-only routes: user management, activity log, invites.
"""
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services.auth import (
    create_user, delete_user, get_all_users, set_user_active,
    update_user_password, update_user, approve_user, get_pending_clients,
)
from services.email import (
    generate_invite_token, get_all_tokens, send_invite_email,
)
from services.misc import audit_log, get_activity_logs
from services.documents import load_docs
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


@admin_bp.route("/staff-document-stats")
@admin_required
def staff_document_stats():
    """Show document counts per staff member - for admin to track productivity."""
    try:
        audit_log("staff_doc_stats_viewed", "Admin accessed staff document statistics",
                  username=session.get("username","admin"), ip=get_client_ip())
    except Exception:
        pass
    
    # Get all users with staff role
    all_users = get_all_users()
    staff_users = [u for u in all_users if u.get("role") in ("staff", "admin") and u.get("username") != ADMIN_USERNAME]
    
    # Load all documents
    docs = load_docs()
    
    # Calculate stats per staff
    staff_stats = {}
    for staff in staff_users:
        username = staff.get("username")
        full_name = staff.get("full_name") or username
        
        # Count documents where this staff is the original logger or current holder
        staff_docs = [
            d for d in docs
            if d.get("original_logged_by") == username 
            or d.get("logged_by") == username
        ]
        
        # Count by status
        status_counts = {}
        for d in staff_docs:
            status = d.get("status", "Unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        staff_stats[username] = {
            "full_name": full_name,
            "office": staff.get("office", ""),
            "total": len(staff_docs),
            "status_counts": status_counts
        }
    
    # Find documents with no staff assigned (not logged_by any staff and not submitted_by any client)
    unassigned_docs = [
        d for d in docs
        if not d.get("logged_by") and not d.get("original_logged_by") and not d.get("submitted_by")
    ]
    
    # Client-submitted documents (for reference)
    client_docs = [d for d in docs if d.get("submitted_by")]
    
    return render_template("staff_document_stats.html",
                           staff_stats=staff_stats,
                           unassigned_count=len(unassigned_docs),
                           unassigned_docs=unassigned_docs[:50],  # Show first 50
                           client_count=len(client_docs),
                           total_docs=len(docs),
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
    batch_results = None
    try:
        if request.method == "POST":
            mode = request.form.get("mode", "single")
            base = _base_url(request.host_url.rstrip("/"))

            if mode == "batch":
                # ── Batch invite ──────────────────────────────────────────
                raw    = request.form.get("batch_emails", "")
                emails = [e.strip() for e in raw.replace(",", "\n").split("\n") if e.strip()]
                # Deduplicate while preserving order
                seen, emails = set(), [e for e in emails if not (e in seen or seen.add(e))]

                if not emails:
                    result = {"ok": False, "msg": "No valid email addresses found."}
                else:
                    batch_results = []
                    for email in emails:
                        if MAIL_ENABLED:
                            ok, token_or_err = send_invite_email(email, "", base)
                            if ok:
                                link = f"{base}/register?token={token_or_err}"
                                batch_results.append({"email": email, "ok": True,
                                                      "link": link, "msg": "Sent"})
                            else:
                                token = generate_invite_token(email, "")
                                link  = f"{base}/register?token={token}"
                                batch_results.append({"email": email, "ok": False,
                                                      "link": link,
                                                      "msg": "Email failed — link generated"})
                        else:
                            token = generate_invite_token(email, "")
                            link  = f"{base}/register?token={token}"
                            batch_results.append({"email": email, "ok": True,
                                                  "link": link, "msg": "Link generated"})

                    ok_count = sum(1 for r in batch_results if r["ok"])
                    audit_log("batch_invites_sent",
                              f"total={len(batch_results)} ok={ok_count}",
                              username=session.get("username", "admin"),
                              ip=get_client_ip())

            else:
                # ── Single invite ─────────────────────────────────────────
                to_email = request.form.get("email", "").strip()
                to_name  = request.form.get("name", "").strip()
                if not to_email:
                    result = {"ok": False, "msg": "Email address is required."}
                elif MAIL_ENABLED:
                    ok, token_or_err = send_invite_email(to_email, to_name, base)
                    if ok:
                        generated_link = f"{base}/register?token={token_or_err}"
                        result = {"ok": True, "msg": f"Invite sent to {to_email}!"}
                    else:
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
                               batch_results=batch_results,
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


@admin_bp.route("/change-password/<username>", methods=["POST"])
@admin_required
def change_password_route(username):
    if username == ADMIN_USERNAME and session.get("username") != ADMIN_USERNAME:
        flash("Only the main admin can change the admin password.", "error")
        return redirect(url_for("admin.manage_users"))
    new_password = request.form.get("new_password", "").strip()
    confirm      = request.form.get("confirm_password", "").strip()
    if not new_password:
        flash("New password is required.", "error")
        return redirect(url_for("admin.manage_users"))
    if new_password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("admin.manage_users"))
    ok, err = update_user_password(username, new_password)
    if ok:
        audit_log("password_changed",
                  f"admin changed password for user={username}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        flash(f"✅ Password for '{username}' updated successfully.", "success")
    else:
        flash(f"Failed to update password: {err}", "error")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/edit-user/<username>", methods=["POST"])
@admin_required
def edit_user_route(username):
    """Edit user details: full_name, role, and office."""
    from services.auth import update_user
    
    full_name = request.form.get("full_name", "").strip()
    role = request.form.get("role", "").strip()
    office = request.form.get("office", "").strip()
    
    # Get the original user data for audit
    from services.auth import get_all_users
    all_users = get_all_users()
    original_user = next((u for u in all_users if u.get("username") == username), None)
    
    ok, err = update_user(username, full_name=full_name if full_name else None, 
                          role=role if role else None, 
                          office=office if office else None)
    
    if ok:
        # Create audit log details
        changes = []
        if original_user:
            if original_user.get('full_name') != full_name:
                changes.append(f"name: {original_user.get('full_name')} -> {full_name}")
            if original_user.get('role') != role:
                changes.append(f"role: {original_user.get('role')} -> {role}")
            if original_user.get('office') != office:
                changes.append(f"office: {original_user.get('office')} -> {office}")
        
        audit_log("user_edited",
                  f"admin edited user={username}: {'; '.join(changes) if changes else 'no changes'}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        flash(f"✅ User '{username}' updated successfully.", "success")
    else:
        flash(f"Failed to update user: {err}", "error")
    
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