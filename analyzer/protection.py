"""Protected-path detection, shared by the CLI, core engine and web backend."""

from pathlib import Path

from analyzer.constants import (
    PROTECTED_PATH_PREFIXES, PROTECTED_APP_MARKERS, PROTECTED_FILENAMES,
    PROTECTED_ROOT_DIRS,
)


def is_protected_path(file_path: str) -> bool:
    """Determina si un archivo es del sistema y no debe borrarse"""
    if any(file_path.startswith(prefix) for prefix in PROTECTED_PATH_PREFIXES):
        return True
    parts = Path(file_path).parts
    if len(parts) >= 2 and '/' + parts[1] in PROTECTED_ROOT_DIRS:
        return True
    if '/Contents/' in file_path and any(m in file_path for m in PROTECTED_APP_MARKERS):
        return True
    if Path(file_path).name in PROTECTED_FILENAMES:
        return True
    return False
