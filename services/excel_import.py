"""
services/excel_import.py — Import documents from an Excel spreadsheet.

Supports the DepEd Leyte Division tracking sheet format:
  INITIAL DATE | TIME | RECEIVED BY | UNIT/OFFICE/SCHOOL/DISTRICT |
  SOURCE|SENDER | CONTENT PARTICULARS | REFERRED TO | FORWARDED TO |
  DATE & RELEASE TIME | ROUTED TO | USER EMAIL | RECEIVED BY/REMARKS
"""

import json
import uuid
from datetime import datetime

import pandas as pd

from services.documents import now_str, generate_ref

COLUMN_MAP = {
    "initial date":                "date_received",
    "date received":               "date_received",
    "date":                        "date_received",
    "time":                        "time_received",
    "time received":               "time_received",
    "received by":                 "received_by",
    "unit/office/school/district": "sender_org",
    "unit/office/school":          "sender_org",
    "office":                      "sender_org",
    "unit":                        "sender_org",
    "school":                      "sender_org",
    "source|sender":               "sender_name",
    "source/sender":               "sender_name",
    "sender":                      "sender_name",
    "source":                      "sender_name",
    "content particulars":         "doc_name",
    "content":                     "doc_name",
    "particulars":                 "doc_name",
    "document":                    "doc_name",
    "subject":                     "doc_name",
    "referred to":                 "referred_to",
    "forwarded to":                "forwarded_to",
    "date & release time":         "date_released",
    "date released":               "date_released",
    "release date":                "date_released",
    "routed to":                   "routed_to",
    "user email":                  "user_email",
    "email":                       "user_email",
    "received by/remarks":         "notes",
    "remarks":                     "notes",
    "notes":                       "notes",
}


def _norm(col: str) -> str:
    return str(col).strip().lower()


def _str(val) -> str:
    if val is None:
        return ""
    try:
        import math
        if math.isnan(float(val)):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def parse_excel(file_bytes: bytes, filename: str) -> tuple[list[dict], list[str]]:
    import io
    warnings = []
    try:
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception as e:
        return [], [f"Could not open file: {e}"]

    sheet = xl.sheet_names[0]
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=None)

    if df.empty:
        return [], ["The spreadsheet appears to be empty."]

    header_row = 0
    for i, row in df.iterrows():
        non_null = [c for c in row if isinstance(c, str) and c.strip()]
        if len(non_null) >= 3:
            header_row = i
            break

    headers = [_norm(c) for c in df.iloc[header_row]]
    data_rows = df.iloc[header_row + 1:].reset_index(drop=True)

    col_index = {}
    for i, h in enumerate(headers):
        field = COLUMN_MAP.get(h)
        if field and field not in col_index:
            col_index[field] = i

    if "doc_name" not in col_index:
        warnings.append("Could not find a 'Content Particulars' column. Rows imported with blank title.")

    parsed = []
    for _, row in data_rows.iterrows():
        row = list(row)

        def get(field):
            idx = col_index.get(field)
            return _str(row[idx]) if idx is not None and idx < len(row) else ""

        doc_name = get("doc_name")
        sender   = get("sender_name")
        org      = get("sender_org")

        if not any([doc_name, sender, org]):
            continue

        parsed.append({
            "doc_name":     doc_name or "(No title)",
            "sender_name":  sender,
            "sender_org":   org,
            "received_by":  get("received_by"),
            "referred_to":  get("referred_to"),
            "forwarded_to": get("forwarded_to"),
            "routed_to":    get("routed_to"),
            "date_received":get("date_received"),
            "time_received":get("time_received"),
            "date_released":get("date_released"),
            "user_email":   get("user_email"),
            "notes":        get("notes"),
        })

    if not parsed:
        warnings.append("No data rows found after the header row.")

    return parsed, warnings


def import_excel(file_bytes: bytes, filename: str,
                 imported_by: str, default_status: str = "Received",
                 skip_duplicates: bool = True) -> dict:
    """Parse and batch-insert all rows in a single DB transaction."""
    rows, warnings = parse_excel(file_bytes, filename)

    summary = {
        "total":    len(rows),
        "imported": 0,
        "skipped":  0,
        "errors":   [],
        "warnings": warnings,
        "docs":     [],
    }

    if not rows:
        return summary

    # Build all doc dicts first (no DB calls yet)
    docs_to_insert = []
    for row in rows:
        try:
            uid    = str(uuid.uuid4())[:8].upper()
            doc_id = generate_ref()
            ts     = now_str()
            doc = {
                "id":           uid,
                "doc_id":       doc_id,
                "doc_name":     row["doc_name"],
                "category":     "Special Order",
                "status":       default_status,
                "sender_name":  row["sender_name"],
                "sender_org":   row["sender_org"],
                "received_by":  row["received_by"],
                "referred_to":  row["referred_to"],
                "forwarded_to": row["forwarded_to"],
                "routed_to":    row["routed_to"],
                "date_received":row["date_received"],
                "date_released":row["date_released"],
                "notes":        row["notes"],
                "created_at":   ts,
                "created_by":   imported_by,
                "source":       f"Imported from {filename}",
                "deleted":      False,
            }
            docs_to_insert.append(doc)
            summary["docs"].append({
                "doc_id":   doc_id,
                "doc_name": row["doc_name"][:60],
            })
        except Exception as e:
            summary["errors"].append(f"{row.get('doc_name','?')[:40]}: {e}")

    # Single batch insert — one DB connection for all rows
    if docs_to_insert:
        try:
            _batch_insert(docs_to_insert)
            summary["imported"] = len(docs_to_insert)
        except Exception as e:
            summary["errors"].append(f"Batch insert failed: {e}")
            summary["imported"] = 0
            summary["docs"] = []

    return summary


def _batch_insert(docs: list[dict]):
    """Insert all docs in one DB transaction to avoid timeout."""
    from services.database import USE_DB, get_conn
    from services.documents import _save_docs_json, load_docs

    if USE_DB:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for doc in docs:
                    cur.execute(
                        "INSERT INTO documents (id, data, created_at) "
                        "VALUES (%s, %s::jsonb, %s) ON CONFLICT (id) DO NOTHING",
                        (doc["id"], json.dumps(doc), doc.get("created_at", ""))
                    )
            conn.commit()
    else:
        existing = load_docs()
        existing = docs + existing
        _save_docs_json(existing)
