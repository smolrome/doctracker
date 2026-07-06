"""
routes/admin.py — Admin-only routes: user management, activity log, invites.
"""
from datetime import datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from services.auth import (
    create_user, delete_user, get_all_users, set_user_active,
    update_user_password, update_user, approve_user, get_pending_clients,
    update_user_documents_handled, set_user_can_generate_so,
)
from services.database import set_user_can_route_documents, user_has_so_access
from services.email import (
    generate_invite_token, get_all_tokens, send_invite_email,
    send_credentials_email,
)
from services.misc import audit_log, get_activity_logs
from services.documents import load_docs, save_doc, get_doc, delete_doc, backfill_logged_by_office
from utils import admin_required, get_client_ip
import secrets

from config import ADMIN_USERNAME, MAIL_ENABLED, APP_URL, STAFF_LIVE_TOKEN

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
    for u in users:
        u["has_so_access"] = user_has_so_access(u["username"])
    from services.misc import load_saved_offices
    offices = load_saved_offices()
    return render_template("manage_users.html", users=users,
                           admin_username=ADMIN_USERNAME, offices=offices,
                           active_tab="users")


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


# ── Staff Live Dashboard ───────────────────────────────────────────────────────

def _compute_staff_live_stats():
    """Shared computation for both the page render and the JSON refresh endpoint."""
    from datetime import date as _date
    from app import get_user_presence
    all_users = get_all_users()
    docs      = load_docs()
    today     = str(_date.today())

    staff_users = [u for u in all_users
                   if u.get("role") == "staff" and u.get("active", True)]

    presence = get_user_presence({u.get("username", "") for u in staff_users})

    stats = []
    for u in staff_users:
        uname     = u.get("username", "")
        full_name = u.get("full_name") or uname
        if not uname:
            continue

        logged      = sum(1 for d in docs
                          if d.get("logged_by") == uname or d.get("original_logged_by") == uname)
        accepted    = sum(1 for d in docs if d.get("accepted_by") == uname)
        transferred = sum(1 for d in docs if d.get("transferred_by") == uname)
        released    = sum(1 for d in docs if d.get("released_by") == uname)
        received    = sum(1 for d in docs if d.get("received_by") == full_name)
        pending     = sum(1 for d in docs
                          if d.get("pending_at_staff") == uname
                          and (d.get("status") or "") not in ("Released", "Archived", "Rejected"))

        stats.append({
            "username":    uname,
            "full_name":   full_name,
            "office":      u.get("office") or "—",
            "logged":      logged,
            "accepted":    accepted,
            "transferred": transferred,
            "released":    released,
            "received":    received,
            "pending":     pending,
            "total":       logged,
            "presence":    presence.get(uname, "offline"),
        })

    stats.sort(key=lambda x: -x["total"])

    # Group by office (alphabetical office order; within each office, total-desc order preserved)
    from collections import defaultdict as _dd
    _groups = _dd(list)
    for s in stats:
        _groups[s["office"]].append(s)
    office_groups = [
        {"office": k, "staff": v}
        for k, v in sorted(_groups.items())
    ]

    total_docs        = len([d for d in docs if not d.get("deleted")])
    today_docs        = sum(1 for d in docs
                            if (d.get("created_at") or "")[:10] == today and not d.get("deleted"))
    active_staff      = len(stats)
    pending_transfers = sum(1 for d in docs
                            if d.get("transfer_status") == "pending" and not d.get("deleted"))

    totals = {
        "total_docs":        total_docs,
        "today_docs":        today_docs,
        "active_staff":      active_staff,
        "pending_transfers": pending_transfers,
    }
    return stats, totals, office_groups


@admin_bp.route("/staff-live")
def staff_live():
    """TV dashboard — accessible via secret token, no admin login required."""
    token = request.args.get("token", "")
    if not STAFF_LIVE_TOKEN or not token or not secrets.compare_digest(token, STAFF_LIVE_TOKEN):
        return "Access denied", 403
    stats, totals, office_groups = _compute_staff_live_stats()
    last_updated = datetime.now().strftime("%b %d, %Y %I:%M %p")
    return render_template("staff_live.html",
                           staff_stats=stats,
                           office_groups=office_groups,
                           totals=totals,
                           last_updated=last_updated,
                           live_token=token)


@admin_bp.route("/api/staff-live-data")
def staff_live_data():
    """JSON refresh endpoint for the TV dashboard (polled every 30 s)."""
    token = request.args.get("token", "")
    if not STAFF_LIVE_TOKEN or not token or not secrets.compare_digest(token, STAFF_LIVE_TOKEN):
        return jsonify(error="Access denied"), 403
    stats, totals, office_groups = _compute_staff_live_stats()
    return jsonify({
        "staff":         stats,
        "office_groups": office_groups,
        "totals":        totals,
        "last_updated":  datetime.now().strftime("%b %d, %Y %I:%M %p"),
    })


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
    # Only set logged_by (current holder); preserve original_logged_by so the
    # routing-back workflow (transfer → release by original logger) still works.
    # Only seed original_logged_by if the document never had one.
    old_logged_by = doc.get("logged_by", "")
    doc["logged_by"] = staff_username
    if not doc.get("original_logged_by"):
        doc["original_logged_by"] = staff_username
    
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
        if not doc.get("original_logged_by"):
            doc["original_logged_by"] = staff_username

        save_doc(doc)
        assigned_count += 1
    
    audit_log("doc_batch_assigned",
              f"count={assigned_count} assigned to={staff_username}",
              username=session.get("username", "admin"),
              ip=get_client_ip())
    
    flash(f"✅ {assigned_count} document(s) assigned to {staff_full_name}.", "success")
    return redirect(url_for("admin.staff_document_stats"))


