from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import json
import os
import uuid
import base64
import anthropic
from datetime import datetime

app = Flask(__name__)
app.secret_key = "doctracker-secret-key"

# ── Anthropic client (reads ANTHROPIC_API_KEY from environment) ──────────────
ai_client = anthropic.Anthropic()

DATA_FILE = "documents.json"

def load_docs():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return []

def save_docs(docs):
    with open(DATA_FILE, "w") as f:
        json.dump(docs, f, indent=2)

def get_stats(docs):
    return {
        "total": len(docs),
        "pending": sum(1 for d in docs if d["status"] == "Pending"),
        "released": sum(1 for d in docs if d["status"] == "Released"),
        "on_hold": sum(1 for d in docs if d["status"] == "On Hold"),
        "in_review": sum(1 for d in docs if d["status"] == "In Review"),
    }

@app.route("/")
def index():
    docs = load_docs()
    search = request.args.get("search", "").lower()
    filter_status = request.args.get("status", "All")
    filter_type = request.args.get("type", "All")

    filtered = docs
    if search:
        filtered = [d for d in filtered if search in (d.get("doc_name","") + d.get("doc_id","") + d.get("sender_name","") + d.get("recipient_name","") + d.get("category","")).lower()]
    if filter_status != "All":
        filtered = [d for d in filtered if d["status"] == filter_status]
    if filter_type == "Received":
        filtered = [d for d in filtered if d.get("date_received") and not d.get("date_released")]
    elif filter_type == "Released":
        filtered = [d for d in filtered if d.get("date_released")]

    stats = get_stats(docs)
    return render_template("index.html", docs=filtered, stats=stats,
                           search=search, filter_status=filter_status, filter_type=filter_type,
                           status_options=["All","Pending","In Review","Released","On Hold","Archived"])

@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        docs = load_docs()
        doc = {
            "id": str(uuid.uuid4())[:8].upper(),
            "doc_id": request.form.get("doc_id", "").strip(),
            "doc_name": request.form.get("doc_name", "").strip(),
            "category": request.form.get("category", "").strip(),
            "description": request.form.get("description", "").strip(),
            "sender_name": request.form.get("sender_name", "").strip(),
            "sender_org": request.form.get("sender_org", "").strip(),
            "sender_contact": request.form.get("sender_contact", "").strip(),
            "recipient_name": request.form.get("recipient_name", "").strip(),
            "recipient_org": request.form.get("recipient_org", "").strip(),
            "recipient_contact": request.form.get("recipient_contact", "").strip(),
            "date_received": request.form.get("date_received", ""),
            "date_released": request.form.get("date_released", ""),
            "status": request.form.get("status", "Pending"),
            "notes": request.form.get("notes", "").strip(),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if not doc["doc_name"]:
            flash("Document name is required.", "error")
            return render_template("form.html", doc=doc, action="add",
                                   status_options=["Pending","In Review","Released","On Hold","Archived"])
        docs.insert(0, doc)
        save_docs(docs)
        flash("Document added successfully.", "success")
        return redirect(url_for("index"))
    return render_template("form.html", doc={}, action="add",
                           status_options=["Pending","In Review","Released","On Hold","Archived"])

@app.route("/view/<doc_id>")
def view_doc(doc_id):
    docs = load_docs()
    doc = next((d for d in docs if d["id"] == doc_id), None)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("index"))
    return render_template("detail.html", doc=doc)

@app.route("/edit/<doc_id>", methods=["GET", "POST"])
def edit(doc_id):
    docs = load_docs()
    doc = next((d for d in docs if d["id"] == doc_id), None)
    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        doc.update({
            "doc_id": request.form.get("doc_id", "").strip(),
            "doc_name": request.form.get("doc_name", "").strip(),
            "category": request.form.get("category", "").strip(),
            "description": request.form.get("description", "").strip(),
            "sender_name": request.form.get("sender_name", "").strip(),
            "sender_org": request.form.get("sender_org", "").strip(),
            "sender_contact": request.form.get("sender_contact", "").strip(),
            "recipient_name": request.form.get("recipient_name", "").strip(),
            "recipient_org": request.form.get("recipient_org", "").strip(),
            "recipient_contact": request.form.get("recipient_contact", "").strip(),
            "date_received": request.form.get("date_received", ""),
            "date_released": request.form.get("date_released", ""),
            "status": request.form.get("status", "Pending"),
            "notes": request.form.get("notes", "").strip(),
        })
        if not doc["doc_name"]:
            flash("Document name is required.", "error")
            return render_template("form.html", doc=doc, action="edit",
                                   status_options=["Pending","In Review","Released","On Hold","Archived"])
        save_docs(docs)
        flash("Document updated successfully.", "success")
        return redirect(url_for("view_doc", doc_id=doc_id))

    return render_template("form.html", doc=doc, action="edit",
                           status_options=["Pending","In Review","Released","On Hold","Archived"])

@app.route("/delete/<doc_id>", methods=["POST"])
def delete(doc_id):
    docs = load_docs()
    docs = [d for d in docs if d["id"] != doc_id]
    save_docs(docs)
    flash("Document deleted.", "error")
    return redirect(url_for("index"))

@app.route("/scan", methods=["GET", "POST"])
def scan():
    extracted = None
    error = None

    if request.method == "POST":
        uploaded = request.files.get("document")
        if not uploaded or uploaded.filename == "":
            error = "Please select a file to scan."
        else:
            try:
                file_bytes = uploaded.read()
                b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
                mime = uploaded.content_type or "image/jpeg"

                # Build the message content depending on file type
                if mime == "application/pdf":
                    content = [
                        {
                            "type": "document",
                            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
                        },
                        {"type": "text", "text": SCAN_PROMPT},
                    ]
                else:
                    content = [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": mime, "data": b64},
                        },
                        {"type": "text", "text": SCAN_PROMPT},
                    ]

                response = ai_client.messages.create(
                    model="claude-opus-4-5",
                    max_tokens=1024,
                    messages=[{"role": "user", "content": content}],
                )

                raw = response.content[0].text.strip()
                # Strip markdown fences if present
                raw = raw.replace("```json", "").replace("```", "").strip()
                extracted = json.loads(raw)

            except json.JSONDecodeError:
                error = "Could not parse document data. Try a clearer image or PDF."
            except Exception as e:
                error = f"Scan failed: {str(e)}"

    return render_template("scan.html", extracted=extracted, error=error,
                           status_options=["Pending", "In Review", "Released", "On Hold", "Archived"])


SCAN_PROMPT = """
You are a document data extraction assistant. Analyze this document and extract all relevant fields.

Return ONLY a valid JSON object with these exact keys (use empty string "" if not found):
{
  "doc_name": "title or subject of the document",
  "doc_id": "any reference number, document ID, or control number",
  "category": "document type e.g. Memo, Letter, Contract, Invoice, Report, etc.",
  "description": "brief one-sentence summary of the document purpose",
  "sender_name": "full name of the sender or author",
  "sender_org": "organization, department, or company of the sender",
  "sender_contact": "email, phone, or address of the sender",
  "recipient_name": "full name of the recipient or addressee",
  "recipient_org": "organization or department of the recipient",
  "recipient_contact": "email, phone, or address of the recipient",
  "date_received": "date in YYYY-MM-DD format if found, else empty string",
  "date_released": "",
  "notes": "any other important details, subject line, or key information"
}

Return ONLY the JSON. No explanation, no markdown, no extra text.
"""


@app.route("/api/docs")
def api_docs():
    return jsonify(load_docs())

if __name__ == "__main__":
    app.run(debug=True)
