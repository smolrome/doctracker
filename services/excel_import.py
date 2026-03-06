"""
services/excel_import.py — Import documents from an Excel spreadsheet.

Supports the DepEd Leyte Division tracking sheet format:
  INITIAL DATE | TIME | RECEIVED BY | UNIT/OFFICE/SCHOOL/DISTRICT |
  SOURCE|SENDER | CONTENT PARTICULARS | REFERRED TO | FORWARDED TO |
  DATE & RELEASE TIME | ROUTED TO | USER EMAIL | RECEIVED BY/REMARKS

Also accepts looser column names (case-insensitive, stripped) so slight
variations in the sheet header don't break the import.
"""

import re
import uuid
from datetime import datetime

import pandas as pd

from services.documents import insert_doc, get_doc, now_str, generate_ref

# ── Column aliases ────────────────────────────────────────────────────────────
# Maps normalised column name -> DocTracker field
COLUMN_MAP = {
    # Date received
    "initial date":        "date_received",
    "date received":       "date_received",
    "date":                "date_received",
    # Time
    "time":                "time_received",
    "time received":       "time_received",
    # Received by
    "received by":         "received_by",
    "received by/remarks": "received_by",   # fallback if remarks col absent
    # Office / unit
    "unit/office/school/district": "sender_org",
    "unit/office/school":          "sender_org",
    "office":                      "sender_org",
    "unit":                        "sender_org",
    "school":                      "sender_org",
    # Sender
    "source|sender":       "sender_name",
    "source/sender":       "sender_name",
    "sender":              "sender_name",
    "source":              "sender_name",
    # Document content / title
    "content particulars": "doc_name",
    "content":             "doc_name",
    "particulars":         "doc_name",
    "document":            "doc_name",
    "subject":             "doc_name",
    # Referred to
    "referred to":         "referred_to",
    # Forwarded to
    "forwarded to":        "forwarded_to",
    # Release date
    "date & release time": "date_released",
    "date released":       "date_released",
    "release date":        "date_released",
    # Routed to
    "routed to":           "routed_to",
    # Email
    "user email":          "user_email",
    "email":               "user_email",
    # Notes / remarks
    "received by/remarks": "notes",
    "remarks":             "notes",
    "notes":               "notes",
}


def _norm(col: str) -> str:
    """Lowercase, strip whitespace."""
    return str(col).strip().lower()


def _str(val) -> str:
    """Safe stringify — blank for NaN/None."""
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
    """
    Parse an Excel file and return (rows_as_dicts, warnings).
    Does NOT insert into DB — caller decides what to do with rows.
    """
    import io
    warnings = []

    try:
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception as e:
        return [], [f"Could not open file: {e}"]

    # Pick first sheet
    sheet = xl.sheet_names[0]
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=None)

    if df.empty:
        return [], ["The spreadsheet appears to be empty."]

    # Find header row — first row that contains at least 3 non-null string cells
    header_row = 0
    for i, row in df.iterrows():
        non_null = [c for c in row if isinstance(c, str) and c.strip()]
        if len(non_null) >= 3:
            header_row = i
            break

    headers = [_norm(c) for c in df.iloc[header_row]]
    data_rows = df.iloc[header_row + 1 :].reset_index(drop=True)

    # Map headers -> fields
    col_index = {}   # field_name -> column position
    for i, h in enumerate(headers):
        field = COLUMN_MAP.get(h)
        if field and field not in col_index:
            col_index[field] = i

    if "doc_name" not in col_index:
        warnings.append(
            "Could not find a 'Content Particulars' or document title column. "
            "Rows will be imported with a blank title."
        )

    parsed = []
    for _, row in data_rows.iterrows():
        row = list(row)

        def get(field):
            idx = col_index.get(field)
            return _str(row[idx]) if idx is not None and idx < len(row) else ""

        doc_name = get("doc_name")
        sender   = get("sender_name")
        org      = get("sender_org")

        # Skip entirely blank rows
        if not any([doc_name, sender, org]):
            continue

        parsed.append({
            "doc_name":    doc_name or "(No title)",
            "sender_name": sender,
            "sender_org":  org,
            "received_by": get("received_by"),
            "referred_to": get("referred_to"),
            "forwarded_to":get("forwarded_to"),
            "routed_to":   get("routed_to"),
            "date_received":get("date_received"),
            "time_received":get("time_received"),
            "date_released":get("date_released"),
            "user_email":  get("user_email"),
            "notes":       get("notes"),
        })

    if not parsed:
        warnings.append("No data rows were found after the header row.")

    return parsed, warnings


def import_excel(file_bytes: bytes, filename: str,
                 imported_by: str, default_status: str = "Received",
                 skip_duplicates: bool = True) -> dict:
    """
    Parse and insert documents from Excel into DocTracker.
    Returns a summary dict.
    """
    rows, warnings = parse_excel(file_bytes, filename)

    summary = {
        "total":      len(rows),
        "imported":   0,
        "skipped":    0,
        "errors":     [],
        "warnings":   warnings,
        "docs":       [],
    }

    for row in rows:
        try:
            doc_id = generate_ref()
            uid    = str(uuid.uuid4())[:8].upper()
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

            insert_doc(doc)
            summary["imported"] += 1
            summary["docs"].append({
                "doc_id":   doc_id,
                "doc_name": row["doc_name"][:60],
            })

        except Exception as e:
            summary["errors"].append(f"{row.get('doc_name','?')[:40]}: {e}")

    return summary
