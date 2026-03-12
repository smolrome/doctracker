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
from services.dropdown_options import (
    get_all_dropdown_configs, update_dropdown_options, reset_to_default,
    MANAGEABLE_FIELDS
)
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
    from services.misc import load_saved_offices
    users = get_all_users()
    offices = load_saved_offices()
    return render_template("manage_users.html", users=users,
                           admin_username=ADMIN_USERNAME, offices=offices)


@admin_bp.route("/office-staff")
@admin_required
def office_staff():
    """Show list of offices with staff count."""
    try:
        from services.misc import audit_log
        from utils import get_client_ip
        audit_log("office_staff_viewed", "Admin accessed office staff list",
                  username=session.get("username","admin"), ip=get_client_ip())
    except Exception:
        pass
    
    from services.misc import load_saved_offices
    from services.database import USE_DB, get_conn
    from services.auth import get_all_users
    
    offices = load_saved_offices()
    all_users = get_all_users()
    # If no saved offices, auto-build from users' office field
    if not offices:
        seen = set()
        for u in all_users:
            o = (u.get('office') or '').strip()
            if o and o not in seen:
                seen.add(o)
                offices.append({'office_name': o, 'office_slug': o, 'created_by': '', 'primary_recipient': ''})
    staff_members = [u for u in all_users if u.get("role") in ("staff", "admin")]
    
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT office, COUNT(*) as count FROM users 
                           WHERE role IN ('staff', 'admin') AND office != '' 
                           GROUP BY office"""
                    )
                    staff_counts = {row['office']: row['count'] for row in cur.fetchall()}
        except Exception:
            staff_counts = {}
    else:
        staff_counts = {}
        for user in all_users:
            if user.get('role') in ('staff', 'admin') and user.get('office'):
                office = user['office']
                staff_counts[office] = staff_counts.get(office, 0) + 1
    
    # DEBUG: Print staff matching info
    print(f"DEBUG: offices = {[o.get('office_name') for o in offices]}")
    print(f"DEBUG: all_users = {[(u.get('username'), u.get('office'), u.get('role')) for u in all_users]}")
    
    office_staff_counts = []
    
    for office in offices:
        office_slug = office.get('office_slug', '')
        office_name = office.get('office_name', '')
        staff_count = staff_counts.get(office_name, 0) + staff_counts.get(office_slug, 0)
        
        # Match staff by office - case insensitive, flexible matching
        office_name_lower = office_name.strip().lower() if office_name else ''
        
        office_staff_list = []
        for u in all_users:
            if u.get("role") in ("staff", "admin"):
                user_office = u.get("office", "") or ""
                user_office_lower = user_office.strip().lower()
                
                # Match if office name is same or if user's office contains the office name
                if user_office_lower == office_name_lower or office_name_lower in user_office_lower:
                    office_staff_list.append(u)
        
        print(f"DEBUG: office '{office_name}' matched staff: {[(u.get('username'), u.get('office')) for u in office_staff_list]}")
        
        office_staff_counts.append({
            'office_name': office_name,
            'office_slug': office_slug,
            'staff_count': staff_count,
            'created_by': office.get('created_by', ''),
            'primary_recipient': office.get('primary_recipient', ''),
            'staff': office_staff_list
        })
    
    for office_key, count in staff_counts.items():
        if not any(o['office_name'] == office_key or o['office_slug'] == office_key for o in office_staff_counts):
            office_staff_counts.append({
                'office_name': office_key,
                'office_slug': office_key,
                'staff_count': count,
                'created_by': '',
                'primary_recipient': '',
                'staff': []
            })
    
    office_staff_json = {}
    for o in office_staff_counts:
        staff_list = [
            {'username': s['username'], 'full_name': s.get('full_name') or s['username']}
            for s in (o.get('staff') or [])
        ]
        office_staff_json[o['office_slug']] = staff_list
        office_staff_json[o['office_name']] = staff_list

    return render_template("office_staff.html",
                           office_staff=office_staff_counts,
                           staff_members=staff_members,
                           office_staff_json=office_staff_json)

@admin_bp.route("/delete-office/<office_slug>", methods=["POST"])
@admin_required
def delete_office(office_slug):
    """Delete an office from saved_offices."""
    from services.misc import delete_saved_office, audit_log
    from utils import get_client_ip
    
    # Decode the office_slug (handle URL encoding)
    from urllib.parse import unquote
    office_slug_decoded = unquote(office_slug)
    
    delete_saved_office(office_slug_decoded)
    audit_log("office_deleted", f"deleted_office={office_slug_decoded}",
              username=session.get("username", "admin"), ip=get_client_ip())
    flash(f"Office '{office_slug_decoded}' has been deleted.", "success")
    return redirect(url_for("admin.office_staff"))


@admin_bp.route("/update-office-recipient", methods=["POST"])
@admin_required
def update_office_recipient():
    """Update the primary recipient for an office."""
    from services.misc import update_office_primary_recipient, audit_log
    from utils import get_client_ip
    from urllib.parse import unquote
    
    office_slug = request.form.get("office_slug", "").strip()
    office_slug = unquote(office_slug)
    primary_recipient = request.form.get("primary_recipient", "").strip()
    
    update_office_primary_recipient(office_slug, primary_recipient)
    
    if primary_recipient:
        audit_log("office_recipient_updated", f"office={office_slug} recipient={primary_recipient}",
                  username=session.get("username", "admin"), ip=get_client_ip())
        flash(f"Primary recipient updated for office.", "success")
    else:
        audit_log("office_recipient_cleared", f"office={office_slug}",
                  username=session.get("username", "admin"), ip=get_client_ip())
        flash(f"Primary recipient cleared for office.", "success")
    
    return redirect(url_for("admin.office_staff"))


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
def change_user_password(username):
    """Admin can change any user's password."""
    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()
    
    if username == ADMIN_USERNAME:
        flash("Cannot change the main admin password through this interface.", "error")
        return redirect(url_for("admin.manage_users"))
    
    if not new_password:
        flash("Password cannot be empty.", "error")
        return redirect(url_for("admin.manage_users"))
    
    if new_password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("admin.manage_users"))
    
    if len(new_password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("admin.manage_users"))
    
    success, error = update_user_password(username, new_password)
    if success:
        audit_log("user_password_changed", f"password_changed_for={username}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        flash(f"Password for '{username}' has been changed.", "success")
    else:
        flash(f"Error: {error}", "error")
    
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/edit-user/<username>", methods=["GET", "POST"])
@admin_required
def edit_user(username):
    """Admin can edit user details: full_name, role, and office."""
    from services.misc import load_saved_offices
    
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "").strip()
        office = request.form.get("office", "").strip()
        
        # Prevent editing main admin
        if username == ADMIN_USERNAME:
            flash("Cannot edit the main admin account.", "error")
            return redirect(url_for("admin.manage_users"))
        
        # Update user - only pass non-empty values
        success, error = update_user(
            username,
            full_name=full_name if full_name else None,
            role=role if role else None,
            office=office if office else None
        )
        
        if success:
            audit_log("user_edited", f"edited_user={username}, role={role}, office={office}",
                      username=session.get("username", "admin"),
                      ip=get_client_ip())
            flash(f"User '{username}' has been updated.", "success")
        else:
            flash(f"Error: {error}", "error")
        
        return redirect(url_for("admin.manage_users"))
    
    # GET request - show edit form
    users = get_all_users()
    user = next((u for u in users if u["username"] == username), None)
    
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin.manage_users"))
    
    if username == ADMIN_USERNAME:
        flash("Cannot edit the main admin account.", "error")
        return redirect(url_for("admin.manage_users"))
    
    offices = load_saved_offices()
    return render_template("edit_user.html", user=user, offices=offices,
                           admin_username=ADMIN_USERNAME)


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


