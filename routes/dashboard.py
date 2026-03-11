"""
routes/dashboard.py — Main staff/admin document dashboard and document CRUD.
"""
import uuid

from flask import (Blueprint, flash, jsonify, redirect,
                   render_template, request, send_file, session, url_for)
from io import BytesIO
import re

from services.documents import (
    delete_doc, get_doc, get_stats, insert_doc,
    load_docs, now_str, generate_ref, restore_doc, save_doc,
)
from services.auth import get_all_users
from services.misc import audit_log, load_saved_offices
from services.qr import generate_qr_b64, make_qr_png
from services.dropdown_options import get_dropdown_options
from utils import admin_required, get_client_ip, is_logged_in, login_required
from config import STATUS_OPTIONS
from services.dropdown_options import get_dropdown_options

dashboard_bp = Blueprint("dashboard", __name__)


def _get_staff_by_office(current_username: str = ""):
    """Get staff members grouped by office for transfer modal."""
    all_users = get_all_users()
    staff = [u for u in all_users if u.get("role") != "client" and u.get("username") != current_username]
    offices = {}

    # Ensure current user's office is always in the dict even if they're the only one there
    for u in all_users:
        if u.get("username") == current_username:
            office = u.get("office", "") or "No Office"
            if office not in offices:
                offices[office] = []
            break

    for s in staff:
        office = s.get("office", "") or "No Office"
        if office not in offices:
            offices[office] = []
        offices[office].append(s)

    return offices


def _get_user_office(username: str) -> str:
    """Get the office of a specific user from the database."""
    if not username:
        return ""
    all_users = get_all_users()
    for u in all_users:
        if u.get("username") == username:
            return u.get("office", "") or ""
    return ""


def _build_offices_dict_and_sorted(current_username: str, current_office: str):
    """
    Build offices_dict (staff grouped by office) and sorted_offices
    (office names sorted: current_office first, No Office last).
    """
    offices_dict = _get_staff_by_office(current_username)
    sorted_offices = sorted(
        offices_dict.keys(),
        key=lambda x: (x == "No Office", x != current_office, x.lower())
    )
    return offices_dict, sorted_offices


@dashboard_bp.route("/")
def index():
    role = session.get("role", "")
    if role not in ("staff", "admin"):
        return render_template("landing.html", saved_offices=load_saved_offices())

    current_username = session.get("username", "")
    user_role = session.get("role", "")

    docs = load_docs()
    if user_role != "admin":
        # Exclude documents that are pending acceptance for this user
        # (they should only appear in "Documents to Receive" modal until accepted)
        docs = [d for d in docs if d.get("logged_by") == current_username 
                and not (d.get("transfer_status") == "pending" and d.get("pending_at_staff") == current_username)]

    search           = request.args.get("search", "").lower()
    filter_status    = request.args.get("status", "All")
    filter_type      = request.args.get("type", "All")
    filter_date      = request.args.get("date", "").strip()
    filter_time_from = request.args.get("time_from", "").strip()
    filter_time_to   = request.args.get("time_to", "").strip()

    filtered = docs

    if search:
        def _matches(d, q):
            haystack = " ".join([
                d.get("doc_name",    "") or "",
                d.get("doc_id",      "") or "",
                d.get("sender_name", "") or "",
                d.get("sender_org",  "") or "",
                d.get("referred_to", "") or "",
                d.get("category",    "") or "",
                d.get("source",      "") or "",
                d.get("notes",       "") or "",
            ]).lower()
            return q in haystack
        filtered = [d for d in filtered if _matches(d, search)]

    if filter_status != "All":
        filtered = [d for d in filtered if d.get("status") == filter_status]

    if filter_type == "Received":
        filtered = [d for d in filtered if d.get("date_received") and not d.get("date_released")]
    elif filter_type == "Released":
        filtered = [d for d in filtered if d.get("date_released")]

    if filter_date:
        def _doc_date(d):
            return (d.get("date_received") or d.get("created_at", "") or "")[:10]
        filtered = [d for d in filtered if _doc_date(d) == filter_date]

    if filter_time_from or filter_time_to:
        def _doc_time(d):
            return (d.get("created_at", "") or "")[11:16]
        if filter_time_from:
            filtered = [d for d in filtered if _doc_time(d) >= filter_time_from]
        if filter_time_to:
            filtered = [d for d in filtered if _doc_time(d) <= filter_time_to]

    try:
        per_page = int(request.args.get("per_page", 25))
    except ValueError:
        per_page = 25
    if per_page not in (10, 25, 50, 100):
        per_page = 25
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    total       = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page        = min(page, total_pages)
    start       = (page - 1) * per_page
    paginated   = filtered[start : start + per_page]

    # Transfer modal data — resolve office of currently logged-in user (for internal transfers)
    # Using EXACT same logic as transfer_doc route
    all_users = get_all_users()
    logged_in_user = session.get("username", "")
    raw_office = ""
    for u in all_users:
        if u.get("username") == logged_in_user:
            raw_office = u.get("office", "") or ""
            break
    current_office = raw_office if raw_office else "No Office"
    
    offices_dict, sorted_offices = _build_offices_dict_and_sorted(logged_in_user, current_office)

    return render_template("index.html",
        docs=paginated, stats=get_stats(docs),
        search=search, filter_status=filter_status,
        filter_type=filter_type, filter_date=filter_date,
        filter_time_from=filter_time_from, filter_time_to=filter_time_to,
        status_options=["All"] + get_dropdown_options("status"),
        saved_offices=load_saved_offices(),
        page=page, total_pages=total_pages,
        per_page=per_page, total=total,
        staff_by_office=offices_dict,
        current_office=current_office,
        offices_dict=offices_dict,
        sorted_offices=sorted_offices)


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") not in ("staff", "admin"):
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("dashboard.index"))


