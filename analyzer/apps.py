"""How much each app really takes: its bundle plus its data in ~/Library.

Only informs: an app's data can be impossible to recover, so nothing here is
ever offered for deletion. It only helps to find the app in Finder.

Data is tied to an app by exact bundle identifier or exact bundle name, never
by a similar name: that would add someone else's data to the wrong app.

There is no last-used date: Spotlight returned nothing for the apps tried, not
even one in daily use. Better no date than a wrong one.
"""
import os
import plistlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from analyzer.proyectos import TAMANO_MINIMO, _tamano

CARPETAS = ('/Applications', '~/Applications')
# Reading this without Full Disk Access makes macOS ask, app by app.
ENV_ACCESO = 'DISK_ANALYZER_ACCESO_TOTAL'


def _bundle(app: Path) -> Tuple[Optional[str], Optional[str]]:
    """Identifier and name from the bundle's Info.plist."""
    try:
        with open(app / 'Contents' / 'Info.plist', 'rb') as f:
            info = plistlib.load(f)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None, None
    return info.get('CFBundleIdentifier'), info.get('CFBundleName')


def _apps(carpeta: Path) -> Iterator[Tuple[Path, Path]]:
    """(what to measure, the bundle). An app in a folder of its own, as games
    and suites do, takes the whole folder: the rest of it is the app's too."""
    try:
        entradas = sorted(os.scandir(carpeta), key=lambda e: e.name)
    except OSError:
        return
    for e in entradas:
        if not e.is_dir(follow_symlinks=False):
            continue
        ruta = Path(e.path)
        if e.name.endswith('.app'):
            yield ruta, ruta
            continue
        try:
            dentro = sorted(x for x in ruta.iterdir() if x.name.endswith('.app'))
        except OSError:
            continue
        if dentro:
            yield ruta, dentro[0]


def _datos(bundle_id: Optional[str], nombre: Optional[str], biblioteca: Path) -> List[Path]:
    rutas = []
    if bundle_id:
        rutas += [biblioteca / 'Containers' / bundle_id,
                  biblioteca / 'Application Support' / bundle_id]
    if nombre:
        rutas.append(biblioteca / 'Application Support' / nombre)
    # Dropping a duplicate matters: an app whose name is its identifier.
    return [r for r in dict.fromkeys(rutas) if r.is_dir() and not r.is_symlink()]


def _medir(par: Tuple[Path, Path], biblioteca: Optional[Path]) -> Optional[Dict]:
    medir, bundle = par
    bundle_id, nombre = _bundle(bundle)
    tam = _tamano(medir)
    datos = 0
    if biblioteca is not None:
        datos = sum(_tamano(r) for r in _datos(bundle_id, nombre, biblioteca))
    if tam + datos < TAMANO_MINIMO:
        return None
    return {'id': f'app:{medir}', 'titulo': medir.name.removesuffix('.app'),
            'descripcion': str(medir), 'categoria': 'apps', 'consecuencia': 'solo_lista',
            'space': tam + datos, 'tam_app': tam, 'tam_datos': datos, 'ruta': str(medir),
            'motivo': 'solo informa', 'command': ''}


def inventario(carpetas: Optional[Tuple[str, ...]] = None,
               biblioteca: Optional[Path] = None) -> List[Dict]:
    """Largest first. Without `biblioteca`, only the bundles are measured."""
    if biblioteca is None and os.environ.get(ENV_ACCESO) == '1':
        biblioteca = Path.home() / 'Library'
    pares: List[Tuple[Path, Path]] = []
    for carpeta in (carpetas if carpetas is not None else CARPETAS):
        ruta = Path(carpeta).expanduser()
        if ruta.is_dir():
            pares.extend(_apps(ruta))
    with ThreadPoolExecutor(max_workers=6) as hilos:
        filas = list(hilos.map(lambda p: _medir(p, biblioteca), pares))
    salida = [f for f in filas if f]
    salida.sort(key=lambda f: -f['space'])
    return salida
