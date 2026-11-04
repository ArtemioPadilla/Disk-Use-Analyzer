"""What Docker holds, by name: images that can go and volumes that stay.

An image only goes with `docker image rm`, without `-f`, so Docker itself refuses
if a container uses it. Volumes are listed and nothing more: they hold the
containers' data, which does not come back.
"""
import json
import subprocess
from typing import Dict, List, Optional, Set

from analyzer.comandos import escapar

UNIDADES = {'B': 1, 'KB': 10**3, 'MB': 10**6, 'GB': 10**9, 'TB': 10**12}
EN_USO = 'la usa un contenedor'
VOLUMEN = 'guarda datos: no se toca'


def _bytes(texto: str) -> int:
    """A size as Docker prints it, in decimal units: `12.5GB`, `1.2kB`, `0B`."""
    t = texto.strip().upper()
    for unidad in ('TB', 'GB', 'MB', 'KB', 'B'):
        if t.endswith(unidad):
            try:
                return int(float(t[:-len(unidad)]) * UNIDADES[unidad])
            except ValueError:
                return 0
    return 0


def _docker(*args: str) -> Optional[str]:
    try:
        r = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _json_por_linea(salida: Optional[str]) -> List[Dict]:
    filas = []
    for linea in (salida or '').splitlines():
        try:
            filas.append(json.loads(linea))
        except json.JSONDecodeError:
            continue
    return filas


def _imagenes_en_uso() -> Set[str]:
    """How containers name their images: name and tag, or an ID."""
    salida = _docker('ps', '-a', '--format', '{{.Image}}') or ''
    return {l.strip() for l in salida.splitlines() if l.strip()}


def inventario() -> List[Dict]:
    """Empty with the daemon off: the only source of these names is the daemon."""
    if _docker('version') is None:
        return []
    en_uso = _imagenes_en_uso()
    filas = []
    for i in _json_por_linea(_docker('image', 'ls', '--format', '{{json .}}')):
        id_ = i.get('ID', '')
        if not id_:
            continue
        nombre = f"{i.get('Repository', '<none>')}:{i.get('Tag', '<none>')}"
        # A miss here is harmless: without `-f`, Docker refuses by itself.
        ocupada = (nombre in en_uso or id_ in en_uso
                   or (i.get('Tag') == 'latest' and i.get('Repository') in en_uso))
        # By name, not by ID: an image with several tags is several rows, and
        # Docker refuses to remove it by ID. Each row only unties its own tag.
        objetivo = id_ if '<none>' in nombre else nombre
        filas.append({'id': f'docker:imagen:{id_}:{nombre}', 'titulo': nombre, 'descripcion': id_,
                      'categoria': 'docker_detalle', 'consecuencia': 'redescarga',
                      'space': _bytes(i.get('Size', '0B')),
                      'motivo': EN_USO if ocupada else '',
                      'command': '' if ocupada else f'docker image rm {escapar(objetivo)}'})
    df = _docker('system', 'df', '-v', '--format', '{{json .}}')
    try:
        volumenes = json.loads(df).get('Volumes') or [] if df else []
    except json.JSONDecodeError:
        volumenes = []
    for v in volumenes:
        filas.append({'id': f"docker:volumen:{v.get('Name', '')}", 'titulo': v.get('Name', ''),
                      'descripcion': '', 'categoria': 'docker_detalle',
                      'consecuencia': 'solo_lista', 'space': _bytes(v.get('Size', '0B')),
                      'motivo': VOLUMEN, 'command': ''})
    filas.sort(key=lambda f: -f['space'])
    return filas
