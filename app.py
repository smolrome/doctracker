import os, uuid, base64, json, re, hashlib, hmac, time, secrets, threading
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timedelta
from io import BytesIO
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session, abort
import urllib.request
import qrcode

# ── bcrypt for secure password hashing ──
try:
    import bcrypt
    BCRYPT_OK = True
except ImportError:
    BCRYPT_OK = False

# ─────────────────────────────────────────────
#  RATE LIMITING  (in-memory, thread-safe)
#  5 failed logins → 15-min lockout per IP
# ─────────────────────────────────────────────
_rate_lock  = threading.Lock()
_rate_store = {}  # key → {count, window_start, locked_until}

RATE_LIMITS = {
    "login":    {"max": 5,  "window": 300,  "lockout": 900},
    "register": {"max": 5,  "window": 3600, "lockout": 3600},
}

def get_client_ip():
    return (request.headers.get("X-Forwarded-For","").split(",")[0].strip()
            or request.remote_addr or "unknown")

def check_rate_limit(action, identifier):
    cfg = RATE_LIMITS.get(action, {"max": 20, "window": 60, "lockout": 120})
    key = f"{action}:{identifier}"
    now = time.time()
    with _rate_lock:
        e = _rate_store.get(key, {"count": 0, "window_start": now, "locked_until": 0})
        if e["locked_until"] > now:
            return False, int(e["locked_until"] - now)
        if now - e["window_start"] > cfg["window"]:
            e = {"count": 0, "window_start": now, "locked_until": 0}
        e["count"] += 1
        if e["count"] > cfg["max"]:
            e["locked_until"] = now + cfg["lockout"]
            _rate_store[key] = e
            return False, int(cfg["lockout"])
        _rate_store[key] = e
        return True, 0

def reset_rate_limit(action, identifier):
    with _rate_lock:
        _rate_store.pop(f"{action}:{identifier}", None)

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

# ── Secret key — MUST be set in Railway env vars for production ──
_secret = os.environ.get("SECRET_KEY", "")
if not _secret:
    _secret = "doctracker-dev-CHANGE-ME-in-production"
    print("WARNING: SECRET_KEY not set — using insecure default. Set it in Railway Variables!")
app.secret_key = _secret

# ── Secure session cookie settings ──
app.config.update(
    SESSION_COOKIE_HTTPONLY  = True,   # JS cannot read cookie
    SESSION_COOKIE_SAMESITE  = "Lax",  # CSRF mitigation
    SESSION_COOKIE_SECURE    = os.environ.get("RAILWAY_ENVIRONMENT") == "production",
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8),
    MAX_CONTENT_LENGTH       = 10 * 1024 * 1024,  # 10 MB upload limit
)

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
                    active BOOLEAN DEFAULT TRUE,
                    last_login TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Safe migrations for existing installs
            for col_sql in [
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP",
            ]:
                try:
                    cur.execute(col_sql)
                except Exception:
                    pass
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
            # Saved offices for QR page persistence across devices
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saved_offices (
                    office_slug TEXT PRIMARY KEY,
                    office_name TEXT NOT NULL,
                    created_by TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Activity / audit log — login, logout, deletions
            cur.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id SERIAL PRIMARY KEY,
                    username TEXT,
                    action TEXT NOT NULL,
                    ip_address TEXT,
                    detail TEXT,
                    ts TIMESTAMP DEFAULT NOW()
                )
            """)
            # Routing slips — batch routing documents sent to another office
            cur.execute("""
                CREATE TABLE IF NOT EXISTS routing_slips (
                    id TEXT PRIMARY KEY,
                    slip_no TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    prepared_by TEXT,
                    doc_ids JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    notes TEXT,
                    slip_date TEXT,
                    time_from TEXT,
                    time_to TEXT
                )
            """)
            # Office traffic log — counts clients in/out per office per day
            cur.execute("""
                CREATE TABLE IF NOT EXISTS office_traffic (
                    id SERIAL PRIMARY KEY,
                    office_slug TEXT NOT NULL,
                    office_name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    doc_id TEXT,
                    client_username TEXT,
                    scanned_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Document QR tokens — RECEIVE and RELEASE one-time-use tokens
            cur.execute("""
                CREATE TABLE IF NOT EXISTS doc_qr_tokens (
                    token TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    token_type TEXT NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            for col_sql in [
                "ALTER TABLE doc_qr_tokens ADD COLUMN IF NOT EXISTS used BOOLEAN DEFAULT FALSE",
            ]:
                try: cur.execute(col_sql)
                except Exception: pass
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
    print(f"500 ERROR:\n{tb}")  # visible in Railway logs only
    is_dev = os.environ.get("FLASK_DEBUG") == "1"
    if is_dev:
        return f"<pre style='padding:20px;font-size:13px;'><b>500 Internal Server Error:</b>\n\n{tb}</pre>", 500
    # Production: show friendly page, log the error
    try:
        audit_log("500_error", str(e)[:300])
    except Exception:
        pass
    return render_template("500.html"), 500

@app.errorhandler(429)
def too_many_requests(e):
    return render_template("500.html",
        error_title="Too Many Attempts",
        error_msg="Too many login attempts. Please wait a few minutes before trying again."), 429

@app.errorhandler(403)
def forbidden(e):
    flash("You do not have permission to access that page.", "error")
    return redirect(url_for("index"))


@app.route("/logo.png")
def serve_logo():
    """Serve the logo from templates/logo/ folder."""
    import os
    logo_path = os.path.join(os.path.dirname(__file__), 'templates', 'logo', 'doctrackerLOGO.png')
    return send_file(logo_path, mimetype='image/png')

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
        current_full_name=session.get("full_name",""),
        now=datetime.now,
    )

@app.after_request
def add_security_headers(response):
    """Add security headers to every response."""
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]          = "SAMEORIGIN"
    response.headers["X-XSS-Protection"]         = "1; mode=block"
    response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]        = "geolocation=(), microphone=(), camera=(self)"
    # Session expiry check
    if is_logged_in():
        last_active = session.get("last_active", 0)
        now = time.time()
        if last_active and now - last_active > 8 * 3600:  # 8 hour timeout
            session.clear()
            flash("Your session expired. Please log in again.", "error")
        else:
            session["last_active"] = now
    return response

@app.before_request
def check_session_active():
    """Block requests from disabled user accounts mid-session."""
    if is_logged_in() and session.get("role") != "admin":
        username = session.get("username","")
        if username and USE_DB:
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT active FROM users WHERE username=%s", (username,))
                        row = cur.fetchone()
                        if row and not row["active"]:
                            session.clear()
                            flash("Your account has been disabled. Contact the administrator.", "error")
                            return redirect(url_for("login"))
            except Exception:
                pass

# ─────────────────────────────────────────────
#  USER HELPERS
# ─────────────────────────────────────────────

def hash_password(password):
    """Hash with bcrypt if available, SHA-256 fallback."""
    if BCRYPT_OK:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain, stored_hash):
    """Verify password against stored hash — handles both bcrypt and SHA-256."""
    if BCRYPT_OK and stored_hash.startswith("$2"):
        try:
            return bcrypt.checkpw(plain.encode(), stored_hash.encode())
        except Exception:
            return False
    # Legacy SHA-256 fallback
    return hashlib.sha256(plain.encode()).hexdigest() == stored_hash

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
    """Returns (full_name, role) if valid, else (None, None)."""
    uname = username.strip().lower()

    # ── Admin via env var — constant-time compare to prevent timing attacks ──
    admin_ok = (secrets.compare_digest(uname, ADMIN_USERNAME.lower())
                and secrets.compare_digest(password, ADMIN_PASSWORD))
    if admin_ok:
        return ADMIN_USERNAME, "admin"

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Fetch hash first, verify outside SQL to use bcrypt
                    cur.execute(
                        "SELECT full_name, role, password_hash FROM users WHERE username=%s AND active=TRUE",
                        (uname,)
                    )
                    row = cur.fetchone()
                    if row and verify_password(password, row["password_hash"]):
                        # Re-hash with bcrypt if still stored as SHA-256
                        if BCRYPT_OK and not row["password_hash"].startswith("$2"):
                            new_hash_val = hash_password(password)
                            try:
                                with get_conn() as conn2:
                                    with conn2.cursor() as cur2:
                                        cur2.execute(
                                            "UPDATE users SET password_hash=%s WHERE username=%s",
                                            (new_hash_val, uname)
                                        )
                                    conn2.commit()
                            except Exception:
                                pass
                        return row["full_name"] or uname, row["role"]
        except Exception as e:
            print(f"verify_user error: {e}")
    else:
        users = load_users_json()
        for u in users:
            if u["username"] == uname and verify_password(password, u.get("password_hash","")):
                return u.get("full_name") or uname, u.get("role","staff")
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
                    cur.execute(
                        "SELECT username, full_name, role, active, last_login, created_at FROM users ORDER BY created_at DESC"
                    )
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"get_all_users error: {e}")
            return []
    return load_users_json()

def set_user_active(username, active):
    """Enable or disable a user account."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE users SET active=%s WHERE username=%s", (active, username))
                conn.commit()
        except Exception as e:
            print(f"set_user_active error: {e}")
    else:
        users = load_users_json()
        for u in users:
            if u["username"] == username:
                u["active"] = active
        with open("users.json","w") as f:
            json.dump(users, f, indent=2)

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

def audit_log(action, detail=""):
    """Record an event in the activity_log table."""
    username = session.get("username", "anonymous") if session else "system"
    ip = get_client_ip()
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO activity_log (username, action, ip_address, detail) VALUES (%s,%s,%s,%s)",
                        (username, action, ip, detail[:500] if detail else "")
                    )
                conn.commit()
        except Exception as e:
            print(f"audit_log error: {e}")
    else:
        # JSON fallback
        path = "activity_log.json"
        logs = []
        if os.path.exists(path):
            with open(path) as f_log:
                logs = json.load(f_log)
        logs.append({"username": username, "action": action, "ip": ip,
                     "detail": detail, "ts": datetime.now().isoformat()})
        logs = logs[-500:]  # keep last 500
        with open(path, "w") as f_log:
            json.dump(logs, f_log, indent=2)

