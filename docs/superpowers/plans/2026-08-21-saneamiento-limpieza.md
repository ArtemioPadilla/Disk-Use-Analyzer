# Saneamiento de la limpieza — Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDO: usa `superpowers:subagent-driven-development`
> (recomendado) o `superpowers:executing-plans` para ejecutar este plan task por
> task. Los pasos usan casillas (`- [ ]`) para seguimiento.

**Objetivo:** dejar la limpieza en un estado en el que se pueda construir encima
— sin inyección de shell, sin comandos que mienten, con una sola definición de
los niveles de riesgo y sin secuestrar el puerto 8000.

**Arquitectura:** los comandos de borrado dejan de construirse a mano en cada
sitio y pasan por un único constructor con escapado; el ahorro se mide del disco
en vez de deducirse del código de salida; las dos copias de
`generate_recommendations` se fusionan en una, con un `id` estable por
recomendación; y la app de bandeja pide un puerto libre al sistema en lugar de
asumir el 8000.

**Stack:** Python 3.13 (solo biblioteca estándar en el motor), pytest, React +
Vitest en el frontend, Rust + Tauri 2 en la app de bandeja.

**Origen:** este plan no nace de un spec sino de cinco revisiones adversariales
sobre la propuesta de añadir acciones de limpieza al menú de la bandeja. Los
hallazgos están reproducidos abajo. El spec de la app de bandeja sigue siendo
[`docs/superpowers/specs/2026-08-19-app-bandeja-tauri-design.md`](../specs/2026-08-19-app-bandeja-tauri-design.md).

## Restricciones globales

- El motor (`disk_analyzer.py`, `disk_analyzer_core.py`, `analyzer/`) usa **solo
  biblioteca estándar**. `shlex` lo es; no añadir dependencias.
- Mensajes de cara al usuario en **español**; comentarios de código en inglés.
- **Desarrollo guiado por tests:** el test falla primero, luego el arreglo.
- La suite existente —153 backend, 72 frontend, 17 Rust— debe quedar en verde.
- **Un commit por task**, mensaje en español.
- No cambiar las formas del API que consume `web/src/lib/api.ts`, salvo para
  **añadir** campos opcionales.
- La app de bandeja ejecuta `disk_analyzer.py` (no el core): ver
  `desktop/src-tauri/src/analisis.rs`. Cualquier arreglo que solo toque el core
  no llega a la bandeja.

---

## Hallazgos verificados que originan este plan

Los cinco están **reproducidos**, no supuestos.

**H1 — Inyección de shell por el nombre de una carpeta (crítico).**
`disk_analyzer_core.py:571,585` y `disk_analyzer.py:758,881,904,929` construyen
`f"rm -rf '{path}/*'"` sin escapar. Una carpeta llamada
`x' ; rm -rf victim ; touch pwned '` genera tres comandos encadenados.
Reproducido: borró una carpeta ajena y ejecutó código arbitrario. La ruta la
aporta el escaneo del disco. Bajo `sudo make web`, corre como root.

El escapado correcto **ya existe** en `disk_analyzer.py:662`
(`file_path.replace("'", "'\"'\"'")`); el generador de recomendaciones no lo
llama.

**H2 — Los comandos de logs y VS Code no borran nada y salen con éxito.**
El `*` va **dentro** de las comillas simples, así que el shell no lo expande.
Reproducido: `rm -rf 'dir/*'` → código 0, el fichero sigue ahí. Y
`web/src/hooks/useCleanupRunner.ts:168-172` acredita el ahorro al ver código 0.
Resultado: la interfaz dice "liberados 85 MB" habiendo borrado cero bytes.

Nota: `disk_analyzer.py:881` pone el glob **fuera** de las comillas y sí
funciona. El bug es incoherencia entre sitios.

**H3 — Un `tier` desconocido se trata como Seguro.**
`web/src/components/CleanupWizard.tsx:37,40,46,50` hace `r.tier || 1`. Una
recomendación con `tier` ausente, `null` o `0` entra en el botón de ejecución
por lotes del nivel 1. Lo desconocido debe caer en lo más restrictivo.

**H4 — `is_protected_path` no protege datos de usuario.**
Verificado: devuelve `False` (borrable) para `~/Documents`, `~/Desktop`,
`~/Library/Mobile Documents` (iCloud), `/Volumes/Backup Time Machine` y el
propio `$HOME`. Es una lista negra del sistema operativo, no una whitelist de lo
que se puede borrar. Además los prefijos llevan barra final
(`analyzer/constants.py:99-111`), así que `/System/Library` (el directorio en sí)
tampoco está protegido, solo su contenido.

**H5 — La bandeja abre lo que sea que haya en el puerto 8000.**
`desktop/src-tauri/src/servidor.rs` comprueba solo que *algo* acepte TCP en
127.0.0.1:8000 y, si lo hay, abre esa URL como si fuera el analizador. Con un
Django o un Rails en el 8000, "Abrir analizador completo" abre esa aplicación.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `analyzer/comandos.py` *(nuevo)* | Único constructor de comandos de borrado. Escapa rutas, coloca el glob fuera de las comillas y clasifica el efecto de cada comando. |
| `analyzer/protection.py` | Añade `puede_borrarse()`: whitelist real, además de la lista negra existente. |
| `analyzer/constants.py` | Añade `RUTAS_DE_DATOS_DE_USUARIO`. |
| `disk_analyzer_core.py` | Única `generate_recommendations`, con `id` estable y campo `efecto`. Reglas nuevas. |
| `disk_analyzer.py` | Su `generate_recommendations` pasa a delegar en el core. |
| `web/src/lib/api.ts` | Tipo `Recommendation` con `id` y `efecto` opcionales. |
| `web/src/hooks/useCleanupRunner.ts` | Acredita el ahorro medido del disco, no el estimado. |
| `web/src/components/CleanupWizard.tsx` | Lo desconocido deja de ser Seguro. |
| `desktop/src-tauri/src/servidor.rs` | Puerto efímero y reutilización solo de instancias propias. |

---

## Fase 1 — Seguridad

### Task 1: Un único constructor de comandos de borrado

**Archivos:**
- Crear: `analyzer/comandos.py`
- Crear: `tests/test_comandos.py`
- Modificar: `disk_analyzer_core.py:571,585`, `disk_analyzer.py:758,881,904,929`

**Interfaces:**
- Consume: nada.
- Produce: `borrar_contenido(paths: List[str]) -> str`,
  `borrar_rutas(paths: List[str]) -> str`, `escapar(path: str) -> str`.

- [ ] **Paso 1: Escribe los tests que fallan**

