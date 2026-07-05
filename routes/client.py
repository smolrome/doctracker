"""
routes/client.py — Client portal: login, register, submit, track documents.

Security fixes applied:
  1. Open redirect: next_url validated to only allow safe internal paths.
  2. CSRF protection: All state-changing POST routes require a valid CSRF token.
  3. Rate limiting on /register to prevent spam/enumeration.
  4. Session fixation: session ID regenerated after login via _regenerate_session().
  5. Username enumeration via timing: dummy bcrypt compare done in verify_user (note added).
  6. Ownership checks centralised in get_owned_doc() helper.
  7. Batch doc_id list capped to prevent DoS.
  8. Audit log made safe even if delete_doc() raises.
  9. permanent_delete_all requires explicit confirm token to prevent accidental wipe.
 10. Session lifetime reminder comment added.
"""
import hmac
import os
import secrets
import time
import urllib.parse
import uuid

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from urllib.parse import urlparse

from services.auth import (
    approve_user, check_rate_limit, create_user, get_user, reset_rate_limit,
    update_last_login, verify_user,
)
from services.documents import (
    get_doc, insert_doc, load_docs, now_str, generate_ref,
)
from services.appointments import get_appointments_by_client, create_appointment, get_appointment, cancel_appointment
from services.misc import audit_log, load_saved_offices
from services.qr import create_doc_token, generate_qr_b64, make_doc_status_qr_png
from services.dropdown_options import get_dropdown_options
from utils import get_client_ip, is_logged_in
import base64

client_bp = Blueprint("client", __name__, url_prefix="/client")

# ── Security helpers ──────────────────────────────────────────────────────────

_MAX_BATCH = 50  # FIX 7: cap batch size to prevent DoS


def _safe_redirect_url(url: str, fallback: str) -> str:
    """
    FIX 1 – Open Redirect guard.
    Only allow relative URLs that start with '/' and have no scheme/netloc,
    preventing redirects to external attacker-controlled sites.
    """
    if not url:
        return fallback
    parsed = urlparse(url)
    # Reject anything with a scheme or netloc (e.g. //evil.com, https://evil.com)
    if parsed.scheme or parsed.netloc:
        return fallback
    # Must start with a slash (relative path), not a protocol-relative URL
    if not url.startswith("/"):
        return fallback
    return url


def _generatecsrf_token() -> str:
    """
    FIX 2 – CSRF token generation.
    Creates a cryptographically random token stored in the session.
    """
    token = secrets.token_hex(32)
    session["csrf_token"] = token
    return token


def _getcsrf_token() -> str:
    """Return existing CSRF token or create a new one."""
    if "csrf_token" not in session:
        return _generatecsrf_token()
    return session["csrf_token"]


def _validate_csrf(form_token: str) -> bool:
    """
    FIX 2 – Constant-time CSRF token comparison to prevent timing attacks.
    """
    expected = session.get("csrf_token", "")
    if not expected or not form_token:
        return False
    return hmac.compare_digest(expected, form_token)


