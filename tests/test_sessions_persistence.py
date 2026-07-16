"""Tests for session metadata persistence."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import disk_analyzer_web


def test_running_sessions_marked_interrupted_on_load(tmp_path, monkeypatch):
    # load_session_metadata() reads a JSON *list* of metadata entries, each
    # keyed by "id" (see disk_analyzer_web.py:93-117), not a dict keyed by
    # session id. Match that real on-disk shape here.
    sessions_file = tmp_path / "sessions_metadata.json"
    sessions_file.write_text(json.dumps([
        {"id": "abc123", "status": "running", "paths": ["/tmp"], "started_at": "2026-07-15T10:00:00"},
        {"id": "def456", "status": "completed", "paths": ["/tmp"], "started_at": "2026-07-15T09:00:00"},
    ]))
    monkeypatch.setattr(disk_analyzer_web, "SESSIONS_FILE", sessions_file)
    monkeypatch.setattr(disk_analyzer_web, "analysis_sessions", {})

    disk_analyzer_web.load_session_metadata()

    sessions = disk_analyzer_web.analysis_sessions
    assert sessions["abc123"]["status"] == "interrupted"
    assert sessions["def456"]["status"] == "completed"
