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

from analyzer.protection import puede_borrarse

# Rutas que jamás pueden ser el objetivo de un comando generado, por muy
# protegida que esté la lógica que llama aquí. Es la última red, no la primera.
_PROHIBIDAS = {"/", "//", "/.", ""}


def escapar(path: str) -> str:
    """Deja una ruta lista para incrustarse en una línea de shell."""
    return shlex.quote(path)


def _utiles(paths: List[str]) -> List[str]:
    """Limpia la lista y descarta lo que `puede_borrarse` rechace.

    `protection.puede_borrarse` existía desde antes pero nadie fuera de sus
    propios tests la llamaba: una verja de seguridad construida y no
    instalada. Este es el paso obligado de todo comando de borrado que
    genera el motor -- para esquivarla habría que evitar `comandos.py` por
    completo, y ese es justo el módulo que toda regla de generate_recommendations
    y detect_smart_recommendations ya usa para construir sus 'rm -rf'.
    """
    limpias = []
    for p in paths:
        p = (p or "").rstrip("/") if (p or "").rstrip("/") else (p or "")
        if p.strip() in _PROHIBIDAS or not p.strip():
            continue
        if not puede_borrarse(p):
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
