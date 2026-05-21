"""
services/database.py — Database connection, initialization, and migrations.
Supports PostgreSQL with automatic JSON file fallback for local dev.
"""
import os
import json

try:
    import psycopg2
    from psycopg2 import pool as pg_pool
    from psycopg2.extras import RealDictCursor
    from config import DATABASE_URL
    USE_DB = bool(DATABASE_URL)
except ImportError:
    USE_DB = False

_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        _pool = pg_pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=DATABASE_URL,
            cursor_factory=RealDictCursor,
        )
    return _pool


class _ConnCtx:
    """Borrows a connection from the pool; returns it on exit."""
    def __init__(self):
        self._conn = None

    def __enter__(self):
        self._conn = _get_pool().getconn()
        self._conn.autocommit = False
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        _get_pool().putconn(self._conn)
        return False


def get_conn():
    """Borrow a connection from the pool. Use as context manager — auto commits/returns."""
    return _ConnCtx()


def init_db():
    """Create all tables and run safe column migrations on startup."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                _create_tables(cur)
                _run_migrations(cur)
    except Exception as e:
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
            created_at  TIMESTAMP DEFAULT NOW(),
            primary_recipient TEXT
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
            status      TEXT DEFAULT 'Routed',
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS push_tokens (
            username   TEXT PRIMARY KEY,
            token      TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_carts (
            username   TEXT PRIMARY KEY,
            cart_data  JSONB NOT NULL DEFAULT '[]',
            saved_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id              TEXT PRIMARY KEY,
            client_name     TEXT NOT NULL,
            client_username TEXT DEFAULT '',
            office          TEXT DEFAULT '',
            service_code    TEXT DEFAULT '',
            service_name    TEXT DEFAULT '',
            preferred_date  TEXT DEFAULT '',
            preferred_time  TEXT DEFAULT '',
            purpose         TEXT DEFAULT '',
            status          TEXT DEFAULT 'pending',
            queue_ticket    TEXT DEFAULT NULL,
            queue_ticket_id INTEGER DEFAULT NULL,
            source          TEXT DEFAULT 'web',
            notes           TEXT DEFAULT '',
            created_at      TEXT DEFAULT '',
            updated_at      TEXT DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS so_records (
            id                 SERIAL PRIMARY KEY,
            filename           VARCHAR(255) NOT NULL,
            so_type            VARCHAR(100) NOT NULL,
            employee_full_name VARCHAR(255) NOT NULL,
            employee_position  VARCHAR(255),
            date_issued        VARCHAR(50),
            generated_by       VARCHAR(100) NOT NULL,
            generated_at       TIMESTAMP DEFAULT NOW(),
            file_path          VARCHAR(500) NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS staff_pairings (
            id         SERIAL PRIMARY KEY,
            user_a     TEXT NOT NULL,
            user_b     TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_a, user_b)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS staff_groups (
            id         SERIAL PRIMARY KEY,
            group_name TEXT NOT NULL UNIQUE,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS staff_group_members (
            id       SERIAL PRIMARY KEY,
            group_id INTEGER REFERENCES staff_groups(id) ON DELETE CASCADE,
            username TEXT NOT NULL,
            added_by TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(group_id, username)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transfer_batches (
            id                    TEXT PRIMARY KEY,
            transferred_by        TEXT NOT NULL,
            transferred_to        TEXT NOT NULL,
            transferred_to_office TEXT,
            transferred_to_name   TEXT,
            transfer_type         TEXT,
            doc_ids               JSONB NOT NULL,
            created_at            TIMESTAMP DEFAULT NOW()
        )
    """)
    # Performance + audit query indexes
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_activity_log_user ON activity_log(username)""")
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_activity_log_ts ON activity_log(ts DESC)""")
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC)""")
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_so_records_generated ON so_records(generated_at DESC)""")


def _run_migrations(cur):
    """Safe ALTER TABLE migrations — idempotent, won't break existing installs."""
    migrations = [
        # users
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS active     BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS office     TEXT DEFAULT ''",
        # Client approval - clients must be approved by admin before using their account
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS approved   BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email      TEXT DEFAULT ''",
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
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS status      TEXT DEFAULT 'Routed'",
        # New reroute fields
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS is_rerouted         BOOLEAN DEFAULT FALSE",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS archived_at       TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS archived_by      TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS rerouted_to      TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS original_slip_id TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS original_slip_no TEXT",
        "ALTER TABLE routing_slips ADD COLUMN IF NOT EXISTS rerouted_from     TEXT",
    ]
    # Migration for saved_offices primary_recipient
    migrations.append(
        "ALTER TABLE saved_offices ADD COLUMN IF NOT EXISTS primary_recipient TEXT"
    )
    migrations.append("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS assigned_to TEXT DEFAULT ''")
    migrations.append("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS assigned_to_name TEXT DEFAULT ''")
    migrations.append("ALTER TABLE users ADD COLUMN IF NOT EXISTS can_generate_so BOOLEAN DEFAULT FALSE")
    migrations.append("ALTER TABLE users ADD COLUMN IF NOT EXISTS can_route_documents BOOLEAN DEFAULT FALSE")
    migrations.append("CREATE INDEX IF NOT EXISTS idx_staff_pairings_a ON staff_pairings(user_a)")
    migrations.append("CREATE INDEX IF NOT EXISTS idx_staff_pairings_b ON staff_pairings(user_b)")
    migrations.append("CREATE INDEX IF NOT EXISTS idx_sgm_group ON staff_group_members(group_id)")
    migrations.append("CREATE INDEX IF NOT EXISTS idx_sgm_username ON staff_group_members(username)")
    migrations.append("ALTER TABLE staff_groups ADD COLUMN IF NOT EXISTS has_so_access BOOLEAN DEFAULT FALSE")
    migrations.append("ALTER TABLE staff_groups ADD COLUMN IF NOT EXISTS has_shared_dashboard BOOLEAN DEFAULT TRUE")
    migrations.append("CREATE TABLE IF NOT EXISTS transfer_batches (id TEXT PRIMARY KEY, transferred_by TEXT NOT NULL, transferred_to TEXT NOT NULL, transferred_to_office TEXT, transferred_to_name TEXT, transfer_type TEXT, doc_ids JSONB NOT NULL, created_at TIMESTAMP DEFAULT NOW())")
    migrations.append("ALTER TABLE so_records ADD COLUMN IF NOT EXISTS doc_id TEXT REFERENCES documents(id) ON DELETE SET NULL")
    for sql in migrations:
        try:
            cur.execute("SAVEPOINT mig")
            cur.execute(sql)
            cur.execute("RELEASE SAVEPOINT mig")
        except Exception as e:
            cur.execute("ROLLBACK TO SAVEPOINT mig")  # keep transaction alive