@admin_bp.route("/delete-unassigned-batch", methods=["POST"])
@admin_required
def delete_unassigned_batch():
    """Admin can delete all unassigned documents or selected ones."""
    doc_ids = request.form.get("doc_ids", "").strip()
    delete_all = request.form.get("delete_all", "").strip() == "1"

    if delete_all:
        # Delete ALL unassigned documents (not just those on current page)
        docs = load_docs()
        unassigned_docs = [
            d for d in docs
            if not d.get("logged_by") and not d.get("original_logged_by") and not d.get("submitted_by")
        ]
        deleted_count = 0
        username = session.get("username", "admin")
        for doc in unassigned_docs:
            doc_id = doc.get("id")
            if doc_id:
                delete_doc(doc_id, deleted_by=username)
                deleted_count += 1

        audit_log("unassigned_docs_deleted_all",
                  f"deleted_count={deleted_count}",
                  username=username,
                  ip=get_client_ip())

        flash(f"✅ {deleted_count} unassigned document(s) deleted.", "success")
    else:
        # Delete selected documents only
        if not doc_ids:
            flash("No documents selected.", "error")
            return redirect(url_for("admin.staff_document_stats"))

        id_list = [d.strip() for d in doc_ids.split(",") if d.strip()]
        deleted_count = 0
        username = session.get("username", "admin")

        for doc_id in id_list:
            doc = get_doc(doc_id)
            if not doc:
                continue
            # Only delete if truly unassigned
            if not doc.get("logged_by") and not doc.get("original_logged_by") and not doc.get("submitted_by"):
                delete_doc(doc_id, deleted_by=username)
                deleted_count += 1

        audit_log("unassigned_docs_deleted_selected",
                  f"deleted_count={deleted_count}",
                  username=username,
                  ip=get_client_ip())

        flash(f"✅ {deleted_count} unassigned document(s) deleted.", "success")

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


@admin_bp.route("/backfill-office", methods=["POST"])
@admin_required
def run_backfill_office():
    """One-time backfill to populate logged_by_office for existing docs."""
    try:
        count = backfill_logged_by_office()
        flash(f"✅ Backfilled logged_by_office for {count} documents.", "success")
    except Exception as e:
        flash(f"❌ Backfill failed: {e}", "error")
    return redirect(url_for("admin.activity_log"))


@admin_bp.route("/pending-clients")
@admin_required
def pending_clients():
    """Show pending client registrations for admin approval."""
    try:
        from services.misc import audit_log
        from utils import get_client_ip
        audit_log("pending_clients_viewed", "Admin accessed pending clients",
                  username=session.get("username","admin"), ip=get_client_ip())
    except Exception:
        pass
    pending = get_pending_clients()
    return render_template("pending_clients.html", pending_clients=pending,
                           admin_username=ADMIN_USERNAME, active_tab="pending")


@admin_bp.route("/api/admin/pending-clients-count")
@admin_required
def pending_clients_count():
    """JSON: count of unapproved client accounts. Polled by the nav badge."""
    return jsonify(count=len(get_pending_clients()))


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

    # Normalized (strip + casefold) office-name lookup → canonical office_docs key.
    # Removes case/spacing fragility in matching. READ-ONLY: nothing is written to docs.
    def _norm(s):
        return (s or "").strip().casefold()
    office_by_norm = {_norm(name): name for name in office_docs}

    for doc in docs:
        target       = _norm(doc.get("target_office_name"))
        pending      = _norm(doc.get("pending_at_office"))
        logged_by    = doc.get("logged_by", "").strip()
        staff_office = _norm(user_office_map.get(logged_by, ""))
        # sender_org is noisy (holds towns/districts/external senders too), so it is
        # only used as a display inference when it EXACTLY matches a known office name.
        sender_org   = _norm(doc.get("sender_org"))

        match = None
        if target and target in office_by_norm:
            match = office_by_norm[target]
        elif pending and pending in office_by_norm:
            match = office_by_norm[pending]
        elif staff_office and staff_office in office_by_norm:
            match = office_by_norm[staff_office]
        elif sender_org and sender_org in office_by_norm:
            match = office_by_norm[sender_org]

        if match:
            office_docs[match]["docs"].append(doc)
            office_docs[match]["count"] += 1
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
                           office_total=office_total,
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


