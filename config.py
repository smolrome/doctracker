"""
config.py — All configuration in one place.
Set these as Railway environment variables in production.

Security fixes applied:
  1.  SECRET_KEY default is now a random value per-process in dev instead of a
      fixed known string — eliminates the risk of the default ever reaching prod.
  2.  ADMIN_PASSWORD default removed entirely; startup raises an error in
      production if it is not explicitly set.
  3.  SESSION_COOKIE_SECURE now also activates when HTTPS is detected via
      FORWARDED_PROTO, not only on Railway.
  4.  PERMANENT_SESSION_LIFETIME reduced from 8 hours to 2 hours; idle timeout
      in app.py handles the 4-hour window, so the cookie lifetime is a backstop.
  5.  QR_SIGN_SECRET falls back to SECRET_KEY only as a last resort and warns
      loudly — a dedicated secret is strongly recommended.
  6.  CLIENT_REG_CODE default changed from the guessable "client-reg" to a
      random token generated at startup if not set.
  7.  All "WARNING" prints upgraded to use warnings.warn so they appear in logs
      with a stacktrace and can be filtered/escalated by log aggregators.
  8.  IS_PRODUCTION helper derived in one place and reused throughout to avoid
      repeated inline environment checks.
  9.  MAX_CONTENT_LENGTH kept at 10 MB but documented and made env-configurable.
 10.  Weak-secret guard: if SECRET_KEY is shorter than 32 chars in production,
      startup is aborted with a clear error message.
"""

import os
import secrets
import warnings
from datetime import timedelta

# ── Environment detection ──────────────────────────────────────────────────────

# FIX 8: single canonical production flag reused everywhere below
IS_PRODUCTION = (
    os.environ.get("RAILWAY_ENVIRONMENT") == "production"
    or os.environ.get("FLASK_ENV") == "production"
    or os.environ.get("ENV") == "production"
)

# ── Flask ──────────────────────────────────────────────────────────────────────

_secret_env = os.environ.get("SECRET_KEY", "")

if _secret_env:
    SECRET_KEY = _secret_env
    # FIX 10: abort in production if the key is too short
    if IS_PRODUCTION and len(SECRET_KEY) < 32:
        raise RuntimeError(
            "SECRET_KEY is set but is shorter than 32 characters. "
            "Generate a strong key with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
else:
    if IS_PRODUCTION:
        # FIX 10: hard fail — never silently use a weak key in production
        raise RuntimeError(
            "SECRET_KEY environment variable is not set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    # FIX 1: dev/test gets a fresh random key per process — it is never a known
    # fixed string, so it cannot accidentally leak into production.
    SECRET_KEY = secrets.token_hex(32)
    warnings.warn(
        "SECRET_KEY not set — using a random ephemeral key. "
        "Sessions will not survive restarts. Set SECRET_KEY for persistent dev sessions.",
        stacklevel=2,
    )

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# FIX 3: also enable Secure flag when running behind an HTTPS proxy
SESSION_COOKIE_SECURE = IS_PRODUCTION or (
    os.environ.get("FORWARDED_PROTO", "").lower() == "https"
)

# FIX 4: reduced from 8 h → 2 h. The app-level idle timeout (4 h) acts as an
# inner guard; this cookie lifetime is the outer hard cap.
PERMANENT_SESSION_LIFETIME = timedelta(
    seconds=int(os.environ.get("SESSION_LIFETIME_SECONDS", str(2 * 3600)))
)

# FIX 9: configurable via env var, documented, default 10 MB
MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

# ── Database ───────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    # SQLAlchemy dropped the legacy postgres:// scheme
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DATA_FILE = os.environ.get("DATA_FILE", "documents.json")  # JSON fallback

# ── Admin credentials ──────────────────────────────────────────────────────────

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")

_admin_pw_env = os.environ.get("ADMIN_PASSWORD", "")

# FIX 2: no default password shipped in code at all.
if not _admin_pw_env:
    if IS_PRODUCTION:
        raise RuntimeError(
            "ADMIN_PASSWORD environment variable is not set. "
            "Set a strong password in your Railway Variables before deploying."
        )
    # In dev, generate a one-time password and print it clearly once
    _admin_pw_env = secrets.token_urlsafe(16)
    warnings.warn(
        f"ADMIN_PASSWORD not set — generated ephemeral dev password: {_admin_pw_env}\n"
        "Set ADMIN_PASSWORD in your environment for a stable dev password.",
        stacklevel=2,
    )

ADMIN_PASSWORD = _admin_pw_env

# ── Email (Brevo) ──────────────────────────────────────────────────────────────

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
MAIL_SENDER   = os.environ.get("MAIL_SENDER", "")
MAIL_ENABLED  = bool(BREVO_API_KEY and MAIL_SENDER)

# ── App URL (for QR codes) ─────────────────────────────────────────────────────

APP_URL = os.environ.get("APP_URL", "").rstrip("/")

# ── QR Code signing ────────────────────────────────────────────────────────────

_qr_secret_env = os.environ.get("QR_SIGN_SECRET", "")

if _qr_secret_env:
    QR_SIGN_SECRET = _qr_secret_env
else:
    # FIX 5: fall back to SECRET_KEY but warn — a dedicated secret means
    # rotating SESSION keys doesn't silently invalidate all QR codes.
    QR_SIGN_SECRET = SECRET_KEY
    warnings.warn(
        "QR_SIGN_SECRET not set — falling back to SECRET_KEY. "
        "Set a dedicated QR_SIGN_SECRET so QR codes survive session key rotations.",
        stacklevel=2,
    )

QR_SIGN_VALIDITY_DAYS = int(os.environ.get("QR_SIGN_DAYS", "365"))

# ── Client registration ────────────────────────────────────────────────────────

_reg_code_env = os.environ.get("CLIENT_REG_CODE", "")

if _reg_code_env:
    CLIENT_REG_CODE = _reg_code_env
else:
    # FIX 6: "client-reg" is trivially guessable; generate a random token if
    # the operator hasn't set one, and tell them what it is so they can share it.
    CLIENT_REG_CODE = secrets.token_urlsafe(16)
    warnings.warn(
        f"CLIENT_REG_CODE not set — generated ephemeral code: {CLIENT_REG_CODE}\n"
        "Set CLIENT_REG_CODE in your environment to make this stable.",
        stacklevel=2,
    )

# ── Rate limits ────────────────────────────────────────────────────────────────

RATE_LIMITS = {
    "login":         {"max": 5,   "window": 300,  "lockout": 900},   # 5 tries / 5 min → 15 min lockout
    "register":      {"max": 3,   "window": 3600, "lockout": 7200},  # 3 / hr → 2 hr lockout
    "status_update": {"max": 100, "window": 60,   "lockout": 60},    # prevent status floods
    "doc_create":    {"max": 50,  "window": 60,   "lockout": 60},    # prevent doc spam
    "api":           {"max": 60,  "window": 60,   "lockout": 120},   # API protection
}

# ── Document statuses ──────────────────────────────────────────────────────────

STATUS_OPTIONS = [
    "Logged", "Pending", "Received", "In Review",
    "Routed", "Released", "On Hold", "Archived",
]