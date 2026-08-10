"""
tests/test_safe_delete_user.py — the hybrid safe-delete footprint gate.

Admin delete-user is a bare DELETE FROM users with no cascade, so deleting a
user who appears in history tables would orphan their username across ~18
tables. The gate: if user_has_history(username) → BLOCK the delete and steer the
admin to disable instead; if the user has no footprint → allow the delete.

These run on the JSON backend (conftest forces DATABASE_URL=""). document_releases
has a JSON fallback (create_document_release), so its branch is exercised here;
the DB-only tables (staff_*, transfer_batches, import_batches, so_records) have
no JSON file and simply contribute no hit — verified indirectly by the "clean
user is deletable" test.

Guardrails NOT added by this feature (env-admin + self-delete) are asserted to
still hold, so the new elif slots in without weakening them.
"""

import os
import uuid

os.environ.setdefault("SECRET_KEY", "c" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


# ── Helpers ─────────────────────────────────────────────────────────────────

def _mkdoc(**fields):
    """Persist a minimal document carrying the given actor fields."""
    from services.documents import save_doc
    doc = {"id": uuid.uuid4().hex, "status": "Logged", **fields}
    save_doc(doc)
    return doc


def _usernames():
    from services.auth import get_all_users
    return {u["username"] for u in get_all_users()}


def _csrf(client):
    """The app enforces a custom same-session CSRF token on POST regardless of
    WTF_CSRF_ENABLED, redirecting tokenless POSTs to /login. The token is only
    (re-)seeded by ensurecsrf_token on a GET — the login POST leaves it empty —
    so hit a page first, then read it back."""
    client.get("/manage-users")
    with client.session_transaction() as sess:
        return sess.get("csrf_token", "")


# ── user_has_history unit tests (JSON backend) ──────────────────────────────

class TestUserHasHistoryUnit:
    def test_documents_actor_is_history(self, app):
        """A username named as a document actor (submitted_by) has history."""
        from services.auth import user_has_history
        _mkdoc(submitted_by="sd-u-docactor")
        assert user_has_history("sd-u-docactor") is True

    def test_travel_log_officer_is_history(self, app):
        from services.auth import user_has_history
        _mkdoc(submitted_by="someoneelse",
               travel_log=[{"officer": "sd-u-officer", "action": "Logged"}])
        assert user_has_history("sd-u-officer") is True

    def test_document_release_collector_is_history(self, app):
        """CRITICAL: document_releases is NOT in rename_user's sweep — the gate
        must catch collector_username here explicitly."""
        from services.auth import user_has_history
        from services.database import create_document_release
        create_document_release(
            "sd-rel-doc-a", released_by="somestaff",
            collector_name="Collector X", collector_username="sd-u-collector",
        )
        assert user_has_history("sd-u-collector") is True

    def test_document_release_released_by_is_history(self, app):
        from services.auth import user_has_history
        from services.database import create_document_release
        create_document_release(
            "sd-rel-doc-b", released_by="sd-u-releaser",
            collector_name="Collector Y", collector_username=None,
        )
        assert user_has_history("sd-u-releaser") is True

    def test_absent_user_has_no_history(self, app):
        """A username present nowhere → deletable."""
        from services.auth import user_has_history
        assert user_has_history("sd-u-absent-nowhere") is False

    def test_throwaway_only_is_not_history(self, app):
        """A user present ONLY in a throwaway table (client_qr_tokens) is still
        clean to delete — the gate must NOT count it."""
        from services.auth import user_has_history
        from services.qr import get_or_create_client_token
        get_or_create_client_token("sd-u-tokenonly")
        assert user_has_history("sd-u-tokenonly") is False

    def test_blank_username_is_not_history(self, app):
        from services.auth import user_has_history
        assert user_has_history("") is False


# ── Delete route gate (the core guard) ──────────────────────────────────────

class TestDeleteRouteGate:
    def test_user_with_history_is_blocked(self, admin_client):
        """A user with document history is NOT deleted and the admin is told to
        disable instead."""
        from services.auth import create_user
        create_user("sd-hist-user", "TestPass1!", full_name="Hist User", role="staff")
        _mkdoc(submitted_by="sd-hist-user")

        assert "sd-hist-user" in _usernames()
        rv = admin_client.post("/delete-user/sd-hist-user",
                               data={"csrf_token": _csrf(admin_client)},
                               follow_redirects=True)
        assert rv.status_code == 200
        # Blocked: still present …
        assert "sd-hist-user" in _usernames()
        # … and steered to disable.
        assert b"cannot be deleted" in rv.data

    def test_user_without_history_is_deleted(self, admin_client):
        """A freshly-created user with no footprint IS deleted — the gate does
        not over-block."""
        from services.auth import create_user
        create_user("sd-clean-user", "TestPass1!", full_name="Clean User", role="staff")
        assert "sd-clean-user" in _usernames()

        rv = admin_client.post("/delete-user/sd-clean-user",
                               data={"csrf_token": _csrf(admin_client)},
                               follow_redirects=True)
        assert rv.status_code == 200
        assert "sd-clean-user" not in _usernames()

    def test_release_collector_user_is_blocked(self, admin_client):
        """End-to-end: a user recorded as a release collector is blocked (the
        document_releases branch, the one rename_user misses)."""
        from services.auth import create_user
        from services.database import create_document_release
        create_user("sd-rel-user", "TestPass1!", full_name="Rel User", role="staff")
        create_document_release(
            "sd-rel-doc-route", released_by="somestaff",
            collector_name="Rel User", collector_username="sd-rel-user",
        )
        rv = admin_client.post("/delete-user/sd-rel-user",
                               data={"csrf_token": _csrf(admin_client)},
                               follow_redirects=True)
        assert rv.status_code == 200
        assert "sd-rel-user" in _usernames()
        assert b"cannot be deleted" in rv.data


# ── Pre-existing guards must still hold (unchanged by this feature) ──────────

class TestExistingGuardsUnchanged:
    def test_main_admin_self_delete_still_blocked(self, admin_client):
        """Deleting the logged-in env-admin (self AND main admin) is still
        refused — the new elif did not disturb the earlier guards."""
        rv = admin_client.post(f"/delete-user/{os.environ['ADMIN_USERNAME']}",
                               data={"csrf_token": _csrf(admin_client)},
                               follow_redirects=True)
        assert rv.status_code == 200
        assert b"Cannot delete the main admin account" in rv.data
