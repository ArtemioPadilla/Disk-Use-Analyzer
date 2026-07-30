"""Tests for agents safety (dry-run + confirmation)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import agents_manager as agents_manager_module
from agents_manager import AgentsManager, AGENT_DEFINITIONS


class _Completed:
    returncode = 0
    stdout = ""
    stderr = ""


def _fake_completed():
    return _Completed()


def _make_manager(tmp_path, monkeypatch):
    # Never let the manager touch the real home directory during tests.
    monkeypatch.setattr(agents_manager_module, "AGENTS_FILE", tmp_path / "agents.json")
    monkeypatch.setattr(agents_manager_module, "AGENTS_LOG", tmp_path / "agents.log")
    return AgentsManager()


class TestRunAgentDryRun:
    def test_dry_run_does_not_execute(self, tmp_path, monkeypatch):
        mgr = _make_manager(tmp_path, monkeypatch)
        calls = []
        monkeypatch.setattr(
            agents_manager_module.subprocess, "run",
            lambda *a, **k: calls.append(a) or _fake_completed(),
        )
        result = mgr.run_agent("cache_cleaner", dry_run=True)
        assert result["dry_run"] is True
        assert calls == [], "dry-run must not call subprocess.run"
        assert result["would_run"] == AGENT_DEFINITIONS["cache_cleaner"]["commands"]
        assert result["freed"] == 0

    def test_default_is_dry_run(self, tmp_path, monkeypatch):
        mgr = _make_manager(tmp_path, monkeypatch)
        called = []
        monkeypatch.setattr(
            agents_manager_module.subprocess, "run",
            lambda *a, **k: called.append(a) or _fake_completed(),
        )
        result = mgr.run_agent("cache_cleaner")  # no dry_run arg
        assert result["dry_run"] is True
        assert called == []

    def test_real_run_executes(self, tmp_path, monkeypatch):
        mgr = _make_manager(tmp_path, monkeypatch)
        called = []
        monkeypatch.setattr(
            agents_manager_module.subprocess, "run",
            lambda *a, **k: called.append(a) or _fake_completed(),
        )
        result = mgr.run_agent("cache_cleaner", dry_run=False)
        assert result["dry_run"] is False
        assert len(called) == len(AGENT_DEFINITIONS["cache_cleaner"]["commands"])

    def test_real_run_preserves_state_bookkeeping(self, tmp_path, monkeypatch):
        """The pre-existing last_run/last_freed/total_freed/run_count bookkeeping
        must survive the dry_run refactor exactly as it worked before."""
        mgr = _make_manager(tmp_path, monkeypatch)
        monkeypatch.setattr(
            agents_manager_module.subprocess, "run",
            lambda *a, **k: _fake_completed(),
        )
        result = mgr.run_agent("cache_cleaner", dry_run=False)
        state = mgr.agents_state["cache_cleaner"]
        assert state["run_count"] == 1
        assert "last_run" in state
        assert state["last_freed"] == result["freed"]
        assert state["total_freed"] == result["freed"]

        # A second real run should accumulate, not reset, total_freed/run_count.
        mgr.run_agent("cache_cleaner", dry_run=False)
        state = mgr.agents_state["cache_cleaner"]
        assert state["run_count"] == 2

    def test_unknown_agent_raises(self, tmp_path, monkeypatch):
        mgr = _make_manager(tmp_path, monkeypatch)
        try:
            mgr.run_agent("does_not_exist", dry_run=True)
            assert False, "expected ValueError"
        except ValueError:
            pass
