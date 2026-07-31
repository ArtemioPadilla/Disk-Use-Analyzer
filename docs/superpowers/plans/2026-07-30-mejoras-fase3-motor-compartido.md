# Plan de Mejoras — Fase 3: Motor compartido

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar la duplicación entre `disk_analyzer.py` (CLI) y `disk_analyzer_core.py` (motor de web y GUI), para que un bug se arregle en un solo lugar.

**Architecture:** Extracción incremental a un paquete `analyzer/`, en orden de riesgo creciente: primero una red de tests de caracterización, luego las constantes (idénticas byte a byte, movimiento mecánico), luego la protección de rutas, luego la clasificación de cachés (la única con implicaciones de comportamiento reales), y por último el escaneo. `disk_analyzer.py` conserva su CLI y su generador de reportes HTML; deja de tener su propia copia del motor.

**Tech Stack:** Python 3.13, pytest. Sin dependencias nuevas: el CLI debe seguir funcionando solo con la biblioteca estándar.

## Global Constraints

- Tests: `venv-web/bin/python -m pytest tests/ -v` desde la raíz. Baseline: **79 passed**. Verde antes de cada commit.
- **El CLI no puede adquirir dependencias externas.** `analyzer/` usa solo la biblioteca estándar. Verificación: `python3 -c "import analyzer"` con el Python del sistema, sin venv.
- Mensajes de cara al usuario en español; comentarios de código en inglés.
- **Ningún cambio de comportamiento salvo donde este plan lo diga explícitamente.** Los tests de caracterización del Task 1 son el contrato: si uno se rompe en un task posterior, es un bug del refactor, no un test que actualizar — salvo que el task diga lo contrario y explique por qué.
- Cada task es un commit. No mezclar movimiento mecánico con cambio de comportamiento en el mismo commit.
- Al terminar cada task, verificar las tres interfaces a mano, no solo la suite:
  `venv-web/bin/python disk_analyzer.py ./test --min-size 1` (o cualquier ruta pequeña),
  `venv-web/bin/python -c "import disk_analyzer_web"`, y
  `venv-web/bin/python -c "import disk_analyzer_gui"` (puede fallar por falta de customtkinter: eso es aceptable, lo que importa es que no falle por el refactor).

## Contexto: qué está duplicado

Inventario verificado. La duplicación es **bidireccional** entre `DiskAnalyzer`
(4.882 líneas) y `DiskAnalyzerCore` (762). La GUI no tiene motor propio: importa
el core. `disk_analyzer_web.py` importa el core, y toca el monolito en un solo
punto (`generate_html_report`, para el export HTML).

- **Constantes idénticas en valor** (`KB/MB/GB`, `CACHE_DIRS` en sus tres
  variantes de plataforma, `LARGE_FILE_EXTENSIONS`, `IGNORE_PATTERNS`,
  `MACOS_APFS_SKIP_DIRS`, `PROTECTED_*`): copia literal, sin divergencias.
- **Métodos idénticos**: `format_size`, `get_file_age`, `is_cache_or_temp`,
  `should_ignore`, `is_protected_path`, `get_home_dir`, `get_temp_dirs`,
  `get_disk_usage`.
- **Divergencias reales que hay que reconciliar**:
  - `get_directory_size`: el CLI usa `du -sk` por subproceso
    (`disk_analyzer.py:553`), el core recorre con `rglob` y `st_blocks`
    (`disk_analyzer_core.py:388`). Pueden dar totales distintos para el mismo
    directorio.
  - `find_cache_locations`: el CLI solo reporta si `size > MB`
    (`disk_analyzer.py:378`), el core si `size > 0`
    (`disk_analyzer_core.py:372`).
  - Clasificación de cachés: el CLI tiene `classify_cache` con 8 etiquetas
    (`'Docker'`, `'Xcode Development'`, `'VS Code'`, `'Node.js/npm'`,
    `'Downloads'`, `'Papelera'`, `'Logs del Sistema'`, `'Cache General'`); el
    core tiene `categorize_cache` con 12 (`'VS Code Cache'`, `'Chrome Cache'`,
    `'Firefox Cache'`, `'NPM Cache'`, `'Python Cache'`, `'Xcode Cache'`,
    `'Docker'`, `'Papelera'`, `'Archivos Temporales'`, `'Logs del Sistema'`,
    `'Downloads'`, `'Cache General'`), con distinta precedencia.
  - `get_all_drives`: devuelve `List[str]` en el CLI, `List[Dict]` en el core.
  - `scan_directory`: misma lógica de conteo; difiere el andamiaje (progreso por
    TTY y estimación de ETA en el CLI; callback de progreso, cancelación y
    `max_depth` en el core).

