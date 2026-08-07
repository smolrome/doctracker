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


# 5. History dedupes consecutive same-office entries. Staff name is now surfaced
#    ONLY in detail.officer_name; remarks and raw action are STILL never leaked.
def test_history_dedupes_surfaces_officer_in_detail_only():
    doc = {
        "status": "Received",
        "travel_log": [
            {"office": "Records Section", "action": "Document Submitted by Client - Pending at Jane Smith",
             "officer": "Client Person", "timestamp": "2026-07-01T09:00:00",
             "remarks": "Submitted via client portal. Target office: Records."},
            # same office + same bucket noise → should collapse:
            {"office": "Records Section", "action": "Document Submitted by Client - Pending at Jane Smith",
             "officer": "Client Person", "timestamp": "2026-07-01T09:01:00",
             "remarks": "LEAKED_REMARK_TEXT should never reach the client"},
            # officer given as a USERNAME → must resolve to the full name in detail:
            {"office": "Records Section", "action": "Document Received",
             "officer": "jsmith", "timestamp": "2026-07-01T10:00:00",
             "remarks": "Document received and accepted by Jane Smith."},
            {"office": "Cash Unit", "action": "Routed — (Outside Office) (Cycle 1)",
             "officer": "Big Boss", "timestamp": "2026-07-02T08:00:00",
             "remarks": "Transferred to LEAKED_REMARK_TEXT (Cash Unit)."},
        ],
    }
    view = build_client_track_view(doc, USERS)
    history = view["history"]

    # 4 raw entries → 3 after collapsing the duplicate submitted entry.
    assert len(history) == 3
    # Each item keeps the collapsed view AND gains a nested detail block.
    ALLOWED_DETAIL_KEYS = {"label", "office", "officer_name", "date_time",
                           "actor_role", "recipient_name"}
    ACTOR_ROLES = {"Received by", "Sent by", "Released by", "Handled by",
                   "Logged by", "By"}
    for item in history:
        assert {"office", "label", "date"} <= set(item.keys())
        assert "detail" in item
        d = item["detail"]
        # detail keys are drawn only from the safe allow-list (base 5 keys, plus
        # recipient_name on the latest transfer item):
        assert {"label", "office", "officer_name", "date_time", "actor_role"} <= set(d.keys())
        assert set(d.keys()) <= ALLOWED_DETAIL_KEYS
        # actor_role is a FIXED-VOCABULARY prefix, never free text:
        assert d["actor_role"] in ACTOR_ROLES
        # remarks/raw-action fields never appear on the item or in detail:
        assert "remarks" not in item and "remarks" not in d
        assert "action" not in item and "action" not in d

    # Officer name IS now surfaced — and a bare username resolves to the full name.
    received = next(h for h in history if h["label"] == "Received & being processed")
    assert received["detail"]["officer_name"] == "Jane Smith"   # jsmith → Jane Smith
    assert received["detail"]["actor_role"] == "Received by"
    # date_time carries date + time (top-level date stays date-only).
    assert received["detail"]["date_time"] == "2026-07-01T10:00"
    assert received["date"] == "2026-07-01"

    # Remarks text (and its fragments) must appear NOWHERE — including in detail.
    blob = json.dumps(history)
    assert "LEAKED_REMARK_TEXT" not in blob        # remarks never leak
    assert "accepted by" not in blob               # no remark fragments


# 5b. Raw action strings are NEVER surfaced — only the bucketed label. A staff
#     name embedded in the action f-string must not reach the client output.
def test_history_never_surfaces_raw_action():
    doc = {
        "status": "Released",
        "travel_log": [
            # Real collector-release shape: "Released to {name} of {origin} by {staff}".
            {"office": "Cash Unit",
             "action": "Released to SECRET_PERSON of SECRET_ORIGIN by Jane Smith",
             "officer": "jsmith", "timestamp": "2026-07-03T11:00:00",
             "remarks": "contact: 0917-xxx"},
        ],
    }
    view = build_client_track_view(doc, USERS)
    blob = json.dumps(view["history"])
    # Only the bucketed label is used, so neither the collector name nor origin
    # from the raw action string ever appears; nor does the remark.
    assert "SECRET_PERSON" not in blob
    assert "SECRET_ORIGIN" not in blob
    assert "contact" not in blob
    # The "released to … by …" signature classifies this as a collector hand-off,
    # but the label itself carries NO name — the collector's identity never leaks.
    assert view["history"][0]["label"] == "Released to collector"
    assert view["history"][0]["detail"]["actor_role"] == "Released by"


