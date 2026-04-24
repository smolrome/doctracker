"""
routes/offices.py — Office QR page, routing slips, welcome page.
"""
import re
import uuid

from flask import (Blueprint, flash, redirect, render_template,
                   request, send_file, session, url_for)
from io import BytesIO

from services.auth import get_all_users
from services.documents import get_doc, now_str
from services.misc import (
    audit_log, delete_saved_office, get_office_traffic_today,
    generate_slip_no, get_existing_offices_without_qr, get_routing_slip, load_saved_offices,
    save_office, save_routing_slip,
)
from services.qr import make_office_qr_png, get_base_url
from utils import admin_required, get_client_ip, is_logged_in, login_required
from config import APP_URL, CLIENT_REG_CODE

offices_bp = Blueprint("offices", __name__)


# ── Office QR management page ─────────────────────────────────────────────────

@offices_bp.route("/office-qr-page", methods=["GET", "POST"])
@admin_required
def office_qr_page():
    base = get_base_url(request.host_url)

    if request.method == "POST" and request.form.get("_action") == "delete_office":
        slug = request.form.get("office_slug", "").strip()
        if slug:
            delete_saved_office(slug)
            flash("Office removed.", "success")
        return redirect(url_for("offices.office_qr_page"))

    office_name = (request.args.get("office", "").strip()
                   or request.form.get("office_name", "").strip())
    primary_recipient = request.form.get("primary_recipient", "").strip()
    qr_data = None

    def make_slug(name, suffix):
        return re.sub(r'\s+', '-', name.strip()) + suffix

    if office_name:
        save_office(office_name, session.get("username", ""), primary_recipient)
        qr_data = {
            "reg": make_slug(office_name, "-reg"),
            "sub": make_slug(office_name, "-sub"),
            "rec": make_slug(office_name, "-rec"),
            "rel": make_slug(office_name, "-rel"),
        }
        office_traffic = get_office_traffic_today(
            re.sub(r'\s+', '-', office_name.strip().lower())
        )
    else:
        office_traffic = None

    # Get all staff members for the dropdown
    all_users = get_all_users()
    staff_members = [u for u in all_users if u.get("role") in ("staff", "admin")]

    # Get existing offices that don't have QR codes yet
    existing_offices = get_existing_offices_without_qr()

    return render_template("office_qr_page.html",
                           base=base,
                           office_name=office_name,
                           qr_data=qr_data,
                           office_traffic=office_traffic,
                           saved_offices=load_saved_offices(),
                           existing_offices=existing_offices,
                           client_reg_code=CLIENT_REG_CODE,
                           staff_members=staff_members)


# ── Office Staff List page ───────────────────────────────────────────────────

@offices_bp.route("/office-staff")
@admin_required
def office_staff():
    """Display list of offices with their staff members."""
    from services.auth import get_all_users
    from services.misc import load_saved_offices
    
    # Get all users with office assignments
    all_users = get_all_users()
    saved_offices = load_saved_offices()
    
    # Build office_staff list from saved_offices
    office_staff_list = []
    for office in saved_offices:
        office_slug = office.get('office_slug', '')
        office_name = office.get('office_name', '')
        
        # Get staff assigned to this office
        staff = [u for u in all_users if u.get('office', '').strip().lower() == office_name.strip().lower()]
        
        office_staff_list.append({
            'office_name': office_name,
            'office_slug': office_slug,
            'created_by': office.get('created_by', ''),
            'primary_recipient': office.get('primary_recipient', ''),
            'staff_count': len(staff),
            'staff': staff
        })
    
    return render_template("office_staff.html",
                           office_staff=office_staff_list,
                           office_staff_json={office['office_slug']: office['staff'] for office in office_staff_list})


@offices_bp.route("/update-office-recipient", methods=["POST"])
@admin_required
def update_office_recipient():
    """Update the primary recipient for an office."""
    from services.misc import update_office_primary_recipient
    
    office_slug = request.form.get("office_slug", "").strip()
    primary_recipient = request.form.get("primary_recipient", "").strip()
    
    if office_slug:
        update_office_primary_recipient(office_slug, primary_recipient)
        flash("Primary recipient updated successfully.", "success")
    
    return redirect(url_for("offices.office_staff"))