**Trampa conocida:** las etiquetas de caché no son cosméticas. Las consume el
safelist de `clean_cache` (`disk_analyzer.py`), los filtros de
`generate_recommendations` en ambos módulos, y el emparejamiento por categoría
de `/api/cleanup/preview`. Cambiar una etiqueta sin actualizar a sus tres
consumidores rompe funcionalidad en silencio: ya pasó una vez (Fase 1, Task 3).

---

### Task 1: Red de tests de caracterización del motor

Antes de mover una sola línea hay que fijar el comportamiento actual. Hoy el
motor no tiene ningún test: la suite cubre terminal, auth, agents y cleanup, pero
nada de escaneo, categorización ni recomendaciones. Sin esta red, el refactor es
a ciegas.

Estos tests describen **lo que el código hace hoy**, no lo que debería hacer. Si
alguno documenta algo que parece un bug, se anota en el reporte y se deja pasar:
arreglarlo es otra tarea, no esta.

**Files:**
- Create: `tests/test_engine_characterization.py`
- Test: el archivo es el entregable

**Interfaces:**
- Consumes: `DiskAnalyzerCore` de `disk_analyzer_core.py`; `DiskAnalyzer` de `disk_analyzer.py`
- Produces: una suite que cualquier task posterior puede correr para detectar regresiones del refactor

- [ ] **Step 1: Escribir los tests de tamaño y escaneo**

Crear `tests/test_engine_characterization.py`:

```python
"""Characterization tests: pin the engine's CURRENT behavior before refactoring.

These describe what the code does today, not what it ideally should do.
A failure here during the shared-engine extraction means the refactor changed
behavior — fix the refactor, not the test.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from disk_analyzer_core import DiskAnalyzerCore, KB, MB, GB


@pytest.fixture
def tree(tmp_path):
    """A small, predictable directory tree."""
    (tmp_path / "big.bin").write_bytes(b"x" * (3 * 1024 * 1024))   # 3 MB
    (tmp_path / "small.txt").write_text("hello")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.bin").write_bytes(b"y" * (2 * 1024 * 1024))     # 2 MB
    ignored = tmp_path / "node_modules"
    ignored.mkdir()
    (ignored / "junk.bin").write_bytes(b"z" * (5 * 1024 * 1024))
    return tmp_path


class TestFormatSize:
    def test_bytes(self):
        core = DiskAnalyzerCore(".")
        assert core.format_size(0) == "0.00 B"

    def test_kilobytes(self):
        core = DiskAnalyzerCore(".")
        assert core.format_size(1536).endswith("KB")

    def test_gigabytes(self):
        core = DiskAnalyzerCore(".")
        assert core.format_size(5 * GB).startswith("5.00")


class TestScanDirectory:
    def test_finds_large_files_above_min_size(self, tree):
        core = DiskAnalyzerCore(str(tree), min_size_mb=1)
        core.scan_directory(tree)
        names = {Path(f["path"]).name for f in core.large_files}
        assert "big.bin" in names
        assert "small.txt" not in names

    def test_uses_real_disk_blocks_not_logical_size(self, tree):
        core = DiskAnalyzerCore(str(tree), min_size_mb=1)
        core.scan_directory(tree)
        entry = next(f for f in core.large_files if Path(f["path"]).name == "big.bin")
        stat = (tree / "big.bin").stat()
        expected = stat.st_blocks * 512 if hasattr(stat, "st_blocks") else stat.st_size
        assert entry["size"] == expected

    def test_skips_ignored_directories(self, tree):
        core = DiskAnalyzerCore(str(tree), min_size_mb=1)
        core.scan_directory(tree)
        paths = " ".join(f["path"] for f in core.large_files)
        assert "node_modules" not in paths

    def test_does_not_follow_symlinks(self, tmp_path):
        target = tmp_path / "real"
        target.mkdir()
        (target / "file.bin").write_bytes(b"a" * (2 * 1024 * 1024))
        link = tmp_path / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks not supported here")
        core = DiskAnalyzerCore(str(tmp_path), min_size_mb=1)
        core.scan_directory(tmp_path)
        # The file is found once (through the real dir), not twice via the link
        matches = [f for f in core.large_files if Path(f["path"]).name == "file.bin"]
        assert len(matches) == 1

    def test_records_file_type_stats(self, tree):
        core = DiskAnalyzerCore(str(tree), min_size_mb=1)
        core.scan_directory(tree)
        assert ".bin" in core.file_type_stats


class TestProtectedPaths:
    @pytest.mark.parametrize("path,expected", [
        ("/System/Library/Kernels/kernel", True),
        ("/usr/lib/libSystem.dylib", True),
        ("/bin", True),
        ("/sbin", True),
        ("/Applications/Foo.app/Contents/MacOS/Foo", True),
        ("/private/var/vm/sleepimage", True),
        (str(Path.home() / "Downloads" / "movie.mp4"), False),
        (str(Path.home() / "Library" / "Caches" / "something"), False),
    ])
    def test_protection_table(self, path, expected):
        core = DiskAnalyzerCore(".")
        assert core.is_protected_path(path) is expected

    def test_prefix_match_not_substring(self):
        """A path merely CONTAINING a protected prefix is not protected."""
        core = DiskAnalyzerCore(".")
        assert core.is_protected_path(str(Path.home() / "my/System/notes.txt")) is False
```

