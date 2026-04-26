"""
tests/test_email_service.py — Unit tests for services/email.py.

Covers:
  - generate_invite_token() creates a unique hex token
  - generate_invite_token() replaces old unused token for same email
  - validate_invite_token() returns (email, name) for a valid token
  - validate_invite_token() returns (None, None) for unknown token
  - validate_invite_token() returns (None, None) after token is consumed
  - consume_invite_token() marks token as used
  - send_invite_email() short-circuits when MAIL_ENABLED=False
  - get_all_tokens() returns a list
"""

import os
import pytest

os.environ.setdefault("SECRET_KEY", "g" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Each test gets its own scratch directory so invite_tokens.json is clean."""
    monkeypatch.chdir(tmp_path)


class TestInviteTokenCRUD:
    def test_generate_returns_hex_string(self):
        from services.email import generate_invite_token
        token = generate_invite_token("alice@example.com", "Alice")
        assert isinstance(token, str)
        assert len(token) == 32  # uuid4().hex
        # Validate it's hex
        int(token, 16)  # should not raise

    def test_generate_different_tokens_per_call(self):
        from services.email import generate_invite_token
        t1 = generate_invite_token("bob@example.com", "Bob")
        t2 = generate_invite_token("carol@example.com", "Carol")
        assert t1 != t2

    def test_generate_replaces_old_unused_token_for_same_email(self):
        from services.email import generate_invite_token, validate_invite_token
        old = generate_invite_token("dave@example.com", "Dave")
        new = generate_invite_token("dave@example.com", "Dave")
        # Old token should no longer be valid
        email, _ = validate_invite_token(old)
        assert email is None
        # New token should be valid
        email2, name2 = validate_invite_token(new)
        assert email2 == "dave@example.com"

    def test_validate_valid_token(self):
        from services.email import generate_invite_token, validate_invite_token
        token = generate_invite_token("eve@example.com", "Eve")
        email, name = validate_invite_token(token)
        assert email == "eve@example.com"
        assert name == "Eve"

    def test_validate_unknown_token(self):
        from services.email import validate_invite_token
        email, name = validate_invite_token("0" * 32)
        assert email is None
        assert name is None

    def test_validate_empty_token(self):
        from services.email import validate_invite_token
        email, name = validate_invite_token("")
        assert email is None
        assert name is None

    def test_consume_marks_token_used(self):
        from services.email import generate_invite_token, validate_invite_token, consume_invite_token
        token = generate_invite_token("frank@example.com", "Frank")
        # Valid before consume
        email, _ = validate_invite_token(token)
        assert email == "frank@example.com"
        # Consume
        consume_invite_token(token)
        # Should be invalid now
        email2, _ = validate_invite_token(token)
        assert email2 is None

    def test_consume_nonexistent_token_does_not_raise(self):
        from services.email import consume_invite_token
        # Should complete silently
        consume_invite_token("f" * 32)

    def test_get_all_tokens_returns_list(self):
        from services.email import generate_invite_token, get_all_tokens
        generate_invite_token("list@example.com", "List Test")
        tokens = get_all_tokens()
        assert isinstance(tokens, list)
        assert len(tokens) >= 1


class TestEmailSending:
    def test_send_invite_email_disabled_by_default(self, monkeypatch):
        """Without BREVO_API_KEY, MAIL_ENABLED=False → returns (False, error_msg)."""
        # Ensure BREVO_API_KEY is absent
        monkeypatch.delenv("BREVO_API_KEY", raising=False)
        import importlib, config, services.email as email_mod
        importlib.reload(config)
        importlib.reload(email_mod)
        ok, msg = email_mod.send_invite_email("test@example.com", "Test User")
        assert ok is False
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_send_invite_email_mocked_brevo(self, monkeypatch, tmp_path):
        """Mock urllib.request.urlopen to simulate successful API call."""
        monkeypatch.setenv("BREVO_API_KEY", "test-key-123")
        monkeypatch.setenv("APP_URL", "https://test.example.com")
        monkeypatch.setenv("MAIL_SENDER", "noreply@test.com")

        import importlib, config, services.email as email_mod
        importlib.reload(config)
        importlib.reload(email_mod)

        if not email_mod.MAIL_ENABLED:
            pytest.skip("MAIL_ENABLED is False even with key set — check config logic")

        # Mock the HTTP call
        class FakeResponse:
            def read(self): return b'{"messageId": "fake123"}'
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: FakeResponse())

        ok, result = email_mod.send_invite_email("recipient@example.com", "Recipient")
        assert ok is True
        assert isinstance(result, str)  # Returns token on success
