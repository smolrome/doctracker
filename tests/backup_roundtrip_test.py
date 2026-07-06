#!/usr/bin/env python
r"""
tests/backup_roundtrip_test.py — Full backup/restore round-trip harness.

Stage-0 diagnostic tool. Proves EXACTLY what the app's Full backup
(services.backup.create_backup) captures and what restore_backup(mode="replace")
reproduces, by running the *real* application code paths against throwaway
databases and diffing every table.

────────────────────────────────────────────────────────────────────────────
SAFETY — this script will NEVER touch production:
  * It refuses to run unless BOTH env vars below are set to throwaway DSNs:
        ROUNDTRIP_SOURCE_URL   seeded, then backed up
        ROUNDTRIP_TARGET_URL   created empty, then restored into
  * It aborts if either URL equals config.DATABASE_URL (the app's real DB).
  * It aborts unless each target dbname contains a throwaway marker
    (test / tmp / throwaway / roundtrip / scratch), unless ROUNDTRIP_FORCE=1.
  * Every phase runs in its own subprocess with DATABASE_URL bound to ONE
    throwaway DSN, exactly as the app binds it at runtime — so the app's
    global connection pool can only ever reach the throwaway you named.

Both databases must already exist and be EMPTY (this script has no CREATE
DATABASE privilege assumption). Create them yourself, e.g.:
    createdb doctracker_roundtrip_src
    createdb doctracker_roundtrip_tgt

────────────────────────────────────────────────────────────────────────────
RUN:
    # from repo root, with the project venv:
    ROUNDTRIP_SOURCE_URL=postgresql://user:pw@localhost:5432/doctracker_roundtrip_src \
    ROUNDTRIP_TARGET_URL=postgresql://user:pw@localhost:5432/doctracker_roundtrip_tgt \
    .venv/Scripts/python.exe tests/backup_roundtrip_test.py

    # Windows PowerShell:
    $env:ROUNDTRIP_SOURCE_URL="postgresql://user:pw@localhost:5432/doctracker_roundtrip_src"
    $env:ROUNDTRIP_TARGET_URL="postgresql://user:pw@localhost:5432/doctracker_roundtrip_tgt"
    .venv\Scripts\python.exe tests\backup_roundtrip_test.py

Exit code 0 = harness ran to completion (read the report for the coverage gap).
Non-zero  = a safety guard tripped or a phase errored.
"""
import os
import sys
import json
import subprocess

# Ensure the project root is importable BEFORE any 'from services...' /
# 'from config...' resolves — needed when run from the repo root, both
# directly and via -m, and inside each per-phase subprocess.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# ── The full 21-table schema (source of truth for the diff) ────────────────
ALL_TABLES = [
    "documents", "users", "invite_tokens", "office_qr_codes", "saved_offices",
    "activity_log", "routing_slips", "office_traffic", "doc_qr_tokens",
    "password_reset_tokens", "password_reset_rate_limits", "dropdown_options",
    "push_tokens", "user_carts", "appointments", "so_records", "staff_pairings",
    "staff_groups", "staff_group_members", "transfer_batches", "import_batches",
]
# What create_backup() actually serializes (services/backup.py:create_backup)
COVERED_TABLES = ["documents", "users", "routing_slips", "saved_offices", "office_traffic"]
UNCOVERED_TABLES = [t for t in ALL_TABLES if t not in COVERED_TABLES]

THROWAWAY_MARKERS = ("test", "tmp", "throwaway", "roundtrip", "scratch")
_BACKUP_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "_roundtrip_backup.json")


# ══════════════════════════════════════════════════════════════════════════
#  SAFETY GUARDS
# ══════════════════════════════════════════════════════════════════════════
def _dbname(dsn: str) -> str:
    # naive: last path segment before any ?query
    tail = dsn.split("/")[-1]
    return tail.split("?")[0].lower()