# 5b-ii. An ORIGIN-LESS collector release ("Released to {name} by {staff}" — the
#     origin field is optional on every surface) must STILL classify as a
#     collector hand-off. This is the case the old " of … by " pattern missed.
def test_history_originless_collector_release_is_collector():
    doc = {
        "status": "Released",
        "travel_log": [
            {"office": "Cash Unit", "action": "Released to SECRET_PERSON by Jane Smith",
             "officer": "jsmith", "timestamp": "2026-07-03T11:00:00", "remarks": "x"},
        ],
    }
    view = build_client_track_view(doc, USERS)
    assert view["history"][0]["label"] == "Released to collector"
    assert "SECRET_PERSON" not in json.dumps(view["history"])


# 5b-iii. Non-collector release actions must NOT be pulled into the collector
#     bucket by the looser " by " match. "Released by Originating Staff" contains
#     " by " but is NOT a collector hand-off (no "released to "), and the slip/
#     office releases contain neither marker.
def test_history_non_collector_releases_stay_office():
    for action in (
        "Released by Originating Staff",     # has " by " — the trap case
        "Released via Routing Slip",
        "Released — Routed to Cash Unit",
        "Released from Records Section",
        "Document Released / Picked Up",
        "Document Released from Office",
    ):
        assert bucket_label(action) == "Released from the office", action


# 5c. Transient recipient — on a multi-transfer doc, the doc-level
#     pending_at_staff_name (latest pending recipient) attaches ONLY to the
#     latest transfer/route item, never to earlier hops or non-transfer items.
def test_recipient_name_only_on_latest_transfer():
    doc = {
        "status": "Routed",
        "transfer_status": "pending",
        # latest pending recipient — a resolved staff full name, never a contact:
        "pending_at_staff_name": "Cherry Medalla",
        # contact-ish fields that must NEVER surface in the client history:
        "recipient_contact": "0917-111-2222",
        "collector_contact": "0917-333-4444",
        "travel_log": [
            {"office": "Records Section", "action": "Document Received",
             "officer": "jsmith", "timestamp": "2026-07-01T09:00:00", "remarks": "r"},
            # first hop (earlier transfer) — must NOT carry a recipient name:
            {"office": "Records Section",
             "action": "Transferred to Big Boss — (Inside Office) (Cycle 1)",
             "officer": "jsmith", "timestamp": "2026-07-02T09:00:00",
             "remarks": "Transferred to Big Boss."},
            # second hop (latest transfer) — SHOULD carry pending_at_staff_name:
            {"office": "Cash Unit",
             "action": "Routed to Cherry Medalla — (Outside Office) (Cycle 2)",
             "officer": "boss", "timestamp": "2026-07-03T09:00:00",
             "remarks": "Routed to Cherry Medalla (Cash Unit)."},
        ],
    }
    view = build_client_track_view(doc, USERS)
    history = view["history"]

    transfers = [h for h in history if h["detail"]["actor_role"] == "Sent by"]
    assert len(transfers) == 2
    earlier, latest = transfers[0], transfers[1]

    # Only the latest transfer item gets recipient_name = pending_at_staff_name.
    assert "recipient_name" not in earlier["detail"]
    assert latest["detail"]["recipient_name"] == "Cherry Medalla"
    # Non-transfer items never carry recipient_name.
    for h in history:
        if h["detail"]["actor_role"] != "Sent by":
            assert "recipient_name" not in h["detail"]

    # CONTACT INVARIANT — no contact number leaks anywhere in the history.
    blob = json.dumps(history)
    assert "0917-111-2222" not in blob
    assert "0917-333-4444" not in blob
    assert "recipient_contact" not in blob and "collector_contact" not in blob


# 5d. When pending_at_staff_name is empty (e.g. already accepted / no transfer),
#     NO recipient_name is attached — the field is inherently transient.
def test_recipient_name_absent_when_pending_cleared():
    doc = {
        "status": "Received",
        "pending_at_staff_name": "",   # cleared on acceptance
        "travel_log": [
            {"office": "Records Section",
             "action": "Transferred to Big Boss — (Inside Office) (Cycle 1)",
             "officer": "jsmith", "timestamp": "2026-07-02T09:00:00", "remarks": "r"},
        ],
    }
    view = build_client_track_view(doc, USERS)
    assert view["history"][0]["label"] == "Transferred — Inside Office"
    assert "recipient_name" not in view["history"][0]["detail"]


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