# ── Add document ──────────────────────────────────────────────────────────────

@dashboard_bp.route("/add", methods=["GET", "POST"])
@login_required
def add():
    cart  = session.get("staff_cart", [])
    error = None

    if request.method == "POST":
        action = request.form.get("_action", "add")

        if action == "add":
            doc_name = request.form.get("doc_name", "").strip()
            if not doc_name:
                error = "Content / Particulars is required."
            else:
                cart.append({
                    "tmp_id":      uuid.uuid4().hex[:8].upper(),
                    "doc_name":    doc_name,
                    "sender_org":  request.form.get("sender_org", "").strip(),
                    "sender_name": request.form.get("sender_name", "").strip(),
                    "referred_to": request.form.get("referred_to", "").strip(),
                    "category":    request.form.get("category", "").strip(),
                    "description": request.form.get("description", "").strip(),
                    "notes":       request.form.get("notes", "").strip(),
                })
                session["staff_cart"] = cart
                session.modified = True
                flash(f"✅ '{doc_name}' added to the log list.", "success")

        elif action == "remove":
            tmp_id = request.form.get("tmp_id", "")
            cart = [d for d in cart if d["tmp_id"] != tmp_id]
            session["staff_cart"] = cart
            session.modified = True

        elif action == "edit":
            tmp_id = request.form.get("tmp_id", "")
            edit_item = None
            for item in cart:
                if item.get("tmp_id") == tmp_id:
                    edit_item = item
                    break
            if edit_item:
                return render_template("form.html", doc={}, action="edit_cart",
                                       edit_item=edit_item, cart=cart, error=None,
                                       auto_ref=generate_ref(),
                                       status_options=get_dropdown_options("status"),
                                       category_options=get_dropdown_options("category"))

        elif action == "update":
            tmp_id = request.form.get("tmp_id", "")
            for i, item in enumerate(cart):
                if item.get("tmp_id") == tmp_id:
                    cart[i]["doc_name"] = request.form.get("doc_name", "").strip()
                    cart[i]["sender_org"] = request.form.get("sender_org", "").strip()
                    cart[i]["sender_name"] = request.form.get("sender_name", "").strip()
                    cart[i]["referred_to"] = request.form.get("referred_to", "").strip()
                    cart[i]["category"] = request.form.get("category", "").strip()
                    cart[i]["description"] = request.form.get("description", "").strip()
                    cart[i]["notes"] = request.form.get("notes", "").strip()
                    session["staff_cart"] = cart
                    session.modified = True
                    flash(f"✅ Document updated successfully.", "success")
                    break
            return redirect(url_for("dashboard.add"))

        elif action == "submit_all":
            if not cart:
                error = "No documents to log. Add at least one document first."
            else:
                actor = session.get("full_name") or session.get("username") or "Staff"
                current_office = session.get("office") or "DepEd Leyte Division"
                logged_doc_ids = []
                for item in cart:
                    audit_log("doc_created",
                              f"doc_name={item.get('doc_name','')[:80]} sender_org={item.get('sender_org','')}",
                              username=session.get("username","?"), ip=get_client_ip())
                    doc = {
                        "id":             str(uuid.uuid4())[:8].upper(),
                        "doc_id":         generate_ref(),
                        "doc_name":       item["doc_name"],
                        "category":       item["category"],
                        "description":    item["description"],
                        "sender_name":    item["sender_name"],
                        "sender_org":     item["sender_org"],
                        "sender_contact": "",
                        "referred_to":    item["referred_to"],
                        "forwarded_to":   "",
                        "recipient_name": "", "recipient_org": "", "recipient_contact": "",
                        "received_by":    actor,
                        "date_received":  now_str()[:16].replace('T', ' '),
                        "date_released":  "",
                        "doc_date":       now_str()[:10],
                        "status":         "Logged",
                        "notes":          item["notes"],
                        "created_at":     now_str(),
                        "routing":        [],
                        "travel_log":     [],
                        "logged_by":      session.get("username"),
                    }
                    doc["travel_log"].append({
                        "office":    item["sender_org"] or "Division Office",
                        "action":    "Document Logged by Staff",
                        "officer":   actor,
                        "timestamp": doc["created_at"],
                        "remarks":   f"Logged into system by {actor}. Status: Logged. Batch of {len(cart)}.",
                    })
                    insert_doc(doc)
                    logged_doc_ids.append(doc["id"])
                
                # Create a logging slip for the logged documents
                from services.misc import generate_slip_no
                from services.qr import create_slip_token
                slip_id = str(uuid.uuid4())[:8].upper()
                slip_no = generate_slip_no()
                
                # Determine destination (where it's going)
                destination = ""
                if cart and cart[0].get("referred_to"):
                    destination = cart[0]["referred_to"]
                
                logging_slip = {
                    "id":            slip_id,
                    "slip_no":       slip_no,
                    "type":          "logging",
                    "doc_ids":       logged_doc_ids,
                    "from_office":   current_office,
                    "destination":   destination,
                    "prepared_by":   actor,
                    "logged_at":     now_str(),
                    "slip_date":     now_str()[:10],
                    "status":        "Logged",
                }
                
                # Save the logging slip using the existing function
                from services.misc import save_routing_slip
                try:
                    save_routing_slip(logging_slip)
                except Exception as e:
                    print(f"Error saving logging slip: {e}")
                
                # Update each logged document with the slip ID
                for doc_id in logged_doc_ids:
                    doc = get_doc(doc_id)
                    if doc:
                        doc["routing_slip_id"] = slip_id
                        doc["routing_slip_no"] = slip_no
                        save_doc(doc)
                
                session.pop("staff_cart", None)
                session.modified = True
                flash(f"✅ {len(cart)} document{'s' if len(cart) != 1 else ''} logged successfully.", "success")
                return redirect(url_for("dashboard.index"))

        cart = session.get("staff_cart", [])

    return render_template("form.html", doc={}, action="add",
                           cart=cart, error=error,
                           auto_ref=generate_ref(),
                           status_options=get_dropdown_options("status"),
                           category_options=get_dropdown_options("category"))


