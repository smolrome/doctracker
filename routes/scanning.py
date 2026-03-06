"""
routes/scanning.py — All QR scan actions:
  - /office-action/<action>   — office station QR landing
  - /doc-scan/<token>         — one-time RECEIVE/RELEASE token scan
  - /receive/<doc_id>         — legacy manual receive/release
  - /upload-qr                — upload QR image to auto-log
  - /scan                     — AI document scan
  - /office-qr/<action>.png   — generate office QR PNG
  - /doc-qr-download/<token>  — download doc token QR PNG
"""
import base64
import re
import urllib.parse

from flask import (Blueprint, flash, redirect, render_template,
                   request, send_file, session, url_for)
from io import BytesIO

from services.documents import get_doc, now_str, save_doc
from services.misc import (
    audit_log, get_office_traffic_today, log_office_traffic,
)
from services.qr import (
    QR_READ_OK, create_doc_token, decode_qr_image, extract_doc_id_from_qr,
    generate_qr_b64, make_doc_status_qr_png, make_office_qr_png, use_doc_token,
    get_token_doc,
)
from utils import get_client_ip, is_logged_in, login_required

scanning_bp = Blueprint("scanning", __name__)


# ── Office action QR landing ──────────────────────────────────────────────────

@scanning_bp.route("/office-action/<path:action>", methods=["GET", "POST"])
def office_action(action):
    """Landing page for all office QR types: -rec, -rel, -reg, -sub."""
    if action.endswith("-rec"):
        return _handle_receive_release(action[:-4].replace("-", " ").title(),
                                       action[:-4].lower(), "receive")
    if action.endswith("-rel"):
        return _handle_receive_release(action[:-4].replace("-", " ").title(),
                                       action[:-4].lower(), "release")
    if action.endswith("-reg"):
        office_name = action[:-4].replace("-", " ").title()
        slug        = action[:-4].lower()
        if is_logged_in() and session.get("role") == "client":
            return redirect(url_for("client.portal"))
        return render_template("client_gate.html", office_name=office_name,
                               office_slug=slug,
                               next_url=url_for("client.portal"))
    if action.endswith("-sub"):
        office_name = action[:-4].replace("-", " ").title()
        slug        = action[:-4].lower()
        submit_url  = (f"/client/submit?office_slug={urllib.parse.quote(slug)}"
                       f"&office_name={urllib.parse.quote(office_name)}")
        if not is_logged_in():
            return render_template("client_gate.html", office_name=office_name,
                                   office_slug=slug, next_url=submit_url)
        if session.get("role") != "client":
            flash("This QR code is for clients only.", "error")
            return redirect(url_for("dashboard.index"))
        return redirect(submit_url)
    if action in ("receive", "release"):
        return _handle_receive_release("Main Office", "main-office", action)
    return redirect(url_for("dashboard.index"))


def _handle_receive_release(office_name: str, office_slug: str, action_type: str):
    result = None
    if request.method == "POST":
        doc_id = request.form.get("doc_id", "").strip().upper()
        doc    = get_doc(doc_id)
        if not doc:
            result = {"ok": False, "msg": "Document not found. Check the ID and try again."}
        elif not is_logged_in():
            result = {"ok": False, "msg": "Please log in to update document status.",
                      "login_required": True}
        elif session.get("role") == "client" and doc.get("submitted_by") != session.get("username"):
            result = {"ok": False, "msg": "You can only update status of your own documents."}
        else:
            actor = session.get("full_name") or session.get("username") or "Staff"
            if action_type == "receive":
                doc["status"]        = "Received"
                doc["date_received"] = now_str()[:10]
                log_action = "Document Received at Office"
                log_remark = "Marked Received via office entrance QR scan."
            else:
                doc["status"]        = "Released"
                doc["date_released"] = now_str()[:10]
                log_action = "Document Released from Office"
                log_remark = "Marked Released via office exit QR scan."
            doc.setdefault("travel_log", []).append({
                "office":    "DepEd Leyte Division Office",
                "action":    log_action,
                "officer":   actor,
                "timestamp": now_str(),
                "remarks":   log_remark,
            })
            save_doc(doc)
            result = {"ok": True, "doc": doc, "action": action_type}
    return render_template("office_action.html",
                           action=action_type, result=result)


# ── One-time doc token scan ───────────────────────────────────────────────────

