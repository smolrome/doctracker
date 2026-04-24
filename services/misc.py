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
        import tempfile
        path = "activity_log.json"
        logs = []
        if os.path.exists(path):
            try:
                with open(path) as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        logs.append({
            "username": username, "action": action, "ip": ip,
            "detail": detail, "ts": datetime.now().isoformat(),
        })
        logs = logs[-2000:]  # keep last 2000 in JSON fallback
        data = json.dumps(logs, indent=2)
        dir_ = os.path.dirname(os.path.abspath(path)) or '.'
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(data)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


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
    """Delete an office from saved_offices and clear office assignment from all users."""
    # First get the office name before deleting
    office_name = ""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT office_name FROM saved_offices WHERE office_slug=%s", (office_slug,))
                    row = cur.fetchone()
                    if row:
                        office_name = row['office_name']
        except Exception as e:
            print(f"[services.misc] delete_saved_office DB error for slug={office_slug}: {e}")
    else:
        path = "saved_offices.json"
        if os.path.exists(path):
            with open(path) as f:
                offices = json.load(f)
            if office_slug in offices:
                office_name = offices[office_slug].get('office_name', '')
    
    # Delete the office from saved_offices
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM saved_offices WHERE office_slug=%s", (office_slug,))
                    # Also clear office field from users assigned to this office
                    if office_name:
                        cur.execute("UPDATE users SET office='' WHERE office=%s", (office_name,))
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
        
        # Also clear office field from users in JSON
        if office_name:
            users_path = "users.json"
            if os.path.exists(users_path):
                with open(users_path) as f:
                    users = json.load(f)
                for user in users:
                    if user.get('office', '') == office_name:
                        user['office'] = ''
                with open(users_path, "w") as f:
                    json.dump(users, f, indent=2)


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


def get_existing_offices_without_qr() -> list[dict]:
    """
    Get all unique offices from users that don't have QR codes yet.
    These are offices that have staff assigned but no saved_offices entry.
    Returns list of dicts with 'office_slug' and 'office_name'.
    """
    from services.database import USE_DB, get_conn
    
    # First get all saved office slugs (those that already have QR codes)
    saved_slugs = set()
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT office_slug FROM saved_offices")
                    for row in cur.fetchall():
                        saved_slugs.add(row['office_slug'])
        except Exception as e:
            print(f"[services.misc] get_existing_offices_without_qr DB error: {e}")
    else:
        import os
        path = "saved_offices.json"
        if os.path.exists(path):
            with open(path) as f:
                offices = json.load(f)
                saved_slugs = set(offices.keys())
    
    # Now get unique offices from users that aren't in saved_slugs
    result = []
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Get distinct offices from users
                    cur.execute(
                        """SELECT DISTINCT office FROM users 
                           WHERE office IS NOT NULL AND office != '' 
                           ORDER BY office"""
                    )
                    for row in cur.fetchall():
                        office = row['office'].strip()
                        if office:
                            slug = re.sub(r'\s+', '-', office.lower())
                            if slug not in saved_slugs:
                                result.append({
                                    'office_slug': slug,
                                    'office_name': office
                                })
        except Exception as e:
            print(f"[services.misc] get_existing_offices_without_qr DB error: {e}")
    else:
        # JSON fallback - read users
        import os
        path = "users.json"
        if os.path.exists(path):
            with open(path) as f:
                users = json.load(f)
            offices = set()
            for user in users:
                office = user.get('office', '').strip()
                if office:
                    offices.add(office)
            for office in sorted(offices):
                slug = re.sub(r'\s+', '-', office.lower())
                if slug not in saved_slugs:
                    result.append({
                        'office_slug': slug,
                        'office_name': office
                    })
    
    return result


# ═══════════════════════════════════════════════════════════════════
#  ROUTING SLIPS
# ═══════════════════════════════════════════════════════════════════

def generate_slip_no() -> str:
    # 8 hex chars → ~4.3 billion combinations per year; collision probability
    # is negligible even under concurrent load.
    yr     = datetime.now().year
    suffix = uuid.uuid4().hex[:8].upper()
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
            # DB insert failed — fall back to JSON
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
                    r["created_at"] = str(r["created_at"]) if r.get("created_at") else now_str()
                    return r
        except Exception as e:
            return None
    path = "routing_slips.json"
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f).get(slip_id)


def get_all_routing_slips(filter_type=None) -> list[dict]:
    """Return all routing slips, newest first.
    
    Args:
        filter_type: 'active' for non-archived, 'archived' for archived, None for all
    """
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    if filter_type == 'active':
                        cur.execute("SELECT * FROM routing_slips WHERE status != 'Archived' ORDER BY created_at DESC")
                    elif filter_type == 'archived':
                        cur.execute("SELECT * FROM routing_slips WHERE status = 'Archived' ORDER BY created_at DESC")
                    else:
                        cur.execute("SELECT * FROM routing_slips ORDER BY created_at DESC")
                    rows = cur.fetchall()
                    slips = []
                    for row in rows:
                        r = dict(row)
                        if isinstance(r.get("doc_ids"), str):
                            r["doc_ids"] = json.loads(r["doc_ids"])
                        r["created_at"] = str(r["created_at"]) if r.get("created_at") else ""
                        slips.append(r)
                    return slips
        except Exception:
            return []
    else:
        return get_all_routing_slips_json(filter_type)

def get_all_routing_slips_json(filter_type=None) -> list[dict]:
    """Get all routing slips from JSON file (fallback).
    
    Args:
        filter_type: 'active' for non-archived, 'archived' for archived, None for all
    """
    import os
    path = "routing_slips.json"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    slips = list(data.values())
    
    # Filter by type
    if filter_type == 'active':
        slips = [s for s in slips if s.get('status') != 'Archived']
    elif filter_type == 'archived':
        slips = [s for s in slips if s.get('status') == 'Archived']
    
    slips.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return slips


def delete_routing_slip(slip_id: str) -> bool:
    """Delete a routing slip by ID. Returns True if successful."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM routing_slips WHERE id = %s", (slip_id,))
                    conn.commit()
                    return True
        except Exception as e:
            return False
    else:
        # JSON fallback
        return delete_routing_slip_json(slip_id)


def delete_routing_slip_json(slip_id: str) -> bool:
    """Delete a routing slip from JSON file (fallback)."""
    import os
    path = "routing_slips.json"
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            data = json.load(f)
        if slip_id in data:
            del data[slip_id]
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        return False
    except Exception:
        return False
