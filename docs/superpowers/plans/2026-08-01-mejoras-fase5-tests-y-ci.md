# Plan de Mejoras — Fase 5: Tests y CI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que romper el proyecto sea difícil: una suite rápida que la gente corra de verdad, los huecos de cobertura que dejaron las fases anteriores, y CI que verifique cada push y pull request.

**Architecture:** Primero se arregla la suite que ya existe (hoy dos tests consumen el 93 % del tiempo), luego se cierran los huecos de cobertura conocidos, luego se hace verificable el frontend, y solo entonces se automatiza en GitHub Actions. El orden importa: automatizar una suite lenta o roja produce CI que la gente ignora.

**Tech Stack:** pytest, GitHub Actions, Astro/TypeScript (`astro check`), Make.

## Global Constraints

- Tests: `venv-web/bin/python -m pytest tests/ -v` desde la raíz. Baseline: **137 passed**. Verde antes de cada commit.
- Mensajes de cara al usuario en español; comentarios de código en inglés.
- **Ningún test puede depender del contenido real de la máquina.** Ni del `$HOME` del usuario, ni de sus cachés, ni de que Docker esté instalado. Un test que pasa en tu portátil y falla en CI (o al revés) es peor que no tenerlo.
- **Ningún test puede borrar archivos reales.** Todo lo que toque rutas destructivas usa `tmp_path` y monkeypatch.
- El CLI sigue sin dependencias externas: nada de lo que se añada puede obligar a instalar algo para correr `disk_analyzer.py`.
- Python 3.13, Node 25, npm 11. Existe `web/package-lock.json`, así que `npm ci` es válido.
- Un commit por task.

## Contexto: de qué se parte

Verificado sobre `main` (commit `4e19107`):

- **137 tests en 17 archivos**, todos en verde.
- **Dos tests consumen 39 de los 42 segundos**: `test_preview_without_categories_is_accepted`
  (20,05 s) y `test_execute_dry_run_returns_preview` (19,12 s), ambos en
  `tests/test_cleanup_api.py`. Pasan `str(Path.home())` al endpoint, que acaba
  escaneando las cachés reales de la máquina. Es el hallazgo que la Fase 1 dejó
  diferido, y es la razón por la que la suite tarda lo que tarda.
- **No existe `.github/workflows/`**: no hay CI de ningún tipo. Los PR #5, #6 y
  #7 se auto-mergearon al instante justamente porque no había checks que
  esperar.
- **El frontend no tiene chequeo de tipos ejecutable**: `web/package.json` solo
  define `dev`, `build` y `preview`, y sus devDependencies son `@types/react`,
  `@types/react-dom` y `typescript` — falta `@astrojs/check`, que es lo que
  `astro check` necesita.
- **Hay 5 errores de tipos preexistentes** que un chequeo bloqueante haría
  fallar desde el primer día: tipos de `plotly.js-dist-min`,
  `default_min_size_mb` ausente en la interfaz `SystemInfo` que usa
  `HeroScan.tsx`, el namespace `NodeJS`, y un estrechamiento de tipos en
  `ReverseView.tsx`. El Task 4 los arregla antes de que el Task 5 los haga
  bloqueantes.
- **No hay tests de frontend** de ningún tipo, ni infraestructura para
  escribirlos.

### Deudas de test que arrastran las fases anteriores

Registradas en el
[registro de ejecución](2026-07-15-registro-ejecucion.md) y asignadas a esta
fase:

| Deuda | Origen |
|---|---|
| Un test escanea el `Path.home()` real: lento y dependiente de la máquina | Fase 1 |
| El test de cableado del reaper arranca el ciclo de vida completo (fixture pesada) | Fase 1 |
| Falta un test end-to-end del camino 429 (máximo de sesiones) de `create_terminal` | Fase 1 |
| `tests/test_auth.py` recarga el módulo nueve veces y deja una entrada viva en `websocket_connections` | Fase 2 |
| No hay tests de la lógica de fallo cerrado del frontend | Fase 2 |

---

### Task 1: Acelerar la suite quitándole la dependencia de la máquina

