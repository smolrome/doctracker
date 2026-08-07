"""
services/client_view.py — Client-facing presentation layer for document tracking.

Pure, read-only transforms that turn a raw document (the same dict staff see) into
a CLIENT-SAFE view-model. This module deliberately lives OUTSIDE
services/documents.py so it can never be pulled into staff-facing rendering
(detail.html) or the mobile API.

Guarantees:
  - Never mutates the document or its travel_log.
  - Never surfaces the internal `officer` or `remarks` fields to the client
    (the single exception is `rejection_reason`, the one internal note a client
    is entitled to see).
  - Internal role tokens ("staff"/"admin") are relabelled to a client-friendly
    role label — the raw token is never shown.

The document `action` strings are f-strings, NOT an enum (see the real
vocabulary in the codebase), so action classification is done by LOWERCASED
SUBSTRING matching, never equality. Anything unmatched falls back to a safe
generic label — the raw action string is never rendered.
"""

from __future__ import annotations


# ── Action → client-friendly classification (lowercased-substring, never eq) ────
#
# The travel_log `action` strings are f-strings (they embed staff names and free
# text), NOT an enum, so classification is done by LOWERCASED SUBSTRING matching.
# `_classify` returns three derived, SAFE values — the raw action is never echoed:
#
#   label       the client-visible line (specific, but carries NO person name)
#   actor_role  a FIXED-VOCABULARY role prefix for the expanded detail — one of a
#               closed set of strings, never free text pulled from the entry
#   kind        a coarse class token used only to locate the latest transfer item
#
# ORDER MATTERS: `released` is checked before `transfer`/`rout` because
# "Released — Routed to X" contains both.

_ACTION_FALLBACK = "Document processed"


def _classify(action: str) -> tuple[str, str, str]:
    """Classify a raw travel_log action → (label, actor_role, kind).

    Pure and side-effect free. Uses lowercased substring matching, never
    equality, and NEVER returns any substring of the raw action — only the
    fixed, client-safe label / role / kind vocabularies below. An unrecognised
    action yields the safe generic fallback.
    """
    a = (action or "").lower()

    if "submitted" in a:
        return "Submitted to the office", "By", "submitted"

    # rejected/returned collapse to one client-facing outcome.
    if "rejected" in a or "returned" in a:
        return "Not accepted — returned", "Handled by", "rejected"

    # Released is checked BEFORE transfer/route: "Released — Routed to X" would
    # otherwise be mis-bucketed as a forward. The collector hand-off is the ONLY
    # release action of the form "Released to {name}[ of {origin}] by {staff}"
    # (blueprints/api.py) — it ALWAYS contains BOTH "released to " and " by ",
    # even when the origin is blank ("Released to Jane by Staff"). Every other
    # release action is a slip/office/originating close-out that lacks at least
    # one marker:
    #   "Released via Routing Slip"        — neither
    #   "Released from {office}"           — neither
    #   "Released — Routed to {office}"    — no "released to " (it's "…— routed")
    #   "Document Released / Picked Up"    — neither
    #   "Released by Originating Staff"    — has " by " but NOT "released to "
    # Requiring BOTH markers keeps "Released by Originating Staff" out of the
    # collector bucket. The collector's name and origin are never echoed.
    if "released" in a or "picked up" in a:
        if "released to " in a and " by " in a:
            return "Released to collector", "Released by", "released"
        return "Released from the office", "Released by", "released"

    if "received" in a or "accepted" in a:
        return "Received & being processed", "Received by", "received"

    # transfer/route/routed/reroute/rerouted — split inside-office vs outside by
    # the explicit "(Inside Office)" / "(Outside Office)" marker (or "routed").
    if "transfer" in a or "rout" in a:
        if "outside office" in a or "routed" in a:
            return "Forwarded — Another Office", "Sent by", "transfer"
        # "(Inside Office)" or a bare "transferred" both mean an in-office hop.
        return "Transferred — Inside Office", "Sent by", "transfer"

    if "assigned" in a:
        return "Assignment updated", "By", "assigned"
    if "hold" in a:
        return "Placed on hold", "By", "hold"
    if "logged" in a:
        return "Logged into the system", "Logged by", "logged"
    if "edited" in a:
        return "Details updated", "By", "edited"
    if "archived" in a:
        return "Archived", "By", "archived"

    return _ACTION_FALLBACK, "Handled by", "other"


def bucket_label(action: str) -> str:
    """Map a raw travel_log `action` string to a client-friendly label.

    Uses lowercased substring matching. Never returns the raw action string;
    an unrecognised action yields the safe generic fallback.
    """
    return _classify(action)[0]


def _bucket_key(action: str) -> str:
    """De-duplication key for the history walk.

    Keyed on the client-visible label so that ONLY genuinely-identical
    consecutive entries (same office AND same label) collapse — two different
    labels in the same office (e.g. a transfer then a release) stay distinct.
    Unmatched actions all share the fallback label, so they still de-dupe
    against each other.
    """
    return _classify(action)[0]


# ── Status → client-friendly display (covers ALL 11 real statuses) ─────────────

