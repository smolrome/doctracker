"""
services/documents.py — Document CRUD, filtering, and statistics.
Transparent DB / JSON-file switch.
"""
import json
import os
import uuid
from datetime import datetime

from services.database import USE_DB, get_conn
from config import DATA_FILE


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_str() -> str:
    # Use Asia/Manila timezone (UTC+8) for local time
    from datetime import datetime, timezone, timedelta
    Manila_tz = timezone(timedelta(hours=8))
    return datetime.now(Manila_tz).strftime("%Y-%m-%d %H:%M:%S")


def generate_ref() -> str:
    """Generate a readable reference like REF-2026-A3F9."""
    return f"REF-{datetime.now().year}-{uuid.uuid4().hex[:4].upper()}"


# ── CRUD ──────────────────────────────────────────────────────────────────────

def load_docs(include_deleted: bool = False) -> list[dict]:
    """Load all documents. Soft-deleted items excluded by default."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT data FROM documents ORDER BY created_at DESC")
                    docs = [row["data"] for row in cur.fetchall()]
        except Exception as e:
            docs = []
    else:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE) as f:
                docs = json.load(f)
        else:
            docs = []

    if not include_deleted:
        docs = [d for d in docs if not d.get("deleted")]
    return docs


def get_doc(doc_id: str) -> dict | None:
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT data FROM documents WHERE id=%s", (doc_id,))
                    row = cur.fetchone()
                    return row["data"] if row else None
        except Exception as e:
            return None
    return next((d for d in load_docs() if d["id"] == doc_id), None)


def get_docs_by_ids(doc_ids: list[str]) -> dict[str, dict]:
    """Fetch multiple documents in one query. Returns {id: doc} dict."""
    if not doc_ids:
        return {}
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT data FROM documents WHERE id = ANY(%s)",
                        (list(doc_ids),)
                    )
                    return {row["data"]["id"]: row["data"] for row in cur.fetchall()}
        except Exception as e:
            return {}
    # JSON fallback — load once, filter
    all_docs = load_docs(include_deleted=True)
    id_set = set(doc_ids)
    return {d["id"]: d for d in all_docs if d.get("id") in id_set}


def insert_doc(doc: dict):
    """Insert a brand-new document."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO documents (id, data, created_at) VALUES (%s, %s::jsonb, %s)",
                        (doc["id"], json.dumps(doc), doc.get("created_at", now_str()))
                    )
                conn.commit()
        except Exception as e:
            pass
    else:
        docs = load_docs()
        docs.insert(0, doc)
        _save_docs_json(docs)


def save_doc(doc: dict):
    """Upsert an existing document."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO documents (id, data, created_at)
                           VALUES (%s, %s::jsonb, %s)
                           ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data""",
                        (doc["id"], json.dumps(doc), doc.get("created_at", now_str()))
                    )
                conn.commit()
        except Exception as e:
            pass
    else:
        docs = load_docs()
        for i, d in enumerate(docs):
            if d["id"] == doc["id"]:
                docs[i] = doc
                break
        else:
            docs.insert(0, doc)
        _save_docs_json(docs)


def batch_save_docs(docs: list[dict]):
    """Save multiple documents in a single DB transaction."""
    if not docs:
        return
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    for doc in docs:
                        cur.execute(
                            """INSERT INTO documents (id, data, created_at)
                               VALUES (%s, %s::jsonb, %s)
                               ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data""",
                            (doc["id"], json.dumps(doc), doc.get("created_at", now_str()))
                        )
                conn.commit()
        except Exception as e:
            pass
    else:
        # JSON fallback — load once, update all, save once
        all_docs = load_docs(include_deleted=True)
        doc_map = {d["id"]: i for i, d in enumerate(all_docs)}
        for doc in docs:
            if doc["id"] in doc_map:
                all_docs[doc_map[doc["id"]]] = doc
            else:
                all_docs.insert(0, doc)
        _save_docs_json(all_docs)


def delete_doc(doc_id: str, deleted_by: str = ""):
    """Soft delete — never physically removes from DB."""
    doc = get_doc(doc_id)
    if not doc:
        return
    doc.update({
        "deleted":    True,
        "deleted_by": deleted_by or "unknown",
        "deleted_at": now_str(),
    })
    save_doc(doc)


def restore_doc(doc_id: str):
    """Undo a soft delete."""
    doc = get_doc(doc_id)
    if not doc:
        return
    doc.pop("deleted", None)
    doc.pop("deleted_by", None)
    doc.pop("deleted_at", None)
    save_doc(doc)


def delete_doc_forever(doc_id: str):
    """Permanently delete a document from the database."""
    if USE_DB:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
            conn.commit()
    else:
        # JSON file storage
        all_docs = load_docs(include_deleted=True)
        all_docs = [d for d in all_docs if d.get("id") != doc_id]
        _save_docs_json(all_docs)


# ── Statistics ────────────────────────────────────────────────────────────────

def get_stats(docs: list[dict]) -> dict:
    return {
        "total":      len(docs),
        "logged":     sum(1 for d in docs if d.get("status") == "Logged"),
        "pending":    sum(1 for d in docs if d.get("status") == "Pending"),
        "received":   sum(1 for d in docs if d.get("status") == "Received"),
        "in_review":  sum(1 for d in docs if d.get("status") == "In Review"),
        "in_transit": sum(1 for d in docs if d.get("status") == "In Transit"),
        "released":   sum(1 for d in docs if d.get("status") == "Released"),
        "on_hold":    sum(1 for d in docs if d.get("status") == "On Hold"),
        "archived":   sum(1 for d in docs if d.get("status") == "Archived"),
    }


# ── Private ───────────────────────────────────────────────────────────────────

def _save_docs_json(docs: list[dict]):
    with open(DATA_FILE, "w") as f:
        json.dump(docs, f, indent=2)
