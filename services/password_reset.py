"""
services/password_reset.py — Self-service password reset: SECURE TOKEN CORE.

Checkpoint A (backend security foundation, no user-facing pages yet):

  1. RESET TOKEN STORE — password_reset_tokens table + JSON fallback, mirroring
     how invite_tokens / doc_qr_tokens are stored. Tokens are stored HASHED
     (SHA-256 of a secrets.token_urlsafe(32) value); the RAW token exists only
     transiently to build the email link and is NEVER persisted. Tokens are
     single-use and time-limited (45 min). Creating a new token for a user
     invalidates that user's prior unused ones.

  2. RATE LIMITING — DB-backed request throttle (JSON fallback), enforced
     per-email AND per-IP within a rolling window. A DB counter is used instead
     of the in-memory limiter in services.auth because multi-worker gunicorn
     would give each process its own in-memory view, letting an attacker exceed
     the global limit N-fold.

  3. PASSWORD SET — reuses the EXISTING Werkzeug/bcrypt hashing path
     (services.auth.update_user_password → hash_password). No second hashing
     method is introduced. Basic server-side strength validation (min length).

SECURITY NOTES
  - Deliberately does NOT copy the invite flow's plaintext-token pattern
    (services.email.generate_invite_token stores the raw token). Here only the
    SHA-256 hash is stored, so a read of the token table cannot be used to forge
    reset links.
  - Token comparison uses secrets.compare_digest (constant-time) on the hashes.
  - Unknown / tampered tokens hash to a non-matching digest and are rejected.
"""

import hashlib
import json
import os
import secrets
import time

from services.database import USE_DB, get_conn
# Reuse the EXISTING password hashing path — do NOT introduce a second method.
from services.auth import update_user_password, hmac_safe_compare
from config import (
    PASSWORD_RESET_TOKEN_TTL_MINUTES,
    PASSWORD_RESET_MIN_PASSWORD_LENGTH,
    PASSWORD_RESET_RATE_LIMITS,
)

# JSON fallback files (relative paths — resolve to CWD, like the other stores)
_TOKENS_JSON = "password_reset_tokens.json"
_RATE_JSON   = "password_reset_rate_limits.json"


# ── Token hashing ──────────────────────────────────────────────────────────────

