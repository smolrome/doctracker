"""
routes/client.py — Client portal: login, register, submit, track documents.
"""
import time
import urllib.parse
import uuid

from flask import (Blueprint, flash, redirect, render_template,
                   request, session, url_for)

from services.auth import (
    check_rate_limit, create_user, reset_rate_limit,
    update_last_login, verify_user,
)
from services.documents import (
    get_doc, insert_doc, load_docs, now_str, generate_ref,
)
from services.misc import audit_log, load_saved_offices
from services.qr import create_doc_token, generate_qr_b64, make_doc_status_qr_png
from services.dropdown_options import get_dropdown_options
from utils import get_client_ip, is_logged_in
import base64

client_bp = Blueprint("client", __name__, url_prefix="/client")


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
            o = (u.get('office') or '').strip()
            if o and o not in seen:
                seen.add(o)
                offices.append({'office_name': o, 'office_slug': o, 'primary_recipient': ''})
    return offices


# ── Auth ──────────────────────────────────────────────────────────────────────

@client_bp.route("/login", methods=["GET", "POST"])
def login():
    if is_logged_in():
        role = session.get("role")
        return redirect(url_for("client.portal") if role == "client"
                        else url_for("dashboard.index"))
    error = None
    lockout_remaining = 0
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        ip = get_client_ip()
        allowed, wait = check_rate_limit("login", f"{ip}:{username.lower()}")
        if not allowed:
            mins = max(1, wait // 60)
            error = f"Too many failed attempts. Try again in {mins} minute{'s' if mins != 1 else ''}."
            lockout_remaining = wait
            audit_log("client_login_blocked", f"username={username}",
                      username=username, ip=ip)
        else:
            full_name, role, office = verify_user(username, password)
            if full_name:
                reset_rate_limit("login", f"{ip}:{username.lower()}")
                session.clear()
                session.update({
                    "logged_in":   True,
                    "username":    username.lower().strip(),
                    "full_name":   full_name,
                    "role":        role,
                    "office":      office,
                    "last_active": time.time(),
                })
                session.permanent = True
                update_last_login(username.lower().strip())
                audit_log("client_login_ok", f"role={role}",
                          username=username, ip=ip)
                next_url = (request.form.get("next_url", "").strip()
                            or request.args.get("next", "").strip())
                if role == "client":
                    return redirect(next_url or url_for("client.portal"))
                return redirect(url_for("dashboard.index"))
            else:
                error = "Invalid username or password."
                audit_log("client_login_fail", f"username={username}",
                          username=username, ip=ip)

    return render_template("client_login.html", error=error,
                           lockout_remaining=lockout_remaining,
                           office_slug=request.args.get("office_slug", ""),
                           office_name=request.args.get("office_name", ""),
                           next_url=request.args.get("next", ""))


@client_bp.route("/register", methods=["GET", "POST"])
def register():
    if is_logged_in():
        next_url = request.args.get("next", "")
        if session.get("role") == "client":
            return redirect(next_url or url_for("client.portal"))
        return redirect(url_for("dashboard.index"))

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
        username  = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password  = request.form.get("password", "").strip()
        confirm   = request.form.get("confirm_password", "").strip()
        if not full_name:
            error = "Full name is required."
        elif not username:
            error = "Username is required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            ok, err = create_user(username, password, full_name, role="client")
            if ok:
                flash("Registration successful! Your account is pending approval by the administrator. You will be able to login once your account is approved.", "info")
                return redirect(url_for("client.login"))
            else:
                error = err

    return render_template("client_register.html", error=error,
                           office_name=office_name, office_slug=office_slug,
                           next_url=next_url)


# ── Portal & document tracking ────────────────────────────────────────────────

@client_bp.route("")
@_require_client
def portal():
    username = session.get("username")
    docs     = load_docs()
    my_docs  = [d for d in docs if d.get("submitted_by") == username]
    return render_template("client_portal.html", docs=my_docs,
                           saved_offices=_get_saved_offices())


@client_bp.route("/track/<doc_id>")
@_require_client
def track(doc_id):
    doc = get_doc(doc_id)
    if not doc or doc.get("submitted_by") != session.get("username"):
        flash("Document not found.", "error")
        return redirect(url_for("client.portal"))
    return render_template("client_track.html", doc=doc,
                           qr_b64=generate_qr_b64(doc, request.host_url))


@client_bp.route("/delete/<doc_id>", methods=["POST"])
@_require_client
def delete(doc_id):
    """Allow clients to soft-delete their rejected documents (moves to trash)."""
    doc = get_doc(doc_id)
    if not doc or doc.get("submitted_by") != session.get("username"):
        flash("Document not found or you don't have permission.", "error")
        return redirect(url_for("client.portal"))
    
    # Only allow deletion if document is rejected
    if doc.get("status") != "Rejected":
        flash("You can only delete rejected documents.", "error")
        return redirect(url_for("client.track", doc_id=doc_id))
    
    from services.documents import delete_doc
    doc_name = doc.get("doc_name", doc_id)
    delete_doc(doc_id, deleted_by=session.get("username", ""))
    
    from services.misc import audit_log
    audit_log("client_doc_deleted", f"doc_id={doc_id} name={doc_name}",
              username=session.get("username", ""), ip=get_client_ip())
    
    flash(f"Document '{doc_name}' moved to trash. You can restore or permanently delete it from your Trash.", "success")
    return redirect(url_for("client.portal"))


@client_bp.route("/trash")
@_require_client
def trash():
    """Show client's deleted documents (soft-deleted), auto-delete if older than 30 days."""
    username = session.get("username", "")
    from services.documents import load_docs, delete_doc_forever
    from datetime import datetime, timedelta
    
    all_docs = load_docs(include_deleted=True)
    # Filter to only show documents submitted by this client that are deleted
    my_deleted_docs = [
        d for d in all_docs 
        if d.get("deleted") and d.get("submitted_by") == username
    ]
    
    # Auto-delete documents older than 30 days
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    remaining_docs = []
    for doc in my_deleted_docs:
        deleted_at = doc.get("deleted_at", "")[:10] if doc.get("deleted_at") else ""
        if deleted_at and deleted_at < thirty_days_ago:
            # Permanently delete documents older than 30 days
            delete_doc_forever(doc.get("id", ""))
        else:
            remaining_docs.append(doc)
    
    return render_template("client_trash.html", docs=remaining_docs)


@client_bp.route("/trash/permanent-delete/<doc_id>", methods=["POST"])
@_require_client
def permanent_delete(doc_id):
    """Permanently delete a document from trash."""
    doc = get_doc(doc_id)
    if not doc or doc.get("submitted_by") != session.get("username"):
        flash("Document not found or you don't have permission.", "error")
        return redirect(url_for("client.trash"))
    
    from services.documents import delete_doc_forever
    doc_name = doc.get("doc_name", doc_id)
    delete_doc_forever(doc_id)
    
    from services.misc import audit_log
    audit_log("client_doc_permanent_delete", f"doc_id={doc_id} name={doc_name}",
              username=session.get("username", ""), ip=get_client_ip())
    
    flash(f"Document '{doc_name}' permanently deleted.", "success")
    return redirect(url_for("client.trash"))


@client_bp.route("/trash/permanent-delete-all", methods=["POST"])
@_require_client
def permanent_delete_all():
    """Permanently delete all documents from client's trash."""
    username = session.get("username", "")
    from services.documents import load_docs, delete_doc_forever
    all_docs = load_docs(include_deleted=True)
    my_deleted_docs = [
        d for d in all_docs 
        if d.get("deleted") and d.get("submitted_by") == username
    ]
    
    count = 0
    for doc in my_deleted_docs:
        delete_doc_forever(doc.get("id", ""))
        count += 1
    
    from services.misc import audit_log
    audit_log("client_doc_permanent_delete_all", f"count={count}",
              username=username, ip=get_client_ip())
    
    flash(f"Permanently deleted {count} document(s) from trash.", "success")
    return redirect(url_for("client.trash"))


@client_bp.route("/trash/restore/<doc_id>", methods=["POST"])
@_require_client
def restore(doc_id):
    """Restore a document from trash."""
    doc = get_doc(doc_id)
    if not doc or doc.get("submitted_by") != session.get("username"):
        flash("Document not found or you don't have permission.", "error")
        return redirect(url_for("client.trash"))
    
    from services.documents import restore_doc
    doc_name = doc.get("doc_name", doc_id)
    restore_doc(doc_id)
    
    from services.misc import audit_log
    audit_log("client_doc_restored", f"doc_id={doc_id} name={doc_name}",
              username=session.get("username", ""), ip=get_client_ip())
    
    flash(f"Document '{doc_name}' restored successfully.", "success")
    return redirect(url_for("client.portal"))


@client_bp.route("/scan")
@_require_client
def scan():
    return render_template("client_scan.html")


# ── Document submission (cart flow) ──────────────────────────────────────────

@client_bp.route("/submit", methods=["GET", "POST"])
@_require_client
def submit():
    cart  = session.get("submit_cart", [])
    error = None

    if request.method == "POST":
        action = request.form.get("_action", "add")

        if action == "add":
            doc_name    = request.form.get("doc_name", "").strip()
            referred_to = request.form.get("referred_to", "").strip()
            if not doc_name:
                error = "Document name / particulars is required."
            elif not referred_to:
                error = "Referred To is required."
            else:
                cart.append({
                    "tmp_id":      uuid.uuid4().hex[:8].upper(),
                    "doc_name":    doc_name,
                    "unit_office": request.form.get("unit_office", "").strip(),
                    "referred_to": referred_to,
                    "category":    request.form.get("category", "").strip(),
                    "description": request.form.get("description", "").strip(),
                    "notes":       request.form.get("notes", "").strip(),
                })
                session["submit_cart"] = cart
                session.modified = True
                flash(f"✅ '{doc_name}' added to your submission list.", "success")

        elif action == "remove":
            tmp_id = request.form.get("tmp_id", "")
            cart = [d for d in cart if d["tmp_id"] != tmp_id]
            session["submit_cart"] = cart
            session.modified = True

        elif action == "submit_all":
            if not cart:
                error = "No documents to submit. Add at least one first."
            else:
                submitted_ids  = []
                receive_tokens = []
                office_slug    = session.get("submit_office_slug", "")
                office_name    = session.get("submit_office_name", "")

                from services.auth import get_all_users
                all_users = get_all_users()

                saved_offices = _get_saved_offices()
                primary_recipient = ""
                for off in saved_offices:
                    if (off.get("office_slug") == office_slug or
                            off.get("office_name", "").strip().lower() == office_name.strip().lower()):
                        primary_recipient = off.get("primary_recipient", "")
                        break

                if primary_recipient:
                    assigned_staff = ""
                    assigned_staff_name = ""
                    for u in all_users:
                        if u.get("username") == primary_recipient:
                            assigned_staff = primary_recipient
                            assigned_staff_name = u.get("full_name", "") or u.get("username", "")
                            break
                else:
                    # Try to find staff in the same office
                    office_staff = [u for u in all_users if u.get("office", "").strip().lower() == office_name.strip().lower() and u.get("role") in ("staff", "admin")]
                    if not office_staff:
                        # If still no staff, get any staff/admin
                        office_staff = [u for u in all_users if u.get("role") in ("staff", "admin")]
                    assigned_staff = office_staff[0].get("username") if office_staff else ""
                    assigned_staff_name = office_staff[0].get("full_name", "") if office_staff else ""

                for item in cart:
                    doc = {
                        "id":                  str(uuid.uuid4())[:8].upper(),
                        "doc_id":              generate_ref(),
                        "doc_name":            item["doc_name"],
                        "category":            item["category"],
                        "description":         item["description"],
                        "sender_name":         session.get("full_name") or session.get("username"),
                        "sender_org":          item["unit_office"],
                        "sender_contact":      "",
                        "referred_to":         item["referred_to"] or office_name,
                        "forwarded_to":        "",
                        "recipient_name":      "", "recipient_org": "", "recipient_contact": "",
                        "received_by":         "",
                        "date_received":       "",
                        "date_released":       "",
                        "doc_date":            now_str()[:10],
                        "status":              "Pending",
                        "notes":               item["notes"],
                        "created_at":          now_str(),
                        "routing":             [],
                        "travel_log":          [],
                        "submitted_by":        session.get("username"),
                        "submitted_by_name":   session.get("full_name") or session.get("username"),
                        "target_office_slug":  office_slug,
                        "target_office_name":  office_name,
                        "pending_at_staff":    assigned_staff,
                        "pending_at_staff_name": assigned_staff_name,
                        "pending_at_office":   office_name,
                        # Always set to "pending" so any staff in the office can see it
                        "transfer_status":     "pending" if assigned_staff or office_name else "",
                    }
                    doc["travel_log"].append({
                        "office":    office_name or item["unit_office"] or "Client",
                        "action":    "Document Submitted by Client - Pending at " + (assigned_staff_name or assigned_staff or "Office"),
                        "officer":   doc["sender_name"],
                        "timestamp": doc["created_at"],
                        "remarks":   f"Submitted via client portal. Target office: {office_name or 'General'}. Assigned to: {assigned_staff_name or assigned_staff or 'Any staff'}.",
                    })
                    insert_doc(doc)
                    receive_tokens.append(create_doc_token(doc["id"], "RECEIVE"))
                    submitted_ids.append(doc["id"])

                session.pop("submit_cart", None)
                session.pop("submit_office_slug", None)
                session.pop("submit_office_name", None)
                session.modified = True
                return redirect(url_for("client.submitted_batch",
                                        ids=",".join(submitted_ids),
                                        tokens=",".join(receive_tokens)))

        cart = session.get("submit_cart", [])

    if request.args.get("office_slug") and request.args.get("office_name"):
        session["submit_office_slug"] = request.args["office_slug"]
        session["submit_office_name"] = request.args["office_name"]
        session.modified = True

    office_name = session.get("submit_office_name", "")
    office_slug = session.get("submit_office_slug", "")
    assigned_staff = ""
    assigned_staff_name = ""
    if office_name:
        from services.auth import get_all_users
        all_users = get_all_users()

        saved_offices = _get_saved_offices()
        primary_recipient = ""
        for off in saved_offices:
            if (off.get("office_slug") == office_slug or
                    off.get("office_name", "").strip().lower() == office_name.strip().lower()):
                primary_recipient = off.get("primary_recipient", "")
                break

        if primary_recipient:
            for u in all_users:
                if u.get("username") == primary_recipient:
                    assigned_staff = primary_recipient
                    assigned_staff_name = u.get("full_name", "") or u.get("username", "")
                    break
        else:
            office_staff = [u for u in all_users if u.get("office", "").strip().lower() == office_name.strip().lower() and u.get("role") in ("staff", "admin")]
            if not office_staff:
                office_staff = [u for u in all_users if u.get("role") in ("staff", "admin")]
            if office_staff:
                assigned_staff = office_staff[0].get("username", "")
                assigned_staff_name = office_staff[0].get("full_name", "")

    return render_template("client_submit.html",
                           cart=cart, error=error, doc={},
                           office_slug=office_slug,
                           office_name=office_name,
                           unit_office_default=_get_client_org(session.get("username", "")),
                           category_options=get_dropdown_options("category"),
                           saved_offices=_get_saved_offices(),
                           assigned_staff=assigned_staff,
                           assigned_staff_name=assigned_staff_name)


# ── Submission confirmation ────────────────────────────────────────────────────

@client_bp.route("/submitted/<doc_id>")
@_require_client
def submitted(doc_id):
    doc = get_doc(doc_id)
    if not doc or doc.get("submitted_by") != session.get("username"):
        return redirect(url_for("client.portal"))
    qr_b64 = generate_qr_b64(doc, request.host_url)
    return render_template("client_submitted.html",
                           docs=[doc], qr_list=[(doc, qr_b64, None)], batch=False)


@client_bp.route("/submitted-batch")
@_require_client
def submitted_batch():
    ids_raw    = request.args.get("ids", "")
    tokens_raw = request.args.get("tokens", "")
    doc_ids    = [i.strip() for i in ids_raw.split(",") if i.strip()]
    tokens     = [t.strip() for t in tokens_raw.split(",") if t.strip()]
    if not doc_ids:
        return redirect(url_for("client.portal"))

    qr_list = []
    for i, doc_id in enumerate(doc_ids):
        doc = get_doc(doc_id)
        if doc and doc.get("submitted_by") == session.get("username"):
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