"""
tests/test_so_download.py — id-based SO download endpoint (routes/so.py::so_download).

This is the test that would have caught the original "Invalid filename" bug: an SO
generated for a person with a non-ASCII name (e.g. "Glenda T. Cariño") produces a
filename containing Ñ, which the old ASCII-only guard (^SO_[A-Z0-9_]+\\.docx$) rejected.
Serving by so_records id + Content-Disposition download_name removes that guard entirely.

The endpoint looks up the row via routes.so._fetch_so_record; tests monkeypatch that
helper so no PostgreSQL is needed (the suite runs on the JSON backend). admin_client is
used because admin passes both _require_staff() and the ("staff","admin") role check.
"""

import os
import routes.so as so_mod


def _make_so_file(subdir, filename):
    """Create a real file under so_output/<subdir>/ (inside the allowed root)."""
    out = os.path.join("so_output", subdir)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, filename)
    with open(path, "wb") as f:
        f.write(b"PK\x03\x04 fake docx bytes")
    return path


class TestSoDownloadById:
    def test_unicode_name_downloads(self, admin_client, monkeypatch):
        """A Cariño SO must download — the ñ survives via Content-Disposition."""
        filename = "SO_DESIGNATION_RENEWAL_GLENDA_T_CARIÑO_20260901.docx"
        path = _make_so_file("designation_renewal", filename)
        monkeypatch.setattr(
            so_mod, "_fetch_so_record",
            lambda rid: {"id": rid, "filename": filename, "file_path": path},
        )

        rv = admin_client.get("/api/so/download/42")
        assert rv.status_code == 200, rv.data[:200]
        with open(path, "rb") as f:
            assert rv.data == f.read()

        cd = rv.headers.get("Content-Disposition", "")
        # Ñ (U+00D1) → UTF-8 0xC3 0x91 → RFC 5987 filename* percent-encoding
        assert "filename*=" in cd, cd
        assert "%C3%91" in cd.upper(), cd

    def test_ascii_name_downloads(self, admin_client, monkeypatch):
        """Regression: a plain-ASCII name still downloads fine."""
        filename = "SO_DESIGNATION_RENEWAL_JOHN_SMITH_20260901.docx"
        path = _make_so_file("designation_renewal", filename)
        monkeypatch.setattr(
            so_mod, "_fetch_so_record",
            lambda rid: {"id": rid, "filename": filename, "file_path": path},
        )

        rv = admin_client.get("/api/so/download/7")
        assert rv.status_code == 200, rv.data[:200]
        cd = rv.headers.get("Content-Disposition", "")
        assert "JOHN_SMITH" in cd, cd

    def test_missing_record_404(self, admin_client, monkeypatch):
        """A bogus (nonexistent) id → 404."""
        monkeypatch.setattr(so_mod, "_fetch_so_record", lambda rid: None)
        rv = admin_client.get("/api/so/download/99999")
        assert rv.status_code == 404, rv.data[:200]

    def test_nonint_id_404(self, admin_client):
        """A non-integer id fails the <int:...> converter → 404 (never reaches handler)."""
        rv = admin_client.get("/api/so/download/not-an-int")
        assert rv.status_code == 404

    def test_path_escape_blocked(self, admin_client, monkeypatch, tmp_path):
        """A stored file_path outside the allowed SO roots is rejected (403)."""
        outside = tmp_path / "evil.docx"
        outside.write_bytes(b"nope")
        monkeypatch.setattr(
            so_mod, "_fetch_so_record",
            lambda rid: {"id": rid, "filename": "evil.docx", "file_path": str(outside)},
        )
        rv = admin_client.get("/api/so/download/1")
        assert rv.status_code == 403, rv.data[:200]