```python
# tests/test_comandos.py
"""El constructor de comandos de borrado.

Los dos fallos que estos tests fijan estaban en producción y se reprodujeron:
una carpeta con un apóstrofe en el nombre ejecutaba comandos arbitrarios, y el
glob entrecomillado hacía que el borrado no borrara nada y saliera con éxito.
"""
import os
import subprocess
import tempfile

from analyzer.comandos import borrar_contenido, borrar_rutas, escapar


def _ejecutar(cmd: str, cwd: str) -> int:
    return subprocess.run(["/bin/sh", "-c", cmd], cwd=cwd,
                          capture_output=True).returncode


def test_una_ruta_maliciosa_no_ejecuta_comandos_extra():
    """El nombre de una carpeta no puede ser código.

    Reproducido en producción: `x' ; rm -rf victim ; touch pwned '` con la
    plantilla vieja generaba tres comandos y borraba una carpeta ajena.
    """
    with tempfile.TemporaryDirectory() as box:
        os.makedirs(os.path.join(box, "victima"))
        malicioso = os.path.join(box, "x' ; rm -rf victima ; touch pwned '")
        os.makedirs(malicioso)

        _ejecutar(borrar_contenido([malicioso]), cwd=box)

        assert os.path.isdir(os.path.join(box, "victima")), (
            "el nombre de otra carpeta consiguió borrar la víctima"
        )
        assert not os.path.exists(os.path.join(box, "pwned")), (
            "se ejecutó un comando arbitrario embebido en el nombre"
        )


def test_borrar_contenido_borra_de_verdad():
    """El glob tiene que quedar FUERA de las comillas o no expande.

    Con `rm -rf 'dir/*'` el shell trata el asterisco como literal, `rm -f` sale
    0 y no borra nada. La interfaz acreditaba el ahorro por ese 0.
    """
    with tempfile.TemporaryDirectory() as box:
        objetivo = os.path.join(box, "cache")
        os.makedirs(objetivo)
        open(os.path.join(objetivo, "a.log"), "w").write("x")
        open(os.path.join(objetivo, "b.log"), "w").write("x")

        _ejecutar(borrar_contenido([objetivo]), cwd=box)

        assert os.listdir(objetivo) == [], "el contenido sobrevivió al borrado"
        assert os.path.isdir(objetivo), "borró el directorio, no su contenido"


def test_borrar_rutas_borra_el_directorio_entero():
    with tempfile.TemporaryDirectory() as box:
        objetivo = os.path.join(box, "basura")
        os.makedirs(objetivo)
        _ejecutar(borrar_rutas([objetivo]), cwd=box)
        assert not os.path.exists(objetivo)


def test_escapar_neutraliza_metacaracteres():
    for peligro in ["a'b", "a b", "a;b", "a&&b", "a$(id)b", "a`id`b", "a\nb"]:
        assert escapar(peligro) != peligro or "'" not in peligro


def test_una_ruta_vacia_no_produce_comando():
    """Una ruta vacía convertiría `rm -rf ''/*` en algo impredecible."""
    assert borrar_contenido([]) == ""
    assert borrar_contenido([""]) == ""
    assert borrar_rutas(["   "]) == ""


def test_la_raiz_nunca_genera_comando():
    """Salvaguarda de último recurso: nada construye un borrado de `/`."""
    assert borrar_contenido(["/"]) == ""
    assert borrar_rutas(["/"]) == ""
```

- [ ] **Paso 2: Ejecútalos para verificar que fallan**

```bash
venv-web/bin/python -m pytest tests/test_comandos.py -v
```
Esperado: FAIL con `ModuleNotFoundError: No module named 'analyzer.comandos'`.

- [ ] **Paso 3: Escribe el módulo**

```python
# analyzer/comandos.py
"""Único sitio donde se construyen comandos de borrado.

Antes cada sitio armaba su propia f-string. Eso produjo dos fallos que llegaron
a producción y se reprodujeron:

- Una carpeta llamada `x' ; rm -rf victim ; touch pwned '` cerraba las comillas
  de la plantilla y ejecutaba comandos arbitrarios. La ruta la aporta el escaneo
  del disco, así que basta con descomprimir un zip con un nombre hostil.
- El glob iba DENTRO de las comillas (`rm -rf 'dir/*'`), así que el shell no lo
  expandía: `rm -f` salía 0 sin borrar nada, y la interfaz acreditaba el ahorro
  al ver ese 0.

`shlex.quote` es biblioteca estándar, así que esto no rompe la promesa de que el
motor no tiene dependencias.
"""
import shlex
from typing import List

# Rutas que jamás pueden ser el objetivo de un comando generado, por muy
# protegida que esté la lógica que llama aquí. Es la última red, no la primera.
_PROHIBIDAS = {"/", "//", "/.", ""}


def escapar(path: str) -> str:
    """Deja una ruta lista para incrustarse en una línea de shell."""
    return shlex.quote(path)


def _utiles(paths: List[str]) -> List[str]:
    limpias = []
    for p in paths:
        p = (p or "").rstrip("/") if (p or "").rstrip("/") else (p or "")
        if p.strip() in _PROHIBIDAS or not p.strip():
            continue
        limpias.append(p)
    return limpias


def borrar_contenido(paths: List[str]) -> str:
    """Borra lo que hay DENTRO de cada ruta, dejando el directorio en pie.

    El glob va fuera de las comillas a propósito: dentro, el shell lo trata como
    un nombre de fichero literal y el comando no borra nada.
    """
    limpias = _utiles(paths)
    if not limpias:
        return ""
    return " && ".join(f"rm -rf {escapar(p)}/*" for p in limpias)


def borrar_rutas(paths: List[str]) -> str:
    """Borra cada ruta entera, el directorio incluido."""
    limpias = _utiles(paths)
    if not limpias:
        return ""
    return " && ".join(f"rm -rf {escapar(p)}" for p in limpias)
```

- [ ] **Paso 4: Verifica que pasan**

```bash
venv-web/bin/python -m pytest tests/test_comandos.py -v
```
Esperado: 6 passed.

- [ ] **Paso 5: Reemplaza los seis sitios vulnerables**

En `disk_analyzer_core.py`, añade `from analyzer import comandos` junto a los
otros imports de `analyzer`, y sustituye:

```python
# línea ~571 y ~585 — antes:
'command': ' && '.join(f"rm -rf '{l['path']}/*'" for l in log_locs)
# después:
'command': comandos.borrar_contenido([l['path'] for l in log_locs])
```

En `disk_analyzer.py`, mismo import, y sustituye:

```python
# línea ~758 — antes:
'command': f"rm -rf '{dir_path}'",
# después:
'command': comandos.borrar_rutas([dir_path]),

# línea ~881 — antes:
'command': f"rm -rf '{xcode_archives_path}'/*",
# después:
'command': comandos.borrar_contenido([xcode_archives_path]),

# líneas ~904 y ~929 — antes:
'command': ' && '.join(f"rm -rf '{l['path']}/*'" for l in log_locs)
# después:
'command': comandos.borrar_contenido([l['path'] for l in log_locs])
```

Verifica antes de sustituir el nombre real de la variable en cada sitio: la de
la línea 929 es de VS Code, no de logs.

- [ ] **Paso 6: Verifica que no queda ninguna plantilla a mano**

```bash
grep -n "rm -rf '" disk_analyzer.py disk_analyzer_core.py
```
Esperado: solo `disk_analyzer.py:663` (el borrado de fichero suelto, que ya
escapa) y las cadenas dentro del HTML generado.

- [ ] **Paso 7: La suite completa sigue verde**

```bash
venv-web/bin/python -m pytest tests/ -q
```
Esperado: 153 passed + los 6 nuevos.

- [ ] **Paso 8: Commit**

```bash
git add analyzer/comandos.py tests/test_comandos.py disk_analyzer.py disk_analyzer_core.py
git commit -m "fix: el nombre de una carpeta ya no puede ejecutar comandos"
```

---

### Task 2: Whitelist real para lo que se puede borrar

**Archivos:**
- Modificar: `analyzer/constants.py`, `analyzer/protection.py`
- Crear: `tests/test_puede_borrarse.py`

**Interfaces:**
- Consume: `is_protected_path(path) -> bool` (existente).
- Produce: `puede_borrarse(path: str) -> bool`.

- [ ] **Paso 1: Escribe los tests que fallan**

```python
# tests/test_puede_borrarse.py
"""Qué se puede borrar de verdad.

`is_protected_path` es una lista negra del sistema operativo: sirve para "no
toques macOS", no para "esto es seguro de borrar". Verificado: devuelve False
(borrable) para ~/Documents, ~/Desktop, iCloud Drive, /Volumes/... y el propio
$HOME. Con "añadir carpetas propias" eso apuntaría a los datos del usuario.
"""
import os

import pytest

from analyzer.protection import puede_borrarse

CASA = os.path.expanduser("~")


@pytest.mark.parametrize("ruta", [
    CASA,
    os.path.join(CASA, "Documents"),
    os.path.join(CASA, "Desktop"),
    os.path.join(CASA, "Pictures"),
    os.path.join(CASA, "Library/Mobile Documents"),          # iCloud Drive
    os.path.join(CASA, "Library/Mobile Documents/algo/mio"),  # y su contenido
    "/Volumes/Backup Time Machine",
    "/Volumes/Backup Time Machine/2026",
    "/System/Library",     # el directorio en sí, no solo su contenido
    "/System",
    "/",
])
def test_los_datos_del_usuario_y_el_sistema_no_se_borran(ruta):
    assert not puede_borrarse(ruta), f"{ruta} salió como borrable"


@pytest.mark.parametrize("ruta", [
    os.path.join(CASA, "Library/Caches/com.apple.Safari"),
    os.path.join(CASA, ".npm/_cacache"),
    os.path.join(CASA, "Library/Logs/algo.log"),
])
def test_las_caches_conocidas_si_se_borran(ruta):
    assert puede_borrarse(ruta), f"{ruta} debería poder limpiarse"


def test_una_ruta_relativa_o_vacia_nunca_se_borra():
    assert not puede_borrarse("")
    assert not puede_borrarse("relativa/sin/raiz")


def test_no_se_puede_escapar_con_puntos():
    """`~/Library/Caches/../../Documents` es ~/Documents disfrazado."""
    assert not puede_borrarse(os.path.join(CASA, "Library/Caches/../../Documents"))
```

- [ ] **Paso 2: Ejecútalos para verificar que fallan**

```bash
venv-web/bin/python -m pytest tests/test_puede_borrarse.py -v
```
Esperado: FAIL con `ImportError: cannot import name 'puede_borrarse'`.

- [ ] **Paso 3: Añade las rutas de datos de usuario**

En `analyzer/constants.py`, después del bloque `PROTECTED_PATH_PREFIXES`:

```python
# Rutas cuyo borrado destruye datos del usuario. `PROTECTED_PATH_PREFIXES` es
# una lista negra del sistema operativo y no cubre nada de esto: verificado que
# ~/Documents, iCloud Drive y /Volumes/... salían como borrables.
#
# Se guardan relativas a $HOME (o absolutas cuando no dependen del usuario) y se
# expanden al comprobar, para que los tests no dependan de quién ejecuta.
RUTAS_DE_DATOS_DE_USUARIO = [
    '~',
    '~/Documents',
    '~/Desktop',
    '~/Pictures',
    '~/Movies',
    '~/Music',
    '~/Library/Mobile Documents',   # iCloud Drive
    '~/Library/Messages',
    '~/Library/Mail',
    '~/Library/Photos',
    '~/Library/Keychains',
    '~/Library/Application Support/MobileSync',  # backups de iPhone
    '/Volumes',                     # discos externos y Time Machine
    '/Users',
    '/System',
    '/Library',
    '/private',
    '/usr',
    '/etc',
    '/var',
    '/opt',
    '/Applications',
]
```

- [ ] **Paso 4: Implementa `puede_borrarse`**

En `analyzer/protection.py`:

```python
import os

from analyzer.constants import (
    PROTECTED_PATH_PREFIXES, PROTECTED_APP_MARKERS, PROTECTED_FILENAMES,
    PROTECTED_ROOT_DIRS, RUTAS_DE_DATOS_DE_USUARIO,
)


def puede_borrarse(file_path: str) -> bool:
    """Si una ruta puede ser objetivo de un borrado automático.

    Distinta de `is_protected_path`, que solo dice "esto es del sistema
    operativo". Aquí la pregunta es la contraria y más estricta: ¿es seguro que
    una herramienta borre esto sin que un humano lo mire? Ante la duda, no.

    Se normaliza antes de comparar porque
    `~/Library/Caches/../../Documents` es `~/Documents` disfrazado.
    """
    if not file_path or not file_path.strip():
        return False

    ruta = os.path.normpath(os.path.abspath(os.path.expanduser(file_path)))
    if not ruta.startswith('/') or ruta == '/':
        return False

    if is_protected_path(ruta):
        return False

    for cruda in RUTAS_DE_DATOS_DE_USUARIO:
        prohibida = os.path.normpath(os.path.expanduser(cruda))
        # La ruta prohibida en sí, y todo lo que cuelga de ella salvo que una
        # regla más específica lo permita (ver abajo).
        if ruta == prohibida:
            return False

    # Dentro de una zona prohibida solo se salvan las cachés conocidas: eso es
    # lo que convierte esto en whitelist y no en otra lista negra.
    permitidas = [
        os.path.expanduser('~/Library/Caches'),
        os.path.expanduser('~/Library/Logs'),
        os.path.expanduser('~/.cache'),
        os.path.expanduser('~/.npm'),
        os.path.expanduser('~/Library/Developer/Xcode/DerivedData'),
        os.path.expanduser('~/Library/Application Support/Code/Cache'),
        os.path.expanduser('~/Library/Application Support/Code/CachedData'),
        os.path.expanduser('~/Library/Containers/com.docker.docker/Data'),
        '/private/var/folders',
    ]
    if any(ruta == p or ruta.startswith(p + '/') for p in permitidas):
        return True

    for cruda in RUTAS_DE_DATOS_DE_USUARIO:
        prohibida = os.path.normpath(os.path.expanduser(cruda))
        if ruta.startswith(prohibida + '/'):
            return False

    return True
```

- [ ] **Paso 5: Arregla los prefijos sin barra final**

En `analyzer/protection.py`, dentro de `is_protected_path`, el chequeo de
prefijos solo cubre el contenido porque los prefijos llevan barra final. Cambia:

```python
    if any(file_path.startswith(prefix) for prefix in PROTECTED_PATH_PREFIXES):
        return True
```

por:

```python
    # `startswith('/System/Library/')` no cubre '/System/Library' a secas, así
    # que el directorio en sí quedaba desprotegido y solo lo estaba su contenido.
    for prefix in PROTECTED_PATH_PREFIXES:
        if file_path.startswith(prefix) or file_path == prefix.rstrip('/'):
            return True
```

- [ ] **Paso 6: Verifica que pasan y que no rompiste nada**

```bash
venv-web/bin/python -m pytest tests/test_puede_borrarse.py -v
venv-web/bin/python -m pytest tests/ -q
```
Esperado: los nuevos en verde, los 153 anteriores intactos.

- [ ] **Paso 7: Commit**

```bash
git add analyzer/constants.py analyzer/protection.py tests/test_puede_borrarse.py
git commit -m "fix: whitelist real de lo que se puede borrar"
```

---

### Task 3: Lo desconocido deja de ser Seguro

**Archivos:**
- Modificar: `web/src/components/CleanupWizard.tsx:37,40,46,50`
- Crear: `web/src/components/CleanupWizard.tiers.test.tsx`

- [ ] **Paso 1: Escribe el test que falla**

```tsx
// web/src/components/CleanupWizard.tsx usa `r.tier || 1`, así que una
// recomendación sin nivel cae en el grupo Seguro y entra en el botón que
// ejecuta todo el nivel 1 de una vez. El default ante lo desconocido tiene que
// ser el más restrictivo, no el más permisivo.
import { describe, it, expect } from 'vitest';
import { nivelDe } from './CleanupWizard';

describe('nivelDe', () => {
  it('respeta el nivel cuando viene', () => {
    expect(nivelDe({ tier: 1 })).toBe(1);
    expect(nivelDe({ tier: 3 })).toBe(3);
  });

  it('trata lo desconocido como lo más restrictivo, no como Seguro', () => {
    for (const rec of [{}, { tier: undefined }, { tier: null }, { tier: 0 },
                       { tier: NaN }, { tier: 'dos' }, { tier: 9 }]) {
      expect(nivelDe(rec as any)).toBe(4);
    }
  });
});
```

- [ ] **Paso 2: Ejecútalo para verificar que falla**

```bash
cd web && npm test -- --run src/components/CleanupWizard.tiers.test.tsx
```
Esperado: FAIL, `nivelDe` no está exportado.

- [ ] **Paso 3: Implementa y sustituye los cuatro usos**

En `web/src/components/CleanupWizard.tsx`, arriba del componente:

```tsx
/**
 * El nivel de riesgo de una recomendación, o el más restrictivo si no se
 * puede saber.
 *
 * El código anterior hacía `r.tier || 1`, que convertía `undefined`, `null` y
 * `0` en Seguro — y Seguro es justo lo que el botón de "ejecutar todo" lanza
 * sin revisión. Ante una recomendación malformada, lo correcto es lo contrario.
 */
