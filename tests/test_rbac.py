"""
tests/test_rbac.py — Role-Based Access Control tests.

Verifies that:
  - Unauthenticated users are redirected from protected routes
  - Staff cannot access /admin/* routes
  - Client cannot access /admin/* or staff dashboard
  - Admin can access all routes
  - Open-redirect protection on the ?next= parameter
"""

import os
import pytest

os.environ.setdefault("SECRET_KEY", "c" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


# Admin routes have NO url_prefix — they are registered directly
ADMIN_ONLY_ROUTES = [
    "/manage-users",     # admin_bp route (no /admin/ prefix)
    "/activity-log",     # admin_bp route (no /admin/ prefix)
]

# Routes protected by @login_required (not the bare / which is public)
LOGIN_REQUIRED_ROUTES = [
    "/add",          # create document — has @login_required
    "/dashboard",    # staff dashboard copy — has @login_required
]

CLIENT_ROUTES = [
    "/client",
]


class TestUnauthenticated:
    """Unauthenticated users must be redirected to /login."""

    @pytest.mark.parametrize("path", ADMIN_ONLY_ROUTES + LOGIN_REQUIRED_ROUTES)
    def test_protected_route_redirects_to_login(self, client, path):
        rv = client.get(path, follow_redirects=False)
        assert rv.status_code == 302, f"Expected redirect for {path}, got {rv.status_code}"
        location = rv.headers.get("Location", "")
        assert "login" in location

    def test_unauthenticated_403_redirects_to_login(self, client):
        """Admin-only route redirects unauthenticated user to login."""
        rv = client.get("/manage-users", follow_redirects=True)
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "login" in body.lower() or "sign in" in body.lower()


class TestStaffAccess:
    """Staff can access dashboard but not admin-only routes."""

    def test_staff_can_access_dashboard(self, staff_client):
        """Staff can access the main dashboard (/ is publicly accessible)."""
        rv = staff_client.get("/", follow_redirects=True)
        assert rv.status_code == 200

    def test_staff_can_access_add_doc(self, staff_client):
        """Staff can access the add-document page (requires login)."""
        rv = staff_client.get("/add", follow_redirects=True)
        assert rv.status_code == 200

    @pytest.mark.parametrize("path", ADMIN_ONLY_ROUTES)
    def test_staff_blocked_from_admin_routes(self, staff_client, path):
        """Staff user should be redirected away from admin-only routes."""
        rv = staff_client.get(path, follow_redirects=False)
        assert rv.status_code in (302, 403), \
            f"Staff should not access {path}, got {rv.status_code}"

    def test_staff_blocked_from_admin_after_redirect(self, staff_client):
        """Following the redirect for a staff user on admin route lands them away."""
        rv = staff_client.get("/manage-users", follow_redirects=True)
        # Should end up somewhere that is NOT the manage-users page
        assert rv.status_code == 200
        # Should not show the admin user table markup
        body = rv.data.decode().lower()
        assert "manage users" not in body or "permission" in body or "admin" not in body


class TestClientAccess:
    """Client users can access /client but not admin-only areas."""

    def test_client_can_access_portal(self, client_user_client):
        rv = client_user_client.get("/client", follow_redirects=True)
        assert rv.status_code == 200

    def test_client_blocked_from_add_doc(self, client_user_client):
        """Client should not be able to add staff documents (/add requires staff/admin)."""
        rv = client_user_client.get("/add", follow_redirects=False)
        # /add is now @staff_required — a client is logged in (login_required
        # passes) but must be blocked by the role gate: redirect, never a 200.
        assert rv.status_code in (302, 403)

    @pytest.mark.parametrize("path", ADMIN_ONLY_ROUTES)
    def test_client_blocked_from_admin(self, client_user_client, path):
        """Admin-only routes must redirect clients."""
        rv = client_user_client.get(path, follow_redirects=False)
        assert rv.status_code in (302, 403), \
            f"Client should not access {path}, got {rv.status_code}"


class TestAdminAccess:
    """Admin can access all areas."""

    @pytest.mark.parametrize("path", ADMIN_ONLY_ROUTES)
    def test_admin_can_access_admin_routes(self, admin_client, path):
        rv = admin_client.get(path, follow_redirects=True)
        assert rv.status_code == 200, \
            f"Admin should access {path}, got {rv.status_code}: {rv.data[:200]}"

    def test_admin_can_access_dashboard(self, admin_client):
        rv = admin_client.get("/", follow_redirects=True)
        assert rv.status_code == 200

    def test_admin_can_access_add_doc(self, admin_client):
        rv = admin_client.get("/add", follow_redirects=True)
        assert rv.status_code == 200


class TestStaffSurfaceGate:
    """1b — the remaining staff web surface is gated by staff_required
    (HTML → 302 redirect) and staff_required_json (AJAX → 403 JSON).

    Clients are logged in, so login_required passes; the role gate is what
    must block them. Staff/admin must still get through.
    """

    # ── Clients are blocked ──────────────────────────────────────────────
    def test_client_blocked_from_html_route_redirects(self, client_user_client):
        """An HTML staff route (@staff_required) redirects a client (302)."""
        rv = client_user_client.get("/dashboard", follow_redirects=False)
        assert rv.status_code == 302, f"Expected redirect, got {rv.status_code}"

    def test_client_blocked_from_json_get_route(self, client_user_client):
        """A JSON GET route (@staff_required_json) returns 403 JSON, not a redirect."""
        rv = client_user_client.get("/pending-count", follow_redirects=False)
        assert rv.status_code == 403, f"Expected 403, got {rv.status_code}"
        assert rv.is_json, f"Expected JSON body, got {rv.content_type}"
        assert "error" in rv.get_json()

    def test_client_blocked_from_json_post_route(self, client_user_client):
        """A JSON POST route (@staff_required_json) returns 403 JSON for a client.

        A valid CSRF token is supplied so the app's csrf_check before_request
        (which 302-redirects token-less POSTs) is passed and the request reaches
        the RBAC gate. The gate fires before the handler, so a non-existent doc
        id is fine.
        """
        # Login clears the session; the CSRF token is only re-seeded by the
        # ensurecsrf_token before_request on the next request, so hit a GET
        # first, then read the freshly seeded token.
        client_user_client.get("/client")
        with client_user_client.session_transaction() as s:
            csrf = s.get("csrf_token", "")
        rv = client_user_client.post(
            "/accept-document/nonexistent",
            headers={"X-CSRF-Token": csrf},
            follow_redirects=False,
        )
        assert rv.status_code == 403, f"Expected 403, got {rv.status_code}"
        assert rv.is_json, f"Expected JSON body, got {rv.content_type}"
        assert "error" in rv.get_json()

    # ── transfer_doc — the content-negotiating inline gate ───────────────
    def test_client_blocked_from_transfer_ajax_gets_json_403(self, client_user_client):
        """transfer_doc: an AJAX client request gets 403 JSON with ok=False."""
        rv = client_user_client.get(
            "/transfer/nonexistent",
            headers={"X-Requested-With": "XMLHttpRequest"},
            follow_redirects=False,
        )
        assert rv.status_code == 403, f"Expected 403, got {rv.status_code}"
        assert rv.is_json, f"Expected JSON body, got {rv.content_type}"
        assert rv.get_json().get("ok") is False

    def test_client_blocked_from_transfer_non_ajax_redirects(self, client_user_client):
        """transfer_doc: a non-AJAX client request redirects (302), not JSON."""
        rv = client_user_client.get("/transfer/nonexistent", follow_redirects=False)
        assert rv.status_code == 302, f"Expected redirect, got {rv.status_code}"

    # ── Staff / admin still succeed ──────────────────────────────────────
    def test_staff_allowed_on_html_route(self, staff_client):
        """Staff still reach an HTML staff route (200)."""
        rv = staff_client.get("/dashboard", follow_redirects=True)
        assert rv.status_code == 200

    def test_staff_allowed_on_json_route(self, staff_client):
        """Staff still reach a JSON staff route (200 JSON)."""
        rv = staff_client.get("/pending-count", follow_redirects=False)
        assert rv.status_code == 200
        assert rv.is_json

    def test_admin_allowed_on_json_route(self, admin_client):
        """The env-var admin (no users row) still reaches a JSON staff route (200)."""
        rv = admin_client.get("/pending-count", follow_redirects=False)
        assert rv.status_code == 200
        assert rv.is_json


class TestOpenRedirectProtection:
    """The ?next= parameter must not redirect to external URLs."""

    def _login_with_next(self, client, next_url):
        client.get("/login")
        with client.session_transaction() as s:
            csrf = s.get("csrf_token", "")
        return client.post(
            f"/login?next={next_url}",
            data={
                "username": os.environ["ADMIN_USERNAME"],
                "password": os.environ["ADMIN_PASSWORD"],
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

    def test_external_next_url_ignored(self, client):
        rv = self._login_with_next(client, "https://evil.com/steal")
        location = rv.headers.get("Location", "")
        assert "evil.com" not in location

    def test_scheme_only_next_url_ignored(self, client):
        rv = self._login_with_next(client, "javascript:alert(1)")
        location = rv.headers.get("Location", "")
        assert "javascript" not in location

    def test_valid_relative_next_url_allowed(self, client):
        from services.auth import _rate_store, _rate_lock
        admin_user = os.environ["ADMIN_USERNAME"]
        with _rate_lock:
            keys = [k for k in list(_rate_store) if admin_user.lower() in k.lower()]
            for k in keys:
                del _rate_store[k]
        rv = self._login_with_next(client, "/add")
        assert rv.status_code == 302, f"Login should redirect, got {rv.status_code}"
        location = rv.headers.get("Location", "")
        # Must be a local path — must not contain an external domain
        assert "evil" not in location
        assert location.startswith("/") or location.startswith("http://localhost")
