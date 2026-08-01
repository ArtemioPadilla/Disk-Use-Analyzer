# Plan de Mejoras — Fase 2: Seguridad

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar los cuatro huecos de seguridad verificados en el servidor web (sin auth, CORS `*`, agents que ejecutan `rm -rf` sin confirmación, fds heredados por el shell del terminal) sin romper el flujo local de `make web`.

**Architecture:** Auth por token de sesión generado al arrancar (impreso en el banner), validado por un middleware HTTP para `/api/*` y por `Depends` en los dos WebSockets. El token viaja en header `X-Auth-Token` (REST) y query param `?token=` (WS), nunca en cookie — así CSRF queda estructuralmente descartado. Flag `--no-auth` como escape explícito. Agents pasan a dry-run + confirmación. El fork del PTY cierra fds heredados. Cambios acotados sobre `disk_analyzer_web.py`, `agents_manager.py`, `pty_manager.py` y el frontend (`web/src/lib/api.ts`, hooks WS, bootstrap de token).

**Tech Stack:** Python 3.13, FastAPI/Starlette, `secrets`, pytest + `fastapi.testclient.TestClient`; frontend Astro/React (TypeScript).

## Global Constraints

- Tests corren con `venv-web/bin/python -m pytest tests/ -v` desde la raíz (baseline actual: 39 passed). Full suite verde antes de cada commit.
- Mensajes user-facing en español; comentarios de código en inglés.
- **Auth ON por defecto.** `make web` sigue siendo de un solo comando: el usuario abre el link `?token=...` que imprime el banner de arranque. `--no-auth` es opt-in explícito con advertencia.
- El token se genera con `secrets.token_urlsafe(32)` y se compara con `secrets.compare_digest`.
- **Propagación bajo `reload=True`:** uvicorn re-importa el módulo en un subproceso worker; el token/flag deben viajar por **variable de entorno** (`DISK_ANALYZER_TOKEN`, `DISK_ANALYZER_NO_AUTH`), leídas a nivel de módulo, no por `app.state` ni globals de `__main__`.
- No romper las rutas estáticas/SPA (`/`, `/{path:path}`, mounts `/static` y `/_astro`) — quedan abiertas (sirven solo JS/CSS).
- Ninguna operación destructiva de agents sin dry-run y sin confirmación explícita.
- Frontend: no meter el token en cookie ni en `localStorage` persistente entre reinicios; usar `sessionStorage` y limpiar el token de la URL con `history.replaceState`.

---

### Task 1: Auth por token para el API HTTP + CORS lockdown + flag `--no-auth`

Introduce el token de sesión y un middleware HTTP que exige `X-Auth-Token` en toda ruta `/api/*` (menos las estáticas). Cierra CORS a orígenes de dev explícitos. Agrega `--no-auth` y la impresión del link con token en el banner, propagando por env var para sobrevivir el reload.

**Files:**
- Modify: `disk_analyzer_web.py` — bloque de imports (~19-24), config del token a nivel de módulo (nuevo, tras los imports ~30), `CORSMiddleware` (~39-46), middleware de auth (nuevo), bloque `__main__` (~1305-1346)
- Test: `tests/test_auth.py` (nuevo)

**Interfaces:**
- Produces (a nivel de módulo, leídos por el worker de reload):
  - `AUTH_TOKEN: str | None` — el token activo, o `None` si NO_AUTH
  - `NO_AUTH: bool`
  - `require_token(request) -> None` lógica de validación reutilizable (usada por el middleware; la variante WS es Task 2)
- Produces (comportamiento): toda ruta que empiece con `/api/` responde `401` sin header `X-Auth-Token` válido; las rutas `/`, `/{path:path}` y los mounts estáticos quedan abiertas. Con `NO_AUTH=True` el middleware es no-op.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_auth.py`:

```python
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
```

Nota para el implementador: `importlib.reload` re-ejecuta el módulo leyendo las env vars — es la forma de probar los dos modos sin subprocesos. Si el reload provoca efectos colaterales molestos (p. ej. arranque de tareas), aísla la config del token en variables de módulo que solo se lean en el middleware (no en import-time side effects) y ajusta el helper. Corre los tests en serie.

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `venv-web/bin/python -m pytest tests/test_auth.py -v`
Expected: FAIL — sin middleware, `/api/system/info` responde 200 sin token.

- [ ] **Step 3: Implementar token + middleware + CORS + `__main__`**

En `disk_analyzer_web.py`, tras los imports, agregar imports faltantes y la config del token a nivel de módulo:

```python
import os
import secrets
from starlette.responses import JSONResponse as _StarletteJSONResponse

