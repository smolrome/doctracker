"""
services/audit.py — Activity log.
services/offices.py — Saved offices and office traffic.
services/routing.py — Routing slips.

All three are small enough to live in one file grouped by section.
"""
import json
import os
import re
import uuid
from datetime import datetime

from services.database import USE_DB, get_conn
from services.documents import now_str


# ═══════════════════════════════════════════════════════════════════
#  AUDIT LOG
# ═══════════════════════════════════════════════════════════════════

def audit_log(action: str, detail: str = "", username: str = "anonymous",
              ip: str = "unknown"):
    """Record an event in the activity_log table."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO activity_log (username, action, ip_address, detail)
                           VALUES (%s,%s,%s,%s)""",
                        (username, action, ip, (detail[:1000] if detail else ""))
                    )
                conn.commit()
        except Exception as e:
            print(f"[services.misc] audit_log DB error for action={action}: {e}")
    else:
        path = "activity_log.json"
        logs = []
        if os.path.exists(path):
            with open(path) as f:
                logs = json.load(f)
        logs.append({
            "username": username, "action": action, "ip": ip,
            "detail": detail, "ts": datetime.now().isoformat(),
        })
        logs = logs[-2000:]  # keep last 2000 in JSON fallback
        with open(path, "w") as f:
            json.dump(logs, f, indent=2)


def get_activity_logs(limit: int = 200) -> list[dict]:
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT username, action, ip_address, detail, ts
                           FROM activity_log ORDER BY ts DESC LIMIT %s""",
                        (limit,)
                    )
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[services.misc] get_activity_logs DB error: {e}")
            return []
    path = "activity_log.json"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(reversed(json.load(f)))[:limit]


# ═══════════════════════════════════════════════════════════════════
#  OFFICES
# ═══════════════════════════════════════════════════════════════════

def save_office(office_name: str, created_by: str, primary_recipient: str = "") -> str:
    """Persist an office name so it shows on any device. Returns reg_code."""
    slug     = re.sub(r'\s+', '-', office_name.strip().lower())
    reg_code = _make_office_reg_code(slug)
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO saved_offices (office_slug, office_name, created_by, primary_recipient)
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT (office_slug)
                           DO UPDATE SET office_name=EXCLUDED.office_name, primary_recipient=EXCLUDED.primary_recipient""",
                        (slug, office_name.strip(), created_by, primary_recipient)
                    )
                conn.commit()
        except Exception as e:
            print(f"[services.misc] save_office DB error for office={office_name}: {e}")
    else:
        path    = "saved_offices.json"
        offices = {}
        if os.path.exists(path):
            with open(path) as f:
                offices = json.load(f)
        offices[slug] = {"office_name": office_name.strip(), "created_by": created_by, "primary_recipient": primary_recipient}
        with open(path, "w") as f:
            json.dump(offices, f, indent=2)
    return reg_code


def load_saved_offices() -> list[dict]:
    """Load all saved offices, newest first."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT office_name, office_slug, created_by, created_at, primary_recipient
                           FROM saved_offices ORDER BY created_at DESC"""
                    )
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            print(f"[services.misc] load_saved_offices DB error: {e}")
            return []
    path = "saved_offices.json"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        offices = json.load(f)
    return [
        {"office_name": v["office_name"], "office_slug": k, "created_by": v.get("created_by", ""), "primary_recipient": v.get("primary_recipient", "")}
        for k, v in offices.items()
    ]


def delete_saved_office(office_slug: str):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM saved_offices WHERE office_slug=%s", (office_slug,))
                conn.commit()
        except Exception as e:
            print(f"[services.misc] delete_saved_office DB error for slug={office_slug}: {e}")
    else:
        path = "saved_offices.json"
        if os.path.exists(path):
            with open(path) as f:
                offices = json.load(f)
            offices.pop(office_slug, None)
            with open(path, "w") as f:
                json.dump(offices, f, indent=2)


def update_office_primary_recipient(office_slug: str, primary_recipient: str):
    """Update the primary recipient for an office."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE saved_offices SET primary_recipient=%s WHERE office_slug=%s",
                        (primary_recipient, office_slug)
                    )
                conn.commit()
        except Exception as e:
            print(f"[services.misc] update_office_primary_recipient DB error for slug={office_slug}: {e}")
    else:
        path = "saved_offices.json"
        if os.path.exists(path):
            with open(path) as f:
                offices = json.load(f)
            if office_slug in offices:
                offices[office_slug]["primary_recipient"] = primary_recipient
                with open(path, "w") as f:
                    json.dump(offices, f, indent=2)


def log_office_traffic(office_slug: str, office_name: str,
                        event_type: str, doc_id: str, client_username: str):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO office_traffic
                               (office_slug, office_name, event_type, doc_id, client_username)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (office_slug, office_name, event_type, doc_id, client_username)
                    )
                conn.commit()
        except Exception as e:
            print(f"[services.misc] log_office_traffic DB error for office={office_slug}: {e}")
    else:
        path = "office_traffic.json"
        logs = []
        if os.path.exists(path):
            with open(path) as f:
                logs = json.load(f)
        logs.append({
            "office_slug": office_slug, "office_name": office_name,
            "event_type": event_type, "doc_id": doc_id,
            "client_username": client_username, "scanned_at": now_str(),
        })
        with open(path, "w") as f:
            json.dump(logs, f)


def get_office_traffic_today(office_slug: str) -> dict:
    """Returns {received: int, released: int} counts for today."""
    today = datetime.now().strftime("%Y-%m-%d")
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT event_type, COUNT(*) AS cnt FROM office_traffic
                           WHERE office_slug=%s AND DATE(scanned_at)=DATE(NOW())
                           GROUP BY event_type""",
                        (office_slug,)
                    )
                    result = {"received": 0, "released": 0}
                    for r in cur.fetchall():
                        if r["event_type"] == "RECEIVE":
                            result["received"] = r["cnt"]
                        elif r["event_type"] == "RELEASE":
                            result["released"] = r["cnt"]
                    return result
        except Exception as e:
            print(f"[services.misc] get_office_traffic_today DB error for office={office_slug}: {e}")
            return {"received": 0, "released": 0}
    path = "office_traffic.json"
    if not os.path.exists(path):
        return {"received": 0, "released": 0}
    with open(path) as f:
        logs = json.load(f)
    return {
        "received": sum(1 for l in logs if l["office_slug"] == office_slug
                        and l["event_type"] == "RECEIVE"
                        and l.get("scanned_at", "")[:10] == today),
        "released": sum(1 for l in logs if l["office_slug"] == office_slug
                        and l["event_type"] == "RELEASE"
                        and l.get("scanned_at", "")[:10] == today),
    }


