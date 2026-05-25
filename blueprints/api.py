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


@api_bp.route('/app-version', methods=['GET'])
def api_app_version():
    """
    Public endpoint — returns the current app version requirements.
    The mobile app calls this on every launch to decide whether to
    prompt the user to update.

    Edit  static/apk/version.json  to change version numbers; no
    code change or server restart required.
    """
    import json
    from flask import current_app
    version_file = os.path.join(current_app.static_folder, 'apk', 'version.json')
    try:
        with open(version_file, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {
            'latest_version': '1.0.0',
            'min_version':    '1.0.0',
            'download_url':   '/download',
            'release_notes':  '',
            'force_update':   False,
        }
    return jsonify(data)


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
    admin_env = os.environ.get('ADMIN_USERNAME', '')
    if admin_env and secrets.compare_digest(identity.lower(), admin_env.lower()):  # env-var admin bypass
        access_token = create_access_token(identity=identity)
        return jsonify(serialize({"access_token": access_token}))
    user = get_user_by_username(identity)
    if not user:
        return jsonify(error='User not found'), 401
    if not user.get('active', True):
        return jsonify(error='Account disabled'), 403
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


def _matches_office(doc, office_lower):
    # All comparisons are exact (case-insensitive) to prevent "Main"
    # accidentally matching "MainOffice" or "Main Hall".
    doc_referred      = (doc.get("referred_to") or "").lower().strip()
    doc_target        = (doc.get("target_office_name") or "").lower().strip()
    doc_forwarded     = (doc.get("forwarded_to") or "").lower().strip()
    doc_pending       = (doc.get("pending_at_office") or "").lower().strip()
    doc_transferred   = (doc.get("transferred_to_office") or "").lower().strip()
    doc_logged_office = (doc.get("logged_by_office") or "").lower().strip()
    tl = doc.get("travel_log", [])
    tl_office = (tl[0].get("office") or "").lower().strip() if tl else ""
    # routing is a list — check membership, not substring
    routing_offices = [r.lower().strip() for r in doc.get("routing", [])]

    return (
        office_lower == doc_referred or
        office_lower == doc_target or
        office_lower == doc_forwarded or
        office_lower == doc_pending or
        office_lower == doc_transferred or
        office_lower == doc_logged_office or
        office_lower == tl_office or
        office_lower in routing_offices
    )


@api_bp.route('/documents', methods=['GET'])
@jwt_required()
def api_get_documents():
    status    = request.args.get('status')
    office    = request.args.get('office')
    search    = request.args.get('search')
    cat       = request.args.get('cat')
    staff     = request.args.get('staff')
    source    = request.args.get('source')
    date_from = request.args.get('date_from')
    date_to   = request.args.get('date_to')
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
        user_office_lower = user_office.strip().lower() if user_office else ''
        docs = [d for d in docs if
            d.get('logged_by') == user_id
            or d.get('accepted_by') == user_id
            or d.get('accepted_by_username') == user_id
            or d.get('transferred_by') == user_id
            or d.get('pending_at_staff') == user_id
            or d.get('assigned_to') == user_id
            or (user_office_lower and d.get('pending_at_office', '').strip().lower() == user_office_lower)
            or (user_office_lower and _matches_office(d, user_office_lower))
        ]

    if status:
        docs = [d for d in docs if d.get('status') == status]
    if office:
        office_lower = office.lower().strip()
        docs = [d for d in docs if _matches_office(d, office_lower)]
    if search:
        search_lower = search.lower()
        docs = [d for d in docs if
                search_lower in (d.get('doc_name') or '').lower() or
                search_lower in (d.get('doc_id') or '').lower() or
                search_lower in (d.get('sender_org') or '').lower() or
                search_lower in (d.get('from_office') or '').lower()]
    if cat:
        cat_lower = cat.lower()
        docs = [d for d in docs if (d.get('category') or '').lower() == cat_lower]
    if staff:
        docs = [d for d in docs if
                d.get('logged_by') == staff or d.get('assigned_to') == staff]
    if source:
        source_lower = source.lower()
        docs = [d for d in docs if (d.get('source', 'staff') or 'staff').lower() == source_lower]
    if date_from:
        docs = [d for d in docs if (d.get('doc_date') or '')[:10] >= date_from]
    if date_to:
        docs = [d for d in docs if (d.get('doc_date') or '')[:10] <= date_to]

    total = len(docs)
    start = (page - 1) * limit
    end = start + limit
    docs_page = docs[start:end]

    return jsonify(serialize({"documents": docs_page, "total": total, "page": page, "limit": limit}))


@api_bp.route('/export-csv', methods=['GET'])
@jwt_required()
def api_export_csv():
    import csv
    import io as _io
    from datetime import date as _date

    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    user_role = 'admin' if _is_admin_user(user_id) else (user.get('role', '') if user else '')

    docs = load_docs()

    # Role scoping — staff see only their own documents (same as web export-csv)
    if user_role not in ('admin', 'superadmin'):
        docs = [
            d for d in docs
            if d.get('original_logged_by') == user_id
            or d.get('logged_by') == user_id
            or d.get('received_by') == user_id
            or d.get('accepted_by') == user_id
            or d.get('transferred_by') == user_id
        ]

    # Filters (reuse same logic as api_get_documents)
    status    = request.args.get('status')
    office    = request.args.get('office')
    search    = request.args.get('search')
    cat       = request.args.get('cat')
    staff     = request.args.get('staff')
    source    = request.args.get('source')
    date_from = request.args.get('date_from')
    date_to   = request.args.get('date_to')

    if status:
        docs = [d for d in docs if d.get('status') == status]
    if office:
        office_lower = office.lower().strip()
        docs = [d for d in docs if _matches_office(d, office_lower)]
    if search:
        search_lower = search.lower()
        docs = [d for d in docs if
                search_lower in (d.get('doc_name') or '').lower() or
                search_lower in (d.get('doc_id') or '').lower() or
                search_lower in (d.get('sender_name') or '').lower() or
                search_lower in (d.get('sender_org') or '').lower() or
                search_lower in (d.get('referred_to') or '').lower() or
                search_lower in (d.get('notes') or '').lower()]
    if cat:
        docs = [d for d in docs if (d.get('category') or '').lower() == cat.lower()]
    if staff:
        docs = [d for d in docs if
                d.get('logged_by') == staff or d.get('assigned_to') == staff]
    if source:
        source_lower = source.lower()
        docs = [d for d in docs if (d.get('source', 'staff') or 'staff').lower() == source_lower]
    if date_from:
        docs = [d for d in docs if (d.get('doc_date') or '')[:10] >= date_from]
    if date_to:
        docs = [d for d in docs if (d.get('doc_date') or '')[:10] <= date_to]

    # Build CSV
    output = _io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Ref No.', 'Document', 'Category', 'Sender', 'Sender Org',
        'Referred To', 'Status', 'Due Date', 'Date Logged', 'Remarks',
    ])
    for d in docs:
        writer.writerow([
            d.get('doc_id', ''),
            d.get('doc_name', ''),
            d.get('category', ''),
            d.get('sender_name', ''),
            d.get('sender_org', ''),
            d.get('referred_to', ''),
            d.get('status', ''),
            (d.get('created_at') or '')[:10],
            d.get('notes', '') or d.get('description', ''),
        ])

    filename = f"documents_export_{_date.today().isoformat()}.csv"
    from flask import Response
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@api_bp.route('/documents/<doc_id>', methods=['GET'])
@jwt_required()
def api_get_document(doc_id):
    doc = get_doc(doc_id)
    if not doc or doc.get('deleted'):
        return jsonify(error='Document not found'), 404
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        user = get_user_by_username(user_id)
        user_role = user.get('role', '') if user else ''
        if user_role != 'staff' and doc.get('logged_by') != user_id and doc.get('submitted_by') != user_id:
            return jsonify(error='Forbidden'), 403
    return jsonify(serialize(doc))


