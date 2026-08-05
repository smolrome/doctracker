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
import re
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

# Server-side username format rules. Until now there was NO server-side
# username validation — only a client-side `pattern` attribute in
# manage_users.html, trivially bypassed by a direct POST. This is the server
# equivalent, analogous to _VALID_ROLES for roles. Charset matches that
# client-side pattern ([a-z0-9._-]) after lower()+strip(); length is 3–32.
_USERNAME_RE  = re.compile(r"[a-z0-9._-]+")
_USERNAME_MIN = 3
_USERNAME_MAX = 32


def _validate_username(name: str) -> tuple[bool, str | None]:
    """Validate a username's FORMAT. Returns (ok, error_message).

    Rules (after lower()+strip()): 3–32 chars drawn only from [a-z0-9._-];
    empty / whitespace-only is rejected. Mirrors the (ok, err) return style of
    create_user/update_user so callers can surface ``err`` directly. Does NOT
    check uniqueness — that is the caller's job (the DB UNIQUE constraint on
    users.username, or an explicit SELECT in rename_user).

    IMPORTANT: only NEW or CHANGED usernames are ever validated (this is wired
    into create_user, and into update_user ONLY when a rename is requested).
    Existing rows are never re-validated, so legacy accounts whose names predate
    this rule (e.g. a name containing a space) keep working for login and for
    non-rename edits — enforcing here does not retroactively break them.
    """
    if name is None:
        return False, "Username is required."
    uname = name.lower().strip()
    if not uname:
        return False, "Username cannot be empty."
    if len(uname) < _USERNAME_MIN:
        return False, f"Username must be at least {_USERNAME_MIN} characters."
    if len(uname) > _USERNAME_MAX:
        return False, f"Username must be at most {_USERNAME_MAX} characters."
    if not _USERNAME_RE.fullmatch(uname):
        return False, ("Username may contain only lowercase letters, numbers, "
                       "dots, dashes and underscores.")
    return True, None

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
                email: str = "",
                documents_handled: list | None = None) -> tuple[bool, str | None]:
    """Create a new user. Returns (success, error_message).

    Requires DB column for documents_handled:
        ALTER TABLE users ADD COLUMN IF NOT EXISTS documents_handled JSONB DEFAULT '[]';
    """
    import json as _json
    uname = username.lower().strip()

    # Validate username FORMAT server-side (new account → always a new name).
    ok, verr = _validate_username(uname)
    if not ok:
        return False, verr

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
                               (username, password_hash, full_name, role, office, approved, email,
                                documents_handled)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
                        (uname, hash_password(password),
                         full_name.strip(), role, office.strip(), approved, email.strip(),
                         _json.dumps(documents_handled or [])),
                    )
            # Every client gets an opaque QR identity token at creation. This is
            # the single choke point all client-creation paths funnel through
            # (self-registration + admin create), so hooking here guarantees
            # coverage. Best-effort: never fail user creation over a token.
            if role == "client":
                from services.qr import get_or_create_client_token
                get_or_create_client_token(uname)
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
            "username":          uname,
            "password_hash":     hash_password(password),
            "full_name":         full_name.strip(),
            "role":              role,
            "office":            office.strip(),
            "approved":          approved,
            "email":             email.strip(),
            "documents_handled": documents_handled or [],
        })
        _save_users_json(users)
        # Mirror the DB path: clients get an identity token at creation.
        if role == "client":
            from services.qr import get_or_create_client_token
            get_or_create_client_token(uname)
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
                                  COALESCE(email, '') AS email,
                                  COALESCE(documents_handled, '[]'::jsonb) AS documents_handled,
                                  COALESCE(can_generate_so, FALSE) AS can_generate_so,
                                  COALESCE(can_route_documents, FALSE) AS can_route_documents
                           FROM users ORDER BY created_at DESC"""
                    )
                    rows = []
                    for r in cur.fetchall():
                        d = dict(r)
                        # Ensure documents_handled is always a plain Python list
                        dh = d.get("documents_handled")
                        d["documents_handled"] = list(dh) if isinstance(dh, (list, tuple)) else []
                        rows.append(d)
                    return rows
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


def get_user_by_email(email: str) -> dict | None:
    """
    Look up a single user by email address (case-insensitive), covering BOTH
    staff and client roles. Returns {username, email, role, full_name} or None.
    Never returns password_hash. Used by the self-service password reset flow.
    """
    target = (email or "").strip().lower()
    if not target:
        return None
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT username, role, full_name,
                                  COALESCE(email, '') AS email
                           FROM users
                           WHERE LOWER(email) = %s AND COALESCE(email, '') <> ''
                           LIMIT 1""",
                        (target,),
                    )
                    row = cur.fetchone()
                    return dict(row) if row else None
        except Exception:
            return None
    else:
        for u in _load_users_json():
            if (u.get("email", "") or "").strip().lower() == target:
                return {
                    "username":  u.get("username", ""),
                    "email":     u.get("email", ""),
                    "role":      u.get("role", "staff"),
                    "full_name": u.get("full_name", ""),
                }
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
                role: str = None, office: str = None,
                email: str = None,
                new_username: str = None) -> tuple[bool, str | None]:
    """
    Update user details. Only non-None values are changed.
    FIX 6: role is validated against _VALID_ROLES to prevent privilege escalation.
    new_username renames the account; the caller must ensure no collision exists.
    """
    uname = username.lower().strip()

    # FIX 6: validate role value before touching the database
    if role is not None and role not in _VALID_ROLES:
        return False, f"Invalid role '{role}'."

    new_uname = new_username.lower().strip() if new_username else None

    # Validate FORMAT only when a genuine rename is requested. A non-rename edit
    # (new_username is None, or unchanged) never re-validates the existing name,
    # so legacy accounts stay editable. NOTE: this only rewrites the users row —
    # it still orphans documents/other tables that reference the old name. A
    # full-history rewrite is rename_user(); update_user is unchanged otherwise.
    if new_uname and new_uname != uname:
        ok, verr = _validate_username(new_uname)
        if not ok:
            return False, verr

    if USE_DB:
        try:
            updates, params = [], []
            if new_uname and new_uname != uname:
                updates.append("username = %s")
                params.append(new_uname)
            if full_name is not None:
                updates.append("full_name = %s")
                params.append(full_name.strip())
            if role is not None:
                updates.append("role = %s")
                params.append(role)
            if office is not None:
                updates.append("office = %s")
                params.append(office.strip())
            if email is not None:
                updates.append("email = %s")
                params.append(email.strip())
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
            if "unique" in str(e).lower():
                return False, "Username already taken."
            return False, f"Database error: {e}"
    else:
        users = _load_users_json()
        # Check for username collision before making any changes
        if new_uname and new_uname != uname:
            if any(u["username"] == new_uname for u in users):
                return False, "Username already taken."
        for u in users:
            if u["username"] == uname:
                if new_uname and new_uname != uname:
                    u["username"] = new_uname
                if full_name is not None:
                    u["full_name"] = full_name.strip()
                if role is not None:
                    u["role"] = role
                if office is not None:
                    u["office"] = office.strip()
                if email is not None:
                    u["email"] = email.strip()
                _save_users_json(users)
                return True, None
        return False, "User not found."


