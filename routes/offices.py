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
from utils import get_client_ip, is_logged_in, login_required
from config import APP_URL, CLIENT_REG_CODE

offices_bp = Blueprint("offices", __name__)


# ── Office QR management page ─────────────────────────────────────────────────

@offices_bp.route("/office-qr-page", methods=["GET", "POST"])
@login_required
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
        "status":       "In Transit",
    }
    save_routing_slip(slip)

    # Update every document: In Transit + store from/to office
    for doc_id in doc_ids:
        doc = get_doc(doc_id)
        if doc:
            doc["status"]          = "In Transit"
            doc["forwarded_to"]    = destination
            doc["from_office"]     = from_office
            doc["routing_slip_id"] = slip_id
            doc["routing_slip_no"] = slip_no
            doc.setdefault("travel_log", []).append({
                "office":    from_office,
                "action":    f"Released — In Transit to {destination}",
                "officer":   actor,
                "timestamp": now_str(),
                "remarks":   f"Routing slip {slip_no}. Forwarded from {from_office} → {destination}.",
            })
            save_doc(doc)

    audit_log("routing_slip_created",
              f"slip={slip_no} from={from_office} dest={destination} docs={len(doc_ids)}",
              username=session.get("username", ""), ip=get_client_ip())
    return redirect(url_for("offices.view_routing_slip", slip_id=slip_id))


@offices_bp.route("/routing-slip/<slip_id>")
@login_required
def view_routing_slip(slip_id):
    import base64
    from services.qr import make_slip_qr_png, get_base_url

    slip = get_routing_slip(slip_id)
    if not slip:
        flash("Routing slip not found.", "error")
        return redirect(url_for("dashboard.index"))
    docs = [d for d in (get_doc(did) for did in slip["doc_ids"]) if d]

    from_office = slip.get("from_office", "DepEd Leyte Division")
    destination = slip.get("destination", "")
    slip_no     = slip.get("slip_no", slip_id)

    # Use APP_URL if set, otherwise fall back to current request host
    base_url = get_base_url(request.host_url)

    recv_qr_b64 = rel_qr_b64 = None

    if slip.get("recv_token"):
        try:
            png = make_slip_qr_png(slip["recv_token"], "SLIP_RECEIVE",
                                   slip_no, destination, from_office,
                                   base_url=base_url)
            recv_qr_b64 = base64.b64encode(png).decode()
        except Exception as e:
            print(f"recv QR error: {e}")

    if slip.get("rel_token"):
        try:
            png = make_slip_qr_png(slip["rel_token"], "SLIP_RELEASE",
                                   slip_no, destination, from_office,
                                   base_url=base_url)
            rel_qr_b64 = base64.b64encode(png).decode()
        except Exception as e:
            print(f"rel QR error: {e}")

    return render_template("routing_slip.html", slip=slip, docs=docs,
                           recv_qr_b64=recv_qr_b64, rel_qr_b64=rel_qr_b64)