@api_bp.route('/documents', methods=['POST'])
@jwt_required()
def api_create_document():
    data = request.get_json()
    user_id = get_jwt_identity()

    user = get_user_by_username(user_id)
    actor          = (user.get('full_name') or user_id) if user else user_id
    current_office = (user.get('office') or '') if user else ''

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
        "notes": data.get('notes', ''),
        "doc_date": data.get('doc_date', now_str()),
        "status": "Pending",
        "created_at": now_str(),
        "logged_by": user_id,
        "travel_log": [],
    }
    insert_doc(doc)

    # ── Auto-transfer if referred_to_username was provided ─────────────────
    ref_username = (data.get('referred_to_username') or '').strip()
    if ref_username:
        from services.auth import get_all_users
        from services.misc import audit_log
        from utils import get_client_ip
        ref_user = next(
            (u for u in get_all_users() if u.get('username') == ref_username),
            None
        )
        if ref_user:
            ref_office    = ref_user.get('office', '') or ''
            ref_full_name = ref_user.get('full_name', '') or ref_username
            now_t = now_str()
            doc['travel_log'].append({
                'office':    current_office,
                'action':    'Transferred',
                'officer':   actor,
                'timestamp': now_t,
                'remarks':   'Auto-transferred to referred staff',
            })
            doc['status']                = 'Transferred'
            doc['transferred_to']        = ref_username
            doc['transferred_to_office'] = ref_office
            doc['transferred_by']        = user_id
            doc['transferred_at']        = now_t
            doc['transfer_type']         = 'inside_office'
            doc['pending_at_staff']      = ref_username
            doc['pending_at_office']     = ref_office
            doc['pending_at_staff_name'] = ref_full_name
            doc['transfer_status']       = 'pending'
            save_doc(doc)
            audit_log('doc_auto_transferred',
                      f"doc_id={doc['id']} to={ref_username} office={ref_office}",
                      username=user_id, ip=get_client_ip())
    # ── End auto-transfer ──────────────────────────────────────────────────

    return jsonify(serialize(doc)), 201


@api_bp.route('/documents/<doc_id>/status', methods=['PATCH'])
@jwt_required()
def api_update_status(doc_id):
    data = request.get_json()
    new_status = data.get('status')
    from config import STATUS_OPTIONS
    if not new_status or new_status not in STATUS_OPTIONS:
        return jsonify(error=f'Invalid status. Must be one of: {STATUS_OPTIONS}'), 400
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
    from services.misc import audit_log
    from utils import get_client_ip
    audit_log(
        'doc_status_changed',
        f"ref={doc.get('doc_id','')} from={old_status} to={new_status} by={user_id}",
        username=user_id,
        ip=get_client_ip()
    )

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
    base_url = request.host_url.rstrip('/')
    qr.add_data(f"{base_url}/receive/{doc['id']}")
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


@api_bp.route('/qr/slip-preview', methods=['POST'])
@jwt_required()
def api_preview_slip_qr():
    """
    Non-destructive slip token lookup — returns slip metadata without
    consuming the token or updating any document status.
    """
    from services.qr import peek_slip_token
    from services.misc import get_routing_slip

    data = request.get_json() or {}
    token = data.get('token')
    if not token:
        return jsonify(error='No token provided'), 400

    user_id = get_jwt_identity()
    user    = get_user_by_username(user_id)
    if not user or user.get('role') not in ('staff', 'admin'):
        return jsonify(error='Forbidden'), 403

    slip_id, token_type = peek_slip_token(token)
    if not slip_id:
        return jsonify(error='Invalid or expired routing slip QR'), 401

    slip = get_routing_slip(slip_id)
    if not slip:
        return jsonify(error='Routing slip not found'), 404

    user_office = (user.get('office') or '') if user else ''

    # Office validation — staff only
    if user.get('role') == 'staff':
        if token_type == 'SLIP_RECEIVE':
            expected = slip.get('destination', '')
            if expected and user_office.lower() != expected.lower():
                return jsonify(error=f"This slip is not for your office. It is addressed to {expected}."), 403
        elif token_type == 'SLIP_RELEASE':
            expected = slip.get('from_office', '')
            if expected and user_office.lower() != expected.lower():
                return jsonify(error=f"This slip was not sent from your office. It was sent from {expected}."), 403

    return jsonify(serialize({
        'slip':       slip,
        'token_type': token_type,
        'docs_count': len(slip.get('doc_ids', [])),
    }))


@api_bp.route('/qr/slip-scan', methods=['POST'])
@jwt_required()
def api_scan_slip_qr():
    """
    Consume a routing slip QR token and batch-update all docs on the slip.
    SLIP_RECEIVE → marks each doc Received, returns a new SLIP_RELEASE QR.
    SLIP_RELEASE → marks each doc Released.
    """
    from services.qr import peek_slip_token, use_slip_token, make_slip_qr_png
    from services.misc import get_routing_slip, audit_log
    from utils import get_client_ip

    data = request.get_json() or {}
    token = data.get('token')
    if not token:
        return jsonify(error='No token provided'), 400

    user_id = get_jwt_identity()
    user    = get_user_by_username(user_id)
    if not user or user.get('role') not in ('staff', 'admin'):
        return jsonify(error='Forbidden'), 403

    # --- Pre-validation: peek at token WITHOUT consuming it ---
    slip_id, token_type = peek_slip_token(token)
    if not slip_id:
        return jsonify(error='Invalid or expired routing slip QR'), 401

    slip = get_routing_slip(slip_id)
    if not slip:
        return jsonify(error='Routing slip not found'), 404

    override_office     = data.get('override_office', '').strip()
    override_recipient  = data.get('override_recipient', '').strip()

    actor       = (user.get('full_name') or user_id) if user else user_id
    user_office = (user.get('office') or '') if user else ''
    slip_no     = slip.get('slip_no', slip_id)
    destination = slip.get('destination', user_office)
    from_office = slip.get('from_office', '')

    # Office validation — staff only (runs BEFORE token is consumed)
    if user.get('role') == 'staff':
        if token_type == 'SLIP_RECEIVE':
            expected = slip.get('destination', '')
            if expected and user_office.lower() != expected.lower():
                return jsonify(error=f"This slip is not for your office. It is addressed to {expected}."), 403
        elif token_type == 'SLIP_RELEASE':
            expected = slip.get('from_office', '')
            if expected and user_office.lower() != expected.lower():
                return jsonify(error=f"This slip was not sent from your office. It was sent from {expected}."), 403

    # --- All checks passed — now consume the token ---
    slip_id, token_type = use_slip_token(token)
    if not slip_id:
        return jsonify(error='Token expired between preview and confirm'), 401

    # Admin override — replace destination/from_office for travel log attribution
    if user.get('role') == 'admin' and override_office:
        if token_type == 'SLIP_RECEIVE':
            destination = override_office
        elif token_type == 'SLIP_RELEASE':
            from_office = override_office

    receiver = override_recipient if override_recipient else actor

    docs_updated = []
    for doc_id in slip.get('doc_ids', []):
        doc = get_doc(doc_id)
        if not doc:
            continue

        if token_type == 'SLIP_RECEIVE':
            doc['status']        = 'Received'
            doc['received_by']   = receiver
            doc['date_received'] = now_str()[:16].replace('T', ' ')
            doc['updated_at']    = now_str()
            doc['updated_by']    = user_id
            doc.setdefault('travel_log', []).append({
                'office':    destination,
                'action':    'Received via Routing Slip',
                'officer':   receiver,
                'timestamp': now_str(),
                'remarks':   f'Auto-updated via routing slip {slip_no} RECEIVE scan.',
            })

        elif token_type == 'SLIP_RELEASE':
            doc['status']        = 'Released'
            doc['date_released'] = now_str()[:16].replace('T', ' ')
            doc['updated_at']    = now_str()
            doc['updated_by']    = user_id
            doc.setdefault('travel_log', []).append({
                'office':    from_office,
                'action':    'Released via Routing Slip',
                'officer':   actor,
                'timestamp': now_str(),
                'remarks':   f'Auto-updated via routing slip {slip_no} RELEASE scan.',
            })

        save_doc(doc)
        docs_updated.append(doc)

    # For SLIP_RECEIVE: generate a fresh RELEASE token so the receiving
    # office can later scan-out when the documents leave.
    next_qr_b64 = None
    if token_type == 'SLIP_RECEIVE':
        from services.qr import get_base_url
        base_url      = get_base_url(request.host_url)
        new_rel_token = slip.get('rel_token')
        png           = make_slip_qr_png(
            new_rel_token, 'SLIP_RELEASE',
            slip_no, destination, from_office,
            base_url=base_url,
        )
        next_qr_b64 = base64.b64encode(png).decode()

    audit_log(
        f'slip_scan_{token_type.lower()}',
        f'slip={slip_no} docs={len(docs_updated)} by={user_id}',
        username=user_id,
        ip=get_client_ip(),
    )

    return jsonify(serialize({
        'slip':         slip,
        'docs_updated': docs_updated,
        'token_type':   token_type,
        'next_qr_b64':  next_qr_b64,   # None for SLIP_RELEASE scans
    }))


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