Nota: antes de escribir estos tests, leer las firmas reales de
`DiskAnalyzerCore.__init__` (parámetros y sus nombres, por ejemplo si es
`min_size_mb` u otro) y de `scan_directory`, y ajustar las llamadas. Si
`format_size` devuelve otro formato exacto, ajustar los asserts a lo que
devuelve hoy: el objetivo es fijar el comportamiento real, no imponer uno.

- [ ] **Step 2: Escribir los tests de clasificación de cachés y recomendaciones**

Añadir al mismo archivo:

```python
class TestCacheClassification:
    """Pins the CURRENT labels of both implementations, which differ.

    Task 4 unifies them; these tests are what proves the unification did not
    silently drop a category.
    """

    @pytest.mark.parametrize("path,expected", [
        (Path.home() / "Library/Caches/com.docker.docker", "Docker"),
        (Path.home() / "Library/Developer/Xcode/DerivedData", "Xcode Cache"),
        (Path.home() / "Library/Caches/com.microsoft.VSCode", "VS Code Cache"),
        (Path.home() / ".npm", "NPM Cache"),
        (Path.home() / ".Trash", "Papelera"),
    ])
    def test_core_labels(self, path, expected):
        core = DiskAnalyzerCore(".")
        assert core.categorize_cache(path) == expected

    def test_cli_labels_differ_from_core(self):
        """Documents the divergence Task 4 removes."""
        from disk_analyzer import DiskAnalyzer
        cli = DiskAnalyzer(".")
        core = DiskAnalyzerCore(".")
        vscode = Path.home() / "Library/Caches/com.microsoft.VSCode"
        assert cli.classify_cache(vscode) == "VS Code"
        assert core.categorize_cache(vscode) == "VS Code Cache"


class TestRecommendations:
    def test_recommendations_have_required_shape(self):
        core = DiskAnalyzerCore(".")
        core.cache_locations = [
            {"path": "/fake/npm", "size": 3 * GB, "type": "NPM Cache"},
            {"path": "/fake/code", "size": 2 * GB, "type": "VS Code Cache"},
        ]
        recs = core.generate_recommendations()
        assert recs, "expected recommendations for large known caches"
        for rec in recs:
            assert "type" in rec
            assert "space" in rec
            assert "tier" in rec

    def test_recommendations_sorted_by_tier_then_size(self):
        core = DiskAnalyzerCore(".")
        core.cache_locations = [
            {"path": "/fake/npm", "size": 3 * GB, "type": "NPM Cache"},
            {"path": "/fake/code", "size": 9 * GB, "type": "VS Code Cache"},
        ]
        recs = core.generate_recommendations()
        tiers = [r["tier"] for r in recs]
        assert tiers == sorted(tiers)
```

Nota: verificar con `grep -n "def generate_recommendations" -A 40
disk_analyzer_core.py` las claves reales que produce (`type`, `space`, `tier`,
`command`, …) y ajustar. Si el orden no resulta ser por tier, fijar el orden
real, no el deseado.

