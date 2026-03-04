from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
import json, os, uuid, base64
from datetime import datetime
from io import BytesIO
import qrcode

# QR reading via OpenCV
try:
    import cv2
    import numpy as np
    from PIL import Image
    QR_READ_OK = True
except ImportError:
    QR_READ_OK = False

# Anthropic (optional — only needed for /scan AI feature)
try:
    import anthropic
    ai_client = anthropic.Anthropic()
    AI_OK = True
except Exception:
    AI_OK = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "doctracker-deped-leyte-2025")

# Use /data/documents.json on Railway (mount a volume at /data)
# Falls back to local documents.json when running locally
DATA_FILE = os.environ.get("DATA_FILE", "documents.json")

# ─────────────────────────────────────────────
#  DATA HELPERS
# ─────────────────────────────────────────────

def load_docs():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return []

def save_docs(docs):
    with open(DATA_FILE, "w") as f:
        json.dump(docs, f, indent=2)

def get_doc(doc_id):
    return next((d for d in load_docs() if d["id"] == doc_id), None)

def get_stats(docs):
    return {
        "total":      len(docs),
        "pending":    sum(1 for d in docs if d["status"] == "Pending"),
        "released":   sum(1 for d in docs if d["status"] == "Released"),
        "on_hold":    sum(1 for d in docs if d["status"] == "On Hold"),
        "in_review":  sum(1 for d in docs if d["status"] == "In Review"),
        "in_transit": sum(1 for d in docs if d["status"] == "In Transit"),
    }

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def generate_ref():
    """Generate a readable reference number like REF-2026-A3F9"""
    year = datetime.now().year
    suffix = uuid.uuid4().hex[:4].upper()
    return f"REF-{year}-{suffix}"

# ─────────────────────────────────────────────
#  QR HELPERS
# ─────────────────────────────────────────────

def get_server_url(request_host_url):
    """
    Return the correct base URL for QR codes.
    - Online (Railway/Render): use the public HTTPS URL from the request
    - Local network: replace localhost with real network IP
    """
    import socket

    # If it's already a proper public/network address, use it as-is
    if "127.0.0.1" not in request_host_url and "localhost" not in request_host_url:
        return request_host_url.rstrip("/")

    # Running locally — swap localhost with network IP for LAN access
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        return f"http://{local_ip}:5000"
    except Exception:
        return request_host_url.rstrip("/")

