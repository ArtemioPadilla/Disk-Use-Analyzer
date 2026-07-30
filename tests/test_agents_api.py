"""Tests for the /api/agents/{agent_id}/run endpoint's confirm gate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import agents_manager as agents_manager_module
import disk_analyzer_web


class _Completed:
    returncode = 0
    stdout = ""
    stderr = ""


def _fake_completed():
    return _Completed()


class TestRunAgentEndpoint:
    def setup_method(self):
        # conftest's autouse fixture sets NO_AUTH; endpoint reachable without a token.
        self.client = TestClient(disk_analyzer_web.app)

    def test_run_without_confirm_is_dry_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr(agents_manager_module, "AGENTS_FILE", tmp_path / "agents.json")
        monkeypatch.setattr(agents_manager_module, "AGENTS_LOG", tmp_path / "agents.log")
        called = []
        monkeypatch.setattr(
            agents_manager_module.subprocess, "run",
            lambda *a, **k: called.append(a) or _fake_completed(),
        )
        resp = self.client.post("/api/agents/cache_cleaner/run")
        assert resp.status_code == 200
        assert resp.json()["dry_run"] is True
        assert called == []

    def test_run_with_confirm_executes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(agents_manager_module, "AGENTS_FILE", tmp_path / "agents.json")
        monkeypatch.setattr(agents_manager_module, "AGENTS_LOG", tmp_path / "agents.log")
        called = []
        monkeypatch.setattr(
            agents_manager_module.subprocess, "run",
            lambda *a, **k: called.append(a) or _fake_completed(),
        )
        resp = self.client.post("/api/agents/cache_cleaner/run?confirm=true")
        assert resp.status_code == 200
        assert resp.json()["dry_run"] is False
        assert len(called) >= 1

    def test_run_unknown_agent_returns_404(self, tmp_path, monkeypatch):
        monkeypatch.setattr(agents_manager_module, "AGENTS_FILE", tmp_path / "agents.json")
        monkeypatch.setattr(agents_manager_module, "AGENTS_LOG", tmp_path / "agents.log")
        resp = self.client.post("/api/agents/does_not_exist/run")
        assert resp.status_code == 404