# ── Dropdown Options Management ───────────────────────────────────────────────

@admin_bp.route("/dropdown-options")
@admin_required
def manage_dropdown_options():
    """Admin page to view and manage customizable dropdown options."""
    try:
        audit_log("dropdown_options_viewed", "Admin accessed dropdown options management",
                  username=session.get("username", "admin"), ip=get_client_ip())
    except Exception:
        pass
    
    configs = get_all_dropdown_configs()
    return render_template("manage_dropdowns.html", 
                          configs=configs,
                          manageable_fields=MANAGEABLE_FIELDS)


@admin_bp.route("/dropdown-options/edit/<field_name>", methods=["GET", "POST"])
@admin_required
def edit_dropdown_options(field_name):
    """Edit dropdown options for a specific field."""
    if field_name not in MANAGEABLE_FIELDS:
        flash(f"Invalid field: {field_name}", "error")
        return redirect(url_for("admin.manage_dropdown_options"))
    
    if request.method == "POST":
        options_raw = request.form.get("options", "").strip()
        # Split by newlines or commas
        options = []
        for line in options_raw.replace(",", "\n").split("\n"):
            opt = line.strip()
            if opt:
                options.append(opt)
        
        success, message = update_dropdown_options(field_name, options)
        
        if success:
            audit_log("dropdown_options_updated", 
                      f"field={field_name}, count={len(options)}",
                      username=session.get("username", "admin"), 
                      ip=get_client_ip())
            flash(message, "success")
        else:
            flash(message, "error")
        
        return redirect(url_for("admin.manage_dropdown_options"))
    
    # GET request - show edit form
    configs = get_all_dropdown_configs()
    config = configs.get(field_name, {
        "field_name": field_name,
        "display_name": MANAGEABLE_FIELDS.get(field_name, field_name.title()),
        "options": [],
        "is_default": True
    })
    
    return render_template("edit_dropdown.html", 
                          config=config,
                          field_name=field_name,
                          display_name=MANAGEABLE_FIELDS.get(field_name, field_name.title()))


@admin_bp.route("/dropdown-options/reset/<field_name>", methods=["POST"])
@admin_required
def reset_dropdown_options(field_name):
    """Reset dropdown options for a field to default."""
    if field_name not in MANAGEABLE_FIELDS:
        flash(f"Invalid field: {field_name}", "error")
        return redirect(url_for("admin.manage_dropdown_options"))
    
    success, message = reset_to_default(field_name)
    
    if success:
        audit_log("dropdown_options_reset", 
                  f"field={field_name}",
                  username=session.get("username", "admin"), 
                  ip=get_client_ip())
        flash(message, "success")
    else:
        flash(message, "error")
    
    return redirect(url_for("admin.manage_dropdown_options"))


# ── Client Approval Management ───────────────────────────────────────────────

@admin_bp.route("/pending-clients")
@admin_required
def pending_clients():
    """Admin page to view and approve pending client registrations."""
    try:
        audit_log("pending_clients_viewed", "Admin accessed pending clients list",
                  username=session.get("username", "admin"), ip=get_client_ip())
    except Exception:
        pass
    
    pending = get_pending_clients()
    return render_template("pending_clients.html", pending_clients=pending)


@admin_bp.route("/approve-client/<username>", methods=["POST"])
@admin_required
def approve_client_route(username):
    """Approve a pending client account."""
    success, error = approve_user(username)
    
    if success:
        audit_log("client_approved", f"approved_client={username}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        flash(f"Client '{username}' has been approved. They can now login.", "success")
    else:
        flash(f"Error: {error}", "error")
    
    return redirect(url_for("admin.pending_clients"))
