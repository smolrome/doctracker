import json
import os
import uuid
from datetime import datetime

from services.database import USE_DB, get_conn

_APT_FILE = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'appointments.json'))


def now_str():
    return datetime.now().isoformat()


def generate_appointment_id():
    return 'APT-' + uuid.uuid4().hex[:8].upper()


def _load_json():
    if os.path.exists(_APT_FILE):
        with open(_APT_FILE, 'r') as f:
            return json.load(f)
    return []


def _save_json(data):
    with open(_APT_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def _row_to_dict(row) -> dict:
    return dict(row)


def create_appointment(data: dict) -> dict:
    apt = {
        'id':              generate_appointment_id(),
        'client_name':     data.get('client_name', ''),
        'client_username': data.get('client_username', ''),
        'office':          data.get('office', ''),
        'service_code':    data.get('service_code', ''),
        'service_name':    data.get('service_name', ''),
        'preferred_date':  data.get('preferred_date', ''),
        'preferred_time':  data.get('preferred_time', ''),
        'purpose':         data.get('purpose', ''),
        'status':          'pending',
        'queue_ticket':    None,
        'queue_ticket_id': None,
        'source':          data.get('source', 'web'),
        'notes':           data.get('notes', ''),
        'assigned_to':      data.get('assigned_to', ''),
        'assigned_to_name': data.get('assigned_to_name', ''),
        'created_at':      now_str(),
        'updated_at':      now_str(),
    }
    if USE_DB:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO appointments
                    (id, client_name, client_username, office, service_code, service_name,
                     preferred_date, preferred_time, purpose, status, queue_ticket,
                     queue_ticket_id, source, notes, assigned_to, assigned_to_name,
                     created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    apt['id'], apt['client_name'], apt['client_username'],
                    apt['office'], apt['service_code'], apt['service_name'],
                    apt['preferred_date'], apt['preferred_time'], apt['purpose'],
                    apt['status'], apt['queue_ticket'], apt['queue_ticket_id'],
                    apt['source'], apt['notes'], apt['assigned_to'], apt['assigned_to_name'],
                    apt['created_at'], apt['updated_at'],
                ))
    else:
        apts = _load_json()
        apts.append(apt)
        _save_json(apts)
    return apt


def get_appointment(apt_id: str) -> dict | None:
    if USE_DB:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM appointments WHERE id=%s", (apt_id,))
                row = cur.fetchone()
                return _row_to_dict(row) if row else None
    else:
        return next((a for a in _load_json() if a.get('id') == apt_id), None)


def get_appointments_by_client(username: str) -> list:
    if USE_DB:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM appointments WHERE client_username=%s"
                    " ORDER BY preferred_date, preferred_time",
                    (username,)
                )
                return [_row_to_dict(r) for r in cur.fetchall()]
    else:
        return [a for a in _load_json() if a.get('client_username') == username]


def get_all_appointments(date: str = None, office: str = None, status: str = None) -> list:
    if USE_DB:
        with get_conn() as conn:
            with conn.cursor() as cur:
                query = "SELECT * FROM appointments WHERE 1=1"
                params = []
                if date:
                    query += " AND preferred_date=%s"
                    params.append(date)
                if office:
                    query += " AND office=%s"
                    params.append(office)
                if status:
                    query += " AND status=%s"
                    params.append(status)
                query += " ORDER BY preferred_date, preferred_time"
                cur.execute(query, params)
                return [_row_to_dict(r) for r in cur.fetchall()]
    else:
        apts = _load_json()
        if date:
            apts = [a for a in apts if a.get('preferred_date') == date]
        if office:
            apts = [a for a in apts if a.get('office') == office]
        if status:
            apts = [a for a in apts if a.get('status') == status]
        return sorted(apts, key=lambda x: (x.get('preferred_date', ''), x.get('preferred_time', '')))


def update_appointment(apt_id: str, updates: dict) -> dict | None:
    updates['updated_at'] = now_str()
    if USE_DB:
        with get_conn() as conn:
            with conn.cursor() as cur:
                set_clause = ', '.join(f"{k}=%s" for k in updates)
                params = list(updates.values()) + [apt_id]
                cur.execute(f"UPDATE appointments SET {set_clause} WHERE id=%s", params)
                cur.execute("SELECT * FROM appointments WHERE id=%s", (apt_id,))
                row = cur.fetchone()
                return _row_to_dict(row) if row else None
    else:
        apts = _load_json()
        for i, apt in enumerate(apts):
            if apt.get('id') == apt_id:
                apts[i].update(updates)
                _save_json(apts)
                return apts[i]
        return None


def cancel_appointment(apt_id: str) -> bool:
    return update_appointment(apt_id, {'status': 'cancelled'}) is not None
