"""
routes/dashboard.py — Main staff/admin document dashboard and document CRUD.
"""
import uuid
import csv
import io as _io
import difflib
import json
from datetime import date as _date, timedelta as _timedelta

from flask import (Blueprint, flash, jsonify, redirect,
                   render_template, request, send_file, session, url_for)
from io import BytesIO
import re

from services.documents import (
    delete_doc, get_doc, get_stats, insert_doc,
    load_docs, now_str, generate_ref, restore_doc, save_doc,
)
from services.auth import get_all_users
from services.appointments import get_all_appointments, get_appointment, update_appointment
from services.misc import audit_log, load_saved_offices
from services.cart_store import clear_cart
from services.qr import generate_qr_b64, make_qr_png
from services.dropdown_options import get_dropdown_options
from utils import admin_required, get_client_ip, is_logged_in, login_required
from config import STATUS_OPTIONS

dashboard_bp = Blueprint("dashboard", __name__)

# Maximum documents allowed in a single bulk/batch operation.
_MAX_BATCH = 50


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


def _offices_with_staff(all_users=None) -> set:
    """
    Return the set of office names (lowercased, stripped) that have at least one
    non-client user assigned. Authoritative source — derived from user records,
    not the GET-only offices_dict — for deciding whether an office-level transfer
    is permitted. Office-level transfers are only allowed for staffless offices.
    """
    if all_users is None:
        all_users = get_all_users()
    staffed = set()
    for u in all_users:
        if u.get("role") == "client":
            continue
        office = (u.get("office") or "").strip().lower()
        if office:
            staffed.add(office)
    return staffed