@scanning_bp.route("/doc-scan/<token>")
def doc_scan(token):
    """Auto-update document status from one-time RECEIVE or RELEASE QR token."""
    if not is_logged_in():
        return redirect(url_for("auth.login", next=request.url))
    if session.get("role") == "client":
        flash("This QR code is for office staff only.", "error")
        return redirect(url_for("client.portal"))

    doc_id, token_type = use_doc_token(token)
    if not doc_id:
        return render_template("doc_scan_result.html",
                               ok=False,
                               msg="This QR code has already been used or is invalid.",
                               token_type="UNKNOWN", doc=None,
                               release_qr_b64=None, traffic=None)

    doc = get_doc(doc_id)
    if not doc:
        return render_template("doc_scan_result.html",
                               ok=False, msg="Document not found.",
                               token_type=token_type, doc=None,
                               release_qr_b64=None, traffic=None)

    office_slug    = doc.get("target_office_slug", "general")
    office_name    = doc.get("target_office_name", "Office")
    actor          = session.get("full_name") or session.get("username") or "Staff"
    release_qr_b64 = None
    traffic        = None

    if token_type == "RECEIVE":
        doc.update({
            "status":        "Received",
            "date_received": now_str()[:10],
            "received_by":   actor,
        })
        doc.setdefault("travel_log", []).append({
            "office": office_name, "action": "Document Received at Office",
            "officer": actor, "timestamp": now_str(),
            "remarks": "Auto-updated via RECEIVE QR scan.",
        })
        save_doc(doc)
        log_office_traffic(office_slug, office_name, "RECEIVE",
                           doc_id, doc.get("submitted_by", ""))
        rel_token      = create_doc_token(doc_id, "RELEASE")
        rel_png        = make_doc_status_qr_png(rel_token, "RELEASE",
                                                doc.get("doc_name", "Document"))
        release_qr_b64 = base64.b64encode(rel_png).decode()
        doc["release_token"] = rel_token
        save_doc(doc)
        traffic = get_office_traffic_today(office_slug)
        audit_log("doc_received_qr", f"doc_id={doc_id} office={office_name}",
                  username=session.get("username", ""), ip=get_client_ip())

    elif token_type == "RELEASE":
        doc.update({
            "status":        "Released",
            "date_released": now_str()[:10],
        })
        doc.setdefault("travel_log", []).append({
            "office": office_name, "action": "Document Released / Picked Up",
            "officer": actor, "timestamp": now_str(),
            "remarks": "Auto-updated via RELEASE QR scan. Client picked up document.",
        })
        save_doc(doc)
        log_office_traffic(office_slug, office_name, "RELEASE",
                           doc_id, doc.get("submitted_by", ""))
        traffic = get_office_traffic_today(office_slug)
        audit_log("doc_released_qr", f"doc_id={doc_id} office={office_name}",
                  username=session.get("username", ""), ip=get_client_ip())

    return render_template("doc_scan_result.html",
                           ok=True, token_type=token_type, doc=doc,
                           office_name=office_name, actor=actor,
                           release_qr_b64=release_qr_b64,
                           release_token=doc.get("release_token"),
                           traffic=traffic, msg=None)


# ── Legacy manual receive/release ─────────────────────────────────────────────

