import os, uuid, base64, json, re, hashlib
import urllib.request, urllib.error, urllib.parse
from datetime import datetime
from io import BytesIO
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
import urllib.request
import qrcode

# ── PostgreSQL via psycopg2 (Railway) or fallback to JSON file (local) ──
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DB_URL = os.environ.get("DATABASE_URL")
    # Railway uses postgres:// but psycopg2 requires postgresql://
    if DB_URL and DB_URL.startswith("postgres://"):
        DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)
    USE_DB = bool(DB_URL)
except ImportError:
    USE_DB = False

# QR reading via OpenCV
try:
    import cv2
    import numpy as np
    QR_READ_OK = True
except ImportError:
    QR_READ_OK = False

# Anthropic (optional)
try:
    import anthropic
    ai_client = anthropic.Anthropic()
    AI_OK = True
except Exception:
    AI_OK = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "doctracker-deped-leyte-2025")
DATA_FILE = os.environ.get("DATA_FILE", "documents.json")

# ─────────────────────────────────────────────
#  AUTH CONFIG
#  Set ADMIN_USERNAME and ADMIN_PASSWORD as
#  environment variables on Railway.
#  Defaults are for local dev only.
# ─────────────────────────────────────────────

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "deped2025")

# ── Email config — Brevo API (works on Railway) ──
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
MAIL_SENDER   = os.environ.get("MAIL_SENDER", "")  # must be a verified sender in Brevo
MAIL_ENABLED  = bool(BREVO_API_KEY and MAIL_SENDER)

# ─────────────────────────────────────────────
#  INVITE TOKEN HELPERS
# ─────────────────────────────────────────────

def generate_invite_token(email, name=""):
    """Create a unique one-time invite token stored in DB."""
    token = uuid.uuid4().hex  # random 32-char hex token
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Remove any previous unused tokens for this email
                    cur.execute("DELETE FROM invite_tokens WHERE email=%s AND used=FALSE", (email,))
                    cur.execute(
                        "INSERT INTO invite_tokens (token, email, name) VALUES (%s, %s, %s)",
                        (token, email, name)
                    )
                conn.commit()
        except Exception as e:
            print(f"Token insert error: {e}")
    else:
        # JSON fallback
        tokens = _load_tokens_json()
        tokens = [t for t in tokens if not (t["email"] == email and not t.get("used"))]
        tokens.append({"token": token, "email": email, "name": name, "used": False})
        _save_tokens_json(tokens)
    return token

def validate_invite_token(token):
    """Check token is valid, unused, and not expired. Returns (email, name) or (None, None)."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT email, name FROM invite_tokens
                        WHERE token=%s AND used=FALSE AND expires_at > NOW()
                    """, (token,))
                    row = cur.fetchone()
                    return (row["email"], row["name"]) if row else (None, None)
        except Exception as e:
            print(f"Token validate error: {e}")
            return None, None
    else:
        tokens = _load_tokens_json()
        for t in tokens:
            if t["token"] == token and not t.get("used"):
                return t["email"], t.get("name","")
        return None, None

