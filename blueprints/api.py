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


def get_user_by_username(username: str):
    """Fetch user by username."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT id, username, password_hash, full_name, role,
                                  COALESCE(office, '') AS office, active, approved
                           FROM users WHERE username = %s""",
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
    offices = load_saved_offices()
    return jsonify(serialize(offices))


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