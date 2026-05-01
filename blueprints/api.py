"""
blueprints/api.py — REST API for mobile app.
Provides JWT-based authentication and document operations.
"""

import os
import secrets
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity
)
from services.auth import verify_password, check_rate_limit, reset_rate_limit, verify_user, update_last_login
from services.database import USE_DB, get_conn
from services.documents import (
    load_docs,
    get_doc,
    insert_doc,
    save_doc,
    delete_doc,
    get_stats,
    generate_ref,
    now_str,
)
from services.qr import use_doc_token
import base64
import uuid
import qrcode
from io import BytesIO

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.before_request
def api_rate_limit():
    """Apply per-IP rate limiting to all API endpoints."""
    from flask import request as _req
    from utils import get_client_ip
    identifier = get_client_ip()
    allowed, wait = check_rate_limit('api', identifier)
    if not allowed:
        return jsonify(error=f'Rate limit exceeded. Try again in {wait} seconds.'), 429


def serialize(obj):
    """Ensure JSON-serializable output for API responses."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize(i) for i in obj]
    return obj


def get_user_by_username(username: str, include_password: bool = False):
    """Fetch user by username. Set include_password=True only for auth checks."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    fields = "id, username, password_hash, full_name, role, COALESCE(office, '') AS office, active, approved"
                    cur.execute(
                        f"SELECT {fields} FROM users WHERE username = %s",
                        (username.lower().strip(),),
                    )
                    row = cur.fetchone()
                    return dict(row) if row else None
        except Exception:
            return None
    else:
        import json
        import os
        if not os.path.exists("users.json"):
            return None
        with open("users.json") as f:
            users = json.load(f)
        for u in users:
            if u["username"] == username.lower().strip():
                return u
        return None


def _is_admin_user(username: str) -> bool:
    """Return True if the username is the env-var admin OR has role='admin' in the DB."""
    admin_env = os.environ.get('ADMIN_USERNAME', '')
    if admin_env and secrets.compare_digest(username.lower(), admin_env.lower()):
        return True
    user = get_user_by_username(username)
    return bool(user and user.get('role') in ('admin', 'superadmin'))


@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    import os, secrets
    data = request.get_json(force=True, silent=True)

    if not data:
        return jsonify(error='Invalid JSON body'), 400

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify(error='Username and password required'), 400

    from services.auth import check_rate_limit, reset_rate_limit, verify_user, update_last_login
    allowed, wait = check_rate_limit('login', username)
    if not allowed:
        return jsonify(error=f'Too many attempts. Wait {wait} seconds.'), 429

    admin_username = os.environ.get('ADMIN_USERNAME', '')
    admin_password = os.environ.get('ADMIN_PASSWORD', '')

    if (admin_username and admin_password and
            secrets.compare_digest(username.lower(), admin_username.lower()) and
            secrets.compare_digest(password, admin_password)):
        reset_rate_limit('login', username)
        access_token = create_access_token(identity=username)
        refresh_token = create_refresh_token(identity=username)
        return jsonify(
            access_token=access_token,
            refresh_token=refresh_token,
            user=dict(
                username=username,
                full_name='Administrator',
                role='admin',
                office='IT Unit'
            )
        )

    full_name, role, office = verify_user(username, password)

    if role is None:
        return jsonify(error='Invalid username or password'), 401

    reset_rate_limit('login', username)
    update_last_login(username)

    access_token = create_access_token(identity=username)
    refresh_token = create_refresh_token(identity=username)

    return jsonify(
        access_token=access_token,
        refresh_token=refresh_token,
        user=dict(
            username=username,
            full_name=full_name,
            role=role,
            office=office
        )
    )