Dos tests consumen el 93 % del tiempo porque escanean las cachés reales del
usuario. Además de lentos, son frágiles: su resultado depende de qué tenga
instalado quien los corre, y en CI escanearían el `$HOME` vacío del runner, con
lo que probarían algo distinto a lo que prueban aquí.

**Files:**
- Modify: `tests/test_cleanup_api.py`
- Test: el propio archivo es el entregable

**Interfaces:**
- Consumes: `disk_analyzer_web._scan_cleanup_actions(paths, categories)`, `DiskAnalyzerCore.find_cache_locations()`
- Produces: una suite cuyo tiempo total baja de ~42 s a menos de 10 s, sin perder cobertura

- [ ] **Step 1: Medir el punto de partida**

Run: `venv-web/bin/python -m pytest tests/ -q --durations=5`
Anotar el total y los cinco más lentos. Esta cifra es el antes.

- [ ] **Step 2: Entender por qué son lentos antes de tocarlos**

`find_cache_locations()` no escanea la ruta que se le pasa al endpoint: recorre
`CACHE_DIRS`, la lista fija de ubicaciones conocidas de caché
(`~/Library/Caches`, `~/.npm`, etc.). Por eso pasar `Path.home()` dispara un
recorrido de gigabytes.

Dato importante verificado en la Fase 3: `disk_analyzer_core.py` hace
`from analyzer.constants import CACHE_DIRS`, así que el nombre queda ligado en
el espacio del módulo al importarse. Parchear `analyzer.constants.CACHE_DIRS`
**no** intercepta; hay que parchear `disk_analyzer_core.CACHE_DIRS`.

- [ ] **Step 3: Reescribir los dos tests contra un árbol controlado**

En `tests/test_cleanup_api.py`, sustituir el uso de `Path.home()` por un
directorio temporal con contenido conocido:

```python
@pytest.fixture
def fake_caches(tmp_path, monkeypatch):
    """A controlled stand-in for the machine's real cache dirs.

    Without this the endpoint walks the user's actual ~/Library/Caches, which
    makes the test slow (~20s) and its result dependent on whatever the person
    running it happens to have installed.
    """
    import disk_analyzer_core

    big = tmp_path / "Caches" / "com.example.big"
    big.mkdir(parents=True)
    (big / "blob.bin").write_bytes(b"x" * (3 * 1024 * 1024))   # 3 MB, over the 1 MB threshold

    monkeypatch.setattr(disk_analyzer_core, "CACHE_DIRS", [str(tmp_path / "Caches")])
    return tmp_path
```

Y usarla en los dos tests, pasando `str(fake_caches)` como `paths` en lugar de
`str(Path.home())`. Mantener intactas las aserciones sobre la forma de la
respuesta (`actions`, `total_size`, `dry_run`).

Nota: verificar el nombre real del atributo en `disk_analyzer_core` con
`grep -n "CACHE_DIRS" disk_analyzer_core.py` antes de parchear, y añadir un test
canario que confirme que el parcheo intercepta de verdad:

```python
def test_cache_dirs_patch_actually_intercepts(fake_caches):
    """Guard: if this fails, the other tests are scanning the real machine."""
    import disk_analyzer_core
    core = disk_analyzer_core.DiskAnalyzerCore(str(fake_caches))
    core.find_cache_locations()
    for loc in core.cache_locations:
        assert str(fake_caches) in loc["path"], (
            f"leaked outside the fixture: {loc['path']}"
        )
```

- [ ] **Step 4: Verificar la mejora y que no se perdió cobertura**

Run: `venv-web/bin/python -m pytest tests/ -q --durations=5`
Expected: los dos tests bajan de ~20 s a milisegundos; el total baja de ~42 s a
menos de 10 s; siguen pasando 137 tests más el canario.