def update_last_login(username):
    """Stamp last_login timestamp on successful auth."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE users SET last_login=NOW() WHERE username=%s", (username,))
                conn.commit()
        except Exception as e:
            print(f"update_last_login error: {e}")

# ─────────────────────────────────────────────
#  CLIENT REGISTRATION — public QR code flow
# ─────────────────────────────────────────────

CLIENT_REG_CODE = os.environ.get("CLIENT_REG_CODE", "client-reg")  # embed in public QR

# ── QR Signing — HMAC-SHA256 so office QR URLs can be verified ──
QR_SIGN_SECRET = os.environ.get("QR_SIGN_SECRET", app.secret_key)
QR_SIGN_VALIDITY_DAYS = int(os.environ.get("QR_SIGN_DAYS", "365"))  # rotate annually

def sign_office_action(action):
    """Return action + expiry + HMAC sig. Expires in QR_SIGN_VALIDITY_DAYS."""
    expiry = int(time.time()) + QR_SIGN_VALIDITY_DAYS * 86400
    payload = f"{action}:{expiry}"
    sig = hmac.new(QR_SIGN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{action}?exp={expiry}&sig={sig}"

def verify_office_action(action, exp_str, sig):
    """Verify the HMAC signature and expiry. Returns True if valid."""
    try:
        expiry = int(exp_str)
        if time.time() > expiry:
            return False  # expired
        payload = f"{action}:{expiry}"
        expected = hmac.new(QR_SIGN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        return secrets.compare_digest(expected, sig)
    except Exception:
        return False

def get_office_qr_url(action, host_url):
    base = os.environ.get("APP_URL", host_url.rstrip("/"))
    return base + "/office-action/" + action

# ─────────────────────────────────────────────
#  DATA HELPERS — transparent DB / JSON switch
# ─────────────────────────────────────────────

def load_docs(include_deleted=False):
    """Load documents. Soft-deleted docs excluded by default."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT data FROM documents ORDER BY created_at DESC")
                    rows = cur.fetchall()
                    docs = [row['data'] for row in rows]
        except Exception as e:
            print(f"DB load error: {e}")
            docs = []
    else:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE) as f:
                docs = json.load(f)
        else:
            docs = []
    if not include_deleted:
        docs = [d for d in docs if not d.get("deleted")]
    return docs

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

def delete_doc(doc_id, deleted_by=""):
    """Soft delete — marks deleted flag in JSON data, never removes from DB."""
    doc = get_doc(doc_id)
    if not doc:
        return
    doc["deleted"]    = True
    doc["deleted_by"] = deleted_by or "unknown"
    doc["deleted_at"] = now_str()
    save_doc(doc)

def restore_doc(doc_id):
    """Undo a soft delete."""
    doc = get_doc(doc_id)
    if not doc:
        return
    doc.pop("deleted", None)
    doc.pop("deleted_by", None)
    doc.pop("deleted_at", None)
    save_doc(doc)

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
    lockout_remaining = 0
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        ip = get_client_ip()
        # Rate limit by IP + username combo
        allowed, wait = check_rate_limit("login", f"{ip}:{username.lower()}")
        if not allowed:
            mins = max(1, wait // 60)
            error = f"Too many failed attempts. Try again in {mins} minute{'s' if mins!=1 else ''}."
            lockout_remaining = wait
            audit_log("login_blocked", f"username={username}")
        else:
            full_name, role = verify_user(username, password)
            if full_name:
                reset_rate_limit("login", f"{ip}:{username.lower()}")
                session.clear()
                session["logged_in"]   = True
                session["username"]    = username.lower().strip()
                session["full_name"]   = full_name
                session["role"]        = role
                session["last_active"] = time.time()
                session.permanent      = True
                update_last_login(username.lower().strip())
                audit_log("login_ok", f"role={role}")
                if role == "client":
                    return redirect(url_for("client_portal"))
                next_url = request.args.get("next") or url_for("index")
                flash(f"Welcome, {full_name}!", "success")
                return redirect(next_url)
            else:
                error = "Invalid username or password."
                audit_log("login_fail", f"username={username}")
    return render_template("login.html", error=error, lockout_remaining=lockout_remaining)

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
            elif len(password) < 8:
                error = "Password must be at least 8 characters."
            elif not re.search(r'[0-9]', password):
                error = "Password must contain at least one number."
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
    audit_log("logout", "")
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

@app.route("/activity-log")
@login_required
def activity_log_view():
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    logs = []
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT username, action, ip_address, detail, ts FROM activity_log ORDER BY ts DESC LIMIT 200"
                    )
                    logs = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"activity_log_view error: {e}")
    else:
        path = "activity_log.json"
        if os.path.exists(path):
            with open(path) as f:
                logs = list(reversed(json.load(f)))[:200]
    return render_template("activity_log.html", logs=logs)

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

