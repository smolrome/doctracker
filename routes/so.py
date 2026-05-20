"""
routes/so.py — Special Order document generation routes.
Staff and admin only. Loads so_templates/S_O_TEMP.docx, fills the 5 placeholders,
saves to so_output/, and returns a download link.
"""
import os
import re
from datetime import datetime

from flask import (Blueprint, flash, jsonify, redirect,
                   render_template, request, send_file, session, url_for)

from utils import get_client_ip, login_required

so_bp = Blueprint("so", __name__)

TEMPLATE_PATH = os.path.join("so_templates", "S_O_TEMP.docx")

import socket as _socket
_IS_SERVER = os.path.exists('/home/itpersonnelunit/so_documents')

def _get_output_dir(so_type: str) -> str:
    if _IS_SERVER:
        year = datetime.now().strftime('%Y')
        path = f"/home/itpersonnelunit/so_documents/{year}/{so_type}"
    else:
        path = os.path.join("so_output", so_type)
    os.makedirs(path, exist_ok=True)
    return path

# ── SO type registry ────────────────────────────────────────────────────────────
# Each entry: label, subject line, list of dynamic field keys, body template.
# Body template uses str.format() — {employee_full_name} and {employee_position}
# are always available; all keys in "fields" must be supplied by the request.

SO_TYPES = {
    "assignment_order": {
        "label":   "Assignment Order",
        "subject": "ASSIGNMENT ORDER",
        "fields":  ["assigned_school", "assigned_district", "assigned_municipality", "effective_date"],
        "body": (
            "In the exigency of the service, you are hereby assigned at "
            "{assigned_school}, {assigned_district}, {assigned_municipality}, Leyte "
            "effective {effective_date} or upon receipt thereof.\n\n"
            "For your information, proper guidance, and strict compliance."
        ),
    },
    "designation_new": {
        "label":   "Designation — New",
        "subject": "DESIGNATION ORDER",
        "fields":  ["designation_role", "school_name", "municipality",
                    "effective_condition", "validity_condition"],
        "body": (
            "In the exigency and best interest of the service, you are hereby designated as "
            "{designation_role} of {school_name}, {municipality}, Leyte effective "
            "{effective_condition}.\n\n"
            "This order is valid {validity_condition}, subject to the request for renewal and "
            "subsequent approval of the Superintendent.\n\n"
            "For your information, proper guidance, and strict compliance."
        ),
    },
    "designation_renewal": {
        "label":   "Designation — Renewal",
        "subject": "RENEWAL OF DESIGNATION",
        "fields":  ["honorific", "designation_role", "school_name", "district", "municipality",
                    "effective_date", "accountability_amount_figures",
                    "accountability_amount_words", "school_year"],
        "body": (
            "With reference to the Approved Plotting for Designation and in the exigency and "
            "best interest of the service, this office renews the designation of "
            "{honorific} {employee_full_name} as {designation_role} of {school_name}, "
            "{district}, {municipality}, Leyte effective {effective_date} or upon receipt "
            "thereof.\n\n"
            "The amount accountability entrusted to the SDO amounting to "
            "<<bold>>{accountability_amount_words}<</bold>> (<<bold>>{accountability_amount_figures}<</bold>>).\n\n"
            "This order is valid for School Year {school_year} only, subject to the request "
            "for renewal and subsequent approval of the Superintendent.\n\n"
            "For your information, proper guidance, and strict compliance."
        ),
    },
    "detailment": {
        "label":   "Detailment",
        "subject": "DETAIL ORDER",
        "fields":  ["honorific", "previous_so_number", "previous_so_year",
                    "from_school", "from_municipality",
                    "to_school", "to_municipality",
                    "effective_date", "school_year"],
        "body": (
            "With reference to the previous Approved Special Order No. {previous_so_number} "
            "s. {previous_so_year} and in the exigency of the service, this office renews the "
            "detail order of {honorific} {employee_full_name} from {from_school}, "
            "{from_municipality}, Leyte to {to_school}, {to_municipality}, Leyte "
            "effective {effective_date}.\n\n"
            "Further, this Order is valid for School Year {school_year}, subject to request "
            "for renewal and subsequent approval of the Superintendent.\n\n"
            "For your information, proper guidance, and strict compliance."
        ),
    },
    "realignment": {
        "label":   "Realignment",
        "subject": "REALIGNMENT",
        "fields":  ["from_school", "from_municipality",
                    "to_school", "to_municipality",
                    "effective_date", "monthly_salary", "nosca_number", "item_note"],
        "body": (
            "Approval is hereby given to the transfer of {employee_position} with "
            "his/her monthly salary, status and effective date:\n\n"
            "Name: {employee_full_name}\n"
            "From: {from_school}, {from_municipality}, LEYTE\n"
            "To: {to_school}, {to_municipality}, LEYTE\n"
            "Effective Date: {effective_date}\n"
            "Salary: P {monthly_salary}\n"
            "Mode of Transfer: REALIGNMENT (NOSCA NO. {nosca_number})\n"
            "Note: {item_note}"
        ),
    },
    "reassignment": {
        "label":   "Reassignment",
        "subject": "REASSIGNMENT",
        "fields":  ["from_school", "from_district", "from_municipality",
                    "to_school", "to_district", "to_municipality",
                    "new_role", "effective_date"],
        "body": (
            "In the exigency and best interest of the service, you are hereby reassigned from "
            "{from_school}, {from_district}, {from_municipality}, Leyte to "
            "{to_school}, {to_district}, {to_municipality}, Leyte as {new_role} "
            "effective {effective_date} or upon receipt thereof.\n\n"
            "Further, this order is subject to the necessary clearance from any money, property "
            "and work-related accountabilities from your previous station before assuming in "
            "your new station.\n\n"
            "For your information, proper guidance, and strict compliance."
        ),
    },
    "resignation": {
        "label":   "Resignation / Termination",
        "subject": "TERMINATION OF SERVICES",
        "fields":  ["school_name", "municipality",
                    "termination_effective_date", "termination_reason"],
        "body": (
            "The services of {employee_full_name}, {employee_position} of "
            "{school_name}, {municipality}, Leyte is hereby TERMINATED effective "
            "{termination_effective_date}, due to {termination_reason}.\n\n"
            "For your information, proper guidance, and strict compliance."
        ),
    },
    "revocation": {
        "label":   "Revocation of Special Order",
        "subject": "REVOCATION OF SPECIAL ORDER",
        "fields":  ["so_number_revoked", "so_year_revoked", "designation_revoked",
                    "school_name", "district", "municipality"],
        "body": (
            "In the exigency of the service, Special Order No. {so_number_revoked} "
            "s. {so_year_revoked} Designated as {designation_revoked} of "
            "{school_name}, {district} {municipality}, Leyte is hereby REVOKED.\n\n"
            "This Order shall take effect immediately.\n\n"
            "For your information, proper guidance, and strict compliance."
        ),
    },
    "shared_services": {
        "label":   "Shared Services",
        "subject": "SHARED SERVICES",
        "fields":  ["assigned_office", "assigned_location",
                    "period_from", "period_to", "days_per_week",
                    "purpose_description", "calendar_year"],
        "body": (
            "In the exigency of the service, you are hereby assigned at the "
            "{assigned_office}, {assigned_location} from {period_from} to {period_to}, "
            "for {days_per_week} days per week.\n\n"
            "Further, you shall assist in the {purpose_description} for Calendar Year "
            "{calendar_year}.\n\n"
            "For your information, proper guidance, and strict compliance."
        ),
    },
    "transfer_of_agency": {
        "label":   "Transfer of Agency",
        "subject": "TRANSFER OF AGENCY",
        "fields":  ["to_agency_name", "to_agency_location", "effective_date"],
        "body": (
            "Approval is hereby given to the transfer of {employee_full_name} "
            "{employee_position} of DepEd Leyte Division to the "
            "{to_agency_name}, {to_agency_location} effective {effective_date}.\n\n"
            "For your information, proper guidance, and strict compliance."
        ),
    },
    "transfer_of_station": {
        "label":   "Transfer of Station",
        "subject": "TRANSFER OF STATION ASSIGNMENT",
        "fields":  ["agreement_basis", "from_school", "from_municipality",
                    "to_school", "to_municipality", "effective_date"],
        "body": (
            "With reference to the {agreement_basis} and in the exigency of the service, "
            "you are hereby reassigned from {from_school}, {from_municipality}, Leyte to "
            "{to_school}, {to_municipality}, Leyte effective on {effective_date}.\n\n"
            "Further, this Order is subject to the necessary clearance from any money, "
            "property, and work-related accountabilities from your previous station before "
            "assuming office in your new station.\n\n"
            "For your information, proper guidance, and strict compliance."
        ),
    },
    "transfer_of_station_with_designation": {
        "label":   "Transfer of Station with Designation",
        "subject": "TRANSFER OF STATION ASSIGNMENT WITH DESIGNATION",
        "fields":  ["from_school", "from_district", "from_municipality",
                    "to_district", "to_municipality", "new_role", "effective_date"],
        "body": (
            "In the exigency of the service, you are hereby reassigned from "
            "{from_school}, {from_district}, {from_municipality}, Leyte to "
            "{to_district}, {to_municipality}, Leyte and shall serve as {new_role} of "
            "{to_district}, {to_municipality}, Leyte effective {effective_date} or upon "
            "receipt thereof.\n\n"
            "Further, this Order is subject to the necessary clearance from any money, "
            "property, and work-related accountabilities from your previous station before "
            "assuming office in your new station.\n\n"
            "For your information, proper guidance, and strict compliance."
        ),
    },
}

