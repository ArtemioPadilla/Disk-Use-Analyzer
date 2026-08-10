"""Tests for token auth on the HTTP API.

Only two distinct module configurations are actually exercised here: auth ON
with a known token ("secret1"), and `--no-auth`. Reloading disk_analyzer_web
for every single test (nine reloads for eleven tests) rebuilds a
ThreadPoolExecutor, a PTYManager, an AgentsManager, and re-runs
RESULTS_DIR.mkdir() against the real $HOME each time -- wasted work when only
two configurations exist. `auth_app` and `noauth_app` below are module-scoped
so each configuration is loaded exactly once and shared by every test that
needs it.

NO_AUTH/AUTH_TOKEN are plain module globals that `_token_is_valid`/
`auth_middleware` read at call time (not baked into a per-app closure), and
importlib.reload() re-executes into the SAME module `__dict__` (sys.modules
caches the module object). That means reloading for `noauth_app` mutates the
very globals `auth_app`'s already-built client also reads -- so whichever
fixture reloaded LAST determines what EVERY cached client sees next, no
matter which one it was built from.

An earlier version of this file "fixed" that by ordering `noauth_app`'s one
test last in the file. That only holds for a full top-to-bottom run of this
file; it breaks under `pytest --lf`, explicit node-ID subsetting run in a
different order, `-k` filters that skip some tests, or a random-order
plugin -- exactly the kind of invocations CI uses. The `_enforce_auth_globals`
autouse fixture below is the real fix: it re-asserts NO_AUTH/AUTH_TOKEN to
the values THIS test expects immediately before every test body runs,
regardless of what any earlier test (in any order) left behind -- mirroring
the pattern `tests/conftest.py` already uses for every other test file.
Reordering is no longer load-bearing for correctness; tests are kept grouped
by fixture only for readability.
"""
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

TOKEN = "secret1"
_ENV_KEYS = ("DISK_ANALYZER_NO_AUTH", "DISK_ANALYZER_TOKEN")


def _reload_with_env(**env):
    """Reload disk_analyzer_web with a controlled auth env.

    Returns (module, prev_env) so the caller can restore exactly what was
    there before. Uses os.environ directly (not the `monkeypatch` fixture)
    because this runs inside module-scoped fixtures, and `monkeypatch` is
    function-scoped -- pytest forbids a narrower-scoped fixture depending on
    it.
    """
    prev = {k: os.environ.get(k) for k in _ENV_KEYS}
    for k in _ENV_KEYS:
        os.environ.pop(k, None)
    os.environ.update(env)
    import disk_analyzer_web
    importlib.reload(disk_analyzer_web)
    return disk_analyzer_web, prev


def _restore_env(prev):
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(scope="module")
def auth_app():
    """Module loaded once with auth ON and a known token ("secret1").

    Correctness across tests does NOT depend on this running before
    `noauth_app` -- `_enforce_auth_globals` below re-asserts the right
    globals before every test regardless of load order.
    """
    module, prev = _reload_with_env(DISK_ANALYZER_NO_AUTH="0", DISK_ANALYZER_TOKEN=TOKEN)
    client = TestClient(module.app)
    yield module, client
    _restore_env(prev)


@pytest.fixture(scope="module")
def noauth_app():
    """Module loaded once with --no-auth. See `auth_app` docstring: ordering
    relative to it is no longer a correctness requirement."""
    module, prev = _reload_with_env(DISK_ANALYZER_NO_AUTH="1")
    client = TestClient(module.app)
    yield module, client
    _restore_env(prev)


@pytest.fixture(autouse=True)
def _enforce_auth_globals(request):
    """Force NO_AUTH/AUTH_TOKEN to the state THIS test expects, no matter
    what any other test in this module already ran (in any order).

    `auth_app`/`noauth_app` are module-scoped, so after their first use they
    just hand back a cached (module, client) pair without reloading again --
    but NO_AUTH/AUTH_TOKEN are read fresh off the module's globals on every
    request, and those globals are shared, mutable state. If `noauth_app`'s
    one reload has already happened by the time some `auth_app` test runs
    (e.g. because pytest ran that node ID first via `-k`/`--lf`/an explicit
    node-ID list/a random-order plugin), that test would silently run
    against a no-auth server. This fixture is the actual fix: it re-pins the
    globals to the correct value right before every test body executes,
    exactly mirroring what `tests/conftest.py`'s `_default_no_auth` does for
    every other test module.
    """
    import disk_analyzer_web
    if "noauth_app" in request.fixturenames:
        disk_analyzer_web.NO_AUTH = True
        disk_analyzer_web.AUTH_TOKEN = None
    else:
        disk_analyzer_web.NO_AUTH = False
        disk_analyzer_web.AUTH_TOKEN = TOKEN