@app.route("/delete-user/<username>", methods=["POST"])
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
        audit_log("user_deleted", f"deleted_user={username}")
        flash(f"User '{username}' deleted.", "success")
    return redirect(url_for("manage_users"))

@app.route("/disable-user/<username>", methods=["POST"])
@login_required
def disable_user_route(username):
    """Disable a user account — they can't log in but data is preserved."""
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    if username == ADMIN_USERNAME:
        flash("Cannot disable the main admin account.", "error")
    elif username == session.get("username"):
        flash("Cannot disable your own account.", "error")
    else:
        set_user_active(username, False)
        audit_log("user_disabled", f"disabled_user={username}")
        flash(f"Account '{username}' has been disabled.", "success")
    return redirect(url_for("manage_users"))

@app.route("/enable-user/<username>", methods=["POST"])
@login_required
def enable_user_route(username):
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    set_user_active(username, True)
    audit_log("user_enabled", f"enabled_user={username}")
    flash(f"Account '{username}' has been re-enabled.", "success")
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
    filter_date   = request.args.get("date","").strip()       # YYYY-MM-DD
    filter_time_from = request.args.get("time_from","").strip()  # HH:MM
    filter_time_to   = request.args.get("time_to","").strip()    # HH:MM

    filtered = docs

    if search:
        filtered = [d for d in filtered if search in (
            d.get("doc_name","") + d.get("doc_id","") +
            d.get("sender_name","") + d.get("recipient_name","") +
            d.get("sender_org","") + d.get("category","")).lower()]

    if filter_status != "All":
        filtered = [d for d in filtered if d["status"] == filter_status]

    if filter_type == "Received":
        filtered = [d for d in filtered if d.get("date_received") and not d.get("date_released")]
    elif filter_type == "Released":
        filtered = [d for d in filtered if d.get("date_released")]

    # Date filter — match against created_at date portion
    if filter_date:
        filtered = [d for d in filtered if (d.get("created_at","") or "")[:10] == filter_date]

    # Time range filter — match against created_at time portion HH:MM
    if filter_time_from:
        filtered = [d for d in filtered
                    if (d.get("created_at","") or "")[11:16] >= filter_time_from]
    if filter_time_to:
        filtered = [d for d in filtered
                    if (d.get("created_at","") or "")[11:16] <= filter_time_to]

    saved_offices = load_saved_offices()
    return render_template("index.html",
        docs=filtered, stats=get_stats(docs),
        search=search, filter_status=filter_status, filter_type=filter_type,
        filter_date=filter_date, filter_time_from=filter_time_from,
        filter_time_to=filter_time_to,
        status_options=["All","Pending","In Review","In Transit","Released","On Hold","Archived"],
        saved_offices=saved_offices)

# ─────────────────────────────────────────────
#  ADD DOCUMENT
# ─────────────────────────────────────────────