@api_bp.route('/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def api_refresh():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    return jsonify(serialize({"access_token": access_token}))


@api_bp.route('/auth/me', methods=['GET'])
@jwt_required()
def api_me():
    username = get_jwt_identity()
    # Check env-var admin first (has no DB row)
    admin_env = os.environ.get('ADMIN_USERNAME', '')
    if admin_env and secrets.compare_digest(username.lower(), admin_env.lower()):
        return jsonify(serialize({
            "username": username,
            "full_name": "Administrator",
            "role": "admin",
            "office": "IT Unit",
        }))
    user = get_user_by_username(username)
    if not user:
        return jsonify(error='User not found'), 404
    return jsonify(serialize({
        "username": user['username'],
        "full_name": user['full_name'],
        "role": user['role'],
        "office": user['office'],
    }))


@api_bp.route('/documents', methods=['GET'])
@jwt_required()
def api_get_documents():
    status = request.args.get('status')
    office = request.args.get('office')
    search = request.args.get('search')
    try:
        page = int(request.args.get('page', 1))
    except (ValueError, TypeError):
        page = 1
    try:
        limit = max(1, min(int(request.args.get('limit', 20)), 200))
    except (ValueError, TypeError):
        limit = 20

    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    user_role = 'admin' if _is_admin_user(user_id) else (user.get('role', '') if user else '')
    user_office = user.get('office', '') if user else ''

    docs = load_docs()

    # Filter documents based on user role
    if user_role not in ['admin', 'superadmin']:
        docs = [d for d in docs if d.get('logged_by') == user_id]

    if status:
        docs = [d for d in docs if d.get('status') == status]
    if office:
        docs = [d for d in docs if d.get('office') == office]
    if search:
        search_lower = search.lower()
        docs = [d for d in docs if
                search_lower in (d.get('doc_name') or '').lower() or
                search_lower in (d.get('doc_id') or '').lower() or
                search_lower in (d.get('sender_org') or '').lower() or
                search_lower in (d.get('from_office') or '').lower()]

    total = len(docs)
    start = (page - 1) * limit
    end = start + limit
    docs_page = docs[start:end]

    return jsonify(serialize({"documents": docs_page, "total": total, "page": page, "limit": limit}))


@api_bp.route('/documents/<doc_id>', methods=['GET'])
@jwt_required()
def api_get_document(doc_id):
    doc = get_doc(doc_id)
    if not doc or doc.get('deleted'):
        return jsonify(error='Document not found'), 404
    return jsonify(serialize(doc))


@api_bp.route('/documents', methods=['POST'])
@jwt_required()
def api_create_document():
    data = request.get_json()
    user_id = get_jwt_identity()

    doc = {
        "id": str(uuid.uuid4()),
        "doc_id": generate_ref(),
        "doc_name": data.get('doc_name', ''),
        "category": data.get('category', ''),
        "from_office": data.get('from_office', ''),
        "sender_org": data.get('sender_org', data.get('from_office', '')),
        "sender_name": data.get('sender_name', ''),
        "referred_to": data.get('referred_to', ''),
        "remarks": data.get('remarks', ''),
        "doc_date": data.get('doc_date', now_str()),
        "status": "Pending",
        "created_at": now_str(),
        "logged_by": user_id,
    }
    insert_doc(doc)
    return jsonify(serialize(doc)), 201


@api_bp.route('/documents/<doc_id>/status', methods=['PATCH'])
@jwt_required()
def api_update_status(doc_id):
    data = request.get_json()
    new_status = data.get('status')
    remarks = data.get('remarks', '')
    user_id = get_jwt_identity()

    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404

    # Only admin/staff or the document owner may update status
    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        user_role = user.get('role', '') if user else ''
        if user_role not in ('admin', 'staff') and doc.get('logged_by') != user_id:
            return jsonify(error='Forbidden'), 403

    user = get_user_by_username(user_id)
    user_full_name = (user.get('full_name') or user_id) if user else user_id
    user_office = (user.get('office') or '') if user else ''

    old_status = doc.get('status')
    doc['status'] = new_status
    if remarks:
        doc['remarks'] = remarks
    doc['updated_at'] = now_str()
    doc['updated_by'] = user_id

    if new_status == 'Received':
        doc['date_received'] = now_str()[:16].replace('T', ' ')
    elif new_status == 'Released':
        doc['date_released'] = now_str()[:16].replace('T', ' ')

    doc.setdefault('travel_log', []).append({
        'office': user_office,
        'action': f'Status → {new_status}',
        'officer': user_full_name,
        'timestamp': now_str(),
        'remarks': remarks or f'Status changed from {old_status} to {new_status}',
    })

    save_doc(doc)

    if doc.get('logged_by') and doc['logged_by'] != user_id:
        send_push_notification(
            username=doc['logged_by'],
            title=f"Document {new_status}",
            body=f"{doc.get('ref', doc_id)} has been {new_status.lower()}",
            data={
                'doc_id': doc_id,
                'screen': f'/(app)/documents/{doc_id}'
            }
        )

    return jsonify(serialize(doc))


@api_bp.route('/documents/<doc_id>', methods=['DELETE'])
@jwt_required()
def api_delete_document(doc_id):
    user_id = get_jwt_identity()
    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404
    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        user_role = user.get('role', '') if user else ''
        if user_role not in ('admin', 'staff') and doc.get('logged_by') != user_id:
            return jsonify(error='Forbidden'), 403
    delete_doc(doc_id, deleted_by=user_id)
    return jsonify(message='Document deleted')


@api_bp.route('/stats', methods=['GET'])
@jwt_required()
def api_stats():
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    user_role = 'admin' if _is_admin_user(user_id) else (user.get('role', '') if user else '')

    docs = load_docs()

    if user_role not in ['admin', 'superadmin']:
        docs = [d for d in docs if d.get('logged_by') == user_id]

    stats = get_stats(docs)
    return jsonify(serialize(stats))


@api_bp.route('/qr/generate/<doc_id>', methods=['GET'])
@jwt_required()
def api_generate_qr(doc_id):
    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404

    import qrcode.constants
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(doc['id'])
    qr.make(fit=True)
    buf = BytesIO()
    img = qr.make_image(fill_color="#0D1B2A", back_color="white")
    img.save(buf)
    buf.seek(0)
    encoded = base64.b64encode(buf.getvalue()).decode('utf-8')

    return jsonify(
        doc_id=doc_id,
        qr_base64=f"data:image/png;base64,{encoded}"
    )


@api_bp.route('/qr/scan', methods=['POST'])
@jwt_required()
def api_scan_qr():
    data = request.get_json()
    token = data.get('token')

    if not token:
        return jsonify(error='No token provided'), 400

    doc_id, token_type = use_doc_token(token)
    if not doc_id:
        return jsonify(error='Invalid or expired QR token'), 401

    doc = get_doc(doc_id)
    return jsonify(serialize({"doc": doc, "token_type": token_type}))


@api_bp.route('/offices', methods=['GET'])
@jwt_required()
def api_get_offices():
    from services.misc import load_saved_offices
    from services.auth import get_all_users
    offices = load_saved_offices()
    # Resolve primary_recipient username → full name for display
    user_map = {u['username']: u.get('full_name') or u['username'] for u in get_all_users()}
    for off in offices:
        pr = off.get('primary_recipient', '')
        off['primary_recipient_name'] = user_map.get(pr, pr) if pr else ''
    return jsonify(serialize(offices))


@api_bp.route('/offices/<office_slug>/staff', methods=['GET'])
@jwt_required()
def api_get_office_staff(office_slug: str):
    """Return staff list for a specific office (used by client submission form).
    Priority: 1) primary_recipient first, 2) staff matching office name,
    3) all staff as fallback. Mirrors web app office_staff_list logic."""
    from services.misc import load_saved_offices
    from services.auth import get_all_users

    # Resolve slug → office record
    office_name = ''
    primary_recipient = ''
    for off in load_saved_offices():
        if off.get('office_slug') == office_slug:
            office_name = off.get('office_name', '')
            primary_recipient = off.get('primary_recipient', '')
            break

    all_users = get_all_users()
    user_map = {u['username']: u for u in all_users}

    # Build staff list: users whose office field matches
    office_name_lower = office_name.strip().lower()
    staff_usernames_ordered = []

    # 1. Primary recipient goes first (if set and exists)
    if primary_recipient and primary_recipient in user_map:
        staff_usernames_ordered.append(primary_recipient)

    # 2. Staff matching by office name
    for u in all_users:
        if u.get('username') == primary_recipient:
            continue  # already added
        if u.get('role') in ('staff', 'admin') and office_name_lower and \
                (u.get('office') or '').strip().lower() == office_name_lower:
            staff_usernames_ordered.append(u['username'])

    # 3. Fallback: all staff when no office match (and primary_recipient not set)
    if len(staff_usernames_ordered) <= (1 if primary_recipient else 0):
        for u in all_users:
            if u.get('username') in staff_usernames_ordered:
                continue
            if u.get('role') in ('staff', 'admin'):
                staff_usernames_ordered.append(u['username'])

    staff = [
        {
            'username': uname,
            'full_name': user_map[uname].get('full_name') or uname,
            'is_primary': uname == primary_recipient,
        }
        for uname in staff_usernames_ordered
        if uname in user_map
    ]
    return jsonify(serialize(staff))


@api_bp.route('/routing-slips', methods=['GET'])
@jwt_required()
def api_get_routing_slips():
    from services.misc import get_all_routing_slips
    slips = get_all_routing_slips()
    return jsonify(serialize(slips))


@api_bp.route('/activity-log', methods=['GET'])
@jwt_required()
def api_activity_log():
    from services.misc import get_activity_logs
    try:
        limit = max(1, min(int(request.args.get('limit', 200)), 1000))
    except (ValueError, TypeError):
        limit = 200
    logs = get_activity_logs(limit=limit)
    return jsonify(serialize(logs))


@api_bp.route('/dropdown-options', methods=['GET'])
@jwt_required()
def api_dropdown_options():
    from services.dropdown_options import get_all_dropdown_configs
    configs = get_all_dropdown_configs()
    # Flatten to {field_name: [options]} so mobile can use directly
    flat = {
        k: (v.get('options', []) if isinstance(v, dict) else v)
        for k, v in configs.items()
    }

    # Inject referred_to from actual user accounts (mirrors web app office_staff logic):
    # admin  → all active non-client users system-wide
    # staff  → only users in the same office, excluding self
    try:
        user_id = get_jwt_identity()
        is_admin = _is_admin_user(user_id)
        current_user = get_user_by_username(user_id)
        current_office = (current_user.get('office') or '').strip().lower() if current_user else ''

        if USE_DB:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    if is_admin:
                        cur.execute("""
                            SELECT full_name, username FROM users
                            WHERE active = TRUE AND approved = TRUE AND role != 'client'
                            ORDER BY full_name
                        """)
                    else:
                        cur.execute("""
                            SELECT full_name, username FROM users
                            WHERE active = TRUE AND approved = TRUE AND role != 'client'
                              AND LOWER(TRIM(office)) = %s AND username != %s
                            ORDER BY full_name
                        """, (current_office, user_id))
                    rows = cur.fetchall()
                    flat['referred_to'] = [
                        r['full_name'] or r['username'] for r in rows
                    ]
        else:
            import json as _json
            if os.path.exists("users.json"):
                with open("users.json") as f:
                    all_users = _json.load(f)
                flat['referred_to'] = sorted([
                    u.get('full_name') or u.get('username')
                    for u in all_users
                    if u.get('active', True)
                    and u.get('role') != 'client'
                    and (
                        is_admin
                        or (
                            u.get('office', '').strip().lower() == current_office
                            and u.get('username') != user_id
                        )
                    )
                ])
    except Exception:
        pass  # keep whatever referred_to was in the static dropdown config

    return jsonify(serialize(flat))


_push_tokens: dict = {}
_push_tokens_loaded = False
_push_tokens_lock = threading.Lock()


def _ensure_push_tokens_loaded():
    """Load push tokens from DB into memory on first call (lazy load)."""
    global _push_tokens_loaded
    with _push_tokens_lock:
        if _push_tokens_loaded or not USE_DB:
            return
        _push_tokens_loaded = True
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT username, token FROM push_tokens")
                    for row in cur.fetchall():
                        _push_tokens[row['username']] = row['token']
        except Exception:
            pass


@api_bp.route('/notifications/register-token', methods=['POST'])
@jwt_required()
def register_push_token():
    data = request.get_json(force=True, silent=True)
    token = data.get('token')
    username = get_jwt_identity()

    if not token:
        return jsonify(error='Token required'), 400

    with _push_tokens_lock:
        _push_tokens[username] = token

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO push_tokens (username, token, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (username)
                        DO UPDATE SET token = EXCLUDED.token,
                                      updated_at = NOW()
                    """, (username, token))
        except Exception:
            pass

    return jsonify(message='Token registered')


@api_bp.route('/pending-count', methods=['GET'])
@jwt_required()
def api_pending_count():
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    user_role = 'admin' if _is_admin_user(user_id) else (user.get('role', '') if user else '')
    user_office = (user.get('office') or '').strip().lower() if user else ''

    docs = load_docs()
    pending = [d for d in docs if d.get('transfer_status') == 'pending']

    if user_role in ('admin', 'superadmin'):
        count = len(pending)
    else:
        count = sum(
            1 for d in pending
            if d.get('pending_at_staff') == user_id
            or (
                user_office
                and d.get('pending_at_office', '').strip().lower() == user_office
                and not d.get('pending_at_staff', '')
            )
        )
    return jsonify({'count': count})


@api_bp.route('/pending-documents', methods=['GET'])
@jwt_required()
def api_pending_documents():
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    user_role = 'admin' if _is_admin_user(user_id) else (user.get('role', '') if user else '')
    user_office = (user.get('office') or '').strip().lower() if user else ''

    docs = load_docs()

    if user_role in ('admin', 'superadmin'):
        result = [d for d in docs if d.get('transfer_status') == 'pending']
    else:
        result = [
            d for d in docs
            if d.get('transfer_status') == 'pending'
            and (
                d.get('pending_at_staff') == user_id
                or (
                    user_office
                    and d.get('pending_at_office', '').strip().lower() == user_office
                    and not d.get('pending_at_staff', '')
                )
            )
        ]
    return jsonify(serialize(result))


@api_bp.route('/documents/<doc_id>/accept', methods=['POST'])
@jwt_required()
def api_accept_document(doc_id):
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    user_office = (user.get('office') or '') if user else ''
    user_full_name = (user.get('full_name') or user_id) if user else user_id

    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404

    pending_staff = doc.get('pending_at_staff', '')
    pending_office = doc.get('pending_at_office', '').strip().lower()
    user_office_lower = user_office.strip().lower()

    is_authorized = (
        _is_admin_user(user_id)
        or pending_staff == user_id
        or (not pending_staff and pending_office and pending_office == user_office_lower)
    )
    if not is_authorized:
        return jsonify(error='Forbidden'), 403

    doc['transfer_status'] = 'accepted'
    doc['status'] = 'Received'
    doc['date_received'] = now_str()[:16].replace('T', ' ')
    doc['accepted_by'] = user_id
    doc['accepted_at'] = now_str()
    doc['routing_cycle'] = doc.get('routing_cycle', 0) + 1

    doc.setdefault('travel_log', []).append({
        'office': user_office or doc.get('pending_at_office', ''),
        'action': 'Document Accepted',
        'officer': user_full_name,
        'timestamp': now_str(),
        'remarks': (
            f'Document received and accepted by {user_full_name}. '
            f'Routing cycle {doc.get("routing_cycle", 1)} in progress.'
        ),
    })

    save_doc(doc)

    if doc.get('logged_by') and doc['logged_by'] != user_id:
        send_push_notification(
            username=doc['logged_by'],
            title='Document Accepted',
            body=f'{doc.get("doc_id", doc_id)} was accepted by {user_full_name}',
            data={'doc_id': doc_id, 'screen': f'/(app)/documents/{doc_id}'},
        )

    return jsonify(serialize(doc))


@api_bp.route('/documents/<doc_id>/reject', methods=['POST'])
@jwt_required()
def api_reject_document(doc_id):
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    user_office = (user.get('office') or '') if user else ''
    user_full_name = (user.get('full_name') or user_id) if user else user_id

    data = request.get_json(force=True, silent=True) or {}
    reason = data.get('reason', '').strip()
    if not reason:
        return jsonify(error='Rejection reason is required'), 400

    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404

    pending_staff = doc.get('pending_at_staff', '')
    pending_office = doc.get('pending_at_office', '').strip().lower()
    user_office_lower = user_office.strip().lower()

    is_authorized = (
        _is_admin_user(user_id)
        or pending_staff == user_id
        or (not pending_staff and pending_office and pending_office == user_office_lower)
    )
    if not is_authorized:
        return jsonify(error='Forbidden'), 403

    original_logger = doc.get('logged_by', '')
    doc['transfer_status'] = 'rejected'
    doc['status'] = 'Returned'
    doc['rejected_by'] = user_id
    doc['rejected_at'] = now_str()
    doc['pending_at_staff'] = ''
    doc['pending_at_office'] = ''

    doc.setdefault('travel_log', []).append({
        'office': user_office or doc.get('pending_at_office', ''),
        'action': 'Document Rejected',
        'officer': user_full_name,
        'timestamp': now_str(),
        'remarks': f'Rejected by {user_full_name}. Reason: {reason}',
    })

    save_doc(doc)

    if original_logger and original_logger != user_id:
        send_push_notification(
            username=original_logger,
            title='Document Rejected',
            body=f'{doc.get("doc_id", doc_id)} was rejected: {reason[:80]}',
            data={'doc_id': doc_id, 'screen': f'/(app)/documents/{doc_id}'},
        )

    return jsonify(serialize(doc))


@api_bp.route('/staff', methods=['GET'])
@jwt_required()
def api_get_staff():
    """Returns staff list scoped by role — mirrors web app office_staff logic:
       admin  → all active non-client users system-wide
       staff  → only users in the same office, excluding self
    """
    user_id = get_jwt_identity()
    is_admin = _is_admin_user(user_id)
    current_user = get_user_by_username(user_id)
    current_office = (current_user.get('office') or '').strip() if current_user else ''

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    if is_admin:
                        cur.execute("""
                            SELECT username, full_name, COALESCE(office, '') AS office, role
                            FROM users
                            WHERE active = TRUE AND approved = TRUE
                              AND role != 'client'
                            ORDER BY full_name
                        """)
                    else:
                        cur.execute("""
                            SELECT username, full_name, COALESCE(office, '') AS office, role
                            FROM users
                            WHERE active = TRUE AND approved = TRUE
                              AND role != 'client'
                              AND LOWER(TRIM(office)) = LOWER(TRIM(%s))
                              AND username != %s
                            ORDER BY full_name
                        """, (current_office, user_id))
                    rows = cur.fetchall()
                    return jsonify(serialize([dict(r) for r in rows]))
        except Exception:
            return jsonify([])
    else:
        import json as _json
        if not os.path.exists("users.json"):
            return jsonify([])
        with open("users.json") as f:
            users = _json.load(f)

        def _keep(u):
            if not u.get('active', True):
                return False
            if u.get('role') == 'client':
                return False
            if is_admin:
                return True
            # same office, not self
            return (
                u.get('office', '').strip().lower() == current_office.lower()
                and u.get('username') != user_id
            )

        result = sorted(
            [
                {
                    'username': u['username'],
                    'full_name': u.get('full_name') or u['username'],
                    'office': u.get('office', ''),
                    'role': u.get('role', 'staff'),
                }
                for u in users if _keep(u)
            ],
            key=lambda x: x['full_name'],
        )
        return jsonify(serialize(result))


@api_bp.route('/documents/<doc_id>/transfer', methods=['POST'])
@jwt_required()
def api_transfer_document(doc_id):
    user_id = get_jwt_identity()

    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        if not user or user.get('role') not in ('admin', 'staff', 'superadmin'):
            return jsonify(error='Only staff and admin can transfer documents'), 403

    data = request.get_json(force=True, silent=True) or {}
    to_staff = data.get('to_staff', '').strip()
    to_office = data.get('to_office', '').strip()
    remarks = data.get('remarks', '').strip()

    if not to_staff and not to_office:
        return jsonify(error='Specify either a staff member or office to transfer to'), 400

    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404

    user = get_user_by_username(user_id)
    user_full_name = (user.get('full_name') or user_id) if user else user_id
    user_office = (user.get('office') or '') if user else ''
    recipient_display = to_staff or to_office

    doc['transfer_status'] = 'pending'
    doc['pending_at_staff'] = to_staff
    doc['pending_at_office'] = to_office
    doc['status'] = 'Routed'
    doc['referred_to'] = recipient_display
    doc['updated_at'] = now_str()
    doc['updated_by'] = user_id

    doc.setdefault('travel_log', []).append({
        'office': user_office,
        'action': f'Transferred to {recipient_display}',
        'officer': user_full_name,
        'timestamp': now_str(),
        'remarks': remarks or f'Document transferred to {recipient_display} by {user_full_name}',
    })

    save_doc(doc)

    if to_staff and to_staff != user_id:
        send_push_notification(
            username=to_staff,
            title='Document Transferred to You',
            body=f'{doc.get("doc_id", doc_id)}: {doc.get("doc_name", "")[:60]}',
            data={'doc_id': doc_id, 'screen': f'/(app)/documents/{doc_id}'},
        )

    return jsonify(serialize(doc))


@api_bp.route('/check-duplicate', methods=['GET'])
@jwt_required()
def api_check_duplicate():
    q = request.args.get('q', '').strip().lower()
    if len(q) < 4:
        return jsonify(duplicates=[])

    docs = load_docs()
    matches = [
        {
            'id': d['id'],
            'doc_id': d.get('doc_id'),
            'doc_name': d.get('doc_name'),
            'status': d.get('status'),
            'from_office': d.get('from_office'),
        }
        for d in docs
        if not d.get('deleted') and q in (d.get('doc_name') or '').lower()
    ][:5]

    return jsonify(duplicates=matches)


@api_bp.route('/staff-stats', methods=['GET'])
@jwt_required()
def api_staff_stats():
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        if not user or user.get('role') not in ('admin', 'superadmin'):
            return jsonify(error='Admin access required'), 403

    docs = load_docs()
    stats: dict = {}
    for d in docs:
        if d.get('deleted'):
            continue
        logger = d.get('logged_by', 'unknown')
        if logger not in stats:
            stats[logger] = {'total': 0, 'pending': 0, 'received': 0, 'released': 0, 'other': 0}
        stats[logger]['total'] += 1
        s = (d.get('status') or '').lower()
        if s == 'pending':
            stats[logger]['pending'] += 1
        elif s == 'received':
            stats[logger]['received'] += 1
        elif s == 'released':
            stats[logger]['released'] += 1
        else:
            stats[logger]['other'] += 1

    result = [{'username': k, **v} for k, v in sorted(stats.items(), key=lambda x: -x[1]['total'])]
    return jsonify(serialize(result))


# ── Profile ───────────────────────────────────────────────────────────────────

@api_bp.route('/profile', methods=['PATCH'])
@jwt_required()
def api_update_profile():
    user_id = get_jwt_identity()
    data = request.get_json(force=True, silent=True) or {}
    full_name = data.get('full_name', '').strip()
    office = data.get('office', '').strip()
    if not full_name:
        return jsonify(error='Display name is required'), 400
    from services.auth import update_user, get_user
    ok, err = update_user(user_id, full_name=full_name, office=office or None)
    if not ok:
        return jsonify(error=err), 400
    updated = get_user(user_id)
    return jsonify(serialize(updated or {'username': user_id, 'full_name': full_name, 'office': office}))


@api_bp.route('/profile/password', methods=['POST'])
@jwt_required()
def api_change_password():
    user_id = get_jwt_identity()
    data = request.get_json(force=True, silent=True) or {}
    current  = data.get('current_password', '').strip()
    new_pass = data.get('new_password', '').strip()
    confirm  = data.get('confirm_password', '').strip()
    if not current or not new_pass or not confirm:
        return jsonify(error='All fields are required'), 400
    if new_pass != confirm:
        return jsonify(error='New passwords do not match'), 400
    if len(new_pass) < 8:
        return jsonify(error='Password must be at least 8 characters'), 400
    # Verify current password using the raw DB record (includes password_hash)
    user_record = get_user_by_username(user_id)
    if not user_record:
        return jsonify(error='User not found'), 404
    from services.auth import verify_password, update_user_password
    if not verify_password(current, user_record.get('password_hash', '')):
        return jsonify(error='Current password is incorrect'), 400
    ok, err = update_user_password(user_id, new_pass)
    if not ok:
        return jsonify(error=err), 400
    return jsonify(message='Password changed successfully')


# ── Admin: User CRUD ──────────────────────────────────────────────────────────

@api_bp.route('/admin/users', methods=['GET'])
@jwt_required()
def api_admin_get_users():
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    from services.auth import get_all_users
    return jsonify(serialize(get_all_users()))


@api_bp.route('/admin/users', methods=['POST'])
@jwt_required()
def api_admin_create_user():
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    data = request.get_json(force=True, silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    full_name = data.get('full_name', '').strip()
    role = data.get('role', 'staff').strip()
    office = data.get('office', '').strip()
    email = data.get('email', '').strip()
    if not username or not password:
        return jsonify(error='Username and password are required'), 400
    if len(password) < 8:
        return jsonify(error='Password must be at least 8 characters'), 400
    from services.auth import create_user
    ok, err = create_user(username, password, full_name=full_name, role=role, office=office, email=email)
    if not ok:
        return jsonify(error=err), 400
    return jsonify(message='User created', username=username), 201


@api_bp.route('/admin/users/<username>', methods=['PATCH'])
@jwt_required()
def api_admin_update_user(username):
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    data = request.get_json(force=True, silent=True) or {}
    from services.auth import update_user, set_user_active, update_user_password, approve_user, get_user

    full_name = data.get('full_name')
    role = data.get('role')
    office = data.get('office')
    active = data.get('active')
    approved = data.get('approved')
    new_password = data.get('password')

    if full_name is not None or role is not None or office is not None:
        ok, err = update_user(
            username,
            full_name=full_name if full_name is not None else None,
            role=role if role is not None else None,
            office=office if office is not None else None,
        )
        if not ok:
            return jsonify(error=err), 400

    if active is not None:
        set_user_active(username, bool(active))

    if approved is True:
        approve_user(username)

    if new_password:
        ok, err = update_user_password(username, new_password)
        if not ok:
            return jsonify(error=err), 400

    updated = get_user(username)
    return jsonify(serialize(updated or {'username': username}))


@api_bp.route('/admin/users/<username>', methods=['DELETE'])
@jwt_required()
def api_admin_delete_user(username):
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    if username.lower() == user_id.lower():
        return jsonify(error='Cannot delete your own account'), 400
    from services.auth import delete_user
    delete_user(username)
    return jsonify(message='User deleted')


# ── Admin: Document full edit ──────────────────────────────────────────────────

@api_bp.route('/documents/<doc_id>', methods=['PATCH'])
@jwt_required()
def api_edit_document(doc_id):
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        if not user or user.get('role') not in ('admin', 'staff', 'superadmin'):
            return jsonify(error='Staff access required'), 403
    data = request.get_json(force=True, silent=True) or {}
    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404

    for field in ('doc_name', 'category', 'from_office', 'sender_org', 'sender_name', 'referred_to', 'remarks'):
        if field in data:
            doc[field] = data[field]
    doc['updated_at'] = now_str()
    doc['updated_by'] = user_id
    save_doc(doc)
    return jsonify(serialize(doc))


# ── Trash endpoints ───────────────────────────────────────────────────────────

@api_bp.route('/trash', methods=['GET'])
@jwt_required()
def api_get_trash():
    """Admin: list all soft-deleted documents."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        if not user or user.get('role') not in ('admin', 'superadmin'):
            return jsonify(error='Admin access required'), 403
    from services.documents import load_docs
    all_docs = load_docs(include_deleted=True)
    deleted = [d for d in all_docs if d.get('deleted')]
    deleted.sort(key=lambda d: d.get('deleted_at', ''), reverse=True)
    return jsonify(serialize(deleted))


@api_bp.route('/documents/<doc_id>/restore', methods=['POST'])
@jwt_required()
def api_restore_document(doc_id):
    """Admin: restore a soft-deleted document."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        if not user or user.get('role') not in ('admin', 'superadmin'):
            return jsonify(error='Admin access required'), 403
    from services.documents import restore_doc, load_docs
    all_docs = load_docs(include_deleted=True)
    doc = next((d for d in all_docs if d.get('id') == doc_id), None)
    if not doc:
        return jsonify(error='Document not found'), 404
    if not doc.get('deleted'):
        return jsonify(error='Document is not deleted'), 400
    restore_doc(doc_id)
    return jsonify(message='Document restored')


@api_bp.route('/documents/<doc_id>/permanent', methods=['DELETE'])
@jwt_required()
def api_permanent_delete(doc_id):
    """Admin: permanently delete a document (cannot be undone)."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    from services.documents import delete_doc_forever, load_docs
    all_docs = load_docs(include_deleted=True)
    doc = next((d for d in all_docs if d.get('id') == doc_id), None)
    if not doc:
        return jsonify(error='Document not found'), 404
    delete_doc_forever(doc_id)
    return jsonify(message='Document permanently deleted')


# ── Routing slip detail ───────────────────────────────────────────────────────

@api_bp.route('/routing-slips/<slip_id>', methods=['GET'])
@jwt_required()
def api_get_routing_slip(slip_id):
    """Get a single routing slip with its documents resolved."""
    from services.misc import get_routing_slip
    slip = get_routing_slip(slip_id)
    if not slip:
        return jsonify(error='Routing slip not found'), 404
    # Resolve doc_ids to actual document summaries
    doc_ids = slip.get('doc_ids') or []
    if isinstance(doc_ids, str):
        import json as _json
        try:
            doc_ids = _json.loads(doc_ids)
        except Exception:
            doc_ids = []
    docs = []
    for did in doc_ids:
        d = get_doc(did)
        if d:
            docs.append({
                'id': d.get('id'),
                'doc_id': d.get('doc_id'),
                'doc_name': d.get('doc_name'),
                'status': d.get('status'),
                'category': d.get('category'),
                'from_office': d.get('from_office'),
            })
    slip['documents'] = docs
    return jsonify(serialize(slip))


@api_bp.route('/routing-slips', methods=['POST'])
@jwt_required()
def api_create_routing_slip():
    """Staff/Admin: create a new routing slip for one or more documents."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        if not user or user.get('role') not in ('admin', 'staff', 'superadmin'):
            return jsonify(error='Staff access required'), 403

    data = request.get_json(force=True, silent=True) or {}
    doc_ids     = data.get('doc_ids', [])
    destination = data.get('destination', '').strip()
    notes       = data.get('notes', '').strip()
    slip_date   = data.get('slip_date', now_str()[:10])

    if not doc_ids:
        return jsonify(error='At least one document is required'), 400
    if not destination:
        return jsonify(error='Destination office is required'), 400

    from services.misc import save_routing_slip, generate_slip_no
    from services.qr import create_slip_token
    from services.documents import get_doc, save_doc

    user = get_user_by_username(user_id)
    actor       = (user.get('full_name') or user_id) if user else user_id
    from_office = (user.get('office') or 'DepEd Leyte Division') if user else 'DepEd Leyte Division'

    slip_id  = str(uuid.uuid4())[:8].upper()
    slip_no  = generate_slip_no()
    recv_token = create_slip_token(slip_id, 'SLIP_RECEIVE')
    rel_token  = create_slip_token(slip_id, 'SLIP_RELEASE')
    ts = now_str()

    slip = {
        'id':          slip_id,
        'slip_no':     slip_no,
        'destination': destination,
        'from_office': from_office,
        'prepared_by': actor,
        'doc_ids':     doc_ids,
        'notes':       notes,
        'slip_date':   slip_date,
        'created_at':  ts,
        'recv_token':  recv_token,
        'rel_token':   rel_token,
        'status':      'Routed',
    }
    save_routing_slip(slip)

    # Update each document: status → Routed, link to slip
    for did in doc_ids:
        doc = get_doc(did)
        if doc:
            doc['status']          = 'Routed'
            doc['forwarded_to']    = destination
            doc['routing_slip_id'] = slip_id
            doc['routing_slip_no'] = slip_no
            doc['updated_at']      = ts
            doc['updated_by']      = user_id
            doc.setdefault('travel_log', []).append({
                'office':    from_office,
                'action':    f'Released — Routed to {destination}',
                'officer':   actor,
                'timestamp': ts,
                'remarks':   f'Routing slip {slip_no}. Forwarded {from_office} → {destination}.',
                'slip_no':   slip_no,
            })
            save_doc(doc)

    return jsonify(serialize({'slip_id': slip_id, 'slip_no': slip_no, 'destination': destination})), 201


@api_bp.route('/routing-slips/<slip_id>/reroute', methods=['POST'])
@jwt_required()
def api_reroute_slip(slip_id):
    """Staff/Admin: reroute slip to a new destination (archives original, creates new)."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        if not user or user.get('role') not in ('admin', 'staff', 'superadmin'):
            return jsonify(error='Staff access required'), 403

    data = request.get_json(force=True, silent=True) or {}
    new_destination = data.get('destination', '').strip()
    notes           = data.get('notes', '').strip()

    if not new_destination:
        return jsonify(error='New destination is required'), 400

    from services.misc import get_routing_slip, save_routing_slip, generate_slip_no
    from services.qr import create_slip_token
    from services.documents import get_doc, save_doc

    slip = get_routing_slip(slip_id)
    if not slip:
        return jsonify(error='Routing slip not found'), 404

    user = get_user_by_username(user_id)
    actor       = (user.get('full_name') or user_id) if user else user_id
    from_office = (user.get('office') or 'DepEd Leyte Division') if user else 'DepEd Leyte Division'
    ts = now_str()
    old_destination = slip.get('destination', '')
    old_slip_no     = slip.get('slip_no', '')

    # Archive original slip
    slip['status']       = 'Archived'
    slip['archived_at']  = ts
    slip['archived_by']  = actor
    slip['rerouted_to']  = new_destination
    slip['is_rerouted']  = True
    save_routing_slip(slip)

    # Create new slip
    new_slip_id  = str(uuid.uuid4())[:8].upper()
    new_slip_no  = generate_slip_no()
    recv_token   = create_slip_token(new_slip_id, 'SLIP_RECEIVE')
    rel_token    = create_slip_token(new_slip_id, 'SLIP_RELEASE')

    new_slip = {
        'id':               new_slip_id,
        'slip_no':          new_slip_no,
        'destination':      new_destination,
        'from_office':      from_office,
        'prepared_by':      actor,
        'doc_ids':          slip.get('doc_ids', []),
        'notes':            notes,
        'slip_date':        ts[:10],
        'created_at':       ts,
        'recv_token':       recv_token,
        'rel_token':        rel_token,
        'status':           'Routed',
        'original_slip_id': slip_id,
        'original_slip_no': old_slip_no,
        'rerouted_from':    old_destination,
    }
    save_routing_slip(new_slip)

    # Update documents to reference new slip
    for did in slip.get('doc_ids', []):
        doc = get_doc(did)
        if doc:
            doc['forwarded_to']    = new_destination
            doc['routing_slip_id'] = new_slip_id
            doc['routing_slip_no'] = new_slip_no
            doc['updated_at']      = ts
            doc['updated_by']      = user_id
            doc.setdefault('travel_log', []).append({
                'office':    from_office,
                'action':    f'Rerouted to {new_destination}',
                'officer':   actor,
                'timestamp': ts,
                'remarks':   f'Rerouted from {old_destination} → {new_destination}. New slip: {new_slip_no}.',
            })
            save_doc(doc)

    return jsonify(serialize({'slip_id': new_slip_id, 'slip_no': new_slip_no}))


@api_bp.route('/routing-slips/<slip_id>/batch-status', methods=['PATCH'])
@jwt_required()
def api_batch_status_slip(slip_id):
    """Staff/Admin: update all documents in a routing slip to the same status."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        if not user or user.get('role') not in ('admin', 'staff', 'superadmin'):
            return jsonify(error='Staff access required'), 403

    data    = request.get_json(force=True, silent=True) or {}
    status  = data.get('status', '').strip()
    remarks = data.get('remarks', '').strip()

    if not status:
        return jsonify(error='Status is required'), 400

    from services.misc import get_routing_slip, save_routing_slip
    from services.documents import get_doc, save_doc

    slip = get_routing_slip(slip_id)
    if not slip:
        return jsonify(error='Routing slip not found'), 404

    user = get_user_by_username(user_id)
    actor       = (user.get('full_name') or user_id) if user else user_id
    from_office = (user.get('office') or '') if user else ''
    ts = now_str()

    updated = 0
    for did in slip.get('doc_ids', []):
        doc = get_doc(did)
        if doc:
            doc['status']     = status
            doc['updated_at'] = ts
            doc['updated_by'] = user_id
            if status == 'Received':
                doc['date_received'] = ts[:16].replace('T', ' ')
            elif status == 'Released':
                doc['date_released'] = ts[:16].replace('T', ' ')
            doc.setdefault('travel_log', []).append({
                'office':    from_office,
                'action':    f'Batch update → {status}',
                'officer':   actor,
                'timestamp': ts,
                'remarks':   remarks or f'All slip documents marked {status} via slip {slip.get("slip_no", slip_id)}.',
            })
            save_doc(doc)
            updated += 1

    # Also update slip status
    slip['status']     = status
    slip['updated_at'] = ts
    save_routing_slip(slip)

    return jsonify(message=f'{updated} document(s) updated to {status}', updated=updated)


@api_bp.route('/routing-slips/<slip_id>/archive', methods=['POST'])
@jwt_required()
def api_archive_routing_slip(slip_id):
    """Admin/staff: archive a routing slip."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        if not user or user.get('role') not in ('admin', 'staff', 'superadmin'):
            return jsonify(error='Staff access required'), 403
    from services.misc import get_routing_slip
    slip = get_routing_slip(slip_id)
    if not slip:
        return jsonify(error='Routing slip not found'), 404
    if slip.get('status') == 'Archived':
        return jsonify(error='Slip is already archived'), 400
    if USE_DB:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE routing_slips SET status='Archived', archived_at=%s, archived_by=%s WHERE id=%s",
                    (now_str(), user_id, slip_id)
                )
    return jsonify(message='Routing slip archived')


# ── Bulk Trash / Empty All ────────────────────────────────────────────────────

@api_bp.route('/trash/empty', methods=['DELETE'])
@jwt_required()
def api_empty_trash():
    """Admin: permanently delete ALL soft-deleted documents (cannot be undone)."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    from services.documents import load_docs, delete_doc_forever
    all_docs = load_docs(include_deleted=True)
    deleted = [d for d in all_docs if d.get('deleted')]
    count = 0
    for doc in deleted:
        delete_doc_forever(doc['id'])
        count += 1
    return jsonify(message=f'{count} document(s) permanently deleted', count=count)


# ── Health check (JWT-protected) ──────────────────────────────────────────────

@api_bp.route('/health', methods=['GET'])
@jwt_required()
def api_health():
    """Admin: JWT-protected health/DB status check."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    from services.database import USE_DB, get_conn
    db_status = 'not_configured'
    db_error = None
    doc_count = None
    user_count = None
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) as n FROM documents WHERE deleted IS NOT TRUE")
                    doc_count = cur.fetchone()['n']
                    cur.execute("SELECT COUNT(*) as n FROM users WHERE active IS TRUE")
                    user_count = cur.fetchone()['n']
            db_status = 'ok'
        except Exception as e:
            db_status = 'error'
            db_error = str(e)
    else:
        from services.documents import load_docs
        from services.auth import get_all_users
        try:
            doc_count = len([d for d in load_docs() if not d.get('deleted')])
            user_count = len(get_all_users())
            db_status = 'json_fallback'
        except Exception as e:
            db_error = str(e)
    return jsonify({
        'status': 'ok',
        'db_status': db_status,
        'db_error': db_error,
        'doc_count': doc_count,
        'user_count': user_count,
        'server_time': now_str(),
    })