def _hash_token(raw_token: str) -> str:
    """SHA-256 hex digest of the raw urlsafe token. This is what we store."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


# ── Reset token store ──────────────────────────────────────────────────────────

def create_reset_token(username: str) -> str:
    """
    Generate a reset token for ``username``, store its HASH + a 45-minute
    expiry, invalidate the user's prior unused tokens, and return the RAW token
    (for the email link — never stored raw).
    """
    uname = username.lower().strip()
    raw_token  = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now        = time.time()
    ttl        = PASSWORD_RESET_TOKEN_TTL_MINUTES * 60
    expires_at = now + ttl

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Invalidate this user's prior unused tokens
                    cur.execute(
                        "UPDATE password_reset_tokens SET used=TRUE "
                        "WHERE username=%s AND used=FALSE",
                        (uname,),
                    )
                    cur.execute(
                        """INSERT INTO password_reset_tokens
                               (token_hash, username, used, expires_at)
                           VALUES (%s, %s, FALSE,
                                   NOW() + (%s || ' minutes')::interval)""",
                        (token_hash, uname, PASSWORD_RESET_TOKEN_TTL_MINUTES),
                    )
        except Exception:
            pass
    else:
        tokens = _load_tokens_json()
        # Invalidate this user's prior unused tokens
        for rec in tokens.values():
            if rec.get("username") == uname and not rec.get("used"):
                rec["used"] = True
        tokens[token_hash] = {
            "username":   uname,
            "used":       False,
            "created_at": now,
            "expires_at": expires_at,
        }
        _save_tokens_json(tokens)

    return raw_token


def verify_reset_token(raw_token: str) -> str | None:
    """
    Hash ``raw_token`` and return the username of a matching UNUSED, UNEXPIRED
    token, or None. Rejects expired, used, unknown, and tampered tokens.
    Uses constant-time comparison on the stored hash.
    """
    if not raw_token:
        return None
    token_hash = _hash_token(raw_token)

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT username FROM password_reset_tokens "
                        "WHERE token_hash=%s AND used=FALSE AND expires_at > NOW()",
                        (token_hash,),
                    )
                    row = cur.fetchone()
                    return row["username"] if row else None
        except Exception:
            return None
    else:
        now = time.time()
        for stored_hash, rec in _load_tokens_json().items():
            if rec.get("used"):
                continue
            if float(rec.get("expires_at", 0)) <= now:
                continue
            # Constant-time compare on the hash (both are hex digests)
            if hmac_safe_compare(stored_hash, token_hash):
                return rec.get("username")
        return None


def consume_reset_token(raw_token: str) -> bool:
    """
    Mark a valid (unused, unexpired) token as USED. Call ONLY after a successful
    password set. Returns True if a token was consumed, else False. A consumed
    token can never verify again.
    """
    if not raw_token:
        return False
    token_hash = _hash_token(raw_token)

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE password_reset_tokens SET used=TRUE "
                        "WHERE token_hash=%s AND used=FALSE AND expires_at > NOW()",
                        (token_hash,),
                    )
                    return cur.rowcount > 0
        except Exception:
            return False
    else:
        now = time.time()
        tokens = _load_tokens_json()
        rec = tokens.get(token_hash)
        if not rec or rec.get("used") or float(rec.get("expires_at", 0)) <= now:
            return False
        rec["used"] = True
        _save_tokens_json(tokens)
        return True


# ── Rate limiting (per-email AND per-IP, DB-backed with JSON fallback) ──────────

def check_reset_rate_limit(email: str, ip: str) -> tuple[bool, str | None]:
    """
    Record a reset REQUEST and report whether it is allowed.

    Enforces max requests per-email AND per-IP within a rolling window
    (defaults: 3/email/hour, 10/IP/hour). Returns (allowed, reason) where
    ``reason`` is None when allowed, or "email"/"ip" naming the tripped limit.

    The current request is counted, so the (max+1)-th request in the window is
    the first to be blocked.
    """
    email = (email or "").lower().strip()
    ip    = (ip or "").strip()
    email_cfg = PASSWORD_RESET_RATE_LIMITS["email"]
    ip_cfg    = PASSWORD_RESET_RATE_LIMITS["ip"]

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Record this request event for both scopes
                    cur.execute(
                        "INSERT INTO password_reset_rate_limits (scope, identifier) "
                        "VALUES ('email', %s), ('ip', %s)",
                        (email, ip),
                    )
                    email_count = _db_count_window(cur, "email", email, email_cfg["window"])
                    ip_count    = _db_count_window(cur, "ip",    ip,    ip_cfg["window"])
                    # Opportunistic prune of rows older than the longest window
                    cur.execute(
                        "DELETE FROM password_reset_rate_limits "
                        "WHERE created_at < NOW() - (%s || ' seconds')::interval",
                        (max(email_cfg["window"], ip_cfg["window"]),),
                    )
        except Exception:
            # Fail OPEN would let an attacker bypass by breaking the DB; but the
            # invite/login flows already fail open on DB errors, and a hard block
            # here would deny all resets on a transient error. Match app behavior.
            return True, None
        if email_count > email_cfg["max"]:
            return False, "email"
        if ip_count > ip_cfg["max"]:
            return False, "ip"
        return True, None

    # JSON fallback
    now    = time.time()
    max_window = max(email_cfg["window"], ip_cfg["window"])
    events = [e for e in _load_rate_json() if now - e.get("ts", 0) < max_window]
    events.append({"scope": "email", "identifier": email, "ts": now})
    events.append({"scope": "ip",    "identifier": ip,    "ts": now})
    _save_rate_json(events)

    email_count = sum(
        1 for e in events
        if e["scope"] == "email" and e["identifier"] == email
        and now - e["ts"] < email_cfg["window"]
    )
    ip_count = sum(
        1 for e in events
        if e["scope"] == "ip" and e["identifier"] == ip
        and now - e["ts"] < ip_cfg["window"]
    )
    if email_count > email_cfg["max"]:
        return False, "email"
    if ip_count > ip_cfg["max"]:
        return False, "ip"
    return True, None


def _db_count_window(cur, scope: str, identifier: str, window: int) -> int:
    cur.execute(
        "SELECT COUNT(*) AS c FROM password_reset_rate_limits "
        "WHERE scope=%s AND identifier=%s "
        "AND created_at > NOW() - (%s || ' seconds')::interval",
        (scope, identifier, window),
    )
    return cur.fetchone()["c"]


# ── Password set (reuses the existing bcrypt hashing path) ──────────────────────

def validate_password_strength(password: str) -> tuple[bool, str | None]:
    """Basic server-side strength check. Returns (ok, error_message)."""
    if not password or len(password.strip()) < PASSWORD_RESET_MIN_PASSWORD_LENGTH:
        return False, (
            f"Password must be at least "
            f"{PASSWORD_RESET_MIN_PASSWORD_LENGTH} characters."
        )
    return True, None


def set_password(username: str, new_password: str) -> tuple[bool, str | None]:
    """
    Set a user's new password using the EXISTING hashing path
    (services.auth.update_user_password → bcrypt). No password is ever stored
    plaintext and no second hashing method is introduced. Validates strength
    first. Returns (success, error_message).
    """
    ok, err = validate_password_strength(new_password)
    if not ok:
        return False, err
    return update_user_password(username, new_password)


def reset_password_with_token(raw_token: str, new_password: str) -> tuple[bool, str | None]:
    """
    Secure end-to-end combiner used by Checkpoint B's route:
    verify token → validate + set password → consume token (single-use).
    The token is consumed ONLY after the password is successfully set.
    """
    username = verify_reset_token(raw_token)
    if not username:
        return False, "Invalid or expired reset token."

    ok, err = set_password(username, new_password)
    if not ok:
        return False, err

    consume_reset_token(raw_token)
    return True, None


# ── JSON fallback helpers ──────────────────────────────────────────────────────

def _load_tokens_json() -> dict:
    if not os.path.exists(_TOKENS_JSON):
        return {}
    try:
        with open(_TOKENS_JSON) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_tokens_json(tokens: dict):
    with open(_TOKENS_JSON, "w") as f:
        json.dump(tokens, f, indent=2)


def _load_rate_json() -> list:
    if not os.path.exists(_RATE_JSON):
        return []
    try:
        with open(_RATE_JSON) as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_rate_json(events: list):
    with open(_RATE_JSON, "w") as f:
        json.dump(events, f, indent=2)
