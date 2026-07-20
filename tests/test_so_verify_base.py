"""
tests/test_so_verify_base.py — Unit tests for routes/so.py::_verify_base().

Covers:
  - raises RuntimeError when APP_URL is empty
  - raises RuntimeError when APP_URL is not an absolute http(s) URL
  - returns the configured base, trailing slash stripped
  - reads APP_URL at CALL time, not module-import time
"""

import os
import pytest

os.environ.setdefault("SECRET_KEY", "e" * 32)
os.environ.setdefault("ADMIN_USERNAME", "sotestadmin")
os.environ.setdefault("ADMIN_PASSWORD", "SoAdmin123!")
os.environ["DATABASE_URL"] = ""


class TestVerifyBase:
    def test_raises_when_app_url_empty(self, monkeypatch):
        import config
        from routes.so import _verify_base
        monkeypatch.setattr(config, "APP_URL", "")
        with pytest.raises(RuntimeError, match="APP_URL"):
            _verify_base()

    @pytest.mark.parametrize("bad", [
        "doctracker.example.com",   # no scheme
        "localhost:5000",           # no scheme
        "ftp://example.com",        # wrong scheme
        "   ",                      # whitespace only
        "/so/verify",               # relative
    ])
    def test_raises_when_not_absolute_http(self, monkeypatch, bad):
        import config
        from routes.so import _verify_base
        monkeypatch.setattr(config, "APP_URL", bad)
        with pytest.raises(RuntimeError, match="APP_URL"):
            _verify_base()

    def test_returns_configured_base(self, monkeypatch):
        import config
        from routes.so import _verify_base
        monkeypatch.setattr(config, "APP_URL", "https://example.test")
        assert _verify_base() == "https://example.test"

    def test_strips_trailing_slash(self, monkeypatch):
        import config
        from routes.so import _verify_base
        monkeypatch.setattr(config, "APP_URL", "https://example.test/")
        assert _verify_base() == "https://example.test"

    def test_http_scheme_accepted(self, monkeypatch):
        import config
        from routes.so import _verify_base
        monkeypatch.setattr(config, "APP_URL", "http://localhost:5000")
        assert _verify_base() == "http://localhost:5000"

    def test_reads_app_url_at_call_time(self, monkeypatch):
        """The point of the function-local import: no importlib.reload needed."""
        import config
        from routes.so import _verify_base
        monkeypatch.setattr(config, "APP_URL", "https://first.test")
        assert _verify_base() == "https://first.test"
        monkeypatch.setattr(config, "APP_URL", "https://second.test")
        assert _verify_base() == "https://second.test"