_STATUS_DISPLAY = {
    "Pending":     {"label": "Pending",     "icon": "⏳",
                    "sub_text": "Submitted — awaiting processing at the office."},
    "Received":    {"label": "Received",    "icon": "📥",
                    "sub_text": "Received and being processed at the office."},
    "In Review":   {"label": "In Review",   "icon": "🔎",
                    "sub_text": "Currently under review at the office."},
    "Routed":      {"label": "In Transit",  "icon": "🚚",
                    "sub_text": "Forwarded to another office for processing."},
    "Transferred": {"label": "In Transit",  "icon": "🚚",
                    "sub_text": "Being handed to another officer or office."},
    "Released":    {"label": "Released",    "icon": "✅",
                    "sub_text": "Processed and released from the office."},
    "On Hold":     {"label": "On Hold",     "icon": "⏸️",
                    "sub_text": "Temporarily on hold at the office."},
    "Rejected":    {"label": "Not Accepted", "icon": "❌",
                    "sub_text": "Document was not accepted. See the reason below."},
    "Returned":    {"label": "Returned",    "icon": "↩️",
                    "sub_text": "Returned to the sending office."},
    "Logged":      {"label": "Logged",      "icon": "🗒️",
                    "sub_text": "Recorded in the system."},
    "Archived":    {"label": "Archived",    "icon": "📦",
                    "sub_text": "Filed and archived by the office."},
}

_STATUS_FALLBACK = {"label": "In Progress", "icon": "📄",
                    "sub_text": "Your document is being handled by the office."}


def status_display(status: str) -> dict:
    """Return {label, sub_text, icon} for a document status. Safe for any value."""
    d = _STATUS_DISPLAY.get((status or "").strip())
    if d:
        return dict(d)
    return dict(_STATUS_FALLBACK)


# ── Role relabelling ───────────────────────────────────────────────────────────

def _role_label(role: str | None) -> str:
    """Relabel an internal role token to a client-friendly label.

    Never exposes the raw "staff"/"admin" token. Any handler is presented to the
    client as a "Receiving Officer".
    """
    return "Receiving Officer"


# ── User resolution ────────────────────────────────────────────────────────────

def _build_user_map(users) -> dict:
    """Index a list of user dicts by lowercased username."""
    m = {}
    for u in (users or []):
        uname = (u.get("username") or "").strip().lower()
        if uname:
            m[uname] = u
    return m


def _resolve_name(username: str, user_map: dict) -> str | None:
    """Resolve a username → full name via the user map, or None."""
    if not username:
        return None
    u = user_map.get(username.strip().lower())
    if not u:
        return None
    return u.get("full_name") or username


def _latest_office(doc) -> str | None:
    """Most recent non-empty office recorded in the travel_log, if any."""
    for entry in reversed(doc.get("travel_log") or []):
        office = (entry.get("office") or "").strip()
        if office:
            return office
    return None


# ── Current status block ───────────────────────────────────────────────────────

def _build_current(doc, user_map) -> dict:
    """Derive the prominent 'where is it / who holds it' block.

    Branches on transfer_status/status because the pending_* fields are CLEARED
    on acceptance and rejection — reading them blindly would show a stale or
    blank handler.
    """
    status         = (doc.get("status") or "").strip()
    transfer_state = (doc.get("transfer_status") or "").strip().lower()

    # ── Terminal: released ─────────────────────────────────────────────
    if status == "Released" or transfer_state == "released":
        return {
            "state":              "done",
            "location_office":    doc.get("logged_by_office") or _latest_office(doc),
            "handler_name":       None,
            "handler_role_label": None,
            "message":            "Your document has been released. The process is complete.",
        }

    # ── Bounced back to sender ─────────────────────────────────────────
    if status in ("Rejected", "Returned") or transfer_state == "rejected":
        return {
            "state":              "returned",
            "location_office":    None,
            "handler_name":       None,
            "handler_role_label": None,
            "message":            "Returned to the sending office.",
        }

    # ── Actively being worked (accepted) ───────────────────────────────
    if status == "Received" or transfer_state == "accepted":
        handler = (doc.get("accepted_by_name")
                   or _resolve_name(doc.get("accepted_by", ""), user_map)
                   or _resolve_name(doc.get("logged_by", ""), user_map))
        office  = doc.get("logged_by_office") or _latest_office(doc) or doc.get("pending_at_office")
        return {
            "state":              "processing",
            "location_office":    office or None,
            "handler_name":       handler or None,
            "handler_role_label": _role_label(None) if handler else None,
            "message":            ("Your document is being processed."
                                   if handler else
                                   "Your document is being processed at the office."),
        }

    # ── Pending / in transit — awaiting acceptance ─────────────────────
    if transfer_state == "pending" or status in ("Pending", "Routed", "Transferred", ""):
        office = (doc.get("pending_at_office")
                  or doc.get("transferred_to_office")
                  or _latest_office(doc))
        handler = (doc.get("pending_at_staff_name")
                   or _resolve_name(doc.get("pending_at_staff", ""), user_map))
        if handler:
            return {
                "state":              "pending",
                "location_office":    office or None,
                "handler_name":       handler,
                "handler_role_label": _role_label(None),
                "message":            "Please proceed to the office below and look for the officer named.",
            }
        # Office-level transfer: no specific officer assigned yet.
        if office:
            return {
                "state":              "pending",
                "location_office":    office,
                "handler_name":       None,
                "handler_role_label": None,
                "message":            f"At {office} — ask at the office (no specific officer assigned yet).",
            }
        return {
            "state":              "pending",
            "location_office":    None,
            "handler_name":       None,
            "handler_role_label": None,
            "message":            "Submitted — awaiting processing at the office.",
        }

    # ── Safe default ───────────────────────────────────────────────────
    return {
        "state":              "processing",
        "location_office":    doc.get("logged_by_office") or _latest_office(doc),
        "handler_name":       None,
        "handler_role_label": None,
        "message":            "Your document is being handled by the office.",
    }