def _office_primary_recipients() -> dict:
    """
    Map {office_name: primary_recipient_username} for offices that have a
    non-empty primary_recipient.

    primary_recipient is stored as a USERNAME — both recipient pickers
    (office_staff.js and office_qr_page.html) submit option value =
    staff.username — so these values align with the staff usernames in
    officesData and can be matched directly against staff <option> values.
    Offices with no recipient set are omitted (keys present ⇒ has a default).
    """
    recipients = {}
    for o in load_saved_offices():
        name = (o.get("office_name") or "").strip()
        rec  = (o.get("primary_recipient") or "").strip()
        if name and rec:
            recipients[name] = rec
    return recipients


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
    Build offices_dict (staff grouped by office) and sorted_offices.

    offices_dict groups staff by office (drives the staff sub-dropdown).
    sorted_offices is the full list of registered offices from saved_offices
    (so offices with no assigned staff still appear), excluding "No Office"
    and the user's own current_office. Sorted alphabetically.
    """
    offices_dict = _get_staff_by_office(current_username)

    # Source the office list from the saved_offices table, not from the set of
    # offices that happen to have staff assigned. This ensures all registered
    # offices are available as External transfer destinations.
    office_names = {
        (o.get("office_name") or "").strip()
        for o in load_saved_offices()
        if (o.get("office_name") or "").strip()
    }
    office_names.discard("No Office")
    office_names.discard(current_office)

    sorted_offices = sorted(office_names, key=lambda x: x.lower())
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
        from services.database import get_group_usernames
        paired = get_group_usernames(current_username)
        all_usernames = set([current_username] + paired)
        docs = [
            d for d in docs
            if (
                d.get("original_logged_by") in all_usernames
                or d.get("logged_by") in all_usernames
                or d.get("received_by") in all_usernames
                or d.get("accepted_by") in all_usernames
                or d.get("transferred_by") in all_usernames
            )
        ]

    search           = request.args.get("search", "").lower()
    filter_status    = request.args.get("status", "All")
    filter_type      = request.args.get("type", "All")
    filter_source    = request.args.get("source", "All")  # Staff/Client/All
    filter_date      = request.args.get("date", "").strip()
    sort_col         = request.args.get("sort", "created_at")
    sort_dir         = request.args.get("sort_dir", "desc")
    filter_time_from = request.args.get("time_from", "").strip()
    filter_time_to   = request.args.get("time_to", "").strip()
    filter_office    = request.args.get("office", "All")
    filter_cat       = request.args.get("cat", "All")
    filter_staff     = request.args.get("staff", "All")
    filter_batch     = request.args.get("import_batch", "").strip()

    filtered = docs

    if filter_batch:
        filtered = [d for d in filtered if d.get("import_batch_id") == filter_batch]

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
        if filter_status == "Unknown":
            # Filter for documents with empty or unknown status
            known_statuses = {"Logged", "Pending", "Received", "In Review", "Routed", "Transferred", "Released", "On Hold", "Returned", "Archived"}
            filtered = [d for d in filtered if (d.get("status") or "").strip() not in known_statuses]
        else:
            filtered = [d for d in filtered if d.get("status") == filter_status]

    # Source filter: Staff vs Client submissions
    if filter_source == "Staff":
        filtered = [d for d in filtered if d.get("logged_by") and not d.get("submitted_by")]
    elif filter_source == "Client":
        filtered = [d for d in filtered if d.get("submitted_by")]

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

    if filter_office and filter_office != "All":
        office_lower = filter_office.lower().strip()

        def _matches_office(doc):
            # All comparisons are exact (case-insensitive) to prevent "Main"
            # accidentally matching "MainOffice" or "Main Hall".
            doc_referred    = (doc.get("referred_to") or "").lower().strip()
            doc_target      = (doc.get("target_office_name") or "").lower().strip()
            doc_forwarded   = (doc.get("forwarded_to") or "").lower().strip()
            doc_pending     = (doc.get("pending_at_office") or "").lower().strip()
            doc_transferred = (doc.get("transferred_to_office") or "").lower().strip()
            doc_logged_office = (doc.get("logged_by_office") or "").lower().strip()
            tl = doc.get("travel_log", [])
            tl_office = (tl[0].get("office") or "").lower().strip() if tl else ""
            # routing is a list — check membership, not substring
            routing_offices = [r.lower().strip() for r in doc.get("routing", [])]

            return (
                office_lower == doc_referred or
                office_lower == doc_target or
                office_lower == doc_forwarded or
                office_lower == doc_pending or
                office_lower == doc_transferred or
                office_lower == doc_logged_office or
                office_lower == tl_office or
                office_lower in routing_offices
            )

        filtered = [d for d in filtered if _matches_office(d)]

    if filter_cat and filter_cat != "All":
        filtered = [d for d in filtered
                    if (d.get("category") or "").strip().lower() == filter_cat.strip().lower()]

    # Build staff list for the filter dropdown.
    # Admins see all staff system-wide; regular staff see only their own office.
    _cu_office = session.get("office", "")
    _all_users = get_all_users()
    if user_role == "admin":
        office_staff_list = [
            {"username": u.get("username", ""), "full_name": u.get("full_name") or u.get("username", "")}
            for u in _all_users
            if u.get("role") != "client"
            and u.get("active", True)
        ]
    else:
        office_staff_list = [
            {"username": u.get("username", ""), "full_name": u.get("full_name") or u.get("username", "")}
            for u in _all_users
            if u.get("office") == _cu_office
            and u.get("role") != "client"
            and u.get("active", True)
        ]
    office_staff_names = sorted(s["full_name"] for s in office_staff_list)

    if filter_staff and filter_staff != "All":
        # Match by full_name (received_by stores full_name; logged_by stores username)
        staff_username = next(
            (s["username"] for s in office_staff_list if s["full_name"] == filter_staff), None
        )
        filtered = [
            d for d in filtered
            if d.get("received_by") == filter_staff
            or (staff_username and d.get("logged_by") == staff_username)
        ]

    # ── Sorting ──────────────────────────────────────────────────────────────────
    _SORT_KEYS = {
        "doc_name":   lambda d: (d.get("doc_name") or "").lower(),
        "created_at": lambda d: ((d.get("date_received") or d.get("created_at") or "")[:10], d.get("created_at") or "", d.get("seq") or 0),
        "status":     lambda d: (d.get("status") or "").lower(),
        "sender":     lambda d: (d.get("sender_name") or d.get("sender_org") or "").lower(),
    }
    _sort_key = _SORT_KEYS.get(sort_col, _SORT_KEYS["created_at"])
    filtered = sorted(filtered, key=_sort_key, reverse=(sort_dir != "asc"))

    # ── Office-level stats (admin only) ──────────────────────────────────────────
    office_stats = []
    if user_role == "admin":
        _office_map = {}
        for d in filtered:
            _off = d.get("logged_by_office") or "Unknown"
            if _off not in _office_map:
                _office_map[_off] = {"office": _off, "total": 0, "pending": 0, "overdue": 0}
            _office_map[_off]["total"] += 1
            if d.get("status") in ("Pending", "Logged", "In Review"):
                _office_map[_off]["pending"] += 1
            _today = now_str()[:10]
        office_stats = sorted(_office_map.values(), key=lambda x: -x["total"])[:10]

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

    staff_in_office = offices_dict.get(current_office, [])

    # QR Print Queue disabled
    # pending_print_ids   = session.pop('pending_print_ids', [])
    # pending_print_count = session.pop('pending_print_count', 0)
    # all_docs_list = load_docs()
    # unprinted_docs = [d for d in all_docs_list
    #                   if d.get('logged_by') == session.get('username')
    #                   and not d.get('qr_printed')
    #                   and not d.get('deleted')
    #                   and d.get('status') not in ('Released', 'Archived')][:20]

    current_role_val = session.get("role", "")
    if current_role_val == "admin":
        staff_appointments_list = get_all_appointments()
    else:
        staff_appointments_list = get_all_appointments(office=current_office)
    staff_pending_appointments = len([a for a in staff_appointments_list if a.get("status") == "pending"])

    return render_template("index.html",
        docs=paginated, stats=get_stats(filtered),
        search=search, filter_status=filter_status,
        filter_type=filter_type, filter_source=filter_source,
        filter_date=filter_date,
        filter_time_from=filter_time_from, filter_time_to=filter_time_to,
        filter_office=filter_office,
        filter_cat=filter_cat,
        filter_staff=filter_staff,
        sort_col=sort_col, sort_dir=sort_dir,
        status_options=["All"] + get_dropdown_options("status"),
        cat_options=get_dropdown_options("category"),
        office_staff_names=office_staff_names,
        office_staff_list=office_staff_list,
        office_stats=office_stats,
        today=now_str()[:10],
        today_plus3=(_date.today() + _timedelta(days=3)).strftime('%Y-%m-%d'),
        saved_offices=load_saved_offices(),
        page=page, total_pages=total_pages,
        per_page=per_page, total=total,
        staff_by_office=offices_dict,
        current_office=current_office,
        offices_dict=offices_dict,
        sorted_offices=sorted_offices,
        primary_recipients=_office_primary_recipients(),  # {office_name: recipient_username}
        current_user_name=session.get('full_name', ''),
        current_user_role=session.get('role', ''),
        is_admin=session.get('role') == 'admin',
        # pending_print_ids=pending_print_ids,    # QR Print Queue disabled
        # pending_print_count=pending_print_count, # QR Print Queue disabled
        # unprinted_docs=unprinted_docs,           # QR Print Queue disabled
        staff_appointments=staff_appointments_list,
        staff_pending_appointments=staff_pending_appointments)


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
                    "tmp_id":               uuid.uuid4().hex[:8].upper(),
                    "doc_name":             doc_name,
                    "sender_org":           request.form.get("sender_org", "").strip(),
                    "sender_name":          request.form.get("sender_name", "").strip(),
                    "referred_to":          request.form.get("referred_to", "").strip(),
                    "referred_to_username": request.form.get("referred_to_username", "").strip(),
                    "category":             request.form.get("category", "").strip(),
                    "description":          request.form.get("description", "").strip(),
                    "notes":                request.form.get("notes", "").strip(),
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
                _cu   = session.get("username", "")
                _co   = session.get("office", "")
                _role = session.get("role", "")
                _all  = get_all_users()
                if _role == "admin":
                    _office_staff = sorted([
                        {"username": u["username"], "full_name": u.get("full_name") or u["username"],
                         "documents_handled": u.get("documents_handled") or []}
                        for u in _all
                        if u.get("username") != _cu
                        and u.get("role") != "client"
                        and u.get("active", True)
                    ], key=lambda x: x["full_name"])
                else:
                    _office_staff = sorted([
                        {"username": u["username"], "full_name": u.get("full_name") or u["username"],
                         "documents_handled": u.get("documents_handled") or []}
                        for u in _all
                        if u.get("office") == _co
                        and u.get("username") != _cu
                        and u.get("role") != "client"
                        and u.get("active", True)
                    ], key=lambda x: x["full_name"])
                return render_template("form.html", doc={}, action="edit_cart",
                                       edit_item=edit_item, cart=cart, error=None,
                                       auto_ref=generate_ref(),
                                       status_options=get_dropdown_options("status"),
                                       category_options=get_dropdown_options("category"),
                                       office_staff=_office_staff)

        elif action == "update":
            tmp_id = request.form.get("tmp_id", "")
            for i, item in enumerate(cart):
                if item.get("tmp_id") == tmp_id:
                    cart[i]["doc_name"] = request.form.get("doc_name", "").strip()
                    cart[i]["sender_org"] = request.form.get("sender_org", "").strip()
                    cart[i]["sender_name"] = request.form.get("sender_name", "").strip()
                    cart[i]["referred_to"]          = request.form.get("referred_to", "").strip()
                    cart[i]["referred_to_username"] = request.form.get("referred_to_username", "").strip()
                    cart[i]["category"] = request.form.get("category", "").strip()
                    cart[i]["description"] = request.form.get("description", "").strip()
                    cart[i]["notes"] = request.form.get("notes", "") or request.form.get("description", "").strip()
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
                    now = now_str()
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
                        "date_received":  now[:16].replace('T', ' '),
                        "date_released":  "",
                        "doc_date":       now[:10],
                        "status":         "Logged",
                        "notes":          item["notes"],
                        "created_at":     now,
                        "routing":        [],
                        "travel_log":     [],
                        "logged_by":      session.get("username"),
                        "original_logged_by": session.get("username"),
                        "logged_by_office": current_office,
                        "routing_cycle": 0,
                    }

                    doc["travel_log"].append({
                        "office":    current_office,
                        "action":    "Document Logged by Staff",
                        "officer":   actor,
                        "timestamp": now,
                        "remarks":   f"Logged into system by {actor}. Batch of {len(cart)}.",
                    })

                    insert_doc(doc)
                    audit_log("doc_created",
                              f"doc_name={item.get('doc_name','')[:80]} sender_org={item.get('sender_org','')}",
                              username=session.get("username","?"), ip=get_client_ip())

                    # ── Auto-transfer if a referred_to_username was set ──────────────────
                    ref_username = item.get("referred_to_username", "").strip()
                    if ref_username:
                        ref_user = next(
                            (u for u in get_all_users() if u.get("username") == ref_username),
                            None
                        )
                        if ref_user:
                            ref_office    = ref_user.get("office", "") or ""
                            ref_full_name = ref_user.get("full_name", "") or ref_username
                            now_t = now_str()
                            doc["travel_log"].append({
                                "office":    current_office,
                                "action":    "Transferred",
                                "officer":   actor,
                                "timestamp": now_t,
                                "remarks":   f"Auto-transferred to {ref_full_name} ({ref_office or 'N/A'}).",
                            })
                            doc["status"]                = "Transferred"
                            doc["transferred_to"]        = ref_username
                            doc["transferred_to_office"] = ref_office
                            doc["transferred_by"]        = session.get("username")
                            doc["transferred_at"]        = now_t
                            doc["transfer_type"]         = "inside_office"
                            doc["pending_at_staff"]      = ref_username
                            doc["pending_at_office"]     = ref_office
                            doc["pending_at_staff_name"] = ref_full_name
                            doc["transfer_status"]       = "pending"
                            save_doc(doc)
                            audit_log("doc_auto_transferred",
                                      f"doc_id={doc['id']} to={ref_username} office={ref_office}",
                                      username=session.get("username","?"), ip=get_client_ip())
                    # ── End auto-transfer ────────────────────────────────────────────────

                    logged_doc_ids.append(doc["id"])

                # NOTE: Logging a document never creates a routing slip.
                # Routing slips are only created when the user explicitly routes/transfers
                # documents via the routing action in routes/offices.py.

                # session['pending_print_ids'] = logged_doc_ids    # QR Print Queue disabled
                # session['pending_print_count'] = len(cart)       # QR Print Queue disabled
                session.pop("staff_cart", None)
                session.modified = True
                clear_cart(session.get("username", ""))
                flash(f"✅ {len(cart)} document{'s' if len(cart) != 1 else ''} logged successfully.", "success")
                return redirect(url_for("dashboard.index"))

        cart = session.get("staff_cart", [])

    current_username = session.get("username", "")
    current_office   = session.get("office", "")
    current_role     = session.get("role", "")
    all_users        = get_all_users()

    # Admins can refer to any active non-client staff across all offices.
    # Regular staff only see colleagues within their own office.
    if current_role == "admin":
        office_staff = sorted([
            {"username": u["username"], "full_name": u.get("full_name") or u["username"],
             "documents_handled": u.get("documents_handled") or []}
            for u in all_users
            if u.get("username") != current_username
            and u.get("role") != "client"
            and u.get("active", True)
        ], key=lambda x: x["full_name"])
    else:
        office_staff = sorted([
            {"username": u["username"], "full_name": u.get("full_name") or u["username"],
             "documents_handled": u.get("documents_handled") or []}
            for u in all_users
            if u.get("office") == current_office
            and u.get("username") != current_username
            and u.get("role") != "client"
            and u.get("active", True)
        ], key=lambda x: x["full_name"])

    return render_template("form.html", doc={}, action="add",
                           cart=cart, error=error,
                           auto_ref=generate_ref(),
                           status_options=get_dropdown_options("status"),
                           category_options=get_dropdown_options("category"),
                           office_staff=office_staff)


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


# ── Print Logging Slip ────────────────────────────────────────────────────────

@dashboard_bp.route("/logging-slip/print", methods=["POST"])
@login_required
def print_logging_slip():
    from services.misc import save_routing_slip
    from services.documents import get_docs_by_ids

    raw = request.form.get("doc_ids", "").strip()
    id_list = [d.strip() for d in raw.split(",") if d.strip()][:_MAX_BATCH]
    if not id_list:
        flash("No documents selected.", "error")
        return redirect(url_for("dashboard.index"))

    docs_map = get_docs_by_ids(id_list)
    docs = [docs_map[did] for did in id_list if did in docs_map]

    slip_id = "LOG-" + str(uuid.uuid4())[:8].upper()
    slip = {
        "id":          slip_id,
        "slip_no":     slip_id,
        "type":        "logging",
        "destination": "",
        "slip_date":   _date.today().isoformat(),
        "logged_at":   now_str(),
        "prepared_by": session.get("full_name") or session.get("username"),
        "from_office": session.get("office") or "DepEd Leyte Division",
        "doc_ids":     id_list,
    }
    save_routing_slip(slip)
    return render_template("logging_slip.html", slip=slip, docs=docs)


# ── View / Edit / Delete ──────────────────────────────────────────────────────

@dashboard_bp.route("/view/<doc_id>")
@login_required
def view_doc(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("dashboard.index"))

    # Resolve slip type so the template can show the correct button
    slip_type = None
    if doc.get("routing_slip_id"):
        from services.misc import get_all_routing_slips
        for s in get_all_routing_slips():
            if s.get("id") == doc["routing_slip_id"]:
                slip_type = s.get("type")
                break

    # Resolve transfer usernames to full names for display
    all_users = get_all_users()
    user_lookup = {u["username"]: u.get("full_name") or u["username"] for u in all_users}

    transferred_to_name = (
        doc.get("pending_at_staff_name")
        or user_lookup.get(doc.get("transferred_to", ""), doc.get("transferred_to") or "")
    )
    transferred_by_name = user_lookup.get(
        doc.get("transferred_by", ""), doc.get("transferred_by") or ""
    )

    return render_template("detail.html", doc=doc,
                           qr_b64=generate_qr_b64(doc, request.host_url),
                           slip_type=slip_type,
                           status_options=get_dropdown_options("status"),
                           transferred_to_name=transferred_to_name,
                           transferred_by_name=transferred_by_name,
                           rt_changed=request.args.get("rt_changed", ""),
                           rt_name=request.args.get("rt_name", ""),
                           rt_user=request.args.get("rt_user", ""))


@dashboard_bp.route("/edit/<doc_id>", methods=["GET", "POST"])
@login_required
def edit(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("dashboard.index"))

    actor           = session.get("username", "Unknown")
    current_office  = session.get("office", "")
    current_role    = session.get("role", "")
    _all_users      = get_all_users()
    if current_role == "admin":
        office_staff = sorted([
            {"username": u["username"], "full_name": u.get("full_name") or u["username"],
             "documents_handled": u.get("documents_handled") or []}
            for u in _all_users
            if u.get("username") != actor
            and u.get("role") != "client"
            and u.get("active", True)
        ], key=lambda x: x["full_name"])
    else:
        office_staff = sorted([
            {"username": u["username"], "full_name": u.get("full_name") or u["username"],
             "documents_handled": u.get("documents_handled") or []}
            for u in _all_users
            if u.get("office") == current_office
            and u.get("username") != actor
            and u.get("role") != "client"
            and u.get("active", True)
        ], key=lambda x: x["full_name"])
    
    if request.method == "POST":
        routing = [r.strip() for r in request.form.get("routing_offices", "").split(",") if r.strip()]
        old_status      = doc.get("status", "")
        old_doc_name    = doc.get("doc_name", "")
        old_referred_to = doc.get("referred_to", "")

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
                                   category_options=get_dropdown_options("category"),
                                   office_staff=office_staff)
        
        # Add edit to travel_log
        new_status = doc.get("status", "")
        edit_remarks = f"Document edited by {actor}"
        if old_status != new_status:
            edit_remarks = f"Document edited by {actor}. Status changed from {old_status} to {new_status}."
        
        doc.setdefault("travel_log", []).append({
            "office":    "DepEd Leyte Division Office",
            "action":    "Document Edited",
            "officer":   actor,
            "timestamp": now_str(),
            "remarks":   edit_remarks,
        })
        
        save_doc(doc)
        audit_log("doc_edited",
                  f"doc_id={doc_id} doc_name={doc.get('doc_name','')[:80]} status={doc.get('status','')}",
                  username=session.get("username","?"), ip=get_client_ip())
        flash("Document updated.", "success")
        new_referred_to          = doc.get("referred_to", "")
        new_referred_to_username = request.form.get("referred_to_username", "").strip()
        if new_referred_to and new_referred_to != old_referred_to:
            return redirect(url_for("dashboard.view_doc", doc_id=doc_id,
                                    rt_changed="1",
                                    rt_name=new_referred_to,
                                    rt_user=new_referred_to_username))
        return redirect(url_for("dashboard.view_doc", doc_id=doc_id))

    doc["routing_str"] = ", ".join(doc.get("routing", []))
    return render_template("form.html", doc=doc, action="edit",
                           status_options=get_dropdown_options("status"),
                           category_options=get_dropdown_options("category"),
                           office_staff=office_staff)


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


@dashboard_bp.route("/bulk-delete", methods=["POST"])
@admin_required
def bulk_delete():
    doc_ids = request.form.get("doc_ids", "")
    ids = [d.strip() for d in doc_ids.split(",") if d.strip()]
    if not ids:
        flash("No documents selected.", "warning")
        return redirect(url_for("dashboard.index"))

    deleted = 0
    for doc_id in ids:
        doc = get_doc(doc_id)
        if doc:
            delete_doc(doc_id, deleted_by=session.get("username", ""))
            deleted += 1

    audit_log("bulk_delete", f"Admin bulk deleted {deleted} documents: {', '.join(ids)}",
              session.get("username"))
    flash(f"{deleted} document(s) moved to trash.", "success")
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
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "msg": "Not found"}), 404
        return jsonify({"ok": False, "msg": "Not found"}), 404
    new_status = request.form.get("status", "").strip()
    allowed_statuses = get_dropdown_options("status")
    if new_status not in allowed_statuses:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "msg": "Invalid status"}), 400
        return jsonify({"ok": False, "msg": "Invalid status"}), 400
    doc["status"] = new_status
    if new_status == "Received" and not doc.get("date_received"):
        doc["date_received"] = now_str()[:16].replace('T', ' ')
    if new_status == "Released" and not doc.get("date_released"):
        doc["date_released"] = now_str()[:16].replace('T', ' ')
    current_office = session.get("office") or "DepEd Leyte Division Office"
    doc.setdefault("travel_log", []).append({
        "office":    current_office,
        "action":    f"Status Updated to {new_status}",
        "officer":   session.get("full_name") or session.get("username"),
        "timestamp": now_str(),
        "remarks":   "Manual status update by staff.",
    })
    try:
        save_doc(doc)
    except Exception as e:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "msg": str(e)}), 500
        flash(f"Failed to update status: {str(e)}", "error")
        return redirect(url_for("dashboard.view_doc", doc_id=doc_id))
    audit_log("status_updated",
              f"doc_id={doc_id} new_status={new_status} doc_name={doc.get('doc_name','')[:60]}",
              username=session.get("username","?"), ip=get_client_ip())
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "status": new_status})
    flash(f"Status updated to {new_status}.", "success")
    return redirect(url_for("dashboard.view_doc", doc_id=doc_id))


# ── Bulk Status Update ─────────────────────────────────────────────────────────

@dashboard_bp.route("/bulk-update-status", methods=["POST"])
@login_required
def bulk_update_status():
    doc_ids_str = request.form.get("doc_ids", "").strip()
    new_status = request.form.get("new_status", "").strip()
    remarks = request.form.get("remarks", "").strip()
    
    if not doc_ids_str:
        flash("No documents selected.", "error")
        return redirect(url_for("dashboard.index"))
    
    if not new_status:
        flash("Please select a status.", "error")
        return redirect(url_for("dashboard.index"))
    
    allowed_statuses = get_dropdown_options("status")
    if new_status not in allowed_statuses:
        flash("Invalid status.", "error")
        return redirect(url_for("dashboard.index"))
    
    doc_ids = [d.strip() for d in doc_ids_str.split(",") if d.strip()][:_MAX_BATCH]
    if not doc_ids:
        flash("No valid document IDs provided.", "error")
        return redirect(url_for("dashboard.index"))

    current_user = session.get("username", "")
    current_full_name = session.get("full_name", current_user)
    updated_count = 0
    failed_count = 0

    for doc_id in doc_ids:
        doc = get_doc(doc_id)
        if not doc:
            failed_count += 1
            continue
        
        old_status = doc.get("status", "")
        doc["status"] = new_status
        
        if new_status == "Received" and not doc.get("date_received"):
            doc["date_received"] = now_str()[:16].replace('T', ' ')
        if new_status == "Released" and not doc.get("date_released"):
            doc["date_released"] = now_str()[:16].replace('T', ' ')
        
        # Add to travel log
        doc.setdefault("travel_log", []).append({
            "office":    doc.get("target_office_name", "DepEd Leyte Division Office"),
            "action":    f"Status Updated to {new_status}",
            "officer":   current_full_name,
            "timestamp": now_str(),
            "remarks":   remarks or f"Bulk status update from {old_status} to {new_status} by {current_full_name}.",
        })
        
        try:
            save_doc(doc)
            audit_log("bulk_status_updated",
                      f"doc_id={doc_id} new_status={new_status} old_status={old_status}",
                      username=current_user, ip=get_client_ip())
            updated_count += 1
        except Exception:
            failed_count += 1
    
    if failed_count > 0:
        flash(f"Updated {updated_count} document(s). Failed to update {failed_count} document(s).", "warning")
    else:
        flash(f"Status updated to '{new_status}' for {updated_count} document(s).", "success")
    return redirect(url_for("dashboard.index"))


# ── Transfer / Route to Staff ─────────────────────────────────────────────────

@dashboard_bp.route("/transfer/<doc_id>", methods=["GET", "POST"])
@login_required
def transfer_doc(doc_id):
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    doc = get_doc(doc_id)
    if not doc:
        if is_ajax: return jsonify({"ok": False, "error": "Document not found"}), 404
        flash("Document not found.", "error")
        return redirect(url_for("dashboard.index"))

    current_user = session.get("username", "")
    user_role    = session.get("role", "")

    # A user may route a doc if they own it OR share a group with one of its
    # owners that has BOTH shared dashboard AND shared transfer enabled. This is
    # the TRANSFER set (get_group_transfer_usernames), which is narrower than the
    # VISIBILITY set (get_group_usernames, dashboard flag only) used by the index
    # filter — so "can see" can be granted without "can transfer". current_user
    # is always in transfer_set, so a user always transfers their OWN docs
    # regardless of group/flags. received_by is excluded (stores a full name).
    from services.database import get_group_transfer_usernames
    transfer_set = {current_user} | set(get_group_transfer_usernames(current_user))
    owner_fields = {doc.get("original_logged_by"), doc.get("logged_by"),
                    doc.get("accepted_by"), doc.get("transferred_by")}
    owner_fields.discard(None); owner_fields.discard("")
    can_transfer = (user_role == "admin") or bool(owner_fields & transfer_set)

    if user_role != "admin" and not can_transfer:
        if is_ajax: return jsonify({"ok": False, "error": "Not authorized to route this document"}), 403
        flash("You are not authorized to route this document.", "error")
        return redirect(url_for("dashboard.view_doc", doc_id=doc_id))

    if request.method == "POST":
        transfer_type = request.form.get("transfer_type", "").strip()
        new_staff     = request.form.get("new_staff", "").strip()
        new_office    = request.form.get("new_office", "").strip()

        # A specific staff member is required, EXCEPT when transferring to an
        # office that has no registered staff — then an office-level transfer
        # (no specific recipient) is allowed and the doc lands in that office's
        # general pending queue.
        if not new_staff and not new_office:
            if is_ajax: return jsonify({"ok": False, "error": "Please select a staff member or office"}), 400
            flash("Please select a staff member or office.", "error")
            return redirect(url_for("dashboard.transfer_doc", doc_id=doc_id))

        all_users = get_all_users()

        if new_staff:
            # ── Staff-level transfer (existing behavior) ──
            if new_staff == current_user:
                if is_ajax: return jsonify({"ok": False, "error": "You cannot route to yourself"}), 400
                flash("You cannot route to yourself.", "error")
                return redirect(url_for("dashboard.transfer_doc", doc_id=doc_id))

            valid_staff = [u["username"] for u in all_users if u.get("role") != "client"]
            if new_staff not in valid_staff:
                if is_ajax: return jsonify({"ok": False, "error": "Invalid staff member selected"}), 400
                flash("Invalid staff member selected.", "error")
                return redirect(url_for("dashboard.transfer_doc", doc_id=doc_id))

            new_staff_office    = ""
            new_staff_full_name = ""
            for u in all_users:
                if u.get("username") == new_staff:
                    new_staff_office    = u.get("office", "")
                    new_staff_full_name = u.get("full_name", "") or new_staff
                    break
        else:
            # ── Office-level transfer (office has no registered staff) ──
            valid_offices = {(o.get("office_name") or "").strip().lower()
                             for o in load_saved_offices()}
            if new_office.strip().lower() not in valid_offices:
                if is_ajax: return jsonify({"ok": False, "error": "Invalid office selected"}), 400
                flash("Invalid office selected.", "error")
                return redirect(url_for("dashboard.transfer_doc", doc_id=doc_id))

            # Office-level transfers are only for offices with no registered
            # staff. A staffed office must route to a specific person.
            if new_office.strip().lower() in _offices_with_staff(all_users):
                if is_ajax: return jsonify({"ok": False, "error": "Please select a staff member for this office"}), 400
                flash("Please select a staff member for this office.", "error")
                return redirect(url_for("dashboard.transfer_doc", doc_id=doc_id))

            new_staff           = ""          # no specific recipient
            new_staff_office    = new_office
            new_staff_full_name = ""

        # Human-readable recipient for log/flash messages (office-level has no name)
        recipient_display = new_staff_full_name or "the office's general queue"

        original_logger = doc.get("original_logged_by", doc.get("logged_by", ""))
        old_status      = doc.get("status", "")
        cycle           = doc.get("routing_cycle", 0)
        status_note     = "(Inside Office)" if transfer_type == "inside_office" else "(Outside Office)"

        # Determine if this is a forward route (original → another office)
        # or a re-route back (another office → original logger)
        routing_back_to_origin = (new_staff == original_logger)

        if routing_back_to_origin:
            # ── RE-ROUTING BACK TO ORIGINAL STAFF ──
            new_cycle = cycle + 1
            action_label = f"Re-routed back to Originating Staff (Cycle {new_cycle})"
            new_status   = "Transferred" if transfer_type == "inside_office" else "Routed"
            doc["routing_cycle"] = new_cycle
        else:
            # ── ROUTING FORWARD TO ANOTHER OFFICE ──
            action_label = f"{'Transferred to ' + new_staff_full_name if transfer_type == 'inside_office' else 'Routed'} — {status_note} (Cycle {cycle + 1})"
            new_status   = "Transferred" if transfer_type == "inside_office" else "Routed"

        doc["status"]                = new_status
        doc["transferred_to"]        = new_staff
        doc["transferred_to_office"] = new_staff_office
        doc["transferred_by"]        = current_user
        doc["transferred_at"]        = now_str()
        doc["transfer_type"]         = transfer_type
        doc["pending_at_staff"]      = new_staff
        doc["pending_at_office"]     = new_staff_office
        doc["pending_at_staff_name"] = new_staff_full_name
        doc["transfer_status"]       = "pending"
        # NOTE: logged_by is NOT updated here — the receiving staff takes
        # ownership only after they accept via the receive modal.

        current_full_name = session.get("full_name") or session.get("username")
        current_office    = session.get("office") or "DepEd Leyte Division"

        remark = (
            f"Re-routed to {new_staff_full_name} ({new_staff_office or 'N/A'}). "
            f"Cycle {doc['routing_cycle']} completed."
            if routing_back_to_origin else
            f"Transferred to {recipient_display} ({new_staff_office or 'N/A'})."
        )
        # Provenance: when a group-mate (a non-owner, non-admin actor) moves an
        # owner's doc, record BOTH who moved it and who originated it — without
        # overwriting any owner field. Owners' own transfers keep the plain remark.
        doc_owners = {doc.get("original_logged_by"), doc.get("logged_by"), doc.get("accepted_by")}
        if user_role != "admin" and current_user not in doc_owners:
            remark += (
                f" By {current_full_name} — acting on document originated by "
                f"{doc.get('original_logged_by') or 'N/A'}."
            )

        doc.setdefault("travel_log", []).append({
            "office":    new_staff_office or "DepEd Leyte Division Office",
            "action":    action_label,
            "officer":   current_full_name,
            "timestamp": now_str(),
            "remarks":   remark,
        })

        save_doc(doc)
        audit_log(
            "doc_rerouted" if routing_back_to_origin else "doc_transferred",
            f"doc_id={doc_id} from={current_user} to={new_staff or 'office:' + new_staff_office} "
            f"cycle={doc.get('routing_cycle',0)} doc_name={doc.get('doc_name','')[:60]}",
            username=current_user, ip=get_client_ip()
        )

        if routing_back_to_origin:
            flash(
                f"Document re-routed back to {new_staff_full_name}. "
                f"Routing cycle {doc['routing_cycle']} recorded.", "success"
            )
        else:
            flash(
                f"Document routed to {recipient_display} at "
                f"{new_staff_office or 'N/A'} {status_note}.", "success"
            )

        # EXTERNAL transfer → create a routing slip and send the user to the
        # printable slip page. Authority is the OFFICE comparison: if the
        # destination office differs from the sender's own office it is
        # external; if they match (even when transfer_type=="outside_office"
        # because the user picked their own office) it is INTERNAL — no slip.
        is_external = new_staff_office.strip().lower() != current_office.strip().lower()
        if is_external:
            from services.misc import build_transfer_slip
            slip_id = build_transfer_slip(
                [doc_id], new_staff_office, current_office,
                current_full_name, new_staff_full_name or new_staff_office,
            )
            if is_ajax: return jsonify({"ok": True, "slip_id": slip_id})
            return redirect(url_for("offices.view_routing_slip", slip_id=slip_id))

        if is_ajax: return jsonify({"ok": True})
        # Scoped cart clear: remove only this doc, not the user's whole cart.
        return redirect(url_for("dashboard.view_doc", doc_id=doc_id, cleared_ids=doc_id))

    # ── GET ──
    all_users      = get_all_users()
    logged_in_user = session.get("username", "")
    raw_office     = ""
    for u in all_users:
        if u.get("username") == logged_in_user:
            raw_office = u.get("office", "") or ""
            break
    current_user_office = raw_office if raw_office else "No Office"

    offices_dict, sorted_offices = _build_offices_dict_and_sorted(
        current_user, current_user_office
    )
    primary_recipients = _office_primary_recipients()

    original_logger = doc.get("original_logged_by", "")

    return render_template(
        "transfer.html", doc=doc,
        offices_dict=offices_dict,
        sorted_offices=sorted_offices,
        primary_recipients=primary_recipients,     # ← {office_name: recipient_username}
        current_office=current_user_office,
        current_user_name=session.get("full_name", ""),
        current_user_role=session.get("role", ""),
        original_logger=original_logger,          # ← pass to template
        routing_cycle=doc.get("routing_cycle", 0) # ← pass to template
    )
    
    
@dashboard_bp.route("/release/<doc_id>", methods=["POST"])
@login_required
def release_doc(doc_id):
    """
    Final release — only callable by the original logging staff,
    after all routing cycles are done and the document is back with them.
    """
    doc = get_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("dashboard.index"))

    current_user    = session.get("username", "")
    original_logger = doc.get("original_logged_by", doc.get("logged_by", ""))

    # Only the original logger (or admin) can release
    if session.get("role") != "admin" and current_user != original_logger:
        flash("Only the staff who originally logged this document can release it.", "error")
        return redirect(url_for("dashboard.view_doc", doc_id=doc_id))

    # Document must be back in the original logger's hands
    if doc.get("logged_by") != current_user and session.get("role") != "admin":
        flash("Document must be returned to you before you can release it.", "error")
        return redirect(url_for("dashboard.view_doc", doc_id=doc_id))

    current_full_name = session.get("full_name") or session.get("username")
    current_office    = session.get("office") or "DepEd Leyte Division"
    total_cycles      = doc.get("routing_cycle", 0)

    doc["status"]        = "Released"
    doc["date_released"] = now_str()[:16].replace("T", " ")
    doc["released_by"]   = current_user
    doc["transfer_status"] = "released"

    doc.setdefault("travel_log", []).append({
        "office":    current_office,
        "action":    "Released by Originating Staff",
        "officer":   current_full_name,
        "timestamp": now_str(),
        "remarks":   (
            f"All routing cycles completed ({total_cycles} cycle"
            f"{'s' if total_cycles != 1 else ''}). "
            f"Document officially released by {current_full_name}. Workflow closed."
        ),
    })

    save_doc(doc)
    audit_log(
        "doc_released",
        f"doc_id={doc_id} released_by={current_user} cycles={total_cycles} "
        f"doc_name={doc.get('doc_name','')[:60]}",
        username=current_user, ip=get_client_ip()
    )
    flash(
        f"Document released successfully after {total_cycles} routing "
        f"cycle{'s' if total_cycles != 1 else ''}. Workflow is now closed.", "success"
    )
    return redirect(url_for("dashboard.view_doc", doc_id=doc_id))

# ── Batch Transfer ─────────────────────────────────────────────────────────────

@dashboard_bp.route("/transfer-batch", methods=["POST"])
@login_required
def transfer_batch():
    doc_ids       = request.form.get("doc_ids", "").strip()
    transfer_type = request.form.get("transfer_type", "").strip()
    new_staff     = request.form.get("new_staff", "").strip()
    new_office    = request.form.get("new_office", "").strip()

    if not doc_ids:
        flash("No documents selected.", "error")
        return redirect(url_for("dashboard.index"))

    if not transfer_type:
        flash("Please select a transfer type.", "error")
        return redirect(url_for("dashboard.index"))

    # A specific staff member is required, EXCEPT for an office-level transfer
    # to an office with no registered staff (new_staff empty, new_office set).
    if not new_staff and not new_office:
        flash("Please select a staff member or office.", "error")
        return redirect(url_for("dashboard.index"))

    id_list = [d.strip() for d in doc_ids.split(",") if d.strip()][:_MAX_BATCH]

    if not id_list:
        flash("No valid document IDs.", "error")
        return redirect(url_for("dashboard.index"))

    current_user      = session.get("username", "")
    current_full_name = session.get("full_name") or session.get("username") or ""
    current_office    = session.get("office") or "DepEd Leyte Division"
    user_role         = session.get("role", "")
    all_users         = get_all_users()

    if new_staff:
        # ── Staff-level transfer (existing behavior) ──
        valid_staff = [u["username"] for u in all_users if u.get("role") != "client"]
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
    else:
        # ── Office-level transfer (office has no registered staff) ──
        valid_offices = {(o.get("office_name") or "").strip().lower()
                         for o in load_saved_offices()}
        if new_office.strip().lower() not in valid_offices:
            flash("Invalid office.", "error")
            return redirect(url_for("dashboard.index"))

        # Office-level transfers are only for offices with no registered staff.
        # A staffed office must route to a specific person.
        if new_office.strip().lower() in _offices_with_staff(all_users):
            flash("Please select a staff member for this office.", "error")
            return redirect(url_for("dashboard.index"))

        new_staff           = ""          # no specific recipient
        new_staff_office    = new_office
        new_staff_full_name = ""

    # Human-readable recipient for log/flash messages (office-level has no name)
    recipient_display = new_staff_full_name or "the office's general queue"

    status_note       = "(Inside Office)" if transfer_type == "inside_office" else "(Outside Office)"
    transferred_count = 0
    transferred_ids   = []   # only docs actually transferred → scoped cart clear
    skipped_missing   = 0    # doc_id not found
    skipped_unauth    = 0    # caller not authorized to transfer this doc

    # Same authorization set as the single transfer route: {current_user} ∪
    # group-mates whose group has BOTH shared dashboard AND shared transfer on.
    # current_user is always present, so own-doc transfers are never blocked.
    from services.database import get_group_transfer_usernames
    transfer_set = {current_user} | set(get_group_transfer_usernames(current_user))

    for doc_id in id_list:
        doc = get_doc(doc_id)
        if not doc:
            skipped_missing += 1
            continue
        # Authorized if admin, OR one of the doc's owner identities falls in the
        # caller's {self ∪ shared-transfer group} set. Skips are COUNTED, not
        # silently dropped (see honest-feedback block after the loop).
        owner_fields = {doc.get("original_logged_by"), doc.get("logged_by"),
                        doc.get("accepted_by"), doc.get("transferred_by")}
        owner_fields.discard(None); owner_fields.discard("")
        can_transfer = (user_role == "admin") or bool(owner_fields & transfer_set)
        if not can_transfer:
            skipped_unauth += 1
            continue

        old_status      = doc.get("status", "")
        original_logger = doc.get("original_logged_by", doc.get("logged_by", ""))
        cycle           = doc.get("routing_cycle", 0)

        # Preserve original_logged_by — never overwrite it
        if not doc.get("original_logged_by"):
            doc["original_logged_by"] = doc.get("logged_by", current_user)

        routing_back = (new_staff == original_logger)
        if routing_back:
            doc["routing_cycle"] = cycle + 1
            action_label = f"Batch Re-routed to Originating Staff (Cycle {doc['routing_cycle']})"
        else:
            action_label = f"Batch {'Transferred' if transfer_type == 'inside_office' else 'Routed'} — {status_note} (Cycle {cycle + 1})"

        doc["status"]                = "Transferred" if transfer_type == "inside_office" else "Routed"
        doc["transferred_to"]        = new_staff
        doc["transferred_to_office"] = new_staff_office
        doc["transferred_by"]        = current_user
        doc["transferred_at"]        = now_str()
        doc["transfer_type"]         = transfer_type
        doc["pending_at_staff"]      = new_staff
        doc["pending_at_office"]     = new_staff_office
        doc["pending_at_staff_name"] = new_staff_full_name
        doc["transfer_status"]       = "pending"
        # NOTE: logged_by is NOT updated here — the receiving staff takes
        # ownership only after they accept via the receive modal.

        remark = (
            f"Batch re-routed to {new_staff_full_name} ({new_staff_office or 'N/A'}). "
            f"Cycle {doc['routing_cycle']} completed."
            if routing_back else
            f"Batch transferred to {recipient_display} ({new_staff_office or 'N/A'})."
        )
        # Provenance for group-mate (non-owner, non-admin) transfers — record both
        # the actor and the original owner without overwriting any owner field.
        doc_owners = {doc.get("original_logged_by"), doc.get("logged_by"), doc.get("accepted_by")}
        if user_role != "admin" and current_user not in doc_owners:
            remark += (
                f" By {current_full_name} — acting on document originated by "
                f"{doc.get('original_logged_by') or 'N/A'}."
            )
        doc.setdefault("travel_log", []).append({
            "office":    new_staff_office or "DepEd Leyte Division Office",
            "action":    action_label,
            "officer":   session.get("full_name") or session.get("username"),
            "timestamp": now_str(),
            "remarks":   remark,
        })
        save_doc(doc)
        transferred_count += 1
        transferred_ids.append(doc_id)

    audit_log("doc_batch_transferred",
              f"count={transferred_count} skipped_unauth={skipped_unauth} "
              f"skipped_missing={skipped_missing} "
              f"to={new_staff or 'office:' + new_staff_office} type={transfer_type}",
              username=session.get("username","?"), ip=get_client_ip())

    # Honest feedback — never flash success when nothing actually transferred,
    # and surface skipped docs instead of silently dropping them.
    if transferred_count == 0:
        flash(
            f"No documents were transferred. "
            f"{skipped_unauth} not permitted, {skipped_missing} not found.",
            "error"
        )
        return redirect(url_for("dashboard.index"))

    if skipped_unauth or skipped_missing:
        flash(
            f"{transferred_count} document(s) transferred to {recipient_display} at "
            f"{new_staff_office or 'N/A'}. Skipped {skipped_unauth} not permitted, "
            f"{skipped_missing} not found.",
            "warning"
        )
    else:
        flash(
            f"{transferred_count} document(s) transferred to {recipient_display} at "
            f"{new_staff_office or 'N/A'}. Status changed to Routed",
            "success"
        )

    # EXTERNAL transfer (destination office differs from sender's office) →
    # one routing slip for the whole batch (all docs share new_staff_office),
    # then go to the printable slip page. INTERNAL transfers are unchanged.
    is_external = new_staff_office.strip().lower() != current_office.strip().lower()
    if is_external and transferred_count:
        from services.misc import build_transfer_slip
        slip_id = build_transfer_slip(
            id_list, new_staff_office, current_office,
            current_full_name, new_staff_full_name or new_staff_office,
        )
        # Scoped cart clear on the slip page: remove only the transferred docs,
        # leaving any un-transferred docs in the user's cart. routing_slip.html
        # honors ?cleared_ids=...
        return redirect(url_for("offices.view_routing_slip", slip_id=slip_id,
                                cleared_ids=",".join(transferred_ids)))

    # Scoped cart clear: remove only the transferred docs from the cart.
    return redirect(url_for("dashboard.index", cleared_ids=",".join(transferred_ids)))


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
@login_required
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

def _is_active_transfer(doc: dict) -> bool:
    """
    Return True if this document is currently in-transit (awaiting acceptance
    by anyone).  Used by the admin receive modal to show all pending docs
    system-wide.  Covers both current docs (transfer_status="pending") and
    legacy docs routed before that field was introduced.
    """
    if doc.get("deleted"):
        return False
    ts = (doc.get("transfer_status") or "").strip()
    pending_staff  = (doc.get("pending_at_staff") or "").strip()
    pending_office = (doc.get("pending_at_office") or "").strip()
    # Primary: explicit flag
    if ts == "pending":
        return True
    # Legacy: no flag but routing fields are set and not yet accepted
    if not ts and (pending_staff or pending_office) and not doc.get("accepted_by"):
        return True
    return False


def _is_pending_for(doc: dict, username: str, office: str) -> bool:
    """
    Return True if this document is actively awaiting acceptance by the given
    user or office.

    Two paths are checked:
      1. Primary   — transfer_status == "pending" (set by all current transfer
                     routes).  Works correctly even for previously-accepted docs
                     that have been re-transferred, because transfer_status is
                     always reset to "pending" on each new transfer.
      2. Legacy    — transfer_status is absent/blank but pending_at_staff is set
                     and the doc has not yet been accepted.  Covers docs that were
                     routed with older code before transfer_status was introduced.
    """
    if doc.get("deleted"):
        return False

    pending_staff  = (doc.get("pending_at_staff") or "").strip()
    pending_office = (doc.get("pending_at_office") or "").strip().lower()
    office_lower   = (office or "").strip().lower()
    ts             = (doc.get("transfer_status") or "").strip()

    def _matches_user():
        if pending_staff and pending_staff == username:
            return True
        if not pending_staff and pending_office and office_lower and pending_office == office_lower:
            return True
        return False

    # ── Primary: explicit "pending" transfer_status ────────────────────────
    if ts == "pending":
        return _matches_user()

    # ── Legacy: no transfer_status but pending_at_staff is set and not yet
    #    accepted (covers docs routed before transfer_status was introduced) ─
    if not ts and pending_staff and not doc.get("accepted_by"):
        return _matches_user()

    return False


@dashboard_bp.route("/pending-documents")
@login_required
def get_pending_documents():
    """Get all documents pending acceptance for the current user."""
    current_user = session.get("username", "")
    current_role = session.get("role", "")
    current_office = session.get("office", "")

    if not current_user:
        return jsonify([])

    docs = load_docs()

    if current_role == "admin":
        # Admins see ALL currently-pending docs system-wide (primary + legacy).
        pending = [d for d in docs if _is_active_transfer(d)]
    else:
        pending = [d for d in docs if _is_pending_for(d, current_user, current_office)]

    # ── Optional filters ──────────────────────────────────────────────────────
    filter_cat  = request.args.get("cat",  "").strip()
    filter_date = request.args.get("date", "").strip()

    if filter_cat:
        pending = [d for d in pending
                   if (d.get("category") or "").strip().lower() == filter_cat.lower()]

    if filter_date:
        def _pending_date(d):
            # Use last transfer travel_log entry first, then updated_at, then created_at
            tl = d.get("travel_log") or []
            for entry in reversed(tl):
                if "transfer" in (entry.get("action") or "").lower():
                    ts = entry.get("timestamp", "")
                    if ts:
                        return ts.replace("T", " ")[:10]
            return (d.get("updated_at") or d.get("created_at") or "")[:10]

        pending = [d for d in pending if _pending_date(d) == filter_date]

    from services.auth import get_user as _gub
    for d in pending:
        ps = d.get('pending_at_staff')
        if ps and not d.get('pending_at_staff_name'):
            ps_user = _gub(ps)
            d['pending_at_staff_name'] = (ps_user.get('full_name') or ps) if ps_user else ps
        ifu = d.get('intended_for_username')
        if ifu and not d.get('intended_for_name'):
            ifu_user = _gub(ifu)
            d['intended_for_name'] = (ifu_user.get('full_name') or ifu) if ifu_user else ifu

    # Search filter (search ∩ category ∩ date). Applied AFTER name resolution so
    # intended_for_name is searchable. Mirrors the dashboard _matches() style:
    # a lowercased substring match over the fields the modal surfaces.
    filter_search = request.args.get("search", "").strip().lower()
    if filter_search:
        def _pending_matches(d, q):
            haystack = " ".join([
                d.get("doc_name",          "") or "",
                d.get("doc_id",            "") or "",
                d.get("sender_name",       "") or "",
                d.get("sender_org",        "") or "",
                d.get("category",          "") or "",
                d.get("transferred_by",    "") or "",
                d.get("intended_for_name", "") or "",
            ]).lower()
            return q in haystack
        pending = [d for d in pending if _pending_matches(d, filter_search)]

    # ── Pagination of the FILTERED result ─────────────────────────────────────
    # total is the FILTERED count (so search/category/date drive the page count),
    # computed BEFORE slicing. Only the requested page is returned.
    import math
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", 20))
    except (TypeError, ValueError):
        per_page = 20
    per_page = max(1, min(per_page, 100))   # clamp to a sane bound

    total       = len(pending)
    total_pages = max(1, math.ceil(total / per_page))
    if page > total_pages:
        page = total_pages                   # clamp so an out-of-range page returns the last page
    start     = (page - 1) * per_page
    page_docs = pending[start:start + per_page]

    return jsonify({
        "docs":        page_docs,
        "page":        page,
        "per_page":    per_page,
        "total":       total,
        "total_pages": total_pages,
    })


@dashboard_bp.route("/pending-count")
@login_required
def get_pending_count():
    """Get count of documents pending acceptance for the current user."""
    current_user = session.get("username", "")
    current_role = session.get("role", "")
    current_office = session.get("office", "")

    if not current_user:
        return jsonify({"count": 0})

    docs = load_docs()

    if current_role == "admin":
        count = sum(1 for d in docs if _is_active_transfer(d))
    else:
        count = sum(1 for d in docs if _is_pending_for(d, current_user, current_office))

    return jsonify({"count": count})


@dashboard_bp.route("/api/office-staff")
@login_required
def api_office_staff_list():
    """Return staff/admin users for a given office (session-protected).
    Used by the post-accept forward dialog in base.js."""
    office = request.args.get("office", "").strip().lower()
    from services.auth import get_all_users
    all_users = get_all_users()
    staff = [
        {"username": u.get("username", ""), "full_name": u.get("full_name") or u.get("username", "")}
        for u in all_users
        if u.get("role") in ("staff", "admin")
        and (not office or (u.get("office") or "").strip().lower() == office)
    ]
    staff.sort(key=lambda s: (s.get("full_name") or "").lower())
    return jsonify(staff)


@dashboard_bp.route("/accept-document/<doc_id>", methods=["POST"])
@login_required
def accept_document(doc_id):
    """Accept a transferred document."""
    current_user = session.get("username", "")
    current_full_name = session.get("full_name", "")
    current_office = session.get("office", "") or ""
    
    doc = get_doc(doc_id)
    if not doc:
        return jsonify({"ok": False, "error": "Document not found."}), 404

    # Verify this document is pending for the current user OR pending at their office
    pending_staff = doc.get("pending_at_staff", "")
    pending_office = doc.get("pending_at_office", "").strip().lower()
    current_office_lower = current_office.strip().lower()

    is_authorized = (
        pending_staff == current_user  # Specifically assigned to this staff
        or (pending_staff == "" and pending_office == current_office_lower and current_office_lower)  # Pending at office, any staff can accept
    )

    if not is_authorized:
        return jsonify({"ok": False, "error": "You are not authorized to accept this document."}), 403

    # Allow acceptance as long as the doc isn't currently in an accepted state.
    # Checking transfer_status (not accepted_by) ensures that after a transfer
    # resets transfer_status to "pending", Staff B can accept even if accepted_by
    # was previously set by the primary recipient.
    if doc.get("transfer_status") == "accepted":
        return jsonify({"ok": False, "error": "This document has already been accepted."}), 400

    try:
        receiving_office = doc.get("pending_at_office", "") or doc.get("transferred_to_office", "")
        doc["transfer_status"]   = "accepted"
        doc["accepted_by"]       = current_user
        doc["accepted_by_name"]  = current_full_name or current_user
        doc["accepted_at"]       = now_str()
        doc["status"]            = "Received"
        doc["logged_by"]         = current_user        # ← transfer ownership now
        if not doc.get("date_received"):
            doc["date_received"] = now_str()[:16].replace("T", " ")
        doc["pending_at_staff"]  = ""
        doc["pending_at_office"] = ""
        # original_logged_by is intentionally NOT touched here

        doc.setdefault("travel_log", []).append({
            "office":    receiving_office,
            "action":    "Document Received",
            "officer":   current_full_name or current_user,
            "timestamp": now_str(),
            "remarks":   (
                f"Document received and accepted by {current_full_name or current_user}. "
                f"Routing cycle {doc.get('routing_cycle', 0) + 1} in progress."
            ),
        })

        save_doc(doc)

        audit_log("doc_accepted",
                  f"doc_id={doc_id} accepted_by={current_user} doc_name={doc.get('doc_name','')[:60]}",
                  username=current_user, ip=get_client_ip())

        return jsonify({"ok": True, "doc_id": doc_id})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error accepting document: {e}"}), 500


@dashboard_bp.route("/reject-document/<doc_id>", methods=["POST"])
@login_required
def reject_document(doc_id):
    """Reject a transferred document with a reason."""
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    current_user = session.get("username", "")
    current_full_name = session.get("full_name", "")
    current_office = session.get("office", "") or ""
    rejection_reason = request.form.get("rejection_reason", "").strip()

    if not rejection_reason:
        if is_ajax:
            return jsonify({"ok": False, "error": "Rejection reason is required"}), 400
        flash("Please provide a reason for rejection.", "error")
        return redirect(url_for("dashboard.index"))

    doc = get_doc(doc_id)
    if not doc:
        if is_ajax:
            return jsonify({"ok": False, "error": "Document not found"}), 404
        flash("Document not found.", "error")
        return redirect(url_for("dashboard.index"))

    # Verify this document is pending for the current user OR pending at their office
    pending_staff = doc.get("pending_at_staff", "")
    pending_office = doc.get("pending_at_office", "").strip().lower()
    current_office_lower = current_office.strip().lower()

    is_authorized = (
        pending_staff == current_user  # Specifically assigned to this staff
        or (pending_staff == "" and pending_office == current_office_lower and current_office_lower)  # Pending at office, any staff can reject
    )

    if not is_authorized:
        if is_ajax:
            return jsonify({"ok": False, "error": "Not authorized to reject this document"}), 403
        flash("You are not authorized to reject this document.", "error")
        return redirect(url_for("dashboard.index"))

    # Allow rejection as long as the doc hasn't already been accepted.
    if doc.get("accepted_by"):
        if is_ajax:
            return jsonify({"ok": False, "error": "Document already accepted and cannot be rejected"}), 400
        flash("This document has already been accepted and cannot be rejected.", "error")
        return redirect(url_for("dashboard.index"))

    # Resolve the staff member who originally sent/owns this document.
    # Fall back chain: original_logged_by → transferred_by → current rejector (safe fallback).
    original_sender = (
        doc.get("original_logged_by")
        or doc.get("transferred_by")
        or current_user
    )

    rejecting_office = doc.get("pending_at_office", "")

    # Update document status
    doc["transfer_status"] = "rejected"
    doc["rejected_by"] = current_user
    doc["rejected_by_name"] = current_full_name or current_user
    doc["rejected_at"] = now_str()
    doc["rejection_reason"] = rejection_reason
    doc["status"] = "Rejected"

    # Return document to the sender — clear pending fields so it
    # goes straight back to the sender's dashboard, not receive modal.
    doc["logged_by"]         = original_sender
    doc["pending_at_office"] = ""
    doc["pending_at_staff"]  = ""

    # Add to travel log
    doc.setdefault("travel_log", []).append({
        "office":    rejecting_office,
        "action":    "Document Rejected",
        "officer":   current_full_name or current_user,
        "timestamp": now_str(),
        "remarks":   f"Document rejected by {current_full_name or current_user}. Reason: {rejection_reason}",
    })

    save_doc(doc)

    audit_log("doc_rejected",
              f"doc_id={doc_id} rejected_by={current_user} reason={rejection_reason[:50]} doc_name={doc.get('doc_name','')[:60]}",
              username=current_user, ip=get_client_ip())

    if is_ajax:
        return jsonify({"ok": True})
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


@dashboard_bp.route("/api/dropdown-options")
@login_required
def get_dropdown_options_api():
    """
    API endpoint to get dropdown options for a specific field.
    Query params:
        - field: The field name (category, status, sender_org, referred_to)
    Returns JSON list of options.
    """
    field_name = request.args.get("field", "").strip().lower()
    
    # If no field specified, return all available fields with their options
    if not field_name:
        from services.dropdown_options import get_all_dropdown_configs, MANAGEABLE_FIELDS
        all_configs = get_all_dropdown_configs()
        return jsonify(all_configs)
    
    # Get options for specific field
    valid_fields = ["category", "status", "sender_org", "referred_to"]
    if field_name not in valid_fields:
        return jsonify({"error": f"Invalid field. Valid fields: {', '.join(valid_fields)}"}), 400
    
    options = get_dropdown_options(field_name)
    return jsonify(options)


@dashboard_bp.route("/dropdown-options", methods=["GET"])
@login_required
def manage_dropdowns():
    """
    Admin page to manage all dropdown options.
    """
    from services.dropdown_options import get_all_dropdown_configs
    configs = get_all_dropdown_configs()
    return render_template("manage_dropdowns.html", configs=configs)


@dashboard_bp.route("/dropdown-options/edit/<field_name>", methods=["GET"])
@login_required
def edit_dropdown(field_name):
    """
    Admin page to edit a specific dropdown's options.
    """
    from services.dropdown_options import get_all_dropdown_configs, MANAGEABLE_FIELDS
    
    # Validate field_name
    if field_name not in MANAGEABLE_FIELDS:
        flash(f"Invalid field: {field_name}", "error")
        return redirect(url_for("dashboard.manage_dropdowns"))
    
    configs = get_all_dropdown_configs()
    if field_name not in configs:
        flash(f"No configuration found for {field_name}", "error")
        return redirect(url_for("dashboard.manage_dropdowns"))
    
    config = configs[field_name]
    display_name = config.get("display_name", field_name.title())
    
    return render_template("edit_dropdown.html", 
                          field_name=field_name,
                          display_name=display_name,
                          config=config)


@dashboard_bp.route("/dropdown-options/save/<field_name>", methods=["POST"])
@login_required
def save_dropdown(field_name):
    """
    Save dropdown options for a specific field.
    """
    from services.dropdown_options import update_dropdown_options, MANAGEABLE_FIELDS
    
    # Validate field_name
    if field_name not in MANAGEABLE_FIELDS:
        flash(f"Invalid field: {field_name}", "error")
        return redirect(url_for("dashboard.manage_dropdowns"))
    
    # Get options from form - handle both newline-separated and comma-separated
    options_raw = request.form.get("options", "").strip()
    
    # Split by newline or comma
    if "\n" in options_raw:
        options = [opt.strip() for opt in options_raw.split("\n") if opt.strip()]
    else:
        options = [opt.strip() for opt in options_raw.split(",") if opt.strip()]
    
    success, message = update_dropdown_options(field_name, options)
    
    if success:
        flash(message, "success")
    else:
        flash(message, "error")
    
    return redirect(url_for("dashboard.manage_dropdowns"))


@dashboard_bp.route("/dropdown-options/reset/<field_name>", methods=["POST"])
@login_required
def reset_dropdown(field_name):
    """
    Reset dropdown options to default for a specific field.
    Returns JSON for AJAX requests, redirects for form submissions.
    """
    from services.dropdown_options import reset_to_default, MANAGEABLE_FIELDS
    
    # Validate field_name
    if field_name not in MANAGEABLE_FIELDS:
        message = f"Invalid field: {field_name}"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"success": False, "message": message}), 400
        flash(message, "error")
        return redirect(url_for("dashboard.manage_dropdowns"))
    
    success, message = reset_to_default(field_name)
    
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"success": success, "message": message})
    
    if success:
        flash(message, "success")
    else:
        flash(message, "error")
    
    return redirect(url_for("dashboard.manage_dropdowns"))


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


@dashboard_bp.route("/admin/backfill-logged-office", methods=["POST"])
@admin_required
def backfill_logged_office():
    docs = load_docs()
    updated = 0
    for doc in docs:
        if doc.get("logged_by_office"):
            continue  # already has it, skip
        
        # Try to get it from the first travel log entry
        travel_log = doc.get("travel_log", [])
        if travel_log:
            first_entry = travel_log[0]
            office = first_entry.get("office", "")
            if office:
                doc["logged_by_office"] = office
                save_doc(doc)
                updated += 1
    
    return jsonify({"updated": updated, "total": len(docs)})


# ── Export current filtered view to CSV ──────────────────────────────────────

@dashboard_bp.route("/export-csv")
@login_required
def export_csv():
    """Export the current filtered document list as a CSV download."""
    current_username = session.get("username", "")
    user_role        = session.get("role", "")
    docs = load_docs()
    if user_role != "admin":
        docs = [
            d for d in docs
            if d.get("original_logged_by") == current_username
            or d.get("logged_by") == current_username
            or d.get("received_by") == current_username
            or d.get("accepted_by") == current_username
            or d.get("transferred_by") == current_username
        ]

    search        = request.args.get("search", "").lower()
    filter_status = request.args.get("status", "All")
    filter_source = request.args.get("source", "All")
    filter_date   = request.args.get("date", "").strip()
    filter_cat    = request.args.get("cat", "All")
    filter_staff  = request.args.get("staff", "All")

    if search:
        docs = [d for d in docs if search in " ".join([
            d.get("doc_name",""), d.get("doc_id",""), d.get("sender_name",""),
            d.get("sender_org",""), d.get("referred_to",""), d.get("notes",""),
        ]).lower()]
    if filter_status != "All":
        docs = [d for d in docs if d.get("status") == filter_status]
    if filter_source == "Staff":
        docs = [d for d in docs if d.get("logged_by") and not d.get("submitted_by")]
    elif filter_source == "Client":
        docs = [d for d in docs if d.get("submitted_by")]
    if filter_date:
        docs = [d for d in docs if (d.get("date_received") or d.get("created_at",""))[:10] == filter_date]
    if filter_cat and filter_cat != "All":
        docs = [d for d in docs if (d.get("category") or "").lower() == filter_cat.lower()]
    if filter_staff and filter_staff != "All":
        docs = [d for d in docs if d.get("received_by") == filter_staff or d.get("logged_by") == filter_staff]

    output = _io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Ref No.", "Document", "Category", "Sender", "Sender Org",
                     "Referred To", "Status", "Date Logged", "Remarks"])
    for d in docs:
        writer.writerow([
            d.get("doc_id",""), d.get("doc_name",""), d.get("category",""),
            d.get("sender_name",""), d.get("sender_org",""), d.get("referred_to",""),
            d.get("status",""),
            (d.get("created_at") or "")[:10], d.get("notes","") or d.get("description",""),
        ])
    output.seek(0)
    return send_file(
        BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="documents_export.csv",
    )


# ── Quick note update ─────────────────────────────────────────────────────────

@dashboard_bp.route("/quick-note/<doc_id>", methods=["POST"])
@login_required
def quick_note(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        return jsonify({"ok": False, "msg": "Not found"}), 404
    note = request.form.get("note", "").strip()
    doc["notes"] = note
    try:
        save_doc(doc)
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500
    audit_log("note_updated", f"doc_id={doc_id}", username=session.get("username","?"), ip=get_client_ip())
    return jsonify({"ok": True})


# ── Travel log quick-view ─────────────────────────────────────────────────────

@dashboard_bp.route("/travel-log/<doc_id>")
@login_required
def travel_log_json(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        return jsonify({"ok": False, "msg": "Not found"}), 404
    return jsonify({"ok": True, "doc_name": doc.get("doc_name",""), "travel_log": doc.get("travel_log", [])})


# ── Duplicate document check ──────────────────────────────────────────────────

@dashboard_bp.route("/check-duplicate")
@login_required
def check_duplicate():
    q = request.args.get("q", "").strip().lower()
    if len(q) < 5:
        return jsonify({"duplicates": []})
    current_username = session.get("username", "")
    cutoff = now_str()[:10]  # today
    # Look at docs logged in the past 14 days by this office
    current_office = session.get("office", "")
    docs = load_docs()
    recent = [
        d for d in docs
        if (d.get("logged_by_office") == current_office or d.get("logged_by") == current_username)
        and (d.get("created_at") or "")[:10] >= cutoff[:7] + "-01"  # within current month-ish
    ]
    matches = []
    for d in recent:
        name = (d.get("doc_name") or "").lower()
        ratio = difflib.SequenceMatcher(None, q, name).ratio()
        if ratio >= 0.75 or q in name:
            matches.append({
                "id":       d["id"],
                "doc_name": d.get("doc_name",""),
                "doc_id":   d.get("doc_id",""),
                "status":   d.get("status",""),
                "date":     (d.get("created_at") or "")[:10],
            })
        if len(matches) >= 5:
            break
    return jsonify({"duplicates": matches})


# ── QR Print Queue routes disabled ──────────────────────────────────────────
# @dashboard_bp.route("/staff/print-qr-sheet")
# @login_required
# def print_qr_sheet():
#     ids = request.args.get('ids', '')
#     doc_ids = [i.strip() for i in ids.split(',') if i.strip()]
#     docs = []
#     for doc_id in doc_ids:
#         doc = get_doc(doc_id)
#         if doc and not doc.get('deleted'):
#             qr_b64 = generate_qr_b64(doc, request.host_url)
#             docs.append({
#                 'id':         doc.get('id'),
#                 'doc_name':   doc.get('doc_name', 'Unnamed'),
#                 'doc_id':     doc.get('doc_id', ''),
#                 'created_at': (doc.get('created_at') or '')[:10],
#                 'office':     doc.get('logged_by_office', ''),
#                 'qr_b64':     qr_b64,
#             })
#     return render_template('print_qr_sheet.html', docs=docs)
#
#
# @dashboard_bp.route("/staff/mark-qr-printed", methods=["POST"])
# @login_required
# def mark_qr_printed():
#     data = request.get_json(force=True, silent=True) or {}
#     ids = data.get('ids', [])
#     for doc_id in ids:
#         doc = get_doc(doc_id)
#         if doc:
#             doc['qr_printed'] = True
#             doc['updated_at'] = now_str()
#             save_doc(doc)
#     return jsonify(ok=True)


@dashboard_bp.route("/staff/appointments")
@login_required
def staff_appointments():
    if session.get("role") not in ("staff", "admin"):
        return redirect(url_for("dashboard.index"))
    current_username = session.get("username", "")
    current_office   = session.get("office", "")
    current_role     = session.get("role", "")

    if current_role == "admin":
        appointments = get_all_appointments()
    else:
        appointments = get_all_appointments(office=current_office)

    all_users = get_all_users()
    if current_role == "admin":
        office_staff = sorted([
            {"username": u["username"], "full_name": u.get("full_name") or u["username"]}
            for u in all_users
            if u.get("role") != "client" and u.get("active", True)
        ], key=lambda x: x["full_name"])
    else:
        office_staff = sorted([
            {"username": u["username"], "full_name": u.get("full_name") or u["username"]}
            for u in all_users
            if u.get("office") == current_office
            and u.get("role") != "client"
            and u.get("active", True)
        ], key=lambda x: x["full_name"])

    pending_count = len([a for a in appointments if a.get("status") == "pending"])

    return render_template("staff_appointments.html",
                           appointments=appointments,
                           office_staff=office_staff,
                           pending_count=pending_count,
                           current_office=current_office,
                           current_role=current_role)


@dashboard_bp.route("/staff/appointments/<apt_id>/confirm", methods=["POST"])
@login_required
def staff_confirm_appointment(apt_id):
    if session.get("role") not in ("staff", "admin"):
        return redirect(url_for("dashboard.index"))
    data = request.get_json(force=True, silent=True) or {}
    assigned_to      = data.get("assigned_to", "")
    assigned_to_name = data.get("assigned_to_name", "")
    notes            = data.get("notes", "")

    status = data.get("status", "confirmed")
    success = update_appointment(apt_id, {
        "status":           status,
        "assigned_to":      assigned_to,
        "assigned_to_name": assigned_to_name,
        "notes":            notes,
    })
    if success:
        return jsonify(ok=True)
    return jsonify(ok=False, error="Appointment not found"), 404


@dashboard_bp.route("/staff/appointments/<apt_id>/reject", methods=["POST"])
@login_required
def staff_reject_appointment(apt_id):
    if session.get("role") not in ("staff", "admin"):
        return redirect(url_for("dashboard.index"))
    data   = request.get_json(force=True, silent=True) or {}
    reason = data.get("reason", "")

    success = update_appointment(apt_id, {
        "status": "cancelled",
        "notes":  reason,
    })
    if success:
        return jsonify(ok=True)
    return jsonify(ok=False, error="Appointment not found"), 404