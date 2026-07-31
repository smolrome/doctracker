"""
tests/test_admin_rename_route.py — Step 3 of the username-rename feature.

Covers the ROUTE wiring in routes/admin.py:edit_user_route:
  - a genuine username change diverts to rename_user and REWRITES HISTORY
    (documents, not just the users row) — the test that would have caught the
    original orphaning bug
  - a non-username edit still goes through update_user (no rename path)
  - the server-side self-rename guard blocks an admin renaming their own
    logged-in account
  - a taken / invalid new name is rejected with the right message
  - the prominent re-login warning is flashed on success

Runs on the JSON backend (DATABASE_URL="" via conftest). The app fixture is
session-scoped and chdir's into a shared temp dir, so every test uses UNIQUE
usernames to stay independent.
"""

import os
import json
import pytest


def _csrf(client):
    """The per-session CSRF token app.py injects — the app enforces its OWN token
    check on POSTs (independent of WTF_CSRF_ENABLED), so every POST needs it."""
    client.get("/login")
    with client.session_transaction() as sess:
        return sess.get("csrf_token", "")


def _post_edit(client, target, **fields):
    """POST to /edit-user/<target> with the CSRF token folded in."""
    data = {"office": "", "email": "", "documents_handled": "", **fields}
    data["csrf_token"] = _csrf(client)
    return client.post(f"/edit-user/{target}", data=data, follow_redirects=False)


def _flashes(client):
    """Pending flashes as a list of (category, message) — read WITHOUT following
    the redirect, so they are still in the session and not yet consumed."""
    with client.session_transaction() as sess:
        return list(sess.get("_flashes", []))


def _has_flash(client, needle, category=None):
    for cat, msg in _flashes(client):
        if needle.lower() in msg.lower() and (category is None or cat == category):
            return True
    return False


def _seed_docs(docs):
    """Overwrite documents.json with exactly these docs (via the same helper the
    service uses, so the path matches config.DATA_FILE)."""
    from services.documents import _save_docs_json
    _save_docs_json(docs)


def _login(app, username, password):
    """Log a created DB user in on a fresh client (CSRF disabled in test config)."""
    from tests.conftest import _reset_rate
    _reset_rate(username)
    c = app.test_client()
    rv = c.post("/login",
                data={"username": username, "password": password,
                      "csrf_token": _csrf(c)},
                follow_redirects=False)
    assert rv.status_code == 302, f"login for {username} failed: {rv.data[:200]}"
    return c


class TestEditUserRenameWiring:

    def test_username_change_rewrites_history(self, app, admin_client):
        """THE regression test for the orphaning bug: a username change through
        the edit route must rewrite references in DOCUMENTS, not just users.json."""
        from services.auth import create_user, _load_users_json
        create_user("histuser", "GoodPass1!", full_name="Hist User", role="staff")
        _seed_docs([
            {"id": "H1", "logged_by": "histuser", "received_by": "histuser",
             "travel_log": [{"officer": "histuser", "action": "Received"}]},
            {"id": "H2", "logged_by": "someoneelse"},
        ])

        rv = _post_edit(admin_client, "histuser",
                        new_username="histuser2", full_name="Hist User",
                        role="staff", email="hist@example.com")
        assert rv.status_code == 302

        # users row renamed
        unames = {u["username"] for u in _load_users_json()}
        assert "histuser2" in unames and "histuser" not in unames

        # HISTORY rewritten — the whole point (would fail under the old
        # update_user-only path, which orphaned these).
        from services.documents import load_docs
        docs = {d["id"]: d for d in load_docs(include_deleted=True)}
        assert docs["H1"]["logged_by"] == "histuser2"
        assert docs["H1"]["received_by"] == "histuser2"
        assert docs["H1"]["travel_log"][0]["officer"] == "histuser2"
        assert docs["H2"]["logged_by"] == "someoneelse"   # untouched

        # Prominent re-login warning is present on success.
        assert _has_flash(admin_client, "log out", category="warning")
        assert _has_flash(admin_client, "orphaned", category="warning")

    def test_non_username_edit_uses_update_user(self, app, admin_client):
        """Editing email/full_name WITHOUT changing the username stays on the
        plain update_user path (no rename, no error)."""
        from services.auth import create_user, get_user
        create_user("editme", "GoodPass1!", full_name="Edit Me", role="staff")

        rv = _post_edit(admin_client, "editme",
                        new_username="editme",          # unchanged
                        full_name="Edited Name", role="staff",
                        email="edited@example.com")
        assert rv.status_code == 302

        u = get_user("editme")
        assert u["full_name"] == "Edited Name"
        assert u["email"] == "edited@example.com"
        # No rename-specific warning should have fired.
        assert not _has_flash(admin_client, "log out")

    def test_self_rename_blocked(self, app):
        """SERVER-SIDE guard: an admin renaming their OWN logged-in account is
        blocked before any write (a crafted POST must not bypass it)."""
        from services.auth import create_user, _load_users_json
        create_user("selfad", "GoodPass1!", full_name="Self Admin", role="admin")
        c = _login(app, "selfad", "GoodPass1!")

        rv = _post_edit(c, "selfad",
                        new_username="selfad2", full_name="Self Admin",
                        role="admin")
        assert rv.status_code == 302

        assert _has_flash(c, "cannot rename your own account", category="error")
        unames = {u["username"] for u in _load_users_json()}
        assert "selfad" in unames and "selfad2" not in unames   # no write happened

    def test_rename_to_taken_name_rejected(self, app, admin_client):
        from services.auth import create_user, _load_users_json
        create_user("takensrc", "GoodPass1!", full_name="Taken Src", role="staff")
        create_user("takendst", "GoodPass1!", full_name="Taken Dst", role="staff")

        rv = _post_edit(admin_client, "takensrc",
                        new_username="takendst", full_name="Taken Src",
                        role="staff")
        assert rv.status_code == 302

        assert _has_flash(admin_client, "already taken", category="error")
        unames = {u["username"] for u in _load_users_json()}
        assert "takensrc" in unames   # unchanged — rename rejected

    def test_rename_invalid_format_rejected(self, app, admin_client):
        from services.auth import create_user, _load_users_json
        create_user("validsrc", "GoodPass1!", full_name="Valid Src", role="staff")

        rv = _post_edit(admin_client, "validsrc",
                        new_username="bad name",   # space → fails _validate_username
                        full_name="Valid Src", role="staff")
        assert rv.status_code == 302

        # Validator message is surfaced (mentions the allowed characters).
        assert _has_flash(admin_client, "may contain only", category="error")
        unames = {u["username"] for u in _load_users_json()}
        assert "validsrc" in unames   # unchanged
