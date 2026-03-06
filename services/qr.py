"""
services/qr.py — QR code generation, signing, and image decoding.
Covers: office QR PNGs, document QR, doc-status tokens, QR reading via OpenCV.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from io import BytesIO

import qrcode

from config import APP_URL, QR_SIGN_SECRET, QR_SIGN_VALIDITY_DAYS
from services.database import USE_DB, get_conn
from services.documents import now_str

# ── Optional libraries ────────────────────────────────────────────────────────

try:
    import cv2
    import numpy as np
    QR_READ_OK = True
except ImportError:
    QR_READ_OK = False


# ── URL helpers ───────────────────────────────────────────────────────────────

def get_base_url(request_host_url: str = "") -> str:
    """Return the correct base URL — public domain or local network IP."""
    import socket
    if APP_URL:
        return APP_URL
    if request_host_url and "127.0.0.1" not in request_host_url and "localhost" not in request_host_url:
        return request_host_url.rstrip("/")
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        return f"http://{local_ip}:5000"
    except Exception:
        return (request_host_url or "").rstrip("/")


# ── QR URL signing ────────────────────────────────────────────────────────────

def sign_office_action(action: str) -> str:
    """Return action with expiry + HMAC signature appended."""
    expiry  = int(time.time()) + QR_SIGN_VALIDITY_DAYS * 86400
    payload = f"{action}:{expiry}"
    sig     = hmac.new(QR_SIGN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{action}?exp={expiry}&sig={sig}"


def verify_office_action(action: str, exp_str: str, sig: str) -> bool:
    try:
        expiry = int(exp_str)
        if time.time() > expiry:
            return False
        payload  = f"{action}:{expiry}"
        expected = hmac.new(QR_SIGN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        return secrets.compare_digest(expected, sig)
    except Exception:
        return False


# ── Basic document QR ─────────────────────────────────────────────────────────

def make_qr_png(doc: dict, host_url: str, box_size: int = 8) -> bytes:
    """QR that encodes the /receive/<id> URL."""
    url = f"{get_base_url(host_url)}/receive/{doc['id']}"
    return _build_simple_qr(url, box_size)


def generate_qr_b64(doc: dict, host_url: str) -> str:
    return base64.b64encode(make_qr_png(doc, host_url)).decode()


def _build_simple_qr(url: str, box_size: int = 8) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=3,
    )
    qr.add_data(url)
    qr.make(fit=True)
    buf = BytesIO()
    qr.make_image(fill_color="#0D1B2A", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


# ── QR reading (OpenCV) ───────────────────────────────────────────────────────

def decode_qr_image(file_bytes: bytes) -> tuple[str | None, str | None]:
    if not QR_READ_OK:
        return None, "QR reading library not installed. Run: pip install opencv-python Pillow numpy"
    try:
        img = cv2.imdecode(np.frombuffer(file_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None, "Could not read image file. Please upload a valid JPG or PNG."
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if not data:
            data, _, _ = detector.detectAndDecode(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        if data:
            return data, None
        return None, "No QR code found in the image. Make sure the QR code is clearly visible and not blurry."
    except Exception as e:
        return None, f"Could not read image: {e}"


def extract_doc_id_from_qr(qr_text: str) -> str | None:
    m = re.search(r'/receive/([A-Z0-9]{8})', qr_text)
    if m:
        return m.group(1)
    m = re.search(r'\b([A-Z0-9]{8})\b', qr_text)
    return m.group(1) if m else None


# ── Doc status tokens (RECEIVE / RELEASE) ────────────────────────────────────

def create_doc_token(doc_id: str, token_type: str) -> str:
    """Create a one-time RECEIVE or RELEASE token. Returns token string."""
    token = f"{token_type[:3].upper()}-{uuid.uuid4().hex[:16].upper()}"
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Remove old unused token of same type for this doc
                    cur.execute(
                        "DELETE FROM doc_qr_tokens WHERE doc_id=%s AND token_type=%s AND used=FALSE",
                        (doc_id, token_type)
                    )
                    cur.execute(
                        "INSERT INTO doc_qr_tokens (token, doc_id, token_type) VALUES (%s,%s,%s)",
                        (token, doc_id, token_type)
                    )
                conn.commit()
        except Exception as e:
            print(f"create_doc_token error: {e}")
    else:
        path = "doc_qr_tokens.json"
        tokens = {}
        if os.path.exists(path):
            with open(path) as f:
                tokens = json.load(f)
        tokens[token] = {"doc_id": doc_id, "token_type": token_type, "used": False}
        with open(path, "w") as f:
            json.dump(tokens, f)
    return token


def use_doc_token(token: str) -> tuple[str | None, str | None]:
    """Validate and consume a doc QR token. Returns (doc_id, token_type) or (None, None)."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT doc_id, token_type FROM doc_qr_tokens WHERE token=%s AND used=FALSE",
                        (token,)
                    )
                    row = cur.fetchone()
                    if not row:
                        return None, None
                    cur.execute("UPDATE doc_qr_tokens SET used=TRUE WHERE token=%s", (token,))
                conn.commit()
                return row["doc_id"], row["token_type"]
        except Exception as e:
            print(f"use_doc_token error: {e}")
            return None, None
    else:
        path = "doc_qr_tokens.json"
        if not os.path.exists(path):
            return None, None
        with open(path) as f:
            tokens = json.load(f)
        t = tokens.get(token)
        if not t or t.get("used"):
            return None, None
        tokens[token]["used"] = True
        with open(path, "w") as f:
            json.dump(tokens, f)
        return t["doc_id"], t["token_type"]


