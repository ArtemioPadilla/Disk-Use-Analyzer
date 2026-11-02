"""Regression test for the SPA catch-all path-traversal vulnerability
(CVE-worthy finding: unauthenticated arbitrary file read via GET /{path:path}).

IMPORTANT: Starlette's TestClient (backed by httpx) NORMALIZES ".." out of
URLs before they ever reach the ASGI app, so a plain
`client.get("/../../etc/hosts")` cannot reproduce this bug -- it would pass
even against the vulnerable code. These tests instead drive the ASGI `app`
callable directly with a hand-built scope/raw_path, exactly like a real
uvicorn socket would deliver an attacker-controlled request line.
"""
import asyncio
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import disk_analyzer_web


async def _raw_get(app, raw_path: str) -> tuple[int, bytes]:
    """Send a GET request straight into the ASGI app with a literal,
    unnormalized path -- bypassing any client-side URL normalization."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": raw_path,
        "raw_path": raw_path.encode(),
        "query_string": b"",
        "headers": [],
        "http_version": "1.1",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 123),
        "root_path": "",
    }
    messages = []
    entregado = False

    async def receive():
        # Like a real server: the (empty) body once, then nothing until the
        # client leaves. Answering http.disconnect here instead makes
        # Starlette 1.x drop the response body, and these tests would pass
        # against a vulnerable server because there is no body to find.
        nonlocal entregado
        if entregado:
            await asyncio.Event().wait()
        entregado = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, body


MARCA_SPA = b"<!DOCTYPE html><title>spa de prueba</title>"


def _reload_app(monkeypatch, tmp_path):
    """The app, serving a fixture web/dist: the real one is gitignored, and
    without a dist the handler returns before reaching the checks under test."""
    monkeypatch.setenv("DISK_ANALYZER_NO_AUTH", "1")
    importlib.reload(disk_analyzer_web)
    dist = tmp_path / "web" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_bytes(MARCA_SPA)
    monkeypatch.setattr(disk_analyzer_web, "astro_dist", dist)
    return disk_analyzer_web.app, dist


class TestSpaCatchAllTraversal:
    def test_traversal_does_not_leak_etc_hosts(self, monkeypatch, tmp_path):
        app, _ = _reload_app(monkeypatch, tmp_path)
        # Enough "../" to clear the directory depth and reach the filesystem
        # root; extra "../" beyond root are harmless no-ops.
        traversal_path = "/" + "../" * 30 + "etc/hosts"

        status, body = asyncio.run(_raw_get(app, traversal_path))

        # Real /etc/hosts starts with this marker on macOS. If this ever shows
        # up in the response, we've leaked an arbitrary file.
        assert b"Host Database" not in body
        assert status == 200
        assert body == MARCA_SPA

    def test_traversal_does_not_leak_a_file_outside_dist(self, monkeypatch, tmp_path):
        app, dist = _reload_app(monkeypatch, tmp_path)
        # Plant a "secret" outside dist and climb to it the same way the live
        # exploit reached sessions_metadata.json.
        (tmp_path / "definitely_secret.json").write_text('{"leaked": true}')
        traversal_path = "/../../definitely_secret.json"
        assert (dist / "../../definitely_secret.json").is_file()

        status, body = asyncio.run(_raw_get(app, traversal_path))

        assert b"leaked" not in body
        assert body == MARCA_SPA

    def test_legitimate_file_inside_dist_is_served(self, monkeypatch, tmp_path):
        """The checks must not turn every path into the fallback."""
        app, dist = _reload_app(monkeypatch, tmp_path)
        (dist / "favicon.svg").write_bytes(b"<svg/>")

        status, body = asyncio.run(_raw_get(app, "/favicon.svg"))

        assert status == 200
        assert body == b"<svg/>"

    def test_legitimate_unmatched_route_still_falls_back_to_spa(self, monkeypatch, tmp_path):
        """Non-malicious unknown routes must keep working as SPA client-side
        routes (existing behavior) -- the fix must not turn every 404-ish
        route into a hard error."""
        app, _ = _reload_app(monkeypatch, tmp_path)
        status, body = asyncio.run(_raw_get(app, "/some/totally/unknown/route"))
        assert status == 200
        assert body == MARCA_SPA