@scanning_bp.route("/receive/<doc_id>", methods=["GET", "POST"])
def receive(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        return render_template("doc_scan.html", doc=None,
                               error="Document not found in the system.")
    result = None
    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if not is_logged_in():
            result = {"ok": False, "msg": "Please log in first.", "login_required": True}
        elif action not in ("receive", "release"):
            result = {"ok": False, "msg": "Invalid action."}
        else:
            role = session.get("role", "guest")
            if role == "client" and doc.get("submitted_by") != session.get("username"):
                result = {"ok": False, "msg": "You can only update your own documents."}
            else:
                actor = session.get("full_name") or session.get("username")
                if action == "receive":
                    doc["status"]        = "Received"
                    doc["date_received"] = now_str()[:10]
                    log_action = "Document Received at Office"
                    log_remark = "Marked Received by scanning document QR code."
                else:
                    doc["status"]        = "Released"
                    doc["date_released"] = now_str()[:10]
                    log_action = "Document Released from Office"
                    log_remark = "Marked Released by scanning document QR code."
                doc.setdefault("travel_log", []).append({
                    "office":    "DepEd Leyte Division Office",
                    "action":    log_action,
                    "officer":   actor,
                    "timestamp": now_str(),
                    "remarks":   log_remark,
                })
                save_doc(doc)
                doc    = get_doc(doc_id)
                result = {"ok": True, "action": action, "status": doc["status"]}
    return render_template("doc_scan.html", doc=doc, result=result)


# ── Upload QR image → auto-log ─────────────────────────────────────────────

@scanning_bp.route("/upload-qr", methods=["GET", "POST"])
@login_required
def upload_qr():
    result = error = success_entry = None
    doc = None

    if request.method == "POST":
        if "qr_image" in request.files and request.files["qr_image"].filename:
            qr_text, err = decode_qr_image(request.files["qr_image"].read())
            if err:
                error = err
            else:
                result = qr_text
                doc_id = extract_doc_id_from_qr(qr_text)
                doc    = get_doc(doc_id) if doc_id else None
                if not doc:
                    error = f"QR code scanned but no matching document found (ID: {doc_id})."

        elif request.form.get("doc_id_confirm"):
            doc_id  = request.form.get("doc_id_confirm")
            doc     = get_doc(doc_id)
            if not doc:
                error = "Document not found."
            else:
                office  = request.form.get("office", "").strip()
                officer = request.form.get("officer", "").strip()
                action  = request.form.get("action", "Received")
                remarks = request.form.get("remarks", "").strip()
                if not office:
                    error  = "Office / Department is required."
                    result = doc_id
                else:
                    entry = {"office": office, "action": action, "officer": officer,
                             "timestamp": now_str(), "remarks": remarks, "via": "QR Upload"}
                    doc.setdefault("travel_log", []).append(entry)
                    doc["status"] = {
                        "Received": "In Transit", "Released": "Released",
                        "On Hold": "On Hold", "Returned": "In Transit", "Completed": "Released",
                    }.get(action, "In Transit")
                    if action in ("Released", "Completed") and not doc.get("date_released"):
                        from datetime import datetime
                        doc["date_released"] = datetime.now().strftime("%Y-%m-%d")
                    save_doc(doc)
                    success_entry = entry
                    doc = get_doc(doc_id)

    return render_template("upload_qr.html",
                           doc=doc, error=error, success_entry=success_entry,
                           qr_read_ok=QR_READ_OK,
                           action_options=["Received", "Released", "On Hold",
                                           "Returned", "Completed"])


# ── AI document scan ──────────────────────────────────────────────────────────

_SCAN_PROMPT = """
Analyze this document and extract all relevant fields.
Return ONLY a valid JSON object with these exact keys (use empty string if not found):
{"doc_name":"","doc_id":"","category":"","description":"","sender_name":"","sender_org":"",
"sender_contact":"","recipient_name":"","recipient_org":"","recipient_contact":"",
"date_received":"","date_released":"","notes":""}
Return ONLY the JSON. No markdown, no explanation.
"""

@scanning_bp.route("/scan", methods=["GET", "POST"])
@login_required
def ai_scan():
    extracted = error = None
    try:
        import anthropic
        import json
        ai_client = anthropic.Anthropic()
        ai_ok = True
    except Exception:
        ai_ok = False

    if request.method == "POST":
        if not ai_ok:
            error = "Anthropic library not configured."
        else:
            uploaded = request.files.get("document")
            if not uploaded or not uploaded.filename:
                error = "Please select a file."
            else:
                try:
                    import json
                    b64  = base64.standard_b64encode(uploaded.read()).decode()
                    mime = uploaded.content_type or "image/jpeg"
                    content = (
                        [{"type": "document",
                          "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                         {"type": "text", "text": _SCAN_PROMPT}]
                        if mime == "application/pdf" else
                        [{"type": "image",
                          "source": {"type": "base64", "media_type": mime, "data": b64}},
                         {"type": "text", "text": _SCAN_PROMPT}]
                    )
                    resp = ai_client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=1024,
                        messages=[{"role": "user", "content": content}],
                    )
                    raw       = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
                    extracted = json.loads(raw)
                except Exception as e:
                    error = f"Scan failed: {e}"

    from config import STATUS_OPTIONS
    return render_template("scan.html", extracted=extracted, error=error,
                           status_options=STATUS_OPTIONS)


# ── QR PNG generation endpoints ───────────────────────────────────────────────

@scanning_bp.route("/office-qr/<path:action>.png")
def office_qr_png(action):
    buf = BytesIO(make_office_qr_png(action, request.host_url))
    buf.seek(0)
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', action)
    return send_file(buf, mimetype="image/png", download_name=f"qr-{safe}.png")


@scanning_bp.route("/doc-qr-download/<token>")
@login_required
def doc_qr_download(token):
    doc, token_type = get_token_doc(token)
    if not doc:
        return "QR token not found", 404
    png = make_doc_status_qr_png(token, token_type, doc.get("doc_name", "Document"),
                                 box_size=12)
    buf  = BytesIO(png)
    buf.seek(0)
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', doc.get("doc_name", "doc"))[:20]
    return send_file(buf, mimetype="image/png", as_attachment=True,
                     download_name=f"QR_{token_type}_{safe}.png")
