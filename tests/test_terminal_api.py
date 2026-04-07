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