export function nivelDe(rec: { tier?: unknown }): number {
  const n = Number(rec?.tier);
  return Number.isInteger(n) && n >= 1 && n <= 4 ? n : 4;
}
```

Y reemplaza las cuatro apariciones de `(r.tier || 1)` / `rec.tier || 1` por
`nivelDe(r)` / `nivelDe(rec)`.

- [ ] **Paso 4: Verifica**

```bash
cd web && npm test -- --run && npm run check
```
Esperado: todo verde, 0 errores de tipos.

- [ ] **Paso 5: Commit**

```bash
git add web/src/components/CleanupWizard.tsx web/src/components/CleanupWizard.tiers.test.tsx
git commit -m "fix(web): una recomendación sin nivel ya no cuenta como segura"
```

---

## Fase 2 — Honestidad sobre lo que pasa

### Task 4: Etiquetar el efecto real de cada comando

**Archivos:**
- Modificar: `disk_analyzer_core.py` (todas las recomendaciones)
- Modificar: `web/src/lib/api.ts` (tipo `Recommendation`)
- Crear: `tests/test_efecto_recomendaciones.py`

**Interfaces:**
- Produce: cada recomendación gana `'efecto'`, uno de
  `'borra'` | `'irreversible'` | `'solo_lista'`.

- [ ] **Paso 1: Escribe el test que falla**

```python
# tests/test_efecto_recomendaciones.py
"""Cada recomendación tiene que declarar qué hace su comando.

Hoy se mezclan tres cosas distintas bajo el mismo botón:
- borrados de ficheros, que podrían ir a la papelera;
- invocaciones a herramientas (`docker system prune`, `brew cleanup`), que
  borran por su cuenta y NO tienen papelera posible;
- diagnósticos (`du -sh`, `find -ls`), que no borran nada.

Sin este campo, la interfaz no puede prometer reversibilidad honestamente ni
distinguir "liberó espacio" de "te enseñó una lista".
"""
import sys