- [ ] **Step 3: Correr y confirmar que pasan contra el código actual**

Run: `venv-web/bin/python -m pytest tests/test_engine_characterization.py -v`
Expected: PASS. Estos tests describen el presente; si alguno falla, es que la
suposición sobre el comportamiento actual era incorrecta — corregir el test
para reflejar la realidad, y anotar la sorpresa en el reporte.

- [ ] **Step 4: Suite completa y commit**

Run: `venv-web/bin/python -m pytest tests/ -v` → 79 + los nuevos.

```bash
git add tests/test_engine_characterization.py
git commit -m "test: red de caracterización del motor antes de extraer el módulo compartido"
```

---

### Task 2: Extraer las constantes a `analyzer/constants.py`

Movimiento puramente mecánico: las constantes son idénticas en valor entre los
dos módulos. Sin cambio de comportamiento.

**Files:**
- Create: `analyzer/__init__.py`, `analyzer/constants.py`
- Modify: `disk_analyzer.py` (bloque de constantes ~líneas 21-133), `disk_analyzer_core.py` (~líneas 20-115)
- Test: `tests/test_engine_characterization.py` (añadir una comprobación)

**Interfaces:**
- Produces: `analyzer/constants.py` exportando `KB`, `MB`, `GB`, `SYSTEM`, `IS_WINDOWS`, `IS_MACOS`, `IS_LINUX`, `CACHE_DIRS`, `LARGE_FILE_EXTENSIONS`, `IGNORE_PATTERNS`, `MACOS_APFS_SKIP_DIRS`, `PROTECTED_PATH_PREFIXES`, `PROTECTED_APP_MARKERS`, `PROTECTED_FILENAMES`, `PROTECTED_ROOT_DIRS`
- Los dos módulos siguen re-exportando lo que ya exportaban: `disk_analyzer_web.py` importa `MB, GB, IS_MACOS, IS_WINDOWS` desde `disk_analyzer_core`, y `disk_analyzer_gui.py` importa `MB, GB`. Esos imports deben seguir funcionando sin tocar esos archivos.

- [ ] **Step 1: Crear el paquete**

`analyzer/__init__.py`:

```python
"""Shared analysis engine, used by the CLI, the web backend and the GUI.

Standard library only: the CLI must keep working without any pip install.
"""
```

- [ ] **Step 2: Mover las constantes**

Copiar el bloque de constantes **verbatim** desde `disk_analyzer.py` (líneas ~21
a ~133) a `analyzer/constants.py`, con su encabezado de docstring. No reescribir
valores ni reordenar entradas: es un movimiento, no una edición.

Antes de mover, verificar con `diff` que los dos bloques son de verdad idénticos
en valor:

```bash
venv-web/bin/python - <<'PY'
import disk_analyzer as a, disk_analyzer_core as c
for name in ["KB","MB","GB","CACHE_DIRS","LARGE_FILE_EXTENSIONS","IGNORE_PATTERNS",
             "MACOS_APFS_SKIP_DIRS","PROTECTED_PATH_PREFIXES","PROTECTED_APP_MARKERS",
             "PROTECTED_FILENAMES","PROTECTED_ROOT_DIRS"]:
    va, vc = getattr(a, name, "<missing>"), getattr(c, name, "<missing>")
    print(f"{name}: {'IGUAL' if va == vc else 'DISTINTO'}")
    if va != vc:
        print("   CLI :", va)
        print("   CORE:", vc)
PY
```

Si alguna sale `DISTINTO`, **parar y reportarlo**: el inventario decía que eran
idénticas, y una diferencia cambia el alcance de este task.

- [ ] **Step 3: Reemplazar las definiciones por imports**

En `disk_analyzer.py` y `disk_analyzer_core.py`, sustituir el bloque de
constantes por:

```python
from analyzer.constants import (
    KB, MB, GB, SYSTEM, IS_WINDOWS, IS_MACOS, IS_LINUX,
    CACHE_DIRS, LARGE_FILE_EXTENSIONS, IGNORE_PATTERNS, MACOS_APFS_SKIP_DIRS,
    PROTECTED_PATH_PREFIXES, PROTECTED_APP_MARKERS, PROTECTED_FILENAMES,
    PROTECTED_ROOT_DIRS,
)
```

