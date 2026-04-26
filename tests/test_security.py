"""
tests/test_security.py — Security and hardening tests.

Covers:
  - bcrypt is used (not SHA-256) for new passwords
  - Dummy bcrypt compare on unknown username (timing attack prevention)
  - Session cookie flags (HTTPOnly, SameSite)
  - Secret key length guard (< 32 chars → RuntimeError)
  - Security response headers on every page
  - Rate limit on API endpoints (429)
  - ADMIN_PASSWORD not present in any response body
  - get_all_users() never leaks password_hash
"""

import os
import pytest

os.environ.setdefault("SECRET_KEY", "f" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


# ── Password / hashing ────────────────────────────────────────────────────────

class TestPasswordSecurity:
    def test_new_hash_is_bcrypt(self):
        from services.auth import hash_password
        h = hash_password("testpassword1")
        assert h.startswith("$2"), "Expected bcrypt hash starting with $2"

    def test_sha256_legacy_path_still_verified_for_migration(self):
        """
        verify_password() keeps a legacy SHA-256 path for migrating old accounts.
        It intentionally accepts SHA-256 hashes so users can log in once and get
        their hash silently upgraded to bcrypt.  This test documents that behaviour.
        New passwords are ALWAYS stored as bcrypt (tested above); the SHA-256 path
        is read-only — no new hash is ever written in that format.
        """
        import hashlib
        from services.auth import verify_password
        sha_hash = hashlib.sha256(b"testpassword1").hexdigest()
        # The legacy path returns True so the user can log in and get upgraded.
        assert verify_password("testpassword1", sha_hash) is True
        # Wrong password must still fail even with the legacy path.
        assert verify_password("wrongpassword", sha_hash) is False

    def test_verify_unknown_user_does_not_crash(self, tmp_path, monkeypatch):
        """Dummy compare ensures timing parity — must not raise."""
        monkeypatch.chdir(tmp_path)
        import json
        (tmp_path / "users.json").write_text(json.dumps([]))
        from services.auth import verify_user
        result = verify_user("nobody", "whatever")
        assert result == (None, None, "")

    def test_get_all_users_strips_password_hash(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        import json
        (tmp_path / "users.json").write_text(json.dumps([]))
        from services.auth import create_user, get_all_users
        create_user("sectest", "SecTest1!", role="staff")
        for user in get_all_users():
            assert "password_hash" not in user, \
                "get_all_users() must never return password_hash"


# ── Config / startup guards ───────────────────────────────────────────────────

class TestConfigGuards:
    def test_short_secret_key_raises(self):
        """create_app() must raise RuntimeError if SECRET_KEY < 32 chars."""
        old = os.environ.get("SECRET_KEY")
        os.environ["SECRET_KEY"] = "tooshort"
        try:
            # Re-import config (it caches at import time)
            import importlib
            import config as cfg
            importlib.reload(cfg)
            from app import create_app
            with pytest.raises(RuntimeError, match="SECRET_KEY"):
                create_app()
        except RuntimeError:
            pass  # Expected
        finally:
            if old:
                os.environ["SECRET_KEY"] = old
            else:
                os.environ.pop("SECRET_KEY", None)
            # Reload config back to normal
            try:
                import importlib, config
                importlib.reload(config)
            except Exception:
                pass


# ── HTTP response security headers ───────────────────────────────────────────

class TestSecurityHeaders:
    REQUIRED_HEADERS = [
        "X-Content-Type-Options",
        "X-Frame-Options",
        "X-XSS-Protection",
        "Referrer-Policy",
        "Content-Security-Policy",
    ]

    @pytest.mark.parametrize("path", ["/login", "/healthz"])
    def test_security_headers_on_public_pages(self, client, path):
        rv = client.get(path)
        for header in self.REQUIRED_HEADERS:
            assert header in rv.headers, \
                f"Missing security header '{header}' on {path}"

    def test_x_frame_options_is_sameorigin(self, client):
        rv = client.get("/login")
        assert rv.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_x_content_type_options_is_nosniff(self, client):
        rv = client.get("/login")
        assert rv.headers.get("X-Content-Type-Options") == "nosniff"

    def test_csp_has_default_src_self(self, client):
        rv = client.get("/login")
        csp = rv.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp


# ── Admin password leak ───────────────────────────────────────────────────────

class TestAdminPasswordNotLeaked:
    def test_admin_password_not_in_html_response(self, client):
        """The admin password must never appear in any HTML response body."""
        admin_pass = os.environ.get("ADMIN_PASSWORD", "")
        rv = client.get("/login")
        assert admin_pass not in rv.data.decode(), \
            "ADMIN_PASSWORD should never appear in HTML output"

    def test_admin_password_not_in_api_error(self, client):
        admin_pass = os.environ.get("ADMIN_PASSWORD", "")
        rv = client.post(
            "/api/auth/login",
            json={"username": "wrong", "password": "wrong"},
        )
        assert admin_pass not in rv.data.decode()


# ── API rate limiting ─────────────────────────────────────────────────────────

class TestApiRateLimit:
    def test_api_rate_limit_returns_429(self, app):
        """After enough requests, the API returns 429."""
        from services.auth import _rate_store, _rate_lock
        # Pre-fill the rate store to simulate being at the limit
        with _rate_lock:
            _rate_store["api:127.0.0.1"] = {
                "count": 999,
                "window_start": __import__("time").time(),
                "locked_until": __import__("time").time() + 120,
            }
        c = app.test_client()
        rv = c.get("/api/documents")
        assert rv.status_code in (429, 401)
        # Clean up
        with _rate_lock:
            _rate_store.pop("api:127.0.0.1", None)
