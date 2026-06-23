"""
tests/test_transfer_group_auth.py — Shared-dashboard transfer authorization.

Covers the expansion in routes/dashboard.py:
  §1  A group-mate (shares a has_shared_dashboard group with the doc's owner,
      but is NOT the owner) may transfer the doc — single and batch.
  §1  A user with no group membership and no ownership claim may NOT — single
      returns 403 (AJAX), batch counts it as skipped_unauth with no success.
  §3  A group-mate transfer writes a travel_log remark naming BOTH the actor and
      the original owner; an owner's own transfer omits the provenance suffix.
  §4  Honest batch feedback: partial → warning with counts (no silent drop);
      zero authorized → error (not success), no slip redirect.

USE_DB is False in tests, so get_group_usernames() returns [] by default; the
group-mate scenarios monkeypatch services.database.get_group_usernames. Every
POST carries csrf_token (app.py's before_request guard redirects to /login
otherwise) and assertions target the real redirect destination, not /login.
"""
import uuid
import pytest

from services.auth import create_user
from services.documents import insert_doc, get_doc

OFFICE = "Main Office"


# ── helpers ───────────────────────────────────────────────────────────────────

def _csrf(client):
    client.get("/login")
    with client.session_transaction() as s:
        return s.get("csrf_token", "")


def _set_office(client, office=OFFICE):
    with client.session_transaction() as s:
        s["office"] = office


def _patch_group(monkeypatch, mapping):
    """
    Make get_group_transfer_usernames(u) return mapping[u] (default []).

    The transfer gate keys on get_group_transfer_usernames (dashboard AND
    transfer flags both ON); these tests simulate that "both ON" state.
    """
    import services.database as db
    monkeypatch.setattr(db, "get_group_transfer_usernames", lambda u: mapping.get(u, []))


def _make_doc(owner, status="Received"):
    doc_id = uuid.uuid4().hex[:8].upper()
    insert_doc({
        "id":                 doc_id,
        "doc_id":             f"REF-{uuid.uuid4().hex[:4].upper()}",
        "doc_name":           "Group Auth Doc",
        "status":             status,
        "logged_by":          owner,
        "original_logged_by": owner,
        "travel_log":         [],
    })
    return doc_id


@pytest.fixture(autouse=True)
def _people():
    """Owner, a recipient (valid internal staff target), and a stranger owner."""
    create_user("owneruser",     "OwnerPass1!",  full_name="Owner User",
                role="staff", office=OFFICE)
    create_user("recipientuser", "RecipPass1!",  full_name="Recipient User",
                role="staff", office=OFFICE)
    create_user("stranger",      "StrangerP1!",  full_name="Stranger User",
                role="staff", office=OFFICE)
    yield


def _loc(rv):
    return rv.headers.get("Location", "")


# ── §1 group-mate CAN transfer ────────────────────────────────────────────────

class TestGroupMateCanTransfer:
    def test_single_group_mate_can_transfer(self, staff_client, monkeypatch):
        # staffuser shares a shared-dashboard group with owneruser but is NOT
        # the owner of the doc.
        _patch_group(monkeypatch, {"staffuser": ["owneruser"]})
        _set_office(staff_client)
        doc_id = _make_doc("owneruser")

        rv = staff_client.post(
            f"/transfer/{doc_id}",
            data={"transfer_type": "inside_office",
                  "new_staff": "recipientuser", "new_office": "",
                  "csrf_token": _csrf(staff_client)},
            follow_redirects=False,
        )
        assert rv.status_code == 302
        assert "/login" not in _loc(rv)
        assert f"/view/{doc_id}" in _loc(rv)

        doc = get_doc(doc_id)
        assert doc.get("transfer_status") == "pending"
        # §2 attribution: the REAL actor, not the owner.
        assert doc.get("transferred_by") == "staffuser"

    def test_batch_group_mate_can_transfer(self, staff_client, monkeypatch):
        _patch_group(monkeypatch, {"staffuser": ["owneruser"]})
        _set_office(staff_client)
        doc_id = _make_doc("owneruser")

        rv = staff_client.post(
            "/transfer-batch",
            data={"doc_ids": doc_id, "transfer_type": "inside_office",
                  "new_staff": "recipientuser", "new_office": "",
                  "csrf_token": _csrf(staff_client)},
            follow_redirects=False,
        )
        assert rv.status_code == 302
        assert "/login" not in _loc(rv)

        doc = get_doc(doc_id)
        assert doc.get("transfer_status") == "pending"
        assert doc.get("transferred_by") == "staffuser"


# ── §1 no group / no ownership CANNOT transfer ────────────────────────────────