@offices_bp.route("/delete-office/<slug>", methods=["POST"])
@admin_required
def delete_office(slug):
    """Delete an office and clear office assignments from all staff."""
    from services.misc import delete_saved_office
    
    if slug:
        delete_saved_office(slug)
        flash("Office removed successfully.", "success")
    
    return redirect(url_for("offices.office_staff"))


# ── Welcome / public page ─────────────────────────────────────────────────────

@offices_bp.route("/welcome")
def welcome():
    base = get_base_url(request.host_url)
    return render_template("welcome.html",
                           saved_offices=load_saved_offices(),
                           base=base,
                           logged_in=is_logged_in(),
                           current_role=session.get("role", ""),
                           current_user=(session.get("full_name")
                                         or session.get("username", "")))


@offices_bp.route("/app-qr.png")
@login_required
def app_qr():
    if session.get("role") != "admin":
        return "Admin only", 403
    base = get_base_url(request.host_url)
    import qrcode
    qr = qrcode.QRCode(version=None,
                       error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=10, border=4)
    qr.add_data(f"{base}/welcome")
    qr.make(fit=True)
    buf = BytesIO()
    qr.make_image(fill_color="#0A2540", back_color="white").save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png",
                     download_name="doctracker-app-qr.png")


@offices_bp.route("/client-reg-qr.png")
@login_required
def client_reg_qr():
    return redirect(url_for("offices.app_qr"))


# ── Routing slips ─────────────────────────────────────────────────────────────

@offices_bp.route("/routing-slip/create", methods=["POST"])
@login_required
def create_routing_slip():
    doc_ids_raw = request.form.get("doc_ids", "").strip()
    destination = request.form.get("destination", "").strip()
    notes       = request.form.get("notes", "").strip()

    if not doc_ids_raw or not destination:
        flash("Please select documents and enter a destination office.", "error")
        return redirect(url_for("dashboard.index"))

    doc_ids = [d.strip() for d in doc_ids_raw.split(",") if d.strip()]
    if not doc_ids:
        flash("No valid document IDs selected.", "error")
        return redirect(url_for("dashboard.index"))

    actor       = session.get("full_name") or session.get("username") or "Staff"
    from_office = session.get("office") or "DepEd Leyte Division"
    slip_date   = request.form.get("slip_date", "").strip() or now_str()[:10]

    from services.documents import save_doc
    from services.qr import create_slip_token, make_slip_qr_png, APP_URL
    import base64

    slip_id  = str(uuid.uuid4())[:8].upper()
    slip_no  = generate_slip_no()

    # Generate SLIP-level QR tokens
    recv_token = create_slip_token(slip_id, "SLIP_RECEIVE")
    rel_token  = create_slip_token(slip_id, "SLIP_RELEASE")

    slip = {
        "id":           slip_id,
        "slip_no":      slip_no,
        "destination":  destination,
        "from_office":  from_office,
        "prepared_by":  actor,
        "doc_ids":      doc_ids,
        "notes":        notes,
        "slip_date":    slip_date,
        "time_from":    request.form.get("time_from", "").strip(),
        "time_to":      request.form.get("time_to", "").strip(),
        "created_at":   now_str(),
        "recv_token":   recv_token,
        "rel_token":    rel_token,
        "status":       "Routed",
    }
    save_routing_slip(slip)

    # Update every document: Routed + store from/to office
    for doc_id in doc_ids:
        doc = get_doc(doc_id)
        if doc:
            doc["status"]          = "Routed"
            doc["forwarded_to"]    = destination
            doc["from_office"]     = from_office
            doc["routing_slip_id"] = slip_id
            doc["routing_slip_no"] = slip_no
            
            # Create the travel log entry
            new_entry = {
                "office":    from_office,
                "action":    f"Released — Routed to {destination}",
                "officer":   actor,
                "timestamp": now_str(),
                "remarks":   f"Routing slip {slip_no}. Forwarded from {from_office} → {destination}.",
                "slip_no":   slip_no,
            }
            
            # Check if the last entry is a duplicate (same slip_no)
            travel_log = doc.get("travel_log", [])
            if not travel_log or travel_log[-1].get("slip_no") != slip_no:
                travel_log.append(new_entry)
                doc["travel_log"] = travel_log
            
            save_doc(doc)

    audit_log("routing_slip_created",
              f"slip_no={slip_no} from={from_office} dest={destination} "
                  f"docs={len(doc_ids)} ids={','.join(str(x) for x in doc_ids[:5])}",
              username=session.get("username", ""), ip=get_client_ip())
    flash(f"✅ Routing slip {slip_no} created successfully!", "success")
    return redirect(url_for("offices.view_routing_slip", slip_id=slip_id) + "?cart_cleared=1")


