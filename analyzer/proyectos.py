"""What development projects leave on disk and can be rebuilt.

Dependencies and build output usually take more room than any cache, and they
live in arbitrary folders of the user's, so finding them needs a walk rather
than a list of known paths. Only the folders named in `ROOTS` are walked: a
whole-disk scan takes minutes and this has to feed a menu.

Nothing here deletes. Each artifact carries a command built by
`analyzer/comandos.py`, which only lets through what `puede_borrarse` accepts,
and what it accepts needs evidence beside the name: see `es_artefacto`.
"""
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from analyzer import comandos
from analyzer.protection import es_artefacto

# Where projects usually live. A root that does not exist is simply skipped.
ROOTS = ('~/Documents', '~/Developer', '~/Projects', '~/projects', '~/repos',
         '~/src', '~/code', '~/workspace', '~/Desktop')

# Deep enough for monorepos and worktrees inside a repo; the bound keeps a
# strange tree from turning a menu refresh into a whole-disk walk.
PROFUNDIDAD_MAXIMA = 12

# Hidden folders worth entering: they hold worktrees of the repo around them.
OCULTAS_CON_PROYECTOS = ('.claude', '.worktrees')

# Below this, listing it only adds noise.
TAMANO_MINIMO = 10 * 1024 * 1024

# What says a Python environment can be rebuilt. Without any of these a `.venv`
# may be the only copy of what is installed in it.
DEFINE_ENTORNO = ('requirements.txt', 'pyproject.toml', 'uv.lock', 'Pipfile',
                  'poetry.lock', 'environment.yml', 'setup.py')


def _reproducible(ruta: Path) -> bool:
    """Whether the project says how to rebuild this artifact."""
    padre = ruta.parent
    if ruta.name in ('.venv', 'venv'):
        return (any((padre / f).exists() for f in DEFINE_ENTORNO)
                or any(padre.glob('requirements*.txt')))
    if ruta.name == 'node_modules':
        return (padre / 'package.json').exists()
    return True  # `target` and `.next` already require their manifest.


def _buscar(raiz: Path, profundidad: int = 0) -> Iterator[Path]:
    """Artifacts under `raiz`, without entering them or following symlinks."""
    if profundidad > PROFUNDIDAD_MAXIMA:
        return
    try:
        entradas = list(os.scandir(raiz))
    except OSError:
        return
    for e in entradas:
        try:
            if not e.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        ruta = Path(e.path)
        if es_artefacto(str(ruta)):
            yield ruta
        elif e.name == 'Library' or (e.name.startswith('.')
                                     and e.name not in OCULTAS_CON_PROYECTOS):
            continue
        else:
            yield from _buscar(ruta, profundidad + 1)


def _repo_de(ruta: Path) -> Tuple[Optional[Path], bool]:
    """The working tree holding `ruta`, and whether it is a linked worktree:
    those have a `.git` file where a normal clone has a folder."""
    for padre in ruta.parents:
        git = padre / '.git'
        if git.exists():
            return padre, git.is_file()
    return None, False


def _git(arbol: Path, *args: str) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(['git', '-C', str(arbol), *args],
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None


def _ignorado_por_git(ruta: Path, arbol: Path) -> bool:
    """An artifact git does not ignore may be tracked, so it may not be
    rebuildable at all. If git cannot say, treat it as not ignored."""
    r = _git(arbol, 'check-ignore', '-q', str(ruta))
    return r is not None and r.returncode == 0


def _ultima_actividad(ruta: Path, arbol: Optional[Path]) -> float:
    """When the project was last touched, leaving the artifact itself out:
    installing dependencies is not working on the project."""
    momentos = []
    carpeta = ruta.parent
    try:
        for e in os.scandir(carpeta):
            if e.path != str(ruta):
                momentos.append(e.stat(follow_symlinks=False).st_mtime)
    except OSError:
        pass
    if arbol is not None:
        git = arbol / '.git'
        for f in (git / 'index', git / 'HEAD', git):
            try:
                momentos.append(f.stat().st_mtime)
            except OSError:
                pass
    return max(momentos, default=0.0)


def _tamano(ruta: Path) -> int:
    """Real disk use through `du`: this is the slow part, so it runs in
    parallel, and `du` is much faster than a Python walk over node_modules."""
    try:
        r = subprocess.run(['du', '-sk', str(ruta)], capture_output=True,
                           text=True, timeout=300)
        return int(r.stdout.split()[0]) * 1024
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return 0


def raices_unicas(raices) -> List[Path]:
    """The roots that exist, each once: on APFS `~/Projects` and `~/projects` are
    usually the same folder, and walking it twice doubles every total."""
    vistas = set()
    salida = []
    for raiz in raices:
        ruta = Path(raiz).expanduser()
        try:
            if ruta.is_symlink() or not ruta.is_dir():
                continue
            st = ruta.stat()
        except OSError:
            continue
        if (st.st_dev, st.st_ino) not in vistas:
            vistas.add((st.st_dev, st.st_ino))
            salida.append(ruta)
    return salida


def inventario(raices: Optional[List[str]] = None) -> List[Dict]:
    """Every artifact found, largest first."""
    vistos = set()
    for ruta in raices_unicas(raices if raices is not None else ROOTS):
        vistos.update(_buscar(ruta))
    rutas = sorted(vistos)
    with ThreadPoolExecutor(max_workers=6) as hilos:
        tamanos = list(hilos.map(_tamano, rutas))

    ahora = time.time()
    salida = []
    for ruta, tam in zip(rutas, tamanos):
        if tam < TAMANO_MINIMO:
            continue
        arbol, es_worktree = _repo_de(ruta)
        ignorado = arbol is None or _ignorado_por_git(ruta, arbol)
        reproducible = _reproducible(ruta)
        actividad = _ultima_actividad(ruta, arbol)
        comando = comandos.borrar_rutas([str(ruta)]) if ignorado and reproducible else ''
        nombre = (arbol or ruta.parent).name
        salida.append({
            'id': f'proyecto:{ruta}',
            'titulo': f'{nombre} · {ruta.name}',
            'descripcion': str(ruta),
            'categoria': 'proyectos',
            'proyecto': nombre,
            'ruta_proyecto': str(arbol or ruta.parent),
            'artefacto': ruta.name,
            'ruta': str(ruta),
            'space': tam,
            # A file dated in the future must not give a negative age.
            'dias': max(0, int((ahora - actividad) / 86400)) if actividad else None,
            'worktree': es_worktree,
            'reproducible': reproducible,
            'ignorado': ignorado,
            'consecuencia': 'regenera',
            'command': comando,
        })
    salida.sort(key=lambda a: -a['space'])
    return salida