def consume_invite_token(token):
    """Mark token as used after successful registration."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE invite_tokens SET used=TRUE WHERE token=%s", (token,))
                conn.commit()
        except Exception as e:
            print(f"Token consume error: {e}")
    else:
        tokens = _load_tokens_json()
        for t in tokens:
            if t["token"] == token:
                t["used"] = True
        _save_tokens_json(tokens)

def get_all_tokens():
    """Get all invite tokens for admin view as plain dicts."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT token, email, name, used, created_at, expires_at
                        FROM invite_tokens ORDER BY created_at DESC LIMIT 50
                    """)
                    rows = cur.fetchall()
                    # Convert RealDictRow to plain dict so .get() works in templates
                    return [dict(r) for r in rows]
        except Exception as e:
            print(f"get_all_tokens error: {e}")
            return []
    return _load_tokens_json()

def _load_tokens_json():
    if os.path.exists("invite_tokens.json"):
        with open("invite_tokens.json") as f:
            return json.load(f)
    return []

def _save_tokens_json(tokens):
    with open("invite_tokens.json","w") as f:
        json.dump(tokens, f, indent=2)

def send_invite_email(to_email, to_name=""):
    """Send invite via Brevo (Sendinblue) API - works on Railway."""
    if not MAIL_ENABLED:
        return False, "Email not configured. Set BREVO_API_KEY in Railway Variables."
    try:
        token = generate_invite_token(to_email, to_name)
        base_url = os.environ.get("APP_URL", "https://your-app.up.railway.app").rstrip("/")
        register_link = base_url + "/register?token=" + token
        greeting = ("Hi " + to_name + ",") if to_name else "Hello,"

        html_body = (
            "<div style='font-family:Arial,sans-serif;max-width:520px;margin:0 auto;'>"
            "<div style='background:#0D1B2A;padding:28px;text-align:center;border-radius:12px 12px 0 0;'>"
            "<div style='font-size:22px;font-weight:800;color:#fff;'>DocTracker - DepEd Leyte</div>"
            "</div>"
            "<div style='background:#fff;padding:32px;border-radius:0 0 12px 12px;'>"
            "<p>" + greeting + "</p>"
            "<p>You have been invited to join the <strong>DepEd Leyte Division Document Tracker</strong>.</p>"
            "<div style='text-align:center;margin:24px 0;'>"
            "<a href='" + register_link + "' style='background:#3B82F6;color:#fff;text-decoration:none;"
            "padding:14px 32px;border-radius:8px;font-weight:700;font-size:16px;display:inline-block;'>"
            "Accept Invitation &amp; Register</a>"
            "</div>"
            "<p style='color:#92400E;background:#FFF3CD;padding:12px;border-radius:6px;font-size:13px;'>"
            "This link expires in 48 hours and can only be used once.</p>"
            "<p style='color:#666;font-size:12px;word-break:break-all;'>Or copy: " + register_link + "</p>"
            "</div></div>"
        )

        payload_dict = {
            "sender": {"name": "DepEd DocTracker", "email": MAIL_SENDER},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": "You're Invited - DepEd Leyte DocTracker",
            "htmlContent": html_body,
            "textContent": greeting + "\n\nRegister here (expires 48hrs):\n" + register_link
        }
        payload = json.dumps(payload_dict).encode("utf-8")

        headers = {
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=payload,
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return True, token

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return False, "Brevo error " + str(e.code) + ": " + body
    except Exception as e:
        return False, "Email error: " + str(e)
def is_logged_in():
    return session.get("logged_in") is True

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_logged_in():
            flash("Please log in to perform that action.", "error")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────
#  DATABASE SETUP
# ─────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT,
                    role TEXT DEFAULT 'staff',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Safe migration — create invite_tokens if not already present
            cur.execute("""
                CREATE TABLE IF NOT EXISTS invite_tokens (
                    token TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    name TEXT,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '48 hours')
                )
            """)
            # Safe migration — add expires_at column if missing from older installs
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='invite_tokens' AND column_name='expires_at'
                    ) THEN
                        ALTER TABLE invite_tokens
                        ADD COLUMN expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '48 hours');
                    END IF;
                END$$;
            """)
            # Office action QR codes (receive/release stations)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS office_qr_codes (
                    id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    label TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Seed default receive/release QR codes if not present
            cur.execute("""
                INSERT INTO office_qr_codes (id, action, label)
                VALUES ('OFFICE-RECEIVE', 'receive', 'Office Entrance - Receive')
                ON CONFLICT (id) DO NOTHING
            """)
            cur.execute("""
                INSERT INTO office_qr_codes (id, action, label)
                VALUES ('OFFICE-RELEASE', 'release', 'Office Exit - Release')
                ON CONFLICT (id) DO NOTHING
            """)
        conn.commit()

if USE_DB:
    try:
        init_db()
    except Exception as e:
        print(f"DB init error: {e}")

@app.errorhandler(500)
def internal_error(e):
    import traceback
    tb = traceback.format_exc()
    print(f"500 ERROR:\n{tb}")
    # Always show detailed error so we can debug
    return f"<pre style='padding:20px;font-size:13px;'><b>500 Internal Server Error:</b>\n\n{tb}</pre>", 500

