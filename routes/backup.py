"""
routes/backup.py — Backup and restore routes.
Admin-only. Download a full JSON backup, upload to restore.
"""
import json
from datetime import datetime
from io import BytesIO

from flask import (Blueprint, flash, redirect, render_template,
                   request, send_file, session, url_for)

from services.backup import create_backup, restore_backup, create_selective_backup
from services.misc import audit_log
from utils import admin_required, get_client_ip

backup_bp = Blueprint("backup", __name__)


@backup_bp.route("/backup")
@admin_required
def backup_page():
    """Backup & Restore admin page."""
    return render_template("backup.html")


@backup_bp.route("/backup/download")
@admin_required
def backup_download():
    """Generate and download a full system backup as JSON."""
    try:
        data     = create_backup()
        filename = f"doctracker_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        buf      = BytesIO(json.dumps(data, indent=2, default=str).encode("utf-8"))
        buf.seek(0)
        audit_log("backup_downloaded",
                  f"docs={data['meta']['counts']['documents']} "
                  f"users={data['meta']['counts']['users']}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        return send_file(buf, mimetype="application/json",
                         as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f"Backup failed: {e}", "error")
        return redirect(url_for("backup.backup_page"))


@backup_bp.route("/backup/download-excel")
@admin_required
def backup_download_excel():
    """Generate and download a full system backup as a formatted Excel workbook."""
    try:
        from services.backup import create_excel_backup
        filename = f"doctracker_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        buf = BytesIO(create_excel_backup())
        buf.seek(0)
        audit_log("backup_excel_downloaded", "Excel export",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())
        return send_file(buf,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f"Excel export failed: {e}", "error")
        return redirect(url_for("backup.backup_page"))


@backup_bp.route("/backup/export", methods=["POST"])
@admin_required
def backup_export():
    """Generate and download a selective backup based on form selection."""
    # Get what to export
    export_docs = request.form.get("export_docs") == "on"
    export_users = request.form.get("export_users") == "on"
    export_slips = request.form.get("export_slips") == "on"
    export_offices = request.form.get("export_offices") == "on"
    export_traffic = request.form.get("export_traffic") == "on"
    
    # Get file type
    file_type = request.form.get("file_type", "json")
    
    # Validate at least one item is selected
    if not any([export_docs, export_users, export_slips, export_offices, export_traffic]):
        flash("Please select at least one item to export.", "error")
        return redirect(url_for("backup.backup_page"))
    
    export_items = []
    if export_docs:
        export_items.append("documents")
    if export_users:
        export_items.append("users")
    if export_slips:
        export_items.append("routing_slips")
    if export_offices:
        export_items.append("saved_offices")
    if export_traffic:
        export_items.append("office_traffic")
    
    try:
        if file_type == "excel":
            from services.backup import create_selective_excel_backup
            filename = f"doctracker_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            buf = BytesIO(create_selective_excel_backup(export_items))
            buf.seek(0)
            audit_log("backup_excel_downloaded", 
                      f"type=selective items={','.join(export_items)}",
                      username=session.get("username", "admin"),
                      ip=get_client_ip())
            return send_file(buf,
                             mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             as_attachment=True, download_name=filename)
        else:
            data = create_selective_backup(export_items)
            filename = f"doctracker_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            buf = BytesIO(json.dumps(data, indent=2, default=str).encode("utf-8"))
            buf.seek(0)
            audit_log("backup_downloaded",
                      f"type=selective items={','.join(export_items)}",
                      username=session.get("username", "admin"),
                      ip=get_client_ip())
            return send_file(buf, mimetype="application/json",
                             as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f"Export failed: {e}", "error")
        return redirect(url_for("backup.backup_page"))


@backup_bp.route("/backup/restore", methods=["POST"])
@admin_required
def backup_restore():
    """Upload a backup JSON file and restore data."""
    uploaded = request.files.get("backup_file")
    mode     = request.form.get("mode", "merge")   # 'merge' or 'replace'

    if not uploaded or not uploaded.filename:
        flash("Please select a backup file to upload.", "error")
        return redirect(url_for("backup.backup_page"))

    if not uploaded.filename.endswith(".json"):
        flash("Only .json backup files are supported.", "error")
        return redirect(url_for("backup.backup_page"))

    try:
        raw    = uploaded.read()
        backup = json.loads(raw)

        # Basic validation
        if "meta" not in backup or "documents" not in backup:
            flash("Invalid backup file — missing required sections.", "error")
            return redirect(url_for("backup.backup_page"))

        summary = restore_backup(backup, mode=mode)

        audit_log("backup_restored",
                  f"mode={mode} docs={summary['documents']} "
                  f"users={summary['users']} skipped={summary['skipped']}",
                  username=session.get("username", "admin"),
                  ip=get_client_ip())

        return render_template("backup.html", summary=summary, mode=mode)

    except json.JSONDecodeError:
        flash("Could not read the file — it does not appear to be valid JSON.", "error")
        return redirect(url_for("backup.backup_page"))
    except Exception as e:
        flash(f"Restore failed: {e}", "error")
        return redirect(url_for("backup.backup_page"))