# ── View Logging Slip ─────────────────────────────────────────────────────────────

@dashboard_bp.route("/logging-slip/<slip_id>")
@login_required
def view_logging_slip(slip_id):
    from services.misc import get_all_routing_slips
    all_slips = get_all_routing_slips()
    slip = None
    for s in all_slips:
        if s.get("id") == slip_id:
            slip = s
            break
    if not slip:
        flash("Logging slip not found.", "error")
        return redirect(url_for("dashboard.index"))
    from services.documents import get_docs_by_ids
    docs_map = get_docs_by_ids(slip.get("doc_ids", []))
    docs = [docs_map[did] for did in slip.get("doc_ids", []) if did in docs_map]
    return render_template("logging_slip.html", slip=slip, docs=docs)


# ── View / Edit / Delete ──────────────────────────────────────────────────────

@dashboard_bp.route("/view/<doc_id>")
@login_required
def view_doc(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("dashboard.index"))
    return render_template("detail.html", doc=doc, qr_b64=generate_qr_b64(doc, request.host_url))


@dashboard_bp.route("/edit/<doc_id>", methods=["GET", "POST"])
@login_required
def edit(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        routing = [r.strip() for r in request.form.get("routing_offices", "").split(",") if r.strip()]
        doc.update({
            "doc_id":            request.form.get("doc_id", "").strip(),
            "doc_name":          request.form.get("doc_name", "").strip(),
            "category":          request.form.get("category", "").strip(),
            "doc_date":          request.form.get("doc_date", "").strip(),
            "description":       request.form.get("description", "").strip(),
            "sender_name":       request.form.get("sender_name", "").strip(),
            "sender_org":        request.form.get("sender_org", "").strip(),
            "sender_contact":    request.form.get("sender_contact", "").strip(),
            "received_by":       request.form.get("received_by", "").strip(),
            "referred_to":       request.form.get("referred_to", "").strip(),
            "forwarded_to":      request.form.get("forwarded_to", "").strip(),
            "recipient_name":    request.form.get("recipient_name", "").strip(),
            "recipient_org":     request.form.get("recipient_org", "").strip(),
            "recipient_contact": request.form.get("recipient_contact", "").strip(),
            "date_received":     request.form.get("date_received", ""),
            "date_released":     request.form.get("date_released", ""),
            "status":            request.form.get("status", "Pending"),
            "notes":             request.form.get("notes", "").strip(),
            "routing":           routing,
        })
        if not doc["doc_name"]:
            flash("Document name is required.", "error")
            return render_template("form.html", doc=doc, action="edit", 
                                   status_options=get_dropdown_options("status"),
                                   category_options=get_dropdown_options("category"))
        save_doc(doc)
        audit_log("doc_edited",
                  f"doc_id={doc_id} doc_name={doc.get('doc_name','')[:80]} status={doc.get('status','')}",
                  username=session.get("username","?"), ip=get_client_ip())
        flash("Document updated.", "success")
        return redirect(url_for("dashboard.view_doc", doc_id=doc_id))

    doc["routing_str"] = ", ".join(doc.get("routing", []))
    return render_template("form.html", doc=doc, action="edit", 
                           status_options=get_dropdown_options("status"),
                           category_options=get_dropdown_options("category"))


@dashboard_bp.route("/delete/<doc_id>", methods=["POST"])
@admin_required
def delete(doc_id):
    doc = get_doc(doc_id)
    doc_name = doc.get("doc_name", "Unknown") if doc else "Unknown"
    delete_doc(doc_id, deleted_by=session.get("username", ""))
    audit_log("doc_deleted", f"doc_id={doc_id} name={doc_name}",
              username=session.get("username", ""), ip=get_client_ip())
    flash(f"Document '{doc_name}' moved to trash. Admins can restore it.", "success")
    return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/restore/<doc_id>", methods=["POST"])
@admin_required
def restore(doc_id):
    restore_doc(doc_id)
    audit_log("doc_restored", f"doc_id={doc_id}",
              username=session.get("username", ""), ip=get_client_ip())
    flash("Document restored successfully.", "success")
    return redirect(url_for("dashboard.trash"))


@dashboard_bp.route("/trash")
@admin_required
def trash():
    deleted_docs = [d for d in load_docs(include_deleted=True) if d.get("deleted")]
    return render_template("trash.html", docs=deleted_docs)


@dashboard_bp.route("/trash/permanent-delete/<doc_id>", methods=["POST"])
@admin_required
def permanent_delete_doc(doc_id):
    """Permanently delete a single document from trash."""
    from services.documents import get_doc, delete_doc_forever
    doc = get_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("dashboard.trash"))
    doc_name = doc.get("doc_name", doc_id)
    delete_doc_forever(doc_id)
    audit_log("permanent_delete", f"doc_id={doc_id} doc_name={doc_name}",
              username=session.get("username", ""), ip=get_client_ip())
    flash(f"Document '{doc_name}' permanently deleted.", "success")
    return redirect(url_for("dashboard.trash"))


