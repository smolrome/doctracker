"""
tests/test_password_reset_routes.py — Checkpoint B: the user-facing self-service
password reset flow (/forgot-password + /reset-password/<token>).

The security property under test is NO ENUMERATION: the request-reset response
must be byte-for-byte identical whether the email exists, doesn't exist, has no
email on file, or is rate-limited. The reset page must re-verify the token on
POST and single-use it.

Tests run against the JSON backend (conftest forces DATABASE_URL="").
"""

import os
import pytest

from services.auth import create_user, verify_user
from services import password_reset as pr


def _csrf(client):
    client.get("/login")
    with client.session_transaction() as s:
        return s.get("csrf_token", "")


@pytest.fixture(autouse=True)
def _reset_rate_state(app):
    """Clear the JSON rate-limit store before each test so per-email/IP counters
    from a previous test don't bleed in (the app fixture chdirs into a temp dir)."""
    import os as _os
    for f in (pr._RATE_JSON, pr._TOKENS_JSON):
        if _os.path.exists(f):
            _os.remove(f)
    yield


# ── 1 & 2. No enumeration: real vs non-existent email → identical response ───────

def test_forgot_password_real_email_generic_response_and_sends(app, monkeypatch):
    create_user("realuser", "OldPass123", role="staff", email="real@example.com")

    sent = {}
    monkeypatch.setattr("routes.auth.send_email",
                        lambda *a, **k: sent.setdefault("called", True) or (True, ""))

    c = app.test_client()
    csrf = _csrf(c)
    rv = c.post("/forgot-password",
                data={"email": "real@example.com", "csrf_token": csrf})

    assert rv.status_code == 200
    # A token was created for the user...
    tokens = pr._load_tokens_json()
    assert any(rec["username"] == "realuser" for rec in tokens.values())
    # ...and the email was sent.
    assert sent.get("called") is True
    # Stash the body for the enumeration comparison in the next test.
    test_forgot_password_real_email_generic_response_and_sends.body = rv.data


def test_forgot_password_unknown_email_is_identical_and_silent(app, monkeypatch):
    create_user("realuser", "OldPass123", role="staff", email="real@example.com")

    sent = {}
    monkeypatch.setattr("routes.auth.send_email",
                        lambda *a, **k: sent.setdefault("called", True) or (True, ""))

    # First get the response for a REAL email (baseline)
    c1 = app.test_client()
    real = c1.post("/forgot-password",
                   data={"email": "real@example.com", "csrf_token": _csrf(c1)})

    # Now an UNKNOWN email
    sent.clear()
    c2 = app.test_client()
    unknown = c2.post("/forgot-password",
                      data={"email": "nobody@nowhere.com", "csrf_token": _csrf(c2)})

    # Identical status + body → no enumeration
    assert unknown.status_code == real.status_code == 200
    assert unknown.data == real.data
    # No token created for the unknown address, no email sent
    tokens = pr._load_tokens_json()
    assert not any(rec["username"] == "nobody@nowhere.com" for rec in tokens.values())
    assert "called" not in sent


# ── 3. Rate-limited → SAME generic response (no "too many requests" leak) ────────

def test_forgot_password_rate_limited_same_response(app, monkeypatch):
    create_user("rluser", "OldPass123", role="staff", email="rl@example.com")
    monkeypatch.setattr("routes.auth.send_email", lambda *a, **k: (True, ""))

    email_max = pr.PASSWORD_RESET_RATE_LIMITS["email"]["max"]

    baseline = None
    responses = []
    # Fire well past the per-email limit
    for _ in range(email_max + 3):
        c = app.test_client()
        rv = c.post("/forgot-password",
                    data={"email": "rl@example.com", "csrf_token": _csrf(c)})
        responses.append(rv)

    # Every response — allowed AND throttled — is identical (status + body)
    first = responses[0]
    for rv in responses:
        assert rv.status_code == first.status_code == 200
        assert rv.data == first.data
    assert b"too many" not in first.data.lower()
    assert b"rate" not in first.data.lower()


# ── 4. GET reset page: valid token shows form; invalid shows friendly message ────

def test_reset_get_valid_token_shows_form(app):
    create_user("gettest", "OldPass123", role="staff", email="g@example.com")
    raw = pr.create_reset_token("gettest")

    c = app.test_client()
    rv = c.get(f"/reset-password/{raw}")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert 'name="password"' in body
    assert 'name="confirm_password"' in body


