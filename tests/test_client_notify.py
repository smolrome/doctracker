"""
tests/test_client_notify.py — Milestone 2: client notification choke point.

Covers the persistence-layer hook (save_doc / batch_save_docs) and the
notify_client delivery helper. JSON backend, no real DB, no real threads for
the choke-point tests (notify_client is monkeypatched to a synchronous recorder
so scheduling can be observed deterministically).
"""

import json
import os
import uuid
import pytest

os.environ.setdefault("SECRET_KEY", "n" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


@pytest.fixture(autouse=True)
def use_tmp_dir(tmp_path, monkeypatch):
    data_file = str(tmp_path / "documents.json")
    (tmp_path / "documents.json").write_text(json.dumps([]))
    (tmp_path / "users.json").write_text(json.dumps([]))
    monkeypatch.setenv("DATA_FILE", data_file)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def rec(monkeypatch):
    """Record notify_client(doc, status) scheduling instead of threading a send."""
    calls = []
    import services.client_notify as cn
    monkeypatch.setattr(cn, "notify_client",
                        lambda doc, status: calls.append((dict(doc), status)))
    return calls


def _client_doc(status="Pending", **extra):
    d = {"id": uuid.uuid4().hex[:8].upper(), "doc_id": "REF-X",
         "doc_name": "My Request", "status": status, "submitted_by": "clientjoe"}
    d.update(extra)
    return d


# 1. Received on a client doc → scheduled exactly once.
def test_received_client_doc_schedules_once(rec):
    from services.documents import insert_doc, save_doc
    doc = _client_doc("Pending")
    insert_doc(doc)                       # insert_doc must NOT notify
    assert rec == []
    doc["status"] = "Received"
    save_doc(doc)
    assert len(rec) == 1
    assert rec[0][1] == "Received"
    assert rec[0][0]["submitted_by"] == "clientjoe"


# 2. Same status re-saved (old == new) → NOT notified.
def test_same_status_no_notify(rec):
    from services.documents import insert_doc, save_doc
    doc = _client_doc("Received")
    insert_doc(doc)
    save_doc(doc)                         # Received → Received
    assert rec == []


# 3. Double-scanned QR receive (already Received) → only the real transition fires.
def test_double_scan_receive_dedup(rec):
    from services.documents import insert_doc, save_doc
    doc = _client_doc("Pending")
    insert_doc(doc)
    doc["status"] = "Received"
    save_doc(doc)                         # real transition → 1
    doc["status"] = "Received"
    save_doc(doc)                         # double-scan, no change → 0
    assert len(rec) == 1


# 4. Internal Transferred / Routed → NOT notified.
def test_internal_transfer_not_notified(rec):
    from services.documents import insert_doc, save_doc
    for internal in ("Transferred", "Routed"):
        doc = _client_doc("Pending")
        insert_doc(doc)
        doc["status"] = internal
        save_doc(doc)
    assert rec == []


# 5. Staff doc (empty submitted_by) → clean no-op.
def test_staff_doc_no_notify(rec):
    from services.documents import insert_doc, save_doc
    doc = _client_doc("Pending", submitted_by="")
    insert_doc(doc)
    doc["status"] = "Received"
    save_doc(doc)
    assert rec == []


# 6. Channel selection in the real delivery path (_do_send, run synchronously).
def test_channel_push_when_token(monkeypatch):
    import services.client_notify as cn
    import blueprints.api as api
    import services.email as email
    monkeypatch.setattr(api, "send_push_notification", lambda *a, **k: True)
    email_calls = []
    monkeypatch.setattr(email, "send_email", lambda *a, **k: email_calls.append(a) or (True, ""))
    cn._do_send(_client_doc("Received"), "Received")
    assert email_calls == []               # push succeeded → no email


def test_channel_email_when_no_token(monkeypatch):
    import services.client_notify as cn
    import blueprints.api as api
    import services.email as email
    monkeypatch.setattr(api, "send_push_notification", lambda *a, **k: False)
    monkeypatch.setattr(cn, "_resolve_email", lambda u: "joe@example.com")
    email_calls = []
    monkeypatch.setattr(email, "send_email", lambda to, subj, body, *a, **k: email_calls.append(to) or (True, ""))
    cn._do_send(_client_doc("Released"), "Released")
    assert email_calls == ["joe@example.com"]


def test_channel_noop_when_neither(monkeypatch):
    import services.client_notify as cn
    import blueprints.api as api
    import services.email as email
    monkeypatch.setattr(api, "send_push_notification", lambda *a, **k: False)
    monkeypatch.setattr(cn, "_resolve_email", lambda u: "")   # no email
    email_calls = []
    monkeypatch.setattr(email, "send_email", lambda *a, **k: email_calls.append(a) or (True, ""))
    cn._do_send(_client_doc("Received"), "Received")           # must not raise
    assert email_calls == []


def test_rejected_body_includes_reason(monkeypatch):
    import services.client_notify as cn
    import blueprints.api as api
    sent = {}
    monkeypatch.setattr(api, "send_push_notification",
                        lambda username, title, body, data=None: sent.update(title=title, body=body) or True)
    doc = _client_doc("Rejected", rejection_reason="Missing attachment.")
    cn._do_send(doc, "Rejected")
    assert "Missing attachment." in sent["body"]
    assert sent["title"] == "Action needed on your request"


# 7. batch_save_docs → one schedule per eligible doc, old statuses read in ONE pass.
def test_batch_schedules_each_and_reads_once(rec, monkeypatch):
    import services.documents as docs_mod
    from services.documents import insert_doc, batch_save_docs

    batch = [_client_doc("Pending") for _ in range(3)]
    for d in batch:
        insert_doc(d)

    # Spy on load_docs to prove old statuses are captured in a single pass,
    # not once per document (the JSON analogue of "ONE query, not N").
    real_load = docs_mod.load_docs
    calls = {"n": 0}

    def counting_load(*a, **k):
        calls["n"] += 1
        return real_load(*a, **k)
    monkeypatch.setattr(docs_mod, "load_docs", counting_load)

    for d in batch:
        d["status"] = "Received"
    batch_save_docs(batch)

    assert len(rec) == 3                       # one schedule per eligible doc
    assert calls["n"] == 1                     # single old-status read pass


# 8. A notification failure must NOT break persistence.
def test_notify_failure_isolated(monkeypatch):
    import services.client_notify as cn
    from services.documents import insert_doc, save_doc, get_doc

    def boom(doc, status):
        raise RuntimeError("notification subsystem exploded")
    monkeypatch.setattr(cn, "notify_client", boom)

    doc = _client_doc("Pending")
    insert_doc(doc)
    doc["status"] = "Received"
    save_doc(doc)                              # must not raise
    assert get_doc(doc["id"])["status"] == "Received"   # persistence succeeded