sys.path.insert(0, '.')
from disk_analyzer_core import DiskAnalyzerCore

EFECTOS = {'borra', 'irreversible', 'solo_lista'}


def _recomendaciones():
    core = DiskAnalyzerCore('.')
    core.find_cache_locations()
    return core.generate_recommendations()


def test_toda_recomendacion_declara_su_efecto():
    for r in _recomendaciones():
        assert r.get('efecto') in EFECTOS, (
            f"{r.get('type')} no declara efecto válido: {r.get('efecto')!r}"
        )


def test_los_comandos_que_solo_listan_estan_marcados():
    """`du -sh` y `find -ls` no borran; acreditarles ahorro es mentir."""
    for r in _recomendaciones():
        cmd = r.get('command', '')
        if cmd.startswith('du ') or ' -ls' in cmd:
            assert r['efecto'] == 'solo_lista', (
                f"{r['type']} ejecuta un diagnóstico pero no está marcado"
            )


def test_las_herramientas_externas_son_irreversibles():
    """Nada de esto se puede mandar a la papelera."""
    for r in _recomendaciones():
        cmd = r.get('command', '')
        if any(t in cmd for t in ('docker system prune', 'brew cleanup',
                                  'npm cache clean', 'simctl delete')):
            assert r['efecto'] == 'irreversible', (
                f"{r['type']} invoca una herramienta externa: no hay papelera"
            )