@admin_bp.route("/resend-credentials/<username>", methods=["POST"])
@admin_required
def resend_credentials_route(username):
    """Reset password and resend login credentials to the staff member's email."""
    import secrets
    import string

    if username == ADMIN_USERNAME:
        flash("Cannot resend credentials for the built-in admin account.", "error")
        return redirect(url_for("admin.manage_users"))

    all_users = get_all_users()
    user = next((u for u in all_users if u.get("username") == username), None)

    if not user:
        flash(f"User '{username}' not found.", "error")
        return redirect(url_for("admin.manage_users"))

    to_email = (user.get("email") or "").strip()
    if not to_email:
        flash(f"Cannot resend — '{username}' has no email address on record.", "error")
        return redirect(url_for("admin.manage_users"))

    # Generate a new 12-char temporary password (at least one digit + one uppercase)
    alphabet = string.ascii_letters + string.digits
    pw = [
        secrets.choice(string.digits),
        secrets.choice(string.ascii_uppercase),
        *[secrets.choice(alphabet) for _ in range(10)],
    ]
    for j in range(len(pw) - 1, 0, -1):
        k = secrets.randbelow(j + 1)
        pw[j], pw[k] = pw[k], pw[j]
    temp_pw = "".join(pw)

    # Overwrite the user's password with the new temporary one
    ok, err = update_user_password(username, temp_pw)
    if not ok:
        flash(f"Failed to reset password for '{username}': {err}", "error")
        return redirect(url_for("admin.manage_users"))

    # Email the new credentials
    base      = _base_url(request.host_url.rstrip("/"))
    full_name = (user.get("full_name") or username).strip()
    email_sent, email_err = send_credentials_email(to_email, full_name, username, temp_pw, base)

    audit_log(
        "credentials_resent",
        f"user={username} email={to_email} email_sent={email_sent}",
        username=session.get("username", "admin"),
        ip=get_client_ip(),
    )

    if email_sent:
        flash(f"✅ New credentials sent to {to_email}.", "success")
    else:
        flash(
            f"Password reset but email failed ({email_err}). "
            f"Share this temporary password manually: {temp_pw}",
            "error",
        )
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