@app.route("/add", methods=["GET","POST"])
@login_required
def add():
    """Staff logs one or more documents — same cart flow as client submission."""
    cart  = session.get("staff_cart", [])
    error = None

    if request.method == "POST":
        action = request.form.get("_action", "add")

        # ── ADD to cart ──
        if action == "add":
            doc_name    = request.form.get("doc_name","").strip()
            sender_org  = request.form.get("sender_org","").strip()
            sender_name = request.form.get("sender_name","").strip()
            referred_to = request.form.get("referred_to","").strip()
            category    = request.form.get("category","").strip()
            description = request.form.get("description","").strip()
            notes       = request.form.get("notes","").strip()
            if not doc_name:
                error = "Content / Particulars is required."
            else:
                cart.append({
                    "tmp_id":      uuid.uuid4().hex[:8].upper(),
                    "doc_name":    doc_name,
                    "sender_org":  sender_org,
                    "sender_name": sender_name,
                    "referred_to": referred_to,
                    "category":    category,
                    "description": description,
                    "notes":       notes,
                })
                session["staff_cart"] = cart
                session.modified = True
                flash(f"✅ '{doc_name}' added to the log list.", "success")

        # ── REMOVE from cart ──
        elif action == "remove":
            tmp_id = request.form.get("tmp_id","")
            cart = [d for d in cart if d["tmp_id"] != tmp_id]
            session["staff_cart"] = cart
            session.modified = True

        # ── LOG ALL ──
        elif action == "submit_all":
            if not cart:
                error = "No documents to log. Add at least one document first."
            else:
                logged_ids = []
                actor = session.get("full_name") or session.get("username") or "Staff"
                for item in cart:
                    doc = {
                        "id":            str(uuid.uuid4())[:8].upper(),
                        "doc_id":        generate_ref(),
                        "doc_name":      item["doc_name"],
                        "category":      item["category"],
                        "description":   item["description"],
                        "sender_name":   item["sender_name"],
                        "sender_org":    item["sender_org"],
                        "sender_contact":"",
                        "referred_to":   item["referred_to"],
                        "forwarded_to":  "",
                        "recipient_name":"","recipient_org":"","recipient_contact":"",
                        "received_by":   actor,
                        "date_received": now_str()[:10],
                        "date_released": "",
                        "doc_date":      now_str()[:10],
                        "status":        "Received",
                        "notes":         item["notes"],
                        "created_at":    now_str(),
                        "routing":       [],
                        "travel_log":    [],
                        "logged_by":     session.get("username"),
                    }
                    doc["travel_log"].append({
                        "office":    item["sender_org"] or "Division Office",
                        "action":    "Document Logged by Staff",
                        "officer":   actor,
                        "timestamp": doc["created_at"],
                        "remarks":   f"Logged into system by {actor}. Batch of {len(cart)}.",
                    })
                    insert_doc(doc)
                    logged_ids.append(doc["id"])
                session.pop("staff_cart", None)
                session.modified = True
                flash(f"✅ {len(logged_ids)} document{'s' if len(logged_ids)!=1 else ''} logged successfully.", "success")
                return redirect(url_for("index"))

        cart = session.get("staff_cart", [])

    return render_template("form.html", doc={}, action="add",
        cart=cart, error=error,
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
    doc = get_doc(doc_id)
    doc_name = doc.get("doc_name","Unknown") if doc else "Unknown"
    delete_doc(doc_id, deleted_by=session.get("username",""))
    audit_log("doc_deleted", f"doc_id={doc_id} name={doc_name}")
    flash(f"Document '{doc_name}' moved to trash. Admins can restore it.", "success")
    return redirect(url_for("index"))

@app.route("/restore/<doc_id>", methods=["POST"])
@login_required
def restore(doc_id):
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    restore_doc(doc_id)
    audit_log("doc_restored", f"doc_id={doc_id}")
    flash("Document restored successfully.", "success")
    return redirect(url_for("trash"))

@app.route("/trash")
@login_required
def trash():
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    deleted_docs = [d for d in load_docs(include_deleted=True) if d.get("deleted")]
    return render_template("trash.html", docs=deleted_docs)

# ─────────────────────────────────────────────
#  QR DOWNLOAD
# ─────────────────────────────────────────────

@app.route("/doc-qr-download/<token>")
@login_required
def doc_qr_download(token):
    """Download a RELEASE QR PNG by token (doesn't consume it)."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT doc_id, token_type FROM doc_qr_tokens WHERE token=%s",
                        (token,)
                    )
                    row = cur.fetchone()
                    if not row:
                        return "QR token not found", 404
                    doc = get_doc(row["doc_id"])
                    token_type = row["token_type"]
        except Exception as e:
            return f"Error: {e}", 500
    else:
        path = "doc_qr_tokens.json"
        if not os.path.exists(path): return "Not found", 404
        with open(path) as f: tokens = json.load(f)
        t = tokens.get(token)
        if not t: return "Not found", 404
        doc = get_doc(t["doc_id"])
        token_type = t["token_type"]
    if not doc:
        return "Document not found", 404
    png = make_doc_status_qr_png(token, token_type, doc.get("doc_name","Document"), box_size=12)
    buf = BytesIO(png)
    buf.seek(0)
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', doc.get("doc_name","doc"))[:20]
    return send_file(buf, mimetype="image/png", as_attachment=True,
                     download_name=f"QR_{token_type}_{safe}.png")

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


def _get_client_org(username):
    """Try to recall the client's last used unit/office from their docs."""
    if not username:
        return ""
    try:
        docs = load_docs()
        for d in docs:
            if d.get("submitted_by") == username and d.get("sender_org"):
                return d["sender_org"]
    except Exception:
        pass
    return ""

@app.route("/client/submitted/<doc_id>")
def client_submitted(doc_id):
    """Single-doc submission confirmation (legacy / direct link support)."""
    if not is_logged_in() or session.get("role") != "client":
        return redirect(url_for("client_login"))
    doc = get_doc(doc_id)
    if not doc or doc.get("submitted_by") != session.get("username"):
        return redirect(url_for("client_portal"))
    qr_b64 = generate_qr_b64(doc, request.host_url)
    return render_template("client_submitted.html", docs=[doc],
                           qr_list=[(doc, qr_b64, None)], batch=False)

@app.route("/client/submitted-batch")
def client_submitted_batch():
    """Batch submission confirmation — shows RECEIVE QR for every submitted doc."""
    if not is_logged_in() or session.get("role") != "client":
        return redirect(url_for("client_login"))
    ids_raw    = request.args.get("ids","")
    tokens_raw = request.args.get("tokens","")
    doc_ids = [i.strip() for i in ids_raw.split(",") if i.strip()]
    tokens  = [t.strip() for t in tokens_raw.split(",") if t.strip()]
    if not doc_ids:
        return redirect(url_for("client_portal"))
    base = os.environ.get("APP_URL", request.host_url.rstrip("/"))
    qr_list = []
    for i, doc_id in enumerate(doc_ids):
        doc = get_doc(doc_id)
        if doc and doc.get("submitted_by") == session.get("username"):
            token = tokens[i] if i < len(tokens) else None
            if token:
                # RECEIVE QR — client gives this to staff at the office
                qr_png = make_doc_status_qr_png(token, "RECEIVE", doc.get("doc_name","Document"))
                qr_b64 = base64.b64encode(qr_png).decode()
            else:
                qr_b64 = generate_qr_b64(doc, request.host_url)
            qr_list.append((doc, qr_b64, token))
    if not qr_list:
        return redirect(url_for("client_portal"))
    return render_template("client_submitted.html", qr_list=qr_list, batch=True)


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
    lockout_remaining = 0
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        ip = get_client_ip()
        allowed, wait = check_rate_limit("login", f"{ip}:{username.lower()}")
        if not allowed:
            mins = max(1, wait // 60)
            error = f"Too many failed attempts. Try again in {mins} minute{'s' if mins!=1 else ''}."
            lockout_remaining = wait
            audit_log("client_login_blocked", f"username={username}")
        else:
            full_name, role = verify_user(username, password)
            if full_name:
                reset_rate_limit("login", f"{ip}:{username.lower()}")
                session.clear()
                session["logged_in"]   = True
                session["username"]    = username.lower().strip()
                session["full_name"]   = full_name
                session["role"]        = role
                session["last_active"] = time.time()
                session.permanent      = True
                update_last_login(username.lower().strip())
                audit_log("client_login_ok", f"role={role}")
                next_url = request.form.get("next_url","").strip() or request.args.get("next","").strip()
                if role == "client":
                    dest = next_url or url_for("client_portal")
                    return redirect(dest)
                return redirect(url_for("index"))
            else:
                error = "Invalid username or password."
                audit_log("client_login_fail", f"username={username}")
    # Carry context into template
    office_slug = request.args.get("office_slug","")
    office_name = request.args.get("office_name","")
    next_url    = request.args.get("next","")
    return render_template("client_login.html", error=error,
        lockout_remaining=lockout_remaining,
        office_slug=office_slug, office_name=office_name, next_url=next_url)

@app.route("/client/register", methods=["GET","POST"])
def client_register():
    """
    Public client registration — open to anyone.
    Carries office_slug / office_name / next URL through the flow
    so after registering the client is auto-logged in and redirected
    to the submission form for that office.
    """
    if is_logged_in():
        next_url = request.args.get("next","")
        if session.get("role") == "client":
            return redirect(next_url or url_for("client_portal"))
        return redirect(url_for("index"))

    # Carry context from QR scan through GET params or hidden fields
    office_slug = request.args.get("office_slug", request.form.get("office_slug","")).strip()
    office_name = request.args.get("office_name", request.form.get("office_name","")).strip()
    # Legacy: plain ?office= from old -reg QR links
    if not office_name:
        office_name = request.args.get("office", request.form.get("office","")).strip()
    next_url    = request.args.get("next", request.form.get("next_url","")).strip()
    # Build the post-login destination
    if not next_url and office_slug and office_name:
        next_url = f"/client/submit?office_slug={urllib.parse.quote(office_slug)}&office_name={urllib.parse.quote(office_name)}"

    error = None
    if request.method == "POST":
        username  = request.form.get("username","").strip()
        full_name = request.form.get("full_name","").strip()
        password  = request.form.get("password","").strip()
        confirm   = request.form.get("confirm_password","").strip()
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
                # Auto-login after registration
                full_name_db, role = verify_user(username, password)
                session.clear()
                session["username"]  = username.lower().strip()
                session["full_name"] = full_name_db or full_name
                session["role"]      = "client"
                session.permanent    = True
                update_last_login(username)
                audit_log("register_and_login", f"new_client={username}")
                flash(f"Welcome, {full_name}! Your account is ready.", "success")
                return redirect(next_url or url_for("client_portal"))
            else:
                error = err

    return render_template("client_register.html",
        error=error,
        office_name=office_name,
        office_slug=office_slug,
        next_url=next_url)

@app.route("/client/submit", methods=["GET","POST"])
def client_submit():
    """Client builds a batch of documents to submit (cart-style)."""
    if not is_logged_in() or session.get("role") != "client":
        return redirect(url_for("client_login"))

    # Session cart — list of pending docs not yet saved to DB
    cart = session.get("submit_cart", [])
    error = None

    if request.method == "POST":
        action = request.form.get("_action","add")

        # ── ADD a document to the cart ──
        if action == "add":
            doc_name    = request.form.get("doc_name","").strip()
            unit_office = request.form.get("unit_office","").strip()
            referred_to = request.form.get("referred_to","").strip()
            category    = request.form.get("category","").strip()
            description = request.form.get("description","").strip()
            notes       = request.form.get("notes","").strip()

            if not doc_name:
                error = "Document name / particulars is required."
            elif not referred_to:
                error = "Referred To is required."
            else:
                cart.append({
                    "tmp_id":      uuid.uuid4().hex[:8].upper(),  # temp ID for cart ops
                    "doc_name":    doc_name,
                    "unit_office": unit_office,
                    "referred_to": referred_to,
                    "category":    category,
                    "description": description,
                    "notes":       notes,
                })
                session["submit_cart"] = cart
                session.modified = True
                flash(f"✅ '{doc_name}' added to your submission list.", "success")

        # ── REMOVE one item from cart ──
        elif action == "remove":
            tmp_id = request.form.get("tmp_id","")
            cart = [d for d in cart if d["tmp_id"] != tmp_id]
            session["submit_cart"] = cart
            session.modified = True

        # ── SUBMIT ALL — save all cart items to DB + generate RECEIVE tokens ──
        elif action == "submit_all":
            if not cart:
                error = "No documents to submit. Add at least one document first."
            else:
                submitted_ids     = []
                receive_tokens    = []
                office_slug_used  = session.get("submit_office_slug", "")
                office_name_used  = session.get("submit_office_name", "")
                for item in cart:
                    doc = {
                        "id":           str(uuid.uuid4())[:8].upper(),
                        "doc_id":       generate_ref(),
                        "doc_name":     item["doc_name"],
                        "category":     item["category"],
                        "description":  item["description"],
                        "sender_name":  session.get("full_name") or session.get("username"),
                        "sender_org":   item["unit_office"],
                        "sender_contact": "",
                        "referred_to":  item["referred_to"] or office_name_used,
                        "forwarded_to": "",
                        "recipient_name": "",
                        "recipient_org": "",
                        "recipient_contact": "",
                        "received_by":  "",
                        "date_received": "",
                        "date_released": "",
                        "doc_date":     now_str()[:10],
                        "status":       "Pending",
                        "notes":        item["notes"],
                        "created_at":   now_str(),
                        "routing":      [],
                        "travel_log":   [],
                        "submitted_by": session.get("username"),
                        "submitted_by_name": session.get("full_name") or session.get("username"),
                        "target_office_slug": office_slug_used,
                        "target_office_name": office_name_used,
                    }
                    doc["travel_log"].append({
                        "office":    office_name_used or item["unit_office"] or "Client",
                        "action":    "Document Submitted by Client",
                        "officer":   doc["sender_name"],
                        "timestamp": doc["created_at"],
                        "remarks":   f"Submitted via client portal. Target office: {office_name_used or 'General'}.",
                    })
                    insert_doc(doc)
                    # Generate RECEIVE token for this document
                    rec_token = create_doc_token(doc["id"], "RECEIVE")
                    submitted_ids.append(doc["id"])
                    receive_tokens.append(rec_token)

                # Clear cart + office
                session.pop("submit_cart", None)
                session.pop("submit_office_slug", None)
                session.pop("submit_office_name", None)
                session.modified = True
                # Redirect to batch confirmation with tokens
                return redirect(url_for("client_submitted_batch",
                                        ids=",".join(submitted_ids),
                                        tokens=",".join(receive_tokens)))

        # Re-read cart after possible add/remove
        cart = session.get("submit_cart", [])

    # Capture office context from QR scan (?office_slug=...&office_name=...)
    incoming_slug = request.args.get("office_slug","")
    incoming_name = request.args.get("office_name","")
    if incoming_slug and incoming_name:
        session["submit_office_slug"] = incoming_slug
        session["submit_office_name"] = incoming_name
        session.modified = True
    office_slug = session.get("submit_office_slug","")
    office_name = session.get("submit_office_name","")

    return render_template("client_submit.html", cart=cart, error=error, doc={},
                           office_slug=office_slug, office_name=office_name,
                           unit_office_default=_get_client_org(session.get("username","")))

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
#  DOC STATUS QR TOKEN HELPERS
#  Each submitted doc gets a RECEIVE token.
#  When scanned → status=Received → generate RELEASE token.
#  When RELEASE scanned → status=Released. Both log traffic.
# ─────────────────────────────────────────────

def create_doc_token(doc_id, token_type):
    """Create a one-time token for RECEIVE or RELEASE QR. Returns token string."""
    token = f"{token_type[:3].upper()}-{uuid.uuid4().hex[:16].upper()}"
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Remove any previous unused token of same type for this doc
                    cur.execute(
                        "DELETE FROM doc_qr_tokens WHERE doc_id=%s AND token_type=%s AND used=FALSE",
                        (doc_id, token_type)
                    )
                    cur.execute(
                        "INSERT INTO doc_qr_tokens (token, doc_id, token_type) VALUES (%s,%s,%s)",
                        (token, doc_id, token_type)
                    )
                conn.commit()
        except Exception as e:
            print(f"create_doc_token error: {e}")
    else:
        path = "doc_qr_tokens.json"
        tokens = {}
        if os.path.exists(path):
            with open(path) as f: tokens = json.load(f)
        tokens[token] = {"doc_id": doc_id, "token_type": token_type, "used": False}
        with open(path,"w") as f: json.dump(tokens, f)
    return token

def use_doc_token(token):
    """
    Validates and marks a doc QR token as used.
    Returns (doc_id, token_type) or (None, None) if invalid/already used.
    """
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT doc_id, token_type FROM doc_qr_tokens WHERE token=%s AND used=FALSE",
                        (token,)
                    )
                    row = cur.fetchone()
                    if not row:
                        return None, None
                    cur.execute("UPDATE doc_qr_tokens SET used=TRUE WHERE token=%s", (token,))
                conn.commit()
                return row["doc_id"], row["token_type"]
        except Exception as e:
            print(f"use_doc_token error: {e}")
            return None, None
    else:
        path = "doc_qr_tokens.json"
        if not os.path.exists(path): return None, None
        with open(path) as f: tokens = json.load(f)
        t = tokens.get(token)
        if not t or t.get("used"): return None, None
        tokens[token]["used"] = True
        with open(path,"w") as f: json.dump(tokens, f)
        return t["doc_id"], t["token_type"]

def log_office_traffic(office_slug, office_name, event_type, doc_id, client_username):
    """Record a client entering (RECEIVE) or leaving (RELEASE) an office."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO office_traffic
                            (office_slug, office_name, event_type, doc_id, client_username)
                            VALUES (%s,%s,%s,%s,%s)""",
                        (office_slug, office_name, event_type, doc_id, client_username)
                    )
                conn.commit()
        except Exception as e:
            print(f"log_office_traffic error: {e}")
    else:
        path = "office_traffic.json"
        logs = []
        if os.path.exists(path):
            with open(path) as f: logs = json.load(f)
        logs.append({
            "office_slug": office_slug, "office_name": office_name,
            "event_type": event_type, "doc_id": doc_id,
            "client_username": client_username, "scanned_at": now_str()
        })
        with open(path,"w") as f: json.dump(logs, f)

