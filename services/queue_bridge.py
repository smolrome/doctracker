import os
import requests
from typing import Optional

QUEUE_API_URL = os.environ.get('QUEUE_API_URL', 'http://localhost:7003')
QUEUE_API_KEY = os.environ.get('QUEUE_EXTERNAL_API_KEY', '')

HEADERS = {
    'Content-Type': 'application/json',
    'X-API-Key': QUEUE_API_KEY,
}


def get_queue_services() -> list:
    """Fetch available services from the Queuing System."""
    try:
        r = requests.get(f'{QUEUE_API_URL}/api/external/services', headers=HEADERS, timeout=5)
        if r.ok:
            return r.json().get('services', [])
    except Exception:
        pass
    return []


def push_appointment_ticket(
    service_code: str,
    client_name: str,
    lakad_ref: str,
    appointment_id: str,
    priority: int = 1,
) -> Optional[dict]:
    """Push a pre-generated ticket to the Queuing System.
    Returns: { ticket_number, ticket_id } or None on failure.
    """
    try:
        r = requests.post(
            f'{QUEUE_API_URL}/api/external/push-ticket',
            headers=HEADERS,
            json={
                'service_code': service_code,
                'client_name': client_name,
                'lakad_ref': lakad_ref,
                'appointment_id': appointment_id,
                'priority': priority,
            },
            timeout=5,
        )
        if r.ok:
            data = r.json()
            if data.get('ok'):
                return {'ticket_number': data['ticket_number'], 'ticket_id': data['ticket_id']}
    except Exception:
        pass
    return None


def complete_appointment_ticket(ticket_id: int, appointment_id: str) -> bool:
    """Notify Queuing System that an appointment was completed."""
    try:
        r = requests.post(
            f'{QUEUE_API_URL}/api/external/complete-appointment',
            headers=HEADERS,
            json={'ticket_id': ticket_id, 'appointment_id': appointment_id},
            timeout=5,
        )
        return r.ok
    except Exception:
        return False


def is_queue_available() -> bool:
    """Check if the Queuing System is reachable."""
    try:
        r = requests.get(f'{QUEUE_API_URL}/api/external/services', headers=HEADERS, timeout=3)
        return r.ok
    except Exception:
        return False