def get_token_doc(token: str) -> tuple[dict | None, str | None]:
    """Look up token without consuming it. Returns (doc, token_type)."""
    if USE_DB:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT doc_id, token_type FROM doc_qr_tokens WHERE token=%s",
                        (token,)
                    )
                    row = cur.fetchone()
                    if not row:
                        return None, None
                    from services.documents import get_doc
                    return get_doc(row["doc_id"]), row["token_type"]
        except Exception as e:
            return None, None
    else:
        path = "doc_qr_tokens.json"
        if not os.path.exists(path):
            return None, None
        with open(path) as f:
            tokens = json.load(f)
        t = tokens.get(token)
        if not t:
            return None, None
        from services.documents import get_doc
        return get_doc(t["doc_id"]), t["token_type"]


# ── Labeled QR image builders ─────────────────────────────────────────────────

def make_doc_status_qr_png(token: str, token_type: str,
                            doc_name: str, box_size: int = 10) -> bytes:
    """Labeled QR PNG for RECEIVE or RELEASE tokens given to clients."""
    from PIL import Image, ImageDraw, ImageFont

    base = APP_URL or ""
    url  = f"{base}/doc-scan/{token}"

    if token_type == "RECEIVE":
        short_label = "REC"
        label_color = "#1D4ED8"
        bg_color    = "#DBEAFE"
        sub_label   = "SUBMIT TO OFFICE"
    else:
        short_label = "REL"
        label_color = "#065F46"
        bg_color    = "#D1FAE5"
        sub_label   = "PICK UP DOCUMENT"

    qr_img = _render_qr_image(url, box_size, "#0A2540")
    return _compose_labeled_png(qr_img, short_label, sub_label, doc_name,
                                label_color, bg_color, small=True)


def make_office_qr_png(action: str, host_url: str = "") -> bytes:
    """High-resolution labeled QR PNG for office stations."""
    from PIL import Image, ImageDraw, ImageFont

    base         = get_base_url(host_url)
    signed_action = sign_office_action(action)
    url          = f"{base}/office-action/{signed_action}"

    if action.endswith("-rec"):
        short_label   = "REC"
        label_color   = "#1D4ED8"
        bg_color      = "#DBEAFE"
        office_display = action[:-4].replace("-", " ").title()
        sub_label     = "RECEIVE DOCUMENT"
    elif action.endswith("-rel"):
        short_label   = "REL"
        label_color   = "#065F46"
        bg_color      = "#D1FAE5"
        office_display = action[:-4].replace("-", " ").title()
        sub_label     = "RELEASE DOCUMENT"
    elif action.endswith("-reg"):
        short_label   = "REG"
        label_color   = "#92400E"
        bg_color      = "#FEF3C7"
        office_display = action[:-4].replace("-", " ").title()
        sub_label     = "CLIENT REGISTRATION"
    elif action.endswith("-sub"):
        short_label   = "SUB"
        label_color   = "#5B21B6"
        bg_color      = "#EDE9FE"
        office_display = action[:-4].replace("-", " ").title()
        sub_label     = "SUBMIT DOCUMENT"
    else:
        short_label   = action.upper()[:3]
        label_color   = "#0A2540"
        bg_color      = "#F0F7FA"
        office_display = action.replace("-", " ").title()
        sub_label     = "OFFICE QR"

    return _build_office_qr_png(url, short_label, sub_label, office_display,
                                label_color, bg_color)


def _render_qr_image(url: str, box_size: int, fill_color: str):
    """Generate a raw PIL QR image."""
    from PIL import Image
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=3,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color=fill_color, back_color="white").convert("RGB")


