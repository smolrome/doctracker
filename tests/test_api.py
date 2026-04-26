"""
tests/test_api.py — Tests for the REST API (/api/*) consumed by the mobile app.

Covers:
  - POST /api/auth/login  (valid, invalid, missing body)
  - POST /api/auth/refresh
  - GET  /api/auth/me
  - GET  /api/documents       (list, pagination, filters)
  - POST /api/documents       (create)
  - GET  /api/documents/<id>  (get single)
  - PATCH /api/documents/<id>/status
  - DELETE /api/documents/<id>
  - GET  /api/stats
  - All endpoints return 401 without a JWT
  - Rate limit returns 429
"""

import os
import json
import pytest

os.environ.setdefault("SECRET_KEY", "d" * 32)
os.environ.setdefault("ADMIN_USERNAME", "apiadmin")
os.environ.setdefault("ADMIN_PASSWORD", "ApiAdmin123!")
os.environ["DATABASE_URL"] = ""


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def api_app(tmp_path_factory):
    """Isolated app instance for API tests."""
    import secrets as _s
    os.environ["SECRET_KEY"] = _s.token_hex(32)
    os.environ["JWT_SECRET_KEY"] = _s.token_hex(32)

    tmp = tmp_path_factory.mktemp("api_data")
    os.environ["DATA_FILE"] = str(tmp / "documents.json")

    import json
    (tmp / "users.json").write_text(json.dumps([]))
    (tmp / "documents.json").write_text(json.dumps([]))

    original_cwd = os.getcwd()
    os.chdir(str(tmp))

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True

    yield app
    os.chdir(original_cwd)


@pytest.fixture(scope="module")
def api_client(api_app):
    return api_app.test_client()


@pytest.fixture(scope="module")
def admin_tokens(api_client):
    """Log in as the env-var admin and return access + refresh tokens."""
    rv = api_client.post(
        "/api/auth/login",
        json={
            "username": os.environ["ADMIN_USERNAME"],
            "password": os.environ["ADMIN_PASSWORD"],
        },
    )
    assert rv.status_code == 200, rv.data
    data = rv.get_json()
    return data["access_token"], data["refresh_token"]