Importante: ese `from ... import` deja los nombres disponibles a nivel de módulo,
así que `from disk_analyzer_core import MB, GB, IS_MACOS, IS_WINDOWS` (lo que
hace el backend web) sigue funcionando. Confirmarlo, no asumirlo.

- [ ] **Step 4: Añadir la comprobación de que no hay dependencias externas**

Añadir a `tests/test_engine_characterization.py`:

```python
class TestPackaging:
    def test_analyzer_package_is_stdlib_only(self):
        """The CLI must keep working without any pip install."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c", "import analyzer.constants"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent)},
        )
        assert result.returncode == 0, result.stderr
```

- [ ] **Step 5: Verificar las tres interfaces y commitear**

```bash
venv-web/bin/python -m pytest tests/ -v
venv-web/bin/python -c "import disk_analyzer, disk_analyzer_core, disk_analyzer_web; print('imports OK')"
venv-web/bin/python disk_analyzer.py . --min-size 500 | head -20
```
Expected: la suite verde, los imports OK, y el CLI corriendo como antes.

```bash
git add analyzer/ disk_analyzer.py disk_analyzer_core.py tests/test_engine_characterization.py
git commit -m "refactor: extraer las constantes compartidas a analyzer/constants.py"
```

---

### Task 3: Extraer la protección de rutas a `analyzer/protection.py`

`is_protected_path` es idéntico en los dos módulos. Además, el backend web hoy
construye un `DiskAnalyzerCore` entero solo para llamarlo, lo cual es un rodeo
que este task elimina.

**Files:**
- Create: `analyzer/protection.py`
- Modify: `disk_analyzer.py`, `disk_analyzer_core.py`, `disk_analyzer_web.py`
- Test: `tests/test_engine_characterization.py` (los tests de protección ya existen; añadir el de la función libre)

**Interfaces:**
- Produces: `analyzer.protection.is_protected_path(file_path: str) -> bool`, función libre
- Los métodos `DiskAnalyzer.is_protected_path` y `DiskAnalyzerCore.is_protected_path` se conservan como delegación de una línea, para no romper a quien los llame

- [ ] **Step 1: Crear el módulo**

`analyzer/protection.py`: mover el cuerpo de `is_protected_path` (desde
`disk_analyzer_core.py:191`, que es la versión sin comentarios) como función
libre, importando las constantes de `analyzer.constants`. Copiar la lógica
verbatim; no "mejorarla" de paso.

- [ ] **Step 2: Delegar desde ambas clases**

En las dos clases:

```python
    def is_protected_path(self, file_path: str) -> bool:
        """Delegates to the shared implementation (kept for callers)."""
        return protection.is_protected_path(file_path)
```

- [ ] **Step 3: Usar la función libre en el backend web**

Buscar en `disk_analyzer_web.py` los sitios donde se instancia
`DiskAnalyzerCore` únicamente para llamar a `is_protected_path` (hay al menos
dos: el borrado de archivos y el bucle de borrado de cleanup) y sustituirlos por
la función libre. Cuidado: dejar intactas las instancias que sí se usan para
analizar.

- [ ] **Step 4: Test de la función libre**

Añadir a `tests/test_engine_characterization.py`:

```python
class TestProtectionModule:
    def test_free_function_matches_method(self):
        from analyzer.protection import is_protected_path
        core = DiskAnalyzerCore(".")
        for path in ["/System/Library/x", "/bin", str(Path.home() / "Downloads/a.mp4")]:
            assert is_protected_path(path) == core.is_protected_path(path)
```

- [ ] **Step 5: Verificar y commitear**

```bash
venv-web/bin/python -m pytest tests/ -v
git add analyzer/protection.py disk_analyzer.py disk_analyzer_core.py disk_analyzer_web.py tests/test_engine_characterization.py
git commit -m "refactor: extraer is_protected_path a analyzer/protection.py"
```

---

### Task 4: Unificar la clasificación de cachés

El único task de esta fase con cambio de comportamiento real. Hoy hay dos
clasificadores con etiquetas distintas, y tres consumidores que dependen de las
cadenas exactas. Se unifican en uno solo.

