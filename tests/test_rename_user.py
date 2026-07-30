"""
tests/test_rename_user.py — Step 1 of the username-rename feature.

Covers the SERVICE layer only (no route wiring exists yet):
  - _validate_username format rules
  - create_user / update_user reject invalid new/changed names, but a
    non-rename edit never re-validates a legacy name
  - rename_user rewrites the Step-1 surface AND (Step 2) the ambiguous display
    fields received_by / accepted_by and the nested travel_log[].officer hops,
    matching the old username always and the old full_name only when it is
    UNIQUE among users; a shared full_name skips full_name matching and sets
    summary["full_name_ambiguous"]. Composite proxy labels are left intact.

Runs on the JSON backend (DATABASE_URL="" via conftest), so the DB-only
surfaces (staff_*, transfer_batches, import_batches, so_records, push_tokens)
have no file and stay at 0 — that is expected, not a gap.
"""

import os
import json
import pytest

os.environ.setdefault("SECRET_KEY", "c" * 32)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "AdminPass123!")
os.environ["DATABASE_URL"] = ""


# ── _validate_username ──────────────────────────────────────────────────────
class TestValidateUsername:
    @pytest.mark.parametrize("name", ["abc", "a.b_c-1", "jdoe", "x" * 32])
    def test_valid_names_pass(self, name):
        from services.auth import _validate_username
        ok, err = _validate_username(name)
        assert ok is True and err is None

    @pytest.mark.parametrize("name", [
        "",              # empty
        "  ",            # whitespace only
        "ab",            # too short (2)
        "x" * 33,        # too long (33)
        "bella bernales",  # space (the real legacy account that fails)
        "Jean/Doe",      # slash
        "josé",          # non-ascii
    ])
    def test_invalid_names_rejected(self, name):
        from services.auth import _validate_username
        ok, err = _validate_username(name)
        assert ok is False and err


