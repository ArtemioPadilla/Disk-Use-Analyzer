# Plan de Mejoras — Fase 1: Bugs Críticos de Backend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Arreglar los 7 bugs de correctness verificados en el backend web (endpoints de cleanup rotos, parseo Docker que reporta 0, recomendaciones que nunca disparan, timeout de terminal que no corre, sesiones zombie) con tests de regresión.

**Architecture:** Cambios quirúrgicos sobre `disk_analyzer_web.py`, `disk_analyzer_core.py` y `pty_manager.py` sin reestructurar módulos (la extracción del motor compartido es la Fase 3). Cada fix llega con su test primero (TDD). No se toca el frontend en esta fase.

**Tech Stack:** Python 3.10+, FastAPI, pytest, `fastapi.testclient.TestClient`.

## Global Constraints

- Los tests corren con `python -m pytest tests/ -v` desde la raíz del repo (usar `venv-web`).
- Mensajes user-facing en español; comentarios de código en inglés (convención CLAUDE.md).
- Ninguna operación destructiva nueva sin guard `is_protected_path` y sin modo dry-run.
- No cambiar firmas públicas que consume el frontend (`web/src/lib/api.ts`) salvo hacer campos opcionales.
- Antes de cada commit: `python -m pytest tests/ -v` en verde.

---

### Task 1: Reparar `/api/cleanup/preview` y `/api/cleanup/execute`

El endpoint está roto en cadena: (a) el frontend envía `{paths, dry_run}` sin `categories` → FastAPI responde 422 antes de entrar al handler (`CleanupRequest.categories` es requerido); (b) `execute_cleanup` reconstruye el request de preview omitiendo `paths` (requerido) → `pydantic.ValidationError` sin capturar; (c) instancia `DiskAnalyzerCore()` sin el argumento requerido `start_path` → `TypeError` (y la variable ni se usa); (d) el loop de borrado no tiene guard `is_protected_path` ni envío a Papelera, a diferencia de `DELETE /api/files/delete`.

**Files:**
- Modify: `disk_analyzer_web.py:162-165` (modelo `CleanupRequest`)
- Modify: `disk_analyzer_web.py:776-842` (handlers `preview_cleanup` / `execute_cleanup`)
- Test: `tests/test_cleanup_api.py` (nuevo)