# ── Pending Clients ───────────────────────────────────────────────────────────

@api_bp.route('/clients/pending', methods=['GET'])
@jwt_required()
def api_get_pending_clients():
    """Admin: list users with role=client and approved=False."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    from services.auth import get_pending_clients
    clients = get_pending_clients()
    return jsonify(serialize(clients))


@api_bp.route('/clients/<username>/approve', methods=['POST'])
@jwt_required()
def api_approve_client(username):
    """Admin: approve a pending client account."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    from services.auth import approve_user
    success, err = approve_user(username)
    if not success:
        return jsonify(error=err or 'Failed to approve'), 400
    return jsonify(message=f'Client {username} approved')


@api_bp.route('/clients/<username>/reject', methods=['DELETE'])
@jwt_required()
def api_reject_client(username):
    """Admin: reject (delete) a pending client account."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    from services.auth import delete_user
    success = delete_user(username)
    if not success:
        return jsonify(error='Failed to reject / user not found'), 404
    return jsonify(message=f'Client {username} rejected and removed')


# ── Dropdown Options ──────────────────────────────────────────────────────────

@api_bp.route('/dropdown-options/admin', methods=['GET'])
@jwt_required()
def api_get_dropdown_options():
    """Admin: get all dropdown field configurations (full nested structure)."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    from services.dropdown_options import get_all_dropdown_configs
    return jsonify(get_all_dropdown_configs())


