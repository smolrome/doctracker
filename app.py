"""
app.py — Flask application factory.

Security fixes applied:
  1.  CSRF token name unified: both app-level middleware and client.py now use
      'csrf_token' (session key) and 'csrf_token' (form field / header).
  2.  /client/* is NO LONGER globally CSRF-exempt — client.py handles its own
      CSRF checks via _require_csrf().  Only true scan/QR endpoints are exempt.
  3.  Audit logger no longer logs csrf_token values (added to redact list).
  4.  Session idle timeout moved from after_request (wrong place — runs AFTER
      response is already built) to before_request so expired sessions are
      caught before any handler runs.
  5.  4-hour hard idle limit raised to a configurable constant and checked
      consistently; session.clear() is followed by a redirect, not just a flash,
      so the stale session cookie is replaced immediately.
  6.  403 error handler redirects to login for unauthenticated users instead of
      always sending to dashboard (which would 302-loop for guests).
  7.  CSP 'unsafe-inline' for scripts tightened with a note — replace with
      nonces when templates are ready.
  8.  check_session_active now also runs for clients (not just non-admin roles —
      original already did this, but comment clarified).
  9.  CSRF exempt list is now a frozenset tuple of exact prefixes; comment
      documents why each prefix is exempt.
 10.  Secret key length guard added at startup.
"""

import os
import secrets
import time
from datetime import timedelta

from flask import (Flask, flash, jsonify, redirect,
                   render_template, request, session, url_for)

import config
from utils import get_client_ip, is_logged_in

# ── Optional dependencies ──────────────────────────────────────────────────────

try:
    import psycopg2
    _PSYCOPG2_OK = True
except ImportError:
    _PSYCOPG2_OK = False


# ── Constants ──────────────────────────────────────────────────────────────────

# FIX 4/5: single source-of-truth for the idle timeout (seconds)
SESSION_IDLE_TIMEOUT = int(os.environ.get("SESSION_IDLE_TIMEOUT", 4 * 3600))

# FIX 1: single canonical name used everywhere (session key AND form field)
CSRF_SESSION_KEY = "csrf_token"
CSRF_FORM_FIELD  = "csrf_token"
CSRF_HEADER      = "X-CSRF-Token"

# FIX 2/9: Only endpoints that are genuinely accessed without a browser session
# (QR-scanner devices, static files, auth pages) are exempt.
# /client/* is intentionally REMOVED — client.py calls _require_csrf() itself.
CSRF_EXEMPT_PREFIXES = (
    "/office-action/",   # scanned by physical QR reader, no session
    "/slip-scan/",       # same
    "/doc-scan/",        # same
    "/static/",          # static assets
    "/office-qr/",       # QR image download, no state change
    "/login",            # not yet authenticated
    "/register",         # not yet authenticated
    "/logout",           # GET-based logout can stay; POST logout gets CSRF from form
)


