"""
services/excel_import.py — Import documents from an Excel spreadsheet.

Supports the DepEd Leyte Division tracking sheet format:
  INITIAL DATE | TIME | RECEIVED BY | UNIT/OFFICE/SCHOOL/DISTRICT |
  SOURCE|SENDER | CONTENT PARTICULARS | REFERRED TO | FORWARDED TO |
  DATE & RELEASE TIME | ROUTED TO | USER EMAIL | RECEIVED BY/REMARKS
"""

import json
import uuid
from datetime import datetime, timedelta

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


# Word-order-insensitive fallback: {token frozenset -> field}
_TOKEN_MAP: dict = {}
for _k, _v in COLUMN_MAP.items():
    _TOKEN_MAP.setdefault(frozenset(_k.split()), _v)


def _norm(col: str) -> str:
    # case-insensitive, trimmed, and internal whitespace collapsed
    return " ".join(str(col).strip().lower().split())


def _lookup_field(header: str):
    """Map a header to a field. Tries exact (normalized) match first, then a
    word-order-insensitive token-set match so 'RECEIVED DATE' == 'DATE RECEIVED'."""
    h = _norm(header)
    return COLUMN_MAP.get(h) or _TOKEN_MAP.get(frozenset(h.split()))


def _parse_date(val, warnings=None, label="date") -> str:
    """Normalize a cell to ISO 'YYYY-MM-DD'. Accepts real Excel dates
    (datetime/Timestamp), text dates like '5/26/2026', and Excel date serials.
    Blanks -> ''. Unparseable values are kept verbatim and logged to `warnings`."""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = _str(val)
    if not s:
        return ""
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:  # Excel date serial stored as a number/text (epoch 1899-12-30)
        return (datetime(1899, 12, 30) + timedelta(days=float(s))).strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        pass
    if warnings is not None:
        warnings.append(f"Could not parse {label} value '{s}' — kept as-is.")
    return s


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
        field = _lookup_field(h)
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

        def get_date(field):
            idx = col_index.get(field)
            raw = row[idx] if idx is not None and idx < len(row) else None
            return _parse_date(raw, warnings, label=field)

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
            "date_received":get_date("date_received"),
            "time_received":get("time_received"),
            "date_released":get_date("date_released"),
            "user_email":   get("user_email"),
            "notes":        get("notes"),
        })

    if not parsed:
        warnings.append("No data rows found after the header row.")

    return parsed, warnings


def import_excel(file_bytes: bytes, filename: str,
                 imported_by: str, default_status: str = "",
                 default_office: str = "", default_staff_username: str = "",
                 default_staff_name: str = "",
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
            if default_status:
                auto_status = default_status
            else:
                remarks = row["notes"].strip()
                if remarks and "released" in remarks.lower():
                    auto_status = "Released"
                elif not remarks:
                    auto_status = "Logged"
                else:
                    auto_status = "Received"

            doc = {
                "id":           uid,
                "doc_id":       doc_id,
                "doc_name":     row["doc_name"],
                "category":     "Special Order",
                "status":       auto_status,
                "sender_name":  row["sender_name"],
                "sender_org":   default_office or row["sender_org"],
                "received_by":  default_staff_name or row["received_by"],
                "logged_by":    default_staff_username or "",
                "original_logged_by": default_staff_username or "",
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
            _batch_insert(docs_to_insert, session_id=imported_by)
            summary["imported"] = len(docs_to_insert)
        except Exception as e:
            summary["errors"].append(f"Batch insert failed: {e}")
            summary["imported"] = 0
            summary["docs"] = []

    return summary


def _batch_insert(docs: list[dict], session_id: str = ""):
    """Insert all docs in one DB transaction to avoid timeout."""
    from services.database import USE_DB, get_conn
    from services.documents import _save_docs_json, load_docs

    total = len(docs)

    def _emit(i, msg=""):
        if session_id:
            try:
                from routes.progress import update_progress
                pct = int(10 + (i / total) * 85) if total else 95
                update_progress(session_id, pct, msg)
            except Exception:
                pass

    _emit(0, f"Inserting {total} documents...")

    if USE_DB:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for i, doc in enumerate(docs):
                    cur.execute(
                        "INSERT INTO documents (id, data, created_at) "
                        "VALUES (%s, %s::jsonb, %s) ON CONFLICT (id) DO NOTHING",
                        (doc["id"], json.dumps(doc), doc.get("created_at", ""))
                    )
                    if i % 10 == 0:
                        _emit(i + 1, f"Saved {i + 1} of {total}...")
            conn.commit()
    else:
        existing = load_docs()
        existing = docs + existing
        _save_docs_json(existing)

    _emit(total, "Done!")
    if session_id:
        try:
            from routes.progress import update_progress
            update_progress(session_id, 100, "Import complete!", done=True)
        except Exception:
            pass