def get_office_traffic_today(office_slug):
    """Returns {received: int, released: int} for today."""
    today = datetime.now().strftime("%Y-%m-%d")
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT event_type, COUNT(*) as cnt FROM office_traffic
                            WHERE office_slug=%s AND DATE(scanned_at)=DATE(NOW())
                            GROUP BY event_type""",
                        (office_slug,)
                    )
                    rows = cur.fetchall()
                    result = {"received": 0, "released": 0}
                    for r in rows:
                        if r["event_type"] == "RECEIVE": result["received"] = r["cnt"]
                        if r["event_type"] == "RELEASE": result["released"] = r["cnt"]
                    return result
        except Exception as e:
            print(f"get_office_traffic_today error: {e}")
            return {"received": 0, "released": 0}
    else:
        path = "office_traffic.json"
        if not os.path.exists(path): return {"received": 0, "released": 0}
        with open(path) as f: logs = json.load(f)
        received = sum(1 for l in logs if l["office_slug"]==office_slug and l["event_type"]=="RECEIVE" and l.get("scanned_at","")[:10]==today)
        released = sum(1 for l in logs if l["office_slug"]==office_slug and l["event_type"]=="RELEASE" and l.get("scanned_at","")[:10]==today)
        return {"received": received, "released": released}

def make_doc_status_qr_png(token, token_type, doc_name, box_size=10):
    """
    Generate a labeled PNG QR code for a RECEIVE or RELEASE token URL.
    token_type: 'RECEIVE' or 'RELEASE'
    """
    from PIL import Image, ImageDraw, ImageFont
    base = os.environ.get("APP_URL", "")
    url  = f"{base}/doc-scan/{token}"

    if token_type == "RECEIVE":
        short_label = "REC"
        label_color = "#1D4ED8"
        bg_color    = "#DBEAFE"
        sub_label   = "SUBMIT TO OFFICE"
    else:
        short_label = "REL"
        label_color = "#065F46"
        bg_color    = "#D1FAE5"
        sub_label   = "PICK UP DOCUMENT"

    qr = qrcode.QRCode(version=None,
                        error_correction=qrcode.constants.ERROR_CORRECT_M,
                        box_size=box_size, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#0A2540", back_color="white").convert("RGB")
    qr_size = qr_img.size[0]

    bar_h, foot_h, pad = 56, 56, 12
    total_w = qr_size + pad * 2
    total_h = bar_h + qr_size + pad * 2 + foot_h

    canvas = Image.new("RGB", (total_w, total_h), "white")
    draw   = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, total_w, bar_h], fill=bg_color)

    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        font_med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        font_sm  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except:
        font_big = font_med = font_sm = ImageFont.load_default()

    # Top label
    bb = draw.textbbox((0,0), short_label, font=font_big)
    draw.text(((total_w-(bb[2]-bb[0]))/2, (bar_h-(bb[3]-bb[1]))/2-2), short_label, font=font_big, fill=label_color)
    canvas.paste(qr_img, (pad, bar_h + pad))

    # Footer
    foot_y = bar_h + qr_size + pad * 2
    draw.rectangle([0, foot_y, total_w, total_h], fill=bg_color)
    bb2 = draw.textbbox((0,0), sub_label, font=font_med)
    draw.text(((total_w-(bb2[2]-bb2[0]))/2, foot_y+8), sub_label, font=font_med, fill=label_color)

    # Doc name (truncated)
    dname = doc_name[:28] + "…" if len(doc_name) > 28 else doc_name
    bb3 = draw.textbbox((0,0), dname, font=font_sm)
    draw.text(((total_w-(bb3[2]-bb3[0]))/2, foot_y+28), dname, font=font_sm, fill="#5A7A91")

    # Bottom bar
    draw.rectangle([0, total_h-4, total_w, total_h], fill=label_color)

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()

# ─────────────────────────────────────────────
#  DOC SCAN — Auto-status QR (RECEIVE / RELEASE)
#  Client gets RECEIVE QR after submission.
#  Staff scans → status=Received → generates RELEASE QR.
#  Staff scans RELEASE → status=Released.
#  Both events log office traffic.
# ─────────────────────────────────────────────

@app.route("/doc-scan/<token>")
def doc_scan(token):
    """
    One-time-use QR scan that auto-updates document status.
    No form needed — just scan and it happens.
    Must be logged in as staff or admin.
    """
    if not is_logged_in():
        return redirect(url_for("login", next=request.url))
    role = session.get("role","")
    if role == "client":
        # Clients cannot operate the receive/release scanner
        flash("This QR code is for office staff only. Please give it to the receiving officer.", "error")
        return redirect(url_for("client_portal"))

    doc_id, token_type = use_doc_token(token)

    if not doc_id:
        return render_template("doc_scan_result.html",
            ok=False,
            msg="This QR code has already been used or is invalid.",
            token_type="UNKNOWN", doc=None, release_qr_b64=None,
            traffic=None)

    doc = get_doc(doc_id)
    if not doc:
        return render_template("doc_scan_result.html",
            ok=False, msg="Document not found.", token_type=token_type,
            doc=None, release_qr_b64=None, traffic=None)

    office_slug = doc.get("target_office_slug", "general")
    office_name = doc.get("target_office_name", "Office")
    actor       = session.get("full_name") or session.get("username") or "Staff"
    release_qr_b64 = None
    traffic        = None

    if token_type == "RECEIVE":
        doc["status"]        = "Received"
        doc["date_received"] = now_str()[:10]
        doc["received_by"]   = actor
        doc.setdefault("travel_log",[]).append({
            "office":    office_name,
            "action":    "Document Received at Office",
            "officer":   actor,
            "timestamp": now_str(),
            "remarks":   "Auto-updated via RECEIVE QR scan.",
        })
        save_doc(doc)
        # Log traffic — client entered
        log_office_traffic(office_slug, office_name, "RECEIVE", doc_id,
                           doc.get("submitted_by",""))
        # Generate RELEASE token for when they pick up
        rel_token = create_doc_token(doc_id, "RELEASE")
        rel_png   = make_doc_status_qr_png(rel_token, "RELEASE", doc.get("doc_name","Document"))
        release_qr_b64 = base64.b64encode(rel_png).decode()
        doc["release_token"] = rel_token  # store for reference (not saved to DB)
        save_doc(doc)
        traffic = get_office_traffic_today(office_slug)
        audit_log("doc_received_qr", f"doc_id={doc_id} office={office_name}")

    elif token_type == "RELEASE":
        doc["status"]        = "Released"
        doc["date_released"] = now_str()[:10]
        doc.setdefault("travel_log",[]).append({
            "office":    office_name,
            "action":    "Document Released / Picked Up",
            "officer":   actor,
            "timestamp": now_str(),
            "remarks":   "Auto-updated via RELEASE QR scan. Client picked up document.",
        })
        save_doc(doc)
        # Log traffic — client left
        log_office_traffic(office_slug, office_name, "RELEASE", doc_id,
                           doc.get("submitted_by",""))
        traffic = get_office_traffic_today(office_slug)
        audit_log("doc_released_qr", f"doc_id={doc_id} office={office_name}")

    return render_template("doc_scan_result.html",
        ok=True, token_type=token_type, doc=doc,
        office_name=office_name, actor=actor,
        release_qr_b64=release_qr_b64,
        release_token=doc.get("release_token"),
        traffic=traffic,
        msg=None)

# ─────────────────────────────────────────────
#  OFFICE QR ACTIONS — Receive / Release stations
# ─────────────────────────────────────────────

@app.route("/office-action/<path:action>", methods=["GET","POST"])
def office_action(action):
    """
    Office QR scan landing page.
    action format: 'receive', 'release', or 'OfficeName-rec', 'OfficeName-rel', 'OfficeName-reg'
    """
    # Parse office name and action type from format "OfficeName-rec/rel/reg/sub"
    office_slug = re.sub(r'\s+', '-', action.rsplit('-',1)[0]).lower() if '-' in action else action
    office_name = None
    if action.endswith("-rec"):
        office_name = action[:-4].replace("-", " ").title()
        action_type = "receive"
    elif action.endswith("-rel"):
        office_name = action[:-4].replace("-", " ").title()
        action_type = "release"
    elif action.endswith("-reg"):
        office_name = action[:-4].replace("-", " ").title()
        slug = action[:-4].lower()
        # QR1: Registration — show gate page (register or login)
        if is_logged_in() and session.get("role") == "client":
            # Already registered — go straight to portal
            return redirect(url_for("client_portal"))
        return render_template("client_gate.html",
            office_name=office_name,
            office_slug=slug,
            next_url=url_for("client_portal"))
    elif action.endswith("-sub"):
        # QR2: Submission — redirect client to submit form pre-filled with this office
        office_name = action[:-4].replace("-", " ").title()
        slug = action[:-4].lower()
        submit_url = f"/client/submit?office_slug={urllib.parse.quote(slug)}&office_name={urllib.parse.quote(office_name)}"
        if not is_logged_in():
            # Not logged in — show register/login choice page with office context
            return render_template("client_gate.html",
                office_name=office_name,
                office_slug=slug,
                next_url=submit_url)
        if session.get("role") != "client":
            flash("This QR code is for clients. Please log in with a client account.", "error")
            return redirect(url_for("index"))
        return redirect(submit_url)
    elif action in ("receive", "release"):
        action_type = action
        office_slug = "main-office"
        office_name = "Main Office"
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
    """Generate office QR code PNG with label text — REG / REC / REL."""
    from PIL import Image, ImageDraw, ImageFont
    base = os.environ.get("APP_URL", request.host_url.rstrip("/"))
    # Embed signed URL so QR codes can be verified and expired
    signed_action = sign_office_action(action)
    url = base + "/office-action/" + signed_action

    # Determine short label and office display name
    if action.endswith("-rec"):
        short_label = "REC"
        label_color = "#1D4ED8"
        bg_color    = "#DBEAFE"
        office_display = action[:-4].replace("-", " ").title()
        sub_label = "RECEIVE DOCUMENT"
    elif action.endswith("-rel"):
        short_label = "REL"
        label_color = "#065F46"
        bg_color    = "#D1FAE5"
        office_display = action[:-4].replace("-", " ").title()
        sub_label = "RELEASE DOCUMENT"
    elif action.endswith("-reg"):
        short_label = "REG"
        label_color = "#92400E"
        bg_color    = "#FEF3C7"
        office_display = action[:-4].replace("-", " ").title()
        sub_label = "CLIENT REGISTRATION"
    else:
        short_label = action.upper()[:3]
        label_color = "#0A2540"
        bg_color    = "#F0F7FA"
        office_display = action.replace("-", " ").title()
        sub_label = "OFFICE QR"

    # Generate QR module
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10, border=3
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#0A2540", back_color="white").convert("RGB")
    qr_size = qr_img.size[0]  # square

    # Build canvas: QR + header bar + footer bar
    bar_h    = 56   # top bar height
    foot_h   = 48   # bottom bar height
    pad      = 12
    total_w  = qr_size + pad * 2
    total_h  = bar_h + qr_size + pad * 2 + foot_h

    canvas = Image.new("RGB", (total_w, total_h), "white")
    draw   = ImageDraw.Draw(canvas)

    # ── TOP BAR (colored background with short label) ──
    draw.rectangle([0, 0, total_w, bar_h], fill=bg_color)

    # Try to load a font, fall back gracefully
    try:
        font_big  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_med  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        font_sm   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except:
        font_big  = ImageFont.load_default()
        font_med  = ImageFont.load_default()
        font_sm   = ImageFont.load_default()

    # Draw short label centered in top bar
    bbox = draw.textbbox((0, 0), short_label, font=font_big)
    lw   = bbox[2] - bbox[0]
    lh   = bbox[3] - bbox[1]
    draw.text(((total_w - lw) / 2, (bar_h - lh) / 2 - 2), short_label, font=font_big, fill=label_color)

    # ── QR CODE ──
    canvas.paste(qr_img, (pad, bar_h + pad))

    # ── BOTTOM BAR (white with office name + sub label) ──
    foot_y = bar_h + qr_size + pad * 2

    # Sub label (REC / REL / REG description)
    bbox2 = draw.textbbox((0, 0), sub_label, font=font_med)
    sw = bbox2[2] - bbox2[0]
    draw.text(((total_w - sw) / 2, foot_y + 6), sub_label, font=font_med, fill=label_color)

    # Office name
    # Truncate if too long
    office_text = office_display
    while True:
        bbox3 = draw.textbbox((0, 0), office_text, font=font_sm)
        if bbox3[2] - bbox3[0] <= total_w - 16 or len(office_text) < 5:
            break
        office_text = office_text[:-4] + "..."
    bbox3 = draw.textbbox((0, 0), office_text, font=font_sm)
    ow = bbox3[2] - bbox3[0]
    draw.text(((total_w - ow) / 2, foot_y + 26), office_text, font=font_sm, fill="#5A7A91")

    # Thin colored line at bottom
    draw.rectangle([0, total_h - 4, total_w, total_h], fill=label_color)

    buf = BytesIO()
    canvas.save(buf, format="PNG")
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

def make_office_reg_code(office_slug):
    """Generate a stable per-office registration code using HMAC."""
    raw = hmac.new(QR_SIGN_SECRET.encode(), f"reg:{office_slug}".encode(), hashlib.sha256).hexdigest()[:12]
    return f"reg-{raw}"

def save_office(office_name, created_by):
    """Persist an office name so it shows on any device."""
    office_slug = re.sub(r'\s+', '-', office_name.strip().lower())
    reg_code = make_office_reg_code(office_slug)
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO saved_offices (office_slug, office_name, created_by)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (office_slug) DO UPDATE SET office_name=EXCLUDED.office_name
                    """, (office_slug, office_name.strip(), created_by))
                conn.commit()
        except Exception as e:
            print(f"save_office error: {e}")
    else:
        # JSON fallback
        path = "saved_offices.json"
        offices = {}
        if os.path.exists(path):
            with open(path) as f_off:
                offices = json.load(f_off)
        offices[office_slug] = {"office_name": office_name.strip(), "created_by": created_by}
        with open(path, "w") as f_off:
            json.dump(offices, f_off, indent=2)
    return reg_code

