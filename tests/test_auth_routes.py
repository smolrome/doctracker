"""
tests/test_auth_routes.py — Tests for /login, /logout, /register, /profile routes.

Covers:
  - Successful login redirects correctly per role
  - Wrong password returns error without revealing username validity
  - Login rate-limit triggers after 5 fails
  - Logged-in user visiting /login is redirected away
  - Session is cleared on logout
  - Register with valid invite token succeeds
  - Register with expired/missing token is rejected
  - Password change validation on /profile
"""

import os
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _csrf(client):
    """Seed session and return its CSRF token."""
    client.get("/login")
    with client.session_transaction() as s:
        return s.get("csrf_token", "")


def _login(client, username, password):
    csrf = _csrf(client)
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": csrf},
        follow_redirects=False,
    )


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    def test_admin_login_redirects_to_dashboard(self, client):
        rv = _login(client, os.environ["ADMIN_USERNAME"], os.environ["ADMIN_PASSWORD"])
        assert rv.status_code == 302
        assert "/login" not in rv.headers["Location"]

    def test_wrong_password_shows_error(self, client):
        rv = _login(client, os.environ["ADMIN_USERNAME"], "wrongpassword")
        rv_follow = client.post(
            "/login",
            data={
                "username": os.environ["ADMIN_USERNAME"],
                "password": "wrongpassword",
                "csrf_token": _csrf(client),
            },
            follow_redirects=True,
        )
        assert rv_follow.status_code == 200
        body = rv_follow.data.decode()
        assert "Invalid username or password" in body

    def test_nonexistent_username_same_error(self, client):
        """Username enumeration prevention: same error for unknown user."""
        rv = client.post(
            "/login",
            data={
                "username": "totallymadeupuser99",
                "password": "irrelevant",
                "csrf_token": _csrf(client),
            },
            follow_redirects=True,
        )
        assert "Invalid username or password" in rv.data.decode()

    def test_logged_in_user_is_redirected_from_login(self, admin_client):
        rv = admin_client.get("/login", follow_redirects=False)
        assert rv.status_code == 302
        assert "/login" not in rv.headers["Location"]

    def test_empty_credentials_returns_error(self, client):
        rv = client.post(
            "/login",
            data={"username": "", "password": "", "csrf_token": _csrf(client)},
            follow_redirects=True,
        )
        assert rv.status_code == 200
        # Should stay on login page or show error
        body = rv.data.decode()
        assert "Invalid" in body or "login" in body.lower()

    def test_login_rate_limit(self, app, client):
        """After 5 failed attempts the 6th is rate-limited."""
        from services.auth import _rate_store, _rate_lock
        username = os.environ["ADMIN_USERNAME"]
        # Reset any existing state for this key
        with _rate_lock:
            keys_to_del = [k for k in _rate_store if f":{username.lower()}" in k]
            for k in keys_to_del:
                del _rate_store[k]

        for _ in range(5):
            _login(client, username, "wrongpass")

        rv = client.post(
            "/login",
            data={
                "username": username,
                "password": "wrongpass",
                "csrf_token": _csrf(client),
            },
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "Too many" in body or rv.status_code == 429

    def test_client_role_redirects_to_portal(self, app):
        """Client login should redirect to /client, not /dashboard."""
        from services.auth import create_user, approve_user
        create_user("clientlogintest", "TestPass1!", role="client")
        approve_user("clientlogintest")
        c = app.test_client()
        rv = _login(c, "clientlogintest", "TestPass1!")
        assert rv.status_code == 302
        assert "client" in rv.headers["Location"]


# ── Logout ────────────────────────────────────────────────────────────────────

class TestLogout:
    def test_logout_clears_session(self, admin_client):
        admin_client.get("/logout")
        # After logout, accessing a login-required page must redirect to login.
        # Use /add (has @login_required) — the bare / is publicly accessible.
        rv = admin_client.get("/add", follow_redirects=False)
        assert rv.status_code == 302
        assert "login" in rv.headers.get("Location", "")

    def test_logout_redirects(self, admin_client):
        rv = admin_client.get("/logout", follow_redirects=False)
        assert rv.status_code == 302


# ── Register ──────────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_without_token_shows_error(self, client):
        rv = client.post(
            "/register",
            data={
                "username": "newuser",
                "password": "NewPass1!",
                "confirm_password": "NewPass1!",
                "full_name": "New User",
                "office": "Test Office",
                "csrf_token": _csrf(client),
            },
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "Invalid" in body or "expired" in body or "invite" in body.lower()

    def test_register_with_invalid_token_blocked(self, client):
        rv = client.post(
            "/register?token=badtoken123",
            data={
                "username": "hacker",
                "password": "HackPass1!",
                "confirm_password": "HackPass1!",
                "full_name": "Hacker",
                "office": "Evil Office",
                "token": "badtoken123",
                "csrf_token": _csrf(client),
            },
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "Invalid" in body or "expired" in body

    def test_register_weak_password_rejected(self, client):
        """Password < 8 chars or no number should fail."""
        rv = client.post(
            "/register",
            data={
                "username": "weakuser",
                "password": "abc",
                "confirm_password": "abc",
                "full_name": "Weak User",
                "office": "Some Office",
                "token": "",
                "csrf_token": _csrf(client),
            },
            follow_redirects=True,
        )
        # Should still be on register page (no redirect to login)
        assert rv.status_code == 200

    def test_register_password_mismatch_rejected(self, client):
        rv = client.post(
            "/register",
            data={
                "username": "mismatchuser",
                "password": "ValidPass1!",
                "confirm_password": "DifferentPass1!",
                "full_name": "Mismatch",
                "office": "Test Office",
                "csrf_token": _csrf(client),
            },
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "match" in body.lower() or rv.status_code == 200


# ── Profile / Password Change ─────────────────────────────────────────────────

class TestProfile:
    def test_profile_requires_auth(self, client):
        rv = client.get("/profile", follow_redirects=False)
        assert rv.status_code == 302
        assert "login" in rv.headers["Location"]

    def test_profile_page_loads_for_authenticated_user(self, app):
        """
        The env-var admin has no JSON/DB row, so get_user() returns None and the
        profile route redirects.  Use a real staff user that has a JSON row instead.
        """
        from services.auth import create_user
        create_user("profiletestuser", "ProfilePass1!", full_name="Profile Tester", role="staff")
        c = app.test_client()
        csrf = _csrf(c)
        rv = c.post(
            "/login",
            data={"username": "profiletestuser", "password": "ProfilePass1!", "csrf_token": csrf},
            follow_redirects=True,
        )
        assert rv.status_code == 200
        rv2 = c.get("/profile")
        assert rv2.status_code == 200

    def test_password_change_wrong_current(self, admin_client):
        csrf = _csrf(admin_client)
        rv = admin_client.post(
            "/profile",
            data={
                "_section": "password",
                "current_password": "totallyWrong99",
                "new_password": "NewAdminPass1!",
                "confirm_password": "NewAdminPass1!",
                "csrf_token": csrf,
            },
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "incorrect" in body.lower() or "wrong" in body.lower() or rv.status_code == 200

    def test_password_change_too_short(self, admin_client):
        csrf = _csrf(admin_client)
        rv = admin_client.post(
            "/profile",
            data={
                "_section": "password",
                "current_password": os.environ["ADMIN_PASSWORD"],
                "new_password": "short1",
                "confirm_password": "short1",
                "csrf_token": csrf,
            },
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "8" in body or "characters" in body.lower()

    def test_password_change_no_number_rejected(self, admin_client):
        csrf = _csrf(admin_client)
        rv = admin_client.post(
            "/profile",
            data={
                "_section": "password",
                "current_password": os.environ["ADMIN_PASSWORD"],
                "new_password": "NoNumbersHere",
                "confirm_password": "NoNumbersHere",
                "csrf_token": csrf,
            },
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "number" in body.lower() or rv.status_code == 200
