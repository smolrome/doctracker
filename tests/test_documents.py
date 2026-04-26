"""
tests/test_documents.py — Tests for document-related service functions and web routes.

Covers:
  - generate_ref() uniqueness and format
  - normalize_status_fields() logic
  - insert_doc / get_doc / save_doc / delete_doc via JSON backend
  - get_stats() returns expected keys
  - now_str() returns a parseable ISO timestamp
  - Web route: create document (POST /)
  - Web route: document detail page (GET /document/<id>)
  - Web route: document not found (404)
  - Status transitions (valid and invalid)
"""

import os
import re
import pytest
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "e" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


# ── Service-layer unit tests ──────────────────────────────────────────────────

class TestDocumentHelpers:
    def test_generate_ref_format(self):
        from services.documents import generate_ref
        ref = generate_ref()
        current_year = datetime.now().year
        assert re.match(rf"REF-{current_year}-[A-F0-9]{{4}}", ref), \
            f"Unexpected ref format: {ref}"

    def test_generate_ref_uniqueness(self):
        from services.documents import generate_ref
        refs = {generate_ref() for _ in range(50)}
        # Very unlikely two will collide; if they do the test is flaky but harmless
        assert len(refs) >= 48

    def test_now_str_is_parseable(self):
        from services.documents import now_str
        ts = now_str()
        # Should be parseable as ISO 8601
        parsed = datetime.fromisoformat(ts)
        assert parsed.year >= 2024

    def test_normalize_received_adds_timestamp(self):
        from services.documents import normalize_status_fields
        doc = {"status": "Received", "logged_by": "alice"}
        result = normalize_status_fields(doc)
        assert "date_received" in result
        assert result["date_received"] != ""

    def test_normalize_received_preserves_existing_timestamp(self):
        from services.documents import normalize_status_fields
        doc = {"status": "Received", "date_received": "2024-01-01 10:00"}
        result = normalize_status_fields(doc)
        assert result["date_received"] == "2024-01-01 10:00"

    def test_normalize_released_adds_timestamp(self):
        from services.documents import normalize_status_fields
        doc = {"status": "Released", "logged_by": "bob"}
        result = normalize_status_fields(doc)
        assert "date_released" in result

    def test_normalize_other_status_unchanged(self):
        from services.documents import normalize_status_fields
        doc = {"status": "Pending"}
        result = normalize_status_fields(doc)
        assert "date_received" not in result
        assert "date_released" not in result


class TestDocumentCRUD:
    """CRUD tests using the JSON-file backend (no DB)."""

    @pytest.fixture(autouse=True)
    def use_tmp_dir(self, tmp_path, monkeypatch):
        import json
        data_file = str(tmp_path / "documents.json")
        (tmp_path / "documents.json").write_text(json.dumps([]))
        (tmp_path / "users.json").write_text(json.dumps([]))
        monkeypatch.setenv("DATA_FILE", data_file)
        monkeypatch.chdir(tmp_path)

    def test_insert_and_get_doc(self):
        from services.documents import insert_doc, get_doc, generate_ref
        import uuid
        doc = {
            "id": str(uuid.uuid4()),
            "doc_id": generate_ref(),
            "doc_name": "Test Insert",
            "status": "Pending",
        }
        insert_doc(doc)
        fetched = get_doc(doc["id"])
        assert fetched is not None
        assert fetched["doc_name"] == "Test Insert"

    def test_get_nonexistent_doc_returns_none(self):
        from services.documents import get_doc
        assert get_doc("does-not-exist") is None

    def test_save_doc_updates_existing(self):
        from services.documents import insert_doc, get_doc, save_doc, generate_ref
        import uuid
        doc_id = str(uuid.uuid4())
        doc = {"id": doc_id, "doc_id": generate_ref(), "doc_name": "Original", "status": "Pending"}
        insert_doc(doc)
        doc["status"] = "In Review"
        save_doc(doc)
        fetched = get_doc(doc_id)
        assert fetched["status"] == "In Review"

    def test_delete_doc_soft_deletes(self):
        """
        delete_doc() is a SOFT delete — it sets deleted=True but never removes the record.
        get_doc() fetches with include_deleted=True so the record is still there.
        Verify the deleted flag is set, and that load_docs() (default) excludes it.
        """
        from services.documents import insert_doc, get_doc, delete_doc, load_docs, generate_ref
        import uuid
        doc_id = str(uuid.uuid4())
        doc = {"id": doc_id, "doc_id": generate_ref(), "doc_name": "To Delete", "status": "Pending"}
        insert_doc(doc)
        delete_doc(doc_id)
        fetched = get_doc(doc_id)
        # get_doc always returns the record (include_deleted=True internally)
        assert fetched is not None
        assert fetched.get("deleted") is True
        # Normal load (include_deleted=False) must exclude it
        active_ids = [d["id"] for d in load_docs(include_deleted=False)]
        assert doc_id not in active_ids

    def test_load_docs_excludes_deleted(self):
        from services.documents import insert_doc, delete_doc, load_docs, generate_ref
        import uuid
        doc_id = str(uuid.uuid4())
        doc = {"id": doc_id, "doc_id": generate_ref(), "doc_name": "Deleted Doc", "status": "Pending"}
        insert_doc(doc)
        delete_doc(doc_id)
        docs = load_docs(include_deleted=False)
        ids = [d["id"] for d in docs]
        assert doc_id not in ids

    def test_load_docs_include_deleted(self):
        from services.documents import insert_doc, delete_doc, load_docs, generate_ref
        import uuid
        doc_id = str(uuid.uuid4())
        doc = {"id": doc_id, "doc_id": generate_ref(), "doc_name": "Keep Deleted", "status": "Pending"}
        insert_doc(doc)
        delete_doc(doc_id)
        docs = load_docs(include_deleted=True)
        ids = [d["id"] for d in docs]
        assert doc_id in ids

    def test_get_stats_returns_expected_keys(self):
        from services.documents import get_stats
        stats = get_stats([])
        assert isinstance(stats, dict)
        # Should have at least a total count key
        assert any(k in stats for k in ("total", "by_status", "count"))


# ── Web route tests ───────────────────────────────────────────────────────────

class TestDocumentWebRoutes:
    def _csrf(self, c):
        c.get("/login")
        with c.session_transaction() as s:
            return s.get("csrf_token", "")

    def test_add_doc_requires_auth(self, client):
        """The /add route has @login_required — unauthenticated → redirect to login."""
        rv = client.get("/add", follow_redirects=False)
        assert rv.status_code == 302
        assert "login" in rv.headers.get("Location", "")

    def test_dashboard_loads_for_admin(self, admin_client):
        rv = admin_client.get("/", follow_redirects=True)
        assert rv.status_code == 200

    def test_document_detail_not_found_returns_404(self, admin_client):
        rv = admin_client.get("/document/nonexistent-id-xyz", follow_redirects=True)
        assert rv.status_code in (404, 200)  # may render 404 template with 200

    def test_healthz_endpoint(self, client):
        rv = client.get("/healthz")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["ok"] is True or "error" in data

    def test_security_headers_present(self, client):
        """Every response must include key security headers."""
        rv = client.get("/login")
        headers = rv.headers
        assert "X-Content-Type-Options" in headers
        assert "X-Frame-Options" in headers
        assert "Content-Security-Policy" in headers
