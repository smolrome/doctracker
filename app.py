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
import secrets
import time

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

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
            current_office  = session.get("office", ""),
            now             = datetime.now,
            session         = session,
        )

    # ── Request audit logger ──────────────────────────────────────────────────
    AUDIT_WRITE_PATHS = ("/add", "/edit/", "/delete/", "/update-status/",
                         "/routing-slip/", "/routed-documents",
                         "/manage-users", "/send-invite", "/import-excel",
                         "/clear-database", "/backup", "/restore",
                         "/register", "/logout")

    @app.before_request
    def log_write_requests():
        """Log every state-changing HTTP request with IP and user."""
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        path = request.path
        print(f"[HTTP] {request.method} {path} — before_request fired")
        if any(path.startswith("/static") for _ in [1]):
            return
        try:
            from services.misc import audit_log
            actor = session.get("username", "anonymous")
            detail = f"method={request.method} path={path}"
            if request.form:
                # Log form fields except passwords and tokens
                safe_fields = {k: v[:120] for k, v in request.form.items()
                               if k not in ("password", "confirm_password",
                                            "_csrf_token", "password_hash")}
                if safe_fields:
                    detail += f" fields={safe_fields}"
            audit_log("http_write", detail, username=actor, ip=get_client_ip())
        except Exception:
            pass  # Never let logging crash the request

    # ── CSRF Protection ────────────────────────────────────────────────────────
    CSRF_EXEMPT_PREFIXES = ("/office-action/", "/slip-scan/", "/doc-scan/",
                            "/client/", "/static/", "/office-qr/",
                            "/login", "/register", "/logout")

    @app.before_request
    def csrf_check():
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        # Exempt QR scan endpoints (accessed by scanning device, no session)
        path = request.path
        if any(path.startswith(p) for p in CSRF_EXEMPT_PREFIXES):
            return
        session_token = session.get("_csrf_token")
        form_token    = (request.form.get("_csrf_token")
                         or request.headers.get("X-CSRF-Token"))
        if not session_token or not form_token:
            return redirect(url_for("auth.login"))
        if not secrets.compare_digest(session_token, form_token):
            flash("Security check failed. Please try again.", "error")
            return redirect(request.referrer or url_for("dashboard.index"))

    @app.before_request
    def inject_csrf_token():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_hex(32)

    # Make CSRF token available in all templates
    @app.context_processor
    def csrf_context():
        return {"csrf_token": session.get("_csrf_token", "")}

    # Security headers on every response
    @app.after_request
    def add_security_headers(response):
        response.headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options":        "SAMEORIGIN",
            "X-XSS-Protection":       "1; mode=block",
            "Referrer-Policy":        "strict-origin-when-cross-origin",
            "Permissions-Policy":     "geolocation=(), microphone=(), camera=(self)",
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            ),
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        })
        if is_logged_in():
            last_active = session.get("last_active", 0)
            now = time.time()
            if last_active and now - last_active > 4 * 3600:
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

    # API endpoints — require staff/admin login
    @app.route("/api/gen-ref")
    def api_gen_ref():
        if not is_logged_in() or session.get("role") not in ("staff", "admin"):
            return jsonify({"error": "unauthorized"}), 401
        from services.documents import generate_ref
        return jsonify({"ref": generate_ref()})

    @app.route("/api/docs")
    def api_docs():
        if not is_logged_in() or session.get("role") not in ("staff", "admin"):
            return jsonify({"error": "unauthorized"}), 401
        from services.documents import load_docs
        try:
            from services.misc import audit_log
            audit_log("api_docs_export", "Full document list exported via API",
                      username=session.get("username","?"), ip=get_client_ip())
        except Exception:
            pass
        return jsonify(load_docs())

    @app.route("/api/docs/<doc_id>/log")
    def api_log(doc_id):
        if not is_logged_in() or session.get("role") not in ("staff", "admin"):
            return jsonify({"error": "unauthorized"}), 401
        from services.documents import get_doc
        doc = get_doc(doc_id)
        if not doc:
            return jsonify({"error": "not found"}), 404
        return jsonify(doc.get("travel_log", []))

    # 404 handler
    @app.errorhandler(404)
    def not_found(e):
        try:
            from services.misc import audit_log
            audit_log("404_not_found", f"path={request.path}",
                      username=session.get("username", "anonymous"),
                      ip=get_client_ip())
        except Exception:
            pass
        return render_template("500.html",
                               error_title="Page Not Found",
                               error_msg="The page you requested does not exist."), 404

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