```

- [ ] **Paso 2: Ejecútalo para verificar que falla**

```bash
venv-web/bin/python -m pytest tests/test_efecto_recomendaciones.py -v
```
Esperado: FAIL, ninguna recomendación declara `efecto`.

- [ ] **Paso 3: Añade el campo en cada recomendación**

En `disk_analyzer_core.py`, dentro de `generate_recommendations`, añade
`'efecto'` a cada `recommendations.append({...})`:

- logs, VS Code, Homebrew (`brew cleanup`), npm (`npm cache clean`):
  `'efecto': 'irreversible'` para las que invocan herramientas,
  `'efecto': 'borra'` para las que son `rm -rf` de rutas.
- simuladores (`xcrun simctl delete unavailable`): `'irreversible'`.
- Docker (`docker system prune -a -f`): `'irreversible'`.
- Descargas antiguas (`find ~/Downloads ... -ls`): `'solo_lista'`.
- Cache general `~/.cache` (`du -sh ...`): `'solo_lista'`.
- Archivos gigantes: según su comando; si lista, `'solo_lista'`.

Comprueba el comando real de cada bloque antes de etiquetarlo — no supongas por
el nombre.

- [ ] **Paso 4: Añade el campo al tipo del frontend**

En `web/src/lib/api.ts`, en la interfaz de recomendación:

```ts
  /** Qué hace realmente el comando. Opcional: los informes viejos no lo traen. */
  efecto?: 'borra' | 'irreversible' | 'solo_lista';
  /** Identificador estable, ver Task 6. Opcional por la misma razón. */
  id?: string;
```

- [ ] **Paso 5: Verifica**

```bash
venv-web/bin/python -m pytest tests/ -q
cd web && npm run check
```

- [ ] **Paso 6: Commit**

```bash
git add disk_analyzer_core.py web/src/lib/api.ts tests/test_efecto_recomendaciones.py
git commit -m "feat: cada recomendación declara si borra, es irreversible o solo lista"
```

---

### Task 5: El ahorro se mide del disco, no del código de salida

**Archivos:**
- Modificar: `web/src/hooks/useCleanupRunner.ts:168-172`
- Modificar: `web/src/hooks/useCleanupRunner.test.ts`

**Interfaces:**
- Consume: `api.getSystemInfo()` (existente, trae `disk_usage.free`).
- Produce: `cleanup:completed` pasa a emitir `{ command, space, estimado }`,
  donde `space` es el delta medido y `estimado` el que traía la recomendación.

- [ ] **Paso 1: Escribe los tests que fallan**

```ts
// Añadir a web/src/hooks/useCleanupRunner.test.ts
//
// Acreditar el ahorro por el código de salida es lo que hacía que un comando
// no-op reportara "85 MB liberados". `rm -f` devuelve 0 tanto si borró todo
// como si no borró nada, así que el exit code no prueba absolutamente nada
// sobre el espacio.

it('acredita el espacio realmente liberado, no el estimado', async () => {
  // libre antes: 10 GB; después: 12 GB  →  se liberaron 2 GB
  vi.mocked(api.getSystemInfo)
    .mockResolvedValueOnce({ disk_usage: { free: 10e9 } } as any)
    .mockResolvedValueOnce({ disk_usage: { free: 12e9 } } as any);

  const visto = vi.fn();
  on('cleanup:completed', visto);
  await ejecutarYCompletar({ command: 'rm -rf x', space: 99e9 }, 0);

  expect(visto).toHaveBeenCalledWith(
    expect.objectContaining({ space: 2e9, estimado: 99e9 }),
  );
});

it('un comando que no libera nada acredita cero, no su estimación', async () => {
  vi.mocked(api.getSystemInfo)
    .mockResolvedValueOnce({ disk_usage: { free: 10e9 } } as any)
    .mockResolvedValueOnce({ disk_usage: { free: 10e9 } } as any);

  const visto = vi.fn();
  on('cleanup:completed', visto);
  await ejecutarYCompletar({ command: "rm -rf 'x/*'", space: 85e6 }, 0);

  expect(visto).toHaveBeenCalledWith(expect.objectContaining({ space: 0 }));
});

it('nunca acredita un ahorro negativo', async () => {
  // Otro proceso escribió mientras corría la limpieza.
  vi.mocked(api.getSystemInfo)
    .mockResolvedValueOnce({ disk_usage: { free: 12e9 } } as any)
    .mockResolvedValueOnce({ disk_usage: { free: 10e9 } } as any);

  const visto = vi.fn();
  on('cleanup:completed', visto);
  await ejecutarYCompletar({ command: 'rm -rf x', space: 1e9 }, 0);

  expect(visto).toHaveBeenCalledWith(expect.objectContaining({ space: 0 }));
});
```

Adapta `ejecutarYCompletar` al helper que ya use ese fichero de tests para
encolar un trabajo y disparar `terminal:exited` con un código.

- [ ] **Paso 2: Ejecútalos para verificar que fallan**

```bash
cd web && npm test -- --run src/hooks/useCleanupRunner.test.ts
```
Esperado: FAIL, se acredita `job.space`.

- [ ] **Paso 3: Mide antes y después**

En `useCleanupRunner.ts`, guarda el espacio libre al encolar el trabajo y
compáralo al terminar:

```ts
// Antes de lanzar el comando (donde hoy se llama a api.createTerminal):
const libreAntes = await api.getSystemInfo()
  .then(i => i.disk_usage?.free ?? null)
  .catch(() => null);

