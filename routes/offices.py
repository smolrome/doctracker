"""
routes/offices.py — Office QR page, routing slips, welcome page.
"""
import re
import uuid

from flask import (Blueprint, flash, redirect, render_template,
                   request, send_file, session, url_for)
from io import BytesIO

from services.documents import get_doc, now_str
from services.misc import (
    audit_log, delete_saved_office, get_office_traffic_today,
    generate_slip_no, get_routing_slip, load_saved_offices,
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
    qr_data = None

    def make_slug(name, suffix):
        return re.sub(r'\s+', '-', name.strip()) + suffix

    if office_name:
        save_office(office_name, session.get("username", ""))
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

    return render_template("office_qr_page.html",
                           base=base,
                           office_name=office_name,
                           qr_data=qr_data,
                           office_traffic=office_traffic,
                           saved_offices=load_saved_offices(),
                           client_reg_code=CLIENT_REG_CODE)


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
    return redirect(url_for("offices.view_routing_slip", slip_id=slip_id))


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
    slips = get_all_routing_slips()
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
                           page=page, total_pages=total_pages, per_page=per_page)


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
        tl.append({"ts": ts, "entry": log_entry, "actor": actor})
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
    return redirect(url_for("offices.routed_documents"))
