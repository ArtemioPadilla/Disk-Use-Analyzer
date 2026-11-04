"""The large files of the last analysis, grouped by what they are.

These are the user's own files, so nothing here offers to delete them: each group
leads to its list in the analyzer, where they are chosen one by one and go to the
Trash. Each group also carries that link, so the two sides share one definition
of which extensions make a group.

A scan from the menu does not go through the web server, so `guardar` leaves its
report where the server looks for its own: that is what lets the analyzer see it.
"""
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

# (group, extensions). Screen recordings are videos too: their extension cannot
# tell them apart, and telling them by file name depends on the system language.
GRUPOS = (
    ('Videos', ('.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v')),
    ('Imágenes de disco', ('.dmg', '.iso', '.img', '.vmdk', '.vdi', '.qcow2')),
    ('Instaladores', ('.pkg', '.exe', '.msi', '.ipa', '.apk')),
    ('Datos y modelos', ('.csv', '.parquet', '.h5', '.hdf5', '.npy', '.npz', '.arrow',
                         '.feather', '.pt', '.ckpt', '.safetensors', '.gguf')),
    ('Comprimidos', ('.zip', '.tar', '.gz', '.tgz', '.7z', '.rar', '.xz', '.bz2')),
)

# Inside these a large file is not the user's to review one by one: an app or a
# project keeps it there on purpose, and other parts of the menu deal with them.
FUERA = ('/Library/', '/node_modules/', '/.venv/', '/.git/', '/.cache/', '/.Trash/')
RAICES_FUERA = ('/Applications/', '/System/', '/private/', '/opt/', '/usr/')


def resultados() -> Path:
    return Path.home() / '.disk-analyzer' / 'results'


def _revisable(ruta: str) -> bool:
    return not ruta.startswith(RAICES_FUERA) and not any(f in ruta for f in FUERA)


def agrupar(archivos: List[Dict]) -> List[Dict]:
    """A row per group with something in it, largest first."""
    filas = []
    for nombre, extensiones in GRUPOS:
        propios = [a for a in archivos
                   if str(a.get('extension', '')).lower() in extensiones
                   and _revisable(str(a.get('path', '')))]
        if not propios:
            continue
        filas.append({
            'id': f'grupo:{nombre}',
            'titulo': f'{nombre} ({len(propios)})',
            'descripcion': '',
            'categoria': 'archivos',
            'consecuencia': 'solo_lista',
            'space': sum(int(a.get('size', 0)) for a in propios),
            'motivo': 'se eligen uno por uno',
            'destino': f"/files?exts={','.join(extensiones)}",
            'command': '',
        })
    filas.sort(key=lambda f: -f['space'])
    return filas


def _mas_reciente() -> Optional[Path]:
    try:
        ficheros = list(resultados().glob('*.json'))
        return max(ficheros, key=lambda p: p.stat().st_mtime) if ficheros else None
    except OSError:
        return None


def inventario() -> List[Dict]:
    """The groups of the last analysis, or nothing if there has been none."""
    ultimo = _mas_reciente()
    if ultimo is None:
        return []
    try:
        datos = json.loads(ultimo.read_text())
    except (OSError, ValueError):
        return []
    # A file may have gone since the analysis.
    archivos = [a for r in datos for a in r.get('report', {}).get('large_files', [])
                if os.path.exists(str(a.get('path', '')))]
    return agrupar(archivos)


def guardar(ruta_analizada: str, report: Dict) -> Path:
    """Leaves a finished report for the analyzer, replacing the previous one
    from the menu: results take room too. Written whole, so a failure keeps the
    previous one."""
    carpeta = resultados()
    carpeta.mkdir(parents=True, exist_ok=True)
    resumen = report.get('summary', {})
    contenido = [{
        'path': ruta_analizada,
        'report': report,
        'summary': {
            'total_size': resumen.get('total_size', 0),
            'files_scanned': resumen.get('files_scanned', 0),
            'large_files': len(report.get('large_files', [])),
            'cache_size': resumen.get('cache_size', 0),
            'recoverable': resumen.get('recoverable_space', 0),
            'docker_space': resumen.get('docker_space', 0),
            'docker_reclaimable': resumen.get('docker_reclaimable', 0),
        },
    }]
    destino = carpeta / f'menu-{int(time.time())}.json'
    temporal = carpeta / f'{destino.name}.tmp'
    temporal.write_text(json.dumps(contenido, default=str))
    os.replace(temporal, destino)
    for viejo in carpeta.glob('menu-*.json'):
        if viejo != destino:
            viejo.unlink(missing_ok=True)
    return destino
