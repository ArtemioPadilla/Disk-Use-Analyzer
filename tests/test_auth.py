"""Tests for token auth on the HTTP API."""
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient


def _load_app(monkeypatch, *, token=None, no_auth=False):
    """Reload disk_analyzer_web with a controlled auth env, return (module, client)."""
    if no_auth:
        monkeypatch.setenv("DISK_ANALYZER_NO_AUTH", "1")
        monkeypatch.delenv("DISK_ANALYZER_TOKEN", raising=False)
    else:
        monkeypatch.setenv("DISK_ANALYZER_NO_AUTH", "0")
        monkeypatch.setenv("DISK_ANALYZER_TOKEN", token or "test-token-abc")
    import disk_analyzer_web
    importlib.reload(disk_analyzer_web)
    return disk_analyzer_web, TestClient(disk_analyzer_web.app)


class TestHttpAuth:
    def test_api_route_without_token_is_401(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        resp = client.get("/api/system/info")
        assert resp.status_code == 401

    def test_api_route_with_valid_token_is_ok(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        resp = client.get("/api/system/info", headers={"X-Auth-Token": "secret1"})
        assert resp.status_code == 200

    def test_api_route_with_wrong_token_is_401(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        resp = client.get("/api/system/info", headers={"X-Auth-Token": "nope"})
        assert resp.status_code == 401

    def test_destructive_route_without_token_is_401(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        resp = client.post("/api/cleanup/preview", json={"paths": [], "dry_run": True})
        assert resp.status_code == 401

    def test_static_root_is_open(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        # "/" serves the SPA index (or 404 if no build) but must NOT be 401
        resp = client.get("/")
        assert resp.status_code != 401

    def test_no_auth_mode_allows_api(self, monkeypatch):
        _, client = _load_app(monkeypatch, no_auth=True)
        resp = client.get("/api/system/info")
        assert resp.status_code == 200

    def test_non_ascii_token_header_is_401_not_500(self, monkeypatch):
        """secrets.compare_digest() raises TypeError on non-ASCII `str` args,
        and Starlette decodes headers as latin-1 -- a hostile
        "X-Auth-Token: café" header must fail closed (401), not crash the
        request with an unhandled TypeError (500). httpx/TestClient refuses
        to even build a request with a non-ASCII str header value, so this
        drives _token_is_valid() directly with the same kind of string
        Starlette would hand it (a latin-1 decode of UTF-8 bytes)."""
        module, _ = _load_app(monkeypatch, token="secret1")
        hostile = "café".encode("utf-8").decode("latin-1")
        assert module._token_is_valid(hostile) is False

    def test_non_ascii_token_header_via_raw_asgi_is_401(self, monkeypatch):
        """End-to-end version of the above via a raw ASGI request (bypassing
        httpx's client-side header validation) to prove the whole request
        path -- not just the helper function -- fails closed instead of 500."""
        import asyncio

        module, _ = _load_app(monkeypatch, token="secret1")

        async def _raw_get(app, headers):
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/api/system/info",
                "raw_path": b"/api/system/info",
                "query_string": b"",
                "headers": headers,
                "http_version": "1.1",
                "scheme": "http",
                "server": ("testserver", 80),
                "client": ("testclient", 123),
                "root_path": "",
            }
            messages = []

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            await app(scope, receive, send)
            return next(m["status"] for m in messages if m["type"] == "http.response.start")

        status = asyncio.run(
            _raw_get(module.app, [(b"x-auth-token", "café".encode("utf-8"))])
        )
        assert status == 401


import contextlib

import pytest
from starlette.websockets import WebSocketDisconnect


@contextlib.contextmanager
def pytest_raises_ws_close(expected_code=1008):
    # Starlette's TestClient raises WebSocketDisconnect when the server closes
    # before/at accept. We additionally assert the close code is the auth
    # gate's 1008 (policy violation) so this test can't pass "by accident"
    # via some other pre-accept close path (e.g. the terminal WS's unrelated
    # "no such pty session" -> 4004 close, which fires if the auth check
    # isn't actually first).
    with pytest.raises(WebSocketDisconnect) as exc_info:
        yield
    assert exc_info.value.code == expected_code


class TestWebSocketAuth:
    def test_progress_ws_without_token_rejected(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        with pytest_raises_ws_close():
            with client.websocket_connect("/ws/does-not-exist"):
                pass

    def test_progress_ws_with_token_accepts(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        # A valid token must let the handshake through (session unknown is fine)
        with client.websocket_connect("/ws/unknown-session?token=secret1") as ws:
            ws.send_text("ping")
            assert ws.receive_text() == "pong"

    def test_terminal_ws_without_token_rejected(self, monkeypatch):
        _, client = _load_app(monkeypatch, token="secret1")
        # Uses a pty_id that doesn't exist. Asserting code==1008 (not the
        # existence check's 4004) proves the token gate runs BEFORE the
        # pty_id lookup, so unauthenticated clients can't probe which
        # sessions exist.
        with pytest_raises_ws_close():
            with client.websocket_connect("/ws/terminal/whatever"):
                pass
