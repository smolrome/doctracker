"""
config.py — All configuration in one place.
Set these as Railway environment variables in production.
"""
import os
from datetime import timedelta

# ── Flask ──────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "doctracker-dev-CHANGE-ME-in-production")
if SECRET_KEY == "doctracker-dev-CHANGE-ME-in-production":
    print("WARNING: SECRET_KEY not set — using insecure default. Set it in Railway Variables!")

SESSION_COOKIE_HTTPONLY   = True
SESSION_COOKIE_SAMESITE   = "Lax"
SESSION_COOKIE_SECURE     = os.environ.get("RAILWAY_ENVIRONMENT") == "production"
PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
MAX_CONTENT_LENGTH        = 10 * 1024 * 1024  # 10 MB

# ── Database ───────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DATA_FILE = os.environ.get("DATA_FILE", "documents.json")  # JSON fallback

# ── Admin credentials ──────────────────────────────────────────────────────────
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "deped2025")
if ADMIN_PASSWORD == "deped2025":
    print("WARNING: ADMIN_PASSWORD is using the default. Set ADMIN_PASSWORD in Railway Variables immediately!")

# ── Email (Brevo) ──────────────────────────────────────────────────────────────
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
MAIL_SENDER   = os.environ.get("MAIL_SENDER", "")
MAIL_ENABLED  = bool(BREVO_API_KEY and MAIL_SENDER)

# ── App URL (for QR codes) ─────────────────────────────────────────────────────
APP_URL = os.environ.get("APP_URL", "").rstrip("/")

# ── QR Code signing ───────────────────────────────────────────────────────────
QR_SIGN_SECRET       = os.environ.get("QR_SIGN_SECRET", SECRET_KEY)
QR_SIGN_VALIDITY_DAYS = int(os.environ.get("QR_SIGN_DAYS", "365"))

# ── Client registration ────────────────────────────────────────────────────────
CLIENT_REG_CODE = os.environ.get("CLIENT_REG_CODE", "client-reg")

# ── Rate limits ────────────────────────────────────────────────────────────────
RATE_LIMITS = {
    "login":         {"max": 5,   "window": 300,  "lockout": 900},   # 5 tries/5 min → 15 min lockout
    "register":      {"max": 3,   "window": 3600, "lockout": 7200},  # 3/hr → 2 hr lockout
    "status_update": {"max": 100, "window": 60,   "lockout": 60},    # prevent status floods
    "doc_create":    {"max": 50,  "window": 60,   "lockout": 60},    # prevent doc spam
    "api":           {"max": 60,  "window": 60,   "lockout": 120},   # API protection
}

# ── Document statuses ──────────────────────────────────────────────────────────
STATUS_OPTIONS = ["Logged", "Pending", "Received", "In Review", "In Transit", "Released", "On Hold", "Archived"]