**Interfaces:**
- Consumes: `DiskAnalyzerCore(start_path).is_protected_path(path) -> bool` (existente, `disk_analyzer_core.py:191`)
- Produces: `POST /api/cleanup/preview` y `POST /api/cleanup/execute` aceptan `{paths: [...], dry_run: bool}` con `categories` opcional (lista vacía = todas las categorías). Respuesta de execute: `{deleted: [...], errors: [...], freed_size: int, dry_run: false}`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_cleanup_api.py`:

```python
"""Tests for /api/cleanup/* endpoints."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import disk_analyzer_web
from disk_analyzer_web import app


class TestCleanupPreview:
    def setup_method(self):
        self.client = TestClient(app)

    def test_preview_without_categories_is_accepted(self):
        # The frontend sends only paths + dry_run; categories must be optional
        resp = self.client.post(
            "/api/cleanup/preview",
            json={"paths": [str(Path.home())], "dry_run": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "actions" in body
        assert "total_size" in body

    def test_preview_filters_by_category_case_insensitive(self, monkeypatch):
        class FakeAnalyzer:
            def __init__(self, path):
                self.cache_locations = [
                    {"path": "/fake/npm", "size": 100, "type": "NPM Cache"},
                    {"path": "/fake/docker", "size": 200, "type": "Docker"},
                ]

            def find_cache_locations(self):
                pass

        monkeypatch.setattr(disk_analyzer_web, "DiskAnalyzerCore", FakeAnalyzer)
        resp = self.client.post(
            "/api/cleanup/preview",
            json={"paths": ["/tmp"], "categories": ["npm cache"], "dry_run": True},
        )
        assert resp.status_code == 200
        actions = resp.json()["actions"]
        assert len(actions) == 1
        assert actions[0]["path"] == "/fake/npm"


class TestCleanupExecute:
    def setup_method(self):
        self.client = TestClient(app)

    def test_execute_dry_run_returns_preview(self):
        resp = self.client.post(
            "/api/cleanup/execute",
            json={"paths": [str(Path.home())], "dry_run": True},
        )
        assert resp.status_code == 200
        assert resp.json()["dry_run"] is True

    def test_execute_deletes_only_unprotected(self, tmp_path, monkeypatch):
        victim = tmp_path / "cache_dir"
        victim.mkdir()
        (victim / "junk.bin").write_bytes(b"x" * 1024)

        class FakeAnalyzer:
            def __init__(self, path):
                self.cache_locations = [
                    {"path": str(victim), "size": 1024, "type": "Cache General"},
                    {"path": "/System/Library/Kernels", "size": 1, "type": "Cache General"},
                ]

            def find_cache_locations(self):
                pass

            def is_protected_path(self, path):
                return path.startswith("/System")

        monkeypatch.setattr(disk_analyzer_web, "DiskAnalyzerCore", FakeAnalyzer)
        resp = self.client.post(
            "/api/cleanup/execute",
            json={"paths": [str(tmp_path)], "dry_run": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert not victim.exists()
        deleted_paths = [d["path"] for d in body["deleted"]]
        assert str(victim) in deleted_paths
        # The protected path must be skipped, reported as error, never deleted
        error_paths = [e["path"] for e in body["errors"]]
        assert any("/System" in p for p in error_paths)
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `venv-web/bin/python -m pytest tests/test_cleanup_api.py -v`
Expected: FAIL — `test_preview_without_categories_is_accepted` con 422; `test_execute_deletes_only_unprotected` con 500 (ValidationError/TypeError).

- [ ] **Step 3: Implementar el fix**

En `disk_analyzer_web.py`, reemplazar el modelo (líneas 162-165):

```python
class CleanupRequest(BaseModel):
    paths: List[str] = []
    categories: List[str] = []  # empty list means "all categories"
    dry_run: bool = True
```

Reemplazar `preview_cleanup` (líneas 776-801):

```python
@app.post("/api/cleanup/preview")
async def preview_cleanup(request: CleanupRequest):
    """Preview cleanup actions"""
    cleanup_actions = []
    total_size = 0
    wanted = {c.lower() for c in request.categories}

    for path in request.paths:
        analyzer = DiskAnalyzerCore(path)
        # Quick scan for cache locations only
        analyzer.find_cache_locations()

        for cache_loc in analyzer.cache_locations:
            if wanted and cache_loc['type'].lower() not in wanted:
                continue
            cleanup_actions.append({
                "path": cache_loc['path'],
                "size": cache_loc['size'],
                "type": cache_loc['type'],
                "action": "delete"
            })
            total_size += cache_loc['size']

    return {
        "actions": cleanup_actions,
        "total_size": total_size,
        "dry_run": request.dry_run
    }
```

Reemplazar `execute_cleanup` (líneas 803-842):

```python
@app.post("/api/cleanup/execute")
async def execute_cleanup(request: CleanupRequest):
    """Execute cleanup actions"""
    if request.dry_run:
        return await preview_cleanup(request)

    # Safety: always preview first so callers see what would be deleted
    preview = await preview_cleanup(
        CleanupRequest(paths=request.paths, categories=request.categories, dry_run=True)
    )

    checker = DiskAnalyzerCore(str(Path.home()))
    deleted: list[dict] = []
    errors: list[dict] = []
    freed_size = 0

    for action in preview.get("actions", []):
        target = Path(action["path"]).resolve()
        if checker.is_protected_path(str(target)):
            errors.append({"path": str(target), "error": "Ruta protegida del sistema"})
            continue
        try:
            if target.is_file():
                size = target.stat().st_size
                target.unlink()
                deleted.append({"path": str(target), "size": size})
                freed_size += size
            elif target.is_dir():
                import shutil
                size = action.get("size", 0)
                shutil.rmtree(str(target))
                deleted.append({"path": str(target), "size": size})
                freed_size += size
        except Exception as e:
            errors.append({"path": str(target), "error": str(e)})

    return {
        "deleted": deleted,
        "errors": errors,
        "freed_size": freed_size,
        "dry_run": False
    }
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv-web/bin/python -m pytest tests/test_cleanup_api.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Correr toda la suite y commitear**

Run: `venv-web/bin/python -m pytest tests/ -v` → todo en verde.

```bash
git add tests/test_cleanup_api.py disk_analyzer_web.py
git commit -m "fix: reparar endpoints /api/cleanup (422 por categories requerido, ValidationError en execute, guard de rutas protegidas)"
```

---

### Task 2: `parse_docker_size` en el core reporta 0 para el output real de Docker

`docker system df` emite tamaños sin espacio (`"1.5GB"`, `"2.796kB"`). `DiskAnalyzerCore.parse_docker_size` (`disk_analyzer_core.py:574`) hace `size_str.split()` y exige exactamente 2 tokens → devuelve 0 para todo. El CLI (`disk_analyzer.py:504`) ya tiene la versión correcta con regex; hay que portarla.

**Files:**
- Modify: `disk_analyzer_core.py:574-602` (método `parse_docker_size`)
- Test: `tests/test_core_engine.py` (nuevo)

**Interfaces:**
- Produces: `DiskAnalyzerCore.parse_docker_size(size_str: str) -> int` (bytes) que acepta `"1.5GB"`, `"500MB"`, `"2.796kB"`, `"1.5 GB"`, `"0B"`, y strings con sufijos tipo `"(45%)"`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_core_engine.py`:

```python
"""Tests for DiskAnalyzerCore engine logic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from disk_analyzer_core import DiskAnalyzerCore, KB, MB, GB