@dashboard_bp.route("/trash/permanent-delete-all", methods=["POST"])
@admin_required
def permanent_delete_all():
    """Permanently delete all documents in trash."""
    from services.documents import get_doc, delete_doc_forever
    deleted_docs = [d for d in load_docs(include_deleted=True) if d.get("deleted")]
    count = 0
    for doc in deleted_docs:
        delete_doc_forever(doc.get("id", ""))
        count += 1
    audit_log("permanent_delete_all", f"count={count}",
              username=session.get("username", ""), ip=get_client_ip())
    flash(f"Permanently deleted {count} document(s) from trash.", "success")
    return redirect(url_for("dashboard.trash"))


# ── Status update ─────────────────────────────────────────────────────────────

@dashboard_bp.route("/update-status/<doc_id>", methods=["POST"])
@login_required
def update_status(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        return jsonify({"ok": False, "msg": "Not found"}), 404
    new_status = request.form.get("status", "").strip()
    allowed_statuses = get_dropdown_options("status")
    if new_status not in allowed_statuses:
        return jsonify({"ok": False, "msg": "Invalid status"}), 400
    doc["status"] = new_status
    if new_status == "Received" and not doc.get("date_received"):
        doc["date_received"] = now_str()[:16].replace('T', ' ')
    if new_status == "Released" and not doc.get("date_released"):
        doc["date_released"] = now_str()[:16].replace('T', ' ')
    doc.setdefault("travel_log", []).append({
        "office":    "DepEd Leyte Division Office",
        "action":    f"Status Updated to {new_status}",
        "officer":   session.get("full_name") or session.get("username"),
        "timestamp": now_str(),
        "remarks":   "Manual status update by staff.",
    })
    save_doc(doc)
    audit_log("status_updated",
              f"doc_id={doc_id} new_status={new_status} doc_name={doc.get('doc_name','')[:60]}",
              username=session.get("username","?"), ip=get_client_ip())
    flash(f"Status updated to {new_status}.", "success")
    return redirect(url_for("dashboard.view_doc", doc_id=doc_id))


# ── Transfer / Route to Staff ─────────────────────────────────────────────────

@dashboard_bp.route("/transfer/<doc_id>", methods=["GET", "POST"])
@login_required
def transfer_doc(doc_id):
    """Transfer/route a document to another staff member."""
    doc = get_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("dashboard.index"))

    current_user = session.get("username", "")
    user_role    = session.get("role", "")

    if user_role != "admin" and doc.get("logged_by") != current_user:
        flash("You can only transfer documents you logged.", "error")
        return redirect(url_for("dashboard.view_doc", doc_id=doc_id))

    if request.method == "POST":
        transfer_type = request.form.get("transfer_type", "").strip()
        new_staff     = request.form.get("new_staff", "").strip()

        if not new_staff:
            flash("Please select a staff member.", "error")
            return redirect(url_for("dashboard.transfer_doc", doc_id=doc_id))

        if new_staff == current_user:
            flash("You cannot transfer to yourself.", "error")
            return redirect(url_for("dashboard.transfer_doc", doc_id=doc_id))

        all_users   = get_all_users()
        valid_staff = [u["username"] for u in all_users if u.get("role") != "client"]

        new_staff_office = ""
        for u in all_users:
            if u.get("username") == new_staff:
                new_staff_office = u.get("office", "")
                break

        if new_staff not in valid_staff:
            flash("Invalid staff member selected.", "error")
            return redirect(url_for("dashboard.transfer_doc", doc_id=doc_id))

        old_staff   = doc.get("logged_by", "unknown")
        old_status  = doc.get("status", "")
        status_note = "(Inside Office)" if transfer_type == "inside_office" else "(Outside Office)"

        # Get the full name of the new staff member for display
        new_staff_full_name = ""
        for u in all_users:
            if u.get("username") == new_staff:
                new_staff_full_name = u.get("full_name", "") or new_staff
                break

        doc["status"]                = "Pending"
        doc["logged_by"]             = new_staff
        doc["transferred_to"]        = new_staff
        doc["transferred_to_office"] = new_staff_office
        doc["transferred_by"]        = current_user
        doc["transferred_at"]        = now_str()
        doc["transfer_type"]         = transfer_type
        doc["pending_at_staff"]      = new_staff
        doc["pending_at_office"]     = new_staff_office
        doc["pending_at_staff_name"]  = new_staff_full_name
        doc["transfer_status"]       = "pending"  # Track accept/reject status

        doc.setdefault("travel_log", []).append({
            "office":    new_staff_office or "DepEd Leyte Division Office",
            "action":    f"Document Pending {status_note}",
            "officer":   session.get("full_name") or session.get("username"),
            "timestamp": now_str(),
            "remarks":   f"Transferred from {old_staff} ({old_status}) to {new_staff} at {new_staff_office or 'N/A'} {status_note}.",
        })
        save_doc(doc)
        audit_log("doc_transferred",
                  f"doc_id={doc_id} from={old_staff} to={new_staff} type={transfer_type} doc_name={doc.get('doc_name','')[:60]}",
                  username=session.get("username","?"), ip=get_client_ip())
        flash(f"Document transferred to {new_staff_full_name} at {new_staff_office or 'N/A'} {status_note}. Status changed to Pending.", "success")
        return redirect(url_for("dashboard.view_doc", doc_id=doc_id))
    
    # GET — resolve office of currently logged-in user (for internal transfers)
    # Normalize empty office to "No Office" to match _get_staff_by_office logic
    all_users      = get_all_users()
    logged_in_user = session.get("username", "")
    raw_office = ""
    for u in all_users:
        if u.get("username") == logged_in_user:
            raw_office = u.get("office", "") or ""
            break
    current_user_office = raw_office if raw_office else "No Office"

    # DEBUG: Log to console
    print(f"DEBUG transfer_doc: logged_in_user={logged_in_user}, current_user_office={current_user_office}")
    print(f"DEBUG all_users sample: {all_users[:3] if all_users else 'empty'}")

    offices_dict, sorted_offices = _build_offices_dict_and_sorted(current_user, current_user_office)

    return render_template("transfer.html", doc=doc,
                           offices_dict=offices_dict,
                           sorted_offices=sorted_offices,
                           current_office=current_user_office)


