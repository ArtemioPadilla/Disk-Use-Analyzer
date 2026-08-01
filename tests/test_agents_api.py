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


class TestToggleAgentEndpoint:
    """Regression tests: toggle_agent() used to discard _save_state()'s
    return value, so POST /api/agents/{id}/toggle always claimed success even
    when the new enabled/disabled flag lived only in memory and would vanish
    on restart."""

    def setup_method(self):
        self.client = TestClient(disk_analyzer_web.app)

    def test_toggle_reports_saved_true_on_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr(agents_manager_module, "AGENTS_FILE", tmp_path / "agents.json")
        monkeypatch.setattr(agents_manager_module, "AGENTS_LOG", tmp_path / "agents.log")

        resp = self.client.post("/api/agents/cache_cleaner/toggle?enabled=true")

        assert resp.status_code == 200
        body = resp.json()
        assert body["state_saved"] is True
        assert "warning" not in body

    def test_toggle_reports_saved_false_and_warns_on_persistence_failure(self, tmp_path, monkeypatch):
        # Point AGENTS_FILE at a path whose parent directory doesn't exist and
        # can't be created (a file sitting where the directory should be),
        # forcing _save_state()'s mkdir/open to fail.
        blocker = tmp_path / "blocked_as_a_file"
        blocker.write_text("not a directory")
        monkeypatch.setattr(agents_manager_module, "AGENTS_FILE", blocker / "agents.json")
        monkeypatch.setattr(agents_manager_module, "AGENTS_LOG", tmp_path / "agents.log")

        resp = self.client.post("/api/agents/cache_cleaner/toggle?enabled=true")

        assert resp.status_code == 200
        body = resp.json()
        assert body["state_saved"] is False
        assert "warning" in body
