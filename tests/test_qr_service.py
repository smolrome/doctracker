"""
tests/test_qr_service.py — Unit tests for services/qr.py.

Covers:
  - sign_office_action() format and content
  - verify_office_action() valid / expired / tampered
  - create_doc_token() / use_doc_token() round-trip
  - use_doc_token() rejects double-use
  - get_token_doc() non-destructive lookup
  - create_slip_token() / use_slip_token() round-trip
  - make_qr_png() returns valid PNG bytes
  - generate_qr_b64() returns base64 string
  - get_base_url() falls back to local IP when localhost
"""

import os
import time
import pytest

os.environ.setdefault("SECRET_KEY", "f" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Each test gets its own scratch directory for JSON token files."""
    monkeypatch.chdir(tmp_path)


# ── URL signing ───────────────────────────────────────────────────────────────

class TestSignVerifyOfficeAction:
    def test_sign_returns_query_string(self):
        from services.qr import sign_office_action
        result = sign_office_action("main-office-rec")
        assert "?exp=" in result
        assert "&sig=" in result

    def test_sign_includes_action_prefix(self):
        from services.qr import sign_office_action
        result = sign_office_action("division-office-rel")
        assert result.startswith("division-office-rel?")

    def test_verify_valid_signature(self):
        from services.qr import sign_office_action, verify_office_action
        signed = sign_office_action("my-office-rec")
        # Parse the signed URL: action?exp=EXPIRY&sig=SIG
        action, qs = signed.split("?", 1)
        params = dict(p.split("=") for p in qs.split("&"))
        assert verify_office_action(action, params["exp"], params["sig"]) is True

    def test_verify_wrong_signature(self):
        from services.qr import sign_office_action, verify_office_action
        signed = sign_office_action("test-office-rec")
        action, qs = signed.split("?", 1)
        params = dict(p.split("=") for p in qs.split("&"))
        assert verify_office_action(action, params["exp"], "deadbeef00000000") is False

    def test_verify_tampered_action(self):
        from services.qr import sign_office_action, verify_office_action
        signed = sign_office_action("good-office-rec")
        _, qs = signed.split("?", 1)
        params = dict(p.split("=") for p in qs.split("&"))
        # Different action, same sig → should fail
        assert verify_office_action("evil-office-rec", params["exp"], params["sig"]) is False

    def test_verify_expired_timestamp(self):
        from services.qr import verify_office_action
        # exp is in the past
        past_exp = str(int(time.time()) - 100)
        assert verify_office_action("any-office-rec", past_exp, "anysig") is False

    def test_verify_invalid_exp_string(self):
        from services.qr import verify_office_action
        assert verify_office_action("any", "notanumber", "sig") is False


# ── Doc QR tokens ─────────────────────────────────────────────────────────────

class TestDocTokens:
    def test_create_and_use_receive_token(self):
        from services.qr import create_doc_token, use_doc_token
        token = create_doc_token("DOCABC01", "RECEIVE")
        assert token.startswith("REC-")
        doc_id, token_type = use_doc_token(token)
        assert doc_id == "DOCABC01"
        assert token_type == "RECEIVE"

    def test_create_and_use_release_token(self):
        from services.qr import create_doc_token, use_doc_token
        token = create_doc_token("DOCABC02", "RELEASE")
        assert token.startswith("REL-")
        doc_id, token_type = use_doc_token(token)
        assert doc_id == "DOCABC02"
        assert token_type == "RELEASE"

    def test_token_is_one_time_use(self):
        from services.qr import create_doc_token, use_doc_token
        token = create_doc_token("DOCONETIME", "RECEIVE")
        # First use
        doc_id, _ = use_doc_token(token)
        assert doc_id == "DOCONETIME"
        # Second use
        doc_id2, tt2 = use_doc_token(token)
        assert doc_id2 is None
        assert tt2 is None

    def test_unknown_token_returns_none(self):
        from services.qr import use_doc_token
        doc_id, tt = use_doc_token("REC-DOESNOTEXIST0000")
        assert doc_id is None
        assert tt is None

    def test_get_token_doc_non_destructive(self):
        """get_token_doc should not mark the token as used."""
        from services.qr import create_doc_token, get_token_doc, use_doc_token
        from services.documents import insert_doc
        import uuid

        # Insert a real doc so get_doc() can find it
        doc_id = str(uuid.uuid4())[:8].upper()
        insert_doc({"id": doc_id, "doc_id": "REF-2024-AAAA", "doc_name": "Token Test", "status": "Pending"})

        token = create_doc_token(doc_id, "RECEIVE")
        doc, tt = get_token_doc(token)
        assert doc is not None
        assert tt == "RECEIVE"

        # Token must still be valid after non-destructive lookup
        doc_id2, tt2 = use_doc_token(token)
        assert doc_id2 == doc_id


# ── Slip tokens ───────────────────────────────────────────────────────────────

class TestSlipTokens:
    def test_create_and_use_slip_receive_token(self):
        from services.qr import create_slip_token, use_slip_token
        token = create_slip_token("SLIP0001", "SLIP_RECEIVE")
        assert "SLIP_REC" in token or token.startswith("SLIP_REC")
        slip_id, tt = use_slip_token(token)
        assert slip_id == "SLIP0001"
        assert tt == "SLIP_RECEIVE"

    def test_create_and_use_slip_release_token(self):
        from services.qr import create_slip_token, use_slip_token
        token = create_slip_token("SLIP0002", "SLIP_RELEASE")
        slip_id, tt = use_slip_token(token)
        assert slip_id == "SLIP0002"
        assert tt == "SLIP_RELEASE"

    def test_slip_token_one_time_use(self):
        from services.qr import create_slip_token, use_slip_token
        token = create_slip_token("SLIP0003", "SLIP_RECEIVE")
        use_slip_token(token)
        slip_id2, _ = use_slip_token(token)
        assert slip_id2 is None


# ── PNG generators ────────────────────────────────────────────────────────────

class TestQRPng:
    def test_make_qr_png_returns_bytes(self):
        from services.qr import make_qr_png
        doc = {"id": "TESTDOC1"}
        result = make_qr_png(doc, "http://localhost:5000/")
        assert isinstance(result, bytes)
        assert len(result) > 0
        # PNG magic bytes
        assert result[:4] == b"\x89PNG"

    def test_generate_qr_b64_is_valid_base64(self):
        import base64
        from services.qr import generate_qr_b64
        doc = {"id": "TESTDOC2"}
        b64 = generate_qr_b64(doc, "http://localhost:5000/")
        assert isinstance(b64, str)
        # Should decode without error
        decoded = base64.b64decode(b64)
        assert decoded[:4] == b"\x89PNG"

    def test_make_office_qr_png_rec_returns_bytes(self):
        from services.qr import make_office_qr_png
        result = make_office_qr_png("test-office-rec", "http://localhost:5000/")
        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    def test_make_office_qr_png_rel_returns_bytes(self):
        from services.qr import make_office_qr_png
        result = make_office_qr_png("test-office-rel", "http://localhost:5000/")
        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    def test_make_doc_status_qr_png_receive(self):
        from services.qr import create_doc_token, make_doc_status_qr_png
        token = create_doc_token("DOCPNG01", "RECEIVE")
        result = make_doc_status_qr_png(token, "RECEIVE", "Test Document")
        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    def test_make_doc_status_qr_png_release(self):
        from services.qr import create_doc_token, make_doc_status_qr_png
        token = create_doc_token("DOCPNG02", "RELEASE")
        result = make_doc_status_qr_png(token, "RELEASE", "Another Doc")
        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"


# ── get_base_url ──────────────────────────────────────────────────────────────

class TestGetBaseUrl:
    def test_localhost_returns_local_ip_or_fallback(self, monkeypatch):
        # Clear APP_URL so it falls through to IP detection
        monkeypatch.setenv("APP_URL", "")
        # Reload config to pick up env change
        import importlib
        import config
        importlib.reload(config)
        import services.qr as qrmod
        importlib.reload(qrmod)
        result = qrmod.get_base_url("http://localhost:5000/")
        # Should be an http:// URL (local IP or fallback)
        assert result.startswith("http")
        assert result != ""

    def test_non_localhost_returns_request_url(self, monkeypatch):
        monkeypatch.setenv("APP_URL", "")
        import importlib, config, services.qr as qrmod
        importlib.reload(config)
        importlib.reload(qrmod)
        result = qrmod.get_base_url("http://192.168.1.50:5000/")
        assert "192.168.1.50" in result

    def test_app_url_env_takes_priority(self, monkeypatch):
        monkeypatch.setenv("APP_URL", "https://myapp.example.com")
        import importlib, config, services.qr as qrmod
        importlib.reload(config)
        importlib.reload(qrmod)
        result = qrmod.get_base_url("http://localhost:5000/")
        assert result == "https://myapp.example.com"