def test_reset_get_invalid_token_shows_message(app):
    c = app.test_client()
    rv = c.get("/reset-password/not-a-real-token")
    assert rv.status_code == 200
    body = rv.data.decode().lower()
    assert "invalid or has expired" in body


# ── 5. POST valid new password → updated, consumed, redirect; reuse rejected ─────

def test_reset_post_sets_password_consumes_and_redirects(app):
    create_user("settest", "OldPass123", role="staff", email="s@example.com")
    raw = pr.create_reset_token("settest")

    c = app.test_client()
    csrf = _csrf(c)
    rv = c.post(f"/reset-password/{raw}",
                data={"password": "BrandNewPass1", "confirm_password": "BrandNewPass1",
                      "csrf_token": csrf})
    # Redirect to login
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]

    # New password works via the real login path
    full_name, role, office = verify_user("settest", "BrandNewPass1")
    assert role == "staff"

    # Token is consumed — reuse is rejected (GET now shows invalid message)
    assert pr.verify_reset_token(raw) is None
    c2 = app.test_client()
    reuse = c2.post(f"/reset-password/{raw}",
                    data={"password": "AnotherPass9", "confirm_password": "AnotherPass9",
                          "csrf_token": _csrf(c2)})
    assert reuse.status_code == 200
    assert "invalid or has expired" in reuse.data.decode().lower()
    # Password did NOT change to the reuse attempt
    assert verify_user("settest", "AnotherPass9")[1] is None


# ── 6. Mismatched / too-short password → rejected, token NOT consumed ────────────

def test_reset_post_mismatch_does_not_consume_token(app):
    create_user("mismatch", "OldPass123", role="staff", email="m@example.com")
    raw = pr.create_reset_token("mismatch")

    c = app.test_client()
    rv = c.post(f"/reset-password/{raw}",
                data={"password": "GoodPass111", "confirm_password": "DifferentPass2",
                      "csrf_token": _csrf(c)})
    assert rv.status_code == 200
    assert "do not match" in rv.data.decode().lower()
    # Token still valid — user can retry
    assert pr.verify_reset_token(raw) == "mismatch"


def test_reset_post_too_short_does_not_consume_token(app):
    create_user("shortpw", "OldPass123", role="staff", email="sp@example.com")
    raw = pr.create_reset_token("shortpw")

    c = app.test_client()
    rv = c.post(f"/reset-password/{raw}",
                data={"password": "short", "confirm_password": "short",
                      "csrf_token": _csrf(c)})
    assert rv.status_code == 200
    assert "at least 8" in rv.data.decode().lower()
    # Not consumed
    assert pr.verify_reset_token(raw) == "shortpw"


# ── 7. User with NO email → generic response, no crash, no email ─────────────────

def test_forgot_password_user_without_email(app, monkeypatch):
    # Client accounts frequently have no email on file
    create_user("noemailclient", "OldPass123", role="client", email="")

    sent = {}
    monkeypatch.setattr("routes.auth.send_email",
                        lambda *a, **k: sent.setdefault("called", True) or (True, ""))

    c = app.test_client()
    rv = c.post("/forgot-password",
                data={"email": "", "csrf_token": _csrf(c)})
    assert rv.status_code == 200
    # No email sent, no token created, no crash
    assert "called" not in sent
    tokens = pr._load_tokens_json()
    assert not any(rec["username"] == "noemailclient" for rec in tokens.values())


# ── Login page wiring ────────────────────────────────────────────────────────────

def test_login_page_has_forgot_link(app):
    c = app.test_client()
    rv = c.get("/login")
    assert rv.status_code == 200
    assert "/forgot-password" in rv.data.decode()


def test_mail_failure_does_not_500_or_change_response(app, monkeypatch):
    create_user("mailfail", "OldPass123", role="staff", email="mf@example.com")
    # send_email raises — route must swallow it and still return the generic page
    def _boom(*a, **k):
        raise RuntimeError("SMTP down")
    monkeypatch.setattr("routes.auth.send_email", _boom)

    c = app.test_client()
    rv = c.post("/forgot-password",
                data={"email": "mf@example.com", "csrf_token": _csrf(c)})
    assert rv.status_code == 200
    assert b"a reset link has been sent" in rv.data