@app.route("/debug-error")
def debug_error():
    """Only accessible when FLASK_DEBUG=1 — shows system status."""
    if os.environ.get("FLASK_DEBUG") != "1":
        return "Set FLASK_DEBUG=1 in Railway Variables to enable debug info.", 403
    info = {
        "USE_DB": USE_DB,
        "DB_URL_SET": bool(os.environ.get("DATABASE_URL")),
        "MAIL_ENABLED": MAIL_ENABLED,
            "BREVO_CONFIGURED": bool(os.environ.get("BREVO_API_KEY")),
        "APP_URL": os.environ.get("APP_URL","not set"),
        "ADMIN_USERNAME": ADMIN_USERNAME,
    }
    try:
        docs = load_docs()
        info["doc_count"] = len(docs)
        info["db_ok"] = True
    except Exception as ex:
        info["db_ok"] = False
        info["db_error"] = str(ex)
    try:
        tokens = get_all_tokens()
        info["token_count"] = len(tokens)
        info["tokens_ok"] = True
    except Exception as ex:
        info["tokens_ok"] = False
        info["tokens_error"] = str(ex)
    return jsonify(info)

@app.context_processor
def inject_auth():
    return dict(
        logged_in=is_logged_in(),
        current_user=session.get("username",""),
        current_role=session.get("role","guest"),
        current_full_name=session.get("full_name","")
    )

# ─────────────────────────────────────────────
#  USER HELPERS
# ─────────────────────────────────────────────

import hashlib

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password, full_name="", role="staff"):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO users (username, password_hash, full_name, role) VALUES (%s, %s, %s, %s)",
                        (username.lower().strip(), hash_password(password), full_name.strip(), role)
                    )
                conn.commit()
            return True, None
        except Exception as e:
            if "unique" in str(e).lower():
                return False, "Username already taken."
            return False, str(e)
    else:
        # JSON fallback — store in a users.json file
        users = load_users_json()
        if any(u["username"] == username.lower().strip() for u in users):
            return False, "Username already taken."
        users.append({
            "username": username.lower().strip(),
            "password_hash": hash_password(password),
            "full_name": full_name.strip(),
            "role": role
        })
        with open("users.json","w") as f:
            json.dump(users, f, indent=2)
        return True, None

def verify_user(username, password):
    """Returns (full_name, role) if valid, else None."""
    # Check env-var admin first (always works)
    if username.strip() == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return ADMIN_USERNAME, "admin"
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT full_name, role FROM users WHERE username=%s AND password_hash=%s",
                        (username.lower().strip(), hash_password(password))
                    )
                    row = cur.fetchone()
                    if row:
                        return row["full_name"] or username, row["role"]
        except Exception as e:
            print(f"verify_user error: {e}")
    else:
        users = load_users_json()
        for u in users:
            if u["username"] == username.lower().strip() and u["password_hash"] == hash_password(password):
                return u.get("full_name") or username, u.get("role","staff")
    return None, None

def load_users_json():
    if os.path.exists("users.json"):
        with open("users.json") as f:
            return json.load(f)
    return []

def get_all_users():
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT username, full_name, role, created_at FROM users ORDER BY created_at DESC")
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"get_all_users error: {e}")
            return []
    return load_users_json()

def delete_user(username):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM users WHERE username=%s", (username,))
                conn.commit()
        except Exception as e:
            print(f"delete_user error: {e}")
    else:
        users = [u for u in load_users_json() if u["username"] != username]
        with open("users.json","w") as f:
            json.dump(users, f, indent=2)

# ─────────────────────────────────────────────
#  CLIENT REGISTRATION — public QR code flow
# ─────────────────────────────────────────────

CLIENT_REG_CODE = os.environ.get("CLIENT_REG_CODE", "client-reg")  # embed in public QR

def get_office_qr_url(action, host_url):
    base = os.environ.get("APP_URL", host_url.rstrip("/"))
    return base + "/office-action/" + action

# ─────────────────────────────────────────────
#  DATA HELPERS — transparent DB / JSON switch
# ─────────────────────────────────────────────

