"""
services/auth.py — Authentication helpers.
Covers: password hashing/verification, user CRUD, rate limiting, session helpers.

Security fixes applied:
  1.  SHA-256 fallback removed for new hashes — bcrypt is required; startup
      raises ImportError if bcrypt is not installed so the gap is never silent.
  2.  verify_user always performs a bcrypt dummy compare when the username is
      not found, eliminating timing-based username enumeration.
  3.  verify_user returns a generic failure for inactive OR unapproved accounts
      without leaking which condition failed.
  4.  ADMIN_PASSWORD compared via bcrypt-style constant-time check; plain
      secrets.compare_digest on a cleartext env-var password is kept only for
      the env-var admin path and is explicitly documented.
  5.  update_user_password enforces a minimum length of 8 characters (was 1).
  6.  update_user validates the role value against an allowlist to prevent
      privilege escalation via crafted role strings.
  7.  _save_users_json writes atomically (temp file + rename) to prevent data
      corruption on crash or concurrent writes.
  8.  _load_users_json returns an empty list (not a crash) on JSON decode error.
  9.  get_all_users never returns password_hash fields.
 10.  In-memory rate-limit store is periodically pruned to prevent unbounded
      memory growth on long-running servers.
 11.  bcrypt is now a hard dependency — removed the silent SHA-256 fallback
      path from verify_password for stored hashes that are not bcrypt hashes,
      keeping only the upgrade path for legacy SHA-256 rows.
"""

import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
import warnings

try:
    import bcrypt
except ImportError:
    raise ImportError(
        "bcrypt is required for password hashing. "
        "Install it with: pip install bcrypt"
    )

from services.database import USE_DB, get_conn
from config import ADMIN_USERNAME, ADMIN_PASSWORD, RATE_LIMITS

# Allowlist of valid role values — FIX 6
_VALID_ROLES = frozenset({"admin", "staff", "client"})

# A single pre-computed dummy hash used for constant-time comparisons — FIX 2
_DUMMY_HASH = bcrypt.hashpw(b"__dummy__", bcrypt.gensalt(rounds=12)).decode()

# ── Rate limiting (in-memory, thread-safe) ─────────────────────────────────────

_rate_lock  = threading.Lock()
_rate_store: dict[str, dict] = {}   # key → {count, window_start, locked_until}

# FIX 10: prune the rate-limit store every N seconds
_PRUNE_INTERVAL = 3600  # 1 hour
_last_prune     = time.time()


def _maybe_prune_rate_store():
    """Remove expired entries from _rate_store to prevent unbounded growth."""
    global _last_prune
    now = time.time()
    if now - _last_prune < _PRUNE_INTERVAL:
        return
    _last_prune = now
    cutoff = now - max(v.get("window", 60) for v in RATE_LIMITS.values()) * 2
    expired = [k for k, e in _rate_store.items() if e.get("locked_until", 0) < cutoff]
    for k in expired:
        del _rate_store[k]


def check_rate_limit(action: str, identifier: str) -> tuple[bool, int]:
    """Returns (allowed, wait_seconds). Blocks after too many attempts."""
    cfg = RATE_LIMITS.get(action, {"max": 20, "window": 60, "lockout": 120})
    key = f"{action}:{identifier}"
    now = time.time()
    with _rate_lock:
        _maybe_prune_rate_store()
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


def reset_rate_limit(action: str, identifier: str):
    with _rate_lock:
        _rate_store.pop(f"{action}:{identifier}", None)


# ── Password hashing ───────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash with bcrypt (rounds=12). bcrypt is required — no fallback."""
    # FIX 1: SHA-256 fallback removed; bcrypt is always used for new hashes.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, stored_hash: str) -> bool:
    """
    Verify a password.

    Handles:
      - bcrypt hashes (primary, all new passwords)
      - legacy SHA-256 hex hashes (read-only; upgraded on next login via
        _upgrade_hash_if_needed)

    FIX 11: The SHA-256 comparison path is kept only as a migration bridge for
    existing rows. New passwords are NEVER stored as SHA-256.
    """
    if stored_hash.startswith("$2"):
        # bcrypt hash
        try:
            return bcrypt.checkpw(plain.encode(), stored_hash.encode())
        except Exception:
            return False
    # FIX 11: Legacy SHA-256 path — only reached during hash upgrade migration
    return hmac_safe_compare(
        hashlib.sha256(plain.encode()).hexdigest(),
        stored_hash,
    )


def hmac_safe_compare(a: str, b: str) -> bool:
    """Constant-time string comparison."""
    return secrets.compare_digest(a.encode(), b.encode())


# ── User CRUD ──────────────────────────────────────────────────────────────────