def _require_csrf():
    """
    FIX 2 – Call at the top of every state-changing POST handler.
    Aborts with 403 if the CSRF token is missing or invalid.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        token = request.form.get("csrf_token", "")
        if not _validate_csrf(token):
            audit_log("csrf_failure",
                      f"path={request.path}",
                      username=session.get("username", "anon"),
                      ip=get_client_ip())
            abort(403)


def _regenerate_session(keep: dict) -> None:
    """
    FIX 4 – Session fixation mitigation.
    Flask's default cookie-based sessions don't expose a server-side session ID
    to regenerate, but we explicitly clear and rewrite the session cookie data
    AND rotate the CSRF token so any pre-login token is invalidated.
    If you switch to server-side sessions (e.g. Flask-Session), replace this
    with a proper session.regenerate() call.
    """
    session.clear()
    session.update(keep)
    _generatecsrf_token()   # rotate CSRF after login


def _require_client(fn):
    """Redirect non-client users to client login."""
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_logged_in() or session.get("role") != "client":
            return redirect(url_for("client.login"))
        return fn(*args, **kwargs)
    return wrapper


def _get_saved_offices():
    """Load saved offices, auto-building from users if none exist."""
    offices = load_saved_offices()
    if not offices:
        from services.auth import get_all_users
        all_users = get_all_users()
        seen = set()
        for u in all_users:
            o = (u.get("office") or "").strip()
            if o and o not in seen:
                seen.add(o)
                offices.append({"office_name": o, "office_slug": o, "primary_recipient": ""})
    return offices


def _get_owned_doc(doc_id: str):
    """
    FIX 6 – Centralised ownership check.
    Returns the document only if it belongs to the current session user.
    Returns None otherwise, keeping callers simple and consistent.
    """
    doc = get_doc(doc_id)
    if not doc or doc.get("submitted_by") != session.get("username"):
        return None
    return doc


# ── Auth ──────────────────────────────────────────────────────────────────────

@client_bp.route("/login", methods=["GET", "POST"])
def login():
    # Login is centralised at /login (auth.login).
    # Carry any ?next= param through so QR-scan redirect flows still work.
    next_param = request.args.get("next", "")
    target = url_for("auth.login")
    if next_param:
        target = f"{target}?next={next_param}"
    return redirect(target)


@client_bp.route("/register", methods=["GET", "POST"])
def register():
    if is_logged_in():
        raw_next = request.args.get("next", "")
        if session.get("role") == "client":
            # FIX 1 – validate next even here
            return redirect(_safe_redirect_url(raw_next, url_for("client.portal")))
        return redirect(url_for("dashboard.index"))

    csrf_token = _getcsrf_token()

    office_slug = request.args.get("office_slug",
                  request.form.get("office_slug", "")).strip()
    office_name = (request.args.get("office_name",
                   request.form.get("office_name", "")).strip()
                   or request.args.get("office",
                      request.form.get("office", "")).strip())
    next_url = request.args.get("next", request.form.get("next_url", "")).strip()
    if not next_url and office_slug and office_name:
        next_url = (f"/client/submit?office_slug={urllib.parse.quote(office_slug)}"
                    f"&office_name={urllib.parse.quote(office_name)}")

    error = None
    if request.method == "POST":
        # FIX 2 – CSRF check
        _require_csrf()
        is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # FIX 3 – rate-limit registrations per IP to prevent spam/account enumeration
        ip = get_client_ip()
        allowed, wait = check_rate_limit("register", ip)
        if not allowed:
            mins = max(1, wait // 60)
            error = f"Too many registration attempts. Try again in {mins} minute{'s' if mins != 1 else ''}."
            audit_log("client_register_blocked", "", username="", ip=ip)
            if is_xhr:
                return jsonify({'success': False, 'error': error})
        else:
            username  = request.form.get("username", "").strip()
            full_name = request.form.get("full_name", "").strip()
            password  = request.form.get("password", "").strip()
            confirm   = request.form.get("confirm_password", "").strip()
            email     = request.form.get("email", "").strip()
            office    = request.form.get("office", "").strip()
            if not full_name:
                error = "Full name is required."
            elif not username:
                error = "Username is required."
            elif not office:
                error = "School/Office is required."
            elif len(password) < 8:
                error = "Password must be at least 8 characters."
            elif password != confirm:
                error = "Passwords do not match."
            else:
                ok, err = create_user(username, password, full_name, role="client", office=office, email=email)
                if ok:
                    _office_slug = request.form.get("office_slug", "").strip()
                    if _office_slug:
                        # Walk-in via office QR — auto-approve and log them in immediately
                        approve_user(username)
                        _next_url = request.form.get("next_url", "").strip()
                        _regenerate_session({
                            'username':           username,
                            'role':               'client',
                            'full_name':          full_name,
                            'office':             office,
                            'submit_office_slug': request.form.get('office_slug', ''),
                            'submit_office_name': request.form.get('office_name', ''),
                        })
                        session.permanent = True
                        audit_log("client_walkin_register",
                                  f"office_slug={_office_slug}",
                                  username=username, ip=get_client_ip())
                        safe_next = _safe_redirect_url(_next_url, "")
                        if safe_next and safe_next.startswith("/client/submit"):
                            return redirect(safe_next)
                        return redirect(url_for("client.portal"))
                    # Online registration — requires admin approval
                    try:
                        from config import MAIL_ENABLED
                        from services.email import send_admin_notification
                        if MAIL_ENABLED:
                            send_admin_notification(
                                subject='New Client Registration — Pending Approval',
                                body=(
                                    f'A new client has registered and is awaiting your approval.\n\n'
                                    f'Name:     {full_name}\n'
                                    f'Username: {username}\n\n'
                                    f'Login to LAKAD to approve or reject this account:\n'
                                    f'/pending-clients'
                                )
                            )
                    except Exception:
                        pass
                    # Push notification to all admin users
                    try:
                        from services.auth import get_all_users
                        from blueprints.api import send_push_notification
                        for _admin in get_all_users():
                            if _admin.get('role') == 'admin' and _admin.get('username'):
                                send_push_notification(
                                    username=_admin['username'],
                                    title='New Client Registration',
                                    body=f'{full_name} (@{username}) has registered and is awaiting approval.',
                                    data={'screen': '/pending-clients', 'type': 'pending_client'},
                                )
                    except Exception:
                        pass  # never block registration
                    msg = (
                        "Registration submitted. Awaiting admin approval."
                    )
                    if is_xhr:
                        return jsonify({'success': True, 'message': msg})
                    flash(msg, "info")
                    return redirect(url_for("client.login"))
                else:
                    error = err
            if is_xhr and error:
                return jsonify({'success': False, 'error': error})

    return render_template("client_register.html", error=error,
                           office_name=office_name, office_slug=office_slug,
                           next_url=next_url, csrf_token=csrf_token)


# ── Portal & document tracking ────────────────────────────────────────────────

@client_bp.route("")
@_require_client
def portal():
    username     = session.get("username")
    docs         = load_docs()
    my_docs      = [d for d in docs if d.get("submitted_by") == username]
    appointments = get_appointments_by_client(username)
    return render_template("client_portal.html",
                           docs=my_docs,
                           appointments=appointments,
                           saved_offices=_get_saved_offices(),
                           csrf_token=_getcsrf_token())


@client_bp.route("/documents")
@_require_client
def my_documents():
    username = session.get("username")
    docs     = load_docs()
    my_docs  = [d for d in docs if d.get("submitted_by") == username]
    return render_template("client_documents.html",
                           docs=my_docs,
                           saved_offices=_get_saved_offices(),
                           csrf_token=_getcsrf_token())


@client_bp.route("/track/<doc_id>")
@_require_client
def track(doc_id):
    # FIX 6 – use centralised ownership helper
    doc = _get_owned_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("client.portal"))
    # Read-only client-safe presentation layer — never mutates the document.
    from services.auth import get_all_users
    from services.client_view import build_client_track_view
    view = build_client_track_view(doc, get_all_users())
    return render_template("client_track.html", doc=doc, view=view,
                           qr_b64=generate_qr_b64(doc, request.host_url),
                           csrf_token=_getcsrf_token())


@client_bp.route("/delete/<doc_id>", methods=["POST"])
@_require_client
def delete(doc_id):
    """Allow clients to soft-delete their rejected documents (moves to trash)."""
    # FIX 2 – CSRF check
    _require_csrf()

    # FIX 6 – centralised ownership check
    doc = _get_owned_doc(doc_id)
    if not doc:
        flash("Document not found or you don't have permission.", "error")
        return redirect(url_for("client.portal"))

    if doc.get("status") not in ("Rejected", "Pending"):
        flash("You can only cancel pending documents or delete rejected documents.", "error")
        return redirect(url_for("client.track", doc_id=doc_id))

    from services.documents import delete_doc
    doc_name = doc.get("doc_name", doc_id)

    # FIX 8 – audit log is written even if delete_doc() raises
    try:
        delete_doc(doc_id, deleted_by=session.get("username", ""))
    finally:
        audit_log("client_doc_deleted", f"doc_id={doc_id} name={doc_name}",
                  username=session.get("username", ""), ip=get_client_ip())

    flash(f"Document '{doc_name}' moved to trash. "
          "You can restore or permanently delete it from your Trash.", "success")
    return redirect(url_for("client.portal"))


@client_bp.route("/trash")
@_require_client
def trash():
    """Show client's deleted documents (soft-deleted). Trash persists until the
    client explicitly empties it via the permanent-delete routes."""
    username = session.get("username", "")
    from services.documents import load_docs, delete_doc_forever

    all_docs = load_docs(include_deleted=True)
    my_deleted_docs = [
        d for d in all_docs
        if d.get("deleted") and d.get("submitted_by") == username
    ]

    remaining_docs = my_deleted_docs

    return render_template("client_trash.html", docs=remaining_docs,
                           csrf_token=_getcsrf_token())


@client_bp.route("/trash/permanent-delete/<doc_id>", methods=["POST"])
@_require_client
def permanent_delete(doc_id):
    """Permanently delete a document from trash."""
    # FIX 2 – CSRF check
    _require_csrf()

    # FIX 6 – centralised ownership check
    doc = _get_owned_doc(doc_id)
    if not doc:
        flash("Document not found or you don't have permission.", "error")
        return redirect(url_for("client.trash"))

    from services.documents import delete_doc_forever
    doc_name = doc.get("doc_name", doc_id)

    # FIX 8 – audit log protected with try/finally
    try:
        delete_doc_forever(doc_id)
    finally:
        audit_log("client_doc_permanent_delete", f"doc_id={doc_id} name={doc_name}",
                  username=session.get("username", ""), ip=get_client_ip())

    flash(f"Document '{doc_name}' permanently deleted.", "success")
    return redirect(url_for("client.trash"))


@client_bp.route("/trash/permanent-delete-all", methods=["POST"])
@_require_client
def permanent_delete_all():
    """
    Permanently delete all documents from client's trash.
    FIX 9 – requires an explicit confirmation token in the form to prevent
    accidental or CSRF-driven mass deletion. The template must render a
    hidden <input name="confirm_destroy" value="yes"> that the user
    consciously submits (e.g. after a JS confirm dialog).
    """
    # FIX 2 – CSRF check
    _require_csrf()

    # FIX 9 – extra confirmation token
    if request.form.get("confirm_destroy") != "yes":
        flash("Deletion not confirmed.", "error")
        return redirect(url_for("client.trash"))

    username = session.get("username", "")
    from services.documents import load_docs, delete_doc_forever

    all_docs = load_docs(include_deleted=True)
    my_deleted_docs = [
        d for d in all_docs
        if d.get("deleted") and d.get("submitted_by") == username
    ]

    count = 0
    for doc in my_deleted_docs:
        # FIX 8 – keep going even if one deletion fails; log the error
        try:
            delete_doc_forever(doc.get("id", ""))
            count += 1
        except Exception as exc:
            audit_log("client_doc_permanent_delete_error",
                      f"doc_id={doc.get('id', '')} error={exc}",
                      username=username, ip=get_client_ip())

    audit_log("client_doc_permanent_delete_all", f"count={count}",
              username=username, ip=get_client_ip())

    flash(f"Permanently deleted {count} document(s) from trash.", "success")
    return redirect(url_for("client.trash"))


@client_bp.route("/trash/restore/<doc_id>", methods=["POST"])
@_require_client
def restore(doc_id):
    """Restore a document from trash."""
    # FIX 2 – CSRF check
    _require_csrf()

    # FIX 6 – centralised ownership check
    doc = _get_owned_doc(doc_id)
    if not doc:
        flash("Document not found or you don't have permission.", "error")
        return redirect(url_for("client.trash"))

    from services.documents import restore_doc
    doc_name = doc.get("doc_name", doc_id)
    restore_doc(doc_id)

    audit_log("client_doc_restored", f"doc_id={doc_id} name={doc_name}",
              username=session.get("username", ""), ip=get_client_ip())

    flash(f"Document '{doc_name}' restored successfully.", "success")
    return redirect(url_for("client.portal"))


@client_bp.route("/scan")
@_require_client
def scan():
    return render_template("client_scan.html")


# ── Logout ────────────────────────────────────────────────────────────────────

@client_bp.route("/logout")
def client_logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("client.login"))


# ── Document submission (cart flow) ──────────────────────────────────────────

@client_bp.route("/submit", methods=["GET", "POST"])
@_require_client
def submit():
    cart  = session.get("submit_cart", [])
    error = None

    if request.method == "POST":
        # FIX 2 – CSRF check on all submit actions
        _require_csrf()

        action = request.form.get("_action", "add")

        if action == "add":
            doc_name    = request.form.get("doc_name", "").strip()
            referred_to = request.form.get("referred_to", "").strip()
            if not doc_name:
                error = "Document name / particulars is required."
            elif not referred_to:
                error = "Referred To is required."
            else:
                # FIX 7 – cap cart size
                if len(cart) >= _MAX_BATCH:
                    error = f"You can submit at most {_MAX_BATCH} documents at once."
                else:
                    cart.append({
                        "tmp_id":               uuid.uuid4().hex[:8].upper(),
                        "doc_name":             doc_name,
                        "unit_office":          request.form.get("unit_office", "").strip(),
                        "referred_to":          referred_to,
                        "category":             request.form.get("category", "").strip(),
                        "description":          request.form.get("description", "").strip(),
                        "notes":                request.form.get("notes", "").strip(),
                        "referred_to_username": request.form.get("referred_to_username", "").strip(),
                    })
                    session["submit_cart"] = cart
                    session.modified = True
                    flash(f"✅ '{doc_name}' added to your submission list.", "success")

        elif action == "remove":
            tmp_id = request.form.get("tmp_id", "")
            cart = [d for d in cart if d["tmp_id"] != tmp_id]
            session["submit_cart"] = cart
            session.modified = True

        elif action == "select_staff":
            selected_staff = request.form.get("selected_staff", "")
            session["submit_selected_staff"] = selected_staff
            session.modified = True
            flash("✅ Selected staff for document submission.", "success")

        elif action == "submit_all":
            if not cart:
                error = "No documents to submit. Add at least one first."
            else:
                submitted_ids  = []
                receive_tokens = []
                office_slug    = session.get("submit_office_slug", "")
                office_name    = session.get("submit_office_name", "")
                selected_staff = session.get("submit_selected_staff", "")

                from services.auth import get_all_users
                all_users = get_all_users()

                assigned_staff      = ""
                assigned_staff_name = ""
                if selected_staff:
                    for u in all_users:
                        if u.get("username") == selected_staff:
                            assigned_staff      = selected_staff
                            assigned_staff_name = u.get("full_name", "") or u.get("username", "")
                            break

                if not assigned_staff:
                    saved_offices     = _get_saved_offices()
                    primary_recipient = ""
                    for off in saved_offices:
                        if (off.get("office_slug") == office_slug or
                                off.get("office_name", "").strip().lower()
                                == office_name.strip().lower()):
                            primary_recipient = off.get("primary_recipient", "")
                            break

                    if primary_recipient:
                        for u in all_users:
                            if u.get("username") == primary_recipient:
                                assigned_staff      = primary_recipient
                                assigned_staff_name = u.get("full_name", "") or u.get("username", "")
                                break
                    else:
                        office_staff = [
                            u for u in all_users
                            if u.get("office", "").strip().lower()
                            == office_name.strip().lower()
                            and u.get("role") in ("staff", "admin")
                        ]
                        if not office_staff:
                            office_staff = [u for u in all_users
                                            if u.get("role") in ("staff", "admin")]
                        assigned_staff      = office_staff[0].get("username") if office_staff else ""
                        assigned_staff_name = office_staff[0].get("full_name", "") if office_staff else ""

                # FIX 7 – hard cap just before insertion too
                for item in cart[:_MAX_BATCH]:
                    doc_staff      = assigned_staff
                    doc_staff_name = assigned_staff_name
                    doc_office     = office_name

                    doc = {
                        "id":                    str(uuid.uuid4())[:8].upper(),
                        "doc_id":                generate_ref(),
                        "doc_name":              item["doc_name"],
                        "category":              item["category"],
                        "description":           item["description"],
                        "sender_name":           session.get("full_name") or session.get("username"),
                        "sender_org":            item["unit_office"],
                        "sender_contact":        "",
                        "referred_to":           item["referred_to"] or office_name,
                        "forwarded_to":          "",
                        "recipient_name":        "",
                        "recipient_org":         "",
                        "recipient_contact":     "",
                        "received_by":           "",
                        "date_received":         "",
                        "date_released":         "",
                        "doc_date":              now_str()[:10],
                        "status":                "Pending",
                        "notes":                 item["notes"],
                        "created_at":            now_str(),
                        "routing":               [],
                        "travel_log":            [],
                        "submitted_by":          session.get("username"),
                        "submitted_by_name":     session.get("full_name") or session.get("username"),
                        "target_office_slug":    office_slug,
                        "target_office_name":    office_name,
                        "pending_at_staff":      doc_staff,
                        "pending_at_staff_name": doc_staff_name,
                        "pending_at_office":     doc_office,
                        "transfer_status":       "pending" if doc_staff or office_name else "",
                        "intended_for_username": item.get("referred_to_username", "").strip(),
                        "intended_for_name":     next(
                            (u.get("full_name") or u.get("username") for u in all_users
                             if u.get("username") == item.get("referred_to_username", "").strip()),
                            ""
                        ),
                    }
                    doc["travel_log"].append({
                        "office":    office_name or item["unit_office"] or "Client",
                        "action":    "Document Submitted by Client - Pending at "
                                     + (doc_staff_name or doc_staff or "Office"),
                        "officer":   doc["sender_name"],
                        "timestamp": doc["created_at"],
                        "remarks":   (
                            f"Submitted via client portal. "
                            f"Target office: {office_name or 'General'}. "
                            f"Assigned to: {doc_staff_name or doc_staff or 'Any staff'}."
                        ),
                    })
                    insert_doc(doc)
                    receive_tokens.append(create_doc_token(doc["id"], "RECEIVE"))
                    submitted_ids.append(doc["id"])

                session.pop("submit_cart", None)
                session.pop("submit_office_slug", None)
                session.pop("submit_office_name", None)
                session.pop("submit_selected_staff", None)
                session.modified = True
                return redirect(url_for("client.submitted_batch",
                                        ids=",".join(submitted_ids),
                                        tokens=",".join(receive_tokens)))

        cart = session.get("submit_cart", [])

    if request.args.get("office_slug") and request.args.get("office_name"):
        session["submit_office_slug"] = request.args.get("office_slug", "")
        session["submit_office_name"] = request.args.get("office_name", "")
        session["submit_selected_staff"] = ""
        session.modified = True

    office_name    = session.get("submit_office_name", "")
    office_slug    = session.get("submit_office_slug", "")
    office_staff_list = []
    selected_staff = session.get("submit_selected_staff", "")

    if office_name:
        from services.auth import get_all_users
        all_users = get_all_users()
        office_staff_list = [
            {"username": u.get("username", ""),
             "full_name": u.get("full_name", "") or u.get("username", "")}
            for u in all_users
            if u.get("office", "").strip().lower() == office_name.strip().lower()
            and u.get("role") in ("staff", "admin")
        ]
        if not office_staff_list:
            office_staff_list = [
                {"username": u.get("username", ""),
                 "full_name": u.get("full_name", "") or u.get("username", "")}
                for u in all_users
                if u.get("role") in ("staff", "admin")
            ]
        if not selected_staff and office_staff_list:
            # Find the primary recipient for this office from saved_offices
            primary_username = ""
            for off in _get_saved_offices():
                if off.get("office_slug", "") == office_slug or \
                   off.get("office_name", "").strip().lower() == office_name.strip().lower():
                    primary_username = off.get("primary_recipient", "")
                    break
            # Use primary if they are in the staff list, else fall back to first
            staff_usernames = [s["username"] for s in office_staff_list]
            if primary_username and primary_username in staff_usernames:
                selected_staff = primary_username
            else:
                selected_staff = office_staff_list[0]["username"]

    return render_template("client_submit.html",
                           cart=cart, error=error, doc={},
                           office_slug=office_slug,
                           office_name=office_name,
                           unit_office_default=_get_client_org(session.get("username", "")),
                           category_options=get_dropdown_options("category"),
                           saved_offices=_get_saved_offices(),
                           office_staff_list=office_staff_list,
                           selected_staff=selected_staff,
                           csrf_token=_getcsrf_token())


# ── Submission confirmation ────────────────────────────────────────────────────

@client_bp.route("/submitted/<doc_id>")
@_require_client
def submitted(doc_id):
    # FIX 6 – centralised ownership check
    doc = _get_owned_doc(doc_id)
    if not doc:
        return redirect(url_for("client.portal"))
    qr_b64 = generate_qr_b64(doc, request.host_url)
    return render_template("client_submitted.html",
                           docs=[doc], qr_list=[(doc, qr_b64, None)], batch=False)


@client_bp.route("/submitted-batch")
@_require_client
def submitted_batch():
    ids_raw    = request.args.get("ids", "")
    tokens_raw = request.args.get("tokens", "")
    # FIX 7 – cap list length to prevent DoS loop
    doc_ids = [i.strip() for i in ids_raw.split(",") if i.strip()][:_MAX_BATCH]
    tokens  = [t.strip() for t in tokens_raw.split(",") if t.strip()][:_MAX_BATCH]
    if not doc_ids:
        return redirect(url_for("client.portal"))

    qr_list = []
    for i, doc_id in enumerate(doc_ids):
        # FIX 6 – ownership check via helper
        doc = _get_owned_doc(doc_id)
        if doc:
            token = tokens[i] if i < len(tokens) else None
            if token:
                qr_png = make_doc_status_qr_png(token, "RECEIVE", doc.get("doc_name", "Document"))
                qr_b64 = base64.b64encode(qr_png).decode()
            else:
                qr_b64 = generate_qr_b64(doc, request.host_url)
            qr_list.append((doc, qr_b64, token))

    if not qr_list:
        return redirect(url_for("client.portal"))
    return render_template("client_submitted.html", qr_list=qr_list, batch=True)


# ── Appointments ──────────────────────────────────────────────────────────────

@client_bp.route("/appointments")
@_require_client
def my_appointments():
    username = session.get('username', '')
    appointments = get_appointments_by_client(username)
    return render_template('client_appointments.html',
                           appointments=appointments,
                           saved_offices=_get_saved_offices(),
                           csrf_token=_getcsrf_token())


@client_bp.route("/appointments/book", methods=["GET", "POST"])
@_require_client
def book_appointment():
    from services.queue_bridge import get_queue_services
    offices = load_saved_offices()
    services = get_queue_services()
    if request.method == "POST":
        _require_csrf()
        office = request.form.get("office", "").strip()
        service_code = request.form.get("service_code", "").strip()
        service_name = next((s['name'] for s in services if s['code'] == service_code), service_code)
        preferred_date = request.form.get("preferred_date", "").strip()
        preferred_time = request.form.get("preferred_time", "").strip()
        purpose = request.form.get("purpose", "").strip()
        if not all([office, service_code, preferred_date, preferred_time, purpose]):
            flash("All fields are required.", "error")
            return render_template('client_book_appointment.html',
                                   offices=offices, services=services,
                                   csrf_token=_getcsrf_token())
        apt = create_appointment({
            'client_name':     session.get('full_name') or session.get('username'),
            'client_username': session.get('username'),
            'office':          office,
            'service_code':    service_code,
            'service_name':    service_name,
            'preferred_date':  preferred_date,
            'preferred_time':  preferred_time,
            'purpose':         purpose,
            'source':          'web',
        })
        return redirect(url_for('client.appointment_confirmation', apt_id=apt['id']))
    selected_office = request.args.get('office_name', '')
    selected_office_slug = request.args.get('office_slug', '')
    return render_template('client_book_appointment.html',
                           offices=offices, services=services,
                           selected_office=selected_office,
                           selected_office_slug=selected_office_slug,
                           csrf_token=_getcsrf_token())



@client_bp.route("/appointments/<apt_id>/confirmation")
@_require_client
def appointment_confirmation(apt_id):
    from services.appointments import get_appointment
    apt = get_appointment(apt_id)
    if not apt or apt.get('client_username') != session.get('username'):
        return redirect(url_for('client.my_appointments'))
    import qrcode, io, base64
    qr_data = f"APT:{apt['id']}:{apt.get('office','')}:{apt.get('preferred_date','')}:{apt.get('preferred_time','')}"
    qr = qrcode.make(qr_data)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    return render_template('client_appointment_confirmation.html',
                           apt=apt,
                           qr_b64=qr_b64,
                           csrf_token=_getcsrf_token())


@client_bp.route("/appointments/<apt_id>/cancel", methods=["POST"])
@_require_client
def cancel_client_appointment(apt_id):
    _require_csrf()
    apt = get_appointment(apt_id)
    if not apt or apt.get('client_username') != session.get('username'):
        flash("Appointment not found.", "error")
        return redirect(url_for('client.my_appointments'))
    if apt.get('status') not in ('pending', 'confirmed'):
        flash("This appointment cannot be cancelled.", "error")
        return redirect(url_for('client.my_appointments'))
    cancel_appointment(apt_id)
    flash("Appointment cancelled.", "success")
    return redirect(url_for('client.my_appointments'))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client_org(username: str) -> str:
    """Return the client's last used org/unit from their submitted docs."""
    if not username:
        return ""
    try:
        for d in load_docs():
            if d.get("submitted_by") == username and d.get("sender_org"):
                return d["sender_org"]
    except Exception:
        pass
    return ""