# ── Batch Transfer ─────────────────────────────────────────────────────────────

@dashboard_bp.route("/transfer-batch", methods=["POST"])
@login_required
def transfer_batch():
    doc_ids       = request.form.get("doc_ids", "").strip()
    transfer_type = request.form.get("transfer_type", "").strip()
    new_staff     = request.form.get("new_staff", "").strip()

    if not doc_ids:
        flash("No documents selected.", "error")
        return redirect(url_for("dashboard.index"))

    if not new_staff or not transfer_type:
        flash("Please select transfer type and staff member.", "error")
        return redirect(url_for("dashboard.index"))

    id_list = [d.strip() for d in doc_ids.split(",") if d.strip()]
    if not id_list:
        flash("No valid document IDs.", "error")
        return redirect(url_for("dashboard.index"))

    current_user = session.get("username", "")
    user_role    = session.get("role", "")
    all_users    = get_all_users()
    valid_staff  = [u["username"] for u in all_users if u.get("role") != "client"]

    if new_staff not in valid_staff:
        flash("Invalid staff member.", "error")
        return redirect(url_for("dashboard.index"))

    if new_staff == current_user:
        flash("Cannot transfer to yourself.", "error")
        return redirect(url_for("dashboard.index"))

    new_staff_office = ""
    new_staff_full_name = ""
    for u in all_users:
        if u.get("username") == new_staff:
            new_staff_office = u.get("office", "")
            new_staff_full_name = u.get("full_name", "") or new_staff
            break

    status_note       = "(Inside Office)" if transfer_type == "inside_office" else "(Outside Office)"
    transferred_count = 0

    for doc_id in id_list:
        doc = get_doc(doc_id)
        if not doc:
            continue
        if user_role != "admin" and doc.get("logged_by") != current_user:
            continue

        old_staff  = doc.get("logged_by", "unknown")
        old_status = doc.get("status", "")

        doc["status"]                = "Pending"
        doc["logged_by"]             = new_staff
        doc["transferred_to"]        = new_staff
        doc["transferred_to_office"] = new_staff_office
        doc["transferred_by"]        = current_user
        doc["transferred_at"]        = now_str()
        doc["transfer_type"]         = transfer_type
        doc["pending_at_staff"]      = new_staff
        doc["pending_at_office"]     = new_staff_office
        doc["pending_at_staff_name"] = new_staff_full_name
        doc["transfer_status"]       = "pending"  # Track accept/reject status

        doc.setdefault("travel_log", []).append({
            "office":    new_staff_office or "DepEd Leyte Division Office",
            "action":    f"Batch Transfer {status_note}",
            "officer":   session.get("full_name") or session.get("username"),
            "timestamp": now_str(),
            "remarks":   f"Transferred from {old_staff} ({old_status}) to {new_staff} at {new_staff_office or 'N/A'} {status_note}.",
        })
        save_doc(doc)
        transferred_count += 1

    audit_log("doc_batch_transferred",
              f"count={transferred_count} to={new_staff} type={transfer_type}",
              username=session.get("username","?"), ip=get_client_ip())
    flash(f"{transferred_count} document(s) transferred to {new_staff_full_name} at {new_staff_office or 'N/A'}. Status changed to Pending.", "success")
    return redirect(url_for("dashboard.index"))


