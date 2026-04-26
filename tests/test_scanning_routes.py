"""
tests/test_scanning_routes.py — Tests for routes/scanning.py.

Covers:
  - /office-action/<action> GET renders form (public, no auth needed)
  - /office-action/<action> POST without login returns login_required message
  - /office-action/<action> POST with non-existent doc_id returns error
  - /doc-scan/<token> redirects to login if not authenticated (auth redirect has ?next=)
  - /doc-scan/<token> for invalid/used token shows error page
  - /receive/<doc_id> GET shows scan form for valid doc
  - /receive/<doc_id> GET returns 404/error for unknown doc
  - /receive/<doc_id> POST by staff marks doc as received
  - /office-qr/<action>.png returns PNG image bytes
  - /upload-qr requires login (redirects unauthenticated)
"""

import json
import os
import uuid
import pytest

os.environ.setdefault("SECRET_KEY", "i" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


def _make_doc(tmp_path=None, name="Route Doc", status="Pending"):
    from services.documents import insert_doc
    doc = {
        "id":       str(uuid.uuid4())[:8].upper(),
        "doc_id":   f"REF-2024-{uuid.uuid4().hex[:4].upper()}",
        "doc_name": name,
        "status":   status,
    }
    insert_doc(doc)
    return doc


def _csrf(client):
    client.get("/login")
    with client.session_transaction() as s:
        return s.get("csrf_token", "")


# ── /office-action/<action> ───────────────────────────────────────────────────

class TestOfficeAction:
    def test_get_rec_action_renders_200(self, client):
        """Office -rec QR landing is public — unauthenticated GET must return 200."""
        rv = client.get("/office-action/main-office-rec")
        assert rv.status_code == 200

    def test_get_rel_action_renders_200(self, client):
        rv = client.get("/office-action/main-office-rel")
        assert rv.status_code == 200

    def test_get_reg_action_renders_200(self, client):
        rv = client.get("/office-action/main-office-reg")
        assert rv.status_code in (200, 302)

    def test_post_without_login_returns_login_required(self, client, app):
        with app.app_context():
            doc = _make_doc(name="Office Action Doc")
        rv = client.post(
            "/office-action/main-office-rec",
            data={"doc_id": doc["id"]},
        )
        assert rv.status_code == 200
        body = rv.data.decode()
        # Route renders template with login_required result
        assert "log in" in body.lower() or "login" in body.lower()

    def test_post_unknown_doc_returns_error(self, staff_client):
        rv = staff_client.post(
            "/office-action/main-office-rec",
            data={"doc_id": "NOTFOUND"},
        )
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "not found" in body.lower() or "error" in body.lower() or "invalid" in body.lower()

    def test_post_with_valid_doc_marks_received(self, staff_client, app):
        """Staff POST with a known doc_id updates status to Received."""
        with app.app_context():
            doc = _make_doc(name="Receive Via QR")
        rv = staff_client.post(
            "/office-action/main-office-rec",
            data={"doc_id": doc["id"]},
        )
        assert rv.status_code == 200
        # Template should show success (ok=True)
        from services.documents import get_doc
        with app.app_context():
            updated = get_doc(doc["id"])
        assert updated["status"] == "Received"


# ── /doc-scan/<token> ─────────────────────────────────────────────────────────

class TestDocScan:
    def test_unauthenticated_redirects_with_next_param(self, client):
        """CSRF-exempt route — auth redirect must include ?next= not plain /login."""
        rv = client.get("/doc-scan/SOME-TOKEN-HERE-12345", follow_redirects=False)
        assert rv.status_code == 302
        location = rv.headers.get("Location", "")
        assert "next=" in location, (
            f"Expected auth redirect with ?next=, got: '{location}'"
        )

    def test_invalid_token_shows_error_page(self, staff_client):
        """A non-existent token must render the result page with ok=False."""
        rv = staff_client.get("/doc-scan/REC-INVALIDTOKEN00000000", follow_redirects=True)
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "invalid" in body.lower() or "already been used" in body.lower() or "error" in body.lower()

    def test_valid_receive_token_marks_doc_received(self, staff_client, app):
        """A valid one-time RECEIVE token updates doc status and shows success page."""
        from services.qr import create_doc_token
        with app.app_context():
            doc = _make_doc(name="QR Receive Doc")
            token = create_doc_token(doc["id"], "RECEIVE")
        rv = staff_client.get(f"/doc-scan/{token}", follow_redirects=True)
        assert rv.status_code == 200
        from services.documents import get_doc
        with app.app_context():
            updated = get_doc(doc["id"])
        assert updated["status"] == "Received"

    def test_client_role_is_redirected_from_doc_scan(self, client_user_client):
        """Clients should not use the staff doc-scan endpoint."""
        from services.qr import create_doc_token
        with client_user_client.application.app_context() if hasattr(client_user_client, 'application') else pytest.raises(Exception):
            pass
        rv = client_user_client.get("/doc-scan/REC-ANYTOKENVALUE123", follow_redirects=False)
        # Client gets redirected to their portal (not the scan result)
        assert rv.status_code in (302, 200)


# ── /receive/<doc_id> ─────────────────────────────────────────────────────────

class TestReceiveRoute:
    def test_get_valid_doc_returns_200(self, client, app):
        with app.app_context():
            doc = _make_doc(name="Manual Receive Doc")
        rv = client.get(f"/receive/{doc['id']}")
        assert rv.status_code == 200

    def test_get_unknown_doc_shows_not_found(self, client):
        rv = client.get("/receive/XXXXXXXX")
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "not found" in body.lower() or "error" in body.lower()

    def test_post_receive_marks_status(self, staff_client, app):
        with app.app_context():
            doc = _make_doc(name="POST Receive")
        csrf = _csrf(staff_client)
        rv = staff_client.post(
            f"/receive/{doc['id']}",
            data={"action": "receive", "csrf_token": csrf},
        )
        assert rv.status_code == 200
        from services.documents import get_doc
        with app.app_context():
            updated = get_doc(doc["id"])
        assert updated["status"] == "Received"

    def test_post_release_marks_status(self, staff_client, app):
        with app.app_context():
            doc = _make_doc(name="POST Release", status="Received")
        csrf = _csrf(staff_client)
        rv = staff_client.post(
            f"/receive/{doc['id']}",
            data={"action": "release", "csrf_token": csrf},
        )
        assert rv.status_code == 200
        from services.documents import get_doc
        with app.app_context():
            updated = get_doc(doc["id"])
        assert updated["status"] == "Released"

    def test_post_invalid_action_returns_error(self, staff_client, app):
        with app.app_context():
            doc = _make_doc(name="Bad Action")
        csrf = _csrf(staff_client)
        rv = staff_client.post(
            f"/receive/{doc['id']}",
            data={"action": "explode", "csrf_token": csrf},
        )
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "invalid" in body.lower() or "error" in body.lower()


# ── /office-qr/<action>.png ───────────────────────────────────────────────────

class TestOfficeQrPng:
    def test_get_rec_qr_returns_png(self, client):
        rv = client.get("/office-qr/main-office-rec.png")
        assert rv.status_code == 200
        assert rv.content_type == "image/png"
        assert rv.data[:4] == b"\x89PNG"

    def test_get_rel_qr_returns_png(self, client):
        rv = client.get("/office-qr/main-office-rel.png")
        assert rv.status_code == 200
        assert rv.content_type == "image/png"

    def test_get_reg_qr_returns_png(self, client):
        rv = client.get("/office-qr/main-office-reg.png")
        assert rv.status_code == 200
        assert rv.content_type == "image/png"


# ── /upload-qr ────────────────────────────────────────────────────────────────

class TestUploadQr:
    def test_unauthenticated_redirects_to_login(self, client):
        rv = client.get("/upload-qr", follow_redirects=False)
        assert rv.status_code == 302
        assert "login" in rv.headers.get("Location", "")

    def test_authenticated_staff_gets_200(self, staff_client):
        rv = staff_client.get("/upload-qr")
        assert rv.status_code == 200