def get_doc_by_id(doc_id: str):
    """Fetch a document by its internal id. Returns the data dict or None."""
    if not USE_DB or not doc_id:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM documents WHERE id = %s", (doc_id,))
                row = cur.fetchone()
                if not row:
                    return None
                data = row['data']
                if isinstance(data, str):
                    import json
                    data = json.loads(data)
                return data
    except Exception as e:
        print(f"Error in get_doc_by_id: {e}")
        return None


def get_paired_usernames(username: str) -> list:
    """Legacy pair-based lookup — kept for backwards compatibility."""
    if not USE_DB or not username:
        return []
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_b AS partner FROM staff_pairings WHERE user_a = %s
                    UNION
                    SELECT user_a AS partner FROM staff_pairings WHERE user_b = %s
                """, (username, username))
                rows = cur.fetchall()
                return [r['partner'] for r in rows]
    except Exception:
        return []


def get_user_can_route_documents(username: str) -> bool:
    """Return the can_route_documents flag for a user. Defaults to False if not set."""
    uname = username.lower().strip()
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT can_route_documents FROM users WHERE username = %s", (uname,)
                    )
                    row = cur.fetchone()
            return bool(row["can_route_documents"]) if row else False
        except Exception:
            return False
    else:
        return False


def set_user_can_route_documents(username: str, value: bool) -> tuple:
    """Set the can_route_documents flag for a user."""
    uname = username.lower().strip()
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET can_route_documents = %s WHERE username = %s",
                        (value, uname),
                    )
            return True, None
        except Exception as e:
            return False, f"Database error: {e}"
    else:
        return False, "Database not available."


def get_group_usernames(username: str) -> list:
    """Return all usernames that share a shared_dashboard group with this user (excluding self)."""
    if not USE_DB or not username:
        return []
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT sgm2.username
                    FROM staff_group_members sgm1
                    JOIN staff_group_members sgm2 ON sgm1.group_id = sgm2.group_id
                    JOIN staff_groups sg ON sgm1.group_id = sg.id
                    WHERE sgm1.username = %s AND sgm2.username != %s
                      AND sg.has_shared_dashboard = TRUE
                """, (username, username))
                rows = cur.fetchall()
                return [list(row.values())[0] for row in rows]
    except Exception as e:
        print(f"Error getting group usernames: {e}")
        return []


def user_has_so_access(username: str) -> bool:
    """Return True if user is member of any group with has_so_access = TRUE."""
    if not USE_DB or not username:
        return False
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM staff_group_members sgm
                    JOIN staff_groups sg ON sgm.group_id = sg.id
                    WHERE sgm.username = %s AND sg.has_so_access = TRUE
                    LIMIT 1
                """, (username,))
                return cur.fetchone() is not None
    except Exception as e:
        print(f"Error checking SO access: {e}")
        return False


def create_transfer_batch(batch_id, transferred_by, transferred_to,
                          transferred_to_office, transferred_to_name,
                          transfer_type, doc_ids):
    if not USE_DB:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO transfer_batches
                    (id, transferred_by, transferred_to, transferred_to_office,
                     transferred_to_name, transfer_type, doc_ids, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (id) DO NOTHING
            """, (batch_id, transferred_by, transferred_to, transferred_to_office,
                  transferred_to_name, transfer_type, json.dumps(doc_ids)))


def get_transfer_batch(batch_id):
    if not USE_DB:
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM transfer_batches WHERE id = %s", (batch_id,))
            return cur.fetchone()


def get_transfer_history(username, role):
    if not USE_DB:
        return []
    with get_conn() as conn:
        with conn.cursor() as cur:
            if role == 'admin':
                cur.execute("SELECT * FROM transfer_batches ORDER BY created_at DESC")
            else:
                cur.execute(
                    "SELECT * FROM transfer_batches WHERE transferred_by = %s ORDER BY created_at DESC",
                    (username,)
                )
            return cur.fetchall()