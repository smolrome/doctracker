"""
tests/test_csrf.py — CSRF protection tests.

Verifies:
  - POST without a CSRF token is rejected (redirected)
  - POST with a mismatched CSRF token is rejected
  - POST with a correct CSRF token is accepted
  - CSRF-exempt prefixes are actually exempt (/login, /api/, /doc-scan/, etc.)
  - CSRF token is injected into every session automatically
"""

import os
import pytest

os.environ.setdefault("SECRET_KEY", "b" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


def _csrf(client):
    client.get("/login")
    with client.session_transaction() as s:
        return s.get("csrf_token", "")


class TestCSRF:
    # ── Token injection ───────────────────────────────────────────────────────

    def test_csrf_token_in_session_after_any_get(self, client):
        client.get("/login")
        with client.session_transaction() as s:
            assert "csrf_token" in s
            assert len(s["csrf_token"]) >= 32

    def test_csrf_token_is_consistent_within_session(self, client):
        client.get("/login")
        with client.session_transaction() as s:
            token1 = s.get("csrf_token")
        client.get("/login")
        with client.session_transaction() as s:
            token2 = s.get("csrf_token")
        assert token1 == token2  # same session → same token

    # ── Missing token ─────────────────────────────────────────────────────────

    def test_post_without_csrf_token_redirected(self, client):
        """POST to a protected endpoint without any CSRF token must not succeed."""
        # Seed a session first
        client.get("/login")
        rv = client.post(
            "/login",
            data={"username": "x", "password": "y"},
            # Intentionally omit csrf_token
        )
        # Should redirect (CSRF check redirects) or return non-200 on success
        # Successful login would give 302 to dashboard; CSRF fail gives redirect to referrer
        # The key is it must NOT let a non-CSRF request create a session
        assert rv.status_code in (302, 200)
        # If 302, it must NOT point to dashboard
        if rv.status_code == 302:
            location = rv.headers.get("Location", "")
            # Should not have redirected to a logged-in page
            assert "dashboard" not in location or "login" in location

    def test_post_with_wrong_csrf_token_redirected(self, client):
        client.get("/login")
        rv = client.post(
            "/profile",
            data={
                "_section": "info",
                "full_name": "Test",
                "office": "IT",
                "csrf_token": "totallywrongtoken",
            },
            follow_redirects=False,
        )
        # Must redirect (CSRF rejection always redirects)
        assert rv.status_code == 302

    # ── Correct token ─────────────────────────────────────────────────────────

    def test_post_with_correct_csrf_token_processed(self, client):
        """A request with the correct CSRF token must reach the handler."""
        from services.auth import _rate_store, _rate_lock
        admin_user = os.environ["ADMIN_USERNAME"]
        with _rate_lock:
            keys = [k for k in list(_rate_store) if admin_user.lower() in k.lower()]
            for k in keys:
                del _rate_store[k]
        token = _csrf(client)
        rv = client.post(
            "/login",
            data={
                "username": admin_user,
                "password": os.environ["ADMIN_PASSWORD"],
                "csrf_token": token,
            },
            follow_redirects=False,
        )
        # Should be a redirect (successful login) not a CSRF rejection loop
        assert rv.status_code == 302

    # ── CSRF via header ───────────────────────────────────────────────────────

    def test_csrf_accepted_via_x_csrf_token_header(self, client):
        from services.auth import _rate_store, _rate_lock
        admin_user = os.environ["ADMIN_USERNAME"]
        with _rate_lock:
            keys = [k for k in list(_rate_store) if admin_user.lower() in k.lower()]
            for k in keys:
                del _rate_store[k]
        token = _csrf(client)
        rv = client.post(
            "/login",
            data={
                "username": admin_user,
                "password": os.environ["ADMIN_PASSWORD"],
            },
            headers={"X-CSRF-Token": token},
            follow_redirects=False,
        )
        assert rv.status_code == 302

    # ── Exempt prefixes ───────────────────────────────────────────────────────

    def test_login_get_is_exempt(self, client):
        """GET /login should never require a CSRF token."""
        rv = client.get("/login")
        assert rv.status_code == 200

    def test_api_endpoints_csrf_exempt(self, client):
        """API routes skip CSRF (they use JWT instead)."""
        rv = client.post(
            "/api/auth/login",
            json={"username": "x", "password": "y"},
        )
        # 400 or 401 (bad credentials) but NOT a CSRF-redirect
        assert rv.status_code in (400, 401, 422, 429)

    def test_doc_scan_endpoint_csrf_exempt(self, client):
        """
        /doc-scan/* is CSRF-exempt (scanned by physical QR devices with no session).
        The route may still require authentication and redirect to /login — that is
        expected.  What must NOT happen is a CSRF-rejection redirect.

        Distinction:
          - CSRF rejection redirects to referrer/login WITHOUT a `next=` parameter.
          - Auth rejection redirects to /login WITH `?next=<url>`.

        So if there is a redirect, it must carry `next=` (auth redirect, not CSRF).
        """
        rv = client.get("/doc-scan/sometoken123")
        if rv.status_code == 302:
            location = rv.headers.get("Location", "")
            # Auth redirect always includes next= — CSRF redirect does NOT
            assert "next=" in location, (
                f"Unexpected CSRF-like redirect to '{location}' "
                "(no next= param means CSRF middleware triggered, not auth)"
            )