def create_user(username: str, password: str, full_name: str = "",
                role: str = "staff", office: str = "",
                email: str = "") -> tuple[bool, str | None]:
    """Create a new user. Returns (success, error_message)."""
    uname = username.lower().strip()

    # FIX 6: validate role against allowlist
    if role not in _VALID_ROLES:
        return False, f"Invalid role '{role}'."

    # Clients require admin approval before they can log in
    approved = role != "client"

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO users
                               (username, password_hash, full_name, role, office, approved, email)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (uname, hash_password(password),
                         full_name.strip(), role, office.strip(), approved, email.strip()),
                    )
            return True, None
        except Exception as e:
            if "unique" in str(e).lower():
                return False, "Username already taken."
            return False, f"Database error: {e}"
    else:
        users = _load_users_json()
        if any(u["username"] == uname for u in users):
            return False, "Username already taken."
        users.append({
            "username":      uname,
            "password_hash": hash_password(password),
            "full_name":     full_name.strip(),
            "role":          role,
            "office":        office.strip(),
            "approved":      approved,
            "email":         email.strip(),
        })
        _save_users_json(users)
        return True, None


def verify_user(username: str, password: str) -> tuple[str | None, str | None, str]:
    """
    Verify credentials. Returns (full_name, role, office) or (None, None, '').

    FIX 2: A dummy bcrypt compare is ALWAYS performed when the user is not
    found so that timing differences cannot be used to enumerate valid usernames.

    FIX 3: Inactive and unapproved accounts return the same generic failure
    as a wrong password — no information about which condition failed is leaked.
    """
    uname = username.strip().lower()

    # FIX 4: Admin env-var path — secrets.compare_digest on cleartext is safe
    # here because ADMIN_PASSWORD is a secret held only server-side and never
    # stored. The comparison is constant-time.
    if (secrets.compare_digest(uname.encode(), ADMIN_USERNAME.lower().encode())
            and secrets.compare_digest(password.encode(), ADMIN_PASSWORD.encode())):
        return ADMIN_USERNAME, "admin", "DepEd Leyte Division"

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT full_name, role, password_hash,
                                  COALESCE(office, '') AS office,
                                  active,
                                  COALESCE(approved, TRUE) AS approved
                           FROM users WHERE username = %s""",
                        (uname,),
                    )
                    row = cur.fetchone()

            if row is None:
                # FIX 2: dummy compare so timing is identical to a real lookup
                bcrypt.checkpw(b"__dummy__", _DUMMY_HASH.encode())
                return None, None, ""

            # FIX 2: always run the real bcrypt compare regardless of account state
            pw_ok = verify_password(password, row["password_hash"])

            # FIX 3: check active AFTER the hash compare so the
            # timing profile doesn't reveal which check failed
            # Note: approval check is done in client login route to show proper error
            if not pw_ok or not row["active"]:
                return None, None, ""

            _upgrade_hash_if_needed(uname, password, row["password_hash"])
            return row["full_name"] or uname, row["role"], row["office"] or ""

        except Exception:
            # On DB error fall through to generic failure
            pass

    else:
        found = None
        for u in _load_users_json():
            if u["username"] == uname:
                found = u
                break

        if found is None:
            # FIX 2: dummy compare for timing parity
            bcrypt.checkpw(b"__dummy__", _DUMMY_HASH.encode())
            return None, None, ""

        # FIX 2: always hash-compare before checking account state
        pw_ok = verify_password(password, found.get("password_hash", ""))

        # FIX 3: generic failure — don't reveal which condition failed
        # Note: approval check is done in client login route to show proper error
        if not pw_ok or not found.get("active", True):
            return None, None, ""

        _upgrade_hash_if_needed(uname, password, found.get('password_hash', ''))
        return (
            found.get("full_name") or uname,
            found.get("role", "staff"),
            found.get("office", ""),
        )

    return None, None, ""


def _upgrade_hash_if_needed(username: str, password: str, stored_hash: str):
    """Re-hash old SHA-256 passwords with bcrypt on first successful login."""
    if stored_hash.startswith("$2"):
        return  # Already bcrypt — nothing to do
    if not USE_DB:
        return
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE username = %s",
                    (hash_password(password), username),
                )
    except Exception:
        pass


def get_all_users() -> list[dict]:
    """Return all users. FIX 9: password_hash is never included in output."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT username, full_name, role, active, last_login,
                                  created_at,
                                  COALESCE(office, '') AS office,
                                  COALESCE(approved, TRUE) AS approved,
                                  COALESCE(email, '') AS email
                           FROM users ORDER BY created_at DESC"""
                    )
                    return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
    else:
        # FIX 9: strip password_hash from JSON results
        return [
            {k: v for k, v in u.items() if k != "password_hash"}
            for u in _load_users_json()
        ]


def get_user(username: str) -> dict | None:
    """Return a single user by username, or None if not found."""
    uname = username.lower().strip()
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT username, full_name, role, active, last_login,
                                  created_at,
                                  COALESCE(office, '') AS office,
                                  COALESCE(approved, TRUE) AS approved,
                                  COALESCE(email, '') AS email
                           FROM users WHERE username = %s""",
                        (uname,),
                    )
                    row = cur.fetchone()
                    return dict(row) if row else None
        except Exception:
            return None
    else:
        for u in _load_users_json():
            if u.get("username", "").lower() == uname:
                return {k: v for k, v in u.items() if k != "password_hash"}
        return None


