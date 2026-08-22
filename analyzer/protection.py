"""Protected-path detection, shared by the CLI, core engine and web backend."""

import os
from pathlib import Path

from analyzer.constants import (
    PROTECTED_PATH_PREFIXES, PROTECTED_APP_MARKERS, PROTECTED_FILENAMES,
    PROTECTED_ROOT_DIRS, RUTAS_DE_DATOS_DE_USUARIO,
)


def is_protected_path(file_path: str) -> bool:
    """Determina si un archivo es del sistema y no debe borrarse"""
    # APFS no distingue mayúsculas de minúsculas por defecto (sí las
    # conserva): '/bin' y '/BIN' son el mismo directorio. Las cuatro
    # comprobaciones de abajo se hacen sobre la forma en minúsculas para que
    # cambiar la caja no sea una manera de esquivarlas -- normalizar solo
    # amplía lo protegido, nunca lo reduce.
    ruta_cf = file_path.lower()

    # `startswith('/System/Library/')` no cubre '/System/Library' a secas, así
    # que el directorio en sí quedaba desprotegido y solo lo estaba su contenido.
    for prefix in PROTECTED_PATH_PREFIXES:
        prefix_cf = prefix.lower()
        if ruta_cf.startswith(prefix_cf) or ruta_cf == prefix_cf.rstrip('/'):
            return True
    parts = Path(ruta_cf).parts
    if len(parts) >= 2 and '/' + parts[1] in PROTECTED_ROOT_DIRS:
        return True
    if '/contents/' in ruta_cf and any(m.lower() in ruta_cf for m in PROTECTED_APP_MARKERS):
        return True
    if Path(ruta_cf).name in PROTECTED_FILENAMES:
        return True
    return False


def _normalizar(file_path: str):
    """Expande, exige ruta absoluta y resuelve enlaces simbólicos.

    Devuelve `None` si `file_path` no es una ruta absoluta utilizable (vacía,
    solo espacios, o relativa). Se rechaza la ruta relativa ANTES de
    `abspath()`: `abspath()` siempre devuelve algo absoluto anclado al cwd de
    quien llama, así que comprobarlo después sería código muerto que solo
    "funciona" si el cwd cae, por accidente, bajo un prefijo ya prohibido.

    Se resuelven enlaces simbólicos (no solo '..' léxico) porque
    `borrar_contenido` ejecuta `rm -rf <ruta>/*`, y ese glob SÍ atraviesa un
    enlace dentro de un directorio permitido hacia dondequiera que apunte. De
    paso, en macOS esto normaliza /var, /tmp y /etc a su ubicación real bajo
    /private.

    Compartida por `puede_borrarse` y `_coincide_con_permitidas` para que
    ambas apliquen exactamente la misma normalización.
    """
    if not file_path or not file_path.strip():
        return None
    expandida = os.path.expanduser(file_path)
    if not os.path.isabs(expandida):
        return None
    ruta = os.path.realpath(os.path.normpath(os.path.abspath(expandida)))
    if ruta == '/':
        return None
    return ruta


def _coincide_con_permitidas(file_path: str) -> bool:
    """Si `file_path` cae dentro de una de las cachés conocidas y seguras de
    borrar.

    Aislada de `puede_borrarse` a propósito, para poder testear la
    coincidencia en sí. `puede_borrarse` puede devolver `True` por su
    `return True` final aunque esta coincidencia nunca se produzca (por
    ejemplo, si ninguna otra regla bloquea la ruta) -- un test que solo mira
    el resultado de `puede_borrarse` no puede distinguir "es una caché
    conocida" de "no coincidió nada que la prohibiera".
    """
    ruta = _normalizar(file_path)
    if ruta is None:
        return False
    ruta_cf = ruta.lower()

    permitidas = [
        os.path.realpath(os.path.expanduser('~/Library/Caches')),
        os.path.realpath(os.path.expanduser('~/Library/Logs')),
        os.path.realpath(os.path.expanduser('~/.cache')),
        os.path.realpath(os.path.expanduser('~/.npm')),
        os.path.realpath(os.path.expanduser('~/Library/Developer/Xcode/DerivedData')),
        os.path.realpath(os.path.expanduser('~/Library/Application Support/Code/Cache')),
        os.path.realpath(os.path.expanduser('~/Library/Application Support/Code/CachedData')),
        os.path.realpath(os.path.expanduser('~/Library/Containers/com.docker.docker/Data')),
        # El usuario ya decidió tirar esto -- vaciar la papelera es la regla
        # de nivel 1 de generate_recommendations() (id 'papelera').
        os.path.realpath(os.path.expanduser('~/.Trash')),
        # Igual que DerivedData arriba: una ruta con nombre fijo bajo
        # Library/Developer/Xcode, no una clasificación por `type`. No es lo
        # mismo que el bug de cache_types.XCODE que confundía DerivedData con
        # Archives por type -- aquí es detect_smart_recommendations()
        # (id 'xcode_archives_antiguos') apuntando a esta ruta exacta, con su
        # propio umbral de tamaño (>1GB) y descripción honesta sobre qué
        # implica borrarlo.
        os.path.realpath(os.path.expanduser('~/Library/Developer/Xcode/Archives')),
    ]
    return any(ruta_cf == p.lower() or ruta_cf.startswith(p.lower() + '/') for p in permitidas)


def puede_borrarse(file_path: str) -> bool:
    """Si una ruta puede ser objetivo de un borrado automático.

    Distinta de `is_protected_path`, que solo dice "esto es del sistema
    operativo". Aquí la pregunta es la contraria y más estricta: ¿es seguro que
    una herramienta borre esto sin que un humano lo mire? Ante la duda, no.

    Se normaliza antes de comparar porque
    `~/Library/Caches/../../Documents` es `~/Documents` disfrazado.
    """
    ruta = _normalizar(file_path)
    if ruta is None:
        return False

    # APFS no distingue mayúsculas de minúsculas por defecto (sí las
    # conserva): '/Volumes/x' y '/volumes/x' son el mismo directorio. Sin
    # normalizar la caja aquí, cambiar la caja de una ruta prohibida basta
    # para colarla hasta el `return True` final.
    ruta_cf = ruta.lower()

    if is_protected_path(ruta):
        return False

    for cruda in RUTAS_DE_DATOS_DE_USUARIO:
        prohibida = os.path.realpath(os.path.expanduser(cruda))
        # La ruta prohibida en sí, y todo lo que cuelga de ella salvo que una
        # regla más específica lo permita (ver abajo).
        if ruta_cf == prohibida.lower():
            return False

    # Dentro de una zona prohibida solo se salvan las cachés conocidas: eso es
    # lo que convierte esto en whitelist y no en otra lista negra.
    if _coincide_con_permitidas(ruta):
        return True

    for cruda in RUTAS_DE_DATOS_DE_USUARIO:
        prohibida = os.path.realpath(os.path.expanduser(cruda))
        if ruta_cf.startswith(prohibida.lower() + '/'):
            return False

    return True
