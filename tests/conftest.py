"""
tests/conftest.py — Shared fixtures for the entire test suite.

Sets up:
  - A fresh Flask test app per session (JSON-file backend, no real DB)
  - A test client with cookie/session support
  - Helper fixtures to log in as admin, staff, or client
  - CSRF token injection helpers
"""

import os
import json
import tempfile
import secrets
import pytest

# ── Environment must be set BEFORE importing config/app ──────────────────────
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
# Force JSON backend — no real PostgreSQL needed during tests
os.environ["DATABASE_URL"] = ""

# JWT secret for tests
os.environ.setdefault("JWT_SECRET_KEY", secrets.token_hex(32))


# ── App factory ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app(tmp_path_factory):
    """
    Create a Flask test app backed by temporary JSON files.
    Scoped to the whole session for speed; state-changing tests
    should use their own isolated client fixture where needed.
    """
    tmp = tmp_path_factory.mktemp("data")
    users_file = str(tmp / "users.json")
    docs_file = str(tmp / "documents.json")
    offices_file = str(tmp / "saved_offices.json")

    # Point the app at temp files
    os.environ["DATA_FILE"] = docs_file

    # Pre-populate an empty users list so the file exists
    with open(users_file, "w") as f:
        json.dump([], f)
    with open(docs_file, "w") as f:
        json.dump([], f)
    with open(offices_file, "w") as f:
        # saved_offices.json is a dict {slug: {office_name, created_by, ...}}
        json.dump({}, f)

    # Patch the JSON paths used by services/auth.py to use the temp file.
    # services/auth.py hard-codes "users.json" — we patch os.getcwd so that
    # relative paths resolve to our temp directory.
    original_cwd = os.getcwd()
    os.chdir(str(tmp))

    from app import create_app
    flask_app = create_app()
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,       # CSRF tested separately
        SESSION_COOKIE_SECURE=False,  # tests run over HTTP
    )

    yield flask_app

    os.chdir(original_cwd)


@pytest.fixture
def client(app):
    """A plain test client (no logged-in user)."""
    return app.test_client()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _get_csrf(client):
    """
    Hit the login page to seed the session, then extract the CSRF token.
    The CSRF token is injected into every session by app.py's ensurecsrf_token.
    """
    client.get("/login")
    with client.session_transaction() as sess:
        return sess.get("csrf_token", "")


def _reset_rate(username: str, ip: str = "127.0.0.1"):
    """Clear any rate-limit lock for a given username+IP before logging in."""
    from services.auth import _rate_store, _rate_lock
    with _rate_lock:
        keys = [k for k in list(_rate_store) if username.lower() in k.lower()]
        for k in keys:
            del _rate_store[k]


@pytest.fixture
def admin_client(app):
    """Test client pre-authenticated as the env-var admin."""
    admin_user = os.environ["ADMIN_USERNAME"]
    _reset_rate(admin_user)
    c = app.test_client()
    csrf = _get_csrf(c)
    rv = c.post(
        "/login",
        data={
            "username": admin_user,
            "password": os.environ["ADMIN_PASSWORD"],
            "csrf_token": csrf,
        },
        follow_redirects=False,  # avoid cascade crash if dashboard has issues
    )
    assert rv.status_code == 302, f"Admin login failed (expected redirect): {rv.data[:200]}"
    return c


@pytest.fixture
def staff_client(app):
    """
    Test client pre-authenticated as a staff user.
    Creates the staff user on first use (duplicate create is safe).
    """
    from services.auth import create_user
    create_user("staffuser", "StaffPass1!", full_name="Staff User", role="staff")
    _reset_rate("staffuser")
    c = app.test_client()
    csrf = _get_csrf(c)
    rv = c.post(
        "/login",
        data={
            "username": "staffuser",
            "password": "StaffPass1!",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert rv.status_code == 302, f"Staff login failed: {rv.data[:200]}"
    return c


@pytest.fixture
def client_user_client(app):
    """
    Test client pre-authenticated as an approved client user.
    Creates + approves the client user on first use.
    """
    from services.auth import create_user, approve_user
    create_user("clientuser", "ClientPass1!", full_name="Client User", role="client")
    approve_user("clientuser")
    _reset_rate("clientuser")
    c = app.test_client()
    csrf = _get_csrf(c)
    rv = c.post(
        "/login",
        data={
            "username": "clientuser",
            "password": "ClientPass1!",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert rv.status_code == 302, f"Client login failed: {rv.data[:200]}"
    return c