# --- Auth configuration (read at module import so the uvicorn reload worker sees it) ---
NO_AUTH = os.environ.get("DISK_ANALYZER_NO_AUTH") == "1"
AUTH_TOKEN = None if NO_AUTH else os.environ.get("DISK_ANALYZER_TOKEN")


def _token_is_valid(provided: str | None) -> bool:
    if NO_AUTH:
        return True
    if not AUTH_TOKEN or not provided:
        return False
    return secrets.compare_digest(provided, AUTH_TOKEN)
```

Reemplazar el bloque `CORSMiddleware` (~39-46):

```python
# CORS: only the Astro dev server needs cross-origin access (make web-dev).
# In production the frontend is served same-origin from web/dist/.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["X-Auth-Token", "Content-Type"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Require a valid token for /api/* routes; static/SPA routes stay open."""
    if not NO_AUTH and request.url.path.startswith("/api/"):
        provided = request.headers.get("X-Auth-Token")
        if not _token_is_valid(provided):
            return _StarletteJSONResponse(
                {"detail": "Token inválido o ausente"}, status_code=401
            )
    return await call_next(request)
```

Nota: el middleware se registra DESPUÉS de `CORSMiddleware` en el código, pero Starlette ejecuta los middlewares en orden inverso al registro — verificar que las respuestas 401 lleven headers CORS (para que el navegador las lea en dev). Si no, registrar el de auth antes del CORS. Documentar en el reporte cuál orden quedó.

Reemplazar el bloque `__main__` (~1305-1346) para generar/propagar el token y el flag, e imprimir el link:

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Disk Analyzer Web Server")
    parser.add_argument("--min-size", type=float, default=10,
                        help="Default minimum file size in MB (default: 10, use 0 for all files)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--no-auth", action="store_true",
                        help="Disable token auth (only on a fully trusted, isolated network)")
    args = parser.parse_args()

    app.state.default_min_size_mb = args.min_size

    # Propagate auth config via env vars so the uvicorn reload worker (a fresh
    # process that re-imports the module) sees the same token/flag.
    if args.no_auth:
        os.environ["DISK_ANALYZER_NO_AUTH"] = "1"
        token = None
    else:
        os.environ["DISK_ANALYZER_NO_AUTH"] = "0"
        token = os.environ.get("DISK_ANALYZER_TOKEN") or secrets.token_urlsafe(32)
        os.environ["DISK_ANALYZER_TOKEN"] = token

    print("\n" + "="*60)
    print("🌐 Disk Analyzer Web Server")
    print("="*60)
    local_ip = get_local_ip()
    print(f"\n⚙️  Default min file size: {args.min_size} MB")
    if args.no_auth:
        print("\n⚠️  Auth DESHABILITADA (--no-auth): cualquiera en tu red puede")
        print("    leer/borrar archivos y abrir una terminal. Úsalo solo en una red aislada.")
        suffix = ""
    else:
        print("\n🔑 Auth activada. Abre el enlace con token (no lo compartas):")
        suffix = f"/?token={token}"
    print(f"\n📍 Accede a la interfaz web en:")
    print(f"   Local:   http://localhost:{args.port}{suffix}")
    if local_ip != "localhost":
        print(f"   Network: http://{local_ip}:{args.port}{suffix}")
    print(f"\nℹ️  Presiona Ctrl+C para detener el servidor")
    print("="*60 + "\n")

    uvicorn.run(
        "disk_analyzer_web:app",
        host="0.0.0.0",
        port=args.port,
        reload=True,
        log_level="info",
        ws_ping_interval=20,
        ws_ping_timeout=20,
        ws_max_size=16777216
    )
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv-web/bin/python -m pytest tests/test_auth.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Correr toda la suite y commitear**

Run: `venv-web/bin/python -m pytest tests/ -v` → verde (los tests viejos que golpean `/api/*` sin token podrían romperse; ver nota).

Nota importante: los tests existentes de `tests/test_terminal_api.py` y `tests/test_cleanup_api.py` llaman a rutas `/api/*` sin token. Con auth ON por defecto en esos tests, romperán. Solución dentro de este task: hacer que esos TestClients corran en modo no-auth. Añadir en cada archivo afectado un fixture/setup que setee `DISK_ANALYZER_NO_AUTH=1` en el entorno ANTES de importar/recargar `disk_analyzer_web`, o (más simple y robusto) un `conftest.py` en `tests/` con un fixture autouse que ponga `os.environ["DISK_ANALYZER_NO_AUTH"] = "1"` por defecto para toda la suite salvo `test_auth.py` (que gestiona su propio entorno con monkeypatch). Implementar el `conftest.py`:

```python
# tests/conftest.py
import os
import pytest


@pytest.fixture(autouse=True)
def _default_no_auth(monkeypatch, request):
    # test_auth.py manages its own auth env explicitly; leave it alone.
    if request.module.__name__.endswith("test_auth"):
        return
    monkeypatch.setenv("DISK_ANALYZER_NO_AUTH", "1")
```

Verificar que con el `conftest.py` la suite completa queda verde.

```bash
git add tests/test_auth.py tests/conftest.py disk_analyzer_web.py
git commit -m "feat(seguridad): auth por token para /api/*, CORS restringido a dev, flag --no-auth"
```

---

### Task 2: Auth de los dos WebSockets por query param

Los WS (`/ws/{session_id}` de progreso y `/ws/terminal/{pty_id}` interactivo) aceptan sin validar. El middleware HTTP NO cubre WebSockets (Starlette los saltea). Validar el token vía `?token=` antes de `accept()`, cerrando con código 1008 si falla.

**Files:**
- Modify: `disk_analyzer_web.py` — `websocket_endpoint` (~731), `terminal_websocket` (~1094)
- Test: `tests/test_auth.py` (agregar clase)

**Interfaces:**
- Consumes: `_token_is_valid(provided) -> bool` (de Task 1), `NO_AUTH`
- Produces: ambos WS cierran con `code=1008` antes de `accept()` si el `?token=` es inválido y `NO_AUTH` es False; con token válido o en modo no-auth funcionan igual que hoy.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_auth.py`:

```python
from starlette.websockets import WebSocketDisconnect


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
        with pytest_raises_ws_close():
            with client.websocket_connect("/ws/terminal/whatever"):
                pass


import contextlib
import pytest


@contextlib.contextmanager
def pytest_raises_ws_close():
    # Starlette's TestClient raises WebSocketDisconnect when the server closes
    # before/at accept with a policy-violation code.
    with pytest.raises(WebSocketDisconnect):
        yield
```

Nota: verificar el comportamiento exacto del `TestClient` de la versión instalada — si un `close()` pre-accept se manifiesta como `WebSocketDisconnect` o como otra excepción, ajustar el helper. Para el caso "con token válido" usar una sesión inexistente en el WS de progreso (que responde ping/pong sin requerir estado) para aislar la validación de auth del resto de la lógica.

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `venv-web/bin/python -m pytest tests/test_auth.py::TestWebSocketAuth -v`
Expected: FAIL — hoy los WS aceptan sin token.

- [ ] **Step 3: Implementar el gate en ambos WS**

En `websocket_endpoint` (~731), ANTES de `await websocket.accept()`:

```python
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for real-time progress updates"""
    if not _token_is_valid(websocket.query_params.get("token")):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    ...
```

En `terminal_websocket` (~1094), el gate de token va PRIMERO (antes incluso del check de `pty_id`, para no filtrar existencia de sesiones a no autenticados):

```python
@app.websocket("/ws/terminal/{pty_id}")
async def terminal_websocket(websocket: WebSocket, pty_id: str):
    """Bidirectional WebSocket: stdin from browser -> PTY, stdout from PTY -> browser."""
    if not _token_is_valid(websocket.query_params.get("token")):
        await websocket.close(code=1008)
        return
    if pty_id not in pty_manager.sessions:
        await websocket.close(code=4004, reason="No such session")
        return
    await websocket.accept()
    ...
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv-web/bin/python -m pytest tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 5: Suite completa y commit**

Run: `venv-web/bin/python -m pytest tests/ -v` → verde.

```bash
git add tests/test_auth.py disk_analyzer_web.py
git commit -m "feat(seguridad): validar token en los WebSockets de progreso y terminal (cierre 1008)"
```

---

### Task 3: Agents con dry-run + confirmación; sin auto-ejecución al togglear

`agents_manager.run_agent` corre `rm -rf ~/Library/Caches/*` y `rm -rf /tmp/*` sin dry-run ni confirmación, disparable con un `POST /api/agents/{id}/run` (y el scheduler lo corre solo si está enabled). Agregar `dry_run` a `run_agent`, exigir `confirm=true` en el endpoint `/run`, y que el scheduler corra en dry-run por defecto (registrando qué borraría) hasta que el usuario habilite ejecución real explícitamente.

**Files:**
- Modify: `agents_manager.py` — `run_agent` (~111-155), constante nueva de default dry-run, `start_scheduler` (~157-176)
- Modify: `disk_analyzer_web.py` — ruta `run_agent` (~1147-1153)
- Test: `tests/test_agents.py` (nuevo)

**Interfaces:**
- Produces: `AgentsManager.run_agent(agent_id: str, dry_run: bool = True) -> dict`. En dry-run NO ejecuta `subprocess.run`; devuelve `{"agent_id", "dry_run": True, "would_run": [cmd, ...], "freed": 0}`. En real ejecuta como hoy y devuelve además `"dry_run": False`.
- Produces: `POST /api/agents/{agent_id}/run?confirm=<bool>` — sin `confirm=true`, corre en dry-run (nunca borra). El scheduler llama `run_agent(agent_id, dry_run=True)` por defecto.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_agents.py`:

```python
"""Tests for agents safety (dry-run + confirmation)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents_manager import AgentsManager, AGENT_DEFINITIONS


class TestRunAgentDryRun:
    def test_dry_run_does_not_execute(self, monkeypatch):
        mgr = AgentsManager()
        calls = []
        import agents_manager
        monkeypatch.setattr(agents_manager.subprocess, "run",
                            lambda *a, **k: calls.append(a) or _fake_completed())
        result = mgr.run_agent("cache_cleaner", dry_run=True)
        assert result["dry_run"] is True
        assert calls == [], "dry-run must not call subprocess.run"
        assert result["would_run"] == AGENT_DEFINITIONS["cache_cleaner"]["commands"]
        assert result["freed"] == 0

    def test_default_is_dry_run(self, monkeypatch):
        mgr = AgentsManager()
        import agents_manager
        called = []
        monkeypatch.setattr(agents_manager.subprocess, "run",
                            lambda *a, **k: called.append(a) or _fake_completed())
        result = mgr.run_agent("cache_cleaner")  # no dry_run arg
        assert result["dry_run"] is True
        assert called == []

    def test_real_run_executes(self, monkeypatch):
        mgr = AgentsManager()
        import agents_manager
        called = []
        monkeypatch.setattr(agents_manager.subprocess, "run",
                            lambda *a, **k: called.append(a) or _fake_completed())
        result = mgr.run_agent("cache_cleaner", dry_run=False)
        assert result["dry_run"] is False
        assert len(called) == len(AGENT_DEFINITIONS["cache_cleaner"]["commands"])


class _Completed:
    returncode = 0
    stdout = ""
    stderr = ""


def _fake_completed():
    return _Completed()
```

Y un test del endpoint en `tests/test_agents_api.py` (o dentro del mismo archivo con TestClient):

```python
from fastapi.testclient import TestClient
import disk_analyzer_web


class TestRunAgentEndpoint:
    def setup_method(self):
        # conftest autouse sets NO_AUTH; endpoint reachable without token
        self.client = TestClient(disk_analyzer_web.app)

    def test_run_without_confirm_is_dry_run(self, monkeypatch):
        called = []
        import agents_manager
        monkeypatch.setattr(agents_manager.subprocess, "run",
                            lambda *a, **k: called.append(a) or _fake_completed())
        resp = self.client.post("/api/agents/cache_cleaner/run")
        assert resp.status_code == 200
        assert resp.json()["dry_run"] is True
        assert called == []

    def test_run_with_confirm_executes(self, monkeypatch):
        called = []
        import agents_manager
        monkeypatch.setattr(agents_manager.subprocess, "run",
                            lambda *a, **k: called.append(a) or _fake_completed())
        resp = self.client.post("/api/agents/cache_cleaner/run?confirm=true")
        assert resp.status_code == 200
        assert resp.json()["dry_run"] is False
        assert len(called) >= 1
```

Nota: leer la firma real del endpoint `run_agent` antes de escribir el test del API; adaptar nombres. Si `AgentsManager()` toca `~/.disk-analyzer` al construirse, considerar monkeypatch de `AGENTS_FILE`/`AGENTS_LOG` a `tmp_path` para no ensuciar el home.

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `venv-web/bin/python -m pytest tests/test_agents.py tests/test_agents_api.py -v`
Expected: FAIL — `run_agent` no acepta `dry_run` y ejecuta siempre.

- [ ] **Step 3: Implementar dry-run + confirm**

En `agents_manager.py`, reemplazar `run_agent` (~111-155):

```python
def run_agent(self, agent_id: str, dry_run: bool = True) -> dict:
    """Run an agent. dry_run=True (default) reports what WOULD run without executing."""
    if agent_id not in AGENT_DEFINITIONS:
        raise ValueError(f"Unknown agent: {agent_id}")

    defn = AGENT_DEFINITIONS[agent_id]

    if dry_run:
        _log(f"[dry-run] agent {agent_id}: would run {defn['commands']}")
        return {
            "agent_id": agent_id,
            "dry_run": True,
            "would_run": list(defn["commands"]),
            "freed": 0,
            "results": [],
        }

    usage_before = shutil.disk_usage("/").used
    results = []
    for cmd in defn["commands"]:
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=120
            )
            results.append({
                "command": cmd,
                "success": result.returncode == 0,
                "output": result.stdout[:500] if result.stdout else "",
                "error": result.stderr[:500] if result.stderr else "",
            })
        except subprocess.TimeoutExpired:
            results.append({"command": cmd, "success": False, "error": "Timeout"})
        except Exception as e:
            results.append({"command": cmd, "success": False, "error": str(e)})

    usage_after = shutil.disk_usage("/").used
    freed = max(0, usage_before - usage_after)
    # (preserve the existing state update: last_run, last_freed, total_freed, run_count, _save_state, _log)
    self._record_run(agent_id, freed)  # or inline the existing block verbatim
    return {"agent_id": agent_id, "dry_run": False, "freed": freed, "results": results}
```

Nota: preservar VERBATIM el bloque existente que actualiza `agents_state`/`_save_state`/`_log` tras calcular `freed` (arriba está referido como `self._record_run`; si ese helper no existe, inlinear el bloque original que ya estaba en `run_agent`). Leer el método actual completo antes de reemplazar.

En `start_scheduler` (~172), cambiar la llamada del scheduler a dry-run por defecto:

```python
            _log(f"Scheduler running agent (dry-run): {agent_id}")
            try:
                self.run_agent(agent_id, dry_run=True)
            except Exception as e:
                _log(f"Scheduler error for {agent_id}: {e}")
```

Nota de diseño: el scheduler queda en dry-run permanente en esta fase (solo registra qué borraría). Ejecución real automática y desatendida se pospone a una decisión de producto posterior; el usuario puede correr real bajo demanda con `confirm=true`. Documentarlo en el reporte.

En `disk_analyzer_web.py`, la ruta `run_agent` (~1147), aceptar `confirm` y ofrecer a thread:

```python
@app.post("/api/agents/{agent_id}/run")
async def run_agent_endpoint(agent_id: str, confirm: bool = False):
    """Run an agent. Without confirm=true this is a dry-run (nothing is deleted)."""
    try:
        result = await asyncio.to_thread(
            agents_manager.run_agent, agent_id, not confirm
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

Nota: verificar el nombre real de la función del endpoint y de la firma en el código; el punto es pasar `dry_run = not confirm` y offload con `to_thread` (antes corría bloqueante en el event loop).

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv-web/bin/python -m pytest tests/test_agents.py tests/test_agents_api.py -v`
Expected: PASS

- [ ] **Step 5: Suite completa y commit**

Run: `venv-web/bin/python -m pytest tests/ -v` → verde.

```bash
git add tests/test_agents.py tests/test_agents_api.py agents_manager.py disk_analyzer_web.py
git commit -m "feat(seguridad): agents en dry-run por defecto, /run exige confirm=true, scheduler no borra"
```

---

### Task 4: Frontend — bootstrap del token y adjuntarlo a REST + WebSockets

El frontend no manda token. Leer `?token=` de la URL al cargar, guardarlo en `sessionStorage`, limpiar la URL, y adjuntarlo como header `X-Auth-Token` en todos los `fetch` (via el helper `request()` y las llamadas directas) y como `?token=` en las 3 URLs de WebSocket y en `getExportUrl`.

**Files:**
- Create: `web/src/lib/auth.ts` (bootstrap + helpers)
- Modify: `web/src/lib/api.ts` — `request()` (~82-92), `getExportUrl` (~122), y las llamadas directas con `fetch()` que no pasan por `request()` (HeroScan, WeeklyDigest, AgentsPanel — buscarlas)
- Modify: `web/src/hooks/useTerminal.ts` (~12), `web/src/hooks/useWebSocket.ts` (~17), `web/src/components/AnalysisManager.tsx` (~49)
- Modify: `web/src/layouts/MainLayout.astro` — invocar el bootstrap lo antes posible (script inline en `<head>` o import temprano)

**Interfaces:**
- Produces (`web/src/lib/auth.ts`):
  - `getToken(): string | null` — lee de `sessionStorage`
  - `authHeaders(): Record<string,string>` — `{ 'X-Auth-Token': token }` o `{}`
  - `withToken(url: string): string` — agrega `?token=`/`&token=` si hay token (para WS y export)
  - efecto de módulo/bootstrap: al importarse en el navegador, extrae `?token=` de `location.search`, lo guarda en `sessionStorage['da_token']`, y hace `history.replaceState` para quitarlo de la URL.

- [ ] **Step 1: Crear `web/src/lib/auth.ts`**

```typescript
// Token bootstrap + helpers for authenticated API/WS access.
const KEY = 'da_token';

function bootstrap(): void {
  if (typeof window === 'undefined') return;
  const params = new URLSearchParams(window.location.search);
  const urlToken = params.get('token');
  if (urlToken) {
    sessionStorage.setItem(KEY, urlToken);
    params.delete('token');
    const qs = params.toString();
    const clean = window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash;
    window.history.replaceState({}, '', clean);
  }
}

bootstrap();

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return sessionStorage.getItem(KEY);
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { 'X-Auth-Token': t } : {};
}

export function withToken(url: string): string {
  const t = getToken();
  if (!t) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}token=${encodeURIComponent(t)}`;
}
```

- [ ] **Step 2: Cablear en `api.ts`**

En `web/src/lib/api.ts`, importar y usar los helpers. Reemplazar `request()`:

```typescript
import { authHeaders, withToken } from './auth';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(options?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}
```

Nota: el original hacía `...options` DESPUÉS de `headers`, lo que borraba los headers si el caller pasaba `options.headers`. El nuevo orden fusiona headers correctamente. Verificar que ningún caller dependía del bug.

`getExportUrl` debe incluir el token (se abre como link directo):

```typescript
getExportUrl: (id: string, format: string) => withToken(`${BASE}/export/${id}/${format}`),
```

Buscar las llamadas `fetch('/api/...')` que NO pasan por `request()` (grep `fetch(` en `web/src`): `HeroScan` (`/api/analysis/latest`), `WeeklyDigest` (`/api/digest`), `AgentsPanel` (`/api/agents`, toggle, run). Añadirles `{ headers: authHeaders() }`.

- [ ] **Step 3: Cablear en los 3 WebSockets**

`web/src/hooks/useTerminal.ts` (~12), `web/src/hooks/useWebSocket.ts` (~17), `web/src/components/AnalysisManager.tsx` (~49): envolver la URL con `withToken`:

```typescript
import { withToken } from '../lib/auth';   // ajustar path relativo por archivo
const ws = new WebSocket(withToken(`ws://${window.location.host}/ws/terminal/${id}`));
```

(equivalente en los otros dos, respetando su URL).

- [ ] **Step 4: Invocar el bootstrap temprano**

En `web/src/layouts/MainLayout.astro`, asegurar que `auth.ts` se importe/ejecute antes que cualquier fetch. Como los islands se hidratan después, importar `auth.ts` desde `api.ts` ya garantiza el bootstrap al primer uso, pero para quitar el token de la URL cuanto antes, añadir un script inline en el `<head>` que haga el strip mínimo (leer `?token=`, guardar en sessionStorage, `replaceState`) — replicando `bootstrap()` en vanilla JS para que corra en el primer paint. Documentar la decisión (import-driven vs inline) en el reporte.

- [ ] **Step 5: Build + verificación**

Run: `cd web && npm run build`
Expected: build sin errores de TypeScript.

Nota: no hay suite de tests JS en el repo. La verificación de este task es (a) build limpio, (b) el smoke test end-to-end del Task 6 con auth activa.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/auth.ts web/src/lib/api.ts web/src/hooks/useTerminal.ts web/src/hooks/useWebSocket.ts web/src/components/AnalysisManager.tsx web/src/layouts/MainLayout.astro
git commit -m "feat(seguridad): frontend adjunta token en REST (X-Auth-Token) y WS (?token=), lo limpia de la URL"
```

---

### Task 5: Higiene de fds en el fork del PTY

El `os.fork()` del PTY (`pty_manager.py:45-71`) cierra solo su propio master/slave; el shell hijo hereda todos los demás fds del servidor (masters de otros PTY, socket de uvicorn). Cerrar los fds no esenciales en el hijo antes de `execvp`.

**Files:**
- Modify: `pty_manager.py` — método `start` / bloque post-fork del hijo (~45-71)
- Test: `tests/test_pty_manager.py` (agregar test)

**Interfaces:**
- Produces: tras el fork, el proceso hijo cierra todos los fds ≥ 3 excepto el slave que dup-ea a stdio, de modo que no hereda masters de otras sesiones ni el socket del servidor.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_pty_manager.py`:

```python
def test_child_does_not_inherit_extra_fds(self):
    import os
    # Open a sentinel fd in the parent that the child must NOT inherit.
    r, w = os.pipe()
    try:
        pty_id = self.manager.create_session(command=f"ls -l /proc/self/fd 2>/dev/null || ls -l /dev/fd")
        session = self.manager.sessions[pty_id]
        import time
        time.sleep(0.3)
        output = session.read_output()
        # The sentinel write-end fd number must not appear among the child's fds.
        assert str(w) not in output or "No such" in output, (
            f"child leaked fd {w}; fds seen:\n{output}"
        )
        self.manager.kill_session(pty_id)
    finally:
        os.close(r)
        os.close(w)
```

Nota: en macOS no hay `/proc`; `ls -l /dev/fd` lista los fds del proceso. El test es best-effort y dependiente de plataforma — si resulta frágil, sustituirlo por una verificación más directa: tras el fork, el hijo intenta `os.fstat(sentinel_fd)` y reporta si existe. Documentar el enfoque final. Lo esencial es demostrar que un fd centinela abierto en el padre no sobrevive en el hijo tras el fix.

- [ ] **Step 2: Correr el test y observar el estado pre-fix**

Run: `venv-web/bin/python -m pytest tests/test_pty_manager.py -k inherit -v`
Expected: FAIL (el hijo hereda el fd centinela).

- [ ] **Step 3: Cerrar fds heredados en el hijo**

En el bloque del hijo (`self.pid == 0`) de `PTYSession.start`, tras `os.setsid()` y los `dup2` de stdio, antes de `execvp`, cerrar el rango de fds altos:

```python
        # Close any inherited fds (other sessions' PTY masters, the uvicorn
        # socket, etc.) so the spawned shell can't touch them.
        try:
            max_fd = os.sysconf("SC_OPEN_MAX")
        except (AttributeError, ValueError):
            max_fd = 1024
        os.closerange(3, max_fd)
```

Nota: colocarlo DESPUÉS de que stdio (0,1,2) ya apuntan al slave via dup2 y de cualquier uso del slave_fd/master_fd en el hijo; `closerange(3, ...)` no toca 0/1/2. Leer el bloque actual completo para insertarlo en el punto correcto (después de los dup2, antes del execvp).

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `venv-web/bin/python -m pytest tests/test_pty_manager.py -v`
Expected: PASS (incluido el nuevo test y todos los de PTY previos)

- [ ] **Step 5: Commit**

```bash
git add tests/test_pty_manager.py pty_manager.py
git commit -m "fix(seguridad): el shell del PTY no hereda fds del servidor (closerange tras el fork)"
```

---

### Task 6: Verificación integral de la fase

**Files:** ninguno nuevo — verificación.

- [ ] **Step 1: Suite completa**

Run: `venv-web/bin/python -m pytest tests/ -v`
Expected: PASS, 0 failures.

- [ ] **Step 2: Build del frontend**

Run: `cd web && npm run build`
Expected: sin errores.

- [ ] **Step 3: Humo con auth ACTIVA**

```bash
DISK_ANALYZER_NO_AUTH=0 DISK_ANALYZER_TOKEN=smoketoken123 \
  venv-web/bin/python -c "import uvicorn; uvicorn.run('disk_analyzer_web:app', host='127.0.0.1', port=8766)" &
sleep 3
echo "--- sin token (debe ser 401):"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8766/api/system/info
echo "--- con token (debe ser 200):"
curl -s -o /dev/null -w "%{http_code}\n" -H 'X-Auth-Token: smoketoken123' http://localhost:8766/api/system/info
echo "--- agents run sin confirm (debe ser dry_run):"
curl -s -H 'X-Auth-Token: smoketoken123' -X POST http://localhost:8766/api/agents/cache_cleaner/run | head -c 200
kill %1
```
Expected: 401 sin token, 200 con token, `"dry_run": true` en el run sin confirm.

- [ ] **Step 4: Commit de verificación (si hubo ajustes)**

```bash
git add -A && git commit -m "test: verificación integral fase 2 seguridad" --allow-empty
```

---

## Self-Review (ejecutado al escribir el plan)

1. **Cobertura:** los 4 hallazgos de seguridad de la Fase 2 tienen task — auth HTTP+CORS+flag (Task 1), auth WS (Task 2), agents dry-run/confirm (Task 3), frontend token (Task 4), fd hygiene (Task 5) — más verificación (Task 6). El "terminal opt-in detrás de flag" del roadmap se cubre implícitamente: con auth ON el terminal ya requiere token; un gate adicional se pospone (documentado).
2. **Placeholders:** los "Nota: verificar/leer antes" marcan puntos donde el código real debe leerse (nombres de funciones de endpoints, bloque de estado de `run_agent`, comportamiento del TestClient WS); el código de intención está completo en cada step.
3. **Consistencia de tipos:** `_token_is_valid(str|None)->bool` usado por middleware (Task 1) y ambos WS (Task 2); `run_agent(agent_id, dry_run=True)->dict` con `dry_run` en el return, consumido por el endpoint (Task 3) que pasa `not confirm`; helpers de `auth.ts` (`authHeaders`, `withToken`) consumidos por `api.ts` y los 3 WS (Task 4).
