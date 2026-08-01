"""Tests for agents safety (dry-run + confirmation)."""
import asyncio
import sys
from pathlib import Path

import pytest

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


class TestLogFailureDoesNotCrash:
    """Regression tests for the smoke-test bug: a leftover root-owned
    agents.log (e.g. from a previous `sudo make web`) makes _log() raise
    PermissionError on append. That must never bubble out of run_agent() --
    logging is best-effort, not a precondition for the operation it records.
    """

    def _break_log_open(self, monkeypatch):
        """Simulate the log file being unwritable (e.g. owned by root)."""
        real_open = open

        def _boom(path, *a, **k):
            if str(path) == str(agents_manager_module.AGENTS_LOG):
                raise PermissionError(13, "Permission denied", str(path))
            return real_open(path, *a, **k)

        monkeypatch.setattr(agents_manager_module, "open", _boom, raising=False)

    def test_dry_run_survives_log_permission_error(self, tmp_path, monkeypatch, capsys):
        mgr = _make_manager(tmp_path, monkeypatch)
        self._break_log_open(monkeypatch)

        result = mgr.run_agent("cache_cleaner", dry_run=True)

        assert result["dry_run"] is True
        assert result["would_run"] == AGENT_DEFINITIONS["cache_cleaner"]["commands"]
        assert result["freed"] == 0
        # The failure should not be silent: a warning is printed.
        captured = capsys.readouterr()
        assert "Warning" in (captured.out + captured.err)

    def test_real_run_survives_log_permission_error(self, tmp_path, monkeypatch, capsys):
        mgr = _make_manager(tmp_path, monkeypatch)
        # Critical: never let a real destructive command execute in tests.
        called = []
        monkeypatch.setattr(
            agents_manager_module.subprocess, "run",
            lambda *a, **k: called.append(a) or _fake_completed(),
        )
        self._break_log_open(monkeypatch)

        result = mgr.run_agent("cache_cleaner", dry_run=False)

        assert len(called) == len(AGENT_DEFINITIONS["cache_cleaner"]["commands"])
        assert result["dry_run"] is False
        assert "freed" in result
        captured = capsys.readouterr()
        assert "Warning" in (captured.out + captured.err)

    def test_log_permission_error_does_not_propagate_directly(self, tmp_path, monkeypatch):
        """Calling _log() directly with a broken file must not raise."""
        mgr = _make_manager(tmp_path, monkeypatch)
        self._break_log_open(monkeypatch)
        # Should not raise.
        agents_manager_module._log("this should not crash")

    def test_log_reraises_non_io_errors(self, tmp_path, monkeypatch):
        """Programming errors (e.g. TypeError) must not be silently swallowed --
        only I/O failures are best-effort."""
        mgr = _make_manager(tmp_path, monkeypatch)

        def _boom_typeerror(*a, **k):
            raise TypeError("boom")

        monkeypatch.setattr(agents_manager_module, "open", _boom_typeerror, raising=False)
        try:
            agents_manager_module._log("whatever")
            assert False, "expected TypeError to propagate"
        except TypeError:
            pass