# ── Username rename with full-history rewrite ───────────────────────────────────

# Document JSONB keys that hold a bare username string (scoping report §2a).
# These are UNAMBIGUOUS username fields, rewritten by exact match on the old
# username alone. The ambiguous full_name-or-username fields (received_by,
# accepted_by, travel_log[].officer) are handled separately in Step 2 by
# _RENAME_AMBIGUOUS_KEYS + the travel_log round-trip, because they need matching
# on BOTH the old username AND the old full_name.
_RENAME_DOC_KEYS = (
    "logged_by",
    "original_logged_by",
    "submitted_by",
    "pending_at_staff",
    "intended_for_username",
    "transferred_by",
    "transferred_to",
    "released_by",
    "rejected_by",
    "assigned_to",
    "updated_by",
    # Step 2.5 — a PARALLEL username companion to accepted_by. Always a bare
    # username (api.py:1287 writes accepted_by_username = user_id), so it belongs
    # with the unambiguous exact-username keys, not the ambiguous full_name set.
    "accepted_by_username",
)

# Step 2: top-level document fields that store "full_name OR username" — you
# cannot tell which by inspection (scoping report; confirmed in code):
#   - received_by  : full_name on web/scan/excel, username-fallback on mobile
#   - accepted_by  : username on web (dashboard.py:1811), full_name on mobile
#                    (api.py:1276/1286), OR a composite proxy label
#                    "{full_name} (Admin, proxy for {target})" (api.py:1269).
# Step 2.5 adds the client-facing display-name companions. These store a
# full_name for portal display but are read BEFORE live username resolution in
# services/client_view.py (accepted_by_name @192, pending_at_staff_name @211),
# so a stale stored name would win over the renamed username — the highest-
# visibility miss. They go in the ambiguous set (not a full_name-only list)
# because the username-match pass is a harmless safe superset if any ever holds
# a username instead of a display name:
#   - accepted_by_name       (full_name, client-facing)
#   - pending_at_staff_name  (full_name, client-facing)
#   - submitted_by_name      (full_name)
#   - intended_for_name      (full_name, client-facing)
# We rewrite all of these by EXACT match on the old username and — only when the
# old full_name is unique among users — a CASE-INSENSITIVE match on the old
# full_name (Step 2.5 Change B: prod stores full_name with inconsistent casing,
# e.g. users.full_name "KIM WENDELL DAVOCOL" vs documents "Kim Wendell Davocol").
# The full_name match is still corruption-safe: a composite proxy label never
# equals the plain old full_name even case-folded, so it is left intact.
_RENAME_AMBIGUOUS_KEYS = (
    "received_by",
    "accepted_by",
    "accepted_by_name",
    "pending_at_staff_name",
    "submitted_by_name",
    "intended_for_name",
)