class TestNonOwnerNonGroupCannotTransfer:
    def test_single_unauthorized_returns_403(self, staff_client, monkeypatch):
        _patch_group(monkeypatch, {})            # no group membership
        _set_office(staff_client)
        doc_id = _make_doc("owneruser")

        rv = staff_client.post(
            f"/transfer/{doc_id}",
            data={"transfer_type": "inside_office",
                  "new_staff": "recipientuser", "new_office": "",
                  "csrf_token": _csrf(staff_client)},
            headers={"X-Requested-With": "XMLHttpRequest"},
            follow_redirects=False,
        )
        assert rv.status_code == 403
        doc = get_doc(doc_id)
        assert doc.get("transfer_status") != "pending"
        assert doc.get("transferred_by") != "staffuser"

    def test_batch_unauthorized_skipped_no_success(self, staff_client, monkeypatch):
        _patch_group(monkeypatch, {})
        _set_office(staff_client)
        doc_id = _make_doc("owneruser")

        rv = staff_client.post(
            "/transfer-batch",
            data={"doc_ids": doc_id, "transfer_type": "inside_office",
                  "new_staff": "recipientuser", "new_office": "",
                  "csrf_token": _csrf(staff_client)},
            follow_redirects=True,
        )
        # Lands on the dashboard (not /login), shows an honest error, no transfer.
        assert b"No documents were transferred" in rv.data
        assert b"1 not permitted" in rv.data
        doc = get_doc(doc_id)
        assert doc.get("transfer_status") != "pending"


# ── §4 honest batch feedback ──────────────────────────────────────────────────

class TestHonestBatchFeedback:
    def test_partial_batch_warns_with_counts(self, staff_client, monkeypatch):
        # Authorized on the owneruser doc (group-mate), NOT on the stranger doc.
        _patch_group(monkeypatch, {"staffuser": ["owneruser"]})
        _set_office(staff_client)
        ok_id  = _make_doc("owneruser")
        bad_id = _make_doc("stranger")

        rv = staff_client.post(
            "/transfer-batch",
            data={"doc_ids": f"{ok_id},{bad_id}", "transfer_type": "inside_office",
                  "new_staff": "recipientuser", "new_office": "",
                  "csrf_token": _csrf(staff_client)},
            follow_redirects=True,
        )
        # WARNING naming the skip — not a silent drop, not a plain success.
        assert b"Skipped 1 not permitted" in rv.data
        assert get_doc(ok_id).get("transfer_status") == "pending"
        assert get_doc(bad_id).get("transfer_status") != "pending"

    def test_zero_authorized_batch_errors_no_slip(self, staff_client, monkeypatch):
        _patch_group(monkeypatch, {})            # no group; owns nothing here
        _set_office(staff_client)
        a_id = _make_doc("owneruser")
        b_id = _make_doc("stranger")

        rv = staff_client.post(
            "/transfer-batch",
            data={"doc_ids": f"{a_id},{b_id}", "transfer_type": "inside_office",
                  "new_staff": "recipientuser", "new_office": "",
                  "csrf_token": _csrf(staff_client)},
            follow_redirects=False,
        )
        # ERROR path: redirect to the dashboard, never to a routing slip.
        assert rv.status_code == 302
        assert "/routing-slip/" not in _loc(rv)
        assert "/login" not in _loc(rv)
        assert get_doc(a_id).get("transfer_status") != "pending"
        assert get_doc(b_id).get("transfer_status") != "pending"


# ── §3 provenance line ────────────────────────────────────────────────────────

class TestProvenanceRemark:
    def test_group_mate_transfer_records_actor_and_owner(self, staff_client, monkeypatch):
        _patch_group(monkeypatch, {"staffuser": ["owneruser"]})
        _set_office(staff_client)
        doc_id = _make_doc("owneruser")

        staff_client.post(
            f"/transfer/{doc_id}",
            data={"transfer_type": "inside_office",
                  "new_staff": "recipientuser", "new_office": "",
                  "csrf_token": _csrf(staff_client)},
            follow_redirects=False,
        )
        remark = (get_doc(doc_id).get("travel_log") or [])[-1].get("remarks", "")
        # Both the actor (full name) and the original owner appear.
        assert "Staff User" in remark
        assert "owneruser" in remark
        assert "acting on document originated by" in remark

    def test_owner_own_transfer_has_no_provenance_suffix(self, staff_client, monkeypatch):
        _patch_group(monkeypatch, {})
        _set_office(staff_client)
        doc_id = _make_doc("staffuser")          # staffuser owns it

        staff_client.post(
            f"/transfer/{doc_id}",
            data={"transfer_type": "inside_office",
                  "new_staff": "recipientuser", "new_office": "",
                  "csrf_token": _csrf(staff_client)},
            follow_redirects=False,
        )
        remark = (get_doc(doc_id).get("travel_log") or [])[-1].get("remarks", "")
        assert "acting on document originated by" not in remark