# ── Application factory ────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__)

    # FIX 10: Warn loudly if the secret key is too short or is the default
    secret = config.SECRET_KEY
    if not secret or len(secret) < 32:
        raise RuntimeError(
            "SECRET_KEY must be at least 32 characters. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    app.secret_key = secret
    app.config.update(
        SESSION_COOKIE_HTTPONLY    = config.SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE    = config.SESSION_COOKIE_SAMESITE,
        SESSION_COOKIE_SECURE      = config.SESSION_COOKIE_SECURE,
        PERMANENT_SESSION_LIFETIME = config.PERMANENT_SESSION_LIFETIME,
        MAX_CONTENT_LENGTH         = config.MAX_CONTENT_LENGTH,
    )

    # Initialize database
    from services.database import USE_DB, init_db
    if USE_DB:
        try:
            init_db()
        except Exception as e:
            print(f"DB init error: {e}")

    # Register blueprints
    from routes.auth         import auth_bp
    from routes.admin        import admin_bp
    from routes.dashboard    import dashboard_bp
    from routes.client       import client_bp
    from routes.scanning     import scanning_bp
    from routes.offices      import offices_bp
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

    # ── Template filter ────────────────────────────────────────────────────────

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
            h, m   = int(hhmm[:2]), int(hhmm[3:5])
            period = "AM" if h < 12 else "PM"
            return f"{h % 12 or 12}:{m:02d} {period}"
        except Exception:
            return str(ts)

    # ── Context processors ─────────────────────────────────────────────────────

    @app.context_processor
    def inject_auth():
        from datetime import datetime
        return dict(
            logged_in         = is_logged_in(),
            current_user      = session.get("username", ""),
            current_role      = session.get("role", "guest"),
            current_full_name = session.get("full_name", ""),
            current_office    = session.get("office", ""),
            now               = datetime.now,
            session           = session,
        )

    # FIX 1: CSRF token injected globally using the unified key name
    @app.context_processor
    def csrf_context():
        return {CSRF_FORM_FIELD: session.get(CSRF_SESSION_KEY, "")}

    # ── Before-request hooks ───────────────────────────────────────────────────

    @app.before_request
    def ensurecsrf_token():
        """Ensure every session has a CSRF token before any handler runs."""
        if CSRF_SESSION_KEY not in session:
            session[CSRF_SESSION_KEY] = secrets.token_hex(32)

    # FIX 4/5: idle-timeout check moved to before_request so it fires BEFORE
    # the handler, and clears + redirects properly instead of just flashing.
    @app.before_request
    def enforce_session_timeout():
        """Expire idle sessions before any handler runs."""
        if not is_logged_in():
            return
        last_active = session.get("last_active", 0)
        if last_active and (time.time() - last_active) > SESSION_IDLE_TIMEOUT:
            session.clear()
            flash("Your session expired. Please log in again.", "error")
            return redirect(url_for("auth.login"))
        session["last_active"] = time.time()

    @app.before_request
    def log_write_requests():
        """Audit-log every state-changing HTTP request."""
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        if request.path.startswith("/static"):
            return
        try:
            from services.misc import audit_log
            actor  = session.get("username", "anonymous")
            detail = f"method={request.method} path={request.path}"
            if request.form:
                # FIX 3: redact passwords, hashes AND the csrf token from logs
                _REDACT = {"password", "confirm_password", "password_hash",
                           CSRF_FORM_FIELD, "csrf_token"}
                safe_fields = {
                    k: v[:120]
                    for k, v in request.form.items()
                    if k not in _REDACT
                }
                if safe_fields:
                    detail += f" fields={safe_fields}"
            audit_log("http_write", detail, username=actor, ip=get_client_ip())
        except Exception:
            pass  # Never let logging crash the request

    # FIX 1/2: Unified CSRF enforcement using the single token key.
    # /client/* is no longer exempt — it handles CSRF internally.
    @app.before_request
    def csrf_check():
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        path = request.path
        if any(path.startswith(p) for p in CSRF_EXEMPT_PREFIXES):
            return
        session_token = session.get(CSRF_SESSION_KEY, "")
        form_token    = (request.form.get(CSRF_FORM_FIELD, "")
                         or request.headers.get(CSRF_HEADER, ""))
        if not session_token or not form_token:
            flash("Security check failed. Please try again.", "error")
            return redirect(request.referrer or url_for("auth.login"))
        if not secrets.compare_digest(session_token, form_token):
            try:
                from services.misc import audit_log
                audit_log("csrf_mismatch",
                          f"path={path}",
                          username=session.get("username", "anonymous"),
                          ip=get_client_ip())
            except Exception:
                pass
            flash("Security check failed. Please try again.", "error")
            return redirect(request.referrer or url_for("auth.login"))

    @app.before_request
    def check_session_active():
        """Block disabled accounts mid-session before any handler runs."""
        # Exempt unauthenticated requests and static files
        if not is_logged_in() or request.path.startswith("/static"):
            return
        username = session.get("username", "")
        if username and USE_DB:
            try:
                from services.database import get_conn
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT active FROM users WHERE username=%s",
                            (username,),
                        )
                        row = cur.fetchone()
                if row and not row["active"]:
                    session.clear()
                    flash("Your account has been disabled. Contact the administrator.", "error")
                    return redirect(url_for("auth.login"))
            except Exception:
                pass

    # ── After-request hooks ────────────────────────────────────────────────────

    @app.after_request
    def add_security_headers(response):
        """
        Attach security headers to every response.

        FIX 7: 'unsafe-inline' for script-src is kept for now because templates
        use inline <script> blocks. Replace with per-request nonces
        (flask-talisman or manual nonce injection) when templates are updated.
        """
        response.headers.update({
            "X-Content-Type-Options":  "nosniff",
            "X-Frame-Options":         "SAMEORIGIN",
            "X-XSS-Protection":        "1; mode=block",
            "Referrer-Policy":         "strict-origin-when-cross-origin",
            "Permissions-Policy":      "geolocation=(), microphone=(), camera=(self)",
            "Content-Security-Policy": (
                "default-src 'self'; "
                # TODO: replace 'unsafe-inline' with nonces once templates support it
                "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com "
                "           https://fonts.gstatic.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            ),
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        })
        return response

    # ── Error handlers ─────────────────────────────────────────────────────────

    @app.errorhandler(500)
    def internal_error(e):
        import traceback
        print(f"500 ERROR:\n{traceback.format_exc()}")
        if os.environ.get("FLASK_DEBUG") == "1":
            return (
                f"<pre style='padding:20px'><b>500 Error</b>\n\n"
                f"{traceback.format_exc()}</pre>"
            ), 500
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
        return render_template(
            "500.html",
            error_title="Too Many Attempts",
            error_msg="Please wait a few minutes before trying again.",
        ), 429

    # FIX 6: Send unauthenticated users to login, authenticated to dashboard.
    @app.errorhandler(403)
    def forbidden(e):
        if not is_logged_in():
            flash("Please log in to access that page.", "error")
            return redirect(url_for("auth.login"))
        flash("You do not have permission to access that page.", "error")
        return redirect(url_for("dashboard.index"))

    @app.errorhandler(404)
    def not_found(e):
        try:
            from services.misc import audit_log
            audit_log("404_not_found", f"path={request.path}",
                      username=session.get("username", "anonymous"),
                      ip=get_client_ip())
        except Exception:
            pass
        return render_template(
            "500.html",
            error_title="Page Not Found",
            error_msg="The page you requested does not exist.",
        ), 404

    # ── Internal API endpoints ─────────────────────────────────────────────────

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
                      username=session.get("username", "?"), ip=get_client_ip())
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