Si algún test empieza a pasar por la razón equivocada (por ejemplo, `actions`
queda vacío y las aserciones se cumplen trivialmente), corregirlo: la fixture
crea una caché de 3 MB precisamente para que haya algo que encontrar.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cleanup_api.py
git commit -m "test: los tests de cleanup ya no escanean las cachés reales de la máquina"
```

---

### Task 2: Cerrar los huecos de cobertura del API

Endpoints que hoy no toca ningún test: los tres formatos de export, el borrado
de archivos (incluidas sus defensas), el digest y el "último análisis".

**Files:**
- Create: `tests/test_export_api.py`, `tests/test_files_api.py`
- Test: ambos archivos son el entregable

**Interfaces:**
- Consumes: `GET /api/export/{session_id}/{format}` (json/csv/html), `DELETE /api/files/delete`, `GET /api/digest`, `GET /api/analysis/latest`
- Produces: cobertura de los cuatro, incluidos los caminos de error

- [ ] **Step 1: Escribir los tests de export**

Crear `tests/test_export_api.py`:

```python
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
    """Register a completed session with a minimal but realistic report."""
    session_id = "test-export-session"
    report = {
        "summary": {"total_size": 1024, "files_scanned": 2},
        "large_files": [
            {"path": "/fake/a.bin", "size": 2048, "extension": ".bin",
             "age_days": 5, "is_cache": False},
            {"path": "/fake/b.log", "size": 1024, "extension": ".log",
             "age_days": 30, "is_cache": True},
        ],
        "top_directories": [],
        "cache_locations": [],
        "recommendations": [],
        "file_types": {},
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
```

Nota: leer el handler `export_results` antes de escribir, para confirmar el
nombre exacto de las claves del reporte que consume el generador HTML. Si el
export HTML necesita más campos de los que trae este reporte mínimo, ampliarlo
hasta que funcione — pero mantenerlo inventado, sin leer nada de la máquina.

- [ ] **Step 2: Correr y ajustar hasta verde**

Run: `venv-web/bin/python -m pytest tests/test_export_api.py -v`
Expected: PASS los cinco. Si el export HTML falla por un campo que falta en el
reporte de la fixture, añadirlo; si falla por un bug real del generador,
**anotarlo en el reporte y dejar el test marcado con `pytest.mark.xfail` con una
razón explícita**, sin arreglar el bug en este task.

- [ ] **Step 3: Escribir los tests de borrado de archivos**

Crear `tests/test_files_api.py`:

```python
"""Tests for DELETE /api/files/delete, including its defenses."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import disk_analyzer_web
from disk_analyzer_web import app


class TestDeleteFile:
    def setup_method(self):
        self.client = TestClient(app)

    def test_relative_path_is_rejected(self):
        resp = self.client.request(
            "DELETE", "/api/files/delete", json={"path": "relative/file.txt"}
        )
        assert resp.status_code == 400

    def test_protected_path_is_refused(self, monkeypatch):
        monkeypatch.setattr(disk_analyzer_web, "is_protected_path", lambda p: True)
        resp = self.client.request(
            "DELETE", "/api/files/delete", json={"path": "/System/Library/Kernels/kernel"}
        )
        assert resp.status_code == 403

    def test_missing_file_is_404(self):
        resp = self.client.request(
            "DELETE", "/api/files/delete", json={"path": "/tmp/definitely-not-here-12345"}
        )
        assert resp.status_code == 404

    def test_real_file_is_removed(self, tmp_path, monkeypatch):
        victim = tmp_path / "junk.bin"
        victim.write_bytes(b"x" * 1024)
        monkeypatch.setattr(disk_analyzer_web, "is_protected_path", lambda p: False)
        resp = self.client.request(
            "DELETE", "/api/files/delete", json={"path": str(victim)}
        )
        assert resp.status_code == 200
        assert not victim.exists()
```

Nota importante: el test de borrado real depende de a dónde manda el archivo el
endpoint. En macOS usa `osascript` para mover a la Papelera, lo que es lento y
tiene efectos fuera del `tmp_path`. Leer el handler primero: si mueve a la
Papelera, parchear esa rama para que use borrado directo en el test (o parchear
`subprocess.run`), de modo que el test no dependa del Finder ni deje basura en
la Papelera del usuario. Documentar en el reporte qué se parcheó y por qué.

Verificar también el nombre real del símbolo importado en `disk_analyzer_web`
(`is_protected_path` tras la Fase 3) con
`grep -n "is_protected_path" disk_analyzer_web.py` antes de parchear.

- [ ] **Step 4: Añadir los tests de digest y latest**

Al mismo archivo `tests/test_files_api.py`:

```python
class TestDigestAndLatest:
    def setup_method(self):
        self.client = TestClient(app)

    def test_digest_responds_with_its_shape(self):
        resp = self.client.get("/api/digest")
        assert resp.status_code == 200
        body = resp.json()
        # The digest must always answer, even with no history at all
        assert isinstance(body, dict)

    def test_latest_with_no_sessions_is_handled(self, monkeypatch):
        monkeypatch.setattr(disk_analyzer_web, "analysis_sessions", {})
        resp = self.client.get("/api/analysis/latest")
        assert resp.status_code in (200, 404)
```

Nota: leer ambos handlers y afinar las aserciones a lo que devuelven de verdad
(por ejemplo, qué claves trae el digest). Un test que solo comprueba
`status_code == 200` sin mirar el cuerpo es de poco valor: añadir al menos una
aserción sobre una clave concreta que el handler garantice.

- [ ] **Step 5: Suite completa y commit**

```bash
venv-web/bin/python -m pytest tests/ -v
git add tests/test_export_api.py tests/test_files_api.py
git commit -m "test: cubrir export, borrado de archivos, digest y último análisis"
```

---

### Task 3: Saldar las deudas de test de las fases anteriores

Tres deudas concretas, todas registradas: falta el camino 429 del terminal, la
fixture de auth es innecesariamente pesada, y el test de cableado del reaper
arranca la aplicación entera.

**Files:**
- Modify: `tests/test_terminal_api.py`, `tests/test_auth.py`
- Test: ambos archivos

**Interfaces:**
- Consumes: `POST /api/terminal/create` (429 al superar `max_sessions`), `PTYManager(max_sessions=...)`
- Produces: cobertura del 429 end-to-end y una fixture de auth que no recarga el módulo nueve veces

- [ ] **Step 1: Test end-to-end del 429**

`tests/test_pty_manager.py` ya prueba que `PTYManager` lanza `RuntimeError` al
superar el máximo, pero nada comprueba que el endpoint lo traduzca a un 429 —
y ese camino cambió en la Fase 2 al envolverlo en `asyncio.to_thread`. Añadir a
`tests/test_terminal_api.py`:

```python
def test_create_terminal_beyond_max_sessions_is_429(self, monkeypatch):
    """The manager raises RuntimeError; the endpoint must surface it as 429.

    This path changed when create_session moved to asyncio.to_thread, and
    nothing covered it end to end until now.
    """
    import disk_analyzer_web

    def boom(*args, **kwargs):
        raise RuntimeError("Maximum sessions reached")

    monkeypatch.setattr(disk_analyzer_web.pty_manager, "create_session", boom)
    resp = self.client.post("/api/terminal/create", json={})
    assert resp.status_code == 429
```

Nota: confirmar con `grep -n "429" disk_analyzer_web.py` que el endpoint mapea
`RuntimeError` a 429 y no a otro código; si mapea a otro, el test afirma el
código real y se anota la discrepancia con la documentación en el reporte.

- [ ] **Step 2: Correr y verificar**

Run: `venv-web/bin/python -m pytest tests/test_terminal_api.py -v`
Expected: PASS, incluido el nuevo.

- [ ] **Step 3: Aligerar la fixture de auth**

`tests/test_auth.py` llama a `_load_app`, que hace `importlib.reload` del módulo
entero, nueve veces. Cada recarga construye un `ThreadPoolExecutor`, un
`PTYManager`, un `AgentsManager` y vuelve a ejecutar el `mkdir` de
`RESULTS_DIR` contra el `$HOME` real.

Reducir el coste sin perder el aislamiento: mantener la recarga solo donde el
test necesita de verdad un módulo cargado con otras variables de entorno (los
casos con y sin auth), y en el resto reutilizar una instancia por módulo. Una
forma directa es una fixture con `scope="module"` para cada uno de los dos modos
(auth activa y `--no-auth`), en vez de recargar por test.

Requisito que no se puede sacrificar: `test_auth.py` debe seguir pasando cuando
se corre **aislado** (`venv-web/bin/python -m pytest tests/test_auth.py -v`) y
dentro de la suite completa, en ambos casos. Verificar las dos formas.

- [ ] **Step 4: Limpiar la conexión que queda viva**

El test que abre un WebSocket de progreso con token válido deja una entrada en
`disk_analyzer_web.websocket_connections`. Añadir la limpieza al final del test
(o una fixture que lo haga), para que no contamine a los que corren después.

- [ ] **Step 5: Verificar aislamiento y commit**

```bash
venv-web/bin/python -m pytest tests/test_auth.py -v
venv-web/bin/python -m pytest tests/ -q --durations=5
git add tests/test_terminal_api.py tests/test_auth.py
git commit -m "test: cubrir el 429 del terminal y aligerar la fixture de auth"
```

---

### Task 4: Hacer verificable el frontend

Hoy no hay forma de comprobar el frontend salvo mirarlo. `npm run build` no
chequea tipos, y hay cinco errores de tipos preexistentes que hay que arreglar
antes de que un chequeo pueda ser bloqueante.

**Files:**
- Modify: `web/package.json`, `web/src/lib/api.ts`, `web/src/components/HeroScan.tsx`, `web/src/components/ReverseView.tsx`, y los demás archivos que reporten errores
- Create: `web/src/types/plotly.d.ts` (si hace falta para los tipos de plotly)

**Interfaces:**
- Produces: `npm run check` en `web/` sale con código 0

- [ ] **Step 1: Ver los errores reales**

```bash
cd web && npx tsc --noEmit
```
Anotar la lista completa. Los conocidos son cinco: tipos de
`plotly.js-dist-min`, `default_min_size_mb` ausente en la interfaz `SystemInfo`
que usa `HeroScan.tsx`, el namespace `NodeJS`, y un estrechamiento de tipos en
`ReverseView.tsx`. Puede haber más o menos; la lista real manda.

- [ ] **Step 2: Instalar el chequeo de Astro y añadir el script**

```bash
cd web && npm install --save-dev @astrojs/check
```

Y en `web/package.json`, añadir a `scripts`:

```json
    "check": "astro check"
```

`astro check` entiende los archivos `.astro` además de los `.ts`/`.tsx`, que
`tsc` solo no cubre. Confirmar que el `package-lock.json` queda actualizado y se
commitea (CI usará `npm ci`, que exige que el lockfile coincida).

- [ ] **Step 3: Arreglar los errores de tipos, uno por uno**

Dos de ellos tienen arreglo evidente y ya estaban registrados como deuda de la
Fase 1 y la Fase 2:

En `web/src/lib/api.ts`, la interfaz `SystemInfo` no declara el campo que el
backend sí devuelve, y `AnalysisSession` no declara los que le adjunta el
backend ni el estado `'interrupted'` que introdujo la Fase 1:

```typescript
export interface SystemInfo {
  // ...campos existentes...
  default_min_size_mb?: number;
}

export interface AnalysisSession {
  // ...campos existentes...
  status: 'running' | 'completed' | 'error' | 'cancelled' | 'interrupted';
  disk_used?: number;
  disk_total?: number;
}
```

Con eso deberían desaparecer también varios `any` de conveniencia repartidos por
los componentes: buscarlos (`grep -rn "as any\|: any" web/src`) y quitar los que
el tipado correcto vuelve innecesarios. No perseguir todos los `any` del
proyecto — solo los que existían para tapar estos huecos.

Para los tipos de `plotly.js-dist-min` (que no trae los suyos), declarar el
módulo:

```typescript
// web/src/types/plotly.d.ts
declare module 'plotly.js-dist-min' {
  const Plotly: any;
  export default Plotly;
}
```

Es deliberadamente laxo: tipar la API entera de Plotly no aporta aquí y sería
mucho trabajo. Dejar el comentario explicándolo para que nadie lo "mejore" sin
motivo.

Los demás errores se arreglan según lo que diga el compilador. Regla: **arreglar
el tipo, no silenciarlo**. Nada de `@ts-ignore` salvo que se documente en el
mismo sitio por qué es inevitable.

- [ ] **Step 4: Verificar que el chequeo pasa y el build sigue funcionando**

```bash
cd web && npm run check && npm run build
```
Expected: ambos con código 0, sin errores.

- [ ] **Step 5: Verificar que no se rompió el backend**

Los tipos son solo del frontend, pero `api.ts` describe el contrato con el
backend: si al tiparlo se descubre que el backend devuelve algo distinto de lo
declarado, eso es un hallazgo — anotarlo en el reporte.

Run: `venv-web/bin/python -m pytest tests/ -q`

- [ ] **Step 6: Commit**

```bash
git add web/package.json web/package-lock.json web/src
git commit -m "fix(web): arreglar los errores de tipos preexistentes y añadir npm run check"
```

---

### Task 5: CI en GitHub Actions y `make test`

Con la suite rápida, los huecos cerrados y el frontend verificable, se puede
automatizar. Un solo workflow con dos jobs independientes.

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `Makefile`

**Interfaces:**
- Produces: el workflow `CI` con los jobs `backend` y `frontend`, que corre en `push` a `main` y en cada `pull_request`; y el target `make test`

- [ ] **Step 1: Añadir `make test`**

En el `Makefile`, junto a los demás targets, añadir uno que corra lo mismo que
CI, para que se pueda reproducir en local antes de subir:

```make
test: ## Ejecuta la suite de tests (backend + chequeo del frontend)
	@echo "$(BLUE)🧪 Tests del backend...$(NC)"
	@. venv-web/bin/activate && python -m pytest tests/ -v
	@echo "$(BLUE)🧪 Chequeo de tipos del frontend...$(NC)"
	@cd web && npm run check
	@echo "$(GREEN)✅ Todo en verde$(NC)"
```

Respetar el estilo del `Makefile` (variables de color, comentarios `##` para el
menú de ayuda). Verificar con `make -n test` que la sintaxis es válida y que el
target aparece en `make help`.

- [ ] **Step 2: Escribir el workflow**

Crear `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  backend:
    name: Backend (pytest)
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-web.txt
          pip install pytest httpx

      - name: Run tests
        run: python -m pytest tests/ -v

  frontend:
    name: Frontend (build + types)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: npm
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Type check
        run: npm run check

      - name: Build
        run: npm run build
```

Dos decisiones deliberadas que conviene entender:

- **El job de backend corre en macOS**, no en Ubuntu, aunque sea más lento y
  escaso: el proyecto es específico de macOS y los tests de PTY dependen de
  `pty.openpty()`, `os.fork()` y el comportamiento de `waitpid` de Darwin. En
  Ubuntu probarían otra cosa.
- **El job de frontend corre en Ubuntu**, porque es solo Node y ahí es más
  rápido y barato.

- [ ] **Step 3: Verificar el workflow antes de subirlo**

Comprobar la sintaxis del YAML sin depender de que GitHub lo acepte:

```bash
venv-web/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"
```

(Si `yaml` no está instalado en el venv, usar `python3 -c` con el del sistema, o
`pip install pyyaml` solo para la comprobación.)

Y reproducir en local exactamente lo que hará CI:

```bash
venv-web/bin/python -m pytest tests/ -v
cd web && npm ci && npm run check && npm run build
```

Ojo: `npm ci` **borra `node_modules` y lo reinstala desde el lockfile**. Es lo
que hará CI, así que conviene comprobar que funciona, pero tarda. Si falla
porque el lockfile no está sincronizado con `package.json`, arreglarlo aquí —
sería el primer fallo de CI en cuanto se suba.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml Makefile
git commit -m "ci: workflow de GitHub Actions para backend y frontend, y make test"
```

- [ ] **Step 5: Comprobar que CI corre de verdad**

Tras subir la rama, verificar que el workflow aparece y qué resultado da:

```bash
gh run list --limit 3
gh run watch
```

Si algo falla en CI pero pasa en local, la causa más probable es una dependencia
del entorno: el `$HOME` del runner está vacío, no hay Docker, y no hay cachés de
usuario. Eso es exactamente lo que el Task 1 previene — si aun así falla, el
test que falle tiene una dependencia oculta que hay que quitar, no un
`skip` que ponerle.

---

### Task 6: Verificación integral y protección de la rama

**Files:** ninguno de código. Documentación y una recomendación al dueño.

- [ ] **Step 1: Suite completa y tiempos**

```bash
venv-web/bin/python -m pytest tests/ -q --durations=10
```
Expected: verde, y el total claramente por debajo de los ~42 s de partida.
Anotar la cifra final.

- [ ] **Step 2: `make test` de punta a punta**

```bash
make test
```
Expected: backend y frontend en verde.

- [ ] **Step 3: Confirmar que CI está en verde en GitHub**

```bash
gh run list --limit 3
```

- [ ] **Step 4: Actualizar la documentación**

En `docs/superpowers/plans/2026-07-15-registro-ejecucion.md`, añadir la sección
de la Fase 5 con el mismo formato que las anteriores: tabla de tasks con sus
commits, y la cifra de antes/después del tiempo de la suite.

En `docs/superpowers/plans/README.md`, actualizar el estado de la fase, el número
de tests y la siguiente acción.

En `README_WEB.md` o `CLAUDE.md`, mencionar `make test` como la forma de
verificar el proyecto.

- [ ] **Step 5: Recomendar la protección de la rama, sin aplicarla**

Ahora que hay checks, tiene sentido exigirlos antes de mergear — hoy los
auto-merges se fusionan al instante porque no hay nada que esperar.

**No aplicar este cambio sin permiso explícito del dueño del repositorio**: es
una modificación de la configuración de GitHub, no del código, y afecta a cómo
trabaja cualquiera en el proyecto. Dejar preparado el comando y explicarlo:

```bash
# Requiere confirmación del dueño antes de ejecutarse
gh api -X PUT repos/ArtemioPadilla/Disk-Use-Analyzer/branches/main/protection \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[contexts][]=Backend (pytest)' \
  -f 'required_status_checks[contexts][]=Frontend (build + types)' \
  -F 'enforce_admins=false' \
  -F 'required_pull_request_reviews=null' \
  -F 'restrictions=null'
```

- [ ] **Step 6: Commit final**

```bash
git add docs/ README_WEB.md CLAUDE.md
git commit -m "docs: cerrar el registro de la Fase 5 (tests y CI)"
```

---

## Fuera del alcance de esta fase

- **Tests de frontend (Vitest o similar).** El proyecto no tiene ninguna
  infraestructura de test de JavaScript, y montarla es un proyecto en sí:
  elegir runner, configurar jsdom, decidir qué se prueba de una arquitectura de
  islas que se comunica por eventos de `window`. El chequeo de tipos del Task 4
  es la primera red, y es mucho más barata. Si se aborda, la lógica de fallo
  cerrado de `AgentsPanel` es el primer candidato.
- **Cobertura medida (`pytest-cov`).** Añadir el número es fácil; decidir un
  umbral que no sea teatro requiere tener la suite ya asentada. Después.
- **Correr los tests en varias versiones de Python.** El proyecto declara 3.6+
  pero se desarrolla en 3.13. Antes de gastar minutos de CI en una matriz,
  conviene decidir si ese "3.6+" sigue siendo cierto.

## Self-Review (ejecutado al escribir el plan)

1. **Cobertura del alcance:** el roadmap pedía para esta fase la suite del motor
   como permanente (ya está desde la Fase 3), los tests de API que faltaban
   (Task 2), CI con los dos jobs (Task 5) y `make test` (Task 5). Se añaden las
   cinco deudas registradas de fases anteriores (Tasks 1 y 3) y el prerequisito
   que el roadmap no vio: sin arreglar los cinco errores de tipos, el job de
   frontend sería rojo desde el primer commit (Task 4).
2. **Placeholders:** los "verificar antes de parchear" señalan puntos donde el
   nombre real de un símbolo debe confirmarse en el código; el código de
   intención está completo en cada paso. El único bloque deliberadamente laxo es
   la declaración de tipos de Plotly, con su razón escrita al lado.
3. **Consistencia:** `disk_analyzer_core.CACHE_DIRS` es el objetivo de parcheo
   en los Tasks 1 y 2 (no `analyzer.constants.CACHE_DIRS`, que no intercepta);
   `is_protected_path` se parchea sobre `disk_analyzer_web`, que es donde la
   Fase 3 la dejó importada; `npm run check` se define en el Task 4 y se consume
   en el Task 5.
4. **Riesgo principal:** que CI falle por dependencias del entorno que en local
   no se notan. El Task 1 lo ataca de raíz (quitar la dependencia del `$HOME`
   real) y el Task 5 lo dice explícitamente: si un test falla solo en CI, se le
   quita la dependencia oculta, no se le pone un `skip`.