@offices_bp.route("/routing-slip/create-grouped", methods=["POST"])
@login_required
def create_grouped_routing_slip():
    """Create multiple routing slips based on referred_to grouping."""
    import json
    
    grouped_routing_raw = request.form.get("grouped_routing", "").strip()
    notes = request.form.get("grouped_notes", "").strip()
    slip_date = request.form.get("grouped_slip_date", "").strip() or now_str()[:10]
    time_from = request.form.get("grouped_time_from", "").strip()
    time_to = request.form.get("grouped_time_to", "").strip()
    
    if not grouped_routing_raw:
        flash("No grouped routing data provided.", "error")
        return redirect(url_for("dashboard.index"))
    
    try:
        groups = json.loads(grouped_routing_raw)
    except json.JSONDecodeError:
        flash("Invalid grouping data.", "error")
        return redirect(url_for("dashboard.index"))
    
    if not groups:
        flash("No document groups to route.", "error")
        return redirect(url_for("dashboard.index"))
    
    actor = session.get("full_name") or session.get("username") or "Staff"
    from_office = session.get("office") or "DepEd Leyte Division"
    
    from services.documents import save_doc
    from services.qr import create_slip_token, make_slip_qr_png, APP_URL
    import base64
    
    created_slips = []
    
    for destination, doc_ids in groups.items():
        # Skip empty/no referred to groups
        if destination == "(No Referred To)" or not destination:
            continue
            
        if not doc_ids:
            continue
        
        slip_id = str(uuid.uuid4())[:8].upper()
        slip_no = generate_slip_no()
        
        # Generate SLIP-level QR tokens
        recv_token = create_slip_token(slip_id, "SLIP_RECEIVE")
        rel_token = create_slip_token(slip_id, "SLIP_RELEASE")
        
        slip = {
            "id": slip_id,
            "slip_no": slip_no,
            "destination": destination,
            "from_office": from_office,
            "prepared_by": actor,
            "doc_ids": doc_ids,
            "notes": notes,
            "slip_date": slip_date,
            "time_from": time_from,
            "time_to": time_to,
            "created_at": now_str(),
            "recv_token": recv_token,
            "rel_token": rel_token,
            "status": "Routed",
            "is_grouped": True,
        }
        save_routing_slip(slip)
        
        # Update every document in this group
        for doc_id in doc_ids:
            doc = get_doc(doc_id)
            if doc:
                doc["status"] = "Routed"
                doc["forwarded_to"] = destination
                doc["from_office"] = from_office
                doc["routing_slip_id"] = slip_id
                doc["routing_slip_no"] = slip_no
                
                # Create the travel log entry
                new_entry = {
                    "office": from_office,
                    "action": f"Released — Routed to {destination}",
                    "officer": actor,
                    "timestamp": now_str(),
                    "remarks": f"Routing slip {slip_no}. Forwarded from {from_office} → {destination}.",
                    "slip_no": slip_no,
                }
                
                travel_log = doc.get("travel_log", [])
                if not travel_log or travel_log[-1].get("slip_no") != slip_no:
                    travel_log.append(new_entry)
                    doc["travel_log"] = travel_log
                
                save_doc(doc)
        
        created_slips.append(slip_id)
        
        audit_log("grouped_routing_slip_created",
                  f"slip_no={slip_no} from={from_office} dest={destination} "
                      f"docs={len(doc_ids)} ids={','.join(str(x) for x in doc_ids[:5])}",
                  username=session.get("username", ""), ip=get_client_ip())
    
    if not created_slips:
        flash("No routing slips were created. Please ensure documents have valid 'Referred To' values.", "warning")
        return redirect(url_for("dashboard.index"))
    
    # Store the last slip ID for display
    if created_slips:
        session["last_rerouted_slip_id"] = created_slips[-1]
    
    if len(created_slips) == 1:
        flash(f"✅ 1 routing slip created successfully!", "success")
        return redirect(url_for("offices.view_routing_slip", slip_id=created_slips[0]) + "?cart_cleared=1")
    else:
        flash(f"✅ {len(created_slips)} routing slips created successfully!", "success")
        return redirect(url_for("offices.routed_documents") + "?cart_cleared=1")


