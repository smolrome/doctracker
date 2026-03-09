"""
services/email.py — Invite token management and Brevo email sending.
"""
import json
import os
import urllib.error
import urllib.request
import uuid

from services.database import USE_DB, get_conn
from config import BREVO_API_KEY, MAIL_SENDER, MAIL_ENABLED, APP_URL


# ── Token helpers ─────────────────────────────────────────────────────────────

def generate_invite_token(email: str, name: str = "") -> str:
    """Create a unique one-time invite token stored in DB or JSON."""
    token = uuid.uuid4().hex
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM invite_tokens WHERE email=%s AND used=FALSE", (email,)
                    )
                    cur.execute(
                        "INSERT INTO invite_tokens (token, email, name) VALUES (%s, %s, %s)",
                        (token, email, name)
                    )
                conn.commit()
        except Exception as e:
            print(f"generate_invite_token error: {e}")
    else:
        tokens = _load_tokens_json()
        tokens = [t for t in tokens if not (t["email"] == email and not t.get("used"))]
        tokens.append({"token": token, "email": email, "name": name, "used": False})
        _save_tokens_json(tokens)
    return token


def validate_invite_token(token: str) -> tuple[str | None, str | None]:
    """Check token is valid, unused, and not expired. Returns (email, name)."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT email, name FROM invite_tokens
                           WHERE token=%s AND used=FALSE AND expires_at > NOW()""",
                        (token,)
                    )
                    row = cur.fetchone()
                    return (row["email"], row["name"]) if row else (None, None)
        except Exception as e:
            print(f"[validate_invite_token ERROR] {type(e).__name__}: {e}")
            return None, None
    else:
        for t in _load_tokens_json():
            if t["token"] == token and not t.get("used"):
                return t["email"], t.get("name", "")
        return None, None


def consume_invite_token(token: str):
    """Mark token as used after successful registration."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE invite_tokens SET used=TRUE WHERE token=%s", (token,))
                conn.commit()
        except Exception as e:
            print(f"consume_invite_token error: {e}")
    else:
        tokens = _load_tokens_json()
        for t in tokens:
            if t["token"] == token:
                t["used"] = True
        _save_tokens_json(tokens)


def get_all_tokens() -> list[dict]:
    """Return all tokens for admin view."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT token, email, name, used, created_at, expires_at
                           FROM invite_tokens ORDER BY created_at DESC LIMIT 50"""
                    )
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"get_all_tokens error: {e}")
            return []
    return _load_tokens_json()


# ── Email sending ─────────────────────────────────────────────────────────────

def send_invite_email(to_email: str, to_name: str = "",
                      base_url: str = "") -> tuple[bool, str]:
    """Send invite via Brevo API. Returns (success, token_or_error)."""
    if not MAIL_ENABLED:
        return False, "Email not configured. Set BREVO_API_KEY in Railway Variables."

    token  = generate_invite_token(to_email, to_name)
    base   = (base_url or APP_URL).rstrip("/")
    link   = f"{base}/register?token={token}"
    greeting = f"Hi {to_name}," if to_name else "Hello,"

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;">
      <div style="background:#0D1B2A;padding:28px;text-align:center;border-radius:12px 12px 0 0;">
        <div style="font-size:22px;font-weight:800;color:#fff;">DocTracker - DepEd Leyte</div>
      </div>
      <div style="background:#fff;padding:32px;border-radius:0 0 12px 12px;">
        <p>{greeting}</p>
        <p>You have been invited to join the <strong>DepEd Leyte Division Document Tracker</strong>.</p>
        <div style="text-align:center;margin:24px 0;">
          <a href="{link}" style="background:#3B82F6;color:#fff;text-decoration:none;
             padding:14px 32px;border-radius:8px;font-weight:700;font-size:16px;display:inline-block;">
            Accept Invitation &amp; Register
          </a>
        </div>
        <p style="color:#92400E;background:#FFF3CD;padding:12px;border-radius:6px;font-size:13px;">
          This link expires in 48 hours and can only be used once.
        </p>
        <p style="color:#666;font-size:12px;word-break:break-all;">Or copy: {link}</p>
      </div>
    </div>
    """

    payload = json.dumps({
        "sender":      {"name": "DepEd DocTracker", "email": MAIL_SENDER},
        "to":          [{"email": to_email, "name": to_name or to_email}],
        "subject":     "You're Invited - DepEd Leyte DocTracker",
        "htmlContent": html_body,
        "textContent": f"{greeting}\n\nRegister here (expires 48hrs):\n{link}",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=payload,
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return True, token
    except urllib.error.HTTPError as e:
        return False, f"Brevo error {e.code}: {e.read().decode()}"
    except Exception as e:
        return False, f"Email error: {e}"


# ── JSON fallback helpers ─────────────────────────────────────────────────────

def _load_tokens_json() -> list[dict]:
    if os.path.exists("invite_tokens.json"):
        with open("invite_tokens.json") as f:
            return json.load(f)
    return []


def _save_tokens_json(tokens: list[dict]):
    with open("invite_tokens.json", "w") as f:
        json.dump(tokens, f, indent=2)