def _compose_labeled_png(qr_img, short_label: str, sub_label: str,
                         doc_name: str, label_color: str,
                         bg_color: str, small: bool = False) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    qr_size = qr_img.size[0]
    bar_h, foot_h, pad = 56, 56, 12
    total_w = qr_size + pad * 2
    total_h = bar_h + qr_size + pad * 2 + foot_h

    canvas = Image.new("RGB", (total_w, total_h), "white")
    draw   = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, total_w, bar_h], fill=bg_color)

    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        font_med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        font_sm  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except Exception:
        font_big = font_med = font_sm = ImageFont.load_default()

    bb = draw.textbbox((0, 0), short_label, font=font_big)
    draw.text(
        ((total_w - (bb[2] - bb[0])) / 2, (bar_h - (bb[3] - bb[1])) / 2 - 2),
        short_label, font=font_big, fill=label_color
    )
    canvas.paste(qr_img, (pad, bar_h + pad))

    foot_y = bar_h + qr_size + pad * 2
    draw.rectangle([0, foot_y, total_w, total_h], fill=bg_color)

    bb2 = draw.textbbox((0, 0), sub_label, font=font_med)
    draw.text(((total_w - (bb2[2] - bb2[0])) / 2, foot_y + 8), sub_label,
              font=font_med, fill=label_color)

    dname = (doc_name[:28] + "…") if len(doc_name) > 28 else doc_name
    bb3   = draw.textbbox((0, 0), dname, font=font_sm)
    draw.text(((total_w - (bb3[2] - bb3[0])) / 2, foot_y + 28), dname,
              font=font_sm, fill="#5A7A91")

    draw.rectangle([0, total_h - 4, total_w, total_h], fill=label_color)

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def _build_office_qr_png(url: str, short_label: str, sub_label: str,
                          office_display: str, label_color: str,
                          bg_color: str) -> bytes:
    """High-resolution 4x supersampled office QR with large text."""
    from PIL import Image, ImageDraw, ImageFont

    SCALE  = 4
    QR_PX  = 420
    PAD    = 20
    BAR_H  = 110
    FOOT_H = 140

    qr_raw = _render_qr_image(url, box_size=10, fill_color="#0A2540")
    qr_img = qr_raw.resize((QR_PX * SCALE, QR_PX * SCALE), Image.NEAREST)

    W = (QR_PX + PAD * 2) * SCALE
    H = (BAR_H + PAD + QR_PX + PAD + FOOT_H) * SCALE

    canvas = Image.new("RGB", (W, H), "white")
    draw   = ImageDraw.Draw(canvas)

    # Scale dims
    bar_h_s  = BAR_H  * SCALE
    foot_h_s = FOOT_H * SCALE
    pad_s    = PAD    * SCALE

    BOLD_FONTS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
    ]
    REG_FONTS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    ]

    def load_font(bold: bool, size: int):
        for p in (BOLD_FONTS if bold else REG_FONTS):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
        return None

    def draw_centered(draw, text, font, y, fill, canvas_w):
        if font is None:
            return y
        bb = draw.textbbox((0, 0), text, font=font)
        draw.text(((canvas_w - (bb[2] - bb[0])) / 2, y), text, font=font, fill=fill)
        return y + (bb[3] - bb[1])

    font_top    = load_font(True,  200)
    font_office = load_font(True,  168)
    font_type   = load_font(False, 136)

    # Top bar
    draw.rectangle([0, 0, W, bar_h_s], fill=bg_color)
    draw.rectangle([0, 0, W, 10 * SCALE], fill=label_color)
    if font_top:
        bb   = draw.textbbox((0, 0), short_label, font=font_top)
        draw.text(((W - (bb[2] - bb[0])) / 2, (bar_h_s - (bb[3] - bb[1])) / 2),
                  short_label, font=font_top, fill=label_color)

    # QR
    canvas.paste(qr_img, (pad_s, bar_h_s + pad_s))

    # Footer
    foot_y_s = bar_h_s + pad_s + QR_PX * SCALE + pad_s
    draw.rectangle([0, foot_y_s, W, foot_y_s + 8 * SCALE], fill=bg_color)

    # Truncate office name if too wide
    office_text = office_display
    if font_office:
        while True:
            bb = draw.textbbox((0, 0), office_text, font=font_office)
            if (bb[2] - bb[0]) <= W - 40 * SCALE or len(office_text) < 5:
                break
            office_text = office_text[:-4] + "…"

    inner_y = foot_y_s + 8 * SCALE + 20 * SCALE
    inner_y = draw_centered(draw, office_text, font_office, inner_y, "#0A2540", W)
    inner_y += 12 * SCALE
    draw_centered(draw, sub_label, font_type, inner_y, label_color, W)

    draw.rectangle([0, H - 10 * SCALE, W, H], fill=label_color)

    # Downsample to 1x
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = getattr(Image, "LANCZOS", Image.ANTIALIAS)

    final = canvas.resize((W // SCALE, H // SCALE), resample)
    buf   = BytesIO()
    final.save(buf, format="PNG")
    return buf.getvalue()