class TestParseDockerSize:
    def setup_method(self):
        self.core = DiskAnalyzerCore(".")

    def test_no_space_gb(self):
        assert self.core.parse_docker_size("1.5GB") == int(1.5 * GB)

    def test_no_space_mb(self):
        assert self.core.parse_docker_size("500MB") == 500 * MB

    def test_lowercase_kb(self):
        # docker emits kB with lowercase k
        assert self.core.parse_docker_size("2.796kB") == int(2.796 * KB)

    def test_with_space(self):
        assert self.core.parse_docker_size("1.5 GB") == int(1.5 * GB)

    def test_zero_bytes(self):
        assert self.core.parse_docker_size("0B") == 0

    def test_with_percentage_suffix(self):
        assert self.core.parse_docker_size("1.5GB (45%)") == int(1.5 * GB)

    def test_garbage_returns_zero(self):
        assert self.core.parse_docker_size("N/A") == 0
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `venv-web/bin/python -m pytest tests/test_core_engine.py -v`
Expected: FAIL — los casos sin espacio devuelven 0.

- [ ] **Step 3: Portar la implementación con regex del CLI**

Reemplazar `parse_docker_size` en `disk_analyzer_core.py` (líneas 574-602):

```python
def parse_docker_size(self, size_str: str) -> int:
    """Parse docker size strings like '1.5GB', '2.796kB', '500MB (45%)' to bytes"""
    import re
    try:
        clean = size_str.strip().split('(')[0].strip()
        match = re.match(r'([\d.]+)\s*([KMGTk]?B)', clean)
        if not match:
            return 0
        value = float(match.group(1))
        unit = match.group(2).upper()
        multipliers = {'B': 1, 'KB': KB, 'MB': MB, 'GB': GB, 'TB': GB * 1024}
        return int(value * multipliers.get(unit, 1))
    except (ValueError, AttributeError):
        return 0
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv-web/bin/python -m pytest tests/test_core_engine.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_core_engine.py disk_analyzer_core.py
git commit -m "fix: parse_docker_size en core devolvía 0 para el formato real de docker system df (sin espacio)"
```

---

### Task 3: Etiquetas de caché desalineadas — recomendaciones de VS Code y npm nunca disparan en web/GUI