@offices_bp.route("/routing-slip/<slip_id>")
@login_required
def view_routing_slip(slip_id):
    slip = get_routing_slip(slip_id)
    if not slip:
        flash("Routing slip not found.", "error")
        return redirect(url_for("dashboard.index"))
    from services.documents import get_docs_by_ids
    docs_map = get_docs_by_ids(slip.get("doc_ids", []))
    docs = [docs_map[did] for did in slip.get("doc_ids", []) if did in docs_map]
    try:
        from services.misc import audit_log as _alog
        from utils import get_client_ip as _ip
        _alog("slip_viewed",
              f"slip_id={slip_id} slip_no={slip.get('slip_no','?')} "
              f"dest={slip.get('destination','?')} docs={len(docs)}",
              username=session.get("username","?"), ip=_ip())
    except Exception:
        pass
    return render_template("routing_slip.html", slip=slip, docs=docs)


@offices_bp.route("/routed-documents")
@login_required
def routed_documents():
    """Staff view — all routing slips with their documents and batch status update."""
    from services.misc import get_all_routing_slips
    from services.documents import get_docs_by_ids
    
    # Get filter parameter (active, archived, or None for all)
    filter_type = request.args.get('filter', 'active')

    # Get search and filter parameters
    search      = request.args.get('search', '').strip()
    dest_filter = request.args.get('destination', '').strip()
    date_from   = request.args.get('date_from', '').strip()
    date_to     = request.args.get('date_to', '').strip()

    slips = get_all_routing_slips(filter_type)

    # Build unique destination list before narrowing slips
    all_destinations = sorted({s.get('destination', '') for s in slips if s.get('destination')})

    # Apply search filter
    if search:
        search_lower = search.lower()
        slips = [s for s in slips if (
            search_lower in (s.get('slip_no') or '').lower() or
            search_lower in (s.get('destination') or '').lower() or
            search_lower in (s.get('prepared_by') or '').lower() or
            search_lower in (s.get('from_office') or '').lower() or
            search_lower in (s.get('rerouted_to') or '').lower() or
            search_lower in (s.get('rerouted_from') or '').lower()
        )]

    # Apply destination filter
    if dest_filter:
        slips = [s for s in slips if (s.get('destination') or '').lower() == dest_filter.lower()]

    # Apply date range filter (compare against slip_date or created_at[:10])
    if date_from:
        slips = [s for s in slips if (s.get('slip_date') or (s.get('created_at') or '')[:10]) >= date_from]
    if date_to:
        slips = [s for s in slips if (s.get('slip_date') or (s.get('created_at') or '')[:10]) <= date_to]

    # Collect every doc_id needed across all slips, fetch in ONE query
    all_ids = [did for slip in slips for did in slip.get("doc_ids", [])]
    docs_map = get_docs_by_ids(all_ids)
    for slip in slips:
        slip["docs"] = [docs_map[did] for did in slip.get("doc_ids", []) if did in docs_map]

    # Pagination
    try:
        per_page = max(1, int(request.args.get("per_page", 10)))
    except ValueError:
        per_page = 10
    if per_page not in (5, 10, 20, 50):
        per_page = 10
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    total       = len(slips)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page        = min(page, total_pages)
    start       = (page - 1) * per_page
    paginated   = slips[start : start + per_page]

    return render_template("routed_documents.html",
                           slips=paginated, total=total,
                           page=page, total_pages=total_pages, per_page=per_page,
                           filter=filter_type, search=search,
                           dest_filter=dest_filter, date_from=date_from, date_to=date_to,
                           all_destinations=all_destinations)


