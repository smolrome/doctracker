"""
services/cart_store.py — Persist the staff logging cart per user.

Saves the cart to the database (or a JSON file fallback) keyed by username
so the cart survives logout, session expiry, and accidental tab closes.
"""

import json
import os

from services.database import USE_DB, get_conn

_CART_FILE = os.path.join(os.path.dirname(__file__), "..", "pending_carts.json")
_CART_FILE = os.path.normpath(_CART_FILE)


def _ensure_table():
    """Create the user_carts table if it doesn't exist yet."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_carts (
                        username   TEXT PRIMARY KEY,
                        cart_data  JSONB NOT NULL DEFAULT '[]',
                        saved_at   TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
            conn.commit()
    except Exception:
        pass


def save_cart(username: str, cart: list) -> None:
    """Persist the cart for this user. Overwrites any previously saved cart."""
    if not username or not cart:
        return
    if USE_DB:
        _ensure_table()
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO user_carts (username, cart_data, saved_at)
                           VALUES (%s, %s::jsonb, NOW())
                           ON CONFLICT (username) DO UPDATE
                               SET cart_data = EXCLUDED.cart_data,
                                   saved_at  = NOW()""",
                        (username.lower(), json.dumps(cart))
                    )
                conn.commit()
        except Exception as e:
            print(f"[cart_store] save_cart error for {username}: {e}")
    else:
        _file_save(username.lower(), cart)


def load_cart(username: str) -> list:
    """Return the saved cart for this user, or [] if none exists."""
    if not username:
        return []
    if USE_DB:
        _ensure_table()
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT cart_data FROM user_carts WHERE username = %s",
                        (username.lower(),)
                    )
                    row = cur.fetchone()
                    return row["cart_data"] if row else []
        except Exception as e:
            print(f"[cart_store] load_cart error for {username}: {e}")
            return []
    else:
        return _file_load(username.lower())


def clear_cart(username: str) -> None:
    """Delete the saved cart for this user (called after successful submission)."""
    if not username:
        return
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM user_carts WHERE username = %s",
                        (username.lower(),)
                    )
                conn.commit()
        except Exception as e:
            print(f"[cart_store] clear_cart error for {username}: {e}")
    else:
        _file_clear(username.lower())


# ── JSON file fallback (when USE_DB is False) ────────────────────────────────

def _read_file() -> dict:
    if os.path.exists(_CART_FILE):
        try:
            with open(_CART_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _write_file(data: dict) -> None:
    try:
        with open(_CART_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[cart_store] file write error: {e}")


def _file_save(username: str, cart: list) -> None:
    data = _read_file()
    data[username] = cart
    _write_file(data)


def _file_load(username: str) -> list:
    return _read_file().get(username, [])


def _file_clear(username: str) -> None:
    data = _read_file()
    data.pop(username, None)
    _write_file(data)