class TestHttpAuth:
    def test_api_route_without_token_is_401(self, auth_app):
        _, client = auth_app
        resp = client.get("/api/system/info")
        assert resp.status_code == 401

    def test_api_route_with_valid_token_is_ok(self, auth_app):
        _, client = auth_app
        resp = client.get("/api/system/info", headers={"X-Auth-Token": TOKEN})
        assert resp.status_code == 200
        # A bare `== 200` above would ALSO pass if the module were wrongly
        # in no-auth mode (e.g. global-state corruption from another test
        # running out of order) -- it would silently stop testing that the
        # token is actually being checked. Assert the negative case too so a
        # corrupted state fails loudly here instead of passing for the
        # wrong reason.
        resp_wrong = client.get("/api/system/info", headers={"X-Auth-Token": "definitely-wrong"})
        assert resp_wrong.status_code == 401

    def test_api_route_with_wrong_token_is_401(self, auth_app):
        _, client = auth_app
        resp = client.get("/api/system/info", headers={"X-Auth-Token": "nope"})
        assert resp.status_code == 401

    def test_destructive_route_without_token_is_401(self, auth_app):
        _, client = auth_app
        resp = client.post("/api/cleanup/preview", json={"paths": [], "dry_run": True})
        assert resp.status_code == 401

    def test_static_root_is_open(self, auth_app):
        _, client = auth_app
        # "/" serves the SPA index (or 404 if no build) but must NOT be 401
        resp = client.get("/")
        assert resp.status_code != 401

    def test_non_ascii_token_header_is_401_not_500(self, auth_app):
        """secrets.compare_digest() raises TypeError on non-ASCII `str` args,
        and Starlette decodes headers as latin-1 -- a hostile
        "X-Auth-Token: café" header must fail closed (401), not crash the
        request with an unhandled TypeError (500). httpx/TestClient refuses
        to even build a request with a non-ASCII str header value, so this
        drives _token_is_valid() directly with the same kind of string
        Starlette would hand it (a latin-1 decode of UTF-8 bytes)."""
        module, _ = auth_app
        hostile = "café".encode("utf-8").decode("latin-1")
        assert module._token_is_valid(hostile) is False

    def test_non_ascii_token_header_via_raw_asgi_is_401(self, auth_app):
        """End-to-end version of the above via a raw ASGI request (bypassing
        httpx's client-side header validation) to prove the whole request
        path -- not just the helper function -- fails closed instead of 500."""
        import asyncio

        module, _ = auth_app

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
    def test_progress_ws_without_token_rejected(self, auth_app):
        _, client = auth_app
        with pytest_raises_ws_close():
            with client.websocket_connect("/ws/does-not-exist"):
                pass

    def test_progress_ws_with_token_accepts(self, auth_app):
        module, client = auth_app
        # A valid token must let the handshake through (session unknown is fine)
        try:
            with client.websocket_connect("/ws/unknown-session?token=secret1") as ws:
                ws.send_text("ping")
                assert ws.receive_text() == "pong"
        finally:
            # The endpoint only removes the connection from
            # websocket_connections when it observes WebSocketDisconnect
            # while blocked on receive_text() inside its own server-side
            # task; that happens asynchronously relative to the TestClient's
            # `with` block exiting here, so it isn't reliably cleaned up yet.
            # Without this, the entry leaks and contaminates later tests
            # that inspect websocket_connections.
            module.websocket_connections.pop("unknown-session", None)

    def test_terminal_ws_without_token_rejected(self, auth_app):
        _, client = auth_app
        # Uses a pty_id that doesn't exist. Asserting code==1008 (not the
        # existence check's 4004) proves the token gate runs BEFORE the
        # pty_id lookup, so unauthenticated clients can't probe which
        # sessions exist.
        with pytest_raises_ws_close():
            with client.websocket_connect("/ws/terminal/whatever"):
                pass


def test_no_auth_mode_allows_api(noauth_app):
    """No longer needs to be the last test in the file: `_enforce_auth_globals`
    re-pins the module's auth globals to no-auth immediately before this
    test body runs, regardless of what ran before or after it."""
    _, client = noauth_app
    resp = client.get("/api/system/info")
    assert resp.status_code == 200