@offices_bp.route("/routing-slip/<slip_id>/batch-status", methods=["POST"])
@login_required
def batch_update_slip_status(slip_id):
    """Batch update status for all documents in a routing slip."""
    from services.misc import get_routing_slip
    from services.misc import audit_log as _audit
    from utils import get_client_ip

    slip = get_routing_slip(slip_id)
    if not slip:
        flash("Routing slip not found.", "error")
        return redirect(url_for("offices.routed_documents"))

    new_status = request.form.get("status", "").strip()
    notes      = request.form.get("notes", "").strip()
    actor      = session.get("full_name") or session.get("username", "Staff")

    if not new_status:
        flash("Please select a status.", "error")
        return redirect(url_for("offices.routed_documents"))

    from services.documents import get_docs_by_ids, batch_save_docs
    from services.misc import now_str

    doc_ids  = slip.get("doc_ids", [])
    docs_map = get_docs_by_ids(doc_ids)   # one query
    log_entry = f"{new_status} — updated via Routing Slip {slip['slip_no']} by {actor}"
    if notes:
        log_entry += f" | Note: {notes}"
    ts = now_str()

    to_save = []
    for doc_id in doc_ids:
        doc = docs_map.get(doc_id)
        if not doc:
            continue
        doc["status"] = new_status
        tl = doc.get("travel_log") or []
        tl.append({
            "office":    new_status,
            "action":    f"Status Updated — {new_status}",
            "officer":   actor,
            "timestamp": ts,
            "remarks":   log_entry,
        })
        doc["travel_log"] = tl
        if new_status == "Received":
            doc["received_by"] = actor
        to_save.append(doc)

    batch_save_docs(to_save)   # one transaction
    updated = len(to_save)

    _audit("batch_status_update",
           f"slip_id={slip_id} slip_no={slip.get('slip_no','?')} "
           f"new_status={new_status} docs_updated={updated} "
           f"note={notes[:60] if notes else ''}",
           username=session.get("username"), ip=get_client_ip())

    flash(f"✅ {updated} document{'s' if updated != 1 else ''} updated to \"{new_status}\".", "success")
    return redirect(url_for("offices.routed_documents"))


@offices_bp.route("/routing-slip/reroute", methods=["POST"])
@login_required
def reroute_slip():
    """Re-route documents to a new destination office - archives original slip and creates new one."""
    from services.misc import get_routing_slip, save_routing_slip, generate_slip_no
    from services.misc import audit_log as _audit
    from services.documents import get_docs_by_ids, batch_save_docs, save_doc
    from utils import get_client_ip
    from services.misc import now_str
    import uuid

    slip_id = request.form.get("slip_id", "").strip()
    new_destination = request.form.get("destination", "").strip()
    new_status = request.form.get("status", "").strip()
    notes = request.form.get("notes", "").strip()

    if not slip_id or not new_destination:
        flash("Routing slip ID and destination are required.", "error")
        return redirect(url_for("offices.routed_documents"))

    slip = get_routing_slip(slip_id)
    if not slip:
        flash("Routing slip not found.", "error")
        return redirect(url_for("offices.routed_documents"))

    old_destination = slip.get("destination", "")
    old_slip_no = slip.get("slip_no", "")
    actor = session.get("full_name") or session.get("username", "Staff")
    from_office = session.get("office") or "DepEd Leyte Division"
    ts = now_str()

    # Archive the original slip
    slip["status"] = "Archived"
    slip["archived_at"] = ts
    slip["archived_by"] = actor
    slip["rerouted_to"] = new_destination
    slip["rerouted_at"] = ts
    slip["is_rerouted"] = True
    save_routing_slip(slip)

    # Create a new slip for the rerouted documents
    new_slip_id = str(uuid.uuid4())[:8].upper()
    new_slip_no = generate_slip_no()

    # Generate new QR tokens for the new slip
    from services.qr import create_slip_token
    recv_token = create_slip_token(new_slip_id, "SLIP_RECEIVE")
    rel_token = create_slip_token(new_slip_id, "SLIP_RELEASE")

    new_slip = {
        "id": new_slip_id,
        "slip_no": new_slip_no,
        "destination": new_destination,
        "from_office": from_office,
        "prepared_by": actor,
        "doc_ids": slip.get("doc_ids", []),
        "notes": notes,
        "slip_date": ts[:10],
        "created_at": ts,
        "recv_token": recv_token,
        "rel_token": rel_token,
        "status": new_status if new_status else "Routed",
        "original_slip_id": slip_id,
        "original_slip_no": old_slip_no,
        "rerouted_from": old_destination,
        "rerouted_at": ts,
    }
    save_routing_slip(new_slip)

    # Update documents
    doc_ids = slip.get("doc_ids", [])
    docs_map = get_docs_by_ids(doc_ids)

    to_save = []
    for doc_id in doc_ids:
        doc = docs_map.get(doc_id)
        if not doc:
            continue

        # Update to new slip
        doc["forwarded_to"] = new_destination
        doc["routing_slip_id"] = new_slip_id
        doc["routing_slip_no"] = new_slip_no

        # Update status if provided
        if new_status:
            doc["status"] = new_status

        # Update routing array - add new destination
        routing = doc.get("routing", [])
        if new_destination not in routing:
            routing.append(new_destination)
        doc["routing"] = routing

        # Add travel log entry for rerouting
        log_entry = f"Re-routed from {old_destination} to {new_destination}"
        if new_status:
            log_entry += f" | Status: {new_status}"
        if notes:
            log_entry += f" | Note: {notes}"
        log_entry += f" by {actor}"

        # Create new travel log entry
        new_entry = {
            "office": new_destination,
            "action": "Re-routed",
            "officer": actor,
            "timestamp": ts,
            "remarks": log_entry,
            "original_slip_no": old_slip_no,
            "new_slip_no": new_slip_no,
        }

        # Check if the last entry is a duplicate (same new_slip_no)
        tl = doc.get("travel_log", []) or []
        if not tl or tl[-1].get("new_slip_no") != new_slip_no:
            tl.append(new_entry)
            doc["travel_log"] = tl
        to_save.append(doc)

    if to_save:
        batch_save_docs(to_save)

    _audit("reroute_slip",
           f"slip_id={slip_id} slip_no={old_slip_no} "
           f"old_dest={old_destination} new_dest={new_destination} "
           f"new_slip_no={new_slip_no} new_status={new_status} docs_updated={len(to_save)}",
           username=session.get("username"), ip=get_client_ip())

    flash(f"✅ Documents re-routed to \"{new_destination}\" (New Slip: {new_slip_no}).", "success")
    # Store new slip_id in session for the template to show a reprint link
    session["last_rerouted_slip_id"] = new_slip_id
    return redirect(url_for("offices.routed_documents") + "?cart_cleared=1")