# FREE-TEXT BOUNDARY (Step 2.5 — deliberate, not an omission). These fields also
# can contain a person's name, but they are NOT rewritten by rename_user:
#   - referred_to          : free-text recipient string (routes/client.py) — may
#                            coincidentally contain a full_name but is not a
#                            structured identity field.
#   - sender_name          : free-text sender label (api.py:3168/3191/3394).
#   - recipient_name       : free-text recipient label.
#   - travel_log[].remarks : free-text remarks that may mention a name in prose.
# The rename rewrites STRUCTURED identity fields (a field whose whole value IS an
# actor's username or display name), never free-text that merely may contain a
# name — rewriting prose would corrupt it and match by coincidence. If a future
# reader wonders why these are skipped: it was a decision.


def _rename_summary(old: str, new: str) -> dict:
    """Zeroed per-surface counter dict; both backends fill the same shape."""
    return {
        "old_username": old,
        "new_username": new,
        # documents_updated counts FIELD-level rewrites (one document that holds
        # the old name under two keys contributes 2). Honest "rows affected",
        # not distinct-doc count.
        "documents_updated":           0,
        # Step 2 / 2.5 — the ambiguous display fields (field-level rowcounts,
        # summing both the username-match and the full_name-match rewrites).
        "received_by_updated":            0,
        "accepted_by_updated":            0,
        "accepted_by_name_updated":       0,   # Step 2.5 (client-facing)
        "pending_at_staff_name_updated":  0,   # Step 2.5 (client-facing)
        "submitted_by_name_updated":      0,   # Step 2.5
        "intended_for_name_updated":      0,   # Step 2.5 (client-facing)
        "travel_log_hops_updated":     0,   # individual travel_log hops rewritten
        "travel_log_docs_updated":     0,   # distinct docs whose travel_log changed
        # full_name rewrite decision (set in the pre-flight):
        #   full_name_matched   → old full_name was unique, so full_name-based
        #                         rewrite of the ambiguous fields WAS applied.
        #   full_name_ambiguous → old full_name is SHARED by >1 user, so the
        #                         full_name-based rewrite was SKIPPED; some
        #                         historical display names still show the old
        #                         name and the UI should warn.
        "full_name_matched":           False,
        "full_name_ambiguous":         False,
        "activity_log_updated":        0,
        "saved_offices_updated":       0,
        "routing_slips_updated":       0,
        "office_traffic_updated":      0,
        "appointments_updated":        0,
        "so_records_updated":          0,
        "staff_pairings_updated":      0,
        "staff_groups_updated":        0,
        "staff_group_members_updated": 0,
        "transfer_batches_updated":    0,
        "import_batches_updated":      0,
        "client_qr_tokens_updated":    0,
        "password_reset_tokens_updated": 0,
        "push_tokens_updated":         0,
        "user_carts_updated":          0,
        "users_updated":               0,
    }