@api_bp.route('/dropdown-options/<field_name>', methods=['PUT'])
@jwt_required()
def api_update_dropdown_options(field_name):
    """Admin: update dropdown options for a field."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    data = request.get_json(force=True, silent=True) or {}
    options = data.get('options', [])
    if not isinstance(options, list):
        return jsonify(error='options must be a list'), 400
    from services.dropdown_options import update_dropdown_options
    success, msg = update_dropdown_options(field_name, options)
    if not success:
        return jsonify(error=msg), 400
    return jsonify(message=msg)


@api_bp.route('/dropdown-options/<field_name>/reset', methods=['DELETE'])
@jwt_required()
def api_reset_dropdown_options(field_name):
    """Admin: reset a field's dropdown options to defaults."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    from services.dropdown_options import reset_to_default
    success, msg = reset_to_default(field_name)
    if not success:
        return jsonify(error=msg), 400
    return jsonify(message=msg)


# ── Document Assignment ────────────────────────────────────────────────────────

@api_bp.route('/documents/<doc_id>/assign', methods=['POST'])
@jwt_required()
def api_assign_document(doc_id):
    """Admin: assign a document to a staff member."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    data = request.get_json(force=True, silent=True) or {}
    staff_username = data.get('staff_username', '').strip()
    if not staff_username:
        return jsonify(error='staff_username is required'), 400
    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404
    ts = now_str()
    doc['assigned_to'] = staff_username
    doc['assigned_at'] = ts
    doc['assigned_by'] = user_id
    doc['updated_at']  = ts
    doc['updated_by']  = user_id
    doc.setdefault('travel_log', []).append({
        'office':    '',
        'action':    f'Assigned to {staff_username}',
        'officer':   user_id,
        'timestamp': ts,
        'remarks':   f'Document assigned to {staff_username} by {user_id}.',
    })
    save_doc(doc)
    return jsonify(message=f'Document assigned to {staff_username}')


@api_bp.route('/documents/<doc_id>/unassign', methods=['POST'])
@jwt_required()
def api_unassign_document(doc_id):
    """Admin: unassign a document from its current staff handler."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404
    ts = now_str()
    old_assignee = doc.get('assigned_to', '')
    doc['assigned_to'] = None
    doc['assigned_at'] = None
    doc['updated_at']  = ts
    doc['updated_by']  = user_id
    doc.setdefault('travel_log', []).append({
        'office':    '',
        'action':    f'Unassigned (was: {old_assignee})',
        'officer':   user_id,
        'timestamp': ts,
        'remarks':   f'Document unassigned by {user_id}.',
    })
    save_doc(doc)
    return jsonify(message='Document unassigned')