FIELD_LABELS = {
    "assigned_school":               "Assigned School",
    "assigned_district":             "District",
    "assigned_municipality":         "Municipality",
    "effective_date":                "Effective Date",
    "designation_role":              "Designation Role",
    "school_name":                   "School Name",
    "municipality":                  "Municipality",
    "effective_condition":           "Effective Condition",
    "validity_condition":            "Validity Condition",
    "honorific":                     "Honorific (Ms./Mr./Dr.)",
    "district":                      "District",
    "accountability_amount_words":   "Accountability Amount (in words)",
    "accountability_amount_figures": "Accountability Amount (in figures)",
    "school_year":                   "School Year (e.g. 2026-2027)",
    "previous_so_number":            "Previous SO Number",
    "previous_so_year":              "Previous SO Year",
    "from_school":                   "From School",
    "from_municipality":             "From Municipality",
    "to_school":                     "To School",
    "to_municipality":               "To Municipality",
    "from_district":                 "From District",
    "to_district":                   "To District",
    "new_role":                      "New Role / Designation",
    "monthly_salary":                "Monthly Salary (PHP)",
    "nosca_number":                  "NOSCA Number",
    "item_note":                     "Item Note",
    "termination_effective_date":    "Termination Effective Date",
    "termination_reason":            "Reason for Termination",
    "so_number_revoked":             "SO Number to Revoke",
    "so_year_revoked":               "SO Year",
    "designation_revoked":           "Designation Being Revoked",
    "assigned_office":               "Assigned Office",
    "assigned_location":             "Location",
    "period_from":                   "Period From",
    "period_to":                     "Period To",
    "days_per_week":                 "Days Per Week",
    "purpose_description":           "Purpose / Task Description",
    "calendar_year":                 "Calendar Year",
    "to_agency_name":                "Destination Agency Name",
    "to_agency_location":            "Agency Location",
    "agreement_basis":               "Agreement Basis (e.g. Approved Swapping Agreement)",
}

