"""Tests for the export endpoints (json / csv / html)."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import disk_analyzer_web
from disk_analyzer_web import app


@pytest.fixture
def completed_session(monkeypatch):
    """Register a completed session with a minimal but realistic report.

    The report dict must satisfy both the CSV export (which reads
    large_files[*].{path,size,extension,age_days,is_cache}) and the HTML
    export, which delegates to DiskAnalyzer.generate_html_report(). That
    method indexes several summary/report keys directly (not via .get()),
    so a report missing any of them raises a KeyError deep inside HTML
    generation. The keys below were discovered by calling
    generate_html_report() directly against a minimal fixture and adding
    whatever key it complained about next (recoverable_space,
    large_files_count, top_file_types, docker, disk_usage, ...) -- all
    values are invented, nothing is read from the real machine.
    """
    session_id = "test-export-session"
    report = {
        "summary": {
            "total_size": 1024,
            "files_scanned": 2,
            "errors_count": 0,
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-01-01T00:00:01",
            "duration_seconds": 1,
            "recoverable_space": 512,
            "large_files_count": 2,
        },
        "large_files": [
            {"path": "/fake/a.bin", "size": 2048, "extension": ".bin",
             "age_days": 5, "is_cache": False},
            {"path": "/fake/b.log", "size": 1024, "extension": ".log",
             "age_days": 30, "is_cache": True},
        ],
        "top_directories": [],
        "cache_locations": [],
        "recommendations": [],
        "top_file_types": [],
        "docker": None,
        "disk_usage": None,
    }
    monkeypatch.setitem(
        disk_analyzer_web.analysis_sessions, session_id,
        {"status": "completed", "results": [{"path": "/fake", "report": report}]},
    )
    return session_id


class TestExport:
    def setup_method(self):
        self.client = TestClient(app)

    def test_json_export_returns_the_report(self, completed_session):
        resp = self.client.get(f"/api/export/{completed_session}/json")
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]

    def test_csv_export_has_a_header_and_the_files(self, completed_session):
        resp = self.client.get(f"/api/export/{completed_session}/csv")
        assert resp.status_code == 200
        body = resp.text
        assert body.startswith("Path,Size,Type")
        assert "/fake/a.bin" in body

    def test_html_export_is_a_document(self, completed_session):
        resp = self.client.get(f"/api/export/{completed_session}/html")
        assert resp.status_code == 200
        assert resp.text.lstrip().lower().startswith("<!doctype html")

    def test_unknown_format_is_rejected(self, completed_session):
        resp = self.client.get(f"/api/export/{completed_session}/pdf")
        assert resp.status_code == 400

    def test_unknown_session_is_404(self):
        resp = self.client.get("/api/export/does-not-exist/json")
        assert resp.status_code == 404