def _assert_throwaway(label: str, dsn: str):
    if not dsn:
        sys.exit(f"ABORT: {label} is not set. Refusing to run without an explicit throwaway DSN.")
    # Never allow the app's real DB.
    try:
        from config import DATABASE_URL as PROD_URL
    except Exception:
        PROD_URL = ""
    if PROD_URL and dsn.strip() == PROD_URL.strip():
        sys.exit(f"ABORT: {label} equals config.DATABASE_URL (the app's real database). Refusing.")
    name = _dbname(dsn)
    if os.environ.get("ROUNDTRIP_FORCE") != "1":
        if not any(m in name for m in THROWAWAY_MARKERS):
            sys.exit(
                f"ABORT: {label} database name '{name}' has no throwaway marker "
                f"({'/'.join(THROWAWAY_MARKERS)}). Set ROUNDTRIP_FORCE=1 to override "
                f"only if you are certain this is disposable."
            )


# ══════════════════════════════════════════════════════════════════════════
#  SUBPROCESS PHASES  (each binds DATABASE_URL to exactly one throwaway DSN)
# ══════════════════════════════════════════════════════════════════════════
def _assert_truncatable(dsn: str):
    """Refuse to TRUNCATE any DB whose name lacks the throwaway marker.

    Same marker gate the orchestrator uses in _assert_throwaway — so a
    truncation can never run against a real database.
    """
    name = _dbname(dsn)
    if os.environ.get("ROUNDTRIP_FORCE") != "1" and not any(m in name for m in THROWAWAY_MARKERS):
        sys.exit(
            f"ABORT: refusing to TRUNCATE database '{name}' — no throwaway marker "
            f"({'/'.join(THROWAWAY_MARKERS)}). Set ROUNDTRIP_FORCE=1 only if you are "
            f"certain this is disposable."
        )


def _truncate_all(cur):
    """Clear EVERY base table in the current (throwaway) DB, resetting identities.

    Makes the harness repeatable: seeding/restoring always starts from empty.
    Gated behind the throwaway-name marker check — it reads the DSN the child
    was bound to (DATABASE_URL) and refuses if the name lacks the marker.
    Enumerates tables dynamically and uses RESTART IDENTITY CASCADE so serial
    counters reset and FK-linked tables clear cleanly.
    """
    _assert_truncatable(os.environ.get("DATABASE_URL", ""))
    cur.execute("""SELECT table_name FROM information_schema.tables
                   WHERE table_schema='public' AND table_type='BASE TABLE'""")
    tables = [r["table_name"] for r in cur.fetchall()]
    if tables:
        joined = ", ".join(f'"{t}"' for t in tables)
        cur.execute(f"TRUNCATE {joined} RESTART IDENTITY CASCADE")


