"""
routes/import_excel.py — Upload an Excel tracking sheet and import all rows as documents.
"""
from flask import (Blueprint, flash, redirect, render_template,
                   request, session, url_for)

from services.excel_import import import_excel, parse_excel
from services.misc import audit_log
from utils import login_required, get_client_ip

import_bp = Blueprint("import_excel", __name__)

ALLOWED_EXT = {".xlsx", ".xls", ".xlsm"}


def _allowed(filename: str) -> bool:
    import os
    return os.path.splitext(filename.lower())[1] in ALLOWED_EXT


@import_bp.route("/import-excel")
@login_required
def import_page():
    return render_template("import_excel.html")


@import_bp.route("/import-excel/preview", methods=["POST"])
@login_required
def import_preview():
    """Parse the file and show a preview before committing."""
    uploaded = request.files.get("excel_file")
    if not uploaded or not uploaded.filename:
        flash("Please select an Excel file.", "error")
        return redirect(url_for("import_excel.import_page"))
    if not _allowed(uploaded.filename):
        flash("Only .xlsx / .xls files are supported.", "error")
        return redirect(url_for("import_excel.import_page"))

    file_bytes = uploaded.read()
    rows, warnings = parse_excel(file_bytes, uploaded.filename)

    # Store bytes in session is too large — store in a temp file instead
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx",
                                      prefix="dt_import_")
    tmp.write(file_bytes)
    tmp.close()
    session["import_tmp"]      = tmp.name
    session["import_filename"] = uploaded.filename

    return render_template("import_excel.html",
                           preview=rows[:50],   # show first 50 rows
                           total=len(rows),
                           filename=uploaded.filename,
                           warnings=warnings)


@import_bp.route("/import-excel/confirm", methods=["POST"])
@login_required
def import_confirm():
    """Read temp file and do the actual import."""
    tmp_path = session.pop("import_tmp", None)
    filename = session.pop("import_filename", "upload.xlsx")
    status   = request.form.get("default_status", "Received")

    if not tmp_path:
        flash("Session expired — please re-upload the file.", "error")
        return redirect(url_for("import_excel.import_page"))

    import os
    if not os.path.exists(tmp_path):
        flash("Temporary file not found — please re-upload.", "error")
        return redirect(url_for("import_excel.import_page"))

    with open(tmp_path, "rb") as f:
        file_bytes = f.read()
    os.unlink(tmp_path)

    summary = import_excel(file_bytes, filename,
                           imported_by=session.get("username", "admin"),
                           default_status=status)

    audit_log("excel_import",
              f"file={filename} imported={summary['imported']} "
              f"skipped={summary['skipped']} errors={len(summary['errors'])}",
              username=session.get("username", "admin"),
              ip=get_client_ip())

    return render_template("import_excel.html", summary=summary, filename=filename)