**Decisión de diseño (no relitigar):** se conserva el conjunto de etiquetas del
**core** (el más granular, 12 categorías), porque es el que ven la web y la GUI,
y porque las recomendaciones del core ya se alinearon a él en la Fase 1. El CLI
pasa a usarlo. Las etiquetas quedan como constantes con nombre, no como cadenas
sueltas repartidas por el código.

**Files:**
- Create: `analyzer/cache_types.py`
- Modify: `disk_analyzer.py` (`classify_cache`, el safelist de `clean_cache`, `generate_recommendations`), `disk_analyzer_core.py` (`categorize_cache`, `generate_recommendations`)
- Test: `tests/test_engine_characterization.py` (actualizar la clase de clasificación), `tests/test_cache_labels.py` (nuevo)

**Interfaces:**
- Produces: `analyzer/cache_types.py` con una constante por etiqueta (`DOCKER`, `XCODE`, `VSCODE`, `NPM`, `PYTHON`, `CHROME`, `FIREFOX`, `TRASH`, `TEMP`, `LOGS`, `DOWNLOADS`, `GENERAL`), el conjunto `SAFE_TO_CLEAN` que hoy codifica el safelist de `clean_cache`, y `classify(path: Path) -> str`
- Ambas clases delegan su clasificador en `cache_types.classify`

- [ ] **Step 1: Escribir el test que fija el contrato de los consumidores**

Crear `tests/test_cache_labels.py`:

```python
"""The cache labels are a contract between the classifier and three consumers.

Breaking it silently disables cleanup features — it already happened once
(phase 1, task 3), so it gets its own test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer import cache_types
from disk_analyzer_core import DiskAnalyzerCore, GB


def test_every_recommendation_filter_label_is_producible():
    """Any label the recommendation logic filters on must be a real label."""
    known = set(cache_types.ALL_LABELS)
    core = DiskAnalyzerCore(".")
    core.cache_locations = [
        {"path": f"/fake/{label}", "size": 5 * GB, "type": label}
        for label in known
    ]
    recs = core.generate_recommendations()
    # With every known label present at 5 GB, the known-cache recommendations
    # must fire — if a filter references a label that no longer exists, its
    # recommendation silently disappears.
    assert recs, "no recommendations fired for any known cache label"


def test_safe_to_clean_labels_are_real():
    assert cache_types.SAFE_TO_CLEAN, "safelist must not be empty"
    for label in cache_types.SAFE_TO_CLEAN:
        assert label in cache_types.ALL_LABELS, f"{label} is not a real label"


def test_downloads_and_general_are_never_auto_cleanable():
    """Deleting Downloads or an unclassified cache automatically is unsafe."""
    assert cache_types.DOWNLOADS not in cache_types.SAFE_TO_CLEAN
    assert cache_types.GENERAL not in cache_types.SAFE_TO_CLEAN
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `venv-web/bin/python -m pytest tests/test_cache_labels.py -v`
Expected: FAIL con `ModuleNotFoundError: analyzer.cache_types`.

- [ ] **Step 3: Crear el módulo de etiquetas**

`analyzer/cache_types.py`:

```python
"""Cache category labels and classification.

These label strings are a contract: the classifier produces them, and
generate_recommendations (CLI and core), clean_cache's safelist and the web
cleanup endpoint all match on them. Changing a string without updating every
consumer silently disables a cleanup feature.
"""
from pathlib import Path

DOCKER = 'Docker'
XCODE = 'Xcode Cache'
VSCODE = 'VS Code Cache'
NPM = 'NPM Cache'
PYTHON = 'Python Cache'
CHROME = 'Chrome Cache'
FIREFOX = 'Firefox Cache'
TRASH = 'Papelera'
TEMP = 'Archivos Temporales'
LOGS = 'Logs del Sistema'
DOWNLOADS = 'Downloads'
GENERAL = 'Cache General'

ALL_LABELS = (
    DOCKER, XCODE, VSCODE, NPM, PYTHON, CHROME, FIREFOX,
    TRASH, TEMP, LOGS, DOWNLOADS, GENERAL,
)

# Categories safe to delete without human review. Downloads holds user data and
# GENERAL is by definition unclassified, so neither is ever auto-cleanable.
SAFE_TO_CLEAN = frozenset({LOGS, VSCODE, NPM, XCODE, PYTHON, TEMP})


def classify(path: Path) -> str:
    """Classify a cache location by path. Order matters: first match wins."""
    ...