def load_docs():
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT data FROM documents ORDER BY created_at DESC")
                    rows = cur.fetchall()
                    return [row['data'] for row in rows]
        except Exception as e:
            print(f"DB load error: {e}")
            return []
    else:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE) as f:
                return json.load(f)
        return []

def save_docs(docs):
    """Save is only used for JSON mode. DB mode saves per-document."""
    if not USE_DB:
        with open(DATA_FILE, "w") as f:
            json.dump(docs, f, indent=2)

def save_doc(doc):
    """Upsert a single document — used in DB mode."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO documents (id, data, created_at)
                        VALUES (%s, %s::jsonb, %s)
                        ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data
                    """, (doc['id'], json.dumps(doc), doc.get('created_at', now_str())))
                conn.commit()
        except Exception as e:
            print(f"DB save error: {e}")
    else:
        docs = load_docs()
        for i, d in enumerate(docs):
            if d['id'] == doc['id']:
                docs[i] = doc
                break
        else:
            docs.insert(0, doc)
        save_docs(docs)

def insert_doc(doc):
    """Insert a brand new document."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO documents (id, data, created_at) VALUES (%s, %s::jsonb, %s)",
                        (doc['id'], json.dumps(doc), doc.get('created_at', now_str()))
                    )
                conn.commit()
        except Exception as e:
            print(f"DB insert error: {e}")
    else:
        docs = load_docs()
        docs.insert(0, doc)
        save_docs(docs)

def delete_doc(doc_id):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
                conn.commit()
        except Exception as e:
            print(f"DB delete error: {e}")
    else:
        save_docs([d for d in load_docs() if d['id'] != doc_id])

def get_doc(doc_id):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT data FROM documents WHERE id = %s", (doc_id,))
                    row = cur.fetchone()
                    return row['data'] if row else None
        except Exception as e:
            print(f"DB get error: {e}")
            return None
    else:
        return next((d for d in load_docs() if d['id'] == doc_id), None)

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
#  AUTH ROUTES
# ─────────────────────────────────────────────

@app.route("/login", methods=["GET","POST"])
def login():
    if is_logged_in():
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        full_name, role = verify_user(username, password)
        if full_name:
            session["logged_in"] = True
            session["username"]  = username.lower().strip()
            session["full_name"] = full_name
            session["role"]      = role
            if role == "client":
                flash(f"Welcome, {full_name}!", "success")
                return redirect(url_for("client_portal"))
            next_url = request.args.get("next") or url_for("index")
            flash(f"Welcome, {full_name}!", "success")
            return redirect(next_url)
        else:
            error = "Invalid username or password."
    return render_template("login.html", error=error)

@app.route("/register", methods=["GET","POST"])
def register():
    if is_logged_in():
        return redirect(url_for("index"))
    token = request.args.get("token") or request.form.get("token","")
    # Validate token on page load
    token_email, token_name = validate_invite_token(token) if token else (None, None)
    token_valid = bool(token_email)
    error = None

    if request.method == "POST":
        if not token_valid:
            error = "Invalid or expired invite link. Please ask the admin to send a new one."
        else:
            username = request.form.get("username","").strip()
            full_name= request.form.get("full_name","").strip()
            password = request.form.get("password","").strip()
            confirm  = request.form.get("confirm_password","").strip()
            if not username or not password:
                error = "Username and password are required."
            elif len(password) < 6:
                error = "Password must be at least 6 characters."
            elif password != confirm:
                error = "Passwords do not match."
            else:
                ok, err = create_user(username, password, full_name or token_name)
                if ok:
                    consume_invite_token(token)
                    flash("Account created! You can now log in.", "success")
                    return redirect(url_for("login"))
                else:
                    error = err

    return render_template("register.html", error=error,
                           token=token, token_valid=token_valid,
                           token_email=token_email, token_name=token_name)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))

@app.route("/manage-users")
@login_required
def manage_users():
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    users = get_all_users()
    return render_template("manage_users.html", users=users,
                           admin_username=ADMIN_USERNAME)

@app.route("/send-invite", methods=["GET","POST"])
@login_required
def send_invite():
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    result = None
    generated_link = None
    try:
        if request.method == "POST":
            to_email = request.form.get("email","").strip()
            to_name  = request.form.get("name","").strip()
            if not to_email:
                result = {"ok": False, "msg": "Email address is required."}
            elif MAIL_ENABLED:
                try:
                    ok, token_or_err = send_invite_email(to_email, to_name)
                    if ok:
                        base_url = os.environ.get("APP_URL","").rstrip("/") or request.host_url.rstrip("/")
                        generated_link = f"{base_url}/register?token={token_or_err}"
                        result = {"ok": True, "msg": f"Invite sent to {to_email}!"}
                    else:
                        result = {"ok": False, "msg": token_or_err}
                except Exception as e:
                    import traceback
                    print(traceback.format_exc())
                    token = generate_invite_token(to_email, to_name)
                    base_url = os.environ.get("APP_URL","").rstrip("/") or request.host_url.rstrip("/")
                    generated_link = f"{base_url}/register?token={token}"
                    result = {"ok": False, "msg": f"Email failed: {str(e)} — invite link generated below, share it manually."}
            else:
                token = generate_invite_token(to_email, to_name)
                base_url = os.environ.get("APP_URL","").rstrip("/") or request.host_url.rstrip("/")
                generated_link = f"{base_url}/register?token={token}"
                result = {"ok": True, "msg": f"Invite link generated for {to_email}. Copy and share it manually.", "manual": True}

        tokens = get_all_tokens()
        return render_template("send_invite.html", result=result,
                               mail_enabled=MAIL_ENABLED,
                               generated_link=generated_link,
                               tokens=tokens,
                               now=datetime.now())
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        flash(f"Error: {str(e)}", "error")
        return redirect(url_for("manage_users"))
@login_required
def delete_user_route(username):
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    if username == ADMIN_USERNAME:
        flash("Cannot delete the main admin account.", "error")
    elif username == session.get("username"):
        flash("Cannot delete your own account.", "error")
    else:
        delete_user(username)
        flash(f"User '{username}' deleted.", "success")
    return redirect(url_for("manage_users"))

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
@login_required
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
        insert_doc(doc)
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
#  Smart page: client scans doc QR to update status
# ─────────────────────────────────────────────

@app.route("/receive/<doc_id>", methods=["GET","POST"])
def receive(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        return render_template("doc_scan.html", doc=None,
                               error="Document not found in the system.")
    result = None
    if request.method == "POST":
        action = request.form.get("action","").strip()
        if not is_logged_in():
            result = {"ok": False, "msg": "Please log in first.", "login_required": True}
        elif action not in ("receive","release"):
            result = {"ok": False, "msg": "Invalid action."}
        else:
            role = session.get("role","guest")
            # Clients can only update their own docs
            if role == "client" and doc.get("submitted_by") != session.get("username"):
                result = {"ok": False, "msg": "You can only update your own documents."}
            else:
                actor = session.get("full_name") or session.get("username")
                if action == "receive":
                    doc["status"] = "Received"
                    doc["date_received"] = now_str()[:10]
                    log_action = "Document Received at Office"
                    log_remark = "Marked Received by scanning document QR code."
                else:
                    doc["status"] = "Released"
                    doc["date_released"] = now_str()[:10]
                    log_action = "Document Released from Office"
                    log_remark = "Marked Released by scanning document QR code."
                doc.setdefault("travel_log", []).append({
                    "office": "DepEd Leyte Division Office",
                    "action": log_action,
                    "officer": actor,
                    "timestamp": now_str(),
                    "remarks": log_remark,
                })
                save_doc(doc)
                doc = get_doc(doc_id)  # reload fresh
                result = {"ok": True, "action": action, "status": doc["status"]}
    return render_template("doc_scan.html", doc=doc, result=result)

# ─────────────────────────────────────────────
#  UPLOAD QR CODE IMAGE → auto-log
# ─────────────────────────────────────────────

@app.route("/upload-qr", methods=["GET","POST"])
@login_required
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
                    save_doc(doc)
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
@login_required
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
        save_doc(doc)
        flash("Document updated.", "success")
        return redirect(url_for("view_doc", doc_id=doc_id))
    doc["routing_str"] = ", ".join(doc.get("routing", []))
    return render_template("form.html", doc=doc, action="edit",
        status_options=["Pending","In Review","In Transit","Released","On Hold","Archived"])

@app.route("/delete/<doc_id>", methods=["POST"])
@login_required
def delete(doc_id):
    delete_doc(doc_id)
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
@login_required
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

# ─────────────────────────────────────────────
#  CLIENT PORTAL
# ─────────────────────────────────────────────


@app.route("/client/submitted/<doc_id>")
def client_submitted(doc_id):
    """Show QR code immediately after client submits a document."""
    if not is_logged_in() or session.get("role") != "client":
        return redirect(url_for("client_login"))
    doc = get_doc(doc_id)
    if not doc or doc.get("submitted_by") != session.get("username"):
        return redirect(url_for("client_portal"))
    qr_b64 = generate_qr_b64(doc, request.host_url)
    return render_template("client_submitted.html", doc=doc, qr_b64=qr_b64)


@app.route("/client/scan")
def client_scan():
    """Client QR scanner page — uses phone camera to scan a document QR."""
    if not is_logged_in() or session.get("role") != "client":
        return redirect(url_for("client_login"))
    return render_template("client_scan.html")

@app.route("/client")
def client_portal():
    """Client dashboard — shows only their own submitted documents."""
    if not is_logged_in() or session.get("role") != "client":
        return redirect(url_for("client_login"))
    username = session.get("username")
    docs = load_docs()
    my_docs = [d for d in docs if d.get("submitted_by") == username]
    return render_template("client_portal.html", docs=my_docs)

@app.route("/client/login", methods=["GET","POST"])
def client_login():
    if is_logged_in():
        role = session.get("role")
        return redirect(url_for("client_portal") if role == "client" else url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        full_name, role = verify_user(username, password)
        if full_name:
            session["logged_in"] = True
            session["username"]  = username.lower().strip()
            session["full_name"] = full_name
            session["role"]      = role
            if role == "client":
                return redirect(url_for("client_portal"))
            return redirect(url_for("index"))
        else:
            error = "Invalid username or password."
    return render_template("client_login.html", error=error)

@app.route("/client/register", methods=["GET","POST"])
def client_register():
    """Public client registration — no invite needed, just the public reg code."""
    if is_logged_in():
        return redirect(url_for("client_portal") if session.get("role") == "client" else url_for("index"))
    error = None
    if request.method == "POST":
        reg_code  = request.form.get("reg_code","").strip()
        username  = request.form.get("username","").strip()
        full_name = request.form.get("full_name","").strip()
        password  = request.form.get("password","").strip()
        confirm   = request.form.get("confirm_password","").strip()
        if reg_code != CLIENT_REG_CODE:
            error = "Invalid registration code. Please scan the QR code at the office."
        elif not username or not password:
            error = "Username and password are required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            ok, err = create_user(username, password, full_name, role="client")
            if ok:
                flash("Account created! You can now log in and submit documents.", "success")
                return redirect(url_for("client_login"))
            else:
                error = err
    return render_template("client_register.html", error=error, office=request.args.get("office",""), reg_code=request.args.get("code",""))

@app.route("/client/submit", methods=["GET","POST"])
def client_submit():
    """Client submits a new document."""
    if not is_logged_in() or session.get("role") != "client":
        return redirect(url_for("client_login"))
    if request.method == "POST":
        doc = {
            "id":           str(uuid.uuid4())[:8].upper(),
            "doc_id":       generate_ref(),
            "doc_name":     request.form.get("doc_name","").strip(),
            "category":     request.form.get("category","").strip(),
            "description":  request.form.get("description","").strip(),
            "sender_name":  session.get("full_name") or session.get("username"),
            "sender_org":   request.form.get("unit_office","").strip(),
            "sender_contact": "",
            "referred_to":  request.form.get("referred_to","").strip(),
            "forwarded_to": "",
            "recipient_name": "",
            "recipient_org": "",
            "recipient_contact": "",
            "received_by":  "",
            "date_received": "",
            "date_released": "",
            "doc_date":     now_str()[:10],
            "status":       "Pending",
            "notes":        request.form.get("notes","").strip(),
            "created_at":   now_str(),
            "routing":      [],
            "travel_log":   [],
            "submitted_by": session.get("username"),
            "submitted_by_name": session.get("full_name") or session.get("username"),
        }
        if not doc["doc_name"]:
            flash("Document name/particulars is required.", "error")
            return render_template("client_submit.html", doc=doc)
        doc["travel_log"].append({
            "office": doc["sender_org"] or "Client",
            "action": "Document Submitted by Client",
            "officer": doc["sender_name"],
            "timestamp": doc["created_at"],
            "remarks": "Submitted via client portal.",
        })
        insert_doc(doc)
        return redirect(url_for("client_submitted", doc_id=doc["id"]))
    return render_template("client_submit.html", doc={})

@app.route("/client/track/<doc_id>")
def client_track(doc_id):
    """Client views their own document detail."""
    if not is_logged_in() or session.get("role") != "client":
        return redirect(url_for("client_login"))
    doc = get_doc(doc_id)
    if not doc or doc.get("submitted_by") != session.get("username"):
        flash("Document not found.", "error")
        return redirect(url_for("client_portal"))
    qr_b64 = generate_qr_b64(doc, request.host_url)
    return render_template("client_track.html", doc=doc, qr_b64=qr_b64)

# ─────────────────────────────────────────────
#  OFFICE QR ACTIONS — Receive / Release stations
# ─────────────────────────────────────────────

@app.route("/office-action/<path:action>", methods=["GET","POST"])
def office_action(action):
    """
    Office QR scan landing page.
    action format: 'receive', 'release', or 'OfficeName-rec', 'OfficeName-rel', 'OfficeName-reg'
    """
    # Parse office name and action type from format "OfficeName-rec/rel/reg"
    office_name = None
    if action.endswith("-rec"):
        office_name = action[:-4].replace("-", " ")
        action_type = "receive"
    elif action.endswith("-rel"):
        office_name = action[:-4].replace("-", " ")
        action_type = "release"
    elif action.endswith("-reg"):
        office_name = action[:-4].replace("-", " ")
        # Redirect to client register with office AND reg code pre-filled
        base = os.environ.get("APP_URL", request.host_url.rstrip("/"))
        return redirect(base + "/client/register?office=" + urllib.parse.quote(office_name) + "&code=" + urllib.parse.quote(CLIENT_REG_CODE))
    elif action in ("receive", "release"):
        action_type = action
    else:
        return redirect(url_for("index"))
    action = action_type  # normalize
    result = None
    if request.method == "POST":
        doc_id = request.form.get("doc_id","").strip().upper()
        doc = get_doc(doc_id)
        if not doc:
            result = {"ok": False, "msg": "Document not found. Check the ID and try again."}
        else:
            # Clients can only update their own submitted documents
            role = session.get("role","guest")
            if role == "client" and doc.get("submitted_by") != session.get("username"):
                result = {"ok": False, "msg": "You can only update status of documents you submitted."}
            elif role == "guest" or not is_logged_in():
                result = {"ok": False, "msg": "Please log in to update document status.", "login_required": True}
            else:
                if action == "receive":
                    doc["status"] = "Received"
                    doc["date_received"] = now_str()[:10]
                    log_action = "Document Received at Office"
                    log_remark = "Marked Received via office entrance QR scan."
                else:
                    doc["status"] = "Released"
                    doc["date_released"] = now_str()[:10]
                    log_action = "Document Released from Office"
                    log_remark = "Marked Released via office exit QR scan."
                actor = session.get("full_name") or session.get("username") or "Client"
                doc.setdefault("travel_log", []).append({
                    "office": "DepEd Leyte Division Office",
                    "action": log_action,
                    "officer": actor,
                    "timestamp": now_str(),
                    "remarks": log_remark,
                })
                save_doc(doc)
                result = {"ok": True, "doc": doc, "action": action}
    return render_template("office_action.html", action=action, result=result)

@app.route("/office-qr/<path:action>.png")
def office_qr_png(action):
    """Generate office QR code — supports 'receive', 'release', or 'OfficeName-rec/rel/reg'."""
    base = os.environ.get("APP_URL", request.host_url.rstrip("/"))
    url = base + "/office-action/" + action
    # Determine label
    if action.endswith("-rec"):
        label = action[:-4].replace("-"," ") + " — Receive"
    elif action.endswith("-rel"):
        label = action[:-4].replace("-"," ") + " — Release"
    elif action.endswith("-reg"):
        label = action[:-4].replace("-"," ") + " — Register"
    else:
        label = action.capitalize()
    qr = qrcode.QRCode(version=None,
                        error_correction=qrcode.constants.ERROR_CORRECT_M,
                        box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0D1B2A", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', action)
    return send_file(buf, mimetype="image/png", download_name=f"qr-{safe}.png")

@app.route("/client-reg-qr.png")
@login_required
def client_reg_qr():
    """QR code for client registration — admin prints and posts at office."""
    if session.get("role") != "admin":
        return "Admin only", 403
    base = os.environ.get("APP_URL", request.host_url.rstrip("/"))
    url = base + "/client/register"
    qr = qrcode.QRCode(version=None,
                        error_correction=qrcode.constants.ERROR_CORRECT_M,
                        box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0D1B2A", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", download_name="client-registration-qr.png")

@app.route("/office-qr-page", methods=["GET","POST"])
@login_required
def office_qr_page():
    """Staff page to generate their office QR codes."""
    base = os.environ.get("APP_URL", request.host_url.rstrip("/"))
    office_name = request.args.get("office", "").strip() or request.form.get("office_name", "").strip()
    # Build QR slugs: replace spaces with dashes, lowercase
    def slug(name, suffix):
        return re.sub(r'\s+', '-', name.strip()) + suffix
    qr_data = None
    if office_name:
        qr_data = {
            "reg": slug(office_name, "-reg"),
            "rec": slug(office_name, "-rec"),
            "rel": slug(office_name, "-rel"),
        }
    return render_template("office_qr_page.html",
                           base=base,
                           office_name=office_name,
                           qr_data=qr_data,
                           client_reg_code=CLIENT_REG_CODE)

# ─────────────────────────────────────────────
#  QUICK STATUS UPDATE (staff manual)
# ─────────────────────────────────────────────

@app.route("/update-status/<doc_id>", methods=["POST"])
@login_required
def update_status(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        return jsonify({"ok": False, "msg": "Not found"}), 404
    new_status = request.form.get("status","").strip()
    valid = ["Pending","Received","In Review","In Transit","Released","On Hold","Archived"]
    if new_status not in valid:
        return jsonify({"ok": False, "msg": "Invalid status"}), 400
    doc["status"] = new_status
    if new_status == "Received" and not doc.get("date_received"):
        doc["date_received"] = now_str()[:10]
    if new_status == "Released" and not doc.get("date_released"):
        doc["date_released"] = now_str()[:10]
    doc.setdefault("travel_log", []).append({
        "office": "DepEd Leyte Division Office",
        "action": "Status Updated to " + new_status,
        "officer": session.get("full_name") or session.get("username"),
        "timestamp": now_str(),
        "remarks": "Manual status update by staff.",
    })
    save_doc(doc)
    flash("Status updated to " + new_status + ".", "success")
    return redirect(url_for("view_doc", doc_id=doc_id))

@app.route("/db-status")
def db_status():
    if not USE_DB:
        return jsonify({
            "storage": "JSON file (documents.json)",
            "database": False,
            "reason": "DATABASE_URL not set or psycopg2 not installed"
        })
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as total FROM documents")
                row = cur.fetchone()
        return jsonify({
            "storage": "PostgreSQL ✅",
            "database": True,
            "documents": row["total"],
            "db_url_prefix": DB_URL[:30] + "..."
        })
    except Exception as e:
        return jsonify({
            "storage": "PostgreSQL (ERROR)",
            "database": False,
            "error": str(e)
        })

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
