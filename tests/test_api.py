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


@pytest.fixture(scope="module")
def staff_tokens(api_client):
    """Create a role='staff' user and return its access + refresh tokens."""
    from services.auth import create_user
    create_user("apistaff", "ApiStaff123!", full_name="API Staff",
                role="staff", office="IT Unit")
    rv = api_client.post(
        "/api/auth/login",
        json={"username": "apistaff", "password": "ApiStaff123!"},
    )
    assert rv.status_code == 200, rv.data
    data = rv.get_json()
    return data["access_token"], data["refresh_token"]


@pytest.fixture(scope="module")
def client_tokens(api_client):
    """Create + approve a role='client' user and return its access + refresh tokens.

    Clients are created unapproved (create_user sets approved = role != 'client'),
    and verify_user rejects unapproved accounts, so approve_user is required before
    the client can obtain a token.
    """
    from services.auth import create_user, approve_user
    create_user("apiclient", "ApiClient123!", full_name="API Client", role="client")
    approve_user("apiclient")
    rv = api_client.post(
        "/api/auth/login",
        json={"username": "apiclient", "password": "ApiClient123!"},
    )
    assert rv.status_code == 200, rv.data
    data = rv.get_json()
    return data["access_token"], data["refresh_token"]


@pytest.fixture(scope="module")
def client2_tokens(api_client):
    """A SECOND approved role='client' user — used to prove one client cannot
    read or QR another client's document."""
    from services.auth import create_user, approve_user
    create_user("apiclient2", "ApiClient123!", full_name="API Client Two", role="client")
    approve_user("apiclient2")
    rv = api_client.post(
        "/api/auth/login",
        json={"username": "apiclient2", "password": "ApiClient123!"},
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


# ── /api/app-version download_url ─────────────────────────────────────────────

class TestAppVersionDownloadUrl:
    def test_relative_download_url_is_absolutized(self, api_client, monkeypatch):
        """No version.json on disk → code fallback's relative '/download'."""
        import config
        monkeypatch.setattr(config, "APP_URL", "https://configured.test")
        rv = api_client.get("/api/app-version")
        assert rv.status_code == 200
        assert rv.get_json()["download_url"] == "https://configured.test/download"

    def test_absolute_download_url_left_untouched(self, api_app, api_client,
                                                  tmp_path, monkeypatch):
        static_root = tmp_path / "static_root"
        (static_root / "apk").mkdir(parents=True)
        (static_root / "apk" / "version.json").write_text(json.dumps({
            "latest_version": "2.0.0",
            "min_version":    "1.0.0",
            "download_url":   "https://cdn.example.test/app.apk",
            "release_notes":  "",
            "force_update":   False,
        }))
        # Point the app at a temp static folder — never write into the repo.
        monkeypatch.setattr(api_app, "static_folder", str(static_root))
        import config
        monkeypatch.setattr(config, "APP_URL", "https://configured.test")

        rv = api_client.get("/api/app-version")
        assert rv.status_code == 200
        assert rv.get_json()["download_url"] == "https://cdn.example.test/app.apk"


# ── jwt_staff_required gate ─────────────────────────────────────────────────────

class TestJwtStaffGate:
    """jwt_staff_required: staff/admin allowed, clients get 403.

    Covers the three ungated endpoints closed in 1c —
    api_create_document, api_quick_note, api_check_duplicate.
    api_release_document is deliberately excluded: api_client_submit sets
    logged_by to the client, so a client is the legitimate owner and may
    release their own document.
    """

    # ── api_create_document (POST /documents) ──
    def test_create_document_client_forbidden(self, api_client, client_tokens):
        access, _ = client_tokens
        rv = api_client.post(
            "/api/documents",
            json={"doc_name": "Client-Origin Doc"},
            headers=_auth(access),
        )
        assert rv.status_code == 403

    def test_create_document_staff_allowed(self, api_client, staff_tokens):
        access, _ = staff_tokens
        rv = api_client.post(
            "/api/documents",
            json={"doc_name": "Staff-Origin Doc"},
            headers=_auth(access),
        )
        assert rv.status_code == 201

    # ── api_quick_note (POST /documents/<id>/quick-note) ──
    def test_quick_note_client_forbidden(self, api_client, client_tokens):
        # Gate runs before the body, so doc existence is irrelevant to the 403.
        access, _ = client_tokens
        rv = api_client.post(
            "/api/documents/any-id/quick-note",
            json={"note": "should not be allowed"},
            headers=_auth(access),
        )
        assert rv.status_code == 403

    def test_quick_note_staff_allowed(self, api_client, staff_tokens):
        access, _ = staff_tokens
        create_rv = api_client.post(
            "/api/documents",
            json={"doc_name": "Quick-Note Target"},
            headers=_auth(access),
        )
        doc_id = create_rv.get_json()["id"]
        rv = api_client.post(
            f"/api/documents/{doc_id}/quick-note",
            json={"note": "a staff note"},
            headers=_auth(access),
        )
        assert rv.status_code == 200

    # ── api_check_duplicate (GET /check-duplicate) ──
    def test_check_duplicate_client_forbidden(self, api_client, client_tokens):
        access, _ = client_tokens
        rv = api_client.get("/api/check-duplicate?q=test", headers=_auth(access))
        assert rv.status_code == 403

    def test_check_duplicate_staff_allowed(self, api_client, staff_tokens):
        access, _ = staff_tokens
        rv = api_client.get("/api/check-duplicate?q=test", headers=_auth(access))
        assert rv.status_code == 200


# ── Client-safe document endpoint + QR ownership (privacy boundary) ─────────────
#
# These are the SAFETY NET for a decided privacy boundary. The client-facing view
# GET /client/documents/<id> MUST surface release IDENTITY (collector name/origin/
# office/position, release date, releasing staff) but MUST NEVER surface the
# collector's contact info, nor the raw internal travel_log `remarks`/`officer`.
# /qr/generate/<id> MUST require ownership. Each test is written to FAIL if a
# future edit re-leaks (e.g. spreads the release row, re-embeds contact into a
# remark, or drops the QR ownership gate).

# Unique sentinel values so an "anywhere in the payload" search is unambiguous.
_SECRET_CONTACT = "0917-000-SENTINEL-CONTACT-9999"
_SECRET_REMARK = "INTERNAL-OFFICER-NOTE-ZZTOP-DO-NOT-LEAK"


@pytest.fixture(scope="module")
def released_client_doc(api_app, client_tokens, staff_tokens):
    """A Released document OWNED by apiclient, carrying:
      - a document_releases row WITH a collector_contact (must stay hidden), and
      - internal travel_log remarks/officer (must stay hidden).
    staff_tokens is requested so 'apistaff' exists and released_by resolves to a
    real full name. Returns the document's internal id (what get_doc matches on).
    """
    import uuid as _uuid
    from services.documents import insert_doc, now_str, generate_ref
    from services.database import create_document_release

    doc = {
        "id": str(_uuid.uuid4()),
        "doc_id": generate_ref(),
        "doc_name": "Client Release Privacy Doc",
        "category": "Memo",
        "sender_org": "H3h3",
        "referred_to": "",
        "status": "Released",
        "created_at": now_str(),
        "logged_by": "apiclient",
        "travel_log": [
            {"office": "IT Unit", "action": "Logged", "officer": "API Staff",
             "timestamp": now_str(), "remarks": _SECRET_REMARK},
            {"office": "IT Unit",
             "action": "Released to Jerome Pedrosa by API Staff",
             "officer": "API Staff", "timestamp": now_str(),
             "remarks": f"Physically released to Jerome Pedrosa. {_SECRET_REMARK}"},
        ],
    }
    insert_doc(doc)
    create_document_release(
        doc["id"], released_by="apistaff",
        collector_name="Jerome Pedrosa", collector_origin="H3h3",
        collector_office="H3h3 Office", collector_position="Collector",
        collector_contact=_SECRET_CONTACT,
    )
    return doc["id"]


class TestClientDocEndpoint:
    def test_owner_gets_200_and_no_collector_contact(
            self, api_client, client_tokens, released_client_doc):
        access, _ = client_tokens
        rv = api_client.get(
            f"/api/client/documents/{released_client_doc}", headers=_auth(access))
        assert rv.status_code == 200, rv.data
        body = rv.get_json()
        # The release block exists (positive path exercised) ...
        assert body["release"] is not None
        # ... but must NOT carry the contact key ...
        assert "collector_contact" not in body["release"]
        # ... and the raw contact value must appear NOWHERE in the payload
        # (belt-and-suspenders: catches a leak via any field or a row spread).
        assert _SECRET_CONTACT not in json.dumps(body)

    def test_no_raw_travel_log_remarks_or_officer(
            self, api_client, client_tokens, released_client_doc):
        access, _ = client_tokens
        rv = api_client.get(
            f"/api/client/documents/{released_client_doc}", headers=_auth(access))
        assert rv.status_code == 200
        body = rv.get_json()
        # No history item may expose the internal remarks/officer fields ...
        for item in body.get("history", []):
            assert "remarks" not in item
            assert "officer" not in item
        # ... and the internal remark text must appear nowhere in the payload.
        assert _SECRET_REMARK not in json.dumps(body)

    def test_release_block_surfaces_identity(
            self, api_client, client_tokens, released_client_doc):
        # We DO surface release identity — this is the positive guarantee.
        access, _ = client_tokens
        rv = api_client.get(
            f"/api/client/documents/{released_client_doc}", headers=_auth(access))
        assert rv.status_code == 200
        block = rv.get_json()["release"]
        assert block["collector_name"] == "Jerome Pedrosa"
        assert block["collector_origin"] == "H3h3"
        # released_by was stored as the username 'apistaff'; the endpoint must
        # resolve it to the full name.
        assert block["released_by_name"] == "API Staff"

    def test_other_client_forbidden(
            self, api_client, client2_tokens, released_client_doc):
        access, _ = client2_tokens
        rv = api_client.get(
            f"/api/client/documents/{released_client_doc}", headers=_auth(access))
        assert rv.status_code == 403


class TestQrOwnershipGate:
    def test_qr_denied_for_non_owner_client(
            self, api_client, client2_tokens, released_client_doc):
        access, _ = client2_tokens
        rv = api_client.get(
            f"/api/qr/generate/{released_client_doc}", headers=_auth(access))
        assert rv.status_code == 403

    def test_qr_allowed_for_owning_client(
            self, api_client, client_tokens, released_client_doc):
        access, _ = client_tokens
        rv = api_client.get(
            f"/api/qr/generate/{released_client_doc}", headers=_auth(access))
        assert rv.status_code == 200
        assert rv.get_json()["qr_base64"].startswith("data:image/png;base64,")


# ── Collector-identity resolver: response contract (collector-fields Step 4) ────

class TestResolveCollectorIdentity:
    """The release-to-collector scanner posts a collector's client QR token to
    /staff/resolve-collector-identity to auto-fill the capture form. Step 4 makes
    the resolver return origin + position + email (email was a dead read before —
    now in the SELECT) and retires the phone read (no phone column exists); Step 5a
    adds office (already in the SELECT, just not surfaced by the whitelist).

    This proves the resolver RESPONSE CONTRACT in JSON mode: the fields the handler
    whitelists onto the identity dict. office is already in the SELECT, so its
    response contract is JSON-provable here. The DB SELECT column list itself is NOT
    harness-provable — conftest forces the JSON backend (DATABASE_URL=""), which
    returns the raw user dict, so the SELECT string is exercised only on prod and
    is verified there after deploy.
    """

    def test_resolver_returns_origin_office_position_email_no_phone(
            self, api_client, staff_tokens):
        from services.auth import create_user, approve_user
        from services.qr import get_or_create_client_token

        # A collector is just an approved client user with the profile fields set.
        # office is an existing create_user kwarg (mirrors staff records).
        create_user(
            "collector4", "Collect123!", full_name="Collector Four", role="client",
            email="collector@example.com", office="Records Section",
            origin="Region VIII", position="Administrative Officer II",
        )
        approve_user("collector4")

        # Mint that user's long-lived client QR token (the CLI- token the scanner
        # reads); resolve_client_token reverses it inside the resolver.
        token = get_or_create_client_token("collector4")

        access, _ = staff_tokens
        rv = api_client.post(
            "/api/staff/resolve-collector-identity",
            json={"token": token},
            headers=_auth(access),
        )
        assert rv.status_code == 200, rv.data
        body = rv.get_json()
        assert body["origin"] == "Region VIII"
        assert body["office"] == "Records Section"
        assert body["position"] == "Administrative Officer II"
        assert body["email"] == "collector@example.com"
        # phone read is retired — the key must not appear at all.
        assert "phone" not in body


# ── Release action string ⇄ client_view classifier coupling (collector-fields) ──

class TestReleaseActionClassifierBinding:
    """Binds api_release_to_client's composed travel_log `action` string to the
    client_view release classifier — the coupling test_client_view.py can't cover.

    test_client_view.py exercises the classifier against HARDCODED literals, so it
    stays green even if api_release_to_client mangles the "Released to " / " by "
    markers the classifier keys on. This test closes that gap: it drives the REAL
    handler, pulls the ACTUAL action string it appended to the travel_log, and runs
    THAT string through client_view.bucket_label (the same entrypoint the client
    history uses). If a future edit breaks either marker in the handler's f-string,
    the string stops bucketing as the collector hand-off and this test goes RED.

    Uses the env-var admin token so the office-primary-group release gate
    (_staff_in_office_primary_group) passes without standing up saved_offices — the
    gate is orthogonal to the marker coupling under test.
    """

    def test_real_release_action_classifies_as_collector_bucket(
            self, api_client, admin_tokens):
        import uuid as _uuid
        from services.documents import insert_doc, get_doc, generate_ref, now_str
        from services.client_view import bucket_label

        doc_id = str(_uuid.uuid4())
        insert_doc({
            "id": doc_id,
            "doc_id": generate_ref(),
            "doc_name": "Release Classifier Binding Doc",
            "category": "Memo",
            "status": "Released",
            "created_at": now_str(),
            "logged_by": "apiclient",
            "travel_log": [],
        })

        access, _ = admin_tokens
        rv = api_client.post(
            f"/api/documents/{doc_id}/release-to-client",
            json={
                "collector_name":     "Test Collector",
                "collector_origin":   "Region VIII",
                "collector_office":   "ICU",
                "collector_position": "Administrative Officer II",
            },
            headers=_auth(access),
        )
        assert rv.status_code == 201, rv.data

        # Pull the ACTUAL action string the handler composed and appended.
        doc = get_doc(doc_id)
        release_actions = [
            e.get("action", "") for e in doc.get("travel_log", [])
            if "released to " in (e.get("action") or "").lower()
        ]
        assert release_actions, (
            "handler did not append a collector-release travel_log entry: "
            f"{doc.get('travel_log')}"
        )
        action = release_actions[-1]

        # The office + position we passed must be woven into the descriptor (this
        # is the display-only enrichment) WITHOUT breaking the markers.
        assert "ICU" in action and "Administrative Officer II" in action, action

        # THE BINDING: the real string must classify as the collector hand-off.
        # bucket_label keys on "released to " AND " by " — break either in the
        # handler and this flips to "Released from the office" (or the fallback).
        assert bucket_label(action) == "Released to collector", (
            f"real handler action {action!r} did not bucket as the collector "
            f"release — got {bucket_label(action)!r}. The 'Released to '/' by ' "
            "markers the client_view classifier depends on are broken."
        )


# ── Staff-only release history endpoint (B1) ────────────────────────────────────
#
# GET /api/documents/<id>/releases returns the FULL release history WITH
# collector_contact — staff/admin only. The settled rule: staff/admin see contact,
# clients NEVER do. Because this block carries contact, the endpoint MUST be behind
# @jwt_staff_required (which a client JWT cannot pass), NOT the ownership-gated
# api_get_document (which a client CAN reach for their own doc). These tests are the
# safety net: (a) a client is refused AND sees no contact; (b) staff DO see contact.

_STAFF_RELEASE_CONTACT = "collector-b1@example.com-SENTINEL"


class TestStaffReleaseHistory:
    def _make_released_doc(self, contact=_STAFF_RELEASE_CONTACT, n_releases=1):
        """Insert a doc + N release rows (JSON backend) and return its id."""
        import uuid as _uuid
        from services.documents import insert_doc, generate_ref, now_str
        from services.database import create_document_release

        doc_id = str(_uuid.uuid4())
        insert_doc({
            "id": doc_id,
            "doc_id": generate_ref(),
            "doc_name": "Staff Release History Doc",
            "category": "Memo",
            "status": "Released",
            "created_at": now_str(),
            "logged_by": "apiclient",
            "submitted_by": "apiclient",  # so the OWNING client can reach api_get_document
            "travel_log": [],
        })
        for i in range(n_releases):
            create_document_release(
                doc_id, released_by="apistaff",
                collector_name=f"Collector {i}", collector_origin="Region VIII",
                collector_office="ICU", collector_position="Administrative Officer II",
                collector_contact=contact,
            )
        return doc_id

    def test_client_is_refused_and_sees_no_contact(
            self, api_client, client_tokens, staff_tokens):
        # staff_tokens is requested so 'apistaff' exists for released_by resolution.
        doc_id = self._make_released_doc()
        access, _ = client_tokens  # a role='client' JWT — must be rejected.
        rv = api_client.get(
            f"/api/documents/{doc_id}/releases", headers=_auth(access))
        # jwt_staff_required refuses role='client' outright.
        assert rv.status_code == 403, rv.data
        # And the contact value must appear NOWHERE in the refusal body.
        assert _STAFF_RELEASE_CONTACT not in rv.get_data(as_text=True)

    def test_staff_sees_full_release_block_with_contact(
            self, api_client, staff_tokens):
        doc_id = self._make_released_doc()
        access, _ = staff_tokens
        rv = api_client.get(
            f"/api/documents/{doc_id}/releases", headers=_auth(access))
        assert rv.status_code == 200, rv.data
        blocks = rv.get_json()["releases"]
        assert len(blocks) == 1
        b = blocks[0]
        # Staff DO get contact — the whole point of the endpoint.
        assert b["collector_contact"] == _STAFF_RELEASE_CONTACT
        # ... alongside the rest of the structured record.
        assert b["collector_origin"] == "Region VIII"
        assert b["collector_office"] == "ICU"
        assert b["collector_position"] == "Administrative Officer II"
        # released_by (username 'apistaff') resolves to the full name.
        assert b["released_by_name"] == "API Staff"

    def test_multi_release_returns_all(
            self, api_client, staff_tokens):
        doc_id = self._make_released_doc(n_releases=2)
        access, _ = staff_tokens
        rv = api_client.get(
            f"/api/documents/{doc_id}/releases", headers=_auth(access))
        assert rv.status_code == 200, rv.data
        blocks = rv.get_json()["releases"]
        # A doc CAN be re-released — the endpoint returns EVERY release, not just
        # the latest. Assert count + membership; strict newest-first order is NOT
        # asserted here because the JSON backend stamps released_at at second
        # resolution and sorts stably, so two releases in the same second keep
        # insertion order. Newest-first IS guaranteed on the DB backend
        # (ORDER BY released_at DESC), which prod runs.
        assert len(blocks) == 2
        assert {b["collector_name"] for b in blocks} == {"Collector 0", "Collector 1"}

    def test_doc_with_no_release_returns_empty_list_200(
            self, api_client, staff_tokens):
        import uuid as _uuid
        from services.documents import insert_doc, generate_ref, now_str
        doc_id = str(_uuid.uuid4())
        insert_doc({
            "id": doc_id, "doc_id": generate_ref(), "doc_name": "Unreleased",
            "category": "Memo", "status": "Received", "created_at": now_str(),
            "logged_by": "apiclient", "travel_log": [],
        })
        access, _ = staff_tokens
        rv = api_client.get(
            f"/api/documents/{doc_id}/releases", headers=_auth(access))
        assert rv.status_code == 200, rv.data
        assert rv.get_json()["releases"] == []