# ── Bulk Operations ────────────────────────────────────────────────────────────

@api_bp.route('/documents/bulk-status', methods=['POST'])
@jwt_required()
def api_bulk_status():
    """Staff/Admin: update status for multiple documents at once."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        user_obj = get_user_by_username(user_id)
        if not user_obj or user_obj.get('role') not in ('admin', 'staff', 'superadmin'):
            return jsonify(error='Staff access required'), 403
    data    = request.get_json(force=True, silent=True) or {}
    doc_ids = data.get('doc_ids', [])
    status  = data.get('status', '').strip()
    remarks = data.get('remarks', '').strip()
    if not doc_ids:
        return jsonify(error='doc_ids is required'), 400
    if not status:
        return jsonify(error='status is required'), 400
    user_obj = get_user_by_username(user_id)
    actor    = (user_obj.get('full_name') or user_id) if user_obj else user_id
    office   = (user_obj.get('office') or '') if user_obj else ''
    ts = now_str()
    updated = 0
    for did in doc_ids:
        doc = get_doc(did)
        if doc and not doc.get('deleted'):
            doc['status']     = status
            doc['updated_at'] = ts
            doc['updated_by'] = user_id
            if status == 'Received':
                doc['date_received'] = ts[:16].replace('T', ' ')
            elif status == 'Released':
                doc['date_released'] = ts[:16].replace('T', ' ')
            doc.setdefault('travel_log', []).append({
                'office':    office,
                'action':    f'Bulk update → {status}',
                'officer':   actor,
                'timestamp': ts,
                'remarks':   remarks or f'Bulk status update to {status}.',
            })
            save_doc(doc)
            updated += 1
    return jsonify(message=f'{updated} document(s) updated to {status}', updated=updated)


@api_bp.route('/documents/bulk-delete', methods=['POST'])
@jwt_required()
def api_bulk_delete():
    """Admin: soft-delete multiple documents at once."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
    data    = request.get_json(force=True, silent=True) or {}
    doc_ids = data.get('doc_ids', [])
    if not doc_ids:
        return jsonify(error='doc_ids is required'), 400
    from services.documents import delete_doc
    deleted = 0
    for did in doc_ids:
        doc = get_doc(did)
        if doc and not doc.get('deleted'):
            delete_doc(did, user_id)
            deleted += 1
    return jsonify(message=f'{deleted} document(s) moved to trash', deleted=deleted)