// En finishActiveJob, dentro de la rama `code === 0`:
// El código de salida no dice nada sobre el espacio: `rm -f` devuelve 0
// tanto si borró todo como si no borró nada. Se mide el disco.
let liberado = job.space;
if (libreAntes != null) {
  const libreDespues = await api.getSystemInfo()
    .then(i => i.disk_usage?.free ?? null)
    .catch(() => null);
  if (libreDespues != null) {
    liberado = Math.max(0, libreDespues - libreAntes);
  }
}
emit('cleanup:completed', { command: job.command, space: liberado,
                            estimado: job.space });
```

Guarda `libreAntes` en el objeto del trabajo, junto a `command` y `space`.

- [ ] **Paso 4: Verifica**

```bash
cd web && npm test -- --run && npm run check
```

- [ ] **Paso 5: Commit**

```bash
git add web/src/hooks/useCleanupRunner.ts web/src/hooks/useCleanupRunner.test.ts
git commit -m "fix(web): acreditar el espacio medido del disco, no el estimado"
```

---

## Fase 3 — Un solo motor

### Task 6: Fusionar las dos `generate_recommendations` con `id` estable

**Archivos:**
- Modificar: `disk_analyzer_core.py:561` (única implementación, con `id`)
- Modificar: `disk_analyzer.py:888` (pasa a delegar)
- Crear: `tests/test_motor_unico.py`

**Interfaces:**
- Consume: `comandos.borrar_contenido/borrar_rutas` (Task 1),
  `'efecto'` (Task 4).
- Produce: cada recomendación gana `'id'`, un slug estable
  (`'logs'`, `'homebrew'`, `'vscode'`, `'npm'`, `'simuladores'`,
  `'descargas_antiguas'`, `'docker'`, `'cache_general'`, `'archivos_gigantes'`).

- [ ] **Paso 1: Escribe los tests que fallan**

```python
# tests/test_motor_unico.py
"""La CLI y la web tienen que ver las mismas recomendaciones.

Hoy hay dos copias: `disk_analyzer_core.py:561` la usa la web y
`disk_analyzer.py:888` la usan la CLI y la app de bandeja. La app de bandeja
ejecuta `disk_analyzer.py`, así que la barra y la web pueden recomendar cosas
distintas del mismo disco.

Además, ninguna recomendación tiene identificador estable: `type` es una cadena
de display en español y ya difiere entre copias ('Cache de Simuladores' contra
'Cache de Simuladores iOS'). Sin `id` no se puede configurar nada.
"""
import sys

sys.path.insert(0, '.')
from disk_analyzer import DiskAnalyzer
from disk_analyzer_core import DiskAnalyzerCore


def _preparar(obj, cache_locations, docker_stats=None):
    obj.cache_locations = list(cache_locations)
    obj.large_files = []
    obj.docker_stats = docker_stats
    return obj.generate_recommendations()


def test_las_dos_interfaces_recomiendan_lo_mismo():
    core = DiskAnalyzerCore('.')
    core.find_cache_locations()
    locs, docker = core.cache_locations, core.docker_stats

    del_core = _preparar(DiskAnalyzerCore('.'), locs, docker)
    del_cli = _preparar(DiskAnalyzer('.'), locs, docker)

    assert [r['id'] for r in del_core] == [r['id'] for r in del_cli]
    assert [r['tier'] for r in del_core] == [r['tier'] for r in del_cli]
    assert [r['command'] for r in del_core] == [r['command'] for r in del_cli]


def test_los_ids_son_estables_y_no_son_texto_de_interfaz():
    core = DiskAnalyzerCore('.')
    core.find_cache_locations()
    for r in core.generate_recommendations():
        ident = r.get('id', '')
        assert ident, f"{r.get('type')} no tiene id"
        assert ident.islower() and ' ' not in ident, (
            f"{ident!r} parece texto de interfaz, no un identificador"
        )
        assert ident.isascii(), f"{ident!r} no es ascii: no sirve como clave"


def test_los_ids_no_se_repiten():
    core = DiskAnalyzerCore('.')
    core.find_cache_locations()
    ids = [r['id'] for r in core.generate_recommendations()]
    assert len(ids) == len(set(ids)), f"ids duplicados: {ids}"
```

- [ ] **Paso 2: Ejecútalos para verificar que fallan**

```bash
venv-web/bin/python -m pytest tests/test_motor_unico.py -v
```
Esperado: FAIL, no existe `id` y las dos listas difieren.

- [ ] **Paso 3: Añade `id` a cada recomendación del core**

En `disk_analyzer_core.py:561`, añade `'id': '<slug>'` a cada
`recommendations.append({...})`, con los slugs de la sección *Interfaces*.

- [ ] **Paso 4: Haz que la CLI delegue**

Sustituye el cuerpo entero de `generate_recommendations` en
`disk_analyzer.py:888` por una delegación. Antes de escribirlo, **lee las dos
implementaciones y anota las reglas que solo existen en la de la CLI** (Xcode
DerivedData, runtimes de simulador, VMs). Esas reglas se **mueven al core** con
su propio `id`; no se pierden.

```python
    def generate_recommendations(self) -> List[Dict]:
        """Delegado en el motor compartido.

        Antes había aquí una segunda implementación de los mismos niveles, que
        ya había divergido de la del core: la web recomendaba una cosa y la app
        de bandeja otra sobre el mismo disco, porque la bandeja ejecuta este
        fichero.
        """
        from disk_analyzer_core import DiskAnalyzerCore
        prestado = DiskAnalyzerCore(str(self.start_path))
        prestado.cache_locations = self.cache_locations
        prestado.large_files = self.large_files
        prestado.docker_stats = self.docker_stats
        return prestado.generate_recommendations()
```

Verifica el nombre real del atributo de ruta de `DiskAnalyzer` antes de usar
`self.start_path`.

- [ ] **Paso 5: Verifica que la suite entera sigue verde**

```bash
venv-web/bin/python -m pytest tests/ -q
```
Esperado: todo en verde. Si `tests/test_engine_characterization.py` falla,
compara el fallo con las reglas que moviste: puede estar anclando una
recomendación que solo existía en la CLI.

- [ ] **Paso 6: Commit**

```bash
git add disk_analyzer.py disk_analyzer_core.py tests/test_motor_unico.py
git commit -m "refactor: una sola definición de los niveles de limpieza"
```

---

## Fase 4 — Las reglas que faltan

### Task 7: Docker sin escaneo completo, `~/Library/Caches` y papelera

**Archivos:**
- Modificar: `disk_analyzer_core.py` (`generate_recommendations`)
- Crear: `tests/test_reglas_nuevas.py`

**Contexto medido:** las cachés de la máquina de desarrollo suman 101,85 GB,
pero solo se recomiendan 17,6 y solo 4,01 son de nivel 1. Se quedan fuera Docker
(39,6 GB), `~/Library/Caches` (21,4 GB) y la papelera. La regla de Docker
**solo necesita `docker system df`**, que tarda segundos: hoy no aparece en la
bandeja porque nadie rellena `docker_stats` en ese camino.

- [ ] **Paso 1: Escribe los tests que fallan**

```python
# tests/test_reglas_nuevas.py
"""Las reglas que dejaban fuera el 80% de lo encontrado."""
import sys

