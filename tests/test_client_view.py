"""
tests/test_client_view.py — Unit tests for the client-safe track view-model.

These test the pure transform services.client_view.build_client_track_view —
no Flask app or DB required. They lock in the Milestone 1 guarantees:
  - current-status block resolves handler + office by branching on status
  - office-level (no-staff) transfer shows an "ask at the office" message
  - accepted docs read from accepted_by_name, not the cleared pending fields
  - rejected docs expose the rejection reason and state "returned"
  - history is deduped and NEVER leaks officer/remarks text
  - a novel/unmapped action falls back to a generic label, never the raw string
"""

import json

from services.client_view import build_client_track_view, bucket_label


USERS = [
    {"username": "jsmith", "full_name": "Jane Smith", "role": "staff", "office": "Records Section"},
    {"username": "boss",   "full_name": "Big Boss",   "role": "admin", "office": "Records Section"},
]


# 1. Pending at a named staff → current shows that staff name + office.
def test_pending_named_staff():
    doc = {
        "status": "Transferred",
        "transfer_status": "pending",
        "pending_at_staff": "jsmith",
        "pending_at_staff_name": "Jane Smith",
        "pending_at_office": "Records Section",
        "travel_log": [],
    }
    view = build_client_track_view(doc, USERS)
    cur = view["current"]
    assert cur["state"] == "pending"
    assert cur["handler_name"] == "Jane Smith"
    assert cur["location_office"] == "Records Section"
    assert cur["handler_role_label"] == "Receiving Officer"  # never the raw "staff" token


def test_pending_resolves_username_when_name_missing():
    """pending_at_staff_name absent → resolve the username via the users list."""
    doc = {
        "status": "Routed",
        "transfer_status": "pending",
        "pending_at_staff": "jsmith",
        "pending_at_office": "Records Section",
        "travel_log": [],
    }
    view = build_client_track_view(doc, USERS)
    assert view["current"]["handler_name"] == "Jane Smith"
    assert view["current"]["handler_role_label"] == "Receiving Officer"


# 2. Pending at an office with NO staff (office-level) → "ask at the office".
def test_pending_office_level_no_staff():
    doc = {
        "status": "Routed",
        "transfer_status": "pending",
        "pending_at_staff": "",
        "pending_at_office": "Cash Unit",
        "travel_log": [],
    }
    view = build_client_track_view(doc, USERS)
    cur = view["current"]
    assert cur["handler_name"] is None            # no blank name
    assert cur["location_office"] == "Cash Unit"
    assert "ask at the office" in cur["message"].lower()


# 3. An accepted doc → handler comes from accepted_by_name, not cleared pending_at_staff.
def test_accepted_uses_accepted_by_name():
    doc = {
        "status": "Received",
        "transfer_status": "accepted",
        "accepted_by": "jsmith",
        "accepted_by_name": "Jane Smith",
        "logged_by": "jsmith",
        "logged_by_office": "Records Section",
        # pending fields were cleared on acceptance:
        "pending_at_staff": "",
        "pending_at_office": "",
        "travel_log": [],
    }
    view = build_client_track_view(doc, USERS)
    cur = view["current"]
    assert cur["state"] == "processing"
    assert cur["handler_name"] == "Jane Smith"
    assert cur["location_office"] == "Records Section"


# 4. A rejected doc → shows rejection_reason, state "returned".
def test_rejected_shows_reason_and_returned_state():
    doc = {
        "status": "Rejected",
        "transfer_status": "rejected",
        "rejection_reason": "Missing required attachment.",
        "pending_at_staff": "",
        "pending_at_office": "",
        "travel_log": [],
    }
    view = build_client_track_view(doc, USERS)
    assert view["current"]["state"] == "returned"
    assert view["current"]["handler_name"] is None
    assert view["rejection_reason"] == "Missing required attachment."


def test_rejection_reason_hidden_when_not_rejected():
    doc = {"status": "Received", "rejection_reason": "should not appear", "travel_log": []}
    view = build_client_track_view(doc, USERS)
    assert view["rejection_reason"] is None