```

El cuerpo de `classify` se porta **verbatim** desde
`DiskAnalyzerCore.categorize_cache` (`disk_analyzer_core.py:403`), sustituyendo
cada cadena literal por su constante. No cambiar la precedencia de las ramas:
el orden es parte del comportamiento que fijan los tests de caracterización.

Nota sobre `SAFE_TO_CLEAN`: leer el safelist actual de `clean_cache` en
`disk_analyzer.py` (usa las etiquetas viejas del CLI: `'Logs del Sistema'`,
`'VS Code'`, `'Node.js/npm'`, `'Xcode Development'`, `'Python Cache'`) y
traducirlo a las etiquetas nuevas conservando **exactamente el mismo conjunto de
categorías**, ni una más. Si alguna categoría vieja no tiene equivalente exacto,
parar y reportarlo en vez de adivinar.

- [ ] **Step 4: Delegar desde ambas clases y actualizar los consumidores**

- `DiskAnalyzerCore.categorize_cache` → `return cache_types.classify(path)`
- `DiskAnalyzer.classify_cache` → `return cache_types.classify(path)`
- `clean_cache`: sustituir el safelist literal por `cache_types.SAFE_TO_CLEAN`
- `generate_recommendations` en **ambos** módulos: sustituir cada comparación de
  cadena por su constante

Buscar los consumidores con:
`grep -rn "VS Code\|Node.js/npm\|Xcode Development\|Cache General\|NPM Cache\|VS Code Cache" --include="*.py" .`
y no dejar ninguna cadena literal de etiqueta fuera del módulo nuevo.

- [ ] **Step 5: Actualizar el test de caracterización**

La clase `TestCacheClassification` del Task 1 fija la divergencia entre los dos
clasificadores. Este task la elimina a propósito, así que ese test **debe**
actualizarse: `test_cli_labels_differ_from_core` pasa a afirmar que ahora
coinciden. Renombrarlo a `test_cli_and_core_labels_now_match`. Es la única
actualización de un test de caracterización autorizada en esta fase, y es
deliberada.

- [ ] **Step 6: Verificar y commitear**

```bash
venv-web/bin/python -m pytest tests/ -v
venv-web/bin/python disk_analyzer.py . --min-size 500 --clean-cache --dry-run | head -30
```
Lo segundo debe listar categorías con las etiquetas nuevas y **no borrar nada**.

```bash
git add analyzer/cache_types.py disk_analyzer.py disk_analyzer_core.py tests/
git commit -m "refactor: una sola clasificación de cachés con etiquetas como constantes"
```

---

### Task 5: Reconciliar `get_directory_size` y el umbral de `find_cache_locations`

Dos divergencias que dan resultados distintos para la misma entrada.

**Decisiones de diseño (no relitigar):**
- `get_directory_size` se queda con la versión del **core** (`rglob` +
  `st_blocks`), porque es coherente con cómo el resto del motor mide el disco y
  no depende de un subproceso. El CLI cambia. Consecuencia esperada: puede
  reportar cifras ligeramente distintas a `du` en directorios con enlaces duros
  o archivos dispersos; es el mismo criterio que ya usa el escaneo principal.
- El umbral de `find_cache_locations` se queda en **`> MB`** (el del CLI): una
  caché de 3 KB no es accionable y solo ensucia la lista. El core cambia.

**Files:**
- Modify: `disk_analyzer.py` (`get_directory_size`), `disk_analyzer_core.py` (umbral en `find_cache_locations`)
- Test: `tests/test_engine_characterization.py`

- [ ] **Step 1: Escribir los tests**

```python
class TestDirectorySize:
    def test_matches_sum_of_block_sizes(self, tree):
        core = DiskAnalyzerCore(str(tree))
        from disk_analyzer import DiskAnalyzer
        cli = DiskAnalyzer(str(tree))
        # After reconciliation both implementations agree
        assert cli.get_directory_size(tree) == core.get_directory_size(tree)


class TestCacheThreshold:
    def test_tiny_caches_are_not_reported(self, tmp_path, monkeypatch):
        tiny = tmp_path / "tiny_cache"
        tiny.mkdir()
        (tiny / "a.txt").write_text("x")
        import analyzer.constants as consts
        monkeypatch.setattr(consts, "CACHE_DIRS", [str(tiny)], raising=False)
        core = DiskAnalyzerCore(str(tmp_path))
        core.find_cache_locations()
        assert all(loc["size"] > 1024 * 1024 for loc in core.cache_locations)