def load_saved_offices():
    """Load all saved offices, newest first."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT office_name, office_slug, created_by, created_at FROM saved_offices ORDER BY created_at DESC")
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"load_saved_offices error: {e}")
            return []
    else:
        path = "saved_offices.json"
        if not os.path.exists(path):
            return []
        with open(path) as f:
            offices = json.load(f)
        return [{"office_name": v["office_name"], "office_slug": k, "created_by": v.get("created_by","")} for k, v in offices.items()]

def delete_saved_office(office_slug):
    """Remove a saved office."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM saved_offices WHERE office_slug=%s", (office_slug,))
                conn.commit()
        except Exception as e:
            print(f"delete_saved_office error: {e}")
    else:
        path = "saved_offices.json"
        if os.path.exists(path):
            with open(path) as f:
                offices = json.load(f)
            offices.pop(office_slug, None)
            with open(path, "w") as f:
                json.dump(offices, f, indent=2)

@app.route("/office-qr-page", methods=["GET","POST"])
@login_required
def office_qr_page():
    """Staff page to generate and view saved office QR codes."""
    base = os.environ.get("APP_URL", request.host_url.rstrip("/"))

    # Handle DELETE saved office
    if request.method == "POST" and request.form.get("_action") == "delete_office":
        slug_to_delete = request.form.get("office_slug","").strip()
        if slug_to_delete:
            delete_saved_office(slug_to_delete)
            flash("Office removed.", "success")
        return redirect(url_for("office_qr_page"))

    office_name = request.args.get("office", "").strip() or request.form.get("office_name", "").strip()
    qr_data = None

    def make_slug(name, suffix):
        return re.sub(r'\s+', '-', name.strip()) + suffix

    if office_name:
        # Save it so it persists across devices
        save_office(office_name, session.get("username", ""))
        qr_data = {
            "reg": make_slug(office_name, "-reg"),   # QR1: client registration
            "sub": make_slug(office_name, "-sub"),   # QR2: client submission to this office
            "rec": make_slug(office_name, "-rec"),   # QR3a: staff receive scanner
            "rel": make_slug(office_name, "-rel"),   # QR3b: staff release scanner
        }
        # Get today's traffic for this office
        office_slug_key = re.sub(r'\s+', '-', office_name.strip().lower())
        office_traffic  = get_office_traffic_today(office_slug_key)
    else:
        office_traffic = None

    saved_offices = load_saved_offices()

    return render_template("office_qr_page.html",
                           base=base,
                           office_name=office_name,
                           qr_data=qr_data,
                           office_traffic=office_traffic if office_name else None,
                           saved_offices=saved_offices,
                           client_reg_code=CLIENT_REG_CODE)