# Maps category dropdown values (lowercased) to SO_TYPES keys
CATEGORY_TO_SO_TYPE = {
    "assignment order":                      "assignment_order",
    "designation — new":                     "designation_new",
    "designation — renewal":                 "designation_renewal",
    "detailment":                            "detailment",
    "realignment":                           "realignment",
    "reassignment":                          "reassignment",
    "resignation / termination":             "resignation",
    "revocation of special order":           "revocation",
    "shared services":                       "shared_services",
    "transfer of agency":                    "transfer_of_agency",
    "transfer of station":                   "transfer_of_station",
    "transfer of station with designation":  "transfer_of_station_with_designation",
}

# Official SO category names shown in the document type dropdown
SO_CATEGORIES = [
    "Assignment Order",
    "Designation — New",
    "Designation — Renewal",
    "Detailment",
    "Realignment",
    "Reassignment",
    "Resignation / Termination",
    "Revocation of Special Order",
    "Shared Services",
    "Transfer of Agency",
    "Transfer of Station",
    "Transfer of Station with Designation",
]

# Fields that render as date pickers
_DATE_FIELDS = {"effective_date", "termination_effective_date", "period_from", "period_to"}


# ── Date formatter ──────────────────────────────────────────────────────────────

_MONTHS = ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


def _fmt_date(s: str) -> str:
    """Convert ISO date '2026-05-11' → 'May 11, 2026'. Passes other strings through."""
    try:
        d = datetime.strptime(s.strip(), "%Y-%m-%d")
        return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"
    except (ValueError, AttributeError):
        return s


# ── python-docx placeholder helpers ────────────────────────────────────────────

def _apply_run_fmt(run, bold=None, font_name=None, font_size_pt=None):
    """Apply font formatting to a single run without touching anything else."""
    from docx.shared import Pt
    if font_name is not None:
        run.font.name = font_name
    if font_size_pt is not None:
        run.font.size = Pt(font_size_pt)
    if bold is not None:
        run.bold = bold


