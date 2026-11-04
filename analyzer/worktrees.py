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
from analyzer.proyectos import PROFUNDIDAD_MAXIMA, ROOTS, _tamano


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


def _directorios_en_uso() -> Set[str]:
    """Where running processes are working: a session may be inside a worktree
    even with nothing to commit yet."""
    try:
        r = subprocess.run(['/usr/sbin/lsof', '-a', '-d', 'cwd', '-Fn'],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return set()
    return {l[1:] for l in r.stdout.splitlines() if l.startswith('n')}


def _en_uso(ruta: Path, en_uso: Set[str]) -> bool:
    prefijo = f'{ruta}{os.sep}'
    return any(d == str(ruta) or d.startswith(prefijo) for d in en_uso)


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
    """Removes a worktree only if its commit is still merged. `git worktree
    remove` refuses by itself if it has changes or untracked files."""
    r, w = escapar(str(repo)), escapar(str(ruta))
    return (f'git -C {r} merge-base --is-ancestor {escapar(commit)} {escapar(por_defecto)} '
            f'&& git -C {r} worktree remove {w}')


def del_repo(repo: Path, en_uso: Set[str]) -> List[Dict]:
    por_defecto = _rama_por_defecto(repo)
    salida = []
    for w in _listar(repo):
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
            # Nothing of it is left but git's own bookkeeping.
            fila['motivo'] = 'rota: la carpeta ya no está'
            fila['command'] = f'git -C {escapar(str(repo))} worktree prune'
            salida.append(fila)
            continue
        fila['space'] = _tamano(ruta)
        estado = _git(ruta, 'status', '--porcelain')
        fila['cambios'] = len(estado.splitlines()) if estado else 0
        fecha = _git(ruta, 'log', '-1', '--format=%ct')
        if fecha:
            fila['dias'] = int((time.time() - int(fecha)) / 86400)
        commit = w.get('HEAD', '')
        fila['mergeada'] = bool(
            por_defecto and commit
            and _git(repo, 'merge-base', '--is-ancestor', commit, por_defecto) is not None)
        fila['en_uso'] = _en_uso(ruta, en_uso)
        if estado is None:
            fila['motivo'] = 'git no pudo leer su estado'
        elif fila['cambios']:
            fila['motivo'] = 'tiene cambios sin commit'
        elif not por_defecto:
            fila['motivo'] = 'no se sabe cuál es la rama principal'
        elif not fila['mergeada']:
            fila['motivo'] = 'la rama no está mergeada'
        elif fila['en_uso']:
            fila['motivo'] = 'hay un proceso trabajando dentro'
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
    for raiz in (raices if raices is not None else ROOTS):
        ruta = Path(raiz).expanduser()
        if ruta.is_dir() and not ruta.is_symlink():
            repos.update(_repos(ruta))
    salida: List[Dict] = []
    for repo in sorted(repos):
        salida.extend(del_repo(repo, en_uso))
    salida.sort(key=lambda w: -w['space'])
    return salida
