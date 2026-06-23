"""
tests/test_transfer_office_level.py — Office-level transfer behavior.

Covers the step-3 change: a transfer to an office with no registered staff
is allowed (pending_at_staff stays empty), while a transfer with neither a
staff member nor an office is still rejected.
"""
import pytest

from services.documents import save_doc, get_doc
from services.misc import save_office


def _make_doc(doc_id="OFFICEDOC1"):
    save_doc({
        "id": doc_id,
        "doc_name": "Office-level Test Doc",
        "status": "Logged",
        "logged_by": "someoneelse",
        "original_logged_by": "someoneelse",
    })
    return doc_id


def _csrf(client):
    """Seed the session and return the app's CSRF token (manual guard in app.py)."""
    client.get("/login")
    with client.session_transaction() as sess:
        return sess.get("csrf_token", "")


def _location(rv):
    return rv.headers.get("Location", "")


class TestOfficeLevelTransfer:
    def test_rejects_when_both_staff_and_office_empty(self, admin_client):
        doc_id = _make_doc("REJECTDOC")
        rv = admin_client.post(
            f"/transfer/{doc_id}",
            data={"transfer_type": "outside_office", "new_staff": "", "new_office": "",
                  "csrf_token": _csrf(admin_client)},
            follow_redirects=False,
        )
        # Rejected → redirect back to the transfer page (not /login), no transfer.
        assert rv.status_code == 302
        assert f"/transfer/{doc_id}" in _location(rv)
        doc = get_doc(doc_id)
        assert doc.get("transfer_status") != "pending"
        assert not doc.get("pending_at_office")

    def test_rejects_invalid_office(self, admin_client):
        doc_id = _make_doc("BADOFFICEDOC")
        rv = admin_client.post(
            f"/transfer/{doc_id}",
            data={"transfer_type": "outside_office",
                  "new_staff": "", "new_office": "Nonexistent Office XYZ",
                  "csrf_token": _csrf(admin_client)},
            follow_redirects=False,
        )
        assert rv.status_code == 302
        assert f"/transfer/{doc_id}" in _location(rv)
        doc = get_doc(doc_id)
        assert doc.get("transfer_status") != "pending"

    def test_staffed_office_requires_specific_staff(self, admin_client):
        # An office that HAS registered staff must not be routed office-level:
        # submitting with empty new_staff + that office should be rejected.
        from services.auth import create_user
        save_office("Finance Office", "testadmin", "")
        create_user("financeguy", "FinancePass1!", full_name="Finance Guy",
                    role="staff", office="Finance Office")
        doc_id = _make_doc("STAFFEDOFFICEDOC")
        rv = admin_client.post(
            f"/transfer/{doc_id}",
            data={"transfer_type": "outside_office",
                  "new_staff": "", "new_office": "Finance Office",
                  "csrf_token": _csrf(admin_client)},
            follow_redirects=False,
        )
        # Rejected by the guard → back to the transfer page (not /login), no transfer.
        assert rv.status_code == 302
        assert f"/transfer/{doc_id}" in _location(rv)
        doc = get_doc(doc_id)
        assert doc.get("transfer_status") != "pending"
        assert not doc.get("pending_at_office")
        assert not (doc.get("travel_log") or [])

    def test_office_level_transfer_succeeds_staffless(self, admin_client):
        save_office("Records Section", "testadmin", "")
        doc_id = _make_doc("OKOFFICEDOC")
        rv = admin_client.post(
            f"/transfer/{doc_id}",
            data={"transfer_type": "outside_office",
                  "new_staff": "", "new_office": "Records Section",
                  "csrf_token": _csrf(admin_client)},
            follow_redirects=False,
        )
        assert rv.status_code == 302
        doc = get_doc(doc_id)
        assert doc.get("transfer_status") == "pending"
        assert doc.get("pending_at_staff") == ""
        assert doc.get("pending_at_staff_name") == ""
        assert doc.get("pending_at_office") == "Records Section"
        assert doc.get("transferred_to_office") == "Records Section"
        assert doc.get("status") == "Routed"

        # The timeline must NOT be silently empty for an office-level record.
        travel_log = doc.get("travel_log") or []
        assert len(travel_log) >= 1, "office-level transfer wrote no travel_log entry"
        entry = travel_log[-1]
        assert entry.get("office") == "Records Section"
        assert "Routed" in (entry.get("action") or "")
        assert entry.get("remarks") == "Transferred to the office's general queue (Records Section)."
        assert entry.get("officer")        # officer is recorded, not blank
        assert entry.get("timestamp")       # timestamp is recorded
