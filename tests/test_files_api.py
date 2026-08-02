"""Tests for DELETE /api/files/delete, including its defenses, plus
GET /api/digest and GET /api/analysis/latest.
"""
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import disk_analyzer_web
from disk_analyzer_web import app


class TestDeleteFile:
    def setup_method(self):
        self.client = TestClient(app)

    def test_relative_path_is_rejected(self):
        resp = self.client.request(
            "DELETE", "/api/files/delete", json={"path": "relative/file.txt"}
        )
        assert resp.status_code == 400

    def test_protected_path_is_refused(self, monkeypatch):
        monkeypatch.setattr(disk_analyzer_web, "is_protected_path", lambda p: True)
        resp = self.client.request(
            "DELETE", "/api/files/delete", json={"path": "/System/Library/Kernels/kernel"}
        )
        assert resp.status_code == 403

    def test_missing_file_is_404(self):
        resp = self.client.request(
            "DELETE", "/api/files/delete", json={"path": "/tmp/definitely-not-here-12345"}
        )
        assert resp.status_code == 404

    def test_real_file_is_removed(self, tmp_path, monkeypatch):
        """The handler is macOS-first: on IS_MACOS it shells out to
        `osascript` to move the file to the Finder Trash (delete_file,
        disk_analyzer_web.py:1054-1064). Actually invoking osascript in a
        test would be slow, depend on the Finder being available/scriptable
        in CI, and leave junk in the *real* user Trash outside of tmp_path --
        exactly what this task forbids.

        Instead we patch subprocess.run (imported locally inside the
        handler, but that local `import subprocess` binds to the very same
        module object already cached in sys.modules, so patching the
        top-level `subprocess.run` attribute here still takes effect) to
        return a non-zero returncode, which is the "osascript failed"
        branch the handler already has: it falls back to
        `resolved_path.unlink()`. That exercises the real, permanent
        deletion codepath entirely inside tmp_path with no Finder/Trash
        interaction at all.
        """
        victim = tmp_path / "junk.bin"
        victim.write_bytes(b"x" * 1024)
        monkeypatch.setattr(disk_analyzer_web, "is_protected_path", lambda p: False)

        class FakeCompletedProcess:
            returncode = 1
            stdout = ""
            stderr = "osascript not available in tests"

        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeCompletedProcess())

        resp = self.client.request(
            "DELETE", "/api/files/delete", json={"path": str(victim)}
        )
        assert resp.status_code == 200
        assert not victim.exists()


class TestDigestAndLatest:
    def setup_method(self):
        self.client = TestClient(app)

    def test_digest_responds_with_its_shape(self, monkeypatch, tmp_path):
        # get_digest() reads Path.home() / ".disk-analyzer" / "agents.log"
        # for the "agents_log" field. On this dev machine that file is real
        # and has real content, so reading it would make the test depend on
        # (and read) the user's actual $HOME -- forbidden by this task.
        # Redirect Path.home() to an empty tmp_path for the duration of this
        # test so the log file is deterministically absent.
        import pathlib
        monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))

        resp = self.client.get("/api/digest")
        assert resp.status_code == 200
        body = resp.json()
        # get_digest() (disk_analyzer_web.py:717-778) always builds this
        # exact top-level shape, even with zero session history.
        assert isinstance(body, dict)
        assert "scans_this_week" in body
        assert "total_scans" in body
        assert "disk" in body
        assert set(body["disk"].keys()) >= {"used", "total", "free", "percent"}
        assert "growth" in body
        assert body["agents_log"] == []

    def test_latest_with_no_sessions_is_handled(self, monkeypatch, tmp_path):
        monkeypatch.setattr(disk_analyzer_web, "analysis_sessions", {})
        # get_latest_results() falls back to scanning RESULTS_DIR
        # (Path.home() / ".disk-analyzer" / "results") on disk when there
        # are no in-memory sessions. That directory is the *real* user's
        # home directory and may genuinely contain leftover result files
        # from real usage of this tool -- reading it would make this test's
        # outcome depend on the state of the machine it happens to run on,
        # which is exactly what this task must not reintroduce. Point
        # RESULTS_DIR at an empty tmp_path so the "no history at all" path
        # is deterministic.
        monkeypatch.setattr(disk_analyzer_web, "RESULTS_DIR", tmp_path)
        resp = self.client.get("/api/analysis/latest")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_latest_returns_the_newest_completed_session(self, monkeypatch):
        sessions = {
            "older": {
                "id": "older",
                "status": "completed",
                "results": [{"path": "/fake/old"}],
                "started_at": "2026-01-01T00:00:00",
                "completed_at": "2026-01-01T00:00:01",
            },
            "newer": {
                "id": "newer",
                "status": "completed",
                "results": [{"path": "/fake/new"}],
                "started_at": "2026-01-02T00:00:00",
                "completed_at": "2026-01-02T00:00:01",
            },
        }
        monkeypatch.setattr(disk_analyzer_web, "analysis_sessions", sessions)
        resp = self.client.get("/api/analysis/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "newer"
        assert body["results"] == [{"path": "/fake/new"}]