@api_bp.route('/offices/<office_slug>', methods=['PATCH'])
@jwt_required()
def api_update_office(office_slug: str):
    from services.misc import update_office_primary_recipient
    user_id = get_jwt_identity()
    user    = get_user_by_username(user_id)
    if not user or user.get('role') != 'admin':
        return jsonify(error='Forbidden'), 403
    data              = request.get_json() or {}
    primary_recipient = (data.get('primary_recipient') or '').strip()
    try:
        update_office_primary_recipient(office_slug, primary_recipient)
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500


@api_bp.route('/parse-excel-offices', methods=['POST'])
@jwt_required()
def api_parse_excel_offices():
    """JWT-authenticated Excel parser for mobile — same logic as web /api/parse-excel-offices."""
    import openpyxl, io
    user_id = get_jwt_identity()
    user    = get_user_by_username(user_id)
    if not user or user.get('role') != 'admin':
        return jsonify(error='Forbidden'), 403
    f = request.files.get('file')
    if not f:
        return jsonify(error='No file uploaded.'), 400
    try:
        wb = openpyxl.load_workbook(io.BytesIO(f.read()), data_only=True)
        ws = wb.active

        name_col = recipient_col = header_row = None
        for row in ws.iter_rows(min_row=1, max_row=10):
            for cell in row:
                h = str(cell.value or '').strip().lower()
                if name_col is None and ('office' in h or ('name' in h and 'recipient' not in h)):
                    name_col = cell.column
                if recipient_col is None and any(k in h for k in ('recipient', 'staff', 'assigned')):
                    recipient_col = cell.column
            if name_col:
                header_row = row[0].row
                break

        if not header_row:
            return jsonify(error='Could not find an office name column in the file.'), 422

        rows = []
        for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
            office_name = str(row[name_col - 1] or '').strip()
            recipient   = str(row[recipient_col - 1] or '').strip() if recipient_col else ''
            if office_name and office_name.lower() not in ('none', 'nan'):
                rows.append({'office_name': office_name, 'primary_recipient': recipient})
            if len(rows) >= 200:
                break

        if not rows:
            return jsonify(error='No data rows found after the header.'), 422

        return jsonify(rows=rows)
    except Exception as e:
        return jsonify(error=f'Could not read file: {e}'), 400


@api_bp.route('/offices/<office_slug>/staff', methods=['GET'])
@jwt_required()
def api_get_office_staff(office_slug: str):
    """Return staff list for a specific office (used by client submission form).
    Mirrors web app client.py office_staff_list logic exactly:
      1. Filter by user.office == office_name (case-insensitive)
      2. If nothing matches, return ALL staff (fallback)
      primary_recipient is always sorted first with is_primary=True."""
    from services.misc import load_saved_offices
    from services.auth import get_all_users

    # Resolve slug → office name and primary_recipient
    office_name = ''
    primary_recipient = ''
    for off in load_saved_offices():
        if off.get('office_slug') == office_slug:
            office_name = off.get('office_name', '')
            # primary_recipient may be NULL in DB → coerce to str
            primary_recipient = off.get('primary_recipient') or ''
            break

    all_users = get_all_users()
    office_name_lower = office_name.strip().lower()

    def _make_entry(u):
        uname = u.get('username', '')
        return {
            'username':   uname,
            'full_name':  u.get('full_name') or uname,
            'is_primary': uname == primary_recipient,
        }

    # Step 1: staff whose office field matches the office name (same as web app)
    staff = [
        _make_entry(u)
        for u in all_users
        if u.get('role') in ('staff', 'admin')
        and office_name_lower
        and (u.get('office') or '').strip().lower() == office_name_lower
    ]

    # Step 2: fallback — return all staff/admin when no office match (same as web app)
    if not staff:
        staff = [
            _make_entry(u)
            for u in all_users
            if u.get('role') in ('staff', 'admin')
        ]

    # Sort: primary_recipient first, then by full_name alphabetically
    staff.sort(key=lambda s: (not s['is_primary'], (s['full_name'] or '').lower()))

    return jsonify(serialize(staff))


@api_bp.route('/routing-slips', methods=['GET'])
@jwt_required()
def api_get_routing_slips():
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    user_role = 'admin' if _is_admin_user(user_id) else (user.get('role', '') if user else '')
    user_office = (user.get('office') or '') if user else ''

    from services.misc import get_all_routing_slips
    slips = get_all_routing_slips()

    if user_role in ('admin', 'superadmin'):
        return jsonify(serialize(slips))
    elif user_role == 'staff':
        scoped = [
            s for s in slips
            if (user_office and (
                s.get('from_office', '') == user_office or
                s.get('destination', '') == user_office or
                s.get('to_office', '') == user_office
            )) or s.get('created_by') == user_id
        ]
        return jsonify(serialize(scoped))
    else:
        return jsonify(serialize([]))