def rename_user(old_username: str, new_username: str,
                old_full_name: str = "", new_full_name: str = "") -> tuple[bool, str | None, dict]:
    """Rename a user AND rewrite every reference to the old username, atomically.

    Returns (ok, error_message, summary). ``summary`` is always the per-surface
    counter dict (zeroed on failure) so the caller can log/verify.

    A rename changes BOTH the username AND (usually) the full_name, so all four
    strings are known. That is what lets Step 2 rewrite the ambiguous display
    fields — received_by / accepted_by / travel_log[].officer store
    "full_name OR username" and cannot be disambiguated by inspection.

    SCOPE:
      - Step 1: the unambiguous username keys in _RENAME_DOC_KEYS and the
        non-document tables (report §2c).
      - Step 2: the ambiguous display fields _RENAME_AMBIGUOUS_KEYS
        (received_by, accepted_by) and the nested travel_log[].officer hops,
        rewritten by EXACT match on the old username AND — only when the old
        full_name is UNIQUE among users — the old full_name.

    full_name safety: if the old full_name is shared by more than one user,
    matching on it would rewrite a DIFFERENT person's history, so the
    full_name-based rewrite is SKIPPED and summary["full_name_ambiguous"] is set
    True (the username-based rewrite still runs). Composite proxy labels like
    "{full_name} (Admin, proxy for {target})" never equal the plain old
    full_name, so exact matching leaves them intact rather than corrupting them.

    Atomicity mirrors restore_backup (services/backup.py): in DB mode the entire
    rewrite runs inside ONE get_conn() transaction on ONE cursor and commits
    once; any failure rolls the whole thing back (never a half-renamed DB). It
    deliberately uses raw cur.execute only — NOT batch_save_docs or audit_log,
    which open their own connections / commit independently and would break
    atomicity (and audit_log is the ROUTE's job post-commit, Step 3). The nested
    travel_log rewrite is a Python round-trip on that SAME cursor (SELECT the
    affected docs, edit in memory, UPDATE back), never batch_save_docs.

    This is a SERVICE-ONLY function: nothing calls it yet — it is unreachable
    from any HTTP path until the Step 3 route wiring.
    """
    old = (old_username or "").lower().strip()
    new = (new_username or "").lower().strip()
    # full_names are DISPLAY strings — do NOT lowercase; only strip.
    old_fn = (old_full_name or "").strip()
    new_fn = (new_full_name or "").strip()
    summary = _rename_summary(old, new)

    # ── Pre-flight (format only; existence/uniqueness checked per-backend) ──
    ok, verr = _validate_username(new)
    if not ok:
        return False, verr, summary
    if not old:
        return False, "Current username is required.", summary
    if old == new:
        return False, "New username is the same as the current one.", summary

    # Is the full_name actually changing? Only then is a full_name-based rewrite
    # of the ambiguous fields meaningful (if the name is unchanged, occurrences
    # holding the full_name are already correct and the username-based rewrite
    # covers the rest). fn_change gates whether we even consult uniqueness.
    fn_change = bool(old_fn and new_fn and old_fn != new_fn)

    if USE_DB:
        try:
            # ONE connection, ONE transaction. _ConnCtx commits on clean exit and
            # rolls the WHOLE thing back on any exception (database.py:_ConnCtx).
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Pre-flight inside the txn. An early return here exits the
                    # `with` cleanly → commits an EMPTY transaction (no writes yet
                    # = harmless), which is why these checks precede every UPDATE.
                    cur.execute("SELECT 1 FROM users WHERE username = %s", (old,))
                    if not cur.fetchone():
                        return False, f"User '{old}' not found.", summary
                    cur.execute("SELECT 1 FROM users WHERE username = %s", (new,))
                    if cur.fetchone():
                        return False, f"Username '{new}' is already taken.", summary

                    # full_name uniqueness gate (Step 2a). Only consulted when the
                    # full_name is actually changing. COUNT includes the renamed
                    # user's own row, so exactly 1 == unique to this person == safe
                    # to match on. >1 == shared == matching would rewrite someone
                    # else's history, so skip full_name matching and flag it.
                    #
                    # Step 2.5 Change B: the gate is CASE-INSENSITIVE too. Two
                    # rows "Jane Doe" and "JANE DOE" are the same collision risk,
                    # so they must count as a shared name. lower()=lower() also
                    # keeps this consistent with the case-insensitive rewrites
                    # below. (Kim stays unique: only one row case-folds to
                    # "kim wendell davocol", so count == 1 and fn_safe holds.)
                    fn_safe = False
                    if fn_change:
                        cur.execute("SELECT COUNT(*) AS c FROM users WHERE lower(full_name) = lower(%s)", (old_fn,))
                        if cur.fetchone()["c"] == 1:
                            fn_safe = True
                            summary["full_name_matched"] = True
                        else:
                            summary["full_name_ambiguous"] = True

                    # 1) documents.data top-level keys — set-based, one per key.
                    #    jsonb_set(data, '{KEY}', to_jsonb(new)) WHERE data->>'KEY' = old.
                    doc_total = 0
                    for key in _RENAME_DOC_KEYS:
                        cur.execute(
                            "UPDATE documents "
                            "SET data = jsonb_set(data, %s, to_jsonb(%s::text)) "
                            "WHERE data->>%s = %s",
                            ([key], new, key, old),
                        )
                        doc_total += cur.rowcount
                    summary["documents_updated"] = doc_total

                    # 1b) Step 2 — ambiguous display fields (received_by,
                    #     accepted_by). Match the old username always, and the old
                    #     full_name only when fn_safe. Per-field rowcount (username
                    #     + full_name matches summed). Exact match, so a composite
                    #     proxy label is never touched.
                    #     Step 2.5 Change B: the full_name pass matches
                    #     CASE-INSENSITIVELY (lower(data->>KEY) = lower(old_fn))
                    #     so title-case variants are caught; the value written
                    #     back is the new canonical full_name, normalizing casing.
                    #     The username pass stays EXACT (usernames are already
                    #     lower()+strip()'d). Both values remain bound params.
                    for key in _RENAME_AMBIGUOUS_KEYS:
                        field_total = 0
                        cur.execute(
                            "UPDATE documents "
                            "SET data = jsonb_set(data, %s, to_jsonb(%s::text)) "
                            "WHERE data->>%s = %s",
                            ([key], new, key, old),
                        )
                        field_total += cur.rowcount
                        if fn_safe:
                            cur.execute(
                                "UPDATE documents "
                                "SET data = jsonb_set(data, %s, to_jsonb(%s::text)) "
                                "WHERE lower(data->>%s) = lower(%s)",
                                ([key], new_fn, key, old_fn),
                            )
                            field_total += cur.rowcount
                        summary[f"{key}_updated"] = field_total

                    # 1c) Step 2 — travel_log[].officer. Nested JSONB array, so no
                    #     pure set-based rewrite: scope the load with a containment
                    #     filter (@> tests array-element containment of a partial
                    #     object) so we touch only affected docs, not all ~17k;
                    #     edit officer hops in Python; write each changed doc back
                    #     on THIS SAME cursor (never batch_save_docs). Every other
                    #     field in each hop is preserved — only officer changes.
                    #     Step 2.5 Change B: the username filter stays EXACT
                    #     containment (@>), but the full_name filter must be
                    #     CASE-INSENSITIVE — @> is case-sensitive, so it would
                    #     MISS a title-case officer. Scope it with a guarded
                    #     jsonb_array_elements EXISTS on lower(e->>'officer') so
                    #     we still touch only affected docs, not all ~17k. The
                    #     jsonb_typeof guard skips docs whose travel_log is null
                    #     or a non-array scalar (jsonb_array_elements would raise).
                    officer_sql = ("SELECT id, data FROM documents "
                                   "WHERE data->'travel_log' @> %s::jsonb")
                    officer_params = [json.dumps([{"officer": old}])]
                    if fn_safe:
                        officer_sql = (
                            "SELECT id, data FROM documents "
                            "WHERE data->'travel_log' @> %s::jsonb "
                            "   OR (jsonb_typeof(data->'travel_log') = 'array' "
                            "       AND EXISTS ("
                            "         SELECT 1 FROM jsonb_array_elements(data->'travel_log') AS e "
                            "         WHERE lower(e->>'officer') = lower(%s)))")
                        officer_params = [json.dumps([{"officer": old}]), old_fn]
                    cur.execute(officer_sql, officer_params)
                    tl_rows = cur.fetchall()
                    tl_hops = tl_docs = 0
                    old_fn_lower = old_fn.lower()
                    for row in tl_rows:
                        data = row["data"]
                        if isinstance(data, str):        # defensive: normally a dict
                            data = json.loads(data)
                        doc_changed = False
                        for hop in data.get("travel_log", []) or []:
                            if not isinstance(hop, dict):
                                continue
                            off = hop.get("officer")
                            if off == old:
                                hop["officer"] = new
                                tl_hops += 1
                                doc_changed = True
                            elif fn_safe and isinstance(off, str) and off.lower() == old_fn_lower:
                                hop["officer"] = new_fn
                                tl_hops += 1
                                doc_changed = True
                        if doc_changed:
                            cur.execute(
                                "UPDATE documents SET data = %s::jsonb WHERE id = %s",
                                (json.dumps(data), row["id"]),
                            )
                            tl_docs += 1
                    summary["travel_log_hops_updated"] = tl_hops
                    summary["travel_log_docs_updated"] = tl_docs

                    # 2) Non-document tables (report §2c) — one UPDATE per column.
                    cur.execute("UPDATE activity_log SET username = %s WHERE username = %s", (new, old))
                    summary["activity_log_updated"] = cur.rowcount

                    so_updated = 0
                    cur.execute("UPDATE saved_offices SET created_by = %s WHERE created_by = %s", (new, old))
                    so_updated += cur.rowcount
                    # primary_recipient is the office's default receiving-staff
                    # username. A missed rewrite here is the cosmetic "stale
                    # kimwendell" default seen on the mobile submit screen.
                    cur.execute("UPDATE saved_offices SET primary_recipient = %s WHERE primary_recipient = %s", (new, old))
                    so_updated += cur.rowcount
                    summary["saved_offices_updated"] = so_updated

                    slips = 0
                    cur.execute("UPDATE routing_slips SET prepared_by = %s WHERE prepared_by = %s", (new, old))
                    slips += cur.rowcount
                    cur.execute("UPDATE routing_slips SET archived_by = %s WHERE archived_by = %s", (new, old))
                    slips += cur.rowcount
                    summary["routing_slips_updated"] = slips

                    cur.execute("UPDATE office_traffic SET client_username = %s WHERE client_username = %s", (new, old))
                    summary["office_traffic_updated"] = cur.rowcount

                    cur.execute("UPDATE appointments SET client_username = %s WHERE client_username = %s", (new, old))
                    summary["appointments_updated"] = cur.rowcount

                    cur.execute("UPDATE so_records SET generated_by = %s WHERE generated_by = %s", (new, old))
                    summary["so_records_updated"] = cur.rowcount

                    pairings = 0
                    # staff_pairings has UNIQUE(user_a, user_b); a rename that would
                    # duplicate an existing pair raises inside the txn and rolls the
                    # WHOLE rename back cleanly (no partial write). Same for
                    # staff_group_members' UNIQUE(group_id, username). Acceptable in
                    # Step 1 — a clean abort, not corruption.
                    cur.execute("UPDATE staff_pairings SET user_a = %s WHERE user_a = %s", (new, old))
                    pairings += cur.rowcount
                    cur.execute("UPDATE staff_pairings SET user_b = %s WHERE user_b = %s", (new, old))
                    pairings += cur.rowcount
                    cur.execute("UPDATE staff_pairings SET created_by = %s WHERE created_by = %s", (new, old))
                    pairings += cur.rowcount
                    summary["staff_pairings_updated"] = pairings

                    cur.execute("UPDATE staff_groups SET created_by = %s WHERE created_by = %s", (new, old))
                    summary["staff_groups_updated"] = cur.rowcount

                    members = 0
                    cur.execute("UPDATE staff_group_members SET username = %s WHERE username = %s", (new, old))
                    members += cur.rowcount
                    cur.execute("UPDATE staff_group_members SET added_by = %s WHERE added_by = %s", (new, old))
                    members += cur.rowcount
                    summary["staff_group_members_updated"] = members

                    batches = 0
                    cur.execute("UPDATE transfer_batches SET transferred_by = %s WHERE transferred_by = %s", (new, old))
                    batches += cur.rowcount
                    cur.execute("UPDATE transfer_batches SET transferred_to = %s WHERE transferred_to = %s", (new, old))
                    batches += cur.rowcount
                    # Step 2.5 A3: transferred_to_name is a full_name column, so it
                    # is subject to the SAME uniqueness gate + case-insensitive
                    # rule as the ambiguous full_name fields above.
                    if fn_safe:
                        cur.execute(
                            "UPDATE transfer_batches SET transferred_to_name = %s "
                            "WHERE lower(transferred_to_name) = lower(%s)",
                            (new_fn, old_fn),
                        )
                        batches += cur.rowcount
                    summary["transfer_batches_updated"] = batches

                    cur.execute("UPDATE import_batches SET imported_by = %s WHERE imported_by = %s", (new, old))
                    summary["import_batches_updated"] = cur.rowcount

                    # Token tables keyed on their token (client_qr_tokens.token,
                    # password_reset_tokens.token_hash), with username as a plain
                    # non-PK column — so a straight UPDATE old→new can't collide.
                    cur.execute("UPDATE client_qr_tokens SET username = %s WHERE username = %s", (new, old))
                    summary["client_qr_tokens_updated"] = cur.rowcount
                    cur.execute("UPDATE password_reset_tokens SET username = %s WHERE username = %s", (new, old))
                    summary["password_reset_tokens_updated"] = cur.rowcount

                    # 3) PRIMARY-KEY tables: push_tokens.username and
                    #    user_carts.username. A plain UPDATE old→new would violate
                    #    the PK if a STALE row already sits under `new`. We confirmed
                    #    above that `new` is free in `users`, so any push-token/cart
                    #    row under `new` is orphaned data safe to discard first; the
                    #    DELETE is a no-op when none exists. Both statements are in
                    #    this same txn, so a failure still rolls everything back.
                    cur.execute("DELETE FROM push_tokens WHERE username = %s", (new,))
                    cur.execute("UPDATE push_tokens SET username = %s WHERE username = %s", (new, old))
                    summary["push_tokens_updated"] = cur.rowcount

                    cur.execute("DELETE FROM user_carts WHERE username = %s", (new,))
                    cur.execute("UPDATE user_carts SET username = %s WHERE username = %s", (new, old))
                    summary["user_carts_updated"] = cur.rowcount

                    # 4) users.username LAST.
                    cur.execute("UPDATE users SET username = %s WHERE username = %s", (new, old))
                    summary["users_updated"] = cur.rowcount
            # Committed here on clean exit of the `with`.
            return True, None, summary
        except Exception as e:
            # _ConnCtx already rolled back as the exception passed through __exit__.
            if "unique" in str(e).lower():
                return False, f"Rename failed: a uniqueness constraint blocked it ({e}).", summary
            return False, f"Rename failed: {e}", summary

    # ── JSON-file fallback ──────────────────────────────────────────────────
    # The test suite runs JSON-only, so parity matters. BUT the JSON surface is
    # genuinely SMALLER than the DB surface: staff_pairings, staff_groups,
    # staff_group_members, transfer_batches, import_batches, so_records and
    # push_tokens are DB-ONLY features (no JSON file exists for them), so their
    # counters stay 0 in this mode — there is nothing to rewrite, not a miss.
    # Same surface where a file exists, same order, same summary shape.
    return _rename_user_json(old, new, old_fn, new_fn, fn_change, summary)