def make_qr_png(doc, host_url, box_size=8):
    """QR encodes the /receive URL so scanning opens the log-receipt page."""
    server_url = get_server_url(host_url)
    scan_url = f"{server_url}/receive/{doc['id']}"
    qr = qrcode.QRCode(version=None,
                        error_correction=qrcode.constants.ERROR_CORRECT_M,
                        box_size=box_size, border=3)
    qr.add_data(scan_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0D1B2A", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def generate_qr_b64(doc, host_url):
    return base64.b64encode(make_qr_png(doc, host_url)).decode()

def decode_qr_image(file_bytes):
    """
    Decode a QR code image using OpenCV's built-in QR detector.
    Requires: pip install opencv-python Pillow numpy
    """
    if not QR_READ_OK:
        return None, "QR reading library not installed. Run: pip install opencv-python Pillow numpy"
    try:
        # Convert bytes to numpy array for OpenCV
        img_array = np.frombuffer(file_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            return None, "Could not read image file. Please upload a valid JPG or PNG."

        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)

        if data:
            return data, None

        # Try with grayscale if colour failed
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        data, _, _ = detector.detectAndDecode(gray)
        if data:
            return data, None

        return None, "No QR code found in the image. Make sure the QR code is clearly visible and not blurry."
    except Exception as e:
        return None, f"Could not read image: {e}"

def extract_doc_id_from_qr(qr_text):
    """
    Our QR codes encode URLs like http://host/receive/DOCID
    Extract the doc ID from the URL.
    """
    # Try URL pattern first
    import re
    m = re.search(r'/receive/([A-Z0-9]{8})', qr_text)
    if m:
        return m.group(1)
    # Fallback: maybe just the ID was encoded
    m = re.search(r'\b([A-Z0-9]{8})\b', qr_text)
    if m:
        return m.group(1)
    return None

# ─────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────

@app.route("/")
def index():
    docs          = load_docs()
    search        = request.args.get("search","").lower()
    filter_status = request.args.get("status","All")
    filter_type   = request.args.get("type","All")
    filtered = docs
    if search:
        filtered = [d for d in filtered if search in (
            d.get("doc_name","") + d.get("doc_id","") +
            d.get("sender_name","") + d.get("recipient_name","") +
            d.get("category","")).lower()]
    if filter_status != "All":
        filtered = [d for d in filtered if d["status"] == filter_status]
    if filter_type == "Received":
        filtered = [d for d in filtered if d.get("date_received") and not d.get("date_released")]
    elif filter_type == "Released":
        filtered = [d for d in filtered if d.get("date_released")]
    return render_template("index.html",
        docs=filtered, stats=get_stats(docs),
        search=search, filter_status=filter_status, filter_type=filter_type,
        status_options=["All","Pending","In Review","In Transit","Released","On Hold","Archived"])

# ─────────────────────────────────────────────
#  ADD DOCUMENT
# ─────────────────────────────────────────────

@app.route("/add", methods=["GET","POST"])
def add():
    if request.method == "POST":
        docs        = load_docs()
        routing_raw = request.form.get("routing_offices","").strip()
        routing     = [r.strip() for r in routing_raw.split(",") if r.strip()]
        doc = {
            "id":                str(uuid.uuid4())[:8].upper(),
            "doc_id":            request.form.get("doc_id","").strip(),
            "doc_name":          request.form.get("doc_name","").strip(),
            "category":          request.form.get("category","").strip(),
            "doc_date":          request.form.get("doc_date","").strip(),
            "description":       request.form.get("description","").strip(),
            # Source / Sender
            "sender_name":       request.form.get("sender_name","").strip(),
            "sender_org":        request.form.get("sender_org","").strip(),
            "sender_contact":    request.form.get("sender_contact","").strip(),
            # Receiving
            "received_by":       request.form.get("received_by","").strip(),
            # Routing
            "referred_to":       request.form.get("referred_to","").strip(),
            "forwarded_to":      request.form.get("forwarded_to","").strip(),
            # Recipient
            "recipient_name":    request.form.get("recipient_name","").strip(),
            "recipient_org":     request.form.get("recipient_org","").strip(),
            "recipient_contact": request.form.get("recipient_contact","").strip(),
            # Dates
            "date_received":     request.form.get("date_received",""),
            "date_released":     request.form.get("date_released",""),
            "status":            "Pending",
            "notes":             request.form.get("notes","").strip(),
            "created_at":        now_str(),
            "routing":           routing,
            "travel_log":        [],
        }
        if not doc["doc_name"]:
            flash("Document name is required.", "error")
            return render_template("form.html", doc=doc, action="add",
                status_options=["Pending","In Review","In Transit","Released","On Hold","Archived"])
        origin = doc["sender_org"] or doc["sender_name"] or "Origin"
        doc["travel_log"].append({
            "office": origin, "action": "Document Created",
            "officer": doc["sender_name"], "timestamp": doc["created_at"],
            "remarks": "Document logged into the system.",
        })
        docs.insert(0, doc)
        save_docs(docs)
        flash("Document added and routing chain created.", "success")
        return redirect(url_for("view_doc", doc_id=doc["id"]))
    return render_template("form.html", doc={}, action="add",
        auto_ref=generate_ref(),
        status_options=["Pending","In Review","In Transit","Released","On Hold","Archived"])

# ─────────────────────────────────────────────
#  VIEW DOCUMENT (admin)
# ─────────────────────────────────────────────

@app.route("/view/<doc_id>")
def view_doc(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("index"))
    return render_template("detail.html", doc=doc,
                           qr_b64=generate_qr_b64(doc, request.host_url))

# ─────────────────────────────────────────────
#  QR SCAN LANDING — /receive/<id>
#  Mobile page shown when camera scans the code
# ─────────────────────────────────────────────

@app.route("/receive/<doc_id>", methods=["GET","POST"])
def receive(doc_id):
    docs = load_docs()
    doc  = next((d for d in docs if d["id"] == doc_id), None)
    if not doc:
        return render_template("receive.html", doc=None,
                               error="Document not found in the system.")
    success_entry = None
    if request.method == "POST":
        office  = request.form.get("office","").strip()
        officer = request.form.get("officer","").strip()
        action  = request.form.get("action","Received")
        remarks = request.form.get("remarks","").strip()
        if not office:
            flash("Office / Department name is required.", "error")
        else:
            entry = {"office": office, "action": action,
                     "officer": officer, "timestamp": now_str(), "remarks": remarks}
            doc.setdefault("travel_log", []).append(entry)
            doc["status"] = {
                "Received":"In Transit","Released":"Released",
                "On Hold":"On Hold","Returned":"In Transit","Completed":"Released",
            }.get(action, "In Transit")
            if action in ("Released","Completed") and not doc.get("date_released"):
                doc["date_released"] = datetime.now().strftime("%Y-%m-%d")
            save_docs(docs)
            success_entry = entry
    return render_template("receive.html", doc=doc, success_entry=success_entry,
        action_options=["Received","Released","On Hold","Returned","Completed"])

# ─────────────────────────────────────────────
#  UPLOAD QR CODE IMAGE → auto-log
# ─────────────────────────────────────────────

@app.route("/upload-qr", methods=["GET","POST"])
def upload_qr():
    """
    Office uploads a QR code image.
    System reads it, finds the document, pre-fills the log form.
    """
    result   = None   # decoded QR text
    doc      = None   # matched document
    error    = None
    success_entry = None

    if request.method == "POST":
        # ── STEP 1: decode the QR image ──────────────────────────
        if "qr_image" in request.files and request.files["qr_image"].filename:
            uploaded = request.files["qr_image"]
            qr_text, err = decode_qr_image(uploaded.read())

            if err:
                error = err
            elif not qr_text:
                error = "Could not decode QR code. Please use the downloaded QR PNG."
            else:
                result  = qr_text
                doc_id  = extract_doc_id_from_qr(qr_text)
                doc     = get_doc(doc_id) if doc_id else None
                if not doc:
                    error = f"QR code scanned but no matching document found (ID: {doc_id})."

        # ── STEP 2: log the entry after confirmation ──────────────
        elif request.form.get("doc_id_confirm"):
            docs    = load_docs()
            doc_id  = request.form.get("doc_id_confirm")
            doc     = next((d for d in docs if d["id"] == doc_id), None)

            if not doc:
                error = "Document not found."
            else:
                office  = request.form.get("office","").strip()
                officer = request.form.get("officer","").strip()
                action  = request.form.get("action","Received")
                remarks = request.form.get("remarks","").strip()

                if not office:
                    error = "Office / Department is required."
                    # Re-show doc so they can fix it
                    result = doc_id
                else:
                    entry = {
                        "office":    office,
                        "action":    action,
                        "officer":   officer,
                        "timestamp": now_str(),
                        "remarks":   remarks,
                        "via":       "QR Upload",
                    }
                    doc.setdefault("travel_log", []).append(entry)
                    doc["status"] = {
                        "Received":"In Transit","Released":"Released",
                        "On Hold":"On Hold","Returned":"In Transit","Completed":"Released",
                    }.get(action, "In Transit")
                    if action in ("Released","Completed") and not doc.get("date_released"):
                        doc["date_released"] = datetime.now().strftime("%Y-%m-%d")
                    save_docs(docs)
                    success_entry = entry
                    # Reload doc with fresh data
                    doc = get_doc(doc_id)

    return render_template("upload_qr.html",
        doc=doc, error=error, success_entry=success_entry,
        qr_read_ok=QR_READ_OK,
        action_options=["Received","Released","On Hold","Returned","Completed"])

# ─────────────────────────────────────────────
#  EDIT / DELETE
# ─────────────────────────────────────────────

@app.route("/edit/<doc_id>", methods=["GET","POST"])
def edit(doc_id):
    docs = load_docs()
    doc  = next((d for d in docs if d["id"] == doc_id), None)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        routing = [r.strip() for r in request.form.get("routing_offices","").split(",") if r.strip()]
        doc.update({
            "doc_id":            request.form.get("doc_id","").strip(),
            "doc_name":          request.form.get("doc_name","").strip(),
            "category":          request.form.get("category","").strip(),
            "doc_date":          request.form.get("doc_date","").strip(),
            "description":       request.form.get("description","").strip(),
            "sender_name":       request.form.get("sender_name","").strip(),
            "sender_org":        request.form.get("sender_org","").strip(),
            "sender_contact":    request.form.get("sender_contact","").strip(),
            "received_by":       request.form.get("received_by","").strip(),
            "referred_to":       request.form.get("referred_to","").strip(),
            "forwarded_to":      request.form.get("forwarded_to","").strip(),
            "recipient_name":    request.form.get("recipient_name","").strip(),
            "recipient_org":     request.form.get("recipient_org","").strip(),
            "recipient_contact": request.form.get("recipient_contact","").strip(),
            "date_received":     request.form.get("date_received",""),
            "date_released":     request.form.get("date_released",""),
            "status":            request.form.get("status","Pending"),
            "notes":             request.form.get("notes","").strip(),
            "routing":           routing,
        })
        if not doc["doc_name"]:
            flash("Document name is required.", "error")
            return render_template("form.html", doc=doc, action="edit",
                status_options=["Pending","In Review","In Transit","Released","On Hold","Archived"])
        save_docs(docs)
        flash("Document updated.", "success")
        return redirect(url_for("view_doc", doc_id=doc_id))
    doc["routing_str"] = ", ".join(doc.get("routing", []))
    return render_template("form.html", doc=doc, action="edit",
        status_options=["Pending","In Review","In Transit","Released","On Hold","Archived"])

@app.route("/delete/<doc_id>", methods=["POST"])
def delete(doc_id):
    save_docs([d for d in load_docs() if d["id"] != doc_id])
    flash("Document deleted.", "error")
    return redirect(url_for("index"))

# ─────────────────────────────────────────────
#  QR DOWNLOAD
# ─────────────────────────────────────────────

@app.route("/qr/<doc_id>.png")
def qr_download(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        return "Not found", 404
    buf = BytesIO(make_qr_png(doc, request.host_url, box_size=10))
    buf.seek(0)
    safe = doc.get("doc_name","doc").replace(" ","_")[:30]
    return send_file(buf, mimetype="image/png", as_attachment=True,
                     download_name=f"QR_{safe}_{doc_id}.png")

# ─────────────────────────────────────────────
#  AI DOCUMENT SCAN (upload a doc image/PDF)
# ─────────────────────────────────────────────

SCAN_PROMPT = """
Analyze this document and extract all relevant fields.
Return ONLY a valid JSON object with these exact keys (use empty string if not found):
{"doc_name":"","doc_id":"","category":"","description":"","sender_name":"","sender_org":"",
"sender_contact":"","recipient_name":"","recipient_org":"","recipient_contact":"",
"date_received":"","date_released":"","notes":""}
Return ONLY the JSON. No markdown, no explanation.
"""

@app.route("/scan", methods=["GET","POST"])
def scan():
    extracted = None; error = None
    if request.method == "POST":
        if not AI_OK:
            error = "Anthropic library not configured."
        else:
            uploaded = request.files.get("document")
            if not uploaded or not uploaded.filename:
                error = "Please select a file."
            else:
                try:
                    b64  = base64.standard_b64encode(uploaded.read()).decode()
                    mime = uploaded.content_type or "image/jpeg"
                    content = ([{"type":"document","source":{"type":"base64","media_type":"application/pdf","data":b64}},{"type":"text","text":SCAN_PROMPT}]
                               if mime=="application/pdf" else
                               [{"type":"image","source":{"type":"base64","media_type":mime,"data":b64}},{"type":"text","text":SCAN_PROMPT}])
                    resp = ai_client.messages.create(model="claude-opus-4-5", max_tokens=1024,
                               messages=[{"role":"user","content":content}])
                    raw  = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
                    extracted = json.loads(raw)
                except json.JSONDecodeError:
                    error = "Could not parse response. Try a clearer image."
                except Exception as e:
                    error = f"Scan failed: {e}"
    return render_template("scan.html", extracted=extracted, error=error,
        status_options=["Pending","In Review","In Transit","Released","On Hold","Archived"])

# ─────────────────────────────────────────────
#  API
# ─────────────────────────────────────────────

@app.route("/api/gen-ref")
def api_gen_ref():
    return jsonify({"ref": generate_ref()})

@app.route("/api/docs")
def api_docs():
    return jsonify(load_docs())

@app.route("/api/docs/<doc_id>/log")
def api_log(doc_id):
    doc = get_doc(doc_id)
    if not doc: return jsonify({"error":"not found"}), 404
    return jsonify(doc.get("travel_log", []))

if __name__ == "__main__":
    import socket
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "your-ip"
    print("\n" + "="*55)
    print("  DepEd Leyte Division — Document Tracker")
    print("="*55)
    print(f"  ✅ Server running!")
    print(f"  📡 Local network access:")
    print(f"     http://{local_ip}:5000")
    print("="*55 + "\n")
    app.run(debug=False, host='0.0.0.0', port=5000)