# 5. History dedupes consecutive same-office entries and NEVER leaks officer/remarks.
def test_history_dedupes_and_hides_internal_text():
    doc = {
        "status": "Received",
        "travel_log": [
            {"office": "Records Section", "action": "Document Submitted by Client - Pending at Jane Smith",
             "officer": "Client Person", "timestamp": "2026-07-01T09:00:00",
             "remarks": "Submitted via client portal. Target office: Records."},
            # same office + same bucket noise → should collapse:
            {"office": "Records Section", "action": "Document Submitted by Client - Pending at Jane Smith",
             "officer": "SECRET_OFFICER_NAME", "timestamp": "2026-07-01T09:01:00",
             "remarks": "LEAKED_REMARK_TEXT should never reach the client"},
            {"office": "Records Section", "action": "Document Received",
             "officer": "SECRET_OFFICER_NAME", "timestamp": "2026-07-01T10:00:00",
             "remarks": "Document received and accepted by SECRET_OFFICER_NAME."},
            {"office": "Cash Unit", "action": "Routed — (Outside Office) (Cycle 1)",
             "officer": "SECRET_OFFICER_NAME", "timestamp": "2026-07-02T08:00:00",
             "remarks": "Transferred to SECRET_OFFICER_NAME (Cash Unit)."},
        ],
    }
    view = build_client_track_view(doc, USERS)
    history = view["history"]

    # 4 raw entries → 3 after collapsing the duplicate submitted entry.
    assert len(history) == 3
    # Each item exposes only office/label/date.
    for item in history:
        assert set(item.keys()) == {"office", "label", "date"}

    blob = json.dumps(history)
    assert "SECRET_OFFICER_NAME" not in blob      # officer never leaks
    assert "LEAKED_REMARK_TEXT" not in blob        # remarks never leak
    assert "accepted by" not in blob               # no remark fragments


# 6. An unmapped/novel action → generic label, raw string not shown.
def test_unmapped_action_falls_back_to_generic():
    assert bucket_label("Quantum entanglement of document") == "Document processed"
    doc = {
        "status": "Received",
        "travel_log": [
            {"office": "Records Section", "action": "Zorptastic frobnication event",
             "officer": "x", "timestamp": "2026-07-01T09:00:00", "remarks": "internal"},
        ],
    }
    view = build_client_track_view(doc, USERS)
    labels = [h["label"] for h in view["history"]]
    assert labels == ["Document processed"]
    assert "Zorptastic" not in json.dumps(view["history"])


# Extra: "Released — Routed to X" must classify as RELEASED, not routed (ordering).
def test_released_beats_routed_ordering():
    assert bucket_label("Released — Routed to Cash Unit") == "Released from the office"


# Extra: released doc → done state, no handler.
def test_released_done_state():
    doc = {"status": "Released", "logged_by_office": "Records Section", "travel_log": []}
    view = build_client_track_view(doc, USERS)
    assert view["current"]["state"] == "done"
    assert view["current"]["handler_name"] is None


# Extra: status_display covers all 11 real statuses with non-empty friendly copy.
def test_status_display_covers_all_statuses():
    for s in ["Pending", "Received", "In Review", "Routed", "Transferred",
              "Released", "On Hold", "Rejected", "Returned", "Logged", "Archived"]:
        sd = build_client_track_view({"status": s, "travel_log": []}, USERS)["status_display"]
        assert sd["label"] and sd["sub_text"] and sd["icon"]


# Extra: never mutate the input document / travel_log.
def test_does_not_mutate_document():
    tl = [{"office": "A", "action": "Document Received", "officer": "z",
           "timestamp": "2026-07-01T09:00:00", "remarks": "r"}]
    doc = {"status": "Received", "travel_log": tl}
    build_client_track_view(doc, USERS)
    assert doc["travel_log"] is tl and len(tl) == 1
    assert tl[0] == {"office": "A", "action": "Document Received", "officer": "z",
                     "timestamp": "2026-07-01T09:00:00", "remarks": "r"}
