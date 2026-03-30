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
from services.documents import load_docs, save_doc, get_doc
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
    
    # Get all users with staff or admin role
    all_users = get_all_users()
    staff_users = [u for u in all_users if u.get("role") in ("staff", "admin")]
    
    # Add admin user to staff stats so their logged documents are visible
    admin_user = {
        "username": ADMIN_USERNAME,
        "full_name": "Administrator",
        "role": "admin",
        "office": ""
    }
    # Insert admin at the beginning of the list
    staff_users.insert(0, admin_user)
    
    # Pagination for staff table
    try:
        staff_page = max(1, int(request.args.get("staff_page", 1)))
    except ValueError:
        staff_page = 1
    staff_per_page = 10
    staff_total = len(staff_users)
    staff_total_pages = max(1, (staff_total + staff_per_page - 1) // staff_per_page)
    staff_page = min(staff_page, staff_total_pages)
    staff_start = (staff_page - 1) * staff_per_page
    staff_paginated = staff_users[staff_start:staff_start + staff_per_page]
    
    # Load all documents
    docs = load_docs()
    
    # Calculate stats per staff
    staff_stats = {}
    for staff in staff_paginated:
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
            "role": staff.get("role", "staff"),
            "total": len(staff_docs),
            "status_counts": status_counts,
            "docs": staff_docs  # Include actual docs for display
        }
    
    # Find documents with no staff assigned (not logged_by any staff and not submitted_by any client)
    unassigned_docs = [
        d for d in docs
        if not d.get("logged_by") and not d.get("original_logged_by") and not d.get("submitted_by")
    ]
    
    # Pagination for unassigned docs
    try:
        unassigned_page = max(1, int(request.args.get("unassigned_page", 1)))
    except ValueError:
        unassigned_page = 1
    unassigned_per_page = 50
    unassigned_total = len(unassigned_docs)
    unassigned_total_pages = max(1, (unassigned_total + unassigned_per_page - 1) // unassigned_per_page)
    unassigned_page = min(unassigned_page, unassigned_total_pages)
    unassigned_start = (unassigned_page - 1) * unassigned_per_page
    unassigned_paginated = unassigned_docs[unassigned_start:unassigned_start + unassigned_per_page]
    
    # Client-submitted documents (for reference)
    client_docs = [d for d in docs if d.get("submitted_by")]
    
    return render_template("staff_document_stats.html",
                           staff_stats=staff_stats,
                           unassigned_count=len(unassigned_docs),
                           unassigned_docs=unassigned_paginated,
                           client_count=len(client_docs),
                           total_docs=len(docs),
                           admin_username=ADMIN_USERNAME,
                           staff_page=staff_page,
                           staff_total_pages=staff_total_pages,
                           unassigned_page=unassigned_page,
                           unassigned_total_pages=unassigned_total_pages,
                           staff_list=staff_users  # Pass full list for batch operations
    )


@admin_bp.route("/assign-doc/<doc_id>", methods=["POST"])
@admin_required
def assign_doc(doc_id):
    """Admin can assign a document to a staff member."""
    staff_username = request.form.get("staff_username", "").strip()
    
    if not staff_username:
        flash("Please select a staff member.", "error")
        return redirect(url_for("admin.staff_document_stats"))
    
    # Get the document
    doc = get_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("admin.staff_document_stats"))
    
    # Get staff details
    from services.auth import get_all_users
    all_users = get_all_users()
    staff_user = next((u for u in all_users if u.get("username") == staff_username), None)
    
    if not staff_user:
        flash("Staff member not found.", "error")
        return redirect(url_for("admin.staff_document_stats"))
    
    staff_full_name = staff_user.get("full_name") or staff_username
    
    # Assign the document to staff
    old_logged_by = doc.get("logged_by", "")
    doc["logged_by"] = staff_username
    doc["original_logged_by"] = staff_username  # Set as original logger
    
    save_doc(doc)
    
    audit_log("doc_assigned",
              f"doc_id={doc_id} assigned to={staff_username} (was: {old_logged_by or 'unassigned'})",
              username=session.get("username", "admin"),
              ip=get_client_ip())
    
    flash(f"✅ Document assigned to {staff_full_name}.", "success")
    return redirect(url_for("admin.staff_document_stats"))


@admin_bp.route("/unassign-doc/<doc_id>", methods=["POST"])
@admin_required
def unassign_doc(doc_id):
    """Admin can unassign a document from a staff member."""
    doc = get_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("admin.staff_document_stats"))
    
    old_logged_by = doc.get("logged_by", "unassigned")
    old_original = doc.get("original_logged_by", "")
    
    # Unassign the document
    doc["logged_by"] = ""
    doc["original_logged_by"] = ""
    
    save_doc(doc)
    
    audit_log("doc_unassigned",
              f"doc_id={doc_id} unassigned from={old_logged_by} (original: {old_original})",
              username=session.get("username", "admin"),
              ip=get_client_ip())
    
    flash(f"✅ Document unassigned.", "success")
    return redirect(url_for("admin.staff_document_stats"))