class TestSaveStateFailureDoesNotCrash:
    """If ~/.disk-analyzer/agents.json can't be written (e.g. root-owned from
    a previous sudo run), the operation that triggered the save must still
    complete -- but unlike logging, losing state is consequential, so the
    failure must be surfaced rather than pretended-successful.
    """

    def _break_state_open(self, monkeypatch):
        real_open = open

        def _boom(path, *a, **k):
            if str(path) == str(agents_manager_module.AGENTS_FILE):
                raise PermissionError(13, "Permission denied", str(path))
            return real_open(path, *a, **k)

        monkeypatch.setattr(agents_manager_module, "open", _boom, raising=False)

    def test_toggle_agent_survives_save_state_permission_error(self, tmp_path, monkeypatch, capsys):
        mgr = _make_manager(tmp_path, monkeypatch)
        self._break_state_open(monkeypatch)

        # Must not raise.
        mgr.toggle_agent("cache_cleaner", True)

        captured = capsys.readouterr()
        assert "Warning" in (captured.out + captured.err)

    def test_toggle_agent_reports_persistence_failure(self, tmp_path, monkeypatch):
        """toggle_agent() must not silently pretend the change was saved when
        _save_state() fails -- the in-memory flip happened but would vanish
        on restart, and callers need to know that."""
        mgr = _make_manager(tmp_path, monkeypatch)
        self._break_state_open(monkeypatch)

        result = mgr.toggle_agent("cache_cleaner", True)

        assert result["state_saved"] is False
        # The in-memory toggle still took effect even though persistence failed.
        assert mgr.agents_state["cache_cleaner"]["enabled"] is True

    def test_toggle_agent_reports_persistence_success(self, tmp_path, monkeypatch):
        mgr = _make_manager(tmp_path, monkeypatch)
        result = mgr.toggle_agent("cache_cleaner", True)
        assert result["state_saved"] is True

    def test_real_run_survives_save_state_permission_error(self, tmp_path, monkeypatch, capsys):
        mgr = _make_manager(tmp_path, monkeypatch)
        called = []
        monkeypatch.setattr(
            agents_manager_module.subprocess, "run",
            lambda *a, **k: called.append(a) or _fake_completed(),
        )
        self._break_state_open(monkeypatch)

        result = mgr.run_agent("cache_cleaner", dry_run=False)

        assert len(called) == len(AGENT_DEFINITIONS["cache_cleaner"]["commands"])
        # The run itself still completes and reports its result...
        assert result["dry_run"] is False
        assert "freed" in result
        # ...but the persistence failure must be surfaced, not hidden.
        assert result.get("state_saved") is False
        assert "warning" in result
        captured = capsys.readouterr()
        assert "Warning" in (captured.out + captured.err)

    def test_save_state_returns_false_on_failure(self, tmp_path, monkeypatch):
        mgr = _make_manager(tmp_path, monkeypatch)
        self._break_state_open(monkeypatch)
        assert mgr._save_state() is False

    def test_save_state_returns_true_on_success(self, tmp_path, monkeypatch):
        mgr = _make_manager(tmp_path, monkeypatch)
        assert mgr._save_state() is True


def _drive_scheduler_iterations(mgr, iterations, monkeypatch):
    """Run start_scheduler()'s infinite `while True: await sleep(); ...` loop
    for exactly `iterations` passes over the agent list, then break out via
    CancelledError -- same pattern test_terminal_api.py uses for the idle
    reaper's identical infinite-loop shape."""
    calls = {"sleep": 0}

    async def fake_sleep(_seconds):
        calls["sleep"] += 1
        if calls["sleep"] > iterations:
            raise asyncio.CancelledError()

    monkeypatch.setattr(agents_manager_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(mgr.start_scheduler())


class TestSchedulerDryRunGuarantee:
    """Pins the most security-relevant line in this file: the unattended
    scheduler must NEVER execute a real (dry_run=False) agent command.
    Today, deleting `dry_run=True` from start_scheduler()'s
    `self.run_agent(agent_id, dry_run=True)` call breaks no test -- this
    closes that gap."""

    def test_scheduler_only_ever_calls_run_agent_with_dry_run_true(self, tmp_path, monkeypatch):
        mgr = _make_manager(tmp_path, monkeypatch)
        mgr.agents_state["cache_cleaner"] = {"enabled": True}

        calls = []

        def fake_run_agent(agent_id, dry_run=True):
            calls.append((agent_id, dry_run))
            return {"agent_id": agent_id, "dry_run": dry_run}

        monkeypatch.setattr(mgr, "run_agent", fake_run_agent)

        _drive_scheduler_iterations(mgr, iterations=1, monkeypatch=monkeypatch)

        assert calls, "expected the scheduler to call run_agent for an enabled agent"
        assert all(dry_run is True for _, dry_run in calls), (
            f"scheduler must only ever run agents in dry-run mode, got: {calls}"
        )


class TestSchedulerDryRunThrottling:
    """Regression test: an enabled agent used to get a fresh '[dry-run] ...'
    log line on every single hourly tick forever (dry-run never sets
    last_run, so the interval gate never trips) -- unbounded growth of
    agents.log and pure noise in /api/digest's log tail."""

    def test_repeated_ticks_do_not_call_run_agent_every_hour(self, tmp_path, monkeypatch):
        mgr = _make_manager(tmp_path, monkeypatch)
        mgr.agents_state["cache_cleaner"] = {"enabled": True}

        calls = []
        monkeypatch.setattr(
            mgr, "run_agent",
            lambda agent_id, dry_run=True: calls.append((agent_id, dry_run)) or {},
        )

        # cache_cleaner's interval_hours is 168 (weekly); drive 5 hourly
        # ticks. Without throttling this would call run_agent 5 times.
        _drive_scheduler_iterations(mgr, iterations=5, monkeypatch=monkeypatch)

        assert len(calls) == 1, (
            f"expected exactly one dry-run notice within the throttle window, got {calls}"
        )
