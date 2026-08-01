"""Tests for /api/cleanup/* endpoints."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import disk_analyzer_web
from disk_analyzer_web import app


class TestCleanupPreview:
    def setup_method(self):
        self.client = TestClient(app)

    def test_preview_without_categories_is_accepted(self):
        # The frontend sends only paths + dry_run; categories must be optional
        resp = self.client.post(
            "/api/cleanup/preview",
            json={"paths": [str(Path.home())], "dry_run": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "actions" in body
        assert "total_size" in body

    def test_preview_filters_by_category_case_insensitive(self, monkeypatch):
        class FakeAnalyzer:
            def __init__(self, path):
                self.cache_locations = [
                    {"path": "/fake/npm", "size": 100, "type": "NPM Cache"},
                    {"path": "/fake/docker", "size": 200, "type": "Docker"},
                ]

            def find_cache_locations(self):
                pass

        monkeypatch.setattr(disk_analyzer_web, "DiskAnalyzerCore", FakeAnalyzer)
        resp = self.client.post(
            "/api/cleanup/preview",
            json={"paths": ["/tmp"], "categories": ["npm cache"], "dry_run": True},
        )
        assert resp.status_code == 200
        actions = resp.json()["actions"]
        assert len(actions) == 1
        assert actions[0]["path"] == "/fake/npm"


class TestCleanupExecute:
    def setup_method(self):
        self.client = TestClient(app)

    def test_execute_dry_run_returns_preview(self):
        resp = self.client.post(
            "/api/cleanup/execute",
            json={"paths": [str(Path.home())], "dry_run": True},
        )
        assert resp.status_code == 200
        assert resp.json()["dry_run"] is True

    def test_execute_deletes_only_unprotected(self, tmp_path, monkeypatch):
        victim = tmp_path / "cache_dir"
        victim.mkdir()
        (victim / "junk.bin").write_bytes(b"x" * 1024)

        class FakeAnalyzer:
            def __init__(self, path):
                self.cache_locations = [
                    {"path": str(victim), "size": 1024, "type": "Cache General"},
                    {"path": "/System/Library/Kernels", "size": 1, "type": "Cache General"},
                ]

            def find_cache_locations(self):
                pass

        monkeypatch.setattr(disk_analyzer_web, "DiskAnalyzerCore", FakeAnalyzer)
        # _perform_cleanup_deletes now calls the shared analyzer.protection.is_protected_path
        # free function directly (imported into this module's namespace), instead of a
        # DiskAnalyzerCore instance method -- patch it at its new call site.
        monkeypatch.setattr(disk_analyzer_web, "is_protected_path", lambda path: path.startswith("/System"))
        resp = self.client.post(
            "/api/cleanup/execute",
            json={"paths": [str(tmp_path)], "dry_run": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert not victim.exists()
        deleted_paths = [d["path"] for d in body["deleted"]]
        assert str(victim) in deleted_paths
        # The protected path must be skipped, reported as error, never deleted
        error_paths = [e["path"] for e in body["errors"]]
        assert any("/System" in p for p in error_paths)
