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


# ── Action → client-friendly label (substring buckets, ordered by priority) ────
#
# Matched by lowercased substring against the travel_log `action` string.
# ORDER MATTERS: earlier entries win. "released" is checked before the
# transfer/route bucket because "Released — Routed to X" contains both.
#
# Each tuple: (list-of-substrings, client_label).
_ACTION_BUCKETS = [
    (["submitted"],              "You submitted this request"),
    (["rejected"],               "Document was not accepted"),
    (["returned"],               "Returned to the sending office"),
    (["released", "picked up"],  "Released from the office"),
    (["received", "accepted"],   "Received and being processed"),
    (["transfer", "rout"],       "Forwarded to another office"),   # transfer/route/routed/reroute/rerouted
    (["assigned"],               "Assignment updated"),            # assigned / unassigned
    (["logged"],                 "Logged into the system"),
    (["edited"],                 "Details updated"),
    (["hold"],                   "Placed on hold"),
    (["archived"],               "Archived"),
]

_ACTION_FALLBACK = "Document processed"


def bucket_label(action: str) -> str:
    """Map a raw travel_log `action` string to a client-friendly label.

    Uses lowercased substring matching. Never returns the raw action string;
    an unrecognised action yields the safe generic fallback.
    """
    a = (action or "").lower()
    for needles, label in _ACTION_BUCKETS:
        if any(n in a for n in needles):
            return label
    return _ACTION_FALLBACK


def _bucket_key(action: str) -> str:
    """A stable key identifying which bucket an action falls into.

    Used purely for history de-duplication (so two consecutive entries in the
    same office AND same bucket collapse into one). Falls back to a distinct
    marker so unmatched actions still de-dupe against each other.
    """
    a = (action or "").lower()
    for i, (needles, _label) in enumerate(_ACTION_BUCKETS):
        if any(n in a for n in needles):
            return f"b{i}"
    return "b_generic"


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

def _build_history(doc) -> list:
    """Walk travel_log oldest→newest, emitting a de-duped movement list.

    Emits a new item only on a MEANINGFUL transition — the office changes OR the
    action bucket changes. Consecutive entries in the same office with the same
    bucket collapse into a single item. The internal `officer` and `remarks`
    fields are dropped entirely; each item exposes only {office, label, date, icon}.
    """
    history = []
    last_office = object()   # sentinel — guarantees the first entry always emits
    last_bucket = object()

    for entry in (doc.get("travel_log") or []):
        office = (entry.get("office") or "").strip()
        bucket = _bucket_key(entry.get("action"))
        if office == last_office and bucket == last_bucket:
            continue  # collapse consecutive same-office same-bucket noise
        ts = entry.get("timestamp") or ""
        history.append({
            "office": office,
            "label":  bucket_label(entry.get("action")),
            "date":   ts[:10] if ts else "",
        })
        last_office, last_bucket = office, bucket

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
        history:          [{office, label, date}, ...]  (deduped, no officer/remarks)
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
        "history":          _build_history(doc),
        "rejection_reason": reason,
    }