# ── create_user / update_user wiring ─────────────────────────────────────────
class TestValidatorWiring:
    def test_create_user_rejects_invalid_username(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user
        ok, err = create_user("bad name", "GoodPass1!", role="staff")
        assert ok is False and err

    def test_update_user_rejects_rename_to_invalid(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, update_user
        create_user("validname", "GoodPass1!", role="staff")
        ok, err = update_user("validname", new_username="bad name")
        assert ok is False and err

    def test_non_rename_edit_does_not_revalidate_legacy_name(self, tmp_path, monkeypatch):
        """A legacy name with a space must stay EDITABLE (email/role) as long as
        the username itself is not being changed."""
        monkeypatch.chdir(tmp_path)
        from services.auth import update_user, _load_users_json, _save_users_json
        # Seed a legacy row directly (bypasses create_user's new validation),
        # mirroring the real 'bella bernales' account.
        _save_users_json([{
            "username": "bella bernales", "password_hash": "x",
            "full_name": "Bella", "role": "staff", "office": "",
            "approved": True, "email": "", "documents_handled": [],
        }])
        ok, err = update_user("bella bernales", email="bella@example.com")
        assert ok is True, err
        assert _load_users_json()[0]["email"] == "bella@example.com"


# ── rename_user (JSON backend) ────────────────────────────────────────────────
class TestRenameUser:
    def _seed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user
        import services.cart_store as cart_store
        import services.appointments as appts
        # Redirect the two __file__-relative JSON files into the tmp dir so the
        # test is hermetic.
        monkeypatch.setattr(cart_store, "_CART_FILE", str(tmp_path / "pending_carts.json"))
        monkeypatch.setattr(appts, "_APT_FILE", str(tmp_path / "appointments.json"))
        create_user("oldname", "GoodPass1!", full_name="Old Full Name", role="staff")

        # documents.json — Step-1 unambiguous keys, PLUS Step-2 ambiguous fields
        # in BOTH their username-valued and full_name-valued forms, PLUS a
        # composite proxy label that must survive exact-match rewrites intact.
        docs = [
            # D1 — ambiguous fields hold the USERNAME; officer hop holds username.
            # accepted_by_username (Step 2.5 A1) is ALWAYS a bare username.
            {"id": "D1", "logged_by": "oldname", "original_logged_by": "oldname",
             "updated_by": "oldname", "received_by": "oldname",
             "accepted_by": "oldname", "accepted_by_username": "oldname",
             "travel_log": [{"officer": "oldname", "action": "Received"},
                            {"officer": "someoneelse", "action": "Routed"}]},
            # D2 — every unambiguous Step-1 key.
            {"id": "D2", "submitted_by": "oldname", "pending_at_staff": "oldname",
             "transferred_by": "oldname", "transferred_to": "oldname",
             "released_by": "oldname", "rejected_by": "oldname",
             "assigned_to": "oldname", "intended_for_username": "oldname"},
            {"id": "D3", "logged_by": "someoneelse"},
            # D4 — ambiguous fields hold the FULL_NAME; accepted_by is a composite
            # proxy label; officer hops mix a full_name hit and a composite miss.
            # Step 2.5 A2 display-name companions also hold the FULL_NAME here.
            {"id": "D4", "received_by": "Old Full Name",
             "accepted_by": "Old Full Name (Admin, proxy for Someone)",
             "accepted_by_name": "Old Full Name",
             "pending_at_staff_name": "Old Full Name",
             "submitted_by_name": "Old Full Name",
             "intended_for_name": "Old Full Name",
             "travel_log": [{"officer": "Old Full Name", "action": "Accepted"},
                            {"officer": "Old Full Name (Admin, proxy for Someone)",
                             "action": "Proxy"}]},
        ]
        (tmp_path / "documents.json").write_text(json.dumps(docs))
        (tmp_path / "activity_log.json").write_text(json.dumps(
            [{"username": "oldname", "action": "x"}, {"username": "other", "action": "y"}]))
        (tmp_path / "saved_offices.json").write_text(json.dumps(
            [{"office_slug": "a", "office_name": "A", "created_by": "oldname"}]))
        (tmp_path / "routing_slips.json").write_text(json.dumps(
            [{"id": "S1", "prepared_by": "oldname", "archived_by": "oldname"}]))
        (tmp_path / "office_traffic.json").write_text(json.dumps(
            [{"id": 1, "client_username": "oldname"}]))
        (tmp_path / "appointments.json").write_text(json.dumps(
            [{"id": "APT-1", "client_username": "oldname"}]))
        (tmp_path / "pending_carts.json").write_text(json.dumps(
            {"oldname": [{"doc": 1}], "keepme": [{"doc": 2}]}))

    def test_happy_path_rewrites_step1_and_step2_surface(self, tmp_path, monkeypatch):
        self._seed(tmp_path, monkeypatch)
        from services.auth import rename_user
        ok, err, summary = rename_user("oldname", "newname", "Old Full Name", "New Full Name")
        assert ok is True, err

        docs = {d["id"]: d for d in json.loads((tmp_path / "documents.json").read_text())}
        # Step-1 keys rewritten
        assert docs["D1"]["logged_by"] == "newname"
        assert docs["D1"]["original_logged_by"] == "newname"
        assert docs["D1"]["updated_by"] == "newname"
        for k in ("submitted_by", "pending_at_staff", "transferred_by",
                  "transferred_to", "released_by", "rejected_by",
                  "assigned_to", "intended_for_username"):
            assert docs["D2"][k] == "newname", k
        # Untouched doc stays as-is
        assert docs["D3"]["logged_by"] == "someoneelse"

        # Step-2: username-valued ambiguous fields → new username
        assert docs["D1"]["received_by"] == "newname"
        assert docs["D1"]["accepted_by"] == "newname"
        assert docs["D1"]["travel_log"][0]["officer"] == "newname"
        # ...and the unrelated hop is left alone
        assert docs["D1"]["travel_log"][1]["officer"] == "someoneelse"

        # Step 2.5 A1: accepted_by_username is a bare username → new username
        assert docs["D1"]["accepted_by_username"] == "newname"

        # Step-2: full_name-valued ambiguous fields → new full_name (fn unique)
        assert docs["D4"]["received_by"] == "New Full Name"
        assert docs["D4"]["travel_log"][0]["officer"] == "New Full Name"
        # Composite proxy label is NOT equal to the plain old full_name → intact
        assert docs["D4"]["accepted_by"] == "Old Full Name (Admin, proxy for Someone)"
        assert docs["D4"]["travel_log"][1]["officer"] == "Old Full Name (Admin, proxy for Someone)"

        # Step 2.5 A2: client-facing display-name companions → new full_name
        assert docs["D4"]["accepted_by_name"] == "New Full Name"
        assert docs["D4"]["pending_at_staff_name"] == "New Full Name"
        assert docs["D4"]["submitted_by_name"] == "New Full Name"
        assert docs["D4"]["intended_for_name"] == "New Full Name"

        # full_name was unique → matched, not ambiguous
        assert summary["full_name_matched"] is True
        assert summary["full_name_ambiguous"] is False
        # Per-field rowcounts: received_by hit D1(username)+D4(full_name)=2;
        # accepted_by hit D1(username)=1 (D4 composite skipped); travel_log 2 hops/2 docs.
        assert summary["received_by_updated"] == 2
        assert summary["accepted_by_updated"] == 1
        assert summary["travel_log_hops_updated"] == 2
        assert summary["travel_log_docs_updated"] == 2
        # Step 2.5 A2 per-field rowcounts (each hit once on D4's full_name).
        assert summary["accepted_by_name_updated"] == 1
        assert summary["pending_at_staff_name_updated"] == 1
        assert summary["submitted_by_name_updated"] == 1
        assert summary["intended_for_name_updated"] == 1

        # Other surfaces
        assert json.loads((tmp_path / "activity_log.json").read_text())[0]["username"] == "newname"
        assert json.loads((tmp_path / "saved_offices.json").read_text())[0]["created_by"] == "newname"
        slip = json.loads((tmp_path / "routing_slips.json").read_text())[0]
        assert slip["prepared_by"] == "newname" and slip["archived_by"] == "newname"
        assert json.loads((tmp_path / "office_traffic.json").read_text())[0]["client_username"] == "newname"
        assert json.loads((tmp_path / "appointments.json").read_text())[0]["client_username"] == "newname"
        carts = json.loads((tmp_path / "pending_carts.json").read_text())
        assert "oldname" not in carts and carts["newname"] == [{"doc": 1}] and carts["keepme"] == [{"doc": 2}]

        # users.json renamed
        from services.auth import _load_users_json
        assert any(u["username"] == "newname" for u in _load_users_json())
        assert not any(u["username"] == "oldname" for u in _load_users_json())

        # Summary counts (field-level for documents: D1 has 4 Step-1 keys —
        # logged_by, original_logged_by, updated_by, accepted_by_username — D2 has 8)
        assert summary["documents_updated"] == 12
        assert summary["activity_log_updated"] == 1
        assert summary["routing_slips_updated"] == 2
        assert summary["appointments_updated"] == 1
        assert summary["user_carts_updated"] == 1
        assert summary["users_updated"] == 1
        # DB-only surfaces stay 0 in JSON mode
        assert summary["push_tokens_updated"] == 0
        assert summary["transfer_batches_updated"] == 0

    def test_rejects_unknown_old(self, tmp_path, monkeypatch):
        self._seed(tmp_path, monkeypatch)
        from services.auth import rename_user
        ok, err, _ = rename_user("ghost", "newname")
        assert ok is False and "not found" in err.lower()

    def test_rejects_taken_new(self, tmp_path, monkeypatch):
        self._seed(tmp_path, monkeypatch)
        from services.auth import create_user, rename_user
        create_user("taken", "GoodPass1!", role="staff")
        ok, err, _ = rename_user("oldname", "taken")
        assert ok is False and "taken" in err.lower()

    def test_rejects_invalid_new(self, tmp_path, monkeypatch):
        self._seed(tmp_path, monkeypatch)
        from services.auth import rename_user
        ok, err, _ = rename_user("oldname", "bad name")
        assert ok is False and err

    def test_rejects_same_name(self, tmp_path, monkeypatch):
        self._seed(tmp_path, monkeypatch)
        from services.auth import rename_user
        ok, err, _ = rename_user("oldname", "oldname")
        assert ok is False and err

    def test_shared_full_name_skips_full_name_rewrite(self, tmp_path, monkeypatch):
        """When the old full_name is shared by >1 user, full_name matching is
        UNSAFE: the username-based rewrite still runs, but full_name-valued
        occurrences are left untouched and summary['full_name_ambiguous'] is set.

        The twin's full_name differs ONLY IN CASING ("OLD FULL NAME") — proving
        the Step 2.5 case-insensitive uniqueness gate treats it as a collision."""
        self._seed(tmp_path, monkeypatch)
        from services.auth import create_user, rename_user
        # A SECOND user whose full_name case-folds to the SAME string → the
        # case-insensitive gate must flag this as shared/ambiguous.
        create_user("othertwin", "GoodPass1!", full_name="OLD FULL NAME", role="staff")

        ok, err, summary = rename_user("oldname", "newname", "Old Full Name", "New Full Name")
        assert ok is True, err
        assert summary["full_name_ambiguous"] is True
        assert summary["full_name_matched"] is False

        docs = {d["id"]: d for d in json.loads((tmp_path / "documents.json").read_text())}
        # Username-valued occurrences STILL rewritten...
        assert docs["D1"]["received_by"] == "newname"
        assert docs["D1"]["accepted_by"] == "newname"
        assert docs["D1"]["accepted_by_username"] == "newname"  # A1: username, not gated
        assert docs["D1"]["travel_log"][0]["officer"] == "newname"
        # ...but full_name-valued ones are LEFT as the old full_name (unsafe).
        assert docs["D4"]["received_by"] == "Old Full Name"
        assert docs["D4"]["accepted_by_name"] == "Old Full Name"
        assert docs["D4"]["pending_at_staff_name"] == "Old Full Name"
        assert docs["D4"]["travel_log"][0]["officer"] == "Old Full Name"
        assert summary["received_by_updated"] == 1     # only D1's username hit
        assert summary["accepted_by_updated"] == 1
        assert summary["accepted_by_name_updated"] == 0     # full_name-only, skipped
        assert summary["pending_at_staff_name_updated"] == 0
        assert summary["travel_log_hops_updated"] == 1

    def test_other_persons_history_not_touched(self, tmp_path, monkeypatch):
        """A different person's records (their own username AND full_name) must be
        left entirely alone even on a safe (unique) full_name rename."""
        self._seed(tmp_path, monkeypatch)
        from services.auth import create_user, rename_user
        create_user("bystander", "GoodPass1!", full_name="By Stander", role="staff")
        # Add a doc owned entirely by the bystander.
        docs = json.loads((tmp_path / "documents.json").read_text())
        docs.append({"id": "D5", "logged_by": "bystander",
                     "received_by": "By Stander", "accepted_by": "bystander",
                     "travel_log": [{"officer": "By Stander", "action": "Received"},
                                    {"officer": "bystander", "action": "Routed"}]})
        (tmp_path / "documents.json").write_text(json.dumps(docs))

        ok, err, _ = rename_user("oldname", "newname", "Old Full Name", "New Full Name")
        assert ok is True, err

        d5 = {d["id"]: d for d in json.loads((tmp_path / "documents.json").read_text())}["D5"]
        assert d5["logged_by"] == "bystander"
        assert d5["received_by"] == "By Stander"
        assert d5["accepted_by"] == "bystander"
        assert d5["travel_log"][0]["officer"] == "By Stander"
        assert d5["travel_log"][1]["officer"] == "bystander"

    def test_casing_drift_full_name_still_rewritten(self, tmp_path, monkeypatch):
        """THE Step 2.5 Change B proof — mirrors the real Kim data. users.full_name
        is UPPER ("KIM WENDELL DAVOCOL") but documents hold a TITLE-CASE variant
        ("Kim Wendell Davocol"). Exact matching (pre-Change-B) would MISS these;
        case-insensitive matching rewrites them to the new canonical full_name."""
        monkeypatch.chdir(tmp_path)
        from services.auth import create_user, rename_user
        import services.cart_store as cart_store
        import services.appointments as appts
        monkeypatch.setattr(cart_store, "_CART_FILE", str(tmp_path / "pending_carts.json"))
        monkeypatch.setattr(appts, "_APT_FILE", str(tmp_path / "appointments.json"))
        # Stored user full_name is UPPER-CASE, unique.
        create_user("kimd", "GoodPass1!", full_name="KIM WENDELL DAVOCOL", role="staff")
        # Documents hold the TITLE-CASE variant — a casing mismatch vs old_full_name.
        docs = [{
            "id": "K1",
            "received_by": "Kim Wendell Davocol",
            "accepted_by_name": "Kim Wendell Davocol",
            "pending_at_staff_name": "Kim Wendell Davocol",
            "intended_for_name": "Kim Wendell Davocol",
            "travel_log": [{"officer": "Kim Wendell Davocol", "action": "Accepted"}],
        }]
        (tmp_path / "documents.json").write_text(json.dumps(docs))

        # old_full_name passed in is the UPPER users.full_name; new is canonical.
        ok, err, summary = rename_user("kimd", "kimw",
                                       "KIM WENDELL DAVOCOL", "Kim W. Davocol")
        assert ok is True, err
        assert summary["full_name_matched"] is True      # unique despite casing
        assert summary["full_name_ambiguous"] is False

        k1 = json.loads((tmp_path / "documents.json").read_text())[0]
        # Despite the UPPER-vs-title casing mismatch, all were rewritten to the
        # new CANONICAL full_name (casing normalized) — the Change-B payoff.
        assert k1["received_by"] == "Kim W. Davocol"
        assert k1["accepted_by_name"] == "Kim W. Davocol"
        assert k1["pending_at_staff_name"] == "Kim W. Davocol"
        assert k1["intended_for_name"] == "Kim W. Davocol"
        assert k1["travel_log"][0]["officer"] == "Kim W. Davocol"

    def test_free_text_fields_not_touched(self, tmp_path, monkeypatch):
        """Boundary pin: free-text fields (referred_to, sender_name,
        recipient_name, travel_log[].remarks) are NOT rewritten even when they
        coincidentally equal the old full_name. Only structured identity fields
        are rewritten — see the FREE-TEXT BOUNDARY comment in services/auth.py."""
        self._seed(tmp_path, monkeypatch)
        from services.auth import rename_user
        docs = json.loads((tmp_path / "documents.json").read_text())
        docs.append({
            "id": "FT1",
            "referred_to": "Old Full Name",
            "sender_name": "Old Full Name",
            "recipient_name": "Old Full Name",
            "travel_log": [{"officer": "Old Full Name", "action": "Accepted",
                            "remarks": "Old Full Name handed this over"}],
        })
        (tmp_path / "documents.json").write_text(json.dumps(docs))

        ok, err, _ = rename_user("oldname", "newname", "Old Full Name", "New Full Name")
        assert ok is True, err

        ft1 = {d["id"]: d for d in json.loads((tmp_path / "documents.json").read_text())}["FT1"]
        # Free-text fields untouched...
        assert ft1["referred_to"] == "Old Full Name"
        assert ft1["sender_name"] == "Old Full Name"
        assert ft1["recipient_name"] == "Old Full Name"
        assert ft1["travel_log"][0]["remarks"] == "Old Full Name handed this over"
        # ...but the STRUCTURED officer field in the same hop IS rewritten.
        assert ft1["travel_log"][0]["officer"] == "New Full Name"