def _seed_all(cur):
    """Truncate, then insert one representative row into every one of the 21 tables.

    Shared by _phase_seed (source) and _phase_atomicity (target baseline).
    """
    # Repeatability: clear first so re-runs start empty (otherwise the fixed
    # seed IDs raise UniqueViolation on the 2nd run).
    _truncate_all(cur)
    if True:
        if True:
            # documents — id lives both as PK and inside data JSONB (app convention)
            cur.execute(
                "INSERT INTO documents (id, data) VALUES (%s, %s)",
                ("doc-0001", json.dumps({
                    "id": "doc-0001", "doc_id": "REF-2026-0001",
                    "doc_name": "Round-trip test memo", "status": "Received",
                    "sender_org": "Test Office", "date_received": "2026-07-06",
                    "deleted": False,
                })),
            )
            # users
            cur.execute(
                """INSERT INTO users (username, password_hash, full_name, role, office, active)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                ("rt_admin", "hash$abc", "Round Trip Admin", "admin", "Records", True),
            )
            # invite_tokens
            cur.execute("INSERT INTO invite_tokens (token, email, name) VALUES (%s,%s,%s)",
                        ("inv-tok-1", "invitee@example.com", "Invitee"))
            # office_qr_codes
            cur.execute("INSERT INTO office_qr_codes (id, action, label) VALUES (%s,%s,%s)",
                        ("oqr-1", "checkin", "Front Desk"))
            # saved_offices — includes primary_recipient (a restore drop-out suspect)
            cur.execute(
                """INSERT INTO saved_offices (office_slug, office_name, created_by, primary_recipient)
                   VALUES (%s,%s,%s,%s)""",
                ("records", "Records Section", "rt_admin", "juan.delacruz"),
            )
            # activity_log
            cur.execute("INSERT INTO activity_log (username, action, detail) VALUES (%s,%s,%s)",
                        ("rt_admin", "seed", "roundtrip seed row"))
            # routing_slips — populate ALL workflow columns the restore is suspected to drop
            cur.execute(
                """INSERT INTO routing_slips
                   (id, slip_no, destination, prepared_by, doc_ids, notes,
                    slip_date, time_from, time_to, from_office, recv_token,
                    rel_token, type, logged_at, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                ("slip-0001", "RS-2026-0001", "Accounting", "rt_admin",
                 json.dumps(["doc-0001"]), "please expedite",
                 "2026-07-06", "09:00", "10:00", "Records Section",
                 "RCV-TOKEN-XYZ", "REL-TOKEN-XYZ", "routing",
                 "2026-07-06 09:05", "Received"),
            )
            # office_traffic
            cur.execute(
                """INSERT INTO office_traffic
                   (office_slug, office_name, event_type, doc_id, client_username)
                   VALUES (%s,%s,%s,%s,%s)""",
                ("records", "Records Section", "scan_in", "doc-0001", "client1"),
            )
            # doc_qr_tokens
            cur.execute("INSERT INTO doc_qr_tokens (token, doc_id, token_type) VALUES (%s,%s,%s)",
                        ("dqr-1", "doc-0001", "receive"))
            # password_reset_tokens
            cur.execute(
                """INSERT INTO password_reset_tokens (token_hash, username, expires_at)
                   VALUES (%s,%s, NOW() + INTERVAL '45 minutes')""",
                ("prt-hash-1", "rt_admin"),
            )
            # password_reset_rate_limits
            cur.execute("INSERT INTO password_reset_rate_limits (scope, identifier) VALUES (%s,%s)",
                        ("ip", "127.0.0.1"))
            # dropdown_options
            cur.execute("INSERT INTO dropdown_options (field_name, options) VALUES (%s,%s)",
                        ("category", json.dumps(["Memo", "Letter"])))
            # push_tokens
            cur.execute("INSERT INTO push_tokens (username, token) VALUES (%s,%s)",
                        ("rt_admin", "expo-push-tok"))
            # user_carts
            cur.execute("INSERT INTO user_carts (username, cart_data) VALUES (%s,%s)",
                        ("rt_admin", json.dumps(["doc-0001"])))
            # appointments
            cur.execute(
                """INSERT INTO appointments (id, client_name, office, service_code, status)
                   VALUES (%s,%s,%s,%s,%s)""",
                ("appt-1", "Client One", "records", "SVC1", "pending"),
            )
            # so_records (FK doc_id → documents.id)
            cur.execute(
                """INSERT INTO so_records
                   (filename, so_type, employee_full_name, generated_by, file_path, doc_id)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                ("SO_0001.pdf", "Travel Order", "Employee One", "rt_admin",
                 "/data/so/SO_0001.pdf", "doc-0001"),
            )
            # staff_pairings
            cur.execute("INSERT INTO staff_pairings (user_a, user_b, created_by) VALUES (%s,%s,%s)",
                        ("rt_admin", "rt_staff", "rt_admin"))
            # staff_groups → capture id for the FK child
            cur.execute("INSERT INTO staff_groups (group_name, created_by) VALUES (%s,%s) RETURNING id",
                        ("Group A", "rt_admin"))
            gid = cur.fetchone()["id"]
            # staff_group_members (FK group_id → staff_groups.id)
            cur.execute(
                "INSERT INTO staff_group_members (group_id, username, added_by) VALUES (%s,%s,%s)",
                (gid, "rt_admin", "rt_admin"),
            )
            # transfer_batches
            cur.execute(
                """INSERT INTO transfer_batches (id, transferred_by, transferred_to, doc_ids)
                   VALUES (%s,%s,%s,%s)""",
                ("tb-1", "rt_admin", "rt_staff", json.dumps(["doc-0001"])),
            )
            # import_batches
            cur.execute(
                """INSERT INTO import_batches (id, imported_by, filename, doc_ids, row_count)
                   VALUES (%s,%s,%s,%s,%s)""",
                ("ib-1", "rt_admin", "import.xlsx", json.dumps(["doc-0001"]), 1),
            )


def _phase_seed():
    """SOURCE db: build full schema, insert representative rows in all 21 tables."""
    from services.database import init_db, get_conn
    init_db()  # _create_tables + _run_migrations → full migrated 21-table schema
    with get_conn() as conn:
        with conn.cursor() as cur:
            _seed_all(cur)
    print("SEED_OK")


def _snapshot(cur, tables):
    """Per-table (count, content-hash) fingerprint of the current DB state.

    Content hash is md5 over the text of every row (order-independent). Excludes
    sequence values (setval is non-transactional, so those may legitimately
    differ after a rolled-back restore).
    """
    snap = {}
    for t in tables:
        cur.execute(f'SELECT COUNT(*) AS c FROM "{t}"')
        cnt = cur.fetchone()["c"]
        cur.execute(
            f'SELECT md5(COALESCE(string_agg(x, %s ORDER BY x), %s)) AS h '
            f'FROM (SELECT r::text AS x FROM "{t}" AS r) sub',
            ("|", ""),
        )
        snap[t] = {"count": cnt, "hash": cur.fetchone()["h"]}
    return snap


def _phase_atomicity():
    """Prove restore atomicity: a mid-restore failure leaves the TARGET UNCHANGED.

    Seeds a known baseline, snapshots it, then runs a REPLACE restore of a backup
    with an injected FK-violating so_records row. The restore must raise
    RestoreError(status=rolled_back) and the target must be byte-identical to the
    baseline afterward — proving the replace-wipe rolled back too.
    """
    from services.database import init_db, get_conn
    from services.backup import restore_backup, RestoreError
    init_db()

    # Baseline: seed the target, then snapshot counts + content hashes.
    with get_conn() as conn:
        with conn.cursor() as cur:
            _seed_all(cur)
    with get_conn() as conn:
        with conn.cursor() as cur:
            baseline = _snapshot(cur, ALL_TABLES)

    # Build a backup guaranteed to fail mid-restore: inject an so_records row
    # whose doc_id references a non-existent document (FK violation against
    # documents, which is loaded BEFORE so_records and AFTER the replace-wipe).
    with open(_BACKUP_JSON, encoding="utf-8") as f:
        bad = json.load(f)
    bad.setdefault("so_records", [])
    bad["so_records"].append({
        "id": 999999, "filename": "atomicity_bad.pdf", "so_type": "X",
        "employee_full_name": "Should Not Persist", "generated_by": "test",
        "file_path": "/x", "doc_id": "__does_not_exist__",
    })

    raised = False
    status = None
    try:
        restore_backup(bad, mode="replace")
    except RestoreError as e:
        raised = True
        status = (e.summary or {}).get("status")
    if not raised:
        sys.exit("ATOMICITY FAIL: restore did NOT raise on an FK-violating row "
                 "(a partial/committed restore is possible)")
    if status != "rolled_back":
        sys.exit(f"ATOMICITY FAIL: expected status 'rolled_back', got {status!r}")

    # The target MUST equal the baseline — proving the wipe rolled back too.
    with get_conn() as conn:
        with conn.cursor() as cur:
            after = _snapshot(cur, ALL_TABLES)
    if after != baseline:
        diffs = {t: {"baseline": baseline.get(t), "after": after.get(t)}
                 for t in ALL_TABLES if baseline.get(t) != after.get(t)}
        sys.exit(f"ATOMICITY FAIL: target changed after a rolled-back restore: {diffs}")

    print("ATOMICITY_STATUS=" + status)
    print("ATOMICITY_OK=1")


def _phase_capture():
    """SOURCE db: run the app's real create_backup() and write JSON to disk."""
    from services.backup import create_backup, live_base_tables
    data = create_backup()
    with open(_BACKUP_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    keys = [k for k in data.keys() if k != "meta"]
    counts = {k: len(data[k]) for k in keys}

    # DRIFT GUARD (test-side): the backup's captured-table set MUST equal the
    # live information_schema set. If a future table #22 is added to the schema
    # but the backup fails to include it, this fails loudly instead of silently
    # shipping a partial backup.
    live = set(live_base_tables())
    captured = set(data.get("meta", {}).get("tables", keys))
    if live != captured:
        sys.exit(
            "DRIFT: backup tables != live schema tables. "
            f"missing_from_backup={sorted(live - captured)} "
            f"extra_in_backup={sorted(captured - live)}"
        )

    print("CAPTURE_KEYS=" + json.dumps(sorted(keys)))
    print("CAPTURE_COUNTS=" + json.dumps(counts))
    print("CAPTURE_TABLES=" + json.dumps(sorted(captured)))
    print("CAPTURE_BYTES=" + str(os.path.getsize(_BACKUP_JSON)))


def _phase_prep_target():
    """TARGET db: build the full schema, clear it, assert it starts empty."""
    from services.database import init_db, get_conn
    init_db()
    # Fully clear the TARGET first. The restore's own replace-wipe only covers a
    # subset of tables (documents/routing_slips/saved_offices/office_traffic), so
    # the target must be truncated wholesale to guarantee a clean-slate restore
    # and an honest diff on re-runs.
    with get_conn() as conn:
        with conn.cursor() as cur:
            _truncate_all(cur)
    nonempty = {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            for t in ALL_TABLES:
                cur.execute(f"SELECT COUNT(*) AS c FROM {t}")
                c = cur.fetchone()["c"]
                if c:
                    nonempty[t] = c
    if nonempty:
        sys.exit(f"ABORT: TARGET db is not empty before restore: {nonempty}. "
                 f"Point ROUNDTRIP_TARGET_URL at a fresh empty database.")
    print("PREP_OK")


def _phase_restore():
    """TARGET db: run the app's real restore_backup() in REPLACE mode."""
    from services.backup import restore_backup
    with open(_BACKUP_JSON, encoding="utf-8") as f:
        backup = json.load(f)
    summary = restore_backup(backup, mode="replace")
    print("RESTORE_SUMMARY=" + json.dumps(summary, default=str))


def _phase_diff():
    """TARGET db: count all 21 tables + sample the drop-out-suspect rows."""
    from services.database import get_conn
    counts = {}
    samples = {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            for t in ALL_TABLES:
                cur.execute(f"SELECT COUNT(*) AS c FROM {t}")
                counts[t] = cur.fetchone()["c"]
            cur.execute("""SELECT slip_no, status, from_office, recv_token,
                                  rel_token, logged_at, type
                           FROM routing_slips ORDER BY slip_no LIMIT 2""")
            samples["routing_slips"] = [dict(r) for r in cur.fetchall()]
            cur.execute("""SELECT office_slug, office_name, created_by, primary_recipient
                           FROM saved_offices ORDER BY office_slug LIMIT 2""")
            samples["saved_offices"] = [dict(r) for r in cur.fetchall()]
    print("DIFF_COUNTS=" + json.dumps(counts, default=str))
    print("DIFF_SAMPLES=" + json.dumps(samples, default=str))


_PHASES = {
    "seed": _phase_seed,
    "capture": _phase_capture,
    "prep_target": _phase_prep_target,
    "restore": _phase_restore,
    "diff": _phase_diff,
    "atomicity": _phase_atomicity,
}


# ══════════════════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════
def _run_phase(phase: str, dsn: str) -> dict:
    """Spawn a child bound to `dsn`, capture its PHASE=<json> lines."""
    env = dict(os.environ)
    env["DATABASE_URL"] = dsn          # bind the app pool to this throwaway only
    env["ROUNDTRIP_PHASE"] = phase
    # Put the project root on the child's import path too, so its inner
    # 'from services.database import ...' resolves regardless of cwd.
    _existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (_PROJECT_ROOT + os.pathsep + _existing_pp) if _existing_pp else _PROJECT_ROOT
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        env=env, capture_output=True, text=True,
        cwd=_PROJECT_ROOT,
    )
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        sys.exit(f"Phase '{phase}' failed (exit {proc.returncode}).")
    out = {}
    for line in proc.stdout.splitlines():
        if "=" in line and line.split("=", 1)[0].isupper():
            k, v = line.split("=", 1)
            out[k] = v
    return out


def main():
    src = os.environ.get("ROUNDTRIP_SOURCE_URL", "")
    tgt = os.environ.get("ROUNDTRIP_TARGET_URL", "")
    _assert_throwaway("ROUNDTRIP_SOURCE_URL", src)
    _assert_throwaway("ROUNDTRIP_TARGET_URL", tgt)
    if src.strip() == tgt.strip():
        sys.exit("ABORT: source and target must be different databases.")

    print("=" * 74)
    print("FULL BACKUP ROUND-TRIP HARNESS")
    print(f"  source (seed+backup): {_dbname(src)}")
    print(f"  target (restore):     {_dbname(tgt)}")
    print("=" * 74)

    _run_phase("seed", src)
    cap = _run_phase("capture", src)
    _run_phase("prep_target", tgt)
    _run_phase("restore", tgt)
    diff = _run_phase("diff", tgt)

    cap_counts = json.loads(cap.get("CAPTURE_COUNTS", "{}"))
    counts = json.loads(diff.get("DIFF_COUNTS", "{}"))
    samples = json.loads(diff.get("DIFF_SAMPLES", "{}"))

    print("\n" + "=" * 74)
    print("REPORT")
    print("=" * 74)
    print(f"Backup file: {_BACKUP_JSON}  ({cap.get('CAPTURE_BYTES','?')} bytes)")
    print(f"Backup top-level data keys ({len(cap_counts)}): "
          f"{json.dumps(cap_counts)}")

    print("\nPer-table row count in TARGET after restore (all 21):")
    for t in ALL_TABLES:
        tag = "covered" if t in COVERED_TABLES else "NOT in backup"
        print(f"  {t:<28} {counts.get(t, '?'):>4}   [{tag}]")

    empty_because_uncovered = [t for t in UNCOVERED_TABLES if counts.get(t, 0) == 0]
    print(f"\nTables at 0 rows purely because backup never contained them "
          f"({len(empty_because_uncovered)} expected 16):")
    print("  " + ", ".join(empty_because_uncovered))

    print("\nCovered-table fidelity (restored vs seeded=1 each):")
    for t in COVERED_TABLES:
        print(f"  {t:<28} restored={counts.get(t,'?')}")

    print("\nSpotlight — routing_slips restored row(s):")
    for row in samples.get("routing_slips", []):
        print(f"  {json.dumps(row)}")
    print("Spotlight — saved_offices restored row(s):")
    for row in samples.get("saved_offices", []):
        print(f"  {json.dumps(row)}")

    print("\nInterpretation hints:")
    print("  * routing_slips: status should be 'Received' and from_office/recv_token/")
    print("    rel_token/logged_at should be the seeded values. If status='Routed' and")
    print("    those fields are null, the restore dropped them (expected current bug).")
    print("  * saved_offices: primary_recipient should be 'juan.delacruz'. If null,")
    print("    restore dropped it (expected current bug).")
    print("=" * 74)

    # ── Stage 3: atomicity proof (separate phase; re-seeds the target) ──
    atom = _run_phase("atomicity", tgt)
    print("\n" + "=" * 74)
    print("ATOMICITY PROOF (rolled-back restore leaves target unchanged)")
    print("=" * 74)
    print(f"  restore raised RestoreError, status = {atom.get('ATOMICITY_STATUS','?')}")
    print(f"  target identical to baseline after rollback: "
          f"{'YES' if atom.get('ATOMICITY_OK') == '1' else 'NO'}")
    print("=" * 74)


if __name__ == "__main__":
    phase = os.environ.get("ROUNDTRIP_PHASE")
    if phase:
        # Child invocation: DATABASE_URL is already bound to one throwaway DSN.
        _PHASES[phase]()
    else:
        main()
