"""The Python and Node installations and environments on the machine.

Several usually coexist unnoticed. Only conda offers to clean anything here,
with its own commands: removing a Homebrew formula could break others that
depend on it, and the system's Python is not ours to touch, so the rest is
listed to inform, without a command.
"""
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from analyzer.comandos import escapar
from analyzer.proyectos import TAMANO_MINIMO, _tamano

BASES_CONDA = ('/opt/anaconda3', '/opt/miniconda3', '~/anaconda3', '~/miniconda3',
               '~/miniforge3', '~/opt/anaconda3')

# (label, folder holding one folder per version)
VERSIONES = (
    ('uv', '~/.local/share/uv/python'),
    ('pyenv', '~/.pyenv/versions'),
    ('nvm', '~/.nvm/versions/node'),
    ('fnm', '~/.local/share/fnm/node-versions'),
)
CELLAR = '/opt/homebrew/Cellar'
FORMULAS = ('python@', 'node')
GLOBALES_NPM = '/opt/homebrew/lib/node_modules'

SOLO_INFORMA = 'solo informa'


def _fila(id_: str, titulo: str, ruta: Path, consecuencia: str = 'regenera',
          command: str = '', dias: Optional[int] = None) -> Optional[Dict]:
    tam = _tamano(ruta)
    if tam < TAMANO_MINIMO:
        return None
    return {'id': f'ambiente:{id_}', 'titulo': titulo, 'descripcion': str(ruta),
            'categoria': 'ambientes', 'consecuencia': consecuencia, 'ruta': str(ruta),
            'space': tam, 'dias': dias, 'command': command,
            'motivo': '' if command else SOLO_INFORMA}


def _dias_desde(ruta: Path) -> Optional[int]:
    """Days since conda last changed the environment."""
    try:
        return int((time.time() - (ruta / 'conda-meta').stat().st_mtime) / 86400)
    except OSError:
        return None


def _de_conda(base: Path) -> List[Dict]:
    conda = base / 'bin' / 'conda'
    if not conda.exists():
        return []
    c = escapar(str(conda))
    filas = [_fila(f'{base.name}-pkgs', 'Paquetes de conda', base / 'pkgs', 'redescarga',
                   f'{c} clean --all -y')]
    entornos = base / 'envs'
    if entornos.is_dir():
        for e in sorted(os.scandir(entornos), key=lambda e: e.name):
            ruta = Path(e.path)
            # Only what conda itself recognises as an environment.
            if e.is_dir(follow_symlinks=False) and (ruta / 'conda-meta').is_dir():
                filas.append(_fila(f'{base.name}-env-{e.name}', f'Entorno conda {e.name}', ruta,
                                   'redescarga', f'{c} env remove -y -p {escapar(str(ruta))}',
                                   _dias_desde(ruta)))
    return [f for f in filas if f]


def _versiones() -> List[Dict]:
    filas: List[Optional[Dict]] = []
    for etiqueta, carpeta in VERSIONES:
        ruta = Path(carpeta).expanduser()
        if ruta.is_dir():
            for e in sorted(os.scandir(ruta), key=lambda e: e.name):
                if e.is_dir(follow_symlinks=False):
                    filas.append(_fila(f'{etiqueta}-{e.name}', f'{e.name} ({etiqueta})', Path(e.path)))
    cellar = Path(CELLAR)
    if cellar.is_dir():
        for e in sorted(os.scandir(cellar), key=lambda e: e.name):
            if e.name.startswith(FORMULAS) and e.is_dir(follow_symlinks=False):
                filas.append(_fila(f'brew-{e.name}', f'{e.name} (Homebrew)', Path(e.path)))
    globales = Path(GLOBALES_NPM)
    if globales.is_dir():
        filas.append(_fila('npm-globales', 'Paquetes globales de npm', globales))
    return [f for f in filas if f]


def inventario(bases: Optional[Tuple[str, ...]] = None) -> List[Dict]:
    """Every environment found: what can be cleaned first, largest first."""
    filas: List[Dict] = []
    for base in (bases if bases is not None else BASES_CONDA):
        ruta = Path(base).expanduser()
        if ruta.is_dir() and not ruta.is_symlink():
            filas.extend(_de_conda(ruta))
    filas.extend(_versiones())
    filas.sort(key=lambda f: (not f['command'], -f['space']))
    return filas