sys.path.insert(0, '.')
from disk_analyzer_core import DiskAnalyzerCore
from analyzer import cache_types

GB = 1024 ** 3


def _core_con(locs, docker=None):
    core = DiskAnalyzerCore('.')
    core.cache_locations = locs
    core.large_files = []
    core.docker_stats = docker
    return core


def test_las_caches_de_library_se_recomiendan():
    """21,4 GB reales en la máquina de desarrollo, sin ninguna regla."""
    import os
    ruta = os.path.expanduser('~/Library/Caches')
    core = _core_con([{'type': cache_types.GENERAL, 'path': ruta,
                       'size': 21 * GB}])
    ids = {r['id'] for r in core.generate_recommendations()}
    assert 'caches_de_apps' in ids


def test_la_papelera_se_recomienda():
    import os
    ruta = os.path.expanduser('~/.Trash')
    core = _core_con([{'type': cache_types.TRASH, 'path': ruta,
                       'size': 3 * GB}])
    recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'papelera' in recs
    assert recs['papelera']['tier'] == 1, "vaciar la papelera es seguro"


def test_docker_aparece_solo_con_docker_stats():
    """No debe exigir un escaneo del disco completo: `docker system df` basta."""
    core = _core_con([], docker={'available': True, 'reclaimable': 39 * GB})
    recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'docker' in recs
    assert recs['docker']['efecto'] == 'irreversible'


def test_las_caches_de_apps_no_incluyen_datos_de_usuario():
    """La regla no puede arrastrar nada que no sea caché."""
    from analyzer.protection import puede_borrarse
    import os
    core = _core_con([{'type': cache_types.GENERAL,
                       'path': os.path.expanduser('~/Library/Caches'),
                       'size': 21 * GB}])
    for r in core.generate_recommendations():
        if r['id'] == 'caches_de_apps':
            assert puede_borrarse(os.path.expanduser('~/Library/Caches'))
```

- [ ] **Paso 2: Ejecútalos para verificar que fallan**

```bash
venv-web/bin/python -m pytest tests/test_reglas_nuevas.py -v
```
Esperado: FAIL, no existen `caches_de_apps` ni `papelera`.

- [ ] **Paso 3: Añade las reglas al core**

En `generate_recommendations`, junto a las de nivel 2:

```python
        # Cachés de aplicaciones: 21,4 GB medidos en la máquina de desarrollo y
        # ninguna regla los miraba. Nivel 2 y no 1 porque algunas apps guardan
        # ahí cosas que tardan en regenerarse (índices, miniaturas).
        app_caches = [l for l in self.cache_locations
                      if l['type'] == cache_types.GENERAL
                      and 'Library/Caches' in l['path']]
        if app_caches and sum(l['size'] for l in app_caches) > 500 * MB:
            total = sum(l['size'] for l in app_caches)
            recommendations.append({
                'id': 'caches_de_apps', 'tier': 2, 'priority': 'Moderado',
                'type': 'Cachés de aplicaciones',
                'description': f'{self.format_size(total)} en ~/Library/Caches',
                'space': total, 'efecto': 'borra',
                'command': comandos.borrar_contenido(
                    [l['path'] for l in app_caches])})
```

Y junto a las de nivel 1:

```python
        # La papelera: espacio que el usuario ya decidió tirar. Nivel 1 sin
        # discusión, y además es lo único que hace que "mover a la papelera"
        # libere algo de verdad en el mismo volumen.
        papelera = [l for l in self.cache_locations
                    if l['type'] == cache_types.TRASH]
        if papelera and sum(l['size'] for l in papelera) > 100 * MB:
            total = sum(l['size'] for l in papelera)
            recommendations.append({
                'id': 'papelera', 'tier': 1, 'priority': 'Seguro',
                'type': 'Papelera',
                'description': f'{self.format_size(total)} ya en la papelera',
                'space': total, 'efecto': 'borra',
                'command': comandos.borrar_contenido(
                    [l['path'] for l in papelera])})
```

- [ ] **Paso 4: Rellena `docker_stats` en el camino de la bandeja**

`docker_stats` viene de `docker system df` y tarda segundos, pero hoy solo se
rellena en el escaneo completo. Localiza dónde se puebla (busca
`docker_stats` en `disk_analyzer.py`) y llámalo también en el camino que usa
`--export`, para que la bandeja lo tenga. Si Docker no está instalado, el
atributo queda en `None` y la regla no dispara: no hace falta nada más.

- [ ] **Paso 5: Verifica**

```bash
venv-web/bin/python -m pytest tests/ -q
```

- [ ] **Paso 6: Commit**

```bash
git add disk_analyzer_core.py disk_analyzer.py tests/test_reglas_nuevas.py
git commit -m "feat: reglas para cachés de apps, papelera y Docker sin escaneo completo"
```

---

## Fase 5 — El puerto

### Task 8: Puerto efímero y no reutilizar servidores ajenos

**Archivos:**
- Modificar: `desktop/src-tauri/src/servidor.rs`
- Test: módulo `#[cfg(test)]` dentro del mismo fichero

**Contexto:** hoy `PUERTO` es `8000` fijo y `puerto_ocupado()` solo comprueba
que *algo* acepte TCP ahí. Con un Django o un Rails en el 8000, "Abrir
analizador completo" abre esa aplicación diciendo que es el analizador. El 8000
además es un puerto muy disputado, y la app abre el navegador ella misma, así
que el número es invisible para el usuario: no hay ninguna razón para fijarlo.
`make web` se queda con el 8000, que es su comportamiento documentado.

