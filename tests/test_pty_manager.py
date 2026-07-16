import pytest
import time
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from pty_manager import PTYManager, PTYSession


class TestPTYManager:
    def setup_method(self):
        self.manager = PTYManager(max_sessions=2, idle_timeout=5)

    def teardown_method(self):
        self.manager.cleanup_all()

    def test_create_session_returns_pty_id(self):
        pty_id = self.manager.create_session()
        assert pty_id is not None
        assert isinstance(pty_id, str)
        assert len(pty_id) > 0

    def test_create_session_with_command(self):
        pty_id = self.manager.create_session(command="echo hello")
        assert pty_id in self.manager.sessions

    def test_max_sessions_enforced(self):
        self.manager.create_session()
        self.manager.create_session()
        with pytest.raises(RuntimeError, match="Maximum.*sessions"):
            self.manager.create_session()

    def test_read_output(self):
        pty_id = self.manager.create_session(command="echo test_output_marker")
        time.sleep(0.5)
        output = self.manager.read_output(pty_id)
        assert "test_output_marker" in output

    def test_write_input(self):
        pty_id = self.manager.create_session()
        self.manager.write_input(pty_id, "echo pty_write_test\n")
        time.sleep(0.5)
        output = self.manager.read_output(pty_id)
        assert "pty_write_test" in output

    def test_resize(self):
        pty_id = self.manager.create_session()
        self.manager.resize(pty_id, cols=120, rows=40)

    def test_kill_session(self):
        pty_id = self.manager.create_session()
        self.manager.kill_session(pty_id)
        assert pty_id not in self.manager.sessions

    def test_kill_nonexistent_raises(self):
        with pytest.raises(KeyError):
            self.manager.kill_session("nonexistent")

    def test_list_sessions(self):
        id1 = self.manager.create_session()
        id2 = self.manager.create_session(command="echo hi")
        sessions = self.manager.list_sessions()
        assert len(sessions) == 2
        ids = [s['pty_id'] for s in sessions]
        assert id1 in ids
        assert id2 in ids

    def test_blocked_command_rejected(self):
        with pytest.raises(ValueError, match="[Bb]locked"):
            self.manager.create_session(command="rm -rf /")

    def test_kill_reaps_child_no_zombie(self):
        pty_id = self.manager.create_session()
        session = self.manager.sessions[pty_id]
        pid = session.pid
        self.manager.kill_session(pty_id)
        # After kill, the pid must be fully reaped: waitpid must raise
        # ChildProcessError (no such child) rather than find a zombie.
        try:
            result = os.waitpid(pid, os.WNOHANG)
            raise AssertionError(f"child {pid} was not reaped by kill(): {result}")
        except ChildProcessError:
            pass  # correctly reaped

    def test_cleanup_idle_does_not_hold_lock_during_kill(self):
        # kill() can block up to KILL_REAP_TIMEOUT; if cleanup_idle held the
        # manager lock while killing, every other session would freeze.
        manager = self.manager

        class FakeSession:
            def __init__(self):
                self.pty_id = "fake_idle"
                self.command = None
                self.created_at = "now"
                self.alive = True
                self.last_activity = 0  # stale => considered idle
                self.lock_acquired_during_kill = None

            def kill(self):
                # If cleanup_idle released the manager lock before calling
                # kill(), this acquire succeeds immediately.
                acquired = manager._lock.acquire(timeout=0.5)
                self.lock_acquired_during_kill = acquired
                if acquired:
                    manager._lock.release()
                self.alive = False

        fake = FakeSession()
        manager.sessions["fake_idle"] = fake
        manager.cleanup_idle()
        assert fake.lock_acquired_during_kill is True, (
            "cleanup_idle held the manager lock while calling kill()"
        )
        assert "fake_idle" not in manager.sessions

    def test_command_logging(self, tmp_path):
        log_file = tmp_path / "terminal.log"
        manager = PTYManager(max_sessions=2, log_file=str(log_file))
        manager.create_session(command="echo logged_cmd")
        time.sleep(0.2)
        manager.cleanup_all()
        log_content = log_file.read_text()
        assert "echo logged_cmd" in log_content