`DiskAnalyzerCore.categorize_cache` (`disk_analyzer_core.py:403`) emite `'VS Code Cache'` y `'NPM Cache'`, pero `generate_recommendations` (`disk_analyzer_core.py:722,729`) filtra por `'VS Code'` y `'Node.js/npm'` (las etiquetas del CLI). Esos filtros no matchean nunca. Fix mínimo: alinear los filtros con las etiquetas que el core realmente produce. (La unificación completa de etiquetas entre CLI y core es Fase 3.)

**Files:**
- Modify: `disk_analyzer_core.py:703-772` (método `generate_recommendations`)
- Test: `tests/test_core_engine.py` (agregar clase)

**Interfaces:**
- Consumes: `self.cache_locations: List[dict]` con `type` producido por `categorize_cache`
- Produces: recomendaciones tier 1 con `type: 'vscode_cache'` y `type: 'npm_cache'` cuando existen esas cachés

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_core_engine.py`:

```python
class TestRecommendationLabels:
    def test_vscode_and_npm_recommendations_fire(self):
        core = DiskAnalyzerCore(".")
        # Labels exactly as categorize_cache produces them
        core.cache_locations = [
            {"path": "/fake/Code/Cache", "size": 2 * GB, "type": "VS Code Cache"},
            {"path": "/fake/.npm", "size": 3 * GB, "type": "NPM Cache"},
        ]
        recs = core.generate_recommendations()
        types = {r.get("type") for r in recs}
        assert "vscode_cache" in types, f"missing vscode rec, got {types}"
        assert "npm_cache" in types, f"missing npm rec, got {types}"

    def test_categorize_cache_labels_are_covered(self):
        # Guard: every label that generate_recommendations filters on
        # must be producible by categorize_cache
        core = DiskAnalyzerCore(".")
        assert core.categorize_cache(Path("/Users/x/Library/Caches/Code")) == "VS Code Cache"
        assert core.categorize_cache(Path("/Users/x/.npm")) == "NPM Cache"
```

Nota: verificar primero con `grep -n "vscode\|npm" disk_analyzer_core.py` el nombre exacto del campo `type` que asigna `generate_recommendations` a esas recomendaciones; si usa otro identificador (p. ej. no define `type`), ajustar el assert a la clave real (`description` contiene "VS Code" / "npm") manteniendo la intención: con cachés etiquetadas `VS Code Cache`/`NPM Cache` deben aparecer recomendaciones para ambas.

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `venv-web/bin/python -m pytest tests/test_core_engine.py::TestRecommendationLabels -v`
Expected: FAIL — no aparecen recomendaciones de VS Code ni npm.

- [ ] **Step 3: Alinear los filtros**

En `disk_analyzer_core.py::generate_recommendations`, cambiar:

```python
vscode_locs = [l for l in self.cache_locations if l['type'] == 'VS Code']
```
por:
```python
vscode_locs = [l for l in self.cache_locations if l['type'] == 'VS Code Cache']
```
y:
```python
npm_locs = [l for l in self.cache_locations if l['type'] == 'Node.js/npm']
```
por:
```python
npm_locs = [l for l in self.cache_locations if l['type'] == 'NPM Cache']
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv-web/bin/python -m pytest tests/test_core_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_core_engine.py disk_analyzer_core.py
git commit -m "fix: recomendaciones de VS Code/npm nunca disparaban en web/GUI por etiquetas de cache desalineadas"
```

---

### Task 4: `cleanup_idle()` del PTY manager nunca se ejecuta

`PTYManager` se instancia con `idle_timeout=600` (`disk_analyzer_web.py:54`) pero nada llama a `cleanup_idle()` — las sesiones idle ocupan slots (máx. 3) para siempre. Agregar un reaper periódico en el evento de startup.

**Files:**
- Modify: `disk_analyzer_web.py:1107` (función `startup_event`)
- Test: `tests/test_terminal_api.py` (agregar test)

**Interfaces:**
- Consumes: `pty_manager.cleanup_idle()` (existente, `pty_manager.py:259`)
- Produces: task asyncio `_idle_terminal_reaper` corriendo cada 60 s

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_terminal_api.py`:

```python
def test_idle_reaper_task_is_registered():
    """startup must schedule the idle-session reaper."""
    import disk_analyzer_web
    assert hasattr(disk_analyzer_web, "_idle_terminal_reaper"), (
        "expected an _idle_terminal_reaper coroutine registered at startup"
    )
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `venv-web/bin/python -m pytest tests/test_terminal_api.py::test_idle_reaper_task_is_registered -v`
Expected: FAIL con AssertionError.

- [ ] **Step 3: Implementar el reaper**

En `disk_analyzer_web.py`, a nivel de módulo (antes de `startup_event`):

```python
async def _idle_terminal_reaper():
    """Periodically kill PTY sessions idle beyond the configured timeout."""
    while True:
        await asyncio.sleep(60)
        try:
            pty_manager.cleanup_idle()
        except Exception as e:
            logger.warning(f"idle terminal reaper error: {e}")
```

Y dentro de `startup_event` (línea ~1107), al final:

```python
    asyncio.create_task(_idle_terminal_reaper())
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv-web/bin/python -m pytest tests/test_terminal_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_terminal_api.py disk_analyzer_web.py
git commit -m "fix: activar cleanup_idle() del PTY manager — el idle timeout documentado nunca corría"
```

---

### Task 5: Sesiones restauradas como "running" quedan colgadas para siempre tras un restart

`load_session_metadata` (`disk_analyzer_web.py:90-114`) restaura sesiones con el status persistido, incluido `"running"`, sin tarea en vuelo que las complete. Marcarlas `"interrupted"` al cargar.

**Files:**
- Modify: `disk_analyzer_web.py:90-114` (función `load_session_metadata`)
- Test: `tests/test_sessions_persistence.py` (nuevo)

**Interfaces:**
- Produces: toda sesión restaurada con `status == "running"` pasa a `status = "interrupted"`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_sessions_persistence.py`:

```python
"""Tests for session metadata persistence."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import disk_analyzer_web


def test_running_sessions_marked_interrupted_on_load(tmp_path, monkeypatch):
    sessions_file = tmp_path / "sessions_metadata.json"
    sessions_file.write_text(json.dumps({
        "abc123": {"status": "running", "paths": ["/tmp"], "started_at": "2026-07-15T10:00:00"},
        "def456": {"status": "completed", "paths": ["/tmp"], "started_at": "2026-07-15T09:00:00"},
    }))
    monkeypatch.setattr(disk_analyzer_web, "SESSIONS_FILE", sessions_file)
    monkeypatch.setattr(disk_analyzer_web, "analysis_sessions", {})

    disk_analyzer_web.load_session_metadata()

    sessions = disk_analyzer_web.analysis_sessions
    assert sessions["abc123"]["status"] == "interrupted"
    assert sessions["def456"]["status"] == "completed"
```

Nota: leer `load_session_metadata` antes de implementar — si usa `SESSIONS_FILE` como constante importada en otro scope o carga dentro de `startup_event`, adaptar el monkeypatch al nombre real, manteniendo la intención del test.

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `venv-web/bin/python -m pytest tests/test_sessions_persistence.py -v`
Expected: FAIL — status sigue siendo "running".

- [ ] **Step 3: Implementar el fix**

En `load_session_metadata`, después de cargar cada sesión al dict:

```python
        # A restored "running" session has no in-flight task backing it
        if session.get("status") == "running":
            session["status"] = "interrupted"
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv-web/bin/python -m pytest tests/test_sessions_persistence.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_sessions_persistence.py disk_analyzer_web.py
git commit -m "fix: marcar como interrupted las sesiones running restauradas tras un restart del servidor"
```

---

### Task 6: `PTYSession.kill()` deja zombies

`kill()` (`pty_manager.py:131-154`) hace un único `waitpid(WNOHANG)` inmediatamente tras el SIGKILL y descarta el pid aunque no se haya cosechado — el proceso queda zombie hasta que muere el servidor.

**Files:**
- Modify: `pty_manager.py:131-154` (método `kill`)
- Test: `tests/test_pty_manager.py` (agregar test)

