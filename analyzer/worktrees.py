"""The linked git worktrees under the usual project folders.

They pile up unnoticed, many of them left by automated tools, and each one holds
a full copy of the project. Removal only goes through `git worktree remove`
without `--force`, which refuses a worktree with changes, and the command checks
again that the branch is merged: everything may have changed since the measure.

"Merged" means the commit is reachable from the default branch. A squash merge
leaves it unreachable, so it reads as not merged: the safe direction to be wrong.
"""
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set

from analyzer.comandos import escapar
from analyzer.proyectos import PROFUNDIDAD_MAXIMA, ROOTS, _tamano, raices_unicas


# Ignored folders that are safe to lose with the worktree.
SE_RECONSTRUYEN = frozenset((
    'node_modules', '.venv', 'venv', 'target', '.next', 'dist', 'build', '__pycache__',
    '.turbo', '.parcel-cache', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.DS_Store',
    'coverage', '.astro', '.svelte-kit', '.nuxt', '.vite', '.gradle', '.terraform',
))


def _git(arbol: Path, *args: str) -> Optional[str]:
    """A git command's output, or None if it failed."""
    try:
        r = subprocess.run(['git', '-C', str(arbol), *args],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _repos(raiz: Path, profundidad: int = 0) -> Iterator[Path]:
    """Main clones under `raiz`. A linked worktree has a `.git` file, so it is
    reached through its clone, and a clone is not entered: what is inside it
    belongs to it. Not even for its worktrees, which git itself lists."""
    if profundidad > PROFUNDIDAD_MAXIMA:
        return
    try:
        entradas = list(os.scandir(raiz))
    except OSError:
        return
    if any(e.name == '.git' and e.is_dir(follow_symlinks=False) for e in entradas):
        yield raiz
        return
    for e in entradas:
        try:
            es_carpeta = e.is_dir(follow_symlinks=False)
        except OSError:
            continue
        if es_carpeta and not e.name.startswith('.') and e.name not in ('node_modules', 'Library'):
            yield from _repos(Path(e.path), profundidad + 1)


def _rama_por_defecto(repo: Path) -> Optional[str]:
    remota = _git(repo, 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD')
    if remota:
        return remota
    for nombre in ('main', 'master'):
        if _git(repo, 'rev-parse', '--verify', '-q', f'refs/heads/{nombre}'):
            return nombre
    return None


def _directorios_en_uso() -> Optional[Set[str]]:
    """Where running processes are working: a session may be inside a worktree
    even with nothing to commit yet. `None` if it cannot be known, which must
    not read as "nobody": there is always some process with a working folder."""
    try:
        r = subprocess.run(['/usr/sbin/lsof', '-a', '-d', 'cwd', '-Fn'],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    filas = {l[1:] for l in r.stdout.splitlines() if l.startswith('n')}
    return filas or None


def _en_uso(ruta: Path, en_uso: Set[str]) -> bool:
    prefijo = f'{ruta}{os.sep}'
    return any(d == str(ruta) or d.startswith(prefijo) for d in en_uso)


def _ignorados_que_se_pierden(ruta: Path) -> Optional[List[str]]:
    """What `git worktree remove` would delete without warning: it refuses over
    changes and untracked files, but not over ignored ones, and a `.env` is
    ignored precisely because it matters. `None` if git cannot say."""
    salida = _git(ruta, 'status', '--porcelain', '--ignored')
    if salida is None:
        return None
    perdidos = []
    for linea in salida.splitlines():
        if linea.startswith('!! '):
            nombre = linea[3:].strip('"').rstrip('/').rsplit('/', 1)[-1]
            if nombre not in SE_RECONSTRUYEN and not nombre.endswith(('.pyc', '.log')):
                perdidos.append(linea[3:])
    return perdidos


def _listar(repo: Path) -> List[Dict[str, str]]:
    """`git worktree list --porcelain`, without the main working tree."""
    salida = _git(repo, 'worktree', 'list', '--porcelain')
    if salida is None:
        return []
    bloques = [b for b in re.split(r'\n\n+', salida) if b.strip()]
    filas = []
    for bloque in bloques[1:]:
        datos: Dict[str, str] = {}
        for linea in bloque.splitlines():
            clave, _, valor = linea.partition(' ')
            datos[clave] = valor
        filas.append(datos)
    return filas


def comando_quitar(repo: Path, ruta: Path, commit: str, por_defecto: str) -> str:
    """Removes a worktree, checking everything again first, because anything may
    have changed since the measure. `git worktree remove` refuses by itself if
    there are changes or untracked files; the rest is on this command:

    - HEAD is still the commit that was measured (a new one might not be merged);
    - that commit is still in the default branch;
    - no process is working inside, and if that cannot be known, nothing goes;
    - no ignored file has appeared that would be lost.
    """
    r, w, c = escapar(str(repo)), escapar(str(ruta)), escapar(commit)
    n = escapar(f'n{ruta}')
    permitidos = '|'.join(re.escape(x) for x in sorted(SE_RECONSTRUYEN))
    filtro = escapar(f'^!! (.*/)?({permitidos})/?$|\\.(pyc|log)$')
    return (f'test "$(git -C {w} rev-parse HEAD)" = {c} '
            f'&& git -C {r} merge-base --is-ancestor {c} {escapar(por_defecto)} '
            f'&& u="$(/usr/sbin/lsof -a -d cwd -Fn 2>/dev/null)" && test -n "$u" '
            f'&& ! printf %s "$u" | grep -qF -- {n} '
            f'&& ! git -C {w} status --porcelain --ignored | grep "^!! " | grep -qvE {filtro} '
            f'&& git -C {r} worktree remove {w}')


def _prune_seguro(rotas: List[Dict[str, str]], repo: Path, por_defecto: Optional[str]) -> bool:
    """`git worktree prune` acts on the whole repo, and a folder that is not there
    may be on a disk that is not mounted, or moved. Only if every missing one is
    away from any external disk and its commit survives: a branch keeps it, or it
    is merged."""
    for w in rotas:
        if w.get('worktree', '').startswith('/Volumes/'):
            return False
        if 'locked' in w:
            return False
        if 'branch' in w:
            continue
        commit = w.get('HEAD', '')
        if not (por_defecto and commit and _git(
                repo, 'merge-base', '--is-ancestor', commit, por_defecto) is not None):
            return False
    return True


def del_repo(repo: Path, en_uso: Optional[Set[str]]) -> List[Dict]:
    por_defecto = _rama_por_defecto(repo)
    salida = []
    worktrees = _listar(repo)
    rotas = [w for w in worktrees
             if 'prunable' in w or not Path(w.get('worktree', '')).is_dir()]
    prune_seguro = _prune_seguro(rotas, repo, por_defecto)
    for w in worktrees:
        ruta = Path(w.get('worktree', ''))
        rama = w.get('branch', '').replace('refs/heads/', '') or '(sin rama)'
        rota = 'prunable' in w or not ruta.is_dir()
        fila = {
            'id': f'worktree:{ruta}',
            'titulo': f'{repo.name} · {ruta.name}',
            'descripcion': str(ruta),
            'categoria': 'worktrees',
            'consecuencia': 'regenera',
            'repo': str(repo),
            'ruta': str(ruta),
            'rama': rama,
            'rota': rota,
            'cambios': 0,
            'mergeada': False,
            'en_uso': False,
            'dias': None,
            'space': 0,
            'motivo': '',
            'command': '',
        }
        if rota:
            if prune_seguro:
                # Nothing of it is left here but git's own bookkeeping.
                fila['command'] = f'git -C {escapar(str(repo))} worktree prune'
            else:
                fila['motivo'] = 'su carpeta no está: podría haberse movido o estar en otro disco'
            salida.append(fila)
            continue
        fila['space'] = _tamano(ruta)
        estado = _git(ruta, 'status', '--porcelain')
        fila['cambios'] = len(estado.splitlines()) if estado else 0
        fecha = _git(ruta, 'log', '-1', '--format=%ct')
        if fecha:
            # A commit dated in the future must not give a negative age.
            fila['dias'] = max(0, int((time.time() - int(fecha)) / 86400))
        commit = w.get('HEAD', '')
        fila['mergeada'] = bool(
            por_defecto and commit
            and _git(repo, 'merge-base', '--is-ancestor', commit, por_defecto) is not None)
        fila['en_uso'] = en_uso is not None and _en_uso(ruta, en_uso)
        ignorados = _ignorados_que_se_pierden(ruta)
        if estado is None:
            fila['motivo'] = 'git no pudo leer su estado'
        elif fila['cambios']:
            fila['motivo'] = 'tiene cambios sin commit'
        elif not por_defecto:
            fila['motivo'] = 'no se sabe cuál es la rama principal'
        elif not fila['mergeada']:
            fila['motivo'] = 'la rama no está mergeada'
        elif en_uso is None:
            fila['motivo'] = 'no se pudo comprobar si hay algo trabajando dentro'
        elif fila['en_uso']:
            fila['motivo'] = 'hay un proceso trabajando dentro'
        elif ignorados is None:
            fila['motivo'] = 'git no pudo leer sus archivos ignorados'
        elif ignorados:
            fila['motivo'] = 'tiene archivos ignorados que no se reconstruyen'
        elif 'locked' in w:
            fila['motivo'] = 'está bloqueado'
        else:
            fila['command'] = comando_quitar(repo, ruta, commit, por_defecto)
        salida.append(fila)
    return salida


def inventario(raices: Optional[List[str]] = None) -> List[Dict]:
    """Every linked worktree found, largest first."""
    en_uso = _directorios_en_uso()
    repos = set()
    for ruta in raices_unicas(raices if raices is not None else ROOTS):
        repos.update(_repos(ruta))
    salida: List[Dict] = []
    for repo in sorted(repos):
        salida.extend(del_repo(repo, en_uso))
    salida.sort(key=lambda w: -w['space'])
    return salida
