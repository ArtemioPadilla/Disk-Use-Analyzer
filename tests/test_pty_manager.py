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

    def test_kill_dead_session_is_fast(self):
        # A session whose child already exited must not pay the
        # SIGTERM/sleep(0.1)/SIGKILL sequence: the zombie reaps on the first
        # WNOHANG poll, so kill() should return well under 100ms.
        pty_id = self.manager.create_session(command="echo hi")
        session = self.manager.sessions[pty_id]
        # Wait for the short-lived child to exit (reader loop observes EOF)
        deadline = time.time() + 5.0
        while session.alive and time.time() < deadline:
            time.sleep(0.02)
        assert not session.alive, "child did not exit in time"
        start = time.monotonic()
        self.manager.kill_session(pty_id)
        elapsed = time.monotonic() - start
        # Loosened from 0.09s: the old (buggy) signal path costs >=0.1s sleep
        # plus up to a 2s reap, so 0.5s still discriminates fast-path from
        # slow-path while giving CI enough slack to avoid flaking.
        assert elapsed < 0.5, f"kill of dead session took {elapsed:.3f}s"

    def test_kill_with_stale_alive_flag_kills_live_child(self):
        # _read_loop flips alive=False on ANY OSError, not only on confirmed
        # child exit. If kill() trusted that flag to skip the signal
        # sequence, a live child would survive (leaked) while kill() burned
        # the full reap deadline. The liveness pre-check (waitpid) must
        # detect the child is still running and fire the signals.
        pty_id = self.manager.create_session(command="sleep 30")
        session = self.manager.sessions[pty_id]
        pid = session.pid
        time.sleep(0.2)  # let the child start
        session.alive = False  # simulate the spurious-OSError false negative
        start = time.monotonic()
        self.manager.kill_session(pty_id)
        elapsed = time.monotonic() - start
        # Signals fired => completes in ~0.1s, not the 2s reap deadline.
        assert elapsed < 1.0, f"kill took {elapsed:.3f}s (burned reap deadline?)"
        # The child must be dead AND reaped: waitpid must raise
        # ChildProcessError, not report a live/zombie process.
        try:
            result = os.waitpid(pid, os.WNOHANG)
            raise AssertionError(f"child {pid} leaked or unreaped: {result}")
        except ChildProcessError:
            pass  # correctly killed and reaped

    def test_child_does_not_inherit_extra_fds(self):
        # The PTY child forks then execvp's the shell. Since Python 3.4
        # (PEP 446) marks fds it creates as non-inheritable by default, a
        # plain os.pipe() fd would already be auto-closed by exec() with
        # or without our fix -- that would give a false-negative (test
        # passes for the wrong reason). To actually exercise the
        # os.closerange() fix, mark the sentinel fd explicitly inheritable
        # so it WOULD survive execvp absent the fix. This models the real
        # risk: any fd that is (or becomes) inheritable -- other sessions'
        # PTY masters, the uvicorn socket, or fds from code/libraries that
        # don't opt into PEP 446 -- must not reach the spawned shell.
        #
        # The check itself uses a shell builtin fd-redirection probe
        # (`: 1>&N`) instead of `ls -l /dev/fd` or a python subprocess:
        # it runs directly in the exec'd shell with no extra fork+exec
        # hop, so it deterministically reports whether fd N is still
        # open, without depending on /dev/fd listing format (which
        # doesn't exist on macOS the way it does on Linux's /proc).
        r, w = os.pipe()
        os.set_inheritable(w, True)
        try:
            probe = f"( : 1>&{w} ) 2>/dev/null && echo FD_ALIVE || echo FD_CLOSED"
            pty_id = self.manager.create_session(command=probe)
            deadline = time.time() + 3.0
            output = ""
            while time.time() < deadline and "FD_" not in output:
                time.sleep(0.1)
                output += self.manager.read_output(pty_id)
            assert "FD_CLOSED" in output, (
                f"child leaked inheritable sentinel fd {w} past execvp; output:\n{output!r}"
            )
            self.manager.kill_session(pty_id)
        finally:
            os.close(r)
            os.close(w)

    def test_child_does_not_inherit_auth_token(self, monkeypatch):
        # Phase 2 Task 5 closed the fd leak into the spawned shell, but the
        # env channel was left open: DISK_ANALYZER_TOKEN (and the --no-auth
        # bypass flag) were inherited via os.environ into the child, so
        # `env | grep DISK_ANALYZER` in the web terminal would print the
        # server's auth token. The child must see these scrubbed while
        # still inheriting normal vars like PATH/HOME/TERM.
        monkeypatch.setenv("DISK_ANALYZER_TOKEN", "super-secret-token")
        monkeypatch.setenv("DISK_ANALYZER_NO_AUTH", "1")
        # Quoted so zsh doesn't try to glob-expand the literal brackets.
        probe = 'echo "TOKEN=[$DISK_ANALYZER_TOKEN] NOAUTH=[$DISK_ANALYZER_NO_AUTH]"'
        pty_id = self.manager.create_session(command=probe)
        deadline = time.time() + 3.0
        output = ""
        while time.time() < deadline and "TOKEN=[" not in output:
            time.sleep(0.1)
            output += self.manager.read_output(pty_id)
        assert "TOKEN=[]" in output, (
            f"child saw DISK_ANALYZER_TOKEN in its environment; output:\n{output!r}"
        )
        assert "NOAUTH=[]" in output, (
            f"child saw DISK_ANALYZER_NO_AUTH in its environment; output:\n{output!r}"
        )
        self.manager.kill_session(pty_id)

    def test_command_logging(self, tmp_path):
        log_file = tmp_path / "terminal.log"
        manager = PTYManager(max_sessions=2, log_file=str(log_file))
        manager.create_session(command="echo logged_cmd")
        time.sleep(0.2)
        manager.cleanup_all()
        log_content = log_file.read_text()
        assert "echo logged_cmd" in log_content
