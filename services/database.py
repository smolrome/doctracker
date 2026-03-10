"""
services/database.py — Database connection, initialization, and migrations.
Supports PostgreSQL (Railway) with automatic JSON file fallback for local dev.
"""
import os
import json

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from config import DATABASE_URL
    USE_DB = bool(DATABASE_URL)
except ImportError:
    USE_DB = False


class _ConnCtx:
    """Wraps a psycopg2 connection so `with get_conn() as conn:` auto-closes it."""
    def __init__(self, conn):
        self._conn = conn
    def __enter__(self):
        return self._conn
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()
        finally:
            self._conn.close()  # ALWAYS close, even if commit/rollback raises
        return False
    # Forward attribute access so conn.cursor() etc. work directly too
    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_conn():
    """Open a new database connection. Use as context manager — auto commits/closes."""
    from config import DATABASE_URL
    raw = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return _ConnCtx(raw)


def init_db():
    """Create all tables and run safe column migrations on startup."""
    print("[init_db] Starting database initialization...")
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                _create_tables(cur)
                _run_migrations(cur)
        print("[init_db] ✅ Database initialized successfully.")
    except Exception as e:
        print(f"[init_db] ❌ FAILED: {type(e).__name__}: {e}")
        raise


def _create_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id         TEXT PRIMARY KEY,
            data       JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name     TEXT,
            role          TEXT DEFAULT 'staff',
            office        TEXT DEFAULT '',
            active        BOOLEAN DEFAULT TRUE,
            last_login    TIMESTAMP,
            created_at    TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invite_tokens (
            token      TEXT PRIMARY KEY,
            email      TEXT NOT NULL,
            name       TEXT,
            used       BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '48 hours')
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS office_qr_codes (
            id         TEXT PRIMARY KEY,
            action     TEXT NOT NULL,
            label      TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_offices (
            office_slug TEXT PRIMARY KEY,
            office_name TEXT NOT NULL,
            created_by  TEXT,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id         SERIAL PRIMARY KEY,
            username   TEXT,
            action     TEXT NOT NULL,
            ip_address TEXT,
            detail     TEXT,
            ts         TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS routing_slips (
            id          TEXT PRIMARY KEY,
            slip_no     TEXT NOT NULL,
            destination TEXT NOT NULL,
            prepared_by TEXT,
            doc_ids     JSONB NOT NULL,
            notes       TEXT,
            slip_date   TEXT,
            time_from   TEXT,
            time_to     TEXT,
            from_office TEXT,
            recv_token  TEXT,
            rel_token   TEXT,
            type        TEXT DEFAULT 'routing',
            logged_at   TEXT,
            status      TEXT DEFAULT 'In Transit',
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS office_traffic (
            id               SERIAL PRIMARY KEY,
            office_slug      TEXT NOT NULL,
            office_name      TEXT NOT NULL,
            event_type       TEXT NOT NULL,
            doc_id           TEXT,
            client_username  TEXT,
            scanned_at       TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS doc_qr_tokens (
            token      TEXT PRIMARY KEY,
            doc_id     TEXT NOT NULL,
            token_type TEXT NOT NULL,
            used       BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # Customizable dropdown options for document types
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dropdown_options (
            id          SERIAL PRIMARY KEY,
            field_name  TEXT NOT NULL UNIQUE,
            options     JSONB NOT NULL DEFAULT '[]',
            created_at  TIMESTAMP DEFAULT NOW(),
            updated_at  TIMESTAMP DEFAULT NOW()
        )
    """)
    # Performance + audit query indexes
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_activity_log_user ON activity_log(username)""")
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_activity_log_ts ON activity_log(ts DESC)""")
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC)""")


def _run_migrations(cur):
    """Safe ALTER TABLE migrations — idempotent, won't break existing installs."""
    migrations = [
        # users
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS active     BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS office     TEXT DEFAULT ''",
        # invite_tokens — add expires_at if missing
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='invite_tokens' AND column_name='expires_at'
            ) THEN
                ALTER TABLE invite_tokens
                ADD COLUMN expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '48 hours');
            END IF;
        END$$
        """,
        # backfill NULL expires_at for any legacy tokens (set to 48h from now so they still work)
        """UPDATE invite_tokens
           SET expires_at = NOW() + INTERVAL '48 hours'
           WHERE expires_at IS NULL AND used = FALSE""",
        # doc_qr_tokens
        "ALTER TABLE doc_qr_tokens ADD COLUMN IF NOT EXISTS used BOOLEAN DEFAULT FALSE",
        # routing_slips (added after initial deploy)
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS slip_date   TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS time_from   TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS time_to     TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS recv_token  TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS rel_token   TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS from_office TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS type        TEXT DEFAULT 'routing'",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS logged_at   TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS status      TEXT DEFAULT 'In Transit'",
    ]
    for sql in migrations:
        try:
            cur.execute("SAVEPOINT mig")
            cur.execute(sql)
            cur.execute("RELEASE SAVEPOINT mig")
        except Exception as e:
            cur.execute("ROLLBACK TO SAVEPOINT mig")  # keep transaction alive
            print(f"Migration skipped (ok): {str(e)[:120]}")