@admin_bp.route("/assign-doc-batch", methods=["POST"])
@admin_required
def assign_doc_batch():
    """Admin can assign multiple documents to a staff member at once."""
    doc_ids = request.form.get("doc_ids", "").strip()
    staff_username = request.form.get("staff_username", "").strip()
    
    if not doc_ids:
        flash("No documents selected.", "error")
        return redirect(url_for("admin.staff_document_stats"))
    
    if not staff_username:
        flash("Please select a staff member.", "error")
        return redirect(url_for("admin.staff_document_stats"))
    
    # Parse document IDs
    id_list = [d.strip() for d in doc_ids.split(",") if d.strip()]
    
    if not id_list:
        flash("No valid document IDs.", "error")
        return redirect(url_for("admin.staff_document_stats"))
    
    # Get staff details
    from services.auth import get_all_users
    all_users = get_all_users()
    staff_user = next((u for u in all_users if u.get("username") == staff_username), None)
    
    if not staff_user:
        flash("Staff member not found.", "error")
        return redirect(url_for("admin.staff_document_stats"))
    
    staff_full_name = staff_user.get("full_name") or staff_username
    
    # Assign each document
    assigned_count = 0
    for doc_id in id_list:
        doc = get_doc(doc_id)
        if not doc:
            continue
        
        old_logged_by = doc.get("logged_by", "")
        doc["logged_by"] = staff_username
        doc["original_logged_by"] = staff_username
        
        save_doc(doc)
        assigned_count += 1
    
    audit_log("doc_batch_assigned",
              f"count={assigned_count} assigned to={staff_username}",
              username=session.get("username", "admin"),
              ip=get_client_ip())
    
    flash(f"✅ {assigned_count} document(s) assigned to {staff_full_name}.", "success")
    return redirect(url_for("admin.staff_document_stats"))


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


@admin_bp.route("/office-documents")
@admin_required
def office_documents():
    """Show documents grouped by office - for admin to view all office documents."""
    try:
        from services.misc import audit_log
        from utils import get_client_ip
        audit_log("office_documents_viewed", "Admin accessed office documents view",
                  username=session.get("username","admin"), ip=get_client_ip())
    except Exception:
        pass
    
    from services.misc import load_saved_offices
    from services.documents import load_docs
    from services.auth import get_all_users
    
    saved_offices = load_saved_offices()
    docs = load_docs()
    all_users = get_all_users()
    
    user_office_map = {}
    for u in all_users:
        username = u.get("username", "")
        office = u.get("office", "").strip()
        if username and office:
            user_office_map[username] = office
    
    office_docs = {}
    for office in saved_offices:
        office_name = office.get("office_name", "")
        office_slug = office.get("office_slug", "")
        if office_name:
            office_docs[office_name] = {
                "slug": office_slug,
                "name": office_name,
                "docs": [],
                "count": 0
            }
    
    unassigned_docs = []
    
    for doc in docs:
        target = doc.get("target_office_name", "").strip()
        pending = doc.get("pending_at_office", "").strip()
        logged_by = doc.get("logged_by", "").strip()
        
        staff_office = user_office_map.get(logged_by, "")
        
        if target and target in office_docs:
            office_docs[target]["docs"].append(doc)
            office_docs[target]["count"] += 1
        elif pending and pending in office_docs:
            office_docs[pending]["docs"].append(doc)
            office_docs[pending]["count"] += 1
        elif staff_office and staff_office in office_docs:
            office_docs[staff_office]["docs"].append(doc)
            office_docs[staff_office]["count"] += 1
        else:
            unassigned_docs.append(doc)
    
    try:
        office_page = max(1, int(request.args.get("office_page", 1)))
    except ValueError:
        office_page = 1
    office_per_page = 10
    office_list = [o for o in office_docs.values()]
    office_total = len(office_list)
    office_total_pages = max(1, (office_total + office_per_page - 1) // office_per_page)
    office_page = min(office_page, office_total_pages)
    office_start = (office_page - 1) * office_per_page
    office_paginated = office_list[office_start:office_start + office_per_page]
    
    total_docs = len(docs)
    assigned_docs = sum(o["count"] for o in office_docs.values())
    
    return render_template("office_documents.html",
                           office_docs=office_paginated,
                           unassigned_docs=unassigned_docs,
                           unassigned_count=len(unassigned_docs),
                           total_docs=total_docs,
                           assigned_docs=assigned_docs,
                           office_page=office_page,
                           office_total_pages=office_total_pages,
                           admin_username=ADMIN_USERNAME)


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