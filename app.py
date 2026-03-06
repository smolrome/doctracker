"""
app.py — Flask application factory.

Structure:
  config.py           — all environment variables and constants
  utils.py            — shared decorators and helpers
  services/
    database.py       — DB connection, table creation, migrations
    auth.py           — password hashing, user CRUD, rate limiting
    documents.py      — document CRUD and statistics
    qr.py             — QR generation, signing, image decoding
    email.py          — invite tokens and Brevo email
    misc.py           — audit log, offices, routing slips
  routes/
    auth.py           — /login  /register  /logout
    admin.py          — /manage-users  /send-invite  /activity-log  etc.
    dashboard.py      — /  /add  /edit  /view  /delete  /trash  etc.
    client.py         — /client/*
    scanning.py       — /office-action  /doc-scan  /receive  /scan  etc.
    offices.py        — /office-qr-page  /routing-slip/*  /welcome  etc.
"""

import os
import time

from flask import Flask, flash, jsonify, redirect, render_template, session, url_for

import config
from utils import get_client_ip, is_logged_in

# ── Optional dependencies ──────────────────────────────────────────────────────

try:
    import psycopg2
    _PSYCOPG2_OK = True
except ImportError:
    _PSYCOPG2_OK = False


# ── Application factory ────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__)

    # Load config
    app.secret_key = config.SECRET_KEY
    app.config.update(
        SESSION_COOKIE_HTTPONLY   = config.SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE   = config.SESSION_COOKIE_SAMESITE,
        SESSION_COOKIE_SECURE     = config.SESSION_COOKIE_SECURE,
        PERMANENT_SESSION_LIFETIME = config.PERMANENT_SESSION_LIFETIME,
        MAX_CONTENT_LENGTH        = config.MAX_CONTENT_LENGTH,
    )

    # Initialize database
    from services.database import USE_DB, init_db
    if USE_DB:
        try:
            init_db()
        except Exception as e:
            print(f"DB init error: {e}")

    # Register blueprints
    from routes.auth      import auth_bp
    from routes.admin     import admin_bp
    from routes.dashboard import dashboard_bp
    from routes.client    import client_bp
    from routes.scanning  import scanning_bp
    from routes.offices   import offices_bp
    from routes.backup       import backup_bp
    from routes.import_excel import import_bp
    from routes.progress     import progress_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(client_bp)
    app.register_blueprint(scanning_bp)
    app.register_blueprint(offices_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(import_bp)
    app.register_blueprint(progress_bp)

    # Register template filter
    @app.template_filter("time12")
    def time12_filter(ts):
        """Convert 'YYYY-MM-DD HH:MM:SS' or 'HH:MM' to 12-hr format."""
        if not ts:
            return "—"
        try:
            t = str(ts).strip()
            if "T" in t:
                hhmm = t[11:16]
            elif len(t) >= 16:
                hhmm = t[11:16]
            elif ":" in t and len(t) <= 5:
                hhmm = t
            else:
                return t
            h, m    = int(hhmm[:2]), int(hhmm[3:5])
            period  = "AM" if h < 12 else "PM"
            return f"{h % 12 or 12}:{m:02d} {period}"
        except Exception:
            return str(ts)

    # Context processor — injects auth variables into every template
    @app.context_processor
    def inject_auth():
        from datetime import datetime
        return dict(
            logged_in       = is_logged_in(),
            current_user    = session.get("username", ""),
            current_role    = session.get("role", "guest"),
            current_full_name = session.get("full_name", ""),
            now             = datetime.now,
        )

    # Security headers on every response
    @app.after_request
    def add_security_headers(response):
        response.headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options":        "SAMEORIGIN",
            "X-XSS-Protection":       "1; mode=block",
            "Referrer-Policy":        "strict-origin-when-cross-origin",
            "Permissions-Policy":     "geolocation=(), microphone=(), camera=(self)",
        })
        if is_logged_in():
            last_active = session.get("last_active", 0)
            now = time.time()
            if last_active and now - last_active > 8 * 3600:
                session.clear()
                flash("Your session expired. Please log in again.", "error")
            else:
                session["last_active"] = now
        return response

    # Block disabled accounts mid-session
    @app.before_request
    def check_session_active():
        if not is_logged_in() or session.get("role") == "admin":
            return
        username = session.get("username", "")
        if username and USE_DB:
            try:
                from services.database import get_conn
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT active FROM users WHERE username=%s", (username,))
                        row = cur.fetchone()
                        if row and not row["active"]:
                            session.clear()
                            flash("Your account has been disabled. Contact the administrator.", "error")
                            return redirect(url_for("auth.login"))
            except Exception:
                pass

    # Error handlers
    @app.errorhandler(500)
    def internal_error(e):
        import traceback
        print(f"500 ERROR:\n{traceback.format_exc()}")
        if os.environ.get("FLASK_DEBUG") == "1":
            return (f"<pre style='padding:20px'><b>500 Error</b>\n\n"
                    f"{traceback.format_exc()}</pre>"), 500
        try:
            from services.misc import audit_log
            audit_log("500_error", str(e)[:300],
                      username=session.get("username", "anonymous"),
                      ip=get_client_ip())
        except Exception:
            pass
        return render_template("500.html"), 500

    @app.errorhandler(429)
    def too_many_requests(e):
        return render_template("500.html",
                               error_title="Too Many Attempts",
                               error_msg="Please wait a few minutes before trying again."), 429

    @app.errorhandler(403)
    def forbidden(e):
        flash("You do not have permission to access that page.", "error")
        return redirect(url_for("dashboard.index"))

    # Logo route
    @app.route("/logo.png")
    def serve_logo():
        import os
        logo = os.path.join(os.path.dirname(__file__), "templates", "logo", "doctrackerLOGO.png")
        from flask import send_file
        return send_file(logo, mimetype="image/png")

    # Public API endpoints
    @app.route("/api/gen-ref")
    def api_gen_ref():
        from services.documents import generate_ref
        return jsonify({"ref": generate_ref()})

    @app.route("/api/docs")
    def api_docs():
        from services.documents import load_docs
        return jsonify(load_docs())

    @app.route("/api/docs/<doc_id>/log")
    def api_log(doc_id):
        from services.documents import get_doc
        doc = get_doc(doc_id)
        if not doc:
            return jsonify({"error": "not found"}), 404
        return jsonify(doc.get("travel_log", []))

    return app


# ── Entry point ────────────────────────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    import socket
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "your-ip"
    print("\n" + "=" * 55)
    print("  DepEd Leyte Division — Document Tracker")
    print("=" * 55)
    print(f"  ✅ Server running!")
    print(f"  📡 Local: http://{local_ip}:5000")
    print("=" * 55 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000)
