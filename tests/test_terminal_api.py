import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from disk_analyzer_web import app


class TestTerminalAPI:
    def setup_method(self):
        self.client = TestClient(app)

    def test_create_terminal_session(self):
        r = self.client.post('/api/terminal/create', json={})
        assert r.status_code == 200
        data = r.json()
        assert 'pty_id' in data
        assert 'created_at' in data
        self.client.delete(f'/api/terminal/{data["pty_id"]}')

    def test_create_terminal_with_command(self):
        r = self.client.post('/api/terminal/create', json={'command': 'echo hello'})
        assert r.status_code == 200
        data = r.json()
        assert 'pty_id' in data
        self.client.delete(f'/api/terminal/{data["pty_id"]}')

    def test_create_terminal_blocked_command(self):
        r = self.client.post('/api/terminal/create', json={'command': 'rm -rf /'})
        assert r.status_code == 400

    def test_create_terminal_beyond_max_sessions_is_429(self, monkeypatch):
        """The manager raises RuntimeError past max_sessions; the endpoint must
        surface it as 429.

        `tests/test_pty_manager.py` already proves PTYManager itself raises
        RuntimeError past the limit, but nothing checked the HTTP endpoint
        translates that into a 429 -- and that path changed in Phase 2 when
        create_session moved onto asyncio.to_thread (disk_analyzer_web.py,
        the /api/terminal/create handler). This drives the REAL
        PTYManager.create_session (not a mock) by shrinking max_sessions to
        0, so the length check `len(self.sessions) >= self.max_sessions`
        fires immediately -- no pty is actually spawned, keeping this fast
        and deterministic -- while still proving asyncio.to_thread
        propagates the genuine RuntimeError raised inside the manager's
        lock, not just a hand-crafted one.
        """
        import disk_analyzer_web

        monkeypatch.setattr(disk_analyzer_web.pty_manager, "max_sessions", 0)
        resp = self.client.post('/api/terminal/create', json={})
        assert resp.status_code == 429

    def test_list_terminal_sessions(self):
        r1 = self.client.post('/api/terminal/create', json={})
        pty_id = r1.json()['pty_id']
        r2 = self.client.get('/api/terminal/sessions')
        assert r2.status_code == 200
        sessions = r2.json()
        assert any(s['pty_id'] == pty_id for s in sessions)
        self.client.delete(f'/api/terminal/{pty_id}')

    def test_resize_terminal(self):
        r = self.client.post('/api/terminal/create', json={})
        pty_id = r.json()['pty_id']
        r2 = self.client.post(f'/api/terminal/{pty_id}/resize', json={'cols': 120, 'rows': 40})
        assert r2.status_code == 200
        self.client.delete(f'/api/terminal/{pty_id}')

    def test_kill_terminal(self):
        r = self.client.post('/api/terminal/create', json={})
        pty_id = r.json()['pty_id']
        r2 = self.client.delete(f'/api/terminal/{pty_id}')
        assert r2.status_code == 200
        r3 = self.client.delete(f'/api/terminal/{pty_id}')
        assert r3.status_code == 404

    def test_kill_nonexistent(self):
        r = self.client.delete('/api/terminal/nonexistent')
        assert r.status_code == 404


def test_idle_reaper_task_is_registered():
    """startup must schedule the idle-session reaper."""
    import disk_analyzer_web
    assert hasattr(disk_analyzer_web, "_idle_terminal_reaper"), (
        "expected an _idle_terminal_reaper coroutine registered at startup"
    )


def test_idle_reaper_calls_cleanup_and_survives_errors(monkeypatch):
    """One reaper iteration must call cleanup_idle(); a raising cleanup must not kill the loop."""
    import asyncio
    import disk_analyzer_web

    calls = {"cleanup": 0, "sleep": 0}

    def fake_cleanup():
        calls["cleanup"] += 1
        if calls["cleanup"] == 1:
            # Must be swallowed by the reaper so the loop survives
            raise RuntimeError("boom")

    async def fake_sleep(_seconds):
        calls["sleep"] += 1
        if calls["sleep"] > 2:
            # Break out of the infinite loop after two full iterations
            raise asyncio.CancelledError()

    monkeypatch.setattr(disk_analyzer_web.pty_manager, "cleanup_idle", fake_cleanup)
    monkeypatch.setattr(disk_analyzer_web.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(disk_analyzer_web._idle_terminal_reaper())

    # cleanup ran on both iterations: the RuntimeError on the first
    # iteration was swallowed and the loop kept going.
    assert calls["cleanup"] == 2


def test_startup_registers_idle_reaper_task():
    """The app lifespan (startup) must actually create the reaper task."""
    import disk_analyzer_web

    disk_analyzer_web._idle_reaper_task = None
    # `with` triggers the lifespan; bare TestClient(app) does not run startup.
    with TestClient(disk_analyzer_web.app):
        assert disk_analyzer_web._idle_reaper_task is not None, (
            "startup_event did not create the _idle_terminal_reaper task"
        )