# ── Office Documents ──────────────────────────────────────────────────────────

@api_bp.route('/offices/documents', methods=['GET'])
@jwt_required()
def api_office_documents():
    """Get documents grouped by office, or filtered by a specific office."""
    from services.documents import load_docs
    office = request.args.get('office', '').strip()
    docs   = load_docs()
    if office:
        docs = [d for d in docs if (d.get('from_office') or '').lower() == office.lower()]
        docs.sort(key=lambda d: d.get('created_at', ''), reverse=True)
        return jsonify(serialize({'office': office, 'total': len(docs), 'documents': docs}))
    # Grouped view
    groups: dict = {}
    for d in docs:
        off = d.get('from_office') or 'Unknown'
        groups.setdefault(off, []).append(d)
    return jsonify(serialize({
        'grouped': True,
        'offices': [
            {'office': k, 'count': len(v), 'documents': v}
            for k, v in sorted(groups.items())
        ],
    }))


# ── Client Registration & Portal ──────────────────────────────────────────────

@api_bp.route('/client/register', methods=['POST'])
def api_client_register():
    """Public: register a new client account (pending admin approval)."""
    data      = request.get_json(force=True, silent=True) or {}
    username  = data.get('username', '').strip().lower()
    password  = data.get('password', '')
    full_name = data.get('full_name', '').strip()
    email     = data.get('email', '').strip()
    if not username or not password or not full_name:
        return jsonify(error='username, password, and full_name are required'), 400
    if len(password) < 6:
        return jsonify(error='Password must be at least 6 characters'), 400
    from services.auth import get_user_by_username as _get_u, create_user as _create_u
    if _get_u(username):
        return jsonify(error='Username already taken'), 409
    success, msg = _create_u(
        username=username, full_name=full_name,
        password=password, role='client',
        office='', email=email,
    )
    if not success:
        return jsonify(error=msg or 'Registration failed'), 400
    return jsonify(message='Registration submitted. Awaiting admin approval.'), 201


