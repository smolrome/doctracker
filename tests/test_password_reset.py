"""
tests/test_password_reset.py — Checkpoint A security properties for the
self-service password reset TOKEN CORE + RATE LIMITING.

These tests assert the security properties that are the whole point of the
checkpoint. They run against the JSON backend (conftest forces DATABASE_URL="").
Each test isolates its JSON files by chdir-ing into a fresh tmp dir.
"""

import hashlib
import json
import time

import pytest

from services import password_reset as pr
from services.auth import create_user, verify_password, verify_user, _load_users_json


@pytest.fixture(autouse=True)
def _isolate_files(tmp_path, monkeypatch):
    """Run each test in its own temp CWD so JSON stores don't leak between tests."""
    monkeypatch.chdir(tmp_path)
    # users.json must exist for the auth JSON backend
    (tmp_path / "users.json").write_text("[]")
    yield


def _read_token_store():
    with open(pr._TOKENS_JSON) as f:
        return json.load(f)


# ── 1. Token is stored HASHED, never raw ────────────────────────────────────────

def test_token_stored_hashed_not_raw():
    raw = pr.create_reset_token("alice")

    store = _read_token_store()
    raw_file = json.dumps(store)

    # The raw token must NOT appear anywhere in storage...
    assert raw not in raw_file
    assert raw not in store  # not used as a key either
    # ...but its SHA-256 hash IS the stored key.
    expected_hash = hashlib.sha256(raw.encode()).hexdigest()
    assert expected_hash in store
    assert store[expected_hash]["username"] == "alice"
    assert store[expected_hash]["used"] is False


# ── 2. verify accepts valid; rejects expired / used / unknown / tampered ─────────

def test_verify_accepts_valid_token():
    raw = pr.create_reset_token("bob")
    assert pr.verify_reset_token(raw) == "bob"


def test_verify_rejects_expired_token():
    raw = pr.create_reset_token("bob")
    # Force expiry into the past
    store = _read_token_store()
    for rec in store.values():
        rec["expires_at"] = time.time() - 1
    with open(pr._TOKENS_JSON, "w") as f:
        json.dump(store, f)
    assert pr.verify_reset_token(raw) is None


def test_verify_rejects_used_token():
    raw = pr.create_reset_token("bob")
    assert pr.consume_reset_token(raw) is True
    assert pr.verify_reset_token(raw) is None


def test_verify_rejects_unknown_token():
    pr.create_reset_token("bob")  # some unrelated token exists
    assert pr.verify_reset_token("this-token-was-never-issued") is None


def test_verify_rejects_tampered_token():
    raw = pr.create_reset_token("bob")
    # Flip the last character to simulate tampering
    tampered = raw[:-1] + ("A" if raw[-1] != "A" else "B")
    assert pr.verify_reset_token(tampered) is None


# ── 3. A new token invalidates the user's prior unused token ─────────────────────

def test_new_token_invalidates_previous():
    first  = pr.create_reset_token("carol")
    second = pr.create_reset_token("carol")

    assert pr.verify_reset_token(first) is None      # old one dead
    assert pr.verify_reset_token(second) == "carol"  # new one lives


# ── 4. Consume marks used; a consumed token can't be reused ──────────────────────

def test_consume_marks_used_and_prevents_reuse():
    raw = pr.create_reset_token("dave")
    assert pr.consume_reset_token(raw) is True
    # Second consume fails, and it no longer verifies
    assert pr.consume_reset_token(raw) is False
    assert pr.verify_reset_token(raw) is None


# ── 5. Rate limiting: per-email AND per-IP ───────────────────────────────────────

def test_rate_limit_blocks_after_max_per_email():
    email_max = pr.PASSWORD_RESET_RATE_LIMITS["email"]["max"]
    ip = "10.0.0.1"
    # First `email_max` requests are allowed
    for _ in range(email_max):
        allowed, reason = pr.check_reset_rate_limit("spammer@example.com", ip)
        assert allowed is True, reason
    # The (max+1)-th is blocked, and the tripped scope is "email"
    allowed, reason = pr.check_reset_rate_limit("spammer@example.com", ip)
    assert allowed is False
    assert reason == "email"


def test_rate_limit_blocks_after_max_per_ip():
    ip_max = pr.PASSWORD_RESET_RATE_LIMITS["ip"]["max"]
    ip = "10.0.0.99"
    # Use a DISTINCT email each time so the email limit is never the trigger
    for i in range(ip_max):
        allowed, reason = pr.check_reset_rate_limit(f"user{i}@example.com", ip)
        assert allowed is True, reason
    allowed, reason = pr.check_reset_rate_limit("one-more@example.com", ip)
    assert allowed is False
    assert reason == "ip"


def test_rate_limit_is_scoped_per_identifier():
    # Different email + different IP should be unaffected by another's usage
    for i in range(pr.PASSWORD_RESET_RATE_LIMITS["email"]["max"] + 2):
        pr.check_reset_rate_limit("heavy@example.com", "1.1.1.1")
    allowed, reason = pr.check_reset_rate_limit("fresh@example.com", "2.2.2.2")
    assert allowed is True


# ── 6. Password set uses the existing bcrypt hashing path (never plaintext) ──────

def test_password_set_uses_werkzeug_bcrypt_path():
    create_user("erin", "OldPass123", role="staff")
    new_password = "BrandNewPass456"

    ok, err = pr.set_password("erin", new_password)
    assert ok is True, err

    # Stored hash is a bcrypt hash, NOT the plaintext password
    user = next(u for u in _load_users_json() if u["username"] == "erin")
    stored = user["password_hash"]
    assert stored != new_password
    assert new_password not in stored
    assert stored.startswith("$2")  # bcrypt marker

    # New password verifies via the existing verify_password + login path
    assert verify_password(new_password, stored) is True
    full_name, role, office = verify_user("erin", new_password)
    assert role == "staff"


def test_password_set_rejects_weak_password():
    create_user("frank", "OldPass123", role="staff")
    ok, err = pr.set_password("frank", "short")
    assert ok is False
    assert "at least" in (err or "")


# ── End-to-end combiner: verify → set → consume (single use) ─────────────────────

def test_reset_password_with_token_end_to_end():
    create_user("grace", "OldPass123", role="staff")
    raw = pr.create_reset_token("grace")

    ok, err = pr.reset_password_with_token(raw, "FreshSecret789")
    assert ok is True, err

    # Token is consumed (single-use) and the new password works
    assert pr.verify_reset_token(raw) is None
    full_name, role, office = verify_user("grace", "FreshSecret789")
    assert role == "staff"


def test_reset_password_with_bad_token_does_not_change_password():
    create_user("heidi", "OldPass123", role="staff")
    ok, err = pr.reset_password_with_token("bogus-token", "FreshSecret789")
    assert ok is False
    # Original password still valid
    _, role, _ = verify_user("heidi", "OldPass123")
    assert role == "staff"