def _replace_in_para_list(paras, placeholder, value, bold=None, font_name=None, font_size_pt=None):
    for para in paras:
        if placeholder not in para.text:
            continue
        runs = para.runs
        if not runs:
            continue
        # Find the specific run containing the placeholder
        for run in runs:
            if placeholder in run.text:
                # Replace only in this run — preserves label runs untouched
                run.text = run.text.replace(placeholder, value)
                _apply_run_fmt(run, bold=bold, font_name=font_name, font_size_pt=font_size_pt)
                break
        else:
            # Placeholder is split across runs — find boundary and fix
            # Put full replaced text in first run, blank the rest
            # But preserve bold=False on the prefix by splitting into two runs
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn as _qn
            prefix = para.text.split(placeholder)[0]
            runs[0].text = prefix
            runs[0].bold = False
            for run in runs[1:]:
                run.text = ""
            # Add new run for the value with correct formatting
            new_r = OxmlElement("w:r")
            new_rPr = OxmlElement("w:rPr")
            if bold:
                new_b = OxmlElement("w:b")
                new_rPr.append(new_b)
            if font_name:
                new_rFonts = OxmlElement("w:rFonts")
                new_rFonts.set(_qn("w:ascii"), font_name)
                new_rFonts.set(_qn("w:hAnsi"), font_name)
                new_rPr.append(new_rFonts)
            if font_size_pt:
                new_sz = OxmlElement("w:sz")
                new_sz.set(_qn("w:val"), str(int(font_size_pt * 2)))
                new_rPr.append(new_sz)
            new_r.append(new_rPr)
            new_t = OxmlElement("w:t")
            new_t.text = value
            new_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            new_r.append(new_t)
            runs[0]._r.addnext(new_r)


def _replace_simple(doc, placeholder, value,
                    bold=None, font_name=None, font_size_pt=None):
    """Replace a single-value placeholder everywhere in the document."""
    _replace_in_para_list(doc.paragraphs, placeholder, value,
                          bold=bold, font_name=font_name, font_size_pt=font_size_pt)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                _replace_in_para_list(cell.paragraphs, placeholder, value,
                                      bold=bold, font_name=font_name, font_size_pt=font_size_pt)