@api_bp.route('/client/documents', methods=['GET'])
@jwt_required()
def api_client_documents():
    """Client: list their own submitted documents."""
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    if not user or user.get('role') != 'client':
        return jsonify(error='Client access required'), 403
    from services.documents import load_docs
    search        = request.args.get('search', '').strip().lower()
    status_filter = request.args.get('status', '').strip()
    docs = [d for d in load_docs() if not d.get('deleted') and
            (d.get('submitted_by') == user_id or d.get('logged_by') == user_id)]
    if search:
        docs = [d for d in docs if
                search in (d.get('doc_name') or '').lower() or
                search in (d.get('doc_id') or '').lower()]
    if status_filter and status_filter != 'All':
        docs = [d for d in docs if d.get('status') == status_filter]
    docs.sort(key=lambda d: d.get('created_at', ''), reverse=True)
    return jsonify(serialize({'total': len(docs), 'documents': docs}))


@api_bp.route('/client/submit', methods=['POST'])
@jwt_required()
def api_client_submit():
    """Client: submit one or more documents (cart-based). Accepts either a
    single doc object or a list under the key 'documents'. Max 50 items."""
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    if not user or user.get('role') != 'client':
        return jsonify(error='Client access required'), 403
    data = request.get_json(force=True, silent=True) or {}

    # Support both single-doc and cart (list) payloads
    raw_items = data.get('documents')
    if raw_items is None:
        # single-doc legacy format
        raw_items = [data]

    if not isinstance(raw_items, list) or len(raw_items) == 0:
        return jsonify(error='No documents provided'), 400
    if len(raw_items) > 50:
        return jsonify(error='Maximum 50 documents per submission'), 400

    # Top-level office / staff context (same for all docs in the cart)
    office_name     = (data.get('office_name') or '').strip()
    office_slug     = (data.get('office_slug') or '').strip()
    selected_staff  = (data.get('selected_staff') or '').strip()

    # Resolve assigned staff: explicit selection → primary_recipient → auto-find
    assigned_staff      = ''
    assigned_staff_name = ''
    if selected_staff:
        from services.auth import get_all_users
        for u in get_all_users():
            if u.get('username') == selected_staff:
                assigned_staff      = selected_staff
                assigned_staff_name = u.get('full_name') or selected_staff
                break
    if not assigned_staff and office_name:
        from services.auth import get_all_users
        from services.misc import load_saved_offices
        # Try primary_recipient from saved offices
        for off in load_saved_offices():
            if (off.get('office_slug') == office_slug or
                    off.get('office_name', '').strip().lower() == office_name.lower()):
                pr = off.get('primary_recipient', '')
                if pr:
                    for u in get_all_users():
                        if u.get('username') == pr:
                            assigned_staff      = pr
                            assigned_staff_name = u.get('full_name') or pr
                            break
                break
        # Fallback: any staff in that office
        if not assigned_staff:
            for u in get_all_users():
                if (u.get('office', '').strip().lower() == office_name.lower()
                        and u.get('role') in ('staff', 'admin')):
                    assigned_staff      = u.get('username', '')
                    assigned_staff_name = u.get('full_name') or assigned_staff
                    break
        # Final fallback: any staff/admin
        if not assigned_staff:
            for u in get_all_users():
                if u.get('role') in ('staff', 'admin'):
                    assigned_staff      = u.get('username', '')
                    assigned_staff_name = u.get('full_name') or assigned_staff
                    break

    sender_name = user.get('full_name') or user_id

    submitted = []
    ts = now_str()
    for item in raw_items:
        doc_name    = (item.get('doc_name') or '').strip()
        referred_to = (item.get('referred_to') or '').strip()
        category    = (item.get('category') or '').strip()
        unit_office = (item.get('unit_office') or '').strip()
        remarks     = (item.get('remarks') or item.get('description') or '').strip()

        if not doc_name:
            return jsonify(error='doc_name is required for every document'), 400
        if not referred_to:
            return jsonify(error='referred_to is required for every document'), 400

        doc = {
            'id':                   str(uuid.uuid4()),
            'doc_id':               generate_ref(),
            'doc_name':             doc_name,
            'category':             category or 'Request',
            'description':          remarks,
            'from_office':          sender_name,
            'sender_name':          sender_name,
            'sender_org':           unit_office,
            'referred_to':          referred_to or office_name,
            'remarks':              remarks,
            'status':               'Pending',
            'logged_by':            user_id,
            'submitted_by':         user_id,
            'submitted_by_name':    sender_name,
            'target_office_slug':   office_slug,
            'target_office_name':   office_name,
            'pending_at_staff':     assigned_staff,
            'pending_at_staff_name': assigned_staff_name,
            'pending_at_office':    office_name,
            'transfer_status':      'pending' if (assigned_staff or office_name) else '',
            'created_at':           ts,
            'updated_at':           ts,
            'deleted':              False,
            'travel_log':           [{
                'office':    office_name or unit_office or '',
                'action':    f'Document Submitted by Client — Pending at {assigned_staff_name or office_name or "office"}',
                'officer':   sender_name,
                'timestamp': ts,
                'remarks':   f'Submitted via mobile client portal. Target office: {office_name}. Assigned to: {assigned_staff_name}.',
            }],
        }
        save_doc(doc)
        submitted.append({'id': doc['id'], 'doc_id': doc['doc_id'], 'doc_name': doc_name, 'status': 'Pending'})

    return jsonify(serialize({'submitted': submitted, 'count': len(submitted)})), 201