@admin_bp.route("/approve-client/<username>", methods=["POST"])
@admin_required
def approve_client_route(username):
    ok, err = approve_user(username)
    if ok:
        audit_log("client_approved", f"approved_client={username}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        flash(f"Client '{username}' has been approved.", "success")
    else:
        flash(err or "Failed to approve client.", "error")
    return redirect(url_for("admin.pending_clients"))


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
    """Edit user details: username, email, full_name, role, office, documents_handled."""
    new_username = request.form.get("new_username", "").strip().lower()
    email        = request.form.get("email", "").strip()
    full_name    = request.form.get("full_name", "").strip()
    role         = request.form.get("role", "").strip()
    office       = request.form.get("office", "").strip()
    raw_docs     = request.form.get("documents_handled", "").strip()
    doc_types    = [d.strip() for d in raw_docs.split(",") if d.strip()] if raw_docs else []

    # Prevent renaming to a blank username
    if new_username == "":
        new_username = username  # keep original if field was cleared

    # Get original user data for audit
    all_users     = get_all_users()
    original_user = next((u for u in all_users if u.get("username") == username), None)

    ok, err = update_user(
        username,
        full_name    = full_name if full_name else None,
        role         = role if role else None,
        office       = office if office else None,
        email        = email,                               # always pass (blank = clear)
        new_username = new_username if new_username != username else None,
    )

    if ok:
        # After a rename the canonical username has changed — use new_username for follow-up calls
        effective_username = new_username if new_username != username else username

        # Always update documents_handled (blank form field → empty list = clear)
        update_user_documents_handled(effective_username, doc_types)

        changes = []
        if original_user:
            if new_username != username:
                changes.append(f"username: {username} -> {new_username}")
            if original_user.get("email", "") != email:
                changes.append(f"email: {original_user.get('email')} -> {email}")
            if original_user.get("full_name") != full_name:
                changes.append(f"name: {original_user.get('full_name')} -> {full_name}")
            if original_user.get("role") != role:
                changes.append(f"role: {original_user.get('role')} -> {role}")
            if original_user.get("office") != office:
                changes.append(f"office: {original_user.get('office')} -> {office}")
            old_docs = original_user.get("documents_handled") or []
            if old_docs != doc_types:
                changes.append(f"documents_handled: {old_docs} -> {doc_types}")

        audit_log("user_edited",
                  f"admin edited user={username}: {'; '.join(changes) if changes else 'no changes'}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        flash(f"✅ User '{effective_username}' updated successfully.", "success")
    else:
        flash(f"Failed to update user: {err}", "error")

    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/toggle-so-access/<username>", methods=["POST"])
@admin_required
def toggle_so_access(username):
    """Grant or revoke can_generate_so for a staff user."""
    if username == ADMIN_USERNAME:
        flash("Admin always has SO access.", "error")
        return redirect(url_for("admin.manage_users"))
    all_users = get_all_users()
    user = next((u for u in all_users if u.get("username") == username), None)
    if not user:
        flash(f"User '{username}' not found.", "error")
        return redirect(url_for("admin.manage_users"))
    new_value = not bool(user.get("can_generate_so", False))
    ok, err = set_user_can_generate_so(username, new_value)
    if ok:
        action = "granted" if new_value else "revoked"
        audit_log("so_access_toggled",
                  f"user={username} can_generate_so={new_value}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        flash(f"✅ SO access {action} for '{username}'.", "success")
    else:
        flash(f"Failed to update SO access: {err}", "error")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/toggle-route-access/<username>", methods=["POST"])
@admin_required
def toggle_route_access(username):
    """Grant or revoke can_route_documents for a staff user."""
    if username == ADMIN_USERNAME:
        flash("Admin always has Route access.", "error")
        return redirect(url_for("admin.manage_users"))
    all_users = get_all_users()
    user = next((u for u in all_users if u.get("username") == username), None)
    if not user:
        flash(f"User '{username}' not found.", "error")
        return redirect(url_for("admin.manage_users"))
    new_value = not bool(user.get("can_route_documents", False))
    ok, err = set_user_can_route_documents(username, new_value)
    if ok:
        action = "granted" if new_value else "revoked"
        audit_log("route_access_toggled",
                  f"user={username} can_route_documents={new_value}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        flash(f"✅ Route access {action} for '{username}'.", "success")
    else:
        flash(f"Failed to update Route access: {err}", "error")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/manage-pairings")
@admin_required
def manage_pairings():
    from services.database import USE_DB, get_conn
    from services.auth import get_all_users
    groups = []
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, group_name, created_by, has_so_access, has_shared_dashboard,
                               has_shared_transfer,
                               to_char(created_at, 'Mon DD, YYYY') AS created_date
                        FROM staff_groups
                        ORDER BY created_at DESC
                    """)
                    raw_groups = cur.fetchall() or []
                    # Fetch members for each group
                    for g in raw_groups:
                        cur.execute("""
                            SELECT id, username, added_by,
                                   to_char(added_at, 'Mon DD, YYYY') AS added_date
                            FROM staff_group_members
                            WHERE group_id = %s
                            ORDER BY added_at ASC
                        """, (g['id'],))
                        members = cur.fetchall() or []
                        groups.append({
                            'id':                 g['id'],
                            'group_name':         g['group_name'],
                            'created_by':         g['created_by'],
                            'created_date':       g['created_date'],
                            'has_so_access':      bool(g['has_so_access']),
                            'has_shared_dashboard': bool(g['has_shared_dashboard']),
                            'has_shared_transfer':  bool(g.get('has_shared_transfer')),
                            'members':            list(members),
                        })
        except Exception:
            pass
    all_users = get_all_users()
    staff_users = [u for u in all_users if u.get("role") in ("staff", "admin")]
    # Build username → full_name map for display
    name_map = {u['username']: (u.get('full_name') or u['username']) for u in all_users}
    return render_template("manage_pairings.html",
                           groups=groups,
                           staff_users=staff_users,
                           name_map=name_map,
                           active_tab="pairings")


@admin_bp.route("/manage-pairings/create-group", methods=["POST"])
@admin_required
def create_group():
    from services.database import USE_DB, get_conn
    group_name = request.form.get("group_name", "").strip()
    if not group_name:
        flash("Group name is required.", "error")
        return redirect(url_for("admin.manage_pairings"))
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO staff_groups (group_name, created_by)
                        VALUES (%s, %s)
                        ON CONFLICT (group_name) DO NOTHING
                    """, (group_name, session.get("username", "admin")))
            audit_log("group_created", f"group_name={group_name}",
                      username=session.get("username", "admin"), ip=get_client_ip())
            flash(f"Group '{group_name}' created.", "success")
        except Exception as e:
            flash(f"Failed to create group: {e}", "error")
    else:
        flash("Database not available.", "error")
    return redirect(url_for("admin.manage_pairings"))


@admin_bp.route("/manage-pairings/add-member", methods=["POST"])
@admin_required
def add_group_member():
    from services.database import USE_DB, get_conn
    group_id = request.form.get("group_id", "").strip()
    username = request.form.get("username", "").strip()
    if not group_id or not username:
        flash("Group and staff member are required.", "error")
        return redirect(url_for("admin.manage_pairings"))
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO staff_group_members (group_id, username, added_by)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (group_id, username) DO NOTHING
                    """, (int(group_id), username, session.get("username", "admin")))
            audit_log("group_member_added", f"group_id={group_id} username={username}",
                      username=session.get("username", "admin"), ip=get_client_ip())
            flash(f"Added {username} to group.", "success")
        except Exception as e:
            flash(f"Failed to add member: {e}", "error")
    else:
        flash("Database not available.", "error")
    return redirect(url_for("admin.manage_pairings"))


@admin_bp.route("/manage-pairings/remove-member/<int:member_id>", methods=["POST"])
@admin_required
def remove_group_member(member_id):
    from services.database import USE_DB, get_conn
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT username, group_id FROM staff_group_members WHERE id = %s", (member_id,))
                    row = cur.fetchone()
                    if row:
                        cur.execute("DELETE FROM staff_group_members WHERE id = %s", (member_id,))
                        audit_log("group_member_removed",
                                  f"member_id={member_id} username={row['username']} group_id={row['group_id']}",
                                  username=session.get("username", "admin"), ip=get_client_ip())
                        flash(f"Removed {row['username']} from group.", "success")
                    else:
                        flash("Member not found.", "error")
        except Exception as e:
            flash(f"Failed to remove member: {e}", "error")
    else:
        flash("Database not available.", "error")
    return redirect(url_for("admin.manage_pairings"))


@admin_bp.route("/manage-pairings/delete-group/<int:group_id>", methods=["POST"])
@admin_required
def delete_group(group_id):
    from services.database import USE_DB, get_conn
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT group_name FROM staff_groups WHERE id = %s", (group_id,))
                    row = cur.fetchone()
                    if row:
                        cur.execute("DELETE FROM staff_groups WHERE id = %s", (group_id,))
                        audit_log("group_deleted",
                                  f"group_id={group_id} group_name={row['group_name']}",
                                  username=session.get("username", "admin"), ip=get_client_ip())
                        flash(f"Group '{row['group_name']}' deleted.", "success")
                    else:
                        flash("Group not found.", "error")
        except Exception as e:
            flash(f"Failed to delete group: {e}", "error")
    else:
        flash("Database not available.", "error")
    return redirect(url_for("admin.manage_pairings"))


@admin_bp.route("/manage-pairings/toggle-so-access/<int:group_id>", methods=["POST"])
@admin_required
def toggle_group_so_access(group_id):
    from services.database import USE_DB, get_conn
    if not USE_DB:
        flash("Database not available.", "error")
        return redirect(url_for("admin.manage_pairings"))
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT group_name, has_so_access FROM staff_groups WHERE id = %s", (group_id,))
                row = cur.fetchone()
                if not row:
                    flash("Group not found.", "error")
                    return redirect(url_for("admin.manage_pairings"))
                new_val = not bool(row['has_so_access'])
                cur.execute("UPDATE staff_groups SET has_so_access = %s WHERE id = %s", (new_val, group_id))
        audit_log("group_so_access_toggled",
                  f"group_id={group_id} group_name={row['group_name']} has_so_access={new_val}",
                  username=session.get("username", "admin"), ip=get_client_ip())
        state = "enabled" if new_val else "disabled"
        flash(f"SO Access {state} for group '{row['group_name']}'.", "success")
    except Exception as e:
        flash(f"Failed to update SO access: {e}", "error")
    return redirect(url_for("admin.manage_pairings"))


@admin_bp.route("/manage-pairings/toggle-shared-dashboard/<int:group_id>", methods=["POST"])
@admin_required
def toggle_group_shared_dashboard(group_id):
    from services.database import USE_DB, get_conn
    if not USE_DB:
        flash("Database not available.", "error")
        return redirect(url_for("admin.manage_pairings"))
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT group_name, has_shared_dashboard FROM staff_groups WHERE id = %s", (group_id,))
                row = cur.fetchone()
                if not row:
                    flash("Group not found.", "error")
                    return redirect(url_for("admin.manage_pairings"))
                new_val = not bool(row['has_shared_dashboard'])
                # Shared Transfer DEPENDS on Shared Dashboard. Turning the
                # dashboard off forces transfer off in the same update so the row
                # is never left with a stale has_shared_transfer = TRUE (which the
                # data-layer helper already ignores, but we keep state honest).
                if new_val:
                    cur.execute(
                        "UPDATE staff_groups SET has_shared_dashboard = %s WHERE id = %s",
                        (new_val, group_id))
                else:
                    cur.execute(
                        "UPDATE staff_groups SET has_shared_dashboard = %s, "
                        "has_shared_transfer = FALSE WHERE id = %s",
                        (new_val, group_id))
        audit_log("group_shared_dashboard_toggled",
                  f"group_id={group_id} group_name={row['group_name']} has_shared_dashboard={new_val}",
                  username=session.get("username", "admin"), ip=get_client_ip())
        state = "enabled" if new_val else "disabled"
        flash(f"Shared Dashboard {state} for group '{row['group_name']}'.", "success")
    except Exception as e:
        flash(f"Failed to update Shared Dashboard: {e}", "error")
    return redirect(url_for("admin.manage_pairings"))


@admin_bp.route("/manage-pairings/toggle-shared-transfer/<int:group_id>", methods=["POST"])
@admin_required
def toggle_group_shared_transfer(group_id):
    from services.database import USE_DB, get_conn
    if not USE_DB:
        flash("Database not available.", "error")
        return redirect(url_for("admin.manage_pairings"))
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT group_name, has_shared_transfer, has_shared_dashboard "
                    "FROM staff_groups WHERE id = %s", (group_id,))
                row = cur.fetchone()
                if not row:
                    flash("Group not found.", "error")
                    return redirect(url_for("admin.manage_pairings"))
                new_val = not bool(row['has_shared_transfer'])
                # DEPENDENCY GUARD: transfer cannot be enabled without dashboard.
                if new_val and not bool(row['has_shared_dashboard']):
                    flash(
                        f"Enable Shared Dashboard first — Shared Transfer requires "
                        f"it for group '{row['group_name']}'.", "error")
                    return redirect(url_for("admin.manage_pairings"))
                cur.execute(
                    "UPDATE staff_groups SET has_shared_transfer = %s WHERE id = %s",
                    (new_val, group_id))
        audit_log("group_shared_transfer_toggled",
                  f"group_id={group_id} group_name={row['group_name']} has_shared_transfer={new_val}",
                  username=session.get("username", "admin"), ip=get_client_ip())
        state = "enabled" if new_val else "disabled"
        flash(f"Shared Transfer {state} for group '{row['group_name']}'.", "success")
    except Exception as e:
        flash(f"Failed to update Shared Transfer: {e}", "error")
    return redirect(url_for("admin.manage_pairings"))


@admin_bp.route("/clear-database", methods=["POST"])
@admin_required
def clear_database():
    """ARM step of the two-step wipe. Deletes NOTHING.

    Takes a mandatory, VERIFIED pre-wipe backup first — no backup, no wipe.
    On success it arms a single-use token (with a 5-minute expiry) in the
    session and redirects to the Database Management page, where the admin can
    download the backup and confirm the final wipe. The actual, atomic wipe
    happens only at POST /clear-database/confirm once armed.
    """
    from services.backup import write_backup_to_disk
    from datetime import datetime, timezone
    import os

    username = session.get("username", "admin")

    # HARD PRECONDITION: a real, verified safety backup must exist first.
    ok, filepath, err = write_backup_to_disk()
    if not ok:
        # Never leave a stale armed state behind on failure.
        session.pop("clear_db_armed", None)
        current_app.logger.error("clear_database arm aborted — backup failed: %s", err)
        flash(f"Clear aborted — mandatory safety backup failed: {err} "
              "No data was deleted.", "error")
        return redirect(url_for("admin.staff_document_stats"))

    # Arm: single-use token (secrets, like the app's CSRF token) + backup path +
    # UTC arm timestamp for the 5-minute expiry — all held server-side.
    session["clear_db_armed"] = {
        "token":    secrets.token_hex(32),
        "filepath": filepath,
        "armed_at": datetime.now(timezone.utc).isoformat(),
    }

    audit_log("database_clear_armed",
              f"backup={os.path.basename(filepath)} size={os.path.getsize(filepath)}",
              username=username, ip=get_client_ip())

    # Redirect to Database Management (NOT a file download). The armed state
    # lives in the session, so the page renders the "Confirm Final Wipe" step.
    # NOTHING is deleted here.
    flash("Safety backup created and secured. Review it below, then confirm the "
          "final wipe within 5 minutes. Nothing has been deleted yet.", "success")
    return redirect(url_for("backup.backup_page"))


@admin_bp.route("/clear-database/confirm", methods=["POST"])
@admin_required
def clear_database_confirm():
    """FIRE step of the two-step wipe. Requires a prior armed backup.

    Verifies the single-use arm token, then wipes documents + routing slips in
    a SINGLE get_conn() transaction (atomic — fixes the old two-transaction
    non-atomic wipe). Permanent and irreversible.
    """
    from services.database import USE_DB, get_conn
    from services.backup import clear_db_arm_is_valid
    import os, json as _json

    username = session.get("username", "admin")

    # Consume the armed state (single-use). Absent → not armed / session expired.
    armed     = session.pop("clear_db_armed", None)
    submitted = request.form.get("arm_token", "")

    if not isinstance(armed, dict) or not armed.get("token"):
        flash("Clear not armed or session expired — please start again.", "error")
        return redirect(url_for("admin.staff_document_stats"))

    # Defense in depth: independently re-check the 5-minute expiry so a stale
    # token can never be replayed even if the GET didn't disarm it.
    if not clear_db_arm_is_valid(armed):
        current_app.logger.warning("clear_database_confirm expired arm by %s", username)
        flash("Clear-database arming expired (5-minute window) — please re-arm.", "error")
        return redirect(url_for("admin.staff_document_stats"))

    armed_token = armed.get("token", "")
    backup_path = armed.get("filepath")

    # Constant-time token comparison (mirrors app.py CSRF validation).
    if not submitted or not secrets.compare_digest(armed_token, submitted):
        current_app.logger.warning("clear_database_confirm token mismatch by %s", username)
        flash("Confirmation token mismatch — clear aborted. Please start again.", "error")
        return redirect(url_for("admin.staff_document_stats"))

    count = 0
    try:
        if USE_DB:
            # SINGLE transaction: both deletes commit together on clean exit, or
            # both roll back if either fails. get_conn() auto-commits/rolls back.
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) AS cnt FROM documents")
                    row = cur.fetchone()
                    count = row["cnt"] if row else 0
                    cur.execute("DELETE FROM documents")
                    cur.execute("DELETE FROM routing_slips")
        else:
            path = "documents.json"
            if os.path.exists(path):
                with open(path) as f:
                    count = len(_json.load(f))

        # JSON fallback wipe (unconditional, as before).
        for fpath, empty in [("documents.json", []), ("routing_slips.json", {})]:
            if os.path.exists(fpath):
                with open(fpath, "w") as f:
                    _json.dump(empty, f)

        audit_log("database_cleared",
                  f"deleted_count={count} "
                  f"backup={os.path.basename(backup_path) if backup_path else '?'}",
                  username=username,
                  ip=get_client_ip())
        flash(f"Database cleared — {count} document(s) and all routing slips permanently deleted.", "success")
        return redirect(url_for("admin.staff_document_stats"))

    except Exception as e:
        # get_conn() already rolled the failed transaction back; nothing partial
        # was committed thanks to the single-transaction structure above.
        current_app.logger.exception("clear_database_confirm failed")
        flash(f"Clear failed: {e}", "error")
        return redirect(url_for("admin.staff_document_stats"))


@admin_bp.route("/api/parse-excel-users", methods=["POST"])
@admin_required
def parse_excel_users():
    """Parse an uploaded Excel file and return name+email+documents rows as JSON."""
    import openpyxl, io
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file uploaded."}), 400
    try:
        wb = openpyxl.load_workbook(io.BytesIO(f.read()), data_only=True)
        ws = wb.active

        # Find header row (scan first 5 rows for name+email+documents columns)
        name_col = email_col = docs_col = header_row = None
        for row in ws.iter_rows(min_row=1, max_row=5):
            ni = ei = di = None
            for cell in row:
                h = str(cell.value or "").strip().lower()
                if ni is None and ("name" in h or "full" in h):
                    ni = cell.column
                if ei is None and ("email" in h or "mail" in h):
                    ei = cell.column
                if di is None and ("document" in h or "handled" in h):
                    di = cell.column
            if ni and ei:
                name_col, email_col, docs_col, header_row = ni, ei, di, cell.row
                break

        if not header_row:
            return jsonify({"error": "Could not find a Name and Email column in the file."}), 422

        rows = []
        for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
            name  = str(row[name_col - 1]  or "").strip()
            email = str(row[email_col - 1] or "").strip()
            docs  = str(row[docs_col - 1]  or "").strip() if docs_col else ""
            if email:
                rows.append({"name": name, "email": email, "documents": docs})

        if not rows:
            return jsonify({"error": "No data rows found after the header."}), 422

        return jsonify({"rows": rows})
    except Exception as e:
        return jsonify({"error": f"Could not read file: {e}"}), 400


@admin_bp.route("/api/parse-excel-offices", methods=["POST"])
@admin_required
def parse_excel_offices():
    """Parse an uploaded Excel file and return office_name + primary_recipient rows as JSON."""
    import openpyxl, io
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file uploaded."}), 400
    try:
        wb = openpyxl.load_workbook(io.BytesIO(f.read()), data_only=True)
        ws = wb.active

        # Find header row (first row with at least 1 non-null cell)
        name_col = recipient_col = header_row = None
        for row in ws.iter_rows(min_row=1, max_row=10):
            for cell in row:
                h = str(cell.value or "").strip().lower()
                if name_col is None and ("office" in h or ("name" in h and "recipient" not in h)):
                    name_col = cell.column
                if recipient_col is None and any(k in h for k in ("recipient", "staff", "assigned")):
                    recipient_col = cell.column
            if name_col:
                header_row = row[0].row
                break

        if not header_row:
            return jsonify({"error": "Could not find an office name column in the file."}), 422

        rows = []
        for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
            office_name = str(row[name_col - 1] or "").strip()
            recipient   = str(row[recipient_col - 1] or "").strip() if recipient_col else ""
            if office_name and office_name.lower() not in ("none", "nan"):
                rows.append({"office_name": office_name, "primary_recipient": recipient})
            if len(rows) >= 200:
                break

        if not rows:
            return jsonify({"error": "No data rows found after the header."}), 422

        return jsonify({"rows": rows})
    except Exception as e:
        return jsonify({"error": f"Could not read file: {e}"}), 400


@admin_bp.route("/bulk-create-users", methods=["GET", "POST"])
@admin_required
def bulk_create_users():
    """Create multiple user accounts from just name + email. Auto-generates username and password."""
    import re
    import secrets
    import string

    def _make_username(full_name: str, existing: set) -> str:
        """Derive a username from a full name, avoiding collisions in existing set."""
        base = re.sub(r"[^a-z0-9]", ".", full_name.strip().lower())
        base = re.sub(r"\.{2,}", ".", base).strip(".")
        if not base:
            base = "user"
        candidate = base
        suffix = 2
        while candidate in existing:
            candidate = f"{base}{suffix}"
            suffix += 1
        return candidate

    def _make_password() -> str:
        """Generate a 12-char password with at least one digit and one uppercase letter."""
        alphabet = string.ascii_letters + string.digits
        pw = [
            secrets.choice(string.digits),
            secrets.choice(string.ascii_uppercase),
            *[secrets.choice(alphabet) for _ in range(10)],
        ]
        # Fisher-Yates shuffle
        for j in range(len(pw) - 1, 0, -1):
            k = secrets.randbelow(j + 1)
            pw[j], pw[k] = pw[k], pw[j]
        return "".join(pw)

    results = None

    if request.method == "POST":
        full_names   = request.form.getlist("full_name")
        emails       = request.form.getlist("email")
        docs_handled = request.form.getlist("documents_handled")

        # Collect all existing users for collision detection and email lookup
        all_users = get_all_users()
        taken = {u["username"].lower() for u in all_users} | {ADMIN_USERNAME.lower()}
        # Build a case-insensitive email → user map for update-if-exists logic
        existing_by_email = {
            u.get("email", "").strip().lower(): u
            for u in all_users
            if u.get("email", "").strip()
        }

        base = _base_url(request.host_url.rstrip("/"))
        results = []

        role   = request.form.get("role", "staff").strip()
        office = request.form.get("office", "").strip()
        if role not in ("admin", "staff", "client"):
            role = "staff"

        for i, full_name in enumerate(full_names):
            full_name = full_name.strip()
            email     = emails[i].strip() if i < len(emails) else ""

            if not email:
                continue

            # Parse documents_handled: comma-separated string → list
            raw_docs  = docs_handled[i].strip() if i < len(docs_handled) else ""
            doc_types = [d.strip() for d in raw_docs.split(",") if d.strip()] if raw_docs else []

            # ── Update existing user if email already exists ──────────────
            email_lower = email.lower()
            if email_lower in existing_by_email:
                existing = existing_by_email[email_lower]
                uname    = existing["username"]
                if doc_types:
                    update_user_documents_handled(uname, doc_types)
                results.append({
                    "username":          uname,
                    "full_name":         existing.get("full_name") or full_name,
                    "email":             email,
                    "role":              existing.get("role", role),
                    "office":            existing.get("office", office),
                    "ok":                True,
                    "updated":           True,
                    "documents_handled": doc_types,
                    "password":          None,
                    "email_sent":        False,
                    "email_err":         "",
                    "msg":               "",
                })
                continue

            # ── Create new user ───────────────────────────────────────────
            uname   = _make_username(full_name or email.split("@")[0], taken)
            taken.add(uname)
            temp_pw = _make_password()

            ok, err = create_user(uname, temp_pw, full_name, role=role, email=email,
                                  office=office, documents_handled=doc_types or None)
            if not ok:
                results.append({
                    "username": uname, "full_name": full_name, "email": email,
                    "ok": False, "updated": False, "msg": err,
                    "password": None, "email_sent": False,
                })
                continue

            email_sent, email_err = False, "No email provided"
            if email:
                email_sent, email_err = send_credentials_email(
                    email, full_name, uname, temp_pw, base
                )

            results.append({
                "username":          uname,
                "full_name":         full_name,
                "email":             email,
                "role":              role,
                "office":            office,
                "ok":                True,
                "updated":           False,
                "documents_handled": doc_types,
                "password":          temp_pw if not email_sent else None,
                "email_sent":        email_sent,
                "email_err":         email_err if not email_sent else "",
                "msg":               "",
            })

        ok_count = sum(1 for r in results if r["ok"])
        audit_log(
            "bulk_users_created",
            f"total={len(results)} ok={ok_count}",
            username=session.get("username", "admin"),
            ip=get_client_ip(),
        )

    from services.misc import load_saved_offices
    saved_offices = load_saved_offices()

    return render_template(
        "bulk_create_users.html",
        results=results,
        mail_enabled=MAIL_ENABLED,
        saved_offices=saved_offices,
    )


# ── Appointments ──────────────────────────────────────────────────────────────

@admin_bp.route("/appointments")
@admin_required
def admin_appointments():
    from services.appointments import get_all_appointments
    from services.misc import load_saved_offices
    date   = request.args.get('date', '')
    office = request.args.get('office', '')
    status = request.args.get('status', '')
    appointments = get_all_appointments(
        date=date or None,
        office=office or None,
        status=status or None,
    )
    offices = load_saved_offices()
    from datetime import datetime as _dt
    return render_template('admin_appointments.html',
        appointments=appointments,
        offices=offices,
        filter_date=date,
        filter_office=office,
        filter_status=status,
        today_date=_dt.now().strftime('%Y-%m-%d'),
    )


@admin_bp.route("/appointments/<apt_id>/confirm", methods=["POST"])
@admin_required
def confirm_appointment(apt_id):
    from services.appointments import get_appointment, update_appointment
    from services.queue_bridge import push_appointment_ticket
    apt = get_appointment(apt_id)
    if not apt:
        flash("Appointment not found.", "error")
        return redirect(url_for('admin.admin_appointments'))
    result = push_appointment_ticket(
        service_code=apt.get('service_code', 'GENERAL'),
        client_name=apt.get('client_name', ''),
        lakad_ref=apt.get('id', ''),
        appointment_id=apt.get('id', ''),
        priority=1,
    )
    updates = {'status': 'confirmed'}
    if result:
        updates['queue_ticket']    = result['ticket_number']
        updates['queue_ticket_id'] = result['ticket_id']
    update_appointment(apt_id, updates)
    ticket_label = result['ticket_number'] if result else 'N/A'
    flash(f"Appointment confirmed. Queue ticket: {ticket_label}", "success")
    return redirect(url_for('admin.admin_appointments'))


@admin_bp.route("/appointments/<apt_id>/cancel", methods=["POST"])
@admin_required
def admin_cancel_appointment(apt_id):
    from services.appointments import cancel_appointment
    cancel_appointment(apt_id)
    flash("Appointment cancelled.", "success")
    return redirect(url_for('admin.admin_appointments'))

    return redirect(url_for("dashboard.index"))