def _replace_body(doc, placeholder, body_text):
    """Replace a body placeholder, expanding double-newline blocks into numbered paragraphs."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    blocks = [b.strip() for b in body_text.split("\n\n") if b.strip()]
    for para in doc.paragraphs:
        if placeholder not in para.text:
            continue
        parent = para._p.getparent()
        idx    = list(parent).index(para._p)
        for offset, text in enumerate(blocks):
            number = offset + 1
            # Check if paragraph should be bold (wrapped in **)
            is_bold = text.startswith("**") and text.endswith("**")
            if is_bold:
                text = text[2:-2]  # strip the markers
            numbered_text = f"{number}.\t{text}"

            new_p = OxmlElement("w:p")
            new_pPr = OxmlElement("w:pPr")
            new_ind = OxmlElement("w:ind")
            new_ind.set(qn("w:left"), "1080")
            new_ind.set(qn("w:hanging"), "1080")
            new_pPr.append(new_ind)
            new_jc = OxmlElement("w:jc")
            new_jc.set(qn("w:val"), "both")
            new_pPr.append(new_jc)
            new_p.append(new_pPr)

            if "<<bold>>" in text:
                import re as _re
                parts = _re.split(r'(<<bold>>.*?<</bold>>)', text)
                for i, part in enumerate(parts):
                    is_bold_part = part.startswith("<<bold>>")
                    part_text = part.replace("<<bold>>", "").replace("<</bold>>", "")
                    if i == 0:
                        part_text = f"{number}.\t" + part_text
                    if not part_text:
                        continue
                    new_r = OxmlElement("w:r")
                    new_rPr = OxmlElement("w:rPr")
                    if is_bold_part:
                        new_rPr.append(OxmlElement("w:b"))
                    new_rFonts = OxmlElement("w:rFonts")
                    new_rFonts.set(qn("w:ascii"), "Bookman Old Style")
                    new_rFonts.set(qn("w:hAnsi"), "Bookman Old Style")
                    new_rPr.append(new_rFonts)
                    new_sz = OxmlElement("w:sz")
                    new_sz.set(qn("w:val"), "22")
                    new_rPr.append(new_sz)
                    new_szCs = OxmlElement("w:szCs")
                    new_szCs.set(qn("w:val"), "22")
                    new_rPr.append(new_szCs)
                    new_r.append(new_rPr)
                    new_t = OxmlElement("w:t")
                    new_t.text = part_text
                    new_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    new_r.append(new_t)
                    new_p.append(new_r)
            else:
                new_r = OxmlElement("w:r")
                # Run properties: Bookman Old Style, 11pt
                new_rPr = OxmlElement("w:rPr")
                if is_bold:
                    new_b = OxmlElement("w:b")
                    new_rPr.append(new_b)
                new_rFonts = OxmlElement("w:rFonts")
                new_rFonts.set(qn("w:ascii"), "Bookman Old Style")
                new_rFonts.set(qn("w:hAnsi"), "Bookman Old Style")
                new_rPr.append(new_rFonts)
                new_sz = OxmlElement("w:sz")
                new_sz.set(qn("w:val"), "22")  # 11pt = 22 half-points
                new_rPr.append(new_sz)
                new_szCs = OxmlElement("w:szCs")
                new_szCs.set(qn("w:val"), "22")
                new_rPr.append(new_szCs)
                new_r.append(new_rPr)
                new_t = OxmlElement("w:t")
                new_t.text = numbered_text
                new_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                new_r.append(new_t)
                new_p.append(new_r)

            parent.insert(idx + offset, new_p)
        parent.remove(para._p)
        break


# ── SO record persistence ───────────────────────────────────────────────────────

def _save_so_record(filename, so_type, employee_full_name, employee_position,
                    date_issued, generated_by, file_path):
    """Insert a record into so_records. Returns the new record id, or None."""
    try:
        from services.database import USE_DB, get_conn
        if not USE_DB:
            return None
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO so_records
                       (filename, so_type, employee_full_name, employee_position,
                        date_issued, generated_by, file_path)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (filename, so_type, employee_full_name, employee_position,
                     date_issued, generated_by, file_path),
                )
                row = cur.fetchone()
                return row["id"] if row else None
    except Exception:
        return None


_VERIFY_BASE = "https://doctracker.depedleytepersonnelunit.com"


def _embed_qr_in_docx(file_path, verify_url):
    try:
        import io
        import qrcode
        from docx import Document
        from docx.shared import Cm, Pt
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        doc = Document(file_path)

        # Generate QR in memory — small but scannable
        qr = qrcode.QRCode(version=2, box_size=3, border=2)
        qr.add_data(verify_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)

        from docx.oxml.ns import qn as _qn
        from lxml import etree

        replaced = False

        # Search body paragraphs first
        for para in doc.paragraphs:
            if "{{qr_code}}" in para.text:
                for run in para.runs:
                    run.text = ""
                for r in para._p.findall(qn("w:r")):
                    para._p.remove(r)
                run = para.add_run()
                run.add_picture(buf, width=Cm(2.0), height=Cm(2.0))
                replaced = True
                break

        # If not found in body, search text boxes (txbx elements in drawing shapes)
        if not replaced:
            # Find all text box paragraphs in the document XML
            body = doc.element.body
            # Text boxes are inside w:drawing > wp:inline/anchor > a:graphic > ... > wps:txbx > w:txbxContent > w:p
            ns = {
                'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
                'wps': 'http://schemas.microsoft.com/office/word/2010/wordprocessingShape',
            }
            for txbx in body.iter('{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}txbx'):
                for p_elem in txbx.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                    # Get text content
                    text = ''.join(
                        t.text or ''
                        for t in p_elem.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')
                    )
                    if '{{qr_code}}' in text:
                        # Clear all runs
                        for r in p_elem.findall('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r'):
                            p_elem.remove(r)
                        # Create a temporary paragraph to add picture
                        from docx.text.paragraph import Paragraph
                        temp_para = Paragraph(p_elem, doc)
                        run = temp_para.add_run()
                        buf.seek(0)
                        run.add_picture(buf, width=Cm(2.0), height=Cm(2.0))
                        replaced = True
                        break
                if replaced:
                    break

        doc.save(file_path)
    except Exception as e:
        print(f"Warning: QR embedding failed: {e}")


# ── Auto-log SO as document ────────────────────────────────────────────────────

def _log_so_as_document(so_type, employee_full_name, employee_position,
                        date_issued, filename, generated_by, full_name, office):
    """Auto-log the generated SO as a document record and auto-transfer to Personnel recipient."""
    try:
        from uuid import uuid4
        from services.documents import insert_doc, generate_ref, now_str
        now = now_str()
        now_display = datetime.now().strftime("%Y-%m-%d %H:%M")
        actor = full_name or generated_by
        doc_office = office or "DepEd Leyte Division"
        doc = {
            "id":                 str(uuid4())[:8].upper(),
            "doc_id":             generate_ref(),
            "doc_name":           f"Special Order - {employee_full_name}",
            "category":           so_type,
            "description":        f"Auto-generated Special Order for {employee_full_name}, {employee_position}",
            "sender_name":        actor,
            "sender_org":         doc_office,
            "sender_contact":     "",
            "referred_to":        "",
            "forwarded_to":       "",
            "recipient_name":     employee_full_name,
            "recipient_org":      "DepEd Leyte Division",
            "recipient_contact":  "",
            "received_by":        actor,
            "date_received":      now_display,
            "date_released":      "",
            "doc_date":           datetime.now().strftime("%Y-%m-%d"),
            "status":             "Logged",
            "notes":              f"Auto-generated SO document. File: {filename}",
            "created_at":         now,
            "routing":            [],
            "travel_log":         [
                {
                    "office":     doc_office,
                    "action":     "Document Logged by Staff",
                    "officer":    actor,
                    "timestamp":  now,
                    "remarks":    f"Logged into system via Special Order Generator by {actor}.",
                },
                {
                    "office":     doc_office,
                    "action":     "Special Order Generated",
                    "officer":    actor,
                    "timestamp":  now,
                    "remarks":    (
                        f"SO document generated by {actor} for "
                        f"{employee_full_name} ({employee_position}). File: {filename}"
                    ),
                },
            ],
            "logged_by":          generated_by,
            "original_logged_by": generated_by,
            "logged_by_office":   doc_office,
            "routing_cycle":      0,
            "so_filename":        filename,
        }

        # Auto-transfer to Personnel Unit primary recipient if configured
        try:
            from services.database import USE_DB, get_conn
            if USE_DB:
                primary_recipient  = None
                recipient_full_name = None
                recipient_office   = None
                user_row           = None

                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT primary_recipient FROM saved_offices WHERE office_slug = 'personnel'"
                        )
                        row = cur.fetchone()
                        primary_recipient = row['primary_recipient'] if row and row.get('primary_recipient') else None

                    if primary_recipient:
                        with conn.cursor() as cur:
                            cur.execute(
                                "SELECT full_name, office FROM users WHERE username = %s",
                                (primary_recipient,),
                            )
                            user_row = cur.fetchone()
                            if user_row:
                                recipient_full_name = user_row['full_name']
                                recipient_office    = user_row['office']

                if primary_recipient and user_row:
                    doc.update({
                        "status":                "Transferred",
                        "transferred_to":        primary_recipient,
                        "transferred_to_office": recipient_office,
                        "transferred_by":        generated_by,
                        "transferred_at":        now,
                        "transfer_type":         "inside_office",
                        "pending_at_staff":      primary_recipient,
                        "pending_at_office":     recipient_office,
                        "pending_at_staff_name": recipient_full_name,
                        "transfer_status":       "pending",
                    })
                    doc["travel_log"].append({
                        "office":    office or "Personnel Unit",
                        "action":    "Document Transferred",
                        "officer":   generated_by,
                        "timestamp": now,
                        "remarks":   f"Auto-transferred to {recipient_full_name} upon SO generation.",
                    })
        except Exception as transfer_err:
            print(f"Warning: SO auto-transfer skipped: {transfer_err}")

        insert_doc(doc)
    except Exception as e:
        print(f"Warning: could not auto-log SO as document: {e}")


# ── Auth helper ─────────────────────────────────────────────────────────────────

def _require_staff():
    """Redirect users without SO access. Admin always passes; staff need can_generate_so=True."""
    if not session.get("logged_in"):
        return redirect(url_for("auth.login"))
    role = session.get("role")
    if role == "admin":
        return None
    if role == "staff":
        from services.auth import get_user_can_generate_so
        username = session.get("username")
        if username and get_user_can_generate_so(username):
            return None
    flash("You don't have permission to access Special Order features.", "error")
    return redirect(url_for("dashboard.index"))


# ── Routes ──────────────────────────────────────────────────────────────────────

@so_bp.route("/so-request")
@login_required
def so_request_page():
    guard = _require_staff()
    if guard:
        return guard
    return render_template("so_request.html", so_categories=SO_CATEGORIES)


@so_bp.route("/api/so/types")
@login_required
def so_types_list():
    """Return the list of official SO category names."""
    if session.get("role") not in ("staff", "admin"):
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify({"success": True, "types": [{"value": c, "label": c} for c in SO_CATEGORIES]})


@so_bp.route("/api/so/fields/<so_type>")
@login_required
def so_fields(so_type):
    """Return the dynamic field config for a given SO type."""
    if session.get("role") not in ("staff", "admin"):
        return jsonify({"error": "Unauthorized"}), 403
    config = SO_TYPES.get(so_type)
    if not config:
        return jsonify({"error": "Unknown SO type"}), 404
    fields = [
        {
            "key":   f,
            "label": FIELD_LABELS.get(f, f.replace("_", " ").title()),
            "type":  "date" if f in _DATE_FIELDS else "text",
        }
        for f in config["fields"]
    ]
    return jsonify({"fields": fields, "subject": config["subject"]})


def _get_initials(full_name):
    if not full_name:
        return ""
    parts = full_name.strip().split()
    return "".join(p[0].upper() for p in parts if p)


@so_bp.route("/api/so/generate", methods=["POST"])
def so_generate():
    """Generate the SO .docx and return a download URL."""
    # Manual auth check — returns JSON so the frontend can display the error
    if not session.get("logged_in") or session.get("role") not in ("staff", "admin"):
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    data               = request.get_json(force=True, silent=True) or {}
    so_type            = data.get("so_type", "").strip()
    original_so_type   = so_type  # preserve display name before mapping
    employee_full_name = data.get("employee_full_name", "").strip()
    employee_position  = data.get("employee_position", "").strip()
    date_issued        = _fmt_date(data.get("date_issued", "").strip())
    fields             = {k: v.strip() for k, v in data.get("fields", {}).items()}

    initials       = _get_initials(session.get("full_name", ""))
    reference_code = f"OSDS-PU-{initials}" if initials else "OSDS-PU-RVV"

    # Map category name to internal SO type
    mapped = CATEGORY_TO_SO_TYPE.get(so_type.lower())
    if mapped:
        so_type = mapped

    # ── Validate ────────────────────────────────────────────────────────────────
    if not so_type or so_type not in SO_TYPES:
        return jsonify({"success": False, "message": "Invalid SO type"}), 400
    if not employee_full_name:
        return jsonify({"success": False, "message": "Employee name is required"}), 400
    if not employee_position:
        return jsonify({"success": False, "message": "Employee position is required"}), 400
    if not date_issued:
        return jsonify({"success": False, "message": "Date issued is required"}), 400

    config = SO_TYPES[so_type]

    # Format any date-type dynamic fields
    for key in _DATE_FIELDS:
        if key in fields:
            fields[key] = _fmt_date(fields[key])

    # Normalize accountability figures: prepend "Php" if missing
    if "accountability_amount_figures" in fields:
        v = fields["accountability_amount_figures"]
        if v and not v.startswith("Php"):
            try:
                num = float(v.replace(",", ""))
                fields["accountability_amount_figures"] = f"Php{num:,.2f}"
            except Exception:
                fields["accountability_amount_figures"] = "Php" + v
        elif v.startswith("Php"):
            try:
                num = float(v.replace("Php", "").replace(",", ""))
                fields["accountability_amount_figures"] = f"Php{num:,.2f}"
            except Exception:
                pass

    # ── Build body ──────────────────────────────────────────────────────────────
    body_vars = {
        "employee_full_name": employee_full_name,
        "employee_position":  employee_position,
        **fields,
    }
    try:
        body = config["body"].format(**body_vars)
    except KeyError as missing:
        return jsonify({"success": False, "message": f"Missing required field: {missing}"}), 400

    # ── Load template ───────────────────────────────────────────────────────────
    if not os.path.exists(TEMPLATE_PATH):
        return jsonify({"success": False,
                        "message": "SO template not found. Place S_O_TEMP.docx in so_templates/."}), 500

    try:
        from docx import Document
        doc = Document(TEMPLATE_PATH)

        # Replace body FIRST (it expands into multiple paragraphs)
        _replace_body(doc, "{{body}}", body)

        # Replace the four single-value placeholders with explicit formatting
        _replace_simple(doc, "{{employee_full_name}}", employee_full_name,
                        bold=True,  font_name="Bookman Old Style", font_size_pt=11)
        _replace_simple(doc, "{{employee_position}}",  employee_position,
                        bold=False, font_name="Bookman Old Style", font_size_pt=11)
        _replace_simple(doc, "{{subject}}",            config["subject"],
                        bold=True,  font_name="Bookman Old Style", font_size_pt=11)
        _replace_simple(doc, "{{date_issued}}",        date_issued,
                        bold=False, font_name="Bookman Old Style", font_size_pt=11)
        _replace_simple(doc, "{{reference_code}}",    reference_code)

        # ── Save ─────────────────────────────────────────────────────────────────
        out_dir   = _get_output_dir(so_type)
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"SO_{so_type.upper()}_{ts}.docx"
        file_path = os.path.join(out_dir, filename)
        doc.save(file_path)

        record_id = _save_so_record(
            filename, so_type, employee_full_name, employee_position,
            date_issued, session.get("username", "?"), file_path,
        )

        # Build verification URL and embed QR into the saved docx
        verify_identifier = str(record_id) if record_id else filename
        verify_url = f"{_VERIFY_BASE}/so/verify/{verify_identifier}"
        _embed_qr_in_docx(file_path, verify_url)

        _log_so_as_document(
            so_type=original_so_type,
            employee_full_name=employee_full_name,
            employee_position=employee_position,
            date_issued=date_issued,
            filename=filename,
            generated_by=session.get("username", ""),
            full_name=session.get("full_name", ""),
            office=session.get("office", "Personnel Unit"),
        )

        try:
            from services.misc import audit_log
            audit_log(
                "so_generated",
                f"so_type={so_type} employee={employee_full_name} file={filename}",
                username=session.get("username", "?"),
                ip=get_client_ip(),
            )
        except Exception:
            pass

        return jsonify({
            "success":      True,
            "filename":     filename,
            "download_url": url_for("so.so_download", filename=filename),
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@so_bp.route("/api/so/download/<filename>")
@login_required
def so_download(filename):
    """Serve the generated .docx file for download."""
    if session.get("role") not in ("staff", "admin"):
        return jsonify({"error": "Unauthorized"}), 403

    # Only allow filenames that match the generator's pattern
    if not re.match(r"^SO_[A-Z0-9_]+\.docx$", filename):
        return jsonify({"error": "Invalid filename"}), 400

    import glob as _glob
    search_paths = []
    if _IS_SERVER:
        search_paths += _glob.glob(f"/home/itpersonnelunit/so_documents/**/{filename}", recursive=True)
    search_paths += _glob.glob(os.path.join("so_output", "**", filename), recursive=True)
    search_paths.append(os.path.join("so_output", filename))

    filepath = next((p for p in search_paths if os.path.exists(p)), None)
    if not filepath:
        return jsonify({"error": "File not found"}), 404

    return send_file(
        os.path.abspath(filepath),
        as_attachment=True,
        download_name=filename,
        mimetype=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
    )


@so_bp.route("/so-history")
@login_required
def so_history_page():
    guard = _require_staff()
    if guard:
        return guard

    records = []
    try:
        from services.database import USE_DB, get_conn
        if USE_DB:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM so_records ORDER BY generated_at DESC")
                    rows = cur.fetchall()
            for row in rows:
                d = dict(row)
                d["so_label"] = SO_TYPES.get(d.get("so_type", ""), {}).get(
                    "label", (d.get("so_type") or "").replace("_", " ").title()
                )
                ga = d.get("generated_at")
                d["generated_at_str"] = (
                    ga.strftime("%Y-%m-%d %H:%M") if hasattr(ga, "strftime") else str(ga or "—")
                )
                records.append(d)
        else:
            # JSON fallback: derive metadata from filename only
            import glob as _glob
            _local_root = "/home/itpersonnelunit/so_documents" if _IS_SERVER else "so_output"
            all_files = _glob.glob(os.path.join(_local_root, "**", "SO_*.docx"), recursive=True)
            all_files += _glob.glob(os.path.join("so_output", "SO_*.docx"))
            if all_files:
                fnames = sorted(
                    [os.path.basename(f) for f in all_files
                     if re.match(r"^SO_[A-Z0-9_]+\.docx$", os.path.basename(f))],
                    reverse=True,
                )
                for fname in fnames:
                    m = re.match(r"^SO_(.+)_(\d{8})_(\d{6})\.docx$", fname)
                    so_type_key = m.group(1).lower() if m else ""
                    ts_str = "—"
                    if m:
                        try:
                            ts_str = datetime.strptime(
                                m.group(2) + m.group(3), "%Y%m%d%H%M%S"
                            ).strftime("%Y-%m-%d %H:%M")
                        except ValueError:
                            pass
                    records.append({
                        "filename":           fname,
                        "so_type":            so_type_key,
                        "so_label":           SO_TYPES.get(so_type_key, {}).get(
                            "label", so_type_key.replace("_", " ").title()
                        ),
                        "employee_full_name": "—",
                        "employee_position":  "—",
                        "date_issued":        "—",
                        "generated_by":       "—",
                        "generated_at_str":   ts_str,
                    })
    except Exception:
        pass

    return render_template("so_history.html", records=records)


@so_bp.route("/so/verify/<identifier>")
def so_verify(identifier):
    """Public verification page — no login required."""
    record = None
    try:
        from services.database import USE_DB, get_conn
        if USE_DB:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    if identifier.isdigit():
                        cur.execute("SELECT * FROM so_records WHERE id = %s", (int(identifier),))
                    else:
                        cur.execute("SELECT * FROM so_records WHERE filename = %s", (identifier,))
                    row = cur.fetchone()
            if row:
                record = dict(row)
                record["so_label"] = SO_TYPES.get(record.get("so_type", ""), {}).get(
                    "label", (record.get("so_type") or "").replace("_", " ").title()
                )
                ga = record.get("generated_at")
                record["generated_at_str"] = (
                    ga.strftime("%B %d, %Y %I:%M %p")
                    if hasattr(ga, "strftime") else str(ga or "—")
                )
    except Exception:
        pass
    return render_template("so_verify.html", record=record, identifier=identifier)