@api_bp.route('/client/documents/<doc_id>', methods=['DELETE'])
@jwt_required()
def api_client_delete_document(doc_id):
    """Client: soft-delete their own REJECTED document (moves to trash)."""
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    if not user or user.get('role') != 'client':
        return jsonify(error='Client access required'), 403
    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404
    if doc.get('logged_by') != user_id and doc.get('submitted_by') != user_id:
        return jsonify(error='You can only delete your own documents'), 403
    if (doc.get('status') or '').lower() != 'rejected':
        return jsonify(error='You can only delete rejected documents'), 400
    from services.documents import delete_doc
    delete_doc(doc_id, user_id)
    return jsonify(message='Document moved to trash')


@api_bp.route('/client/trash', methods=['GET'])
@jwt_required()
def api_client_trash():
    """Client: list their own soft-deleted documents."""
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    if not user or user.get('role') != 'client':
        return jsonify(error='Client access required'), 403
    from services.documents import load_docs
    all_docs = load_docs(include_deleted=True)
    deleted  = [d for d in all_docs if d.get('deleted') and
                (d.get('submitted_by') == user_id or d.get('logged_by') == user_id)]
    deleted.sort(key=lambda d: d.get('deleted_at', ''), reverse=True)
    return jsonify(serialize(deleted))


@api_bp.route('/client/documents/<doc_id>/restore', methods=['POST'])
@jwt_required()
def api_client_restore_document(doc_id):
    """Client: restore their own soft-deleted document."""
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    if not user or user.get('role') != 'client':
        return jsonify(error='Client access required'), 403
    from services.documents import load_docs, restore_doc
    all_docs = load_docs(include_deleted=True)
    doc = next((d for d in all_docs if d.get('id') == doc_id), None)
    if not doc:
        return jsonify(error='Document not found'), 404
    if doc.get('submitted_by') != user_id and doc.get('logged_by') != user_id:
        return jsonify(error='You can only restore your own documents'), 403
    if not doc.get('deleted'):
        return jsonify(error='Document is not deleted'), 400
    restore_doc(doc_id)
    return jsonify(message='Document restored')


@api_bp.route('/client/documents/<doc_id>/permanent', methods=['DELETE'])
@jwt_required()
def api_client_permanent_delete(doc_id):
    """Client: permanently delete their own document from trash."""
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    if not user or user.get('role') != 'client':
        return jsonify(error='Client access required'), 403
    from services.documents import load_docs, delete_doc_forever
    all_docs = load_docs(include_deleted=True)
    doc = next((d for d in all_docs if d.get('id') == doc_id), None)
    if not doc:
        return jsonify(error='Document not found'), 404
    if doc.get('submitted_by') != user_id and doc.get('logged_by') != user_id:
        return jsonify(error='You can only permanently delete your own documents'), 403
    delete_doc_forever(doc_id)
    return jsonify(message='Document permanently deleted')


@api_bp.route('/client/trash/empty', methods=['DELETE'])
@jwt_required()
def api_client_empty_trash():
    """Client: permanently delete ALL documents in their own trash."""
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    if not user or user.get('role') != 'client':
        return jsonify(error='Client access required'), 403
    from services.documents import load_docs, delete_doc_forever
    all_docs = load_docs(include_deleted=True)
    my_deleted = [d for d in all_docs
                  if d.get('deleted') and
                  (d.get('logged_by') == user_id or d.get('submitted_by') == user_id)]
    count = 0
    for doc in my_deleted:
        try:
            delete_doc_forever(doc.get('id', ''))
            count += 1
        except Exception:
            pass
    return jsonify(message=f'Permanently deleted {count} document(s)', count=count)


def send_push_notification(username: str, title: str, body: str, data: dict = None):
    """Send push notification to a specific user via Expo Push API."""
    if data is None:
        data = {}
    import requests as req

    _ensure_push_tokens_loaded()
    with _push_tokens_lock:
        token = _push_tokens.get(username)
    if not token:
        return False

    try:
        response = req.post(
            'https://exp.host/--/api/v2/push/send',
            json={
                'to': token,
                'title': title,
                'body': body,
                'data': data,
                'sound': 'default',
                'priority': 'high',
                'channelId': 'documents',
            },
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        return response.status_code == 200
    except Exception:
        return False