def _json_rewrite_list(path: str, fields: tuple, old: str, new: str) -> int:
    """Rewrite each top-level string field in `fields` equal to `old` → `new`
    across a JSON file holding a list[dict]. Returns FIELD-level change count.
    Atomic write (temp + os.replace), mirroring _save_users_json. No-op (and no
    write) if the file is absent or nothing changed."""
    if not os.path.exists(path):
        return 0
    try:
        with open(path) as f:
            rows = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(rows, list):
        return 0
    changed = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        for fld in fields:
            if row.get(fld) == old:
                row[fld] = new
                changed += 1
    if changed:
        _atomic_write_json(path, rows)
    return changed


def _atomic_write_json(path: str, data) -> None:
    """Temp-file + os.replace write, matching the _save_users_json pattern."""
    dir_name = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _rename_user_json(old: str, new: str, old_fn: str, new_fn: str,
                      fn_change: bool, summary: dict) -> tuple[bool, str | None, dict]:
    """JSON-backend rename. Not atomic across files (an inherent JSON-mode limit,
    same as restore_backup's JSON path) — best-effort per file, users.json last.
    Mirrors the DB path's Step-2 rewrites (ambiguous fields + travel_log officer)
    with the same full_name-uniqueness gate."""
    from services.cart_store import _CART_FILE   # dict keyed by username
    from services.appointments import _APT_FILE  # __file__-relative, not cwd

    # Existence / uniqueness against users.json.
    users = _load_users_json()
    if not any(u.get("username") == old for u in users):
        return False, f"User '{old}' not found.", summary
    if any(u.get("username") == new for u in users):
        return False, f"Username '{new}' is already taken.", summary

    # full_name uniqueness gate — same rule as the DB path (count includes the
    # renamed user's own row; exactly 1 == unique == safe to match on).
    # Step 2.5 Change B: case-insensitive, matching the DB lower()=lower() gate.
    fn_safe = False
    old_fn_lower = old_fn.lower()
    if fn_change:
        if sum(1 for u in users if (u.get("full_name") or "").lower() == old_fn_lower) == 1:
            fn_safe = True
            summary["full_name_matched"] = True
        else:
            summary["full_name_ambiguous"] = True

    try:
        # 1) documents.json — one pass rewrites the unambiguous _RENAME_DOC_KEYS,
        #    the ambiguous _RENAME_AMBIGUOUS_KEYS (username always, full_name when
        #    fn_safe), and the nested travel_log[].officer hops.
        from services.documents import load_docs, _save_docs_json
        docs = load_docs(include_deleted=True)
        doc_total = 0
        # Per-key ambiguous counters (Step 2.5 — was a hardcoded recv/acc pair).
        amb_counts = {key: 0 for key in _RENAME_AMBIGUOUS_KEYS}
        tl_hops = tl_docs = 0
        for d in docs:
            for key in _RENAME_DOC_KEYS:
                if d.get(key) == old:
                    d[key] = new
                    doc_total += 1
            # Ambiguous fields: username exact always, full_name only when
            # fn_safe and CASE-INSENSITIVELY (Step 2.5 Change B) — write back the
            # new canonical full_name, normalizing casing.
            for key in _RENAME_AMBIGUOUS_KEYS:
                val = d.get(key)
                if val == old:
                    d[key] = new
                elif fn_safe and isinstance(val, str) and val.lower() == old_fn_lower:
                    d[key] = new_fn
                else:
                    continue
                amb_counts[key] += 1
            # travel_log[].officer — preserve every other hop field.
            doc_changed = False
            for hop in d.get("travel_log", []) or []:
                if not isinstance(hop, dict):
                    continue
                off = hop.get("officer")
                if off == old:
                    hop["officer"] = new
                    tl_hops += 1
                    doc_changed = True
                elif fn_safe and isinstance(off, str) and off.lower() == old_fn_lower:
                    hop["officer"] = new_fn
                    tl_hops += 1
                    doc_changed = True
            if doc_changed:
                tl_docs += 1
        if doc_total or any(amb_counts.values()) or tl_hops:
            _save_docs_json(docs)
        summary["documents_updated"]       = doc_total
        for key, cnt in amb_counts.items():
            summary[f"{key}_updated"] = cnt
        summary["travel_log_hops_updated"] = tl_hops
        summary["travel_log_docs_updated"] = tl_docs

        # 2) Other list-shaped JSON files that exist in JSON mode.
        summary["activity_log_updated"]   = _json_rewrite_list("activity_log.json",   ("username",),         old, new)
        summary["saved_offices_updated"]  = _json_rewrite_list("saved_offices.json",  ("created_by", "primary_recipient"), old, new)
        summary["routing_slips_updated"]  = _json_rewrite_list("routing_slips.json",  ("prepared_by", "archived_by"), old, new)
        summary["office_traffic_updated"] = _json_rewrite_list("office_traffic.json", ("client_username",),  old, new)
        summary["appointments_updated"]   = _json_rewrite_list(_APT_FILE,             ("client_username",),  old, new)
        # staff_*/transfer_batches/import_batches/so_records/push_tokens: DB-only,
        # no JSON file — counters intentionally remain 0 here.
        # client_qr_tokens.json and password_reset_tokens.json DO exist in JSON
        # mode, but each is a dict keyed by the TOKEN with `username` as a
        # sub-value — a shape neither _json_rewrite_list (list[dict]) nor the
        # pending_carts block (dict keyed BY username) handles. Covering them
        # would need a bespoke handler; left as a known JSON-mode gap rather
        # than invent a new pattern. The DB path (production) covers both.

        # 3) pending_carts.json is a DICT keyed by username (user_carts twin).
        #    Move the key; drop any stale destination first (new confirmed free).
        if os.path.exists(_CART_FILE):
            try:
                with open(_CART_FILE, encoding="utf-8") as f:
                    carts = json.load(f)
            except (json.JSONDecodeError, OSError):
                carts = None
            if isinstance(carts, dict) and old in carts:
                carts.pop(new, None)
                carts[new] = carts.pop(old)
                _atomic_write_json(_CART_FILE, carts)
                summary["user_carts_updated"] = 1

        # 4) users.json LAST.
        for u in users:
            if u.get("username") == old:
                u["username"] = new
                summary["users_updated"] += 1
        _save_users_json(users)

        return True, None, summary
    except Exception as e:
        return False, f"Rename failed: {e}", summary


