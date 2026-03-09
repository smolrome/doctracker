"""
services/auth.py — Authentication helpers.
Covers: password hashing/verification, user CRUD, rate limiting, session helpers.
"""
import hashlib
import json
import os
import secrets
import threading
import time

try:
    import bcrypt
    BCRYPT_OK = True
except ImportError:
    BCRYPT_OK = False

from services.database import USE_DB, get_conn
from config import ADMIN_USERNAME, ADMIN_PASSWORD, RATE_LIMITS


# ── Rate limiting (in-memory, thread-safe) ────────────────────────────────────

_rate_lock  = threading.Lock()
_rate_store = {}   # key → {count, window_start, locked_until}


def check_rate_limit(action: str, identifier: str) -> tuple[bool, int]:
    """Returns (allowed, wait_seconds). Blocks after too many attempts."""
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


def reset_rate_limit(action: str, identifier: str):
    with _rate_lock:
        _rate_store.pop(f"{action}:{identifier}", None)


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash with bcrypt if available, SHA-256 fallback."""
    if BCRYPT_OK:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain: str, stored_hash: str) -> bool:
    """Verify password — handles both bcrypt and legacy SHA-256 hashes."""
    if BCRYPT_OK and stored_hash.startswith("$2"):
        try:
            return bcrypt.checkpw(plain.encode(), stored_hash.encode())
        except Exception:
            return False
    return hashlib.sha256(plain.encode()).hexdigest() == stored_hash


# ── User CRUD ─────────────────────────────────────────────────────────────────

def create_user(username: str, password: str, full_name: str = "",
                role: str = "staff", office: str = "") -> tuple[bool, str | None]:
    """Create a new user. Returns (success, error_message)."""
    uname = username.lower().strip()
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO users (username, password_hash, full_name, role, office, active)
                           VALUES (%s, %s, %s, %s, %s, TRUE)""",
                        (uname, hash_password(password), full_name.strip(), role, office.strip())
                    )
                conn.commit()
            return True, None
        except Exception as e:
            if "unique" in str(e).lower():
                return False, "Username already taken."
            return False, str(e)
    else:
        users = _load_users_json()
        if any(u["username"] == uname for u in users):
            return False, "Username already taken."
        users.append({
            "username": uname,
            "password_hash": hash_password(password),
            "full_name": full_name.strip(),
            "role": role,
            "office": office.strip(),
            "active": True,
        })
        _save_users_json(users)
        return True, None


def verify_user(username: str, password: str) -> tuple[str | None, str | None, str]:
    """Verify credentials. Returns (full_name, role, office) or (None, None, "")."""
    uname = username.strip().lower()

    # Admin via env var — constant-time compare prevents timing attacks
    if (secrets.compare_digest(uname, ADMIN_USERNAME.lower())
            and secrets.compare_digest(password, ADMIN_PASSWORD)):
        return ADMIN_USERNAME, "admin", "DepEd Leyte Division"

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT full_name, role, password_hash, COALESCE(office,'') AS office
                           FROM users WHERE username=%s AND active=TRUE""",
                        (uname,)
                    )
                    row = cur.fetchone()
                    if row and verify_password(password, row["password_hash"]):
                        _upgrade_hash_if_needed(uname, password, row["password_hash"])
                        return row["full_name"] or uname, row["role"], row["office"] or ""
        except Exception as e:
            print(f"verify_user error: {e}")
    else:
        for u in _load_users_json():
            if (u["username"] == uname 
                and u.get("active", True)
                and verify_password(password, u.get("password_hash", ""))):
                return u.get("full_name") or uname, u.get("role", "staff"), u.get("office", "")

    return None, None, ""


def _upgrade_hash_if_needed(username: str, password: str, stored_hash: str):
    """Re-hash old SHA-256 passwords with bcrypt on first successful login."""
    if not (BCRYPT_OK and not stored_hash.startswith("$2")):
        return
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash=%s WHERE username=%s",
                    (hash_password(password), username)
                )
            conn.commit()
    except Exception:
        pass


def get_all_users() -> list[dict]:
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT username, full_name, role, active, last_login,
                                  created_at, COALESCE(office,'') AS office
                           FROM users ORDER BY created_at DESC"""
                    )
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"get_all_users error: {e}")
            return []
    return _load_users_json()


def set_user_active(username: str, active: bool):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE users SET active=%s WHERE username=%s", (active, username))
                conn.commit()
        except Exception as e:
            print(f"set_user_active error: {e}")
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
                    cur.execute("DELETE FROM users WHERE username=%s", (username,))
                conn.commit()
        except Exception as e:
            print(f"delete_user error: {e}")
    else:
        _save_users_json([u for u in _load_users_json() if u["username"] != username])


def update_last_login(username: str):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE users SET last_login=NOW() WHERE username=%s", (username,))
                conn.commit()
        except Exception as e:
            print(f"update_last_login error: {e}")


# ── JSON fallback helpers ─────────────────────────────────────────────────────

def _load_users_json() -> list[dict]:
    if os.path.exists("users.json"):
        with open("users.json") as f:
            return json.load(f)
    return []


def _save_users_json(users: list[dict]):
    with open("users.json", "w") as f:
        json.dump(users, f, indent=2)
