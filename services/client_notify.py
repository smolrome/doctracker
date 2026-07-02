"""
services/client_notify.py — Client milestone notifications.

Sends a single client-facing notification when a document the client submitted
transitions to a milestone status (Received, Released, Rejected/Returned).
Push if the client has a registered token, otherwise email.

Delivery runs on a daemon BACKGROUND THREAD so the caller (the persistence
layer in services/documents.py) never blocks. A batch slip scan that
transitions many client docs returns immediately; the sends drain off-thread.

DURABILITY TRADEOFF: a raw thread has NO retry, NO persistence, and NO
backpressure. If the process dies mid-send or a send fails, the notification is
simply lost. That is acceptable for best-effort status nudges. If delivery
reliability ever becomes critical, the future upgrade is a real task queue
(RQ / Celery / a DB-backed outbox) — do NOT rely on this thread for guaranteed
delivery, and do NOT add a queue now.
"""

import threading

# Statuses that warrant a client notification. Internal Transferred/Routed
# movements are deliberately EXCLUDED.
MILESTONE_STATUSES = frozenset({"Received", "Released", "Rejected", "Returned"})

# Per-event title copy. Body text is sourced from client_view.status_display so
# the wording matches the client tracker page exactly.
_EVENT_TITLES = {
    "Received": "Your request is being processed",
    "Released": "Your document is ready",
    "Rejected": "Action needed on your request",
    "Returned": "Action needed on your request",
}


def _resolve_email(username: str) -> str:
    """Look up the client's stored email from their user record; '' if none."""
    try:
        from services.auth import get_user
        u = get_user(username)
        return (u.get("email") or "").strip() if u else ""
    except Exception:
        return ""


def _do_send(doc: dict, new_status: str) -> None:
    """Runs on the background thread. Fully isolated — never raises."""
    try:
        username = (doc.get("submitted_by") or "").strip()
        if not username:
            return  # staff-logged doc — nothing to do

        from services.client_view import status_display
        sd = status_display(new_status)

        doc_name = doc.get("doc_name") or doc.get("doc_id") or "Your document"
        title = _EVENT_TITLES.get(new_status, "Update on your request")
        body = f"{doc_name}: {sd['sub_text']}"
        if new_status in ("Rejected", "Returned") and doc.get("rejection_reason"):
            body += f" Reason: {doc['rejection_reason']}"

        data = {"screen": f"/client/track/{doc.get('id', '')}"}

        # Push first; fall back to email only if there is no token / push failed.
        pushed = False
        try:
            from blueprints.api import send_push_notification
            pushed = send_push_notification(username, title, body, data=data)
        except Exception:
            pushed = False

        if not pushed:
            email = _resolve_email(username)
            if email:  # guard: never attempt SMTP with an empty recipient
                try:
                    from services.email import send_email
                    send_email(email, title, body)
                except Exception:
                    pass
    except Exception:
        pass


def notify_client(doc: dict, new_status: str) -> None:
    """Schedule a client milestone notification (non-blocking, fire-and-forget).

    Spins a daemon thread and returns immediately. Safe to call for any doc —
    it no-ops for staff docs (empty submitted_by) and for clients with neither a
    push token nor an email. Never raises into the caller.

    A shallow copy of `doc` is snapshotted so the background thread reads stable
    values even if the caller keeps mutating the original document afterwards.
    """
    try:
        snapshot = dict(doc)
        t = threading.Thread(target=_do_send, args=(snapshot, new_status), daemon=True)
        t.start()
    except Exception:
        pass