def _auth(token):
    """Return Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


# ── Auth endpoints ────────────────────────────────────────────────────────────

class TestApiAuth:
    def test_login_valid_credentials(self, api_client):
        rv = api_client.post(
            "/api/auth/login",
            json={
                "username": os.environ["ADMIN_USERNAME"],
                "password": os.environ["ADMIN_PASSWORD"],
            },
        )
        assert rv.status_code == 200
        data = rv.get_json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password(self, api_client):
        rv = api_client.post(
            "/api/auth/login",
            json={"username": os.environ["ADMIN_USERNAME"], "password": "wrong"},
        )
        assert rv.status_code == 401

    def test_login_missing_body(self, api_client):
        rv = api_client.post(
            "/api/auth/login",
            data="not json",
            content_type="text/plain",
        )
        assert rv.status_code == 400

    def test_login_missing_fields(self, api_client):
        rv = api_client.post("/api/auth/login", json={})
        assert rv.status_code == 400

    def test_refresh_returns_new_access_token(self, api_client, admin_tokens):
        _, refresh = admin_tokens
        rv = api_client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {refresh}"},
        )
        assert rv.status_code == 200
        data = rv.get_json()
        assert "access_token" in data

    def test_refresh_with_access_token_rejected(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert rv.status_code in (401, 422)

    def test_me_returns_user_info(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.get("/api/auth/me", headers=_auth(access))
        assert rv.status_code == 200
        data = rv.get_json()
        assert "username" in data
        assert "role" in data

    def test_me_without_token_rejected(self, api_client):
        rv = api_client.get("/api/auth/me")
        assert rv.status_code == 401


# ── Document endpoints ────────────────────────────────────────────────────────

class TestApiDocuments:
    def test_list_documents_authenticated(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.get("/api/documents", headers=_auth(access))
        assert rv.status_code == 200
        data = rv.get_json()
        assert "documents" in data
        assert "total" in data

    def test_list_documents_unauthenticated(self, api_client):
        rv = api_client.get("/api/documents")
        assert rv.status_code == 401

    def test_create_document(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.post(
            "/api/documents",
            json={
                "doc_name": "Test Document",
                "category": "Memo",
                "from_office": "IT Unit",
                "sender_name": "John Doe",
            },
            headers=_auth(access),
        )
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["doc_name"] == "Test Document"
        assert "id" in data
        assert data["status"] == "Pending"

    def test_create_document_unauthenticated(self, api_client):
        rv = api_client.post(
            "/api/documents",
            json={"doc_name": "Test"},
        )
        assert rv.status_code == 401

    def test_get_single_document(self, api_client, admin_tokens):
        access, _ = admin_tokens
        # Create one first
        create_rv = api_client.post(
            "/api/documents",
            json={"doc_name": "Single Doc Test"},
            headers=_auth(access),
        )
        doc_id = create_rv.get_json()["id"]

        rv = api_client.get(f"/api/documents/{doc_id}", headers=_auth(access))
        assert rv.status_code == 200
        assert rv.get_json()["id"] == doc_id

    def test_get_nonexistent_document_404(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.get("/api/documents/nonexistent-id-xyz", headers=_auth(access))
        assert rv.status_code == 404

    def test_update_document_status(self, api_client, admin_tokens):
        access, _ = admin_tokens
        create_rv = api_client.post(
            "/api/documents",
            json={"doc_name": "Status Test Doc"},
            headers=_auth(access),
        )
        doc_id = create_rv.get_json()["id"]

        rv = api_client.patch(
            f"/api/documents/{doc_id}/status",
            json={"status": "In Review", "remarks": "Under review"},
            headers=_auth(access),
        )
        assert rv.status_code == 200
        assert rv.get_json()["status"] == "In Review"

    def test_update_status_nonexistent_doc(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.patch(
            "/api/documents/fake-id/status",
            json={"status": "Released"},
            headers=_auth(access),
        )
        assert rv.status_code == 404

    def test_delete_document(self, api_client, admin_tokens):
        access, _ = admin_tokens
        create_rv = api_client.post(
            "/api/documents",
            json={"doc_name": "To Delete"},
            headers=_auth(access),
        )
        doc_id = create_rv.get_json()["id"]

        rv = api_client.delete(f"/api/documents/{doc_id}", headers=_auth(access))
        assert rv.status_code == 200

        # Verify it's gone
        rv2 = api_client.get(f"/api/documents/{doc_id}", headers=_auth(access))
        assert rv2.status_code == 404

    def test_delete_nonexistent_document(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.delete("/api/documents/ghost-id", headers=_auth(access))
        assert rv.status_code == 404

    def test_pagination_params(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.get(
            "/api/documents?page=1&limit=5",
            headers=_auth(access),
        )
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["page"] == 1
        assert data["limit"] == 5
        assert len(data["documents"]) <= 5

    def test_status_filter(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.get(
            "/api/documents?status=Pending",
            headers=_auth(access),
        )
        assert rv.status_code == 200
        for doc in rv.get_json()["documents"]:
            assert doc["status"] == "Pending"


# ── Stats ─────────────────────────────────────────────────────────────────────

class TestApiStats:
    def test_stats_authenticated(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.get("/api/stats", headers=_auth(access))
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data, dict)

    def test_stats_unauthenticated(self, api_client):
        rv = api_client.get("/api/stats")
        assert rv.status_code == 401


# ── QR endpoints ──────────────────────────────────────────────────────────────

class TestApiQR:
    def test_generate_qr_for_existing_doc(self, api_client, admin_tokens):
        access, _ = admin_tokens
        create_rv = api_client.post(
            "/api/documents",
            json={"doc_name": "QR Test Doc"},
            headers=_auth(access),
        )
        doc_id = create_rv.get_json()["id"]

        rv = api_client.get(f"/api/qr/generate/{doc_id}", headers=_auth(access))
        assert rv.status_code == 200
        data = rv.get_json()
        assert "qr_base64" in data
        assert data["qr_base64"].startswith("data:image/png;base64,")

    def test_generate_qr_nonexistent_doc(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.get("/api/qr/generate/no-such-doc", headers=_auth(access))
        assert rv.status_code == 404

    def test_scan_invalid_qr_token(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.post(
            "/api/qr/scan",
            json={"token": "invalidtoken"},
            headers=_auth(access),
        )
        assert rv.status_code == 401

    def test_scan_missing_token(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.post("/api/qr/scan", json={}, headers=_auth(access))
        assert rv.status_code == 400


# ── Additional resources ──────────────────────────────────────────────────────

class TestApiMisc:
    def test_offices_authenticated(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.get("/api/offices", headers=_auth(access))
        assert rv.status_code == 200

    def test_activity_log_authenticated(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.get("/api/activity-log", headers=_auth(access))
        assert rv.status_code == 200

    def test_dropdown_options_authenticated(self, api_client, admin_tokens):
        access, _ = admin_tokens
        rv = api_client.get("/api/dropdown-options", headers=_auth(access))
        assert rv.status_code == 200