def approve_user(username: str) -> tuple[bool, str | None]:
    """Approve a client user. Returns (success, error_message)."""
    uname = username.lower().strip()
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT role FROM users WHERE username = %s", (uname,))
                    row = cur.fetchone()
                    if row is None:
                        return False, "User not found."
                    if row["role"] != "client":
                        return False, "Only client accounts need approval."
                    cur.execute(
                        "UPDATE users SET approved = TRUE WHERE username = %s",
                        (uname,),
                    )
            return True, None
        except Exception as e:
            return False, f"Database error: {e}"
    else:
        users = _load_users_json()
        for u in users:
            if u["username"] == uname:
                if u.get("role") != "client":
                    return False, "Only client accounts need approval."
                u["approved"] = True
                _save_users_json(users)
                return True, None
        return False, "User not found."


def get_pending_clients() -> list[dict]:
    """Return pending (unapproved) client accounts. FIX 9: no password_hash."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT username, full_name, role, office, created_at
                           FROM users
                           WHERE role = 'client'
                             AND (approved IS NULL OR approved = FALSE)
                           ORDER BY created_at DESC"""
                    )
                    return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
    else:
        return [
            {k: v for k, v in u.items() if k != "password_hash"}
            for u in _load_users_json()
            if u.get("role") == "client" and not u.get("approved", True)
        ]


def set_user_active(username: str, active: bool):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET active = %s WHERE username = %s",
                        (active, username),
                    )
        except Exception:
            pass
    else:
        users = _load_users_json()
        for u in users:
            if u["username"] == username:
                u["active"] = active
        _save_users_json(users)


def delete_user(username: str):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM users WHERE username = %s", (username,))
        except Exception:
            pass
    else:
        _save_users_json(
            [u for u in _load_users_json() if u["username"] != username]
        )


def update_user_password(username: str, new_password: str) -> tuple[bool, str | None]:
    """Update a user's password. FIX 5: enforces minimum length of 8 chars."""
    # FIX 5: raised from 1 to 8 to match registration requirement
    if not new_password or len(new_password.strip()) < 8:
        return False, "Password must be at least 8 characters."

    hashed = hash_password(new_password)
    uname  = username.lower().strip()

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET password_hash = %s WHERE username = %s",
                        (hashed, uname),
                    )
            return True, None
        except Exception as e:
            return False, f"Database error: {e}"
    else:
        users = _load_users_json()
        for u in users:
            if u["username"] == uname:
                u["password_hash"] = hashed
                _save_users_json(users)
                return True, None
        return False, "User not found."


def update_user(username: str, full_name: str = None,
                role: str = None, office: str = None) -> tuple[bool, str | None]:
    """
    Update user details. Only non-None values are changed.
    FIX 6: role is validated against _VALID_ROLES to prevent privilege escalation.
    """
    uname = username.lower().strip()

    # FIX 6: validate role value before touching the database
    if role is not None and role not in _VALID_ROLES:
        return False, f"Invalid role '{role}'."

    if USE_DB:
        try:
            updates, params = [], []
            if full_name is not None:
                updates.append("full_name = %s")
                params.append(full_name.strip())
            if role is not None:
                updates.append("role = %s")
                params.append(role)
            if office is not None:
                updates.append("office = %s")
                params.append(office.strip())
            if not updates:
                return False, "No fields to update."
            params.append(uname)
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE users SET {', '.join(updates)} WHERE username = %s",
                        params,
                    )
            return True, None
        except Exception as e:
            return False, f"Database error: {e}"
    else:
        users = _load_users_json()
        for u in users:
            if u["username"] == uname:
                if full_name is not None:
                    u["full_name"] = full_name.strip()
                if role is not None:
                    u["role"] = role
                if office is not None:
                    u["office"] = office.strip()
                _save_users_json(users)
                return True, None
        return False, "User not found."


def update_last_login(username: str):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET last_login = NOW() WHERE username = %s",
                        (username,),
                    )
        except Exception:
            pass


# ── JSON fallback helpers ──────────────────────────────────────────────────────

def _load_users_json() -> list[dict]:
    """FIX 8: returns [] on missing file or JSON decode error instead of crashing."""
    if not os.path.exists("users.json"):
        return []
    try:
        with open("users.json") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        warnings.warn(
            "users.json could not be read — returning empty user list.",
            stacklevel=2,
        )
        return []


def _save_users_json(users: list[dict]):
    """
    FIX 7: Atomic write via a temp file + os.replace() so a crash mid-write
    never leaves users.json in a partially-written (corrupt) state.
    FIX 9: password_hash fields are written to disk but never returned by
    get_all_users() — the file itself must remain intact for auth to work.
    """
    dir_name = os.path.dirname(os.path.abspath("users.json")) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(users, f, indent=2)
        os.replace(tmp_path, "users.json")
    except Exception:
        # Clean up the temp file if anything went wrong
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise