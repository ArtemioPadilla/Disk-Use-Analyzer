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

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, body


def _reload_app(monkeypatch):
    monkeypatch.setenv("DISK_ANALYZER_NO_AUTH", "1")
    importlib.reload(disk_analyzer_web)
    return disk_analyzer_web.app


class TestSpaCatchAllTraversal:
    def test_traversal_does_not_leak_etc_hosts(self, monkeypatch):
        app = _reload_app(monkeypatch)
        # Enough "../" to clear the repo's directory depth and reach the
        # filesystem root; extra "../" beyond root are harmless no-ops.
        traversal_path = "/" + "../" * 15 + "etc/hosts"

        status, body = asyncio.run(_raw_get(app, traversal_path))

        # Real /etc/hosts starts with this marker on macOS/Linux. If this
        # ever shows up in the response, we've leaked an arbitrary file.
        assert b"Host Database" not in body
        assert not (status == 200 and b"localhost" in body and b"<!DOCTYPE" not in body)

    def test_traversal_does_not_leak_sessions_metadata(self, monkeypatch, tmp_path):
        app = _reload_app(monkeypatch)
        # Plant a fake "secret" file one level above the repo root and try to
        # reach it the same way the live exploit reached sessions_metadata.json.
        secret_dir = tmp_path
        secret_file = secret_dir / "definitely_secret.json"
        secret_file.write_text('{"leaked": true}')

        # Compute a relative path from web/dist up to the planted file.
        astro_dist = (Path(__file__).parent.parent / "web" / "dist").resolve()
        try:
            rel = Path("/") / Path(secret_file).relative_to(astro_dist.anchor)
        except ValueError:
            rel = Path("/") / secret_file
        # Build an explicit "../.. " climb to the file's absolute path components.
        depth = len(astro_dist.parts) - 1
        traversal_path = "/" + "../" * depth + str(secret_file).lstrip("/")

        status, body = asyncio.run(_raw_get(app, traversal_path))

        assert b"definitely_secret" not in body
        assert b"leaked" not in body

    def test_legitimate_unmatched_route_still_falls_back_to_spa(self, monkeypatch):
        """Non-malicious unknown routes must keep working as SPA client-side
        routes (existing behavior) -- the fix must not turn every 404-ish
        route into a hard error."""
        app = _reload_app(monkeypatch)
        status, body = asyncio.run(_raw_get(app, "/some/totally/unknown/route"))
        assert status == 200
