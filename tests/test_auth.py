"""Tests for token auth on the HTTP API."""
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient


def _load_app(monkeypatch, *, token=None, no_auth=False):
    """Reload disk_analyzer_web with a controlled auth env, return (module, client)."""
    if no_auth:
        monkeypatch.setenv("DISK_ANALYZER_NO_AUTH", "1")
        monkeypatch.delenv("DISK_ANALYZER_TOKEN", raising=False)
    else:
        monkeypatch.setenv("DISK_ANALYZER_NO_AUTH", "0")
        monkeypatch.setenv("DISK_ANALYZER_TOKEN", token or "test-token-abc")
    import disk_analyzer_web
    importlib.reload(disk_analyzer_web)
    return disk_analyzer_web, TestClient(disk_analyzer_web.app)


class TestHttpAuth:
    def test_api_route_without_token_is_401(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        resp = client.get("/api/system/info")
        assert resp.status_code == 401

    def test_api_route_with_valid_token_is_ok(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        resp = client.get("/api/system/info", headers={"X-Auth-Token": "secret1"})
        assert resp.status_code == 200

    def test_api_route_with_wrong_token_is_401(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        resp = client.get("/api/system/info", headers={"X-Auth-Token": "nope"})
        assert resp.status_code == 401

    def test_destructive_route_without_token_is_401(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        resp = client.post("/api/cleanup/preview", json={"paths": [], "dry_run": True})
        assert resp.status_code == 401

    def test_static_root_is_open(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        # "/" serves the SPA index (or 404 if no build) but must NOT be 401
        resp = client.get("/")
        assert resp.status_code != 401

    def test_no_auth_mode_allows_api(self, monkeypatch):
        _, client = _load_app(monkeypatch, no_auth=True)
        resp = client.get("/api/system/info")
        assert resp.status_code == 200
