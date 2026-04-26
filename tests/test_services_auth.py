"""
tests/test_services_auth.py — Unit tests for services/auth.py.

Tests pure service-layer logic without HTTP:
  - hash_password / verify_password
  - hmac_safe_compare
  - create_user / verify_user / get_user / delete_user
  - update_user_password (min length guard)
  - update_user (role allowlist guard)
  - approve_user
  - check_rate_limit / reset_rate_limit
  - get_all_users never returns password_hash
"""

import os
import time
import pytest

os.environ.setdefault("SECRET_KEY", "a" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""  # Force JSON backend


# ── Password hashing ──────────────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_is_bcrypt(self):
        from services.auth import hash_password
        h = hash_password("somepassword")
        assert h.startswith("$2")  # bcrypt sentinel

    def test_verify_correct_password(self):
        from services.auth import hash_password, verify_password
        h = hash_password("mySecret99")
        assert verify_password("mySecret99", h) is True

    def test_verify_wrong_password(self):
        from services.auth import hash_password, verify_password
        h = hash_password("mySecret99")
        assert verify_password("wrongpass", h) is False

    def test_different_hashes_for_same_password(self):
        """bcrypt uses a random salt — same input → different hash."""
        from services.auth import hash_password
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2

    def test_hmac_safe_compare_equal(self):
        from services.auth import hmac_safe_compare
        assert hmac_safe_compare("abc", "abc") is True

    def test_hmac_safe_compare_not_equal(self):
        from services.auth import hmac_safe_compare
        assert hmac_safe_compare("abc", "xyz") is False


# ── User CRUD ─────────────────────────────────────────────────────────────────

class TestUserCRUD:
    """All tests run against the JSON-file backend (no DB)."""

    def test_create_user_success(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, get_user
        ok, err = create_user("alice", "AlicePass1!", full_name="Alice", role="staff")
        assert ok is True
        assert err is None
        user = get_user("alice")
        assert user is not None
        assert user["username"] == "alice"

    def test_create_user_duplicate_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user
        create_user("bob", "BobPass1!", role="staff")
        ok, err = create_user("bob", "AnotherPass1!", role="staff")
        assert ok is False
        assert "taken" in (err or "").lower()

    def test_create_user_invalid_role_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user
        ok, err = create_user("badactor", "Pass1234!", role="superadmin")
        assert ok is False
        assert "Invalid role" in (err or "")

    def test_verify_user_correct_credentials(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, verify_user
        create_user("carol", "CarolPass1!", full_name="Carol", role="staff", office="IT")
        full_name, role, office = verify_user("carol", "CarolPass1!")
        assert full_name == "Carol"
        assert role == "staff"

    def test_verify_user_wrong_password(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, verify_user
        create_user("dave", "DavePass1!", role="staff")
        full_name, role, office = verify_user("dave", "WrongPass1!")
        assert full_name is None
        assert role is None

    def test_verify_user_nonexistent_username(self, tmp_path, monkeypatch):
        """Must return (None, None, '') — not raise."""
        monkeypatch.chdir(tmp_path)
        from services.auth import verify_user
        result = verify_user("nobody_here", "anypass")
        assert result == (None, None, "")

    def test_verify_user_inactive_account_fails(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, set_user_active, verify_user
        create_user("eve", "EvePass1!", role="staff")
        set_user_active("eve", False)
        full_name, role, _ = verify_user("eve", "EvePass1!")
        assert full_name is None

    def test_delete_user(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, delete_user, get_user
        create_user("frank", "FrankPass1!", role="staff")
        delete_user("frank")
        assert get_user("frank") is None

    def test_get_all_users_no_password_hash(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, get_all_users
        create_user("grace", "GracePass1!", role="staff")
        for u in get_all_users():
            assert "password_hash" not in u

    def test_update_user_password_too_short(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, update_user_password
        create_user("henry", "HenryPass1!", role="staff")
        ok, err = update_user_password("henry", "short")
        assert ok is False
        assert "8" in (err or "") or "characters" in (err or "").lower()

    def test_update_user_password_success(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, update_user_password, verify_user
        create_user("ivan", "IvanPass1!", role="staff")
        ok, err = update_user_password("ivan", "NewIvanPass2!")
        assert ok is True
        full_name, role, _ = verify_user("ivan", "NewIvanPass2!")
        assert role == "staff"

    def test_update_user_invalid_role_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, update_user
        create_user("judy", "JudyPass1!", role="staff")
        ok, err = update_user("judy", role="hacker")
        assert ok is False
        assert "Invalid role" in (err or "")

    def test_approve_user_client(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, approve_user, get_user
        create_user("kyle", "KylePass1!", role="client")
        # Client starts unapproved
        user = get_user("kyle")
        assert user.get("approved") is False or user.get("approved") == 0
        ok, err = approve_user("kyle")
        assert ok is True
        user = get_user("kyle")
        assert user.get("approved") is True or user.get("approved") == 1

    def test_approve_nonexistent_user_fails(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import approve_user
        ok, err = approve_user("no_one")
        assert ok is False

    def test_approve_non_client_fails(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, approve_user
        create_user("lena", "LenaPass1!", role="staff")
        ok, err = approve_user("lena")
        assert ok is False
        assert "client" in (err or "").lower()


# ── Rate limiting ─────────────────────────────────────────────────────────────

class TestRateLimit:
    def setup_method(self):
        """Clear the rate store before each test for isolation."""
        from services.auth import _rate_store, _rate_lock
        with _rate_lock:
            _rate_store.clear()

    def test_first_attempt_allowed(self):
        from services.auth import check_rate_limit
        allowed, wait = check_rate_limit("login", "127.0.0.1:testuser")
        assert allowed is True
        assert wait == 0

    def test_lockout_after_max_attempts(self):
        from services.auth import check_rate_limit
        # login max = 5, window = 300
        for _ in range(5):
            check_rate_limit("login", "127.0.0.1:lockeduser")
        allowed, wait = check_rate_limit("login", "127.0.0.1:lockeduser")
        assert allowed is False
        assert wait > 0

    def test_reset_clears_lockout(self):
        from services.auth import check_rate_limit, reset_rate_limit
        for _ in range(6):
            check_rate_limit("login", "127.0.0.1:resetuser")
        reset_rate_limit("login", "127.0.0.1:resetuser")
        allowed, wait = check_rate_limit("login", "127.0.0.1:resetuser")
        assert allowed is True

    def test_different_identifiers_independent(self):
        from services.auth import check_rate_limit
        for _ in range(6):
            check_rate_limit("login", "127.0.0.1:user_a")
        # user_b must be unaffected
        allowed, _ = check_rate_limit("login", "127.0.0.1:user_b")
        assert allowed is True

    def test_unknown_action_uses_defaults(self):
        from services.auth import check_rate_limit
        allowed, wait = check_rate_limit("unknown_action", "127.0.0.1:x")
        assert allowed is True