# ── QR download ───────────────────────────────────────────────────────────────

@dashboard_bp.route("/qr/<doc_id>.png")
def qr_download(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        return "Not found", 404
    buf = BytesIO(make_qr_png(doc, request.host_url, box_size=10))
    buf.seek(0)
    safe = re.sub(r'[^a-zA-Z0-9_]', '_', doc.get("doc_name", "doc"))[:30]
    return send_file(buf, mimetype="image/png", as_attachment=True,
                     download_name=f"QR_{safe}_{doc_id}.png")


# ── Debug / DB status ─────────────────────────────────────────────────────────

@dashboard_bp.route("/db-status")
def db_status():
    from services.database import USE_DB
    if not USE_DB:
        return jsonify({"storage": "JSON file", "database": False})
    try:
        from services.database import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS total FROM documents")
                row = cur.fetchone()
        return jsonify({"storage": "PostgreSQL ✅", "database": True, "documents": row["total"]})
    except Exception as e:
        return jsonify({"storage": "PostgreSQL (ERROR)", "database": False, "error": str(e)})


# ── Document Accept/Reject Routes ─────────────────────────────────────────────

@dashboard_bp.route("/api/pending-documents")
@login_required
def get_pending_documents():
    """Get all documents pending acceptance for the current user."""
    current_user = session.get("username", "")
    current_role = session.get("role", "")
    if not current_user:
        return jsonify([])
    
    docs = load_docs()
    
    # Admin can see all pending transfers
    if current_role == "admin":
        pending = [
            d for d in docs
            if d.get("transfer_status") == "pending"
        ]
    else:
        pending = [
            d for d in docs
            if d.get("transfer_status") == "pending" 
            and d.get("pending_at_staff") == current_user
        ]
    return jsonify(pending)


@dashboard_bp.route("/api/pending-count")
@login_required
def get_pending_count():
    """Get count of documents pending acceptance for the current user."""
    current_user = session.get("username", "")
    current_role = session.get("role", "")
    
    # Get user's office
    all_users = get_all_users()
    current_office = "Not Found"
    for u in all_users:
        if u.get("username") == current_user:
            current_office = u.get("office", "") or "No Office"
            break
    
    print(f"[pending-count] Checking for pending documents...")
    print(f"[pending-count] current_user: {current_user}")
    print(f"[pending-count] current_role: {current_role}")
    print(f"[pending-count] current_office: {current_office}")
    
    if not current_user:
        print("[pending-count] No user, returning 0")
        return jsonify({"count": 0})
    
    docs = load_docs()
    
    # Debug: print all docs with transfer_status
    pending_docs = []
    for d in docs:
        ts = d.get("transfer_status")
        pas = d.get("pending_at_staff")
        if ts:
            print(f"[pending-count] Doc {d.get('id')} has transfer_status={ts}, pending_at_staff={pas}")
        if ts == "pending":
            pending_docs.append(d)
    
    # Admin can see all pending transfers
    if current_role == "admin":
        count = len(pending_docs)
        print(f"[pending-count] Admin view - total pending: {count}")
    else:
        count = sum(
            1 for d in pending_docs
            if d.get("pending_at_staff") == current_user
        )
        print(f"[pending-count] Staff view - pending for {current_user}: {count}")
    
    return jsonify({"count": count})


@dashboard_bp.route("/accept-document/<doc_id>", methods=["POST"])
@login_required
def accept_document(doc_id):
    """Accept a transferred document."""
    current_user = session.get("username", "")
    current_full_name = session.get("full_name", "")
    
    # Force print to flush
    import sys
    print(f"[accept_document] === START === doc_id={doc_id} current_user={current_user}", flush=True)
    
    doc = get_doc(doc_id)
    if not doc:
        print(f"[accept_document] Document not found: {doc_id}", flush=True)
        flash("Document not found.", "error")
        return redirect(url_for("dashboard.index"))
    
    print(f"[accept_document] doc pending_at_staff='{doc.get('pending_at_staff')}' transfer_status='{doc.get('transfer_status')}'", flush=True)
    print(f"[accept_document] current_user='{current_user}'", flush=True)
    
    # Verify this document is pending for the current user
    if doc.get("pending_at_staff") != current_user:
        print(f"[accept_document] Authorization failed!", flush=True)
        flash(f"You are not authorized to accept this document. Document is pending for: {doc.get('pending_at_staff')}", "error")
        return redirect(url_for("dashboard.index"))
    
    if doc.get("transfer_status") != "pending":
        print(f"[accept_document] Already processed: transfer_status={doc.get('transfer_status')}", flush=True)
        flash("This document has already been processed.", "error")
        return redirect(url_for("dashboard.index"))
    
    try:
        # Update document status
        doc["transfer_status"] = "accepted"
        doc["accepted_by"] = current_user
        doc["accepted_by_name"] = current_full_name or current_user
        doc["accepted_at"] = now_str()
        doc["status"] = "Received"  # Update main status to Received
        # Set date_received when accepting
        if not doc.get("date_received"):
            doc["date_received"] = now_str()[:16].replace('T', ' ')
        # Clear pending_at_staff since it's now accepted
        doc["pending_at_staff"] = ""
        doc["pending_at_office"] = ""
        
        # Add to travel log
        doc.setdefault("travel_log", []).append({
            "office":    doc.get("pending_at_office", ""),
            "action":    "Document Accepted",
            "officer":   current_full_name or current_user,
            "timestamp": now_str(),
            "remarks":   f"Document accepted by {current_full_name or current_user}.",
        })
        
        print(f"[accept_document] Saving doc with status={doc.get('status')}", flush=True)
        save_doc(doc)
        print(f"[accept_document] Save complete!", flush=True)
        
        audit_log("doc_accepted",
                  f"doc_id={doc_id} accepted_by={current_user} doc_name={doc.get('doc_name','')[:60]}",
                  username=current_user, ip=get_client_ip())
        
        flash("Document accepted successfully!", "success")
        return redirect(url_for("dashboard.view_doc", doc_id=doc_id))
    except Exception as e:
        print(f"[accept_document] ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        flash(f"Error accepting document: {e}", "error")
        return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/reject-document/<doc_id>", methods=["POST"])
@login_required
def reject_document(doc_id):
    """Reject a transferred document with a reason."""
    current_user = session.get("username", "")
    current_full_name = session.get("full_name", "")
    rejection_reason = request.form.get("rejection_reason", "").strip()
    
    if not rejection_reason:
        flash("Please provide a reason for rejection.", "error")
        return redirect(url_for("dashboard.index"))
    
    doc = get_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("dashboard.index"))
    
    # Verify this document is pending for the current user
    if doc.get("pending_at_staff") != current_user:
        flash("You are not authorized to reject this document.", "error")
        return redirect(url_for("dashboard.index"))
    
    if doc.get("transfer_status") != "pending":
        flash("This document has already been processed.", "error")
        return redirect(url_for("dashboard.index"))
    
    # Store sender info before updating
    original_sender = doc.get("transferred_by", "")
    
    # Update document status
    doc["transfer_status"] = "rejected"
    doc["rejected_by"] = current_user
    doc["rejected_by_name"] = current_full_name or current_user
    doc["rejected_at"] = now_str()
    doc["rejection_reason"] = rejection_reason
    doc["status"] = "Rejected"  # Update main status to Rejected
    
    # Return document to the sender
    doc["logged_by"] = original_sender
    doc["pending_at_staff"] = original_sender
    
    # Add to travel log
    doc.setdefault("travel_log", []).append({
        "office":    doc.get("pending_at_office", ""),
        "action":    "Document Rejected",
        "officer":   current_full_name or current_user,
        "timestamp": now_str(),
        "remarks":   f"Document rejected by {current_full_name or current_user}. Reason: {rejection_reason}",
    })
    
    save_doc(doc)
    
    audit_log("doc_rejected",
              f"doc_id={doc_id} rejected_by={current_user} reason={rejection_reason[:50]} doc_name={doc.get('doc_name','')[:60]}",
              username=current_user, ip=get_client_ip())
    
    flash("Document rejected and returned to sender.", "success")
    return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/api/transferred-documents")
@login_required
def get_transferred_documents():
    """Get documents transferred by current user (to see accept/reject status)."""
    current_user = session.get("username", "")
    if not current_user:
        return jsonify([])
    
    docs = load_docs()
    # Filter documents transferred by current user
    transferred = [
        d for d in docs
        if d.get("transferred_by") == current_user
    ]
    return jsonify(transferred)


@dashboard_bp.route("/debug-error")
def debug_error():
    import os
    if os.environ.get("FLASK_DEBUG") != "1":
        return "Set FLASK_DEBUG=1 to enable.", 403
    from services.database import USE_DB
    info = {"USE_DB": USE_DB}
    try:
        info["doc_count"] = len(load_docs())
    except Exception as ex:
        info["db_error"] = str(ex)
    return jsonify(info)