```

Nota: `find_cache_locations` lee `CACHE_DIRS` — verificar cómo lo referencia
(importado al espacio del módulo o vía `analyzer.constants`) y ajustar el
monkeypatch al nombre real; si resulta difícil de interceptar, construir el test
llamando directamente a la parte que aplica el umbral y decirlo en el reporte.

- [ ] **Step 2: RED, luego implementar, luego GREEN**

Reemplazar el cuerpo de `DiskAnalyzer.get_directory_size` por una delegación a
la implementación compartida (moverla a `analyzer/` si conviene, o llamar a la
del core), y cambiar `if size > 0:` por `if size > MB:` en
`find_cache_locations` del core.

- [ ] **Step 3: Verificar y commitear**

```bash
venv-web/bin/python -m pytest tests/ -v
git add disk_analyzer.py disk_analyzer_core.py tests/test_engine_characterization.py
git commit -m "refactor: una sola forma de medir directorios y un solo umbral de cachés"
```

---

### Task 6: Verificación integral de la fase

**Files:** ninguno nuevo.

- [ ] **Step 1: Suite completa**

Run: `venv-web/bin/python -m pytest tests/ -v` → verde.

- [ ] **Step 2: Las tres interfaces, a mano**

```bash
# CLI: análisis y reporte
venv-web/bin/python disk_analyzer.py . --min-size 100
venv-web/bin/python disk_analyzer.py . --min-size 100 --export /tmp/fase3check --html
# Backend web
venv-web/bin/python -c "import disk_analyzer_web; print('web OK')"
# GUI (puede faltar customtkinter; lo que importa es que no falle por el refactor)
venv-web/bin/python -c "import disk_analyzer_gui" 2>&1 | tail -1
```

- [ ] **Step 3: Confirmar que el CLI sigue sin dependencias externas**

```bash
/usr/bin/python3 -c "import sys; sys.path.insert(0,'.'); import analyzer.constants, analyzer.protection, analyzer.cache_types; print('stdlib only OK')"
```

- [ ] **Step 4: Medir lo que se eliminó**

```bash
wc -l disk_analyzer.py disk_analyzer_core.py analyzer/*.py
```
Anotar el resultado en el registro de ejecución: la métrica de esta fase es
cuánta duplicación desapareció.

- [ ] **Step 5: Commit de verificación**

```bash
git add -A && git commit -m "test: verificación integral fase 3" --allow-empty
```

---

## Fuera del alcance de esta fase

Se dejan deliberadamente para después, porque cada una es un proyecto en sí:

- **Mover `generate_html_report` y los Sankey** (~2.300 líneas) a un módulo de
  reporte. Es la única razón por la que el backend web importa el monolito.
- **Unificar `scan_directory`.** Las dos versiones comparten el conteo pero
  difieren en el andamiaje (progreso por TTY con ETA en el CLI; callback,
  cancelación y `max_depth` en el core). Unificarlas requiere diseñar una
  interfaz de progreso común, y este plan ya toca bastante superficie.
- **`get_all_drives`** (`List[str]` vs `List[Dict]`): cambiar la forma del CLI
  afecta a `--all-drives` en Windows, que no se puede probar aquí.

## Self-Review (ejecutado al escribir el plan)

1. **Cobertura:** el objetivo era eliminar duplicación. Se cubren constantes,
   protección, clasificación de cachés y las dos divergencias de medición. Lo que
   queda fuera está declarado arriba con su motivo, no omitido en silencio.
2. **Placeholders:** los pasos de movimiento mecánico dicen "portar verbatim" a
   propósito — copiar líneas existentes es la acción, y transcribirlas aquí
   invitaría a divergencias. Los tests sí llevan código completo.
3. **Consistencia de tipos:** `is_protected_path(str) -> bool` igual que hoy;
   `classify(Path) -> str` con el mismo dominio de salida que
   `categorize_cache`; `SAFE_TO_CLEAN` es un `frozenset` de etiquetas que
   `ALL_LABELS` contiene, comprobado por test.
4. **Riesgo principal:** el Task 4 toca cadenas de las que depende
   funcionalidad. Por eso lleva su propio archivo de tests de contrato y una
   verificación manual en seco del CLI.
