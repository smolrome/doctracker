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
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
            print(f"load_docs error: {e}")
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
            print(f"get_doc error: {e}")
            return None
    return next((d for d in load_docs() if d["id"] == doc_id), None)


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
            print(f"insert_doc error: {e}")
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
            print(f"save_doc error: {e}")
    else:
        docs = load_docs()
        for i, d in enumerate(docs):
            if d["id"] == doc["id"]:
                docs[i] = doc
                break
        else:
            docs.insert(0, doc)
        _save_docs_json(docs)


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


# ── Statistics ────────────────────────────────────────────────────────────────

def get_stats(docs: list[dict]) -> dict:
    return {
        "total":      len(docs),
        "pending":    sum(1 for d in docs if d["status"] == "Pending"),
        "released":   sum(1 for d in docs if d["status"] == "Released"),
        "on_hold":    sum(1 for d in docs if d["status"] == "On Hold"),
        "in_review":  sum(1 for d in docs if d["status"] == "In Review"),
        "in_transit": sum(1 for d in docs if d["status"] == "In Transit"),
    }


# ── Private ───────────────────────────────────────────────────────────────────

def _save_docs_json(docs: list[dict]):
    with open(DATA_FILE, "w") as f:
        json.dump(docs, f, indent=2)
