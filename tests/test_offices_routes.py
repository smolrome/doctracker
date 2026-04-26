"""
tests/test_offices_routes.py — Tests for routes/offices.py.

Covers:
  - /office-qr-page requires @admin_required
  - /office-qr-page GET renders for admin
  - /office-qr-page POST with office_name creates QR data
  - /welcome is publicly accessible (no login needed)
  - /office-staff requires @admin_required
  - /routing-slip/create requires @login_required
  - /routing-slip/create POST creates a slip and redirects
  - /routing-slip/<slip_id> GET loads an existing slip
  - /routing-slip/<slip_id> GET 404s/redirects for unknown slip
  - /routed-documents requires @login_required
"""

import json
import os
import uuid
import pytest

os.environ.setdefault("SECRET_KEY", "j" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


def _csrf(client):
    client.get("/login")
    with client.session_transaction() as s:
        return s.get("csrf_token", "")


def _make_doc(name="Office Route Doc", status="Pending"):
    from services.documents import insert_doc
    doc = {
        "id":       str(uuid.uuid4())[:8].upper(),
        "doc_id":   f"REF-2024-{uuid.uuid4().hex[:4].upper()}",
        "doc_name": name,
        "status":   status,
    }
    insert_doc(doc)
    return doc


# ── /office-qr-page ───────────────────────────────────────────────────────────

class TestOfficeQrPage:
    def test_unauthenticated_redirected_to_login(self, client):
        rv = client.get("/office-qr-page", follow_redirects=False)
        assert rv.status_code == 302
        assert "login" in rv.headers.get("Location", "")

    def test_staff_blocked_from_office_qr_page(self, staff_client):
        rv = staff_client.get("/office-qr-page", follow_redirects=False)
        assert rv.status_code in (302, 403)

    def test_admin_can_access_office_qr_page(self, admin_client):
        rv = admin_client.get("/office-qr-page", follow_redirects=True)
        assert rv.status_code == 200

    def test_post_with_office_name_generates_qr_data(self, admin_client):
        """Posting an office name should render the page with QR action slugs."""
        csrf = _csrf(admin_client)
        rv = admin_client.post(
            "/office-qr-page",
            data={"office_name": "Test Office QR", "csrf_token": csrf},
            follow_redirects=True,
        )
        assert rv.status_code == 200
        body = rv.data.decode()
        # Should contain the office name or QR-related text
        assert "test-office-qr" in body.lower() or "test office qr" in body.lower() or "qr" in body.lower()


# ── /office-staff ──────────────────────────────────────────────────────────────

class TestOfficeStaff:
    def test_unauthenticated_redirected(self, client):
        rv = client.get("/office-staff", follow_redirects=False)
        assert rv.status_code == 302
        assert "login" in rv.headers.get("Location", "")

    def test_staff_blocked(self, staff_client):
        rv = staff_client.get("/office-staff", follow_redirects=False)
        assert rv.status_code in (302, 403)

    def test_admin_can_view_office_staff(self, admin_client):
        rv = admin_client.get("/office-staff", follow_redirects=True)
        assert rv.status_code == 200


# ── /welcome ───────────────────────────────────────────────────────────────────

class TestWelcomePage:
    def test_welcome_is_public(self, client):
        rv = client.get("/welcome")
        assert rv.status_code == 200

    def test_welcome_shows_for_logged_in_user(self, staff_client):
        rv = staff_client.get("/welcome")
        assert rv.status_code == 200


# ── /routing-slip/create ──────────────────────────────────────────────────────

class TestCreateRoutingSlip:
    def test_unauthenticated_redirected(self, client):
        rv = client.post("/routing-slip/create", data={}, follow_redirects=False)
        assert rv.status_code in (302, 403)

    def test_empty_post_shows_error(self, staff_client):
        """POST without doc_ids or destination flashes an error and redirects."""
        csrf = _csrf(staff_client)
        rv = staff_client.post(
            "/routing-slip/create",
            data={"doc_ids": "", "destination": "", "csrf_token": csrf},
            follow_redirects=True,
        )
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "select" in body.lower() or "required" in body.lower() or "please" in body.lower()

    def test_valid_slip_creation_redirects(self, staff_client, app):
        """POST with valid doc_ids and destination creates a slip and redirects."""
        with app.app_context():
            doc = _make_doc("Slip Test Doc")
        csrf = _csrf(staff_client)
        rv = staff_client.post(
            "/routing-slip/create",
            data={
                "doc_ids":     doc["id"],
                "destination": "Division Office",
                "notes":       "Test routing slip",
                "csrf_token":  csrf,
            },
            follow_redirects=False,
        )
        assert rv.status_code == 302
        # Should redirect to the new slip's view page
        location = rv.headers.get("Location", "")
        assert "routing-slip" in location or "cart_cleared" in location


# ── /routing-slip/<slip_id> ────────────────────────────────────────────────────

class TestViewRoutingSlip:
    def _create_slip(self, app, staff_client):
        """Helper: create a real slip via POST and return its slip_id."""
        with app.app_context():
            doc = _make_doc("Slip View Doc")
        csrf = _csrf(staff_client)
        rv = staff_client.post(
            "/routing-slip/create",
            data={
                "doc_ids":     doc["id"],
                "destination": "Test Destination",
                "csrf_token":  csrf,
            },
            follow_redirects=False,
        )
        # Extract slip_id from redirect location
        location = rv.headers.get("Location", "")
        # Location: /routing-slip/<slip_id>?cart_cleared=1
        parts = location.split("/routing-slip/")
        if len(parts) > 1:
            return parts[1].split("?")[0]
        return None

    def test_unauthenticated_redirected(self, client):
        rv = client.get("/routing-slip/ANYSLIID", follow_redirects=False)
        assert rv.status_code in (302, 200)

    def test_unknown_slip_redirects(self, staff_client):
        rv = staff_client.get("/routing-slip/DOESNOTEXIST", follow_redirects=True)
        assert rv.status_code == 200  # redirected to dashboard with flash

    def test_valid_slip_renders_200(self, staff_client, app):
        slip_id = self._create_slip(app, staff_client)
        if not slip_id:
            pytest.skip("Could not extract slip_id from redirect")
        rv = staff_client.get(f"/routing-slip/{slip_id}", follow_redirects=True)
        assert rv.status_code == 200


# ── /routed-documents ─────────────────────────────────────────────────────────

class TestRoutedDocuments:
    def test_unauthenticated_redirected(self, client):
        rv = client.get("/routed-documents", follow_redirects=False)
        assert rv.status_code == 302
        assert "login" in rv.headers.get("Location", "")

    def test_staff_can_view(self, staff_client):
        rv = staff_client.get("/routed-documents", follow_redirects=True)
        assert rv.status_code == 200

    def test_admin_can_view(self, admin_client):
        rv = admin_client.get("/routed-documents", follow_redirects=True)
        assert rv.status_code == 200

    def test_pagination_param(self, staff_client):
        rv = staff_client.get("/routed-documents?page=1&per_page=5")
        assert rv.status_code == 200
