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
                        """INSERT INTO invite_tokens (token, email, name, expires_at)
                           VALUES (%s, %s, %s, NOW() + INTERVAL '48 hours')""",
                        (token, email, name)
                    )
                conn.commit()
        except Exception as e:
            pass
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
                    # First check if token exists at all (for diagnostics)
                    cur.execute("SELECT email, name, used, expires_at FROM invite_tokens WHERE token=%s", (token,))
                    raw = cur.fetchone()
                    if raw is None:
                        return None, None
                    if raw["used"]:
                        return None, None
                    if raw["expires_at"] and raw["expires_at"] < __import__('datetime').datetime.now():
                        return None, None
                    return raw["email"], raw["name"]
        except Exception as e:
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
            pass
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


def send_credentials_email(to_email: str, to_name: str,
                           username: str, password: str,
                           base_url: str = "") -> tuple[bool, str]:
    """Send a new account's login credentials via Brevo. Returns (success, error_or_empty)."""
    if not MAIL_ENABLED:
        return False, "Email not configured."

    base     = (base_url or APP_URL).rstrip("/")
    login_url = f"{base}/login"
    greeting  = f"Hi {to_name}," if to_name else "Hello,"

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;">
      <div style="background:#0D1B2A;padding:28px;text-align:center;border-radius:12px 12px 0 0;">
        <div style="font-size:22px;font-weight:800;color:#fff;">DocTracker — DepEd Leyte</div>
        <div style="color:#C9A227;font-size:13px;margin-top:4px;">Schools Division of Leyte</div>
      </div>
      <div style="background:#fff;padding:32px;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;">
        <p style="margin:0 0 12px;">{greeting}</p>
        <p style="margin:0 0 20px;">Your account on the <strong>DepEd Leyte Division Document Tracker</strong>
        has been created. Here are your login credentials:</p>

        <div style="background:#F0F9FF;border:1px solid #BAE6FD;border-radius:10px;padding:20px;margin:0 0 24px;">
          <table style="width:100%;border-collapse:collapse;">
            <tr>
              <td style="padding:6px 0;color:#64748B;font-size:13px;width:40%;">Username</td>
              <td style="padding:6px 0;font-weight:700;font-size:15px;color:#0E2A47;
                         font-family:monospace;">{username}</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:#64748B;font-size:13px;">Temporary Password</td>
              <td style="padding:6px 0;font-weight:700;font-size:15px;color:#0E2A47;
                         font-family:monospace;">{password}</td>
            </tr>
          </table>
        </div>

        <div style="text-align:center;margin:0 0 24px;">
          <a href="{login_url}" style="background:#0E2A47;color:#fff;text-decoration:none;
             padding:14px 36px;border-radius:8px;font-weight:700;font-size:15px;
             display:inline-block;">Log In Now</a>
        </div>

        <div style="background:#FEF3C7;border:1px solid #FCD34D;border-radius:8px;
                    padding:12px 16px;font-size:13px;color:#92400E;margin:0 0 16px;">
          ⚠️ <strong>Please change your password</strong> after your first login under
          your profile settings.
        </div>

        <p style="color:#6B7280;font-size:12px;margin:0;">
          If you did not expect this email, please contact your system administrator.
        </p>
      </div>
    </div>
    """

    payload = json.dumps({
        "sender":      {"name": "DepEd DocTracker", "email": MAIL_SENDER},
        "to":          [{"email": to_email, "name": to_name or to_email}],
        "subject":     "Your DocTracker Account — Login Credentials",
        "htmlContent": html_body,
        "textContent": (
            f"{greeting}\n\nYour DocTracker account has been created.\n\n"
            f"Username: {username}\nTemporary Password: {password}\n\n"
            f"Log in at: {login_url}\n\nPlease change your password after first login."
        ),
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
        return True, ""
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