# ── History (deduped movement list) ────────────────────────────────────────────

def _build_history(doc, user_map: dict | None = None) -> list:
    """Walk travel_log oldest→newest, emitting a de-duped movement list.

    Emits a new item only on a MEANINGFUL transition — the office changes OR the
    action bucket changes. Consecutive entries in the same office with the same
    bucket collapse into a single item.

    Each item carries the collapsed view — {office, label, date} — PLUS a nested
    `detail` block for the mobile expand-on-tap:
        {office, label, date, detail: {label, office, officer_name, date_time,
                                       actor_role[, recipient_name]}}

    The staff name is surfaced ONLY inside `detail.officer_name` (resolved
    username→full name via `user_map` when possible, else passed through) — it is
    never folded into the top-level `label` or `office`. `detail.actor_role` is a
    FIXED-VOCABULARY prefix ("Received by", "Sent by", …) chosen by action type,
    never free text from the entry. The raw `action` string is NEVER surfaced
    (only its bucketed `label`), because action f-strings embed staff names and
    free text. The internal `remarks` field is dropped entirely, incl. `detail`.

    Transient recipient: the LATEST transfer/route item additionally gets
    `detail.recipient_name` from the doc-level `pending_at_staff_name` (always a
    resolved staff full name — never a contact field, never the free-text
    `referred_to`). This reflects only the current pending recipient, so earlier
    transfer hops never carry it (avoids showing a stale/wrong name). It clears
    naturally once the recipient accepts (the write path blanks the field), after
    which the next "Received by" item carries the name instead.
    """
    user_map = user_map or {}
    history = []
    last_office = object()   # sentinel — guarantees the first entry always emits
    last_bucket = object()
    latest_transfer_idx = None

    for entry in (doc.get("travel_log") or []):
        office = (entry.get("office") or "").strip()
        label, actor_role, kind = _classify(entry.get("action"))
        bucket = label  # dedup keyed on the visible label (see _bucket_key)
        if office == last_office and bucket == last_bucket:
            continue  # collapse consecutive same-office same-label noise
        ts = entry.get("timestamp") or ""
        officer_raw = entry.get("officer") or ""
        # officer is usually a full name, but can be a bare username — resolve it
        # the same way handler names resolve, falling back to the raw value.
        officer_name = _resolve_name(officer_raw, user_map) or officer_raw
        history.append({
            "office": office,
            "label":  label,
            "date":   ts[:10] if ts else "",
            "detail": {
                "label":        label,
                "office":       office,
                "officer_name": officer_name,
                "date_time":    ts[:16] if ts else "",
                "actor_role":   actor_role,
            },
        })
        if kind == "transfer":
            latest_transfer_idx = len(history) - 1
        last_office, last_bucket = office, bucket

    # Attach the transient recipient to the latest transfer/route item ONLY.
    recipient = (doc.get("pending_at_staff_name") or "").strip()
    if recipient and latest_transfer_idx is not None:
        history[latest_transfer_idx]["detail"]["recipient_name"] = recipient

    return history


# ── Public entry point ─────────────────────────────────────────────────────────

def build_client_track_view(doc: dict, users=None) -> dict:
    """Build the complete client-safe view-model for a tracked document.

    Args:
        doc:   the raw document dict (NOT mutated).
        users: list of user dicts (e.g. from get_all_users()) used only to
               resolve a handler username → display name. Optional.

    Returns a dict with:
        current:          {state, location_office, handler_name, handler_role_label, message}
        status_display:   {label, sub_text, icon}
        history:          [{office, label, date, detail:{label, office, officer_name,
                          date_time, actor_role[, recipient_name]}}, ...]  (deduped;
                          staff name only in detail, no remarks, no raw action)
        rejection_reason: the internal reason ONLY when status is Rejected/Returned, else None
    """
    doc = doc or {}
    user_map = _build_user_map(users)
    status = (doc.get("status") or "").strip()

    reason = None
    if status in ("Rejected", "Returned"):
        reason = doc.get("rejection_reason") or None

    return {
        "current":          _build_current(doc, user_map),
        "status_display":   status_display(status),
        "history":          _build_history(doc, user_map),
        "rejection_reason": reason,
    }