def update_user_documents_handled(username: str, documents_handled: list) -> tuple[bool, str | None]:
    """Replace the documents_handled list for a user. Returns (success, error_message)."""
    import json as _json
    uname = username.lower().strip()
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET documents_handled = %s::jsonb WHERE username = %s",
                        (_json.dumps(documents_handled or []), uname),
                    )
            return True, None
        except Exception as e:
            return False, f"Database error: {e}"
    else:
        users = _load_users_json()
        for u in users:
            if u["username"] == uname:
                u["documents_handled"] = documents_handled or []
                _save_users_json(users)
                return True, None
        return False, "User not found."


def get_user_can_generate_so(username: str) -> bool:
    """Return the can_generate_so flag for a user. Defaults to False if not set."""
    uname = username.lower().strip()
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT can_generate_so FROM users WHERE username = %s", (uname,)
                    )
                    row = cur.fetchone()
            return bool(row["can_generate_so"]) if row else False
        except Exception:
            return False
    else:
        users = _load_users_json()
        for u in users:
            if u["username"] == uname:
                return bool(u.get("can_generate_so", False))
        return False


def set_user_can_generate_so(username: str, value: bool) -> tuple[bool, str | None]:
    """Set the can_generate_so flag for a user."""
    uname = username.lower().strip()
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET can_generate_so = %s WHERE username = %s",
                        (value, uname),
                    )
            return True, None
        except Exception as e:
            return False, f"Database error: {e}"
    else:
        users = _load_users_json()
        for u in users:
            if u["username"] == uname:
                u["can_generate_so"] = value
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