**Interfaces:**
- Produces: `kill()` garantiza que el hijo fue cosechado (o agotó un deadline de 2 s) antes de limpiar `self.pid`.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_pty_manager.py`:

```python
def test_kill_reaps_child_no_zombie(self):
    import os
    pty_id = self.manager.create_session()
    session = self.manager.sessions[pty_id]
    pid = session.pid
    self.manager.kill_session(pty_id)
    # After kill, the pid must be fully reaped: waitpid must raise
    # ChildProcessError (no such child) rather than find a zombie.
    try:
        result = os.waitpid(pid, os.WNOHANG)
        assert result == (0, 0) or result[0] == 0, f"zombie child remains: {result}"
        raise AssertionError(f"child {pid} was not reaped by kill()")
    except ChildProcessError:
        pass  # correctly reaped
```

Nota: ajustar al estilo de setup del archivo existente (usa `setup_method` con `self.manager`).

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `venv-web/bin/python -m pytest tests/test_pty_manager.py -k zombie -v`
Expected: FAIL (el hijo sigue como zombie) — si pasa de manera intermitente por timing, correrlo 5 veces; debe fallar al menos una.

- [ ] **Step 3: Implementar el reap con deadline**

Reemplazar el bloque final de `kill()` en `pty_manager.py`:

```python
def kill(self):
    """Terminate the session process and reap it."""
    self.alive = False
    if self.pid:
        try:
            os.kill(self.pid, signal.SIGTERM)
            time.sleep(0.1)
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            # Reap with a deadline so the child never lingers as a zombie
            deadline = time.time() + 2.0
            while time.time() < deadline:
                try:
                    pid, _ = os.waitpid(self.pid, os.WNOHANG)
                except ChildProcessError:
                    break
                if pid == self.pid:
                    break
                time.sleep(0.05)
        except ProcessLookupError:
            pass
        self.pid = None
    if self.master_fd is not None:
        try:
            os.close(self.master_fd)
        except OSError:
            pass
        self.master_fd = None
```

Nota: conservar cualquier lógica existente de cierre de fds que ya tenga el método actual — leerlo completo antes de reemplazar.

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv-web/bin/python -m pytest tests/test_pty_manager.py -v`
Expected: PASS (suite completa del PTY, no solo el nuevo)

- [ ] **Step 5: Commit**

```bash
git add tests/test_pty_manager.py pty_manager.py
git commit -m "fix: PTYSession.kill() cosecha al hijo con deadline en vez de dejar zombies"
```

---

### Task 7: Verificación integral de la fase

**Files:** ninguno nuevo — verificación.

- [ ] **Step 1: Suite completa**

Run: `venv-web/bin/python -m pytest tests/ -v`
Expected: PASS, 0 failures.

- [ ] **Step 2: Humo del servidor**

```bash
venv-web/bin/python disk_analyzer_web.py --port 8765 &
sleep 3
curl -s http://localhost:8765/api/system/info | head -c 200
curl -s -X POST http://localhost:8765/api/cleanup/preview \
  -H 'Content-Type: application/json' \
  -d '{"paths": ["'$HOME'"], "dry_run": true}' | head -c 300
kill %1
```
Expected: ambos endpoints responden 200 con JSON (el preview ya no da 422).

- [ ] **Step 3: Commit final si hubo ajustes**

```bash
git add -A && git commit -m "test: verificación integral fase 1" --allow-empty
```

---

## Self-Review (ejecutado al escribir el plan)

1. **Cobertura:** los 7 hallazgos críticos/altos de backend con fix acotado tienen task (cleanup endpoints, docker size, etiquetas, idle reaper, sesiones colgadas, zombies). Los hallazgos de seguridad (auth/CORS/agents/PTY interactivo) NO están aquí — son la Fase 2, decisión deliberada de scope.
2. **Placeholders:** los steps con "Nota: verificar/ajustar" señalan puntos donde el código existente debe leerse antes de aplicar el snippet (nombres internos no visibles al 100% desde el assessment); el código de intención está completo en cada caso.
3. **Consistencia de tipos:** `CleanupRequest` con defaults se usa igual en Task 1 tests e implementación; `parse_docker_size -> int` consistente; `is_protected_path(str) -> bool` según firma existente.
