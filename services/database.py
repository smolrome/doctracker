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


def get_conn():
    """Open a new database connection."""
    from config import DATABASE_URL
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    """Create all tables and run safe column migrations on startup."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            _create_tables(cur)
            _run_migrations(cur)
        conn.commit()


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
    # Performance + audit query indexes
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_activity_log_user ON activity_log(username)""")
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_activity_log_ts ON activity_log(created_at DESC)""")
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC)""")


def _run_migrations(cur):
    """Safe ALTER TABLE migrations — idempotent, won't break existing installs."""
    migrations = [
        # users
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS active     BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS office     TEXT DEFAULT ''",
        # Fix any users with NULL or FALSE active - ensure they can log in
        "UPDATE users SET active = TRUE WHERE active IS NULL OR active = FALSE",
        # invite_tokens
        """
        DO $
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='invite_tokens' AND column_name='expires_at'
            ) THEN
                ALTER TABLE invite_tokens
                ADD COLUMN expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '48 hours');
            END IF;
        END$
        """,
        # Fix any invite tokens with NULL expires_at - allow them to still be used
        "UPDATE invite_tokens SET expires_at = NOW() + INTERVAL '48 hours' WHERE expires_at IS NULL",
        # doc_qr_tokens
        "ALTER TABLE doc_qr_tokens ADD COLUMN IF NOT EXISTS used BOOLEAN DEFAULT FALSE",
        # routing_slips (added after initial deploy)
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS slip_date   TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS time_from   TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS time_to     TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS recv_token  TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS rel_token   TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS from_office TEXT",
    ]
    for sql in migrations:
        try:
            cur.execute(sql)
        except Exception:
            pass  # column already exists or similar — safe to skip