def _make_office_reg_code(office_slug: str) -> str:
    import hashlib, hmac as _hmac
    from config import QR_SIGN_SECRET
    raw = _hmac.new(QR_SIGN_SECRET.encode(),
                    f"reg:{office_slug}".encode(),
                    hashlib.sha256).hexdigest()[:12]
    return f"reg-{raw}"


# ═══════════════════════════════════════════════════════════════════
#  ROUTING SLIPS
# ═══════════════════════════════════════════════════════════════════

def generate_slip_no() -> str:
    yr     = datetime.now().year
    suffix = uuid.uuid4().hex[:4].upper()
    return f"SLIP-{yr}-{suffix}"


def save_routing_slip(slip: dict):
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO routing_slips
                               (id, slip_no, destination, prepared_by,
                                doc_ids, notes, slip_date, time_from, time_to,
                                recv_token, rel_token, from_office, type, logged_at, status,
                                is_rerouted, archived_at, archived_by, rerouted_to,
                                original_slip_id, original_slip_no, rerouted_from)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (id) DO UPDATE SET
                               destination = EXCLUDED.destination,
                               doc_ids     = EXCLUDED.doc_ids,
                               notes       = EXCLUDED.notes,
                               slip_date   = EXCLUDED.slip_date,
                               time_from   = EXCLUDED.time_from,
                               time_to     = EXCLUDED.time_to,
                               recv_token  = EXCLUDED.recv_token,
                               rel_token   = EXCLUDED.rel_token,
                               from_office = EXCLUDED.from_office,
                               type        = EXCLUDED.type,
                               logged_at   = EXCLUDED.logged_at,
                               status      = EXCLUDED.status,
                               is_rerouted = EXCLUDED.is_rerouted,
                               archived_at = EXCLUDED.archived_at,
                               archived_by = EXCLUDED.archived_by,
                               rerouted_to = EXCLUDED.rerouted_to,
                               original_slip_id = EXCLUDED.original_slip_id,
                               original_slip_no = EXCLUDED.original_slip_no,
                               rerouted_from = EXCLUDED.rerouted_from""",
                        (
                            slip["id"], slip["slip_no"], slip["destination"],
                            slip["prepared_by"], json.dumps(slip["doc_ids"]),
                            slip.get("notes", ""), slip.get("slip_date", ""),
                            slip.get("time_from", ""), slip.get("time_to", ""),
                            slip.get("recv_token", ""), slip.get("rel_token", ""),
                            slip.get("from_office", ""),
                            slip.get("type", "routing"),
                            slip.get("logged_at", ""),
                            slip.get("status", "Routed"),
                            slip.get("is_rerouted", False),
                            slip.get("archived_at", ""),
                            slip.get("archived_by", ""),
                            slip.get("rerouted_to", ""),
                            slip.get("original_slip_id", ""),
                            slip.get("original_slip_no", ""),
                            slip.get("rerouted_from", ""),
                        )
                    )
                conn.commit()
                return True
        except Exception as e:
            pass
            # Fallback to JSON
            return save_routing_slip_json(slip)
    else:
        return save_routing_slip_json(slip)

def save_routing_slip_json(slip: dict):
    """Save routing slip to JSON file (fallback)."""
    import os
    path  = "routing_slips.json"
    slips = {}
    if os.path.exists(path):
        with open(path) as f:
            slips = json.load(f)
    slips[slip["id"]] = slip
    with open(path, "w") as f:
        json.dump(slips, f)
    return True


def get_routing_slip(slip_id: str) -> dict | None:
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM routing_slips WHERE id=%s", (slip_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    r = dict(row)
                    if isinstance(r["doc_ids"], str):
                        r["doc_ids"] = json.loads(r["doc_ids"])
                    r["created_at"] = str(r["created_at"])[:19] if r.get("created_at") else now_str()
                    return r
        except Exception as e:
            return None
    path = "routing_slips.json"
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f).get(slip_id)


def get_all_routing_slips() -> list[dict]:
    """Return all routing slips, newest first."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM routing_slips ORDER BY created_at DESC")
                    rows = cur.fetchall()
                    slips = []
                    for row in rows:
                        r = dict(row)
                        if isinstance(r.get("doc_ids"), str):
                            r["doc_ids"] = json.loads(r["doc_ids"])
                        r["created_at"] = str(r["created_at"])[:19] if r.get("created_at") else ""
                        slips.append(r)
                    return slips
        except Exception as e:
            pass
            # Fallback to JSON
            return get_all_routing_slips_json()
    else:
        return get_all_routing_slips_json()

def get_all_routing_slips_json() -> list[dict]:
    """Get all routing slips from JSON file (fallback)."""
    import os
    path = "routing_slips.json"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    slips = list(data.values())
    slips.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return slips
