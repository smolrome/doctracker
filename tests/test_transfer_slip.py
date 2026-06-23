"""
tests/test_transfer_slip.py — Transfer → routing-slip integration.

Covers the decision: an EXTERNAL transfer (destination office differs from the
logged-in staff's own office) creates a routing_slips record and redirects to
the printable slip page; an INTERNAL transfer (same office) creates NO slip.

Authority for external/internal is the office comparison, so a transfer where
transfer_type=="outside_office" but the chosen office equals the sender's own
office is treated as INTERNAL.
"""

import os
import uuid
import pytest

os.environ.setdefault("SECRET_KEY", "j" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


def _make_doc(owner="staffuser", status="Received"):
    from services.documents import insert_doc
    doc = {
        "id":         str(uuid.uuid4())[:8].upper(),
        "doc_id":     f"REF-2024-{uuid.uuid4().hex[:4].upper()}",
        "doc_name":   "Transfer Slip Doc",
        "status":     status,
        "logged_by":  owner,            # makes `owner` allowed to transfer it
    }
    insert_doc(doc)
    return doc


def _set_office(client, office):
    with client.session_transaction() as s:
        s["office"] = office


def _csrf(client):
    # The app enforces CSRF via an app-level before_request hook (app.py
    # csrf_check) that is independent of WTF_CSRF_ENABLED, so POSTs must carry
    # the session's token.
    client.get("/login")
    with client.session_transaction() as s:
        return s.get("csrf_token", "")


@pytest.fixture
def external_office():
    """A saved office with no registered staff (valid office-level target)."""
    from services.misc import save_office
    save_office("External Office", "testadmin")
    return "External Office"


class TestExternalTransferCreatesSlip:
    def test_external_office_transfer_creates_slip_and_redirects(
        self, staff_client, external_office
    ):
        from services.misc import get_routing_slip
        csrf = _csrf(staff_client)
        # Sender sits in a DIFFERENT office than the target → external.
        _set_office(staff_client, "Records Office")
        doc = _make_doc()

        rv = staff_client.post(
            "/transfer-batch",
            data={
                "doc_ids":       doc["id"],
                "transfer_type": "outside_office",
                "new_office":    external_office,
                "new_staff":     "",
                "csrf_token":    csrf,
            },
            follow_redirects=False,
        )

        # Redirects to the printable slip page.
        assert rv.status_code == 302
        loc = rv.headers.get("Location", "")
        assert "/routing-slip/" in loc, f"expected slip redirect, got {loc}"

        slip_id = loc.split("/routing-slip/")[1].split("?")[0]
        slip = get_routing_slip(slip_id)
        assert slip is not None
        assert slip["destination"] == external_office
        assert doc["id"] in slip["doc_ids"]


class TestInternalTransferCreatesNoSlip:
    def test_internal_same_office_transfer_creates_no_slip(
        self, staff_client, external_office
    ):
        from services.misc import get_all_routing_slips
        csrf = _csrf(staff_client)
        # Sender's own office equals the target office → internal, even though
        # transfer_type is "outside_office". No slip must be created.
        _set_office(staff_client, external_office)
        doc = _make_doc()

        before = len(get_all_routing_slips())

        rv = staff_client.post(
            "/transfer-batch",
            data={
                "doc_ids":       doc["id"],
                "transfer_type": "outside_office",
                "new_office":    external_office,
                "new_staff":     "",
                "csrf_token":    csrf,
            },
            follow_redirects=False,
        )

        assert rv.status_code == 302
        loc = rv.headers.get("Location", "")
        assert "/routing-slip/" not in loc, f"internal transfer should not route to a slip: {loc}"

        after = len(get_all_routing_slips())
        assert after == before, "internal transfer must not create a routing slip"