# ─────────────────────────────────────────────
#  QUICK STATUS UPDATE (staff manual)
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
#  ROUTING SLIPS — batch route docs to another office
# ─────────────────────────────────────────────

def generate_slip_no():
    """e.g. SLIP-2026-A3F9"""
    yr = datetime.now().strftime("%Y")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"SLIP-{yr}-{suffix}"

def save_routing_slip(slip):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO routing_slips
                            (id,slip_no,destination,prepared_by,doc_ids,notes,slip_date,time_from,time_to)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (id) DO UPDATE SET
                            destination=EXCLUDED.destination,
                            doc_ids=EXCLUDED.doc_ids,
                            notes=EXCLUDED.notes,
                            slip_date=EXCLUDED.slip_date,
                            time_from=EXCLUDED.time_from,
                            time_to=EXCLUDED.time_to""",
                        (slip["id"], slip["slip_no"], slip["destination"],
                         slip["prepared_by"], json.dumps(slip["doc_ids"]),
                         slip.get("notes",""), slip.get("slip_date",""),
                         slip.get("time_from",""), slip.get("time_to",""))
                    )
                conn.commit()
        except Exception as e:
            print(f"save_routing_slip error: {e}")
    else:
        path = "routing_slips.json"
        slips = {}
        if os.path.exists(path):
            with open(path) as f: slips = json.load(f)
        slips[slip["id"]] = slip
        with open(path,"w") as f: json.dump(slips, f)

def get_routing_slip(slip_id):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM routing_slips WHERE id=%s", (slip_id,))
                    row = cur.fetchone()
                    if not row: return None
                    r = dict(row)
                    r["doc_ids"] = r["doc_ids"] if isinstance(r["doc_ids"], list) else json.loads(r["doc_ids"])
                    r["created_at"] = str(r["created_at"])[:19] if r.get("created_at") else now_str()
                    return r
        except Exception as e:
            print(f"get_routing_slip error: {e}")
            return None
    else:
        path = "routing_slips.json"
        if not os.path.exists(path): return None
        with open(path) as f: slips = json.load(f)
        return slips.get(slip_id)

@app.route("/routing-slip/create", methods=["POST"])
@login_required
def create_routing_slip():
    """
    Staff selects documents from dashboard, picks a destination office,
    and creates a routing slip. Selected docs get status → In Transit.
    """
    doc_ids_raw = request.form.get("doc_ids","").strip()
    destination = request.form.get("destination","").strip()
    notes       = request.form.get("notes","").strip()

    if not doc_ids_raw or not destination:
        flash("Please select documents and enter a destination office.", "error")
        return redirect(url_for("index"))

    doc_ids = [d.strip() for d in doc_ids_raw.split(",") if d.strip()]
    if not doc_ids:
        flash("No valid document IDs selected.", "error")
        return redirect(url_for("index"))

    slip_date  = request.form.get("slip_date","").strip()  or now_str()[:10]
    time_from  = request.form.get("time_from","").strip()
    time_to    = request.form.get("time_to","").strip()
    actor = session.get("full_name") or session.get("username") or "Staff"
    slip  = {
        "id":          str(uuid.uuid4())[:8].upper(),
        "slip_no":     generate_slip_no(),
        "destination": destination,
        "prepared_by": actor,
        "doc_ids":     doc_ids,
        "notes":       notes,
        "slip_date":   slip_date,
        "time_from":   time_from,
        "time_to":     time_to,
        "created_at":  now_str(),
    }
    save_routing_slip(slip)

    # Update each doc: status → In Transit, log travel entry
    for doc_id in doc_ids:
        doc = get_doc(doc_id)
        if doc:
            doc["status"]       = "In Transit"
            doc["forwarded_to"] = destination
            doc.setdefault("travel_log",[]).append({
                "office":    destination,
                "action":    "Forwarded — In Transit",
                "officer":   actor,
                "timestamp": now_str(),
                "remarks":   f"Included in routing slip {slip['slip_no']}. Forwarded to {destination}.",
            })
            save_doc(doc)

    audit_log("routing_slip_created",
              f"slip={slip['slip_no']} dest={destination} docs={len(doc_ids)}")
    return redirect(url_for("view_routing_slip", slip_id=slip["id"]))

@app.route("/routing-slip/<slip_id>")
@login_required
def view_routing_slip(slip_id):
    """View / print a routing slip."""
    slip = get_routing_slip(slip_id)
    if not slip:
        flash("Routing slip not found.", "error")
        return redirect(url_for("index"))
    docs = [get_doc(d) for d in slip["doc_ids"]]
    docs = [d for d in docs if d]
    return render_template("routing_slip.html", slip=slip, docs=docs)

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
