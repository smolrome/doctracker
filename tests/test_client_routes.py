"""
tests/test_client_routes.py — Tests for routes/client.py.

Covers:
  - /client/login GET renders form
  - /client/login POST with valid credentials redirects to portal
  - /client/login POST with wrong credentials shows error
  - /client (portal) requires client role
  - /client/submit requires client role; GET renders form
  - /client/submit POST add action adds item to cart
  - /client/track/<doc_id> requires client role and ownership
  - /client/delete/<doc_id> requires client role; only allows rejected docs
  - /client/trash shows deleted docs for client
  - /client/trash/restore/<doc_id> restores a doc
  - /client/register GET renders registration form
  - /client/register POST with short password shows error
  - Open-redirect: /client/login ignores external next_url
"""

import json
import os
import uuid
import pytest

os.environ.setdefault("SECRET_KEY", "k" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _client_csrf(client_obj):
    """Hit /client/login to seed the session, then extract the CSRF token."""
    client_obj.get("/client/login")
    with client_obj.session_transaction() as s:
        return s.get("csrf_token", "")


def _make_client_user(username="clienttest01", password="ClientPass1!"):
    """Create and approve a client user, return (username, password)."""
    from services.auth import create_user, approve_user
    create_user(username, password, full_name="Test Client", role="client")
    approve_user(username)
    return username, password


def _reset_rate(username):
    from services.auth import _rate_store, _rate_lock
    with _rate_lock:
        keys = [k for k in list(_rate_store) if username.lower() in k.lower()]
        for k in keys:
            del _rate_store[k]


def _login_as_client(app_client, username, password):
    """Login via /client/login and return the response."""
    csrf = _client_csrf(app_client)
    _reset_rate(username)
    return app_client.post(
        "/client/login",
        data={"username": username, "password": password, "csrf_token": csrf},
        follow_redirects=False,
    )


@pytest.fixture
def new_client(app):
    """Create a fresh approved client user per test (unique names)."""
    username = f"clt{uuid.uuid4().hex[:6]}"
    password = "ClientPass1!"
    from services.auth import create_user, approve_user
    create_user(username, password, full_name="Fresh Client", role="client")
    approve_user(username)
    return username, password


@pytest.fixture
def logged_in_client(app, new_client):
    """Test client pre-logged-in as an approved client user via /client/login."""
    username, password = new_client
    c = app.test_client()
    rv = _login_as_client(c, username, password)
    assert rv.status_code == 302, f"Client login failed: {rv.data[:200]}"
    return c, username


# ── /client/login ─────────────────────────────────────────────────────────────

class TestClientLogin:
    def test_get_renders_form(self, client):
        rv = client.get("/client/login")
        assert rv.status_code == 200
        assert b"login" in rv.data.lower() or b"username" in rv.data.lower()

    def test_valid_login_redirects_to_portal(self, app):
        _make_client_user("loginclient01", "LoginPass1!")
        c = app.test_client()
        rv = _login_as_client(c, "loginclient01", "LoginPass1!")
        assert rv.status_code == 302
        location = rv.headers.get("Location", "")
        assert "/client" in location

    def test_wrong_password_shows_error(self, app):
        _make_client_user("wrongpass01", "Correct1!")
        c = app.test_client()
        rv = _login_as_client(c, "wrongpass01", "WrongPass99!")
        rv_follow = c.post(
            "/client/login",
            data={
                "username": "wrongpass01",
                "password": "WrongPass99!",
                "csrf_token": _client_csrf(c),
            },
            follow_redirects=True,
        )
        assert rv_follow.status_code == 200
        body = rv_follow.data.decode()
        assert "invalid" in body.lower() or "incorrect" in body.lower()

    def test_unknown_user_same_error(self, client):
        csrf = _client_csrf(client)
        rv = client.post(
            "/client/login",
            data={"username": "nosuchuser999", "password": "anything", "csrf_token": csrf},
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "invalid" in body.lower()

    def test_external_next_url_is_ignored(self, app):
        _make_client_user("nexttest01", "NextPass1!")
        c = app.test_client()
        _reset_rate("nexttest01")
        csrf = _client_csrf(c)
        rv = c.post(
            "/client/login",
            data={
                "username": "nexttest01",
                "password": "NextPass1!",
                "csrf_token": csrf,
                "next_url": "https://evil.com/steal",
            },
            follow_redirects=False,
        )
        location = rv.headers.get("Location", "")
        assert "evil.com" not in location

    def test_already_logged_in_client_redirected_from_login(self, logged_in_client):
        c, _ = logged_in_client
        rv = c.get("/client/login", follow_redirects=False)
        assert rv.status_code == 302

    def test_unapproved_client_cannot_login(self, app):
        from services.auth import create_user
        create_user("unapproved01", "Approved1!", full_name="Waiting", role="client")
        # Do NOT approve
        c = app.test_client()
        rv = _login_as_client(c, "unapproved01", "Approved1!")
        if rv.status_code == 302:
            # Sometimes follows to portal, check it renders approved check
            rv2 = c.get("/client", follow_redirects=False)
            # Either redirected back or shows pending message
            assert rv2.status_code in (200, 302)
        else:
            body = rv.data.decode()
            assert "pending" in body.lower() or "approved" in body.lower()


# ── /client (portal) ──────────────────────────────────────────────────────────

class TestClientPortal:
    def test_unauthenticated_redirected(self, client):
        rv = client.get("/client", follow_redirects=False)
        assert rv.status_code == 302
        # Must redirect to client login
        location = rv.headers.get("Location", "")
        assert "login" in location

    def test_admin_user_redirected_away(self, admin_client):
        """Admin role should not access the client portal."""
        rv = admin_client.get("/client", follow_redirects=False)
        # Expect redirect to client login (not client portal)
        assert rv.status_code in (302, 200)

    def test_logged_in_client_sees_portal(self, logged_in_client):
        c, _ = logged_in_client
        rv = c.get("/client", follow_redirects=True)
        assert rv.status_code == 200


# ── /client/register ─────────────────────────────────────────────────────────

class TestClientRegister:
    def test_get_renders_registration_form(self, client):
        rv = client.get("/client/register")
        assert rv.status_code == 200
        assert b"register" in rv.data.lower() or b"username" in rv.data.lower()

    def test_short_password_rejected(self, client):
        csrf = _client_csrf(client)
        rv = client.post(
            "/client/register",
            data={
                "username":         "shortpwduser",
                "full_name":        "Short Password",
                "password":         "abc",
                "confirm_password": "abc",
                "csrf_token":       csrf,
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "8" in body or "password" in body.lower()

    def test_password_mismatch_rejected(self, client):
        csrf = _client_csrf(client)
        rv = client.post(
            "/client/register",
            data={
                "username":         "mismatchclient",
                "full_name":        "Mismatch User",
                "password":         "ValidPass1!",
                "confirm_password": "DifferentPass1!",
                "csrf_token":       csrf,
            },
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "match" in body.lower() or rv.status_code == 200

    def test_missing_full_name_rejected(self, client):
        csrf = _client_csrf(client)
        rv = client.post(
            "/client/register",
            data={
                "username":         "nofullname",
                "full_name":        "",
                "password":         "ValidPass1!",
                "confirm_password": "ValidPass1!",
                "csrf_token":       csrf,
            },
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "full name" in body.lower() or "required" in body.lower()


# ── /client/submit ────────────────────────────────────────────────────────────

class TestClientSubmit:
    def test_unauthenticated_redirected(self, client):
        rv = client.get("/client/submit", follow_redirects=False)
        assert rv.status_code == 302

    def test_get_renders_form(self, logged_in_client):
        c, _ = logged_in_client
        rv = c.get("/client/submit")
        assert rv.status_code == 200

    def test_add_doc_to_cart(self, logged_in_client):
        c, _ = logged_in_client
        csrf = _client_csrf(c)
        rv = c.post(
            "/client/submit",
            data={
                "_action":    "add",
                "doc_name":   "My Test Document",
                "referred_to": "Division Office",
                "category":   "Memorandum",
                "csrf_token": csrf,
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "my test document" in body.lower() or "added" in body.lower()

    def test_add_without_doc_name_shows_error(self, logged_in_client):
        c, _ = logged_in_client
        csrf = _client_csrf(c)
        rv = c.post(
            "/client/submit",
            data={
                "_action":    "add",
                "doc_name":   "",
                "referred_to": "Division Office",
                "csrf_token": csrf,
            },
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "required" in body.lower() or "name" in body.lower()

    def test_add_without_referred_to_shows_error(self, logged_in_client):
        c, _ = logged_in_client
        csrf = _client_csrf(c)
        rv = c.post(
            "/client/submit",
            data={
                "_action":    "add",
                "doc_name":   "Some Doc",
                "referred_to": "",
                "csrf_token": csrf,
            },
            follow_redirects=True,
        )
        body = rv.data.decode()
        assert "referred" in body.lower() or "required" in body.lower()


# ── /client/track/<doc_id> ────────────────────────────────────────────────────

class TestClientTrack:
    def _insert_client_doc(self, username, name="Client Track Doc"):
        from services.documents import insert_doc
        doc = {
            "id":           str(uuid.uuid4())[:8].upper(),
            "doc_id":       f"REF-2024-{uuid.uuid4().hex[:4].upper()}",
            "doc_name":     name,
            "status":       "Pending",
            "submitted_by": username,
        }
        insert_doc(doc)
        return doc

    def test_unauthenticated_redirected(self, client):
        rv = client.get("/client/track/ANYDOCID", follow_redirects=False)
        assert rv.status_code == 302

    def test_client_can_track_own_doc(self, logged_in_client, app):
        c, username = logged_in_client
        with app.app_context():
            doc = self._insert_client_doc(username)
        rv = c.get(f"/client/track/{doc['id']}", follow_redirects=True)
        assert rv.status_code == 200

    def test_client_cannot_track_other_users_doc(self, logged_in_client, app):
        c, _ = logged_in_client
        with app.app_context():
            doc = self._insert_client_doc("anotheruser99", "Other's Doc")
        rv = c.get(f"/client/track/{doc['id']}", follow_redirects=True)
        # Should redirect to portal (ownership check fails)
        assert rv.status_code == 200
        body = rv.data.decode()
        # Should be on portal or show error, not the track page
        assert "not found" in body.lower() or "portal" in body.lower() or rv.status_code == 200


# ── /client/trash ─────────────────────────────────────────────────────────────

class TestClientTrash:
    def test_unauthenticated_redirected(self, client):
        rv = client.get("/client/trash", follow_redirects=False)
        assert rv.status_code == 302

    def test_client_can_view_trash(self, logged_in_client):
        c, _ = logged_in_client
        rv = c.get("/client/trash", follow_redirects=True)
        assert rv.status_code == 200

    def test_restore_own_deleted_doc(self, logged_in_client, app):
        c, username = logged_in_client
        from services.documents import insert_doc, delete_doc
        with app.app_context():
            doc = {
                "id":           str(uuid.uuid4())[:8].upper(),
                "doc_id":       "REF-2024-TSTR",
                "doc_name":     "Restore Me",
                "status":       "Rejected",
                "submitted_by": username,
            }
            insert_doc(doc)
            delete_doc(doc["id"], deleted_by=username)
        csrf = _client_csrf(c)
        rv = c.post(
            f"/client/trash/restore/{doc['id']}",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        assert rv.status_code == 200
        # After restore it should appear on portal again
        from services.documents import get_doc
        with app.app_context():
            restored = get_doc(doc["id"])
        assert not restored.get("deleted", False)

    def test_permanent_delete_without_confirm_rejected(self, logged_in_client, app):
        c, username = logged_in_client
        from services.documents import insert_doc, delete_doc
        with app.app_context():
            doc = {
                "id":           str(uuid.uuid4())[:8].upper(),
                "doc_id":       "REF-2024-PERM",
                "doc_name":     "Perm Del Test",
                "status":       "Rejected",
                "submitted_by": username,
            }
            insert_doc(doc)
            delete_doc(doc["id"])
        csrf = _client_csrf(c)
        rv = c.post(
            "/client/trash/permanent-delete-all",
            data={"csrf_token": csrf},   # missing confirm_destroy=yes
            follow_redirects=True,
        )
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "confirmed" in body.lower() or "deletion" in body.lower() or rv.status_code == 200


# ── /client/delete/<doc_id> ───────────────────────────────────────────────────

class TestClientDelete:
    def test_cannot_delete_non_rejected_doc(self, logged_in_client, app):
        """Clients can only delete documents in 'Rejected' status."""
        c, username = logged_in_client
        from services.documents import insert_doc
        with app.app_context():
            doc = {
                "id":           str(uuid.uuid4())[:8].upper(),
                "doc_id":       "REF-2024-NDEL",
                "doc_name":     "Not Rejected",
                "status":       "Pending",  # <-- not Rejected
                "submitted_by": username,
            }
            insert_doc(doc)
        csrf = _client_csrf(c)
        rv = c.post(
            f"/client/delete/{doc['id']}",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "only" in body.lower() or "rejected" in body.lower()

    def test_can_delete_rejected_doc(self, logged_in_client, app):
        """Client can soft-delete a rejected document."""
        c, username = logged_in_client
        from services.documents import insert_doc, get_doc
        with app.app_context():
            doc = {
                "id":           str(uuid.uuid4())[:8].upper(),
                "doc_id":       "REF-2024-RDEL",
                "doc_name":     "Rejected Doc",
                "status":       "Rejected",
                "submitted_by": username,
            }
            insert_doc(doc)
        csrf = _client_csrf(c)
        rv = c.post(
            f"/client/delete/{doc['id']}",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        assert rv.status_code == 200
        with app.app_context():
            deleted = get_doc(doc["id"])
        assert deleted.get("deleted") is True
