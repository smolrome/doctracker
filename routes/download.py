"""
Download route — serves the mobile app download page and APK file.

To activate:
  1. Build your APK:   eas build -p android --profile preview
  2. Rename the output file to `doctracker.apk`
  3. Drop it into:     static/apk/doctracker.apk
  4. The /download page will automatically detect it and enable the button.
"""

import json
import os
from flask import Blueprint, render_template, send_from_directory, abort, current_app

download_bp = Blueprint('download', __name__)

APK_FILENAME = 'doctracker.apk'


def _apk_path():
    return os.path.join(current_app.static_folder, 'apk', APK_FILENAME)


def _apk_size_mb():
    """Return human-readable file size, or None if file missing."""
    path = _apk_path()
    if not os.path.exists(path):
        return None
    size_bytes = os.path.getsize(path)
    return f'{size_bytes / 1_048_576:.1f} MB'


@download_bp.route('/download')
def download_page():
    apk_version = '1.0.0'
    version_file = os.path.join(current_app.static_folder, 'apk', 'version.json')
    try:
        with open(version_file, 'r') as f:
            apk_version = json.load(f).get('latest_version', '1.0.0')
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    return render_template(
        'download.html',
        apk_available=os.path.exists(_apk_path()),
        apk_size=_apk_size_mb(),
        apk_filename=APK_FILENAME,
        apk_version=apk_version,
    )


@download_bp.route('/download/apk')
def download_apk():
    """Serve the APK file as a direct download."""
    apk_dir = os.path.join(current_app.static_folder, 'apk')
    if not os.path.exists(os.path.join(apk_dir, APK_FILENAME)):
        abort(404, description='APK not yet available. Check back soon.')
    resp = current_app.make_response(
        send_from_directory(
            apk_dir,
            APK_FILENAME,
            as_attachment=True,
            download_name='DepEd-DocTracker.apk',
            mimetype='application/vnd.android.package-archive',
        )
    )
    resp.headers['Accept-Ranges']       = 'bytes'
    resp.headers['Cache-Control']       = 'no-cache'
    resp.headers['Content-Disposition'] = 'attachment; filename="DepEd-DocTracker.apk"'
    return resp
