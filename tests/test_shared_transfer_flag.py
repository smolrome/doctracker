"""
tests/test_shared_transfer_flag.py — per-group "Shared Transfer" capability.

Shared Transfer controls ONLY whether group-mates can transfer EACH OTHER's
documents. It is DEPENDENT on Shared Dashboard and is a REAL enforcement flag
(gates the transfer route server-side), not a display-only badge.

Route-level enforcement (tests 1-3) runs against the JSON backend by
monkeypatching the data-layer helpers:
  - get_group_transfer_usernames → the TRANSFER set (dashboard AND transfer ON)
  - get_group_usernames          → the VISIBILITY set (dashboard ON)

DB-only behavior (tests 4-6: migration backfill, the admin toggle handlers and
their dependency guard) is Postgres-only — the suite has no Postgres — so those
are exercised against a small in-memory fake connection that implements just the
handful of SQL statements involved.

Every POST carries csrf_token; assertions target the real destination, never
/login.
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


def _patch_transfer_set(monkeypatch, mapping):
    """get_group_transfer_usernames(u) -> mapping[u] (default [])."""
    import services.database as db
    monkeypatch.setattr(db, "get_group_transfer_usernames", lambda u: mapping.get(u, []))


def _patch_visibility_set(monkeypatch, mapping):
    """get_group_usernames(u) -> mapping[u] (default [])."""
    import services.database as db
    monkeypatch.setattr(db, "get_group_usernames", lambda u: mapping.get(u, []))


def _make_doc(owner, status="Received"):
    doc_id = uuid.uuid4().hex[:8].upper()
    insert_doc({
        "id":                 doc_id,
        "doc_id":             f"REF-{uuid.uuid4().hex[:4].upper()}",
        "doc_name":           f"STX-{doc_id}",
        "status":             status,
        "logged_by":          owner,
        "original_logged_by": owner,
        "travel_log":         [],
    })
    return doc_id


@pytest.fixture(autouse=True)
def _people():
    create_user("owneruser",     "OwnerPass1!", full_name="Owner User",
                role="staff", office=OFFICE)
    create_user("recipientuser", "RecipPass1!", full_name="Recipient User",
                role="staff", office=OFFICE)
    yield


def _loc(rv):
    return rv.headers.get("Location", "")


# ── 1. dashboard ON + transfer ON → group-mate CAN transfer ───────────────────

def test_dashboard_on_transfer_on_group_mate_can_transfer(staff_client, monkeypatch):
    _patch_transfer_set(monkeypatch, {"staffuser": ["owneruser"]})
    _set_office(staff_client)
    doc_id = _make_doc("owneruser")

    rv = staff_client.post(
        f"/transfer/{doc_id}",
        data={"transfer_type": "inside_office", "new_staff": "recipientuser",
              "new_office": "", "csrf_token": _csrf(staff_client)},
        follow_redirects=False,
    )
    assert rv.status_code == 302
    assert "/login" not in _loc(rv)
    assert get_doc(doc_id).get("transfer_status") == "pending"
    assert get_doc(doc_id).get("transferred_by") == "staffuser"


# ── 2. dashboard ON + transfer OFF → CANNOT transfer, but CAN still SEE ────────

def test_dashboard_on_transfer_off_cannot_transfer_single(staff_client, monkeypatch):
    # Transfer set excludes the owner (transfer flag OFF) ...
    _patch_transfer_set(monkeypatch, {})
    _set_office(staff_client)
    doc_id = _make_doc("owneruser")

    rv = staff_client.post(
        f"/transfer/{doc_id}",
        data={"transfer_type": "inside_office", "new_staff": "recipientuser",
              "new_office": "", "csrf_token": _csrf(staff_client)},
        headers={"X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    assert rv.status_code == 403
    assert get_doc(doc_id).get("transfer_status") != "pending"


def test_dashboard_on_transfer_off_cannot_transfer_batch(staff_client, monkeypatch):
    _patch_transfer_set(monkeypatch, {})
    _set_office(staff_client)
    doc_id = _make_doc("owneruser")

    rv = staff_client.post(
        "/transfer-batch",
        data={"doc_ids": doc_id, "transfer_type": "inside_office",
              "new_staff": "recipientuser", "new_office": "",
              "csrf_token": _csrf(staff_client)},
        follow_redirects=True,
    )
    # Counted skip, honest feedback — not a silent success.
    assert b"No documents were transferred" in rv.data
    assert b"1 not permitted" in rv.data
    assert get_doc(doc_id).get("transfer_status") != "pending"


def test_dashboard_on_transfer_off_can_still_see(staff_client, monkeypatch):
    # Visibility set (dashboard flag) DOES include the owner ...
    _patch_visibility_set(monkeypatch, {"staffuser": ["owneruser"]})
    # ... while the transfer set does NOT (transfer flag off).
    _patch_transfer_set(monkeypatch, {})
    _set_office(staff_client)
    doc_id = _make_doc("owneruser")

    rv = staff_client.get("/", follow_redirects=False)
    assert rv.status_code == 200
    # The co-member's doc is visible on the shared dashboard.
    assert f"STX-{doc_id}".encode() in rv.data


# ── 3. ANY user can ALWAYS transfer their OWN document ────────────────────────

def test_own_document_always_transferable_regardless_of_flags(staff_client, monkeypatch):
    # No group, no flags at all.
    _patch_transfer_set(monkeypatch, {})
    _patch_visibility_set(monkeypatch, {})
    _set_office(staff_client)
    doc_id = _make_doc("staffuser")          # staffuser OWNS it

    rv = staff_client.post(
        f"/transfer/{doc_id}",
        data={"transfer_type": "inside_office", "new_staff": "recipientuser",
              "new_office": "", "csrf_token": _csrf(staff_client)},
        follow_redirects=False,
    )
    assert rv.status_code == 302
    assert "/login" not in _loc(rv)
    assert get_doc(doc_id).get("transfer_status") == "pending"
    assert get_doc(doc_id).get("transferred_by") == "staffuser"


# ── Fake DB for the Postgres-only paths (tests 4-6) ───────────────────────────

class _FakeCursor:
    """Implements only the SQL the migration backfill and toggle handlers use."""
    def __init__(self, store):
        self.store = store          # {"groups": {id: {...}}, "col_exists": bool}
        self._one = None

    # context-manager (conn.cursor() as cur)
    def __enter__(self): return self
    def __exit__(self, *a): return False

    @staticmethod
    def _norm(sql):
        return " ".join(sql.split()).lower()

    def execute(self, sql, params=None):
        s = self._norm(sql)
        params = params or ()
        self._one = None

        # column-existence probe (migration guard)
        if "information_schema.columns" in s and "has_shared_transfer" in s:
            self._one = (1,) if self.store["col_exists"] else None
            return
        # ALTER ... ADD COLUMN has_shared_transfer
        if s.startswith("alter table staff_groups add column") and "has_shared_transfer" in s:
            self.store["col_exists"] = True
            for g in self.store["groups"].values():
                g.setdefault("has_shared_transfer", False)
            return
        # one-time backfill
        if s.startswith("update staff_groups set has_shared_transfer = true where has_shared_dashboard = true"):
            for g in self.store["groups"].values():
                if g.get("has_shared_dashboard"):
                    g["has_shared_transfer"] = True
            return
        # toggle SELECT for one group
        if s.startswith("select") and "from staff_groups where id" in s:
            gid = params[0]
            g = self.store["groups"].get(gid)
            self._one = dict(g) if g else None
            return
        # dashboard toggle that also clears transfer
        if s.startswith("update staff_groups set has_shared_dashboard = %s, has_shared_transfer = false where id"):
            val, gid = params
            self.store["groups"][gid]["has_shared_dashboard"] = val
            self.store["groups"][gid]["has_shared_transfer"] = False
            return
        # dashboard toggle (enable)
        if s.startswith("update staff_groups set has_shared_dashboard = %s where id"):
            val, gid = params
            self.store["groups"][gid]["has_shared_dashboard"] = val
            return
        # transfer toggle
        if s.startswith("update staff_groups set has_shared_transfer = %s where id"):
            val, gid = params
            self.store["groups"][gid]["has_shared_transfer"] = val
            return
        # everything else (the big migration list, SAVEPOINTs, audit inserts): no-op
        return

    def fetchone(self):
        out, self._one = self._one, None
        return out

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self, store):
        self.store = store
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def cursor(self): return _FakeCursor(self.store)
    def commit(self): pass


def _install_fake_db(monkeypatch, store):
    import services.database as db
    monkeypatch.setattr(db, "USE_DB", True)
    monkeypatch.setattr(db, "get_conn", lambda: _FakeConn(store))
    # Keep audit_log out of the fake DB path.
    monkeypatch.setattr("routes.admin.audit_log", lambda *a, **k: None)


# ── 4. migration backfill: dashboard TRUE → transfer TRUE, once ───────────────

def test_backfill_sets_transfer_true_for_dashboard_groups(monkeypatch):
    import services.database as db
    store = {
        "col_exists": False,
        "groups": {
            1: {"id": 1, "group_name": "A", "has_shared_dashboard": True},
            2: {"id": 2, "group_name": "B", "has_shared_dashboard": False},
        },
    }
    cur = _FakeCursor(store)
    db._run_migrations(cur)

    assert store["groups"][1]["has_shared_transfer"] is True      # dashboard ON → backfilled
    assert store["groups"][2]["has_shared_transfer"] is False     # dashboard OFF → stays off


def test_backfill_runs_only_once(monkeypatch):
    import services.database as db
    # Column already exists (later boot) + admin has since turned transfer OFF.
    store = {
        "col_exists": True,
        "groups": {1: {"id": 1, "group_name": "A",
                       "has_shared_dashboard": True, "has_shared_transfer": False}},
    }
    db._run_migrations(_FakeCursor(store))
    # Backfill must NOT re-assert TRUE — admin's choice is preserved.
    assert store["groups"][1]["has_shared_transfer"] is False


# ── 5. turning dashboard OFF forces transfer OFF ──────────────────────────────

def test_disabling_dashboard_forces_transfer_off(admin_client, monkeypatch):
    store = {"col_exists": True,
             "groups": {7: {"id": 7, "group_name": "G7",
                            "has_shared_dashboard": True, "has_shared_transfer": True}}}
    _install_fake_db(monkeypatch, store)

    rv = admin_client.post(
        "/manage-pairings/toggle-shared-dashboard/7",
        data={"csrf_token": _csrf(admin_client)},
        follow_redirects=False,
    )
    assert rv.status_code == 302
    assert "/login" not in _loc(rv)
    assert store["groups"][7]["has_shared_dashboard"] is False
    assert store["groups"][7]["has_shared_transfer"] is False     # no stale TRUE


# ── 6. admin cannot enable transfer when dashboard is off ─────────────────────

def test_cannot_enable_transfer_when_dashboard_off(admin_client, monkeypatch):
    store = {"col_exists": True,
             "groups": {9: {"id": 9, "group_name": "G9",
                            "has_shared_dashboard": False, "has_shared_transfer": False}}}
    _install_fake_db(monkeypatch, store)

    rv = admin_client.post(
        "/manage-pairings/toggle-shared-transfer/9",
        data={"csrf_token": _csrf(admin_client)},
        follow_redirects=False,
    )
    assert rv.status_code == 302
    assert "/login" not in _loc(rv)
    # Rejected: transfer stays OFF, and the user is told to enable dashboard first.
    assert store["groups"][9]["has_shared_transfer"] is False
    with admin_client.session_transaction() as s:
        flashes = s.get("_flashes", [])
    assert any("Enable Shared Dashboard first" in msg for _cat, msg in flashes)