@offices_bp.route("/routing-slip/<slip_id>/delete", methods=["POST"])
@admin_required
def delete_routing_slip(slip_id):
    """Delete a routing slip by ID."""
    from flask import jsonify
    from services.misc import delete_routing_slip, get_routing_slip
    from services.misc import audit_log as _audit
    from utils import get_client_ip
    
    slip = get_routing_slip(slip_id)
    if not slip:
        return jsonify({"success": False, "message": "Routing slip not found."}), 404
    
    # Only allow deleting archived slips
    if slip.get('status') != 'Archived':
        return jsonify({"success": False, "message": "Only archived routing slips can be deleted."}), 403
    
    result = delete_routing_slip(slip_id)
    if result:
        _audit("delete_routing_slip",
               f"slip_id={slip_id} slip_no={slip.get('slip_no', '?')}",
               username=session.get("username"), ip=get_client_ip())
        return jsonify({"success": True, "message": "Routing slip deleted successfully."})
    else:
        return jsonify({"success": False, "message": "Failed to delete routing slip."}), 500


@offices_bp.route("/routing-slip/<slip_id>/archive", methods=["POST"])
@login_required
def archive_routing_slip(slip_id):
    """Archive a routing slip by ID."""
    from flask import jsonify
    from services.database import get_db
    from services.misc import get_routing_slip, audit_log as _audit
    from utils import get_client_ip
    
    try:
        db = get_db()
        slip = get_routing_slip(slip_id)
        if not slip:
            return jsonify({"success": False, "message": "Routing slip not found."}), 404
        
        slip_ids = slip.get("doc_ids", [])
        
        # Archive the routing slip
        db.routing_slips.update_one(
            {"_id": slip_id},
            {"$set": {"status": "Archived"}}
        )
        
        # Archive all documents in the slip
        if slip_ids:
            db.documents.update_many(
                {"_id": {"$in": slip_ids}},
                {"$set": {"status": "Archived"}}
            )
        
        _audit("archive_routing_slip",
               f"slip_id={slip_id} slip_no={slip.get('slip_no', '?')}",
               username=session.get("username"), ip=get_client_ip())
        return jsonify({"success": True, "message": "Routing slip archived successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@offices_bp.route("/routing-slip/delete-all", methods=["POST"])
@admin_required
def delete_all_routing_slips():
    """Delete all routing slips."""
    from flask import jsonify
    from services.database import get_db
    from services.misc import audit_log as _audit
    from utils import get_client_ip
    
    try:
        db = get_db()
        # Get all slip IDs before deletion
        all_slips = list(db.routing_slips.find({}, {"_id": 1}))
        slip_ids = [s["_id"] for s in all_slips]
        
        if not slip_ids:
            return jsonify({"success": True, "message": "No routing slips to delete."})
        
        # Delete all routing slips and their documents
        db.routing_slips.delete_many({})
        db.documents.delete_many({"slip_id": {"$in": slip_ids}})
        
        _audit("delete_all_routing_slips",
               f"deleted {len(slip_ids)} slips",
               username=session.get("username"), ip=get_client_ip())
        return jsonify({"success": True, "message": f"Deleted {len(slip_ids)} routing slips."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@offices_bp.route("/routing-slip/<slip_id>/delete-all-docs", methods=["POST"])
@admin_required
def delete_all_docs_in_slip(slip_id):
    """Delete all documents in a routing slip."""
    from flask import jsonify
    from services.database import get_db
    from services.misc import get_routing_slip, audit_log as _audit
    from utils import get_client_ip
    
    try:
        db = get_db()
        slip = get_routing_slip(slip_id)
        if not slip:
            return jsonify({"success": False, "message": "Routing slip not found."}), 404
        
        # Delete all documents in this slip
        result = db.documents.delete_many({"slip_id": slip_id})
        
        _audit("delete_all_docs_in_slip",
               f"slip_id={slip_id} deleted {result.deleted_count} docs",
               username=session.get("username"), ip=get_client_ip())
        return jsonify({"success": True, "message": f"Deleted {result.deleted_count} documents."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@offices_bp.route("/document/<doc_id>/delete", methods=["POST"])
@admin_required
def delete_document(doc_id):
    """Delete a single document."""
    from flask import jsonify
    from services.database import get_db
    from services.misc import audit_log as _audit
    from utils import get_client_ip
    
    try:
        db = get_db()
        doc = db.documents.find_one({"_id": doc_id})
        if not doc:
            return jsonify({"success": False, "message": "Document not found."}), 404
        
        db.documents.delete_one({"_id": doc_id})
        
        _audit("delete_document",
               f"doc_id={doc_id} doc_name={doc.get('doc_name', '?')}",
               username=session.get("username"), ip=get_client_ip())
        return jsonify({"success": True, "message": "Document deleted successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@offices_bp.route("/document/<doc_id>/archive", methods=["POST"])
@login_required
def archive_document(doc_id):
    """Archive a single document."""
    from flask import jsonify
    from services.database import get_db
    from services.misc import audit_log as _audit
    from utils import get_client_ip
    
    try:
        db = get_db()
        doc = db.documents.find_one({"_id": doc_id})
        if not doc:
            return jsonify({"success": False, "message": "Document not found."}), 404
        
        db.documents.update_one(
            {"_id": doc_id},
            {"$set": {"status": "Archived"}}
        )
        
        _audit("archive_document",
               f"doc_id={doc_id} doc_name={doc.get('doc_name', '?')}",
               username=session.get("username"), ip=get_client_ip())
        return jsonify({"success": True, "message": "Document archived successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@offices_bp.route("/routing-slip/archive-all", methods=["POST"])
@login_required
def archive_all_routing_slips():
    """Archive all routing slips."""
    from flask import jsonify
    from services.database import get_db
    from services.misc import audit_log as _audit
    from utils import get_client_ip
    
    try:
        db = get_db()
        # Get all slip IDs before update
        all_slips = list(db.routing_slips.find({}, {"_id": 1}))
        slip_ids = [s["_id"] for s in all_slips]
        
        if not slip_ids:
            return jsonify({"success": True, "message": "No routing slips to archive."})
        
        # Archive all routing slips and their documents
        db.routing_slips.update_many({}, {"$set": {"status": "Archived"}})
        db.documents.update_many({"slip_id": {"$in": slip_ids}}, {"$set": {"status": "Archived"}})
        
        _audit("archive_all_routing_slips",
               f"archived {len(slip_ids)} slips",
               username=session.get("username"), ip=get_client_ip())
        return jsonify({"success": True, "message": f"Archived {len(slip_ids)} routing slips."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