@api_bp.route('/activity-log', methods=['GET'])
@jwt_required()
def api_activity_log():
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403
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
    for d in result:
        ps = d.get('pending_at_staff')
        if ps:
            ps_user = get_user_by_username(ps)
            d['pending_at_staff_name'] = (
                ps_user.get('full_name') or ps
            ) if ps_user else ps

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

    # Detect proxy acceptance — admin accepting on behalf of a specific staff member
    is_proxy = _is_admin_user(user_id) and bool(pending_staff) and pending_staff != user_id

    new_cycle = doc.get('routing_cycle', 0) + 1

    if is_proxy:
        # Resolve the staff member's full name for the audit trail
        proxy_target_user = get_user_by_username(pending_staff)
        proxy_target_name = (
            proxy_target_user.get('full_name') or pending_staff
        ) if proxy_target_user else pending_staff
        accepted_by_label = f'{user_full_name} (Admin, proxy for {proxy_target_name})'
        action_label = 'Document Accepted (Proxy)'
        remarks_text = (
            f'Document accepted by {user_full_name} (Admin) as proxy for {proxy_target_name}. '
            f'Routing cycle {new_cycle} in progress.'
        )
    else:
        accepted_by_label = user_full_name
        action_label = 'Document Accepted'
        remarks_text = (
            f'Document received and accepted by {user_full_name}. '
            f'Routing cycle {new_cycle} in progress.'
        )

    doc['transfer_status']      = 'accepted'
    doc['status']               = 'Received'
    doc['date_received']        = now_str()[:16].replace('T', ' ')
    doc['accepted_by']          = accepted_by_label
    doc['accepted_by_username'] = user_id
    doc['accepted_at']          = now_str()
    doc['routing_cycle']        = new_cycle
    if is_proxy:
        doc['logged_by']        = pending_staff
        doc['logged_by_office'] = proxy_target_user.get('office', '') if proxy_target_user else user_office
    else:
        doc['logged_by']        = user_id
        doc['logged_by_office'] = user_office

    doc.setdefault('travel_log', []).append({
        'office': user_office or doc.get('pending_at_office', ''),
        'action': action_label,
        'officer': accepted_by_label,
        'timestamp': now_str(),
        'remarks': remarks_text,
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

    import json as _json

    def _parse_dh(val):
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                parsed = _json.loads(val)
                return parsed if isinstance(parsed, list) else []
            except (ValueError, TypeError):
                return []
        return []

    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    if is_admin:
                        cur.execute("""
                            SELECT username, full_name, COALESCE(office, '') AS office, role,
                                   documents_handled
                            FROM users
                            WHERE active = TRUE AND approved = TRUE
                              AND role != 'client'
                            ORDER BY full_name
                        """)
                    else:
                        cur.execute("""
                            SELECT username, full_name, COALESCE(office, '') AS office, role,
                                   documents_handled
                            FROM users
                            WHERE active = TRUE AND approved = TRUE
                              AND role != 'client'
                              AND LOWER(TRIM(office)) = LOWER(TRIM(%s))
                              AND username != %s
                            ORDER BY full_name
                        """, (current_office, user_id))
                    rows = cur.fetchall()
                    result = []
                    for r in rows:
                        d = dict(r)
                        d['documents_handled'] = _parse_dh(d.get('documents_handled'))
                        result.append(d)
                    return jsonify(serialize(result))
        except Exception:
            return jsonify([])
    else:
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
                    'documents_handled': _parse_dh(u.get('documents_handled')),
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
    recipient_full_name = recipient_display
    if to_staff:
        from services.auth import get_all_users
        target_user = next(
            (u for u in get_all_users() if u.get('username') == to_staff),
            None
        )
        if target_user:
            recipient_full_name = target_user.get('full_name') or to_staff

    doc['transfer_status'] = 'pending'
    doc['pending_at_staff'] = to_staff
    doc['pending_at_office'] = to_office
    transfer_type = (data.get('transfer_type') or '').strip()
    doc['status'] = 'Transferred' if transfer_type == 'inside_office' else 'Routed'
    doc['referred_to'] = recipient_full_name
    doc['updated_at'] = now_str()
    doc['updated_by'] = user_id

    old_status       = doc.get('status', '')
    new_cycle        = doc.get('routing_cycle', 0) + 1
    recipient_office = (target_user.get('office', '') if target_user else '') or to_office
    action_label     = (
        f"Transferred to {recipient_full_name} — (Inside Office) (Cycle {new_cycle})"
        if transfer_type == 'inside_office' else
        f"Routed to {recipient_full_name} — (Outside Office) (Cycle {new_cycle})"
    )
    remarks_text = (
        remarks or
        f"Transferred to {recipient_full_name} ({recipient_office or 'N/A'}) from {user_office}. "
        f"Previous status: {old_status}. Transferred by {user_full_name}."
    )

    doc.setdefault('travel_log', []).append({
        'office':    recipient_office or user_office,
        'action':    action_label,
        'officer':   user_full_name,
        'timestamp': now_str(),
        'remarks':   remarks_text,
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


@api_bp.route('/documents/<doc_id>/release', methods=['POST'])
@jwt_required()
def api_release_document(doc_id):
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    user_role = (user.get('role') or '') if user else ''
    user_full_name = (user.get('full_name') or user_id) if user else user_id
    user_office = (user.get('office') or '') if user else ''

    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404

    original_logger = doc.get('original_logged_by') or doc.get('logged_by', '')

    # Only the original logger (or admin) can release
    if user_role != 'admin' and user_id != original_logger:
        return jsonify(error='Only the staff who originally logged this document can release it'), 403

    # Document must be back in the original logger's hands
    if doc.get('logged_by') != user_id and user_role != 'admin':
        return jsonify(error='Document must be returned to you before you can release it'), 403

    total_cycles = doc.get('routing_cycle', 0)

    doc['status'] = 'Released'
    doc['date_released'] = now_str()[:16].replace('T', ' ')
    doc['released_by'] = user_id
    doc['transfer_status'] = 'released'
    doc['updated_at'] = now_str()
    doc['updated_by'] = user_id

    doc.setdefault('travel_log', []).append({
        'office': user_office,
        'action': 'Released by Originating Staff',
        'officer': user_full_name,
        'timestamp': now_str(),
        'remarks': (
            f'All routing cycles completed ({total_cycles} cycle'
            f'{"s" if total_cycles != 1 else ""}). '
            f'Document officially released by {user_full_name}. Workflow closed.'
        ),
    })

    save_doc(doc)
    from services.misc import audit_log
    from utils import get_client_ip
    audit_log(
        'doc_released',
        f"doc_id={doc_id} released_by={user_id} cycles={total_cycles} doc_name={doc.get('doc_name', '')[:60]}",
        username=user_id,
        ip=get_client_ip(),
    )

    return jsonify(serialize(doc))


@api_bp.route('/documents/<doc_id>/receive-from-client', methods=['POST'])
@jwt_required()
def receive_from_client(doc_id):
    """
    Called when a staff member scans a Released document QR from a different office.
    The client has hand-carried the physical document to a new office.
    Creates a new leg in the travel log without breaking existing history.
    """
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    if not user or user.get('role') == 'client':
        return jsonify(error='Forbidden'), 403

    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404

    # Only works on Released documents
    if doc.get('status') != 'Released':
        return jsonify(error='Document must be Released to receive from client'), 400

    # Prevent same office from using this (use normal accept instead)
    staff_office = (user.get('office') or '').strip().lower()
    doc_office = (doc.get('logged_by_office') or '').strip().lower()
    if staff_office and doc_office and staff_office == doc_office:
        return jsonify(error='Document was released by your own office. Use normal workflow instead.'), 400

    # Update document
    doc['status'] = 'Received'
    doc['received_by'] = user.get('full_name') or user_id
    doc['date_received'] = now_str()[:16].replace('T', ' ')
    doc['pending_at_office'] = user.get('office') or ''
    doc['pending_at_staff'] = user_id
    doc['transfer_status'] = 'accepted'
    doc['updated_at'] = now_str()
    doc['updated_by'] = user_id

    doc.setdefault('travel_log', []).append({
        'action': 'Received from Client',
        'office': user.get('office') or '',
        'officer': user.get('full_name') or user_id,
        'timestamp': now_str(),
        'remarks': f'Document hand-carried by client and received at {user.get("office") or "this office"}.'
    })

    save_doc(doc)

    return jsonify(serialize({
        'success': True,
        'message': f'Document received at {user.get("office")}',
        'doc': doc
    }))


@api_bp.route('/documents/<doc_id>/quick-note', methods=['POST'])
@jwt_required()
def api_quick_note(doc_id):
    user_id = get_jwt_identity()

    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404

    data = request.get_json(force=True, silent=True) or {}
    note = (data.get('note') or '').strip()

    doc['notes'] = note
    doc['updated_at'] = now_str()
    doc['updated_by'] = user_id

    save_doc(doc)
    from services.misc import audit_log
    from utils import get_client_ip
    audit_log('note_updated', f'doc_id={doc_id}', username=user_id, ip=get_client_ip())

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

    from services.auth import get_all_users

    # Build stats keyed by username, seeded from the authoritative user list
    # so only real staff/admin accounts appear (no client or ghost usernames)
    all_users = get_all_users()
    stats: dict = {}
    for u in all_users:
        if u.get('role') not in ('staff', 'admin', 'superadmin'):
            continue
        if not u.get('active', True):
            continue
        uname = u.get('username', '')
        if not uname:
            continue
        stats[uname] = {
            'full_name': u.get('full_name') or uname,
            'office':    u.get('office') or '',
            'total':     0,
            'pending':   0,
            'received':  0,
            'released':  0,
            'other':     0,
        }

    # Count docs where the user is logged_by OR original_logged_by (union)
    docs = load_docs()
    for d in docs:
        if d.get('deleted'):
            continue
        s = (d.get('status') or '').lower()
        # Credit both the current logger and the original logger
        owners = set()
        if d.get('logged_by'):
            owners.add(d['logged_by'])
        if d.get('original_logged_by'):
            owners.add(d['original_logged_by'])
        for uname in owners:
            if uname not in stats:
                continue  # skip usernames not in the staff/admin user list
            stats[uname]['total'] += 1
            if s == 'pending':
                stats[uname]['pending'] += 1
            elif s == 'received':
                stats[uname]['received'] += 1
            elif s == 'released':
                stats[uname]['released'] += 1
            else:
                stats[uname]['other'] += 1

    result = sorted(
        [{'username': k, **v} for k, v in stats.items()],
        key=lambda x: -x['total'],
    )
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
    from services.auth import update_user, set_user_active, update_user_password, approve_user, get_user, update_user_documents_handled

    full_name    = data.get('full_name')
    role         = data.get('role')
    office       = data.get('office')
    email        = data.get('email')
    new_username = (data.get('new_username') or '').strip().lower() or None
    active       = data.get('active')
    approved     = data.get('approved')
    new_password = data.get('password')
    doc_types    = data.get('documents_handled')  # list or None

    if any(v is not None for v in (full_name, role, office, email)) or new_username:
        ok, err = update_user(
            username,
            full_name=full_name if full_name is not None else None,
            role=role if role is not None else None,
            office=office if office is not None else None,
            email=email if email is not None else None,
            new_username=new_username if new_username and new_username != username else None,
        )
        if not ok:
            return jsonify(error=err), 400

    # Use the renamed username for follow-up operations
    effective = new_username if new_username and new_username != username else username

    if isinstance(doc_types, list):
        update_user_documents_handled(effective, doc_types)

    if active is not None:
        set_user_active(effective, bool(active))

    if approved is True:
        approve_user(effective)

    if new_password:
        ok, err = update_user_password(effective, new_password)
        if not ok:
            return jsonify(error=err), 400

    updated = get_user(effective)
    return jsonify(serialize(updated or {'username': effective}))


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


@api_bp.route('/admin/users/<username>/resend-credentials', methods=['POST'])
@jwt_required()
def api_admin_resend_credentials(username):
    """Admin: reset password and email new credentials to a user."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403

    import string
    from services.auth import get_all_users, update_user_password
    from services.email import send_credentials_email
    from services.misc import audit_log
    from utils import get_client_ip
    from config import APP_URL

    all_users = get_all_users()
    user = next((u for u in all_users if u.get('username') == username), None)
    if not user:
        return jsonify(error='User not found'), 404

    to_email = (user.get('email') or '').strip()
    if not to_email:
        return jsonify(error='User has no email address on record'), 400

    # Generate 12-char temp password (same algo as bulk_create_users)
    alphabet = string.ascii_letters + string.digits
    pw = [secrets.choice(string.digits), secrets.choice(string.ascii_uppercase),
          *[secrets.choice(alphabet) for _ in range(10)]]
    for j in range(len(pw) - 1, 0, -1):
        k = secrets.randbelow(j + 1)
        pw[j], pw[k] = pw[k], pw[j]
    temp_pw = ''.join(pw)

    ok, err = update_user_password(username, temp_pw)
    if not ok:
        return jsonify(error=err or 'Failed to reset password'), 400

    base = (APP_URL or '').rstrip('/')
    full_name = (user.get('full_name') or username).strip()
    email_sent, email_err = send_credentials_email(to_email, full_name, username, temp_pw, base)

    audit_log('credentials_resent',
              f'user={username} email={to_email} email_sent={email_sent}',
              username=user_id, ip=get_client_ip())

    if email_sent:
        return jsonify(message=f'Credentials sent to {to_email}', email_sent=True)
    return jsonify(
        message=f'Password reset — email failed ({email_err}). Share temp password manually.',
        email_sent=False,
        temp_password=temp_pw,
    ), 207


@api_bp.route('/admin/send-invite', methods=['POST'])
@jwt_required()
def api_admin_send_invite():
    """Admin: generate invite link(s) and optionally email them."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403

    from services.email import send_invite_email, generate_invite_token
    from services.misc import audit_log
    from utils import get_client_ip
    from config import APP_URL, MAIL_ENABLED

    data = request.get_json(force=True, silent=True) or {}
    mode = data.get('mode', 'single')
    base = (APP_URL or '').rstrip('/')

    if mode == 'batch':
        emails = data.get('emails', [])
        if not isinstance(emails, list) or not emails:
            return jsonify(error='emails list is required'), 400

        results = []
        for raw in emails:
            email = raw.strip()
            if not email:
                continue
            if MAIL_ENABLED:
                ok, tok = send_invite_email(email, '', base)
                link = f'{base}/register?token={tok if ok else generate_invite_token(email, "")}'
                results.append({'email': email, 'ok': ok, 'link': link,
                                'msg': 'Sent' if ok else 'Email failed — link generated'})
            else:
                token = generate_invite_token(email, '')
                results.append({'email': email, 'ok': True,
                                'link': f'{base}/register?token={token}', 'msg': 'Link generated'})

        ok_count = sum(1 for r in results if r['ok'])
        audit_log('batch_invites_sent', f'total={len(results)} ok={ok_count}',
                  username=user_id, ip=get_client_ip())
        return jsonify(results=results, total=len(results), sent=ok_count)

    # Single invite
    to_email = data.get('email', '').strip()
    to_name  = data.get('name', '').strip()
    if not to_email:
        return jsonify(error='email is required'), 400

    if MAIL_ENABLED:
        ok, tok = send_invite_email(to_email, to_name, base)
        if ok:
            link = f'{base}/register?token={tok}'
            audit_log('invite_sent', f'email={to_email}', username=user_id, ip=get_client_ip())
            return jsonify(ok=True, link=link, message=f'Invite sent to {to_email}', mail_sent=True)
        token = generate_invite_token(to_email, to_name)
        return jsonify(ok=False, link=f'{base}/register?token={token}',
                       message=f'Email failed. Share link manually.', mail_sent=False)

    token = generate_invite_token(to_email, to_name)
    audit_log('invite_link_generated', f'email={to_email}', username=user_id, ip=get_client_ip())
    return jsonify(ok=True, link=f'{base}/register?token={token}',
                   message=f'Link generated for {to_email}', mail_sent=False, manual=True)


@api_bp.route('/admin/bulk-create-users', methods=['POST'])
@jwt_required()
def api_admin_bulk_create_users():
    """Admin: create multiple user accounts from a name+email list."""
    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403

    import re, string
    from services.auth import create_user, get_all_users, update_user_documents_handled
    from services.email import send_credentials_email
    from services.misc import audit_log
    from utils import get_client_ip
    from config import APP_URL, MAIL_ENABLED

    data       = request.get_json(force=True, silent=True) or {}
    users_data = data.get('users', [])
    role       = data.get('role', 'staff')
    office     = data.get('office', '').strip()

    if not isinstance(users_data, list) or not users_data:
        return jsonify(error='users list is required'), 400
    if role not in ('admin', 'staff', 'client'):
        role = 'staff'

    def _make_username(name: str, taken: set) -> str:
        base = re.sub(r'[^a-z0-9]', '.', name.strip().lower())
        base = re.sub(r'\.{2,}', '.', base).strip('.') or 'user'
        cand, sfx = base, 2
        while cand in taken:
            cand = f'{base}{sfx}'; sfx += 1
        return cand

    def _make_password() -> str:
        alpha = string.ascii_letters + string.digits
        pw = [secrets.choice(string.digits), secrets.choice(string.ascii_uppercase),
              *[secrets.choice(alpha) for _ in range(10)]]
        for j in range(len(pw) - 1, 0, -1):
            k = secrets.randbelow(j + 1); pw[j], pw[k] = pw[k], pw[j]
        return ''.join(pw)

    all_users = get_all_users()
    taken     = {u['username'].lower() for u in all_users}
    by_email  = {u.get('email', '').strip().lower(): u for u in all_users if u.get('email', '').strip()}
    base      = (APP_URL or '').rstrip('/')
    results   = []

    for item in users_data:
        full_name = (item.get('full_name') or item.get('name') or '').strip()
        email     = (item.get('email') or '').strip()
        raw_docs  = item.get('documents_handled', [])
        doc_types = ([d.strip() for d in raw_docs.split(',') if d.strip()]
                     if isinstance(raw_docs, str) else list(raw_docs))

        if not email:
            continue

        # Update existing user if email already known
        if email.lower() in by_email:
            existing = by_email[email.lower()]
            uname = existing['username']
            if doc_types:
                update_user_documents_handled(uname, doc_types)
            results.append({'username': uname, 'full_name': existing.get('full_name') or full_name,
                            'email': email, 'ok': True, 'updated': True,
                            'email_sent': False, 'msg': 'Updated existing user'})
            continue

        uname   = _make_username(full_name or email.split('@')[0], taken)
        taken.add(uname)
        temp_pw = _make_password()

        ok, err = create_user(uname, temp_pw, full_name, role=role, email=email,
                              office=office, documents_handled=doc_types or None)
        if not ok:
            results.append({'username': uname, 'full_name': full_name, 'email': email,
                            'ok': False, 'updated': False, 'msg': err})
            continue

        email_sent, email_err = False, 'Email not configured'
        if email and MAIL_ENABLED:
            email_sent, email_err = send_credentials_email(email, full_name, uname, temp_pw, base)

        results.append({
            'username': uname, 'full_name': full_name, 'email': email,
            'ok': True, 'updated': False,
            'password': temp_pw if not email_sent else None,
            'email_sent': email_sent,
            'msg': '' if email_sent else (email_err or ''),
        })

    ok_count = sum(1 for r in results if r['ok'])
    audit_log('bulk_users_created', f'total={len(results)} ok={ok_count}',
              username=user_id, ip=get_client_ip())
    return jsonify(results=results, total=len(results), created=ok_count), 201


# ── Admin: Batch document assign ───────────────────────────────────────────────

@api_bp.route('/admin/assign-doc-batch', methods=['POST'])
@jwt_required()
def api_admin_assign_doc_batch():
    """Admin: assign multiple documents to a staff member."""
    from services.auth import get_all_users
    from services.misc import audit_log
    from utils import get_client_ip

    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403

    data = request.get_json(force=True, silent=True) or {}
    doc_ids = data.get('doc_ids', [])
    staff_username = (data.get('staff_username') or '').strip()

    if not isinstance(doc_ids, list) or not doc_ids:
        return jsonify(error='doc_ids must be a non-empty list'), 400
    if not staff_username:
        return jsonify(error='staff_username is required'), 400

    all_users = get_all_users()
    staff_user = next((u for u in all_users if u.get('username') == staff_username), None)
    if not staff_user:
        return jsonify(error=f'Staff user "{staff_username}" not found'), 404

    assigned = 0
    for doc_id in doc_ids:
        doc = get_doc(doc_id)
        if not doc or doc.get('deleted'):
            continue
        doc['logged_by'] = staff_username
        if not doc.get('original_logged_by'):
            doc['original_logged_by'] = staff_username
        save_doc(doc)
        assigned += 1

    audit_log('doc_batch_assigned', f'assigned {assigned} docs to {staff_username}',
              username=user_id, ip=get_client_ip())
    return jsonify(success=True, assigned=assigned, staff=staff_username)


# ── Admin: Batch delete unassigned docs ────────────────────────────────────────

@api_bp.route('/admin/delete-unassigned-batch', methods=['POST'])
@jwt_required()
def api_admin_delete_unassigned_batch():
    """Admin: delete unassigned documents (all or selected)."""
    from services.misc import audit_log
    from utils import get_client_ip

    user_id = get_jwt_identity()
    if not _is_admin_user(user_id):
        return jsonify(error='Admin access required'), 403

    data = request.get_json(force=True, silent=True) or {}
    doc_ids = data.get('doc_ids', [])
    delete_all = bool(data.get('delete_all', False))

    deleted = 0

    if delete_all:
        docs = load_docs()
        for doc in docs:
            if doc.get('deleted'):
                continue
            if not doc.get('logged_by') and not doc.get('original_logged_by') and not doc.get('submitted_by'):
                doc['deleted'] = True
                save_doc(doc)
                deleted += 1
        audit_log('unassigned_docs_deleted_all', f'deleted_count={deleted}',
                  username=user_id, ip=get_client_ip())
    else:
        if not isinstance(doc_ids, list) or not doc_ids:
            return jsonify(error='doc_ids must be a non-empty list when delete_all is false'), 400
        for doc_id in doc_ids:
            doc = get_doc(doc_id)
            if not doc or doc.get('deleted'):
                continue
            if not doc.get('logged_by') and not doc.get('original_logged_by') and not doc.get('submitted_by'):
                doc['deleted'] = True
                save_doc(doc)
                deleted += 1
        audit_log('unassigned_docs_deleted_selected', f'deleted_count={deleted}',
                  username=user_id, ip=get_client_ip())

    return jsonify(success=True, deleted=deleted)


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
    from config import STATUS_OPTIONS
    if not status or status not in STATUS_OPTIONS:
        return jsonify(error=f'Invalid status. Must be one of: {STATUS_OPTIONS}'), 400
    remarks = data.get('remarks', '').strip()
    if not doc_ids:
        return jsonify(error='doc_ids is required'), 400
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
            if status == 'Received' and not doc.get('date_received'):
                doc['date_received'] = ts[:16].replace('T', ' ')
            if status == 'Released' and not doc.get('date_released'):
                doc['date_released'] = ts[:16].replace('T', ' ')
            doc.setdefault('travel_log', []).append({
                'office':    office,
                'action':    f'Bulk update → {status}',
                'officer':   actor,
                'timestamp': ts,
                'remarks':   remarks or f'Bulk status update to {status}.',
            })
            save_doc(doc)
            from services.misc import audit_log
            from utils import get_client_ip
            audit_log('bulk_status_updated',
                      f'doc_id={did} new_status={status}',
                      username=user_id, ip=get_client_ip())
            updated += 1
    return jsonify(message=f'{updated} document(s) updated to {status}', updated=updated)


@api_bp.route('/documents/bulk-transfer', methods=['POST'])
@jwt_required()
def api_bulk_transfer():
    """Staff/Admin: transfer/route multiple documents to another staff member."""
    user_id = get_jwt_identity()
    user_obj = get_user_by_username(user_id)
    user_role = (user_obj.get('role', '') if user_obj else '')
    is_admin = _is_admin_user(user_id) or user_role in ('admin', 'superadmin')
    if not is_admin and user_role != 'staff':
        return jsonify(error='Staff access required'), 403

    data          = request.get_json(force=True, silent=True) or {}
    doc_ids       = data.get('doc_ids', [])
    new_staff     = (data.get('new_staff', '') or '').strip()
    transfer_type = (data.get('transfer_type', 'inside_office') or 'inside_office').strip()
    remarks       = (data.get('remarks', '') or '').strip()

    if not doc_ids:
        return jsonify(error='doc_ids is required'), 400
    if not new_staff:
        return jsonify(error='new_staff is required'), 400
    if transfer_type not in ('inside_office', 'outside_office'):
        return jsonify(error='transfer_type must be inside_office or outside_office'), 400
    if new_staff == user_id:
        return jsonify(error='Cannot transfer to yourself'), 400

    from services.auth import get_all_users
    all_users   = get_all_users()
    valid_staff = [u['username'] for u in all_users if u.get('role') != 'client']
    if new_staff not in valid_staff:
        return jsonify(error='Invalid staff member'), 400

    new_staff_office     = ''
    new_staff_full_name  = ''
    actor                = (user_obj.get('full_name') or user_id) if user_obj else user_id
    for u in all_users:
        if u.get('username') == new_staff:
            new_staff_office    = u.get('office', '')
            new_staff_full_name = u.get('full_name', '') or new_staff
            break

    status_note       = '(Inside Office)' if transfer_type == 'inside_office' else '(Outside Office)'
    id_list           = doc_ids[:50]
    transferred_count = 0
    skipped_count     = 0
    ts = now_str()

    for did in id_list:
        doc = get_doc(did)
        if not doc or doc.get('deleted'):
            skipped_count += 1
            continue

        can_transfer = (
            is_admin or
            doc.get('logged_by') == user_id or
            doc.get('original_logged_by') == user_id or
            doc.get('accepted_by') == user_id
        )
        if not can_transfer:
            skipped_count += 1
            continue

        original_logger = doc.get('original_logged_by', doc.get('logged_by', ''))
        cycle           = doc.get('routing_cycle', 0)

        if not doc.get('original_logged_by'):
            doc['original_logged_by'] = doc.get('logged_by', user_id)

        routing_back = (new_staff == original_logger)
        if routing_back:
            doc['routing_cycle'] = cycle + 1
            action_label = f"Batch Re-routed to Originating Staff (Cycle {doc['routing_cycle']})"
        else:
            action_label = f"Batch {'Transferred' if transfer_type == 'inside_office' else 'Routed'} — {status_note} (Cycle {cycle + 1})"

        doc['status']                = 'Transferred' if transfer_type == 'inside_office' else 'Routed'
        doc['transferred_to']        = new_staff
        doc['transferred_to_office'] = new_staff_office
        doc['transferred_by']        = user_id
        doc['transferred_at']        = ts
        doc['transfer_type']         = transfer_type
        doc['pending_at_staff']      = new_staff
        doc['pending_at_office']     = new_staff_office
        doc['pending_at_staff_name'] = new_staff_full_name
        doc['transfer_status']       = 'pending'
        doc['updated_at']            = ts
        doc['updated_by']            = user_id

        doc.setdefault('travel_log', []).append({
            'office':    new_staff_office or 'DepEd Leyte Division Office',
            'action':    action_label,
            'officer':   actor,
            'timestamp': ts,
            'remarks':   remarks or (
                f"Batch re-routed back to originating staff. Cycle {doc['routing_cycle']} completed."
                if routing_back else
                f"Batch routed from {user_id} → {new_staff} at {new_staff_office or 'N/A'} {status_note}."
            ),
        })
        save_doc(doc)
        transferred_count += 1

    from services.misc import audit_log
    from utils import get_client_ip
    audit_log('doc_batch_transferred',
              f'count={transferred_count} to={new_staff} type={transfer_type}',
              username=user_id, ip=get_client_ip())

    return jsonify(
        message=f'{transferred_count} document(s) transferred to {new_staff_full_name}.',
        transferred=transferred_count,
        skipped=skipped_count,
    )


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
    user_id = get_jwt_identity()
    is_admin = _is_admin_user(user_id)
    if not is_admin:
        user = get_user_by_username(user_id)
        user_role = user.get('role', '') if user else ''
        if user_role != 'staff':
            return jsonify(error='Staff or admin access required'), 403
    from services.documents import load_docs
    office = request.args.get('office', '').strip()
    docs   = load_docs()
    if not is_admin:
        docs = [d for d in docs if d.get('logged_by') == user_id]
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
    office    = data.get('office', '').strip()
    if not username or not password or not full_name:
        return jsonify(error='username, password, and full_name are required'), 400
    if not office:
        return jsonify(error='office is required'), 400
    if len(password) < 8:
        return jsonify(error='Password must be at least 8 characters'), 400
    from services.auth import get_user as _get_u, create_user as _create_u
    if _get_u(username):
        return jsonify(error='Username already taken'), 409
    success, msg = _create_u(
        username=username, full_name=full_name,
        password=password, role='client',
        office=office, email=email,
    )
    if not success:
        return jsonify(error=msg or 'Registration failed'), 400
    # Notify admin — never block registration if email fails
    try:
        from config import MAIL_ENABLED
        from services.email import send_admin_notification
        if MAIL_ENABLED:
            send_admin_notification(
                subject='New Client Registration — Pending Approval',
                body=(
                    f'A new client has registered and is awaiting your approval.\n\n'
                    f'Name:     {full_name}\n'
                    f'Username: {username}\n'
                    f'Email:    {email or "not provided"}\n\n'
                    f'Login to LAKAD to approve or reject this account:\n'
                    f'/pending-clients'
                )
            )
    except Exception:
        pass
    # Push notification to all admin users
    try:
        from services.auth import get_all_users
        for _admin in get_all_users():
            if _admin.get('role') == 'admin' and _admin.get('username'):
                send_push_notification(
                    username=_admin['username'],
                    title='New Client Registration',
                    body=f'{full_name} (@{username}) has registered and is awaiting approval.',
                    data={'screen': '/pending-clients', 'type': 'pending_client'},
                )
    except Exception:
        pass  # never block registration
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
        from services.misc import audit_log
        from utils import get_client_ip
        audit_log(
            'doc_submitted',
            f"ref={doc.get('doc_id','')} doc_name={doc.get('doc_name','')[:80]} submitted_by={user_id}",
            username=user_id,
            ip=get_client_ip()
        )
        submitted.append({'id': doc['id'], 'doc_id': doc['doc_id'], 'doc_name': doc_name, 'status': 'Pending'})

    return jsonify(serialize({'submitted': submitted, 'count': len(submitted)})), 201


@api_bp.route('/client/documents/<doc_id>', methods=['DELETE'])
@jwt_required()
def api_client_delete_document(doc_id):
    """Client: soft-delete their own PENDING or REJECTED document (moves to trash)."""
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    if not user or user.get('role') != 'client':
        return jsonify(error='Client access required'), 403
    doc = get_doc(doc_id)
    if not doc:
        return jsonify(error='Document not found'), 404
    if doc.get('logged_by') != user_id and doc.get('submitted_by') != user_id:
        return jsonify(error='You can only delete your own documents'), 403
    status = (doc.get('status') or '').lower()
    if status not in ('rejected', 'pending'):
        return jsonify(error='You can only cancel pending documents or delete rejected documents'), 400
    from services.documents import delete_doc
    delete_doc(doc_id, user_id)
    message = 'Submission cancelled' if status == 'pending' else 'Document moved to trash'
    return jsonify(message=message)


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


@api_bp.route('/client/submit-mobile', methods=['POST'])
@jwt_required()
def api_client_submit_mobile():
    user_id = get_jwt_identity()
    user = get_user_by_username(user_id)
    if not user or user.get('role') != 'client':
        return jsonify(error='Forbidden'), 403

    data = request.get_json(force=True, silent=True) or {}
    office_slug = (data.get('office_slug') or '').strip().lower()
    office_name = (data.get('office_name') or '').strip()
    selected_staff = (data.get('selected_staff') or '').strip()
    items = data.get('items') or []

    if not office_slug and not office_name:
        return jsonify(error='Office is required'), 400
    if not items:
        return jsonify(error='No documents to submit'), 400
    if len(items) > 50:
        return jsonify(error='Maximum 50 documents per submission'), 400

    from services.auth import get_all_users
    all_users = get_all_users()

    assigned_staff = ''
    assigned_staff_name = ''

    if selected_staff:
        for u in all_users:
            if u.get('username') == selected_staff:
                assigned_staff = selected_staff
                assigned_staff_name = u.get('full_name') or u.get('username', '')
                break

    if not assigned_staff:
        from services.misc import load_saved_offices
        saved_offices = load_saved_offices()
        primary_recipient = ''
        for off in saved_offices:
            if (off.get('office_slug', '').lower() == office_slug or
                    off.get('office_name', '').strip().lower() == office_name.strip().lower()):
                primary_recipient = off.get('primary_recipient', '')
                break
        if primary_recipient:
            for u in all_users:
                if u.get('username') == primary_recipient:
                    assigned_staff = primary_recipient
                    assigned_staff_name = u.get('full_name') or u.get('username', '')
                    break

    if not assigned_staff:
        office_staff = [
            u for u in all_users
            if u.get('office', '').strip().lower() == office_name.strip().lower()
            and u.get('role') in ('staff', 'admin')
        ]
        if not office_staff:
            office_staff = [u for u in all_users if u.get('role') in ('staff', 'admin')]
        if office_staff:
            assigned_staff = office_staff[0].get('username', '')
            assigned_staff_name = office_staff[0].get('full_name') or office_staff[0].get('username', '')

    submitted = []
    sender_name = user.get('full_name') or user_id

    for item in items[:50]:
        doc_name             = (item.get('doc_name') or '').strip()
        unit_office          = (item.get('unit_office') or '').strip()
        referred_to          = (item.get('referred_to') or '').strip()
        referred_to_username = (item.get('referred_to_username') or '').strip()
        if not doc_name or not unit_office or not referred_to:
            continue

        doc = {
            'id':                    str(uuid.uuid4())[:8].upper(),
            'doc_id':                generate_ref(),
            'doc_name':              doc_name,
            'category':              (item.get('category') or '').strip(),
            'description':           (item.get('description') or '').strip(),
            'sender_name':           sender_name,
            'sender_org':            unit_office,
            'sender_contact':        '',
            'referred_to':           referred_to or office_name,
            'forwarded_to':          '',
            'recipient_name':        '',
            'recipient_org':         '',
            'recipient_contact':     '',
            'received_by':           '',
            'date_received':         '',
            'date_released':         '',
            'doc_date':              now_str()[:10],
            'status':                'Pending',
            'notes':                 (item.get('notes') or '').strip(),
            'created_at':            now_str(),
            'routing':               [],
            'travel_log':            [],
            'submitted_by':          user_id,
            'submitted_by_name':     sender_name,
            'target_office_slug':    office_slug,
            'target_office_name':    office_name,
            'pending_at_staff':      assigned_staff,
            'pending_at_staff_name': assigned_staff_name,
            'pending_at_office':     office_name,
            'transfer_status':       'pending' if (assigned_staff or office_name) else '',
            'intended_for_username': referred_to_username,
            'intended_for_name':     next(
                (u.get('full_name') or u.get('username') for u in all_users
                 if u.get('username') == referred_to_username),
                ''
            ),
        }
        doc['travel_log'].append({
            'office':    office_name or unit_office or 'Client',
            'action':    'Document Submitted by Client - Pending at ' + (assigned_staff_name or assigned_staff or 'Office'),
            'officer':   sender_name,
            'timestamp': doc['created_at'],
            'remarks':   (
                f'Submitted via mobile app. '
                f'Target office: {office_name or "General"}. '
                f'Assigned to: {assigned_staff_name or assigned_staff or "Any staff"}.'
            ),
        })
        insert_doc(doc)
        submitted.append({'id': doc['id'], 'doc_id': doc['doc_id'], 'doc_name': doc['doc_name']})

    if not submitted:
        return jsonify(error='No valid documents in submission — check required fields'), 400

    return jsonify(submitted=submitted, count=len(submitted))


def send_push_notification(username: str, title: str, body: str, data: dict = None):
    """Send push notification to a specific user via Expo Push API.
    Never raises — always returns False on any failure."""
    try:
        if data is None:
            data = {}
        import requests as req

        _ensure_push_tokens_loaded()
        with _push_tokens_lock:
            token = _push_tokens.get(username)
        if not token:
            return False

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