- [ ] **Paso 1: Escribe los tests que fallan**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    #[test]
    fn pide_un_puerto_libre_distinto_del_8000() {
        let p = puerto_libre().expect("debería conseguir un puerto");
        assert_ne!(p, 8000, "el 8000 está muy disputado: Django, Rails, etc.");
        assert!(p >= 1024, "no se piden puertos privilegiados");
    }

    #[test]
    fn dos_llamadas_no_devuelven_el_mismo_puerto_ocupado() {
        let a = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let ocupado = a.local_addr().unwrap().port();
        // Mientras `a` siga vivo, nadie debe proponer ese puerto.
        for _ in 0..20 {
            assert_ne!(puerto_libre().unwrap(), ocupado);
        }
    }

    #[test]
    fn no_reutiliza_un_servidor_ajeno() {
        // Alguien ocupa un puerto sin ser nuestro servidor.
        let ajeno = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let puerto = ajeno.local_addr().unwrap().port();
        let servidor = Servidor::new();
        assert!(
            !servidor.es_nuestra_instancia(puerto),
            "abrir el navegador en un servidor ajeno lo presenta como nuestro"
        );
    }
}
```

- [ ] **Paso 2: Ejecútalos para verificar que fallan**

```bash
export PATH="$HOME/.cargo/bin:$PATH"
cargo test --manifest-path desktop/src-tauri/Cargo.toml --lib servidor
```
Esperado: FAIL, `puerto_libre` y `es_nuestra_instancia` no existen.

- [ ] **Paso 3: Implementa el puerto efímero**

```rust
/// Pide al sistema un puerto libre.
///
/// Atar el 0 hace que el kernel asigne uno sin usar; se suelta acto seguido y
/// se le pasa al servidor. Queda una ventana mínima en la que otro proceso
/// podría cogerlo, y por eso quien llama reintenta.
///
/// El 8000 fijo que había antes es un puerto muy disputado (Django, Rails,
/// http.server). Y como la app abre el navegador ella misma, el número nunca
/// lo ve el usuario: fijarlo solo servía para chocar.
fn puerto_libre() -> Result<u16, String> {
    let l = std::net::TcpListener::bind(("127.0.0.1", 0))
        .map_err(|e| format!("no se pudo pedir un puerto libre: {e}"))?;
    let p = l
        .local_addr()
        .map_err(|e| format!("no se pudo leer el puerto asignado: {e}"))?
        .port();
    drop(l);
    Ok(p)
}
```

- [ ] **Paso 4: Reutiliza solo lo nuestro**

```rust
impl Servidor {
    /// Si el puerto lo ocupa el servidor que arrancamos nosotros.
    ///
    /// La versión anterior solo comprobaba que *algo* aceptara TCP en el 8000,
    /// así que un Django del usuario se abría en el navegador como si fuera el
    /// analizador. Ahora se exige que sea nuestra instancia registrada y que su
    /// proceso siga vivo.
    pub fn es_nuestra_instancia(&self, puerto: u16) -> bool {
        let guard = self.instancia.lock().unwrap();
        match guard.as_ref() {
            Some(inst) => {
                inst.puerto == puerto
                    && unsafe { libc::kill(inst.pid, 0) } == 0
                    && acepta(puerto)
            }
            None => false,
        }
    }
}
```

Añade `puerto: u16` al struct `Instancia`, renombra `puerto_ocupado()` a
`acepta(puerto: u16) -> bool` recibiendo el puerto, y en `abrir`:

- si `es_nuestra_instancia(inst.puerto)` → devuelve la URL guardada;
- si no → **siempre** arranca uno nuevo en `puerto_libre()`, sin mirar el 8000;
- borra por completo la rama que abría la URL a secas cuando el puerto estaba
  ocupado por otro.

- [ ] **Paso 5: Verifica**

```bash
export PATH="$HOME/.cargo/bin:$PATH"
cargo clippy --manifest-path desktop/src-tauri/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path desktop/src-tauri/Cargo.toml
```

- [ ] **Paso 6: Verificación manual**

```bash
python3 -m http.server 8000 &     # ocupa el 8000 con algo ajeno
open "/Applications/Disk Use Analyzer.app"
```
Pulsa "Abrir analizador completo". Esperado: se abre **el analizador**, en un
puerto distinto del 8000, no el `http.server`. Después: `kill %1`.

- [ ] **Paso 7: Commit**

```bash
git add desktop/src-tauri/src/servidor.rs
git commit -m "fix(desktop): puerto efímero y no abrir servidores ajenos como propios"
```

---

## Fuera del alcance de este plan

Declarado, no olvidado:

- **La ventana nativa con gráficas propias.** Dos revisiones adversariales
  independientes concluyeron que sería el tercer stack de visualización del
  repositorio (el informe del CLI ya embebe Plotly, la web también) para mostrar
  peor lo que "Abrir analizador completo" ya entrega. Se descarta hasta tener
  una razón que no sea estética.
- **El catálogo declarativo y los cuatro ejes de configuración.** Los `id`
  estables del Task 6 son exactamente la migración que haría falta si algún día
  se construye; hasta entonces no se paga el edificio. De los cuatro ejes, tres
  fueron calificados de teatro por la revisión de producto; el único que se
  gana el sitio —activar/desactivar categorías— cabe como casillas en el diálogo
  de confirmación, sin pantalla de ajustes.
- **El botón "Liberar lo seguro" en el menú de la bandeja.** Es lo que originó
  todo esto, y sigue siendo deseable — pero construirlo antes de la Fase 1 sería
  poner un botón de un clic encima de una inyección de shell. Tendrá su propio
  plan cuando esto esté verde.
- **La semántica de papelera por nivel.** Queda pendiente de decisión: para las
  invocaciones a herramientas no existe papelera posible, y mover ficheros a
  `~/.Trash` en el mismo volumen no libera espacio hasta vaciarla. El campo
  `efecto` del Task 4 es lo que permitirá decidirlo con datos.
- **La Fase 0 de higiene del repositorio**, que sigue pendiente desde julio.

## Autorrevisión

**1. Cobertura de los hallazgos:** H1 → Task 1; H2 → Tasks 1 y 5; H3 → Task 3;
H4 → Task 2; H5 → Task 8. La duplicación del motor → Task 6. El hueco de 101 GB
contra 4 GB recomendados → Task 7.

**2. Marcadores:** ninguno. Las notas del tipo "verifica el nombre real de la
variable antes de sustituir" son deliberadas: los nombres exactos de esos
atributos no se pudieron confirmar al escribir el plan y respetarlas evita un
reemplazo a ciegas.

**3. Consistencia de tipos:** `comandos.borrar_contenido/borrar_rutas` se
definen en el Task 1 y se consumen en los Tasks 1, 6 y 7. `puede_borrarse` se
define en el Task 2 y se consume en el Task 7. `'efecto'` se define en el Task 4
y se consume en el Task 7. `'id'` se define en el Task 6 y se consume en el
Task 7 y en los tests del 7. `nivelDe` es local al Task 3.

**4. Riesgo principal:** el Task 6 toca la función de la que dependen los tests
de caracterización. Por eso va después de las fases de seguridad: si hay que
revertirlo, los arreglos críticos ya están dentro.
