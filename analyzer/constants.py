"""Shared constants for the disk analysis engine.

Moved verbatim from disk_analyzer.py / disk_analyzer_core.py, which used to
define the same values twice. Standard library only.
"""

import platform

# Configuración de tamaños
KB = 1024
MB = KB * 1024
GB = MB * 1024

# Detección del sistema operativo
SYSTEM = platform.system()
IS_WINDOWS = SYSTEM == 'Windows'
IS_MACOS = SYSTEM == 'Darwin'
IS_LINUX = SYSTEM == 'Linux'

# Directorios típicos con archivos temporales o cache por sistema
if IS_WINDOWS:
    CACHE_DIRS = [
        "~/AppData/Local/Temp",
        "~/AppData/Local/Microsoft/Windows/INetCache",
        "~/AppData/Local/Microsoft/Windows/Explorer",
        "~/AppData/Roaming/Code/Cache",
        "~/AppData/Roaming/Code/CachedData",
        "~/AppData/Local/Google/Chrome/User Data/Default/Cache",
        "~/AppData/Local/Mozilla/Firefox/Profiles",
        "~/.npm",
        "~/.cache",
        "~/Downloads",
        "$RECYCLE.BIN",
        "C:/Windows/Temp",
        "~/AppData/Local/Docker",
        "~/.docker",
    ]
elif IS_MACOS:
    CACHE_DIRS = [
        "~/Library/Caches",
        "~/Library/Logs",
        "~/Library/Application Support/Code/Cache",
        "~/Library/Application Support/Code/CachedData",
        "~/Library/Developer/Xcode/DerivedData",
        "~/Library/Developer/Xcode/Archives",
        "~/Library/Developer/CoreSimulator/Devices",
        "~/.npm",
        "~/.cache",
        "~/Downloads",
        "~/.Trash",
        "/private/var/folders",
        "~/Library/Containers/com.docker.docker/Data",
        "~/.docker",
    ]
else:  # Linux
    CACHE_DIRS = [
        "~/.cache",
        "~/.local/share/Trash",
        "/tmp",
        "/var/tmp",
        "~/.config/Code/Cache",
        "~/.config/Code/CachedData",
        "~/.mozilla/firefox",
        "~/.cache/google-chrome",
        "~/.npm",
        "~/Downloads",
        "/var/cache",
        "~/.docker",
        "/var/lib/docker",
    ]

# Extensiones de archivos grandes comunes
LARGE_FILE_EXTENSIONS = {
    '.dmg', '.iso', '.pkg', '.zip', '.rar', '.7z',
    '.mov', '.mp4', '.avi', '.mkv', '.mpg',
    '.psd', '.ai', '.sketch',
    '.vmdk', '.vdi', '.qcow2'
}

# Archivos/carpetas a ignorar
IGNORE_PATTERNS = {
    '.DS_Store', '.localized', 'node_modules', '__pycache__',
    '.git/objects', 'venv', 'env', '.virtualenv', 'Docker.raw'
}

# Volúmenes APFS a excluir en macOS para evitar doble conteo por firmlinks
MACOS_APFS_SKIP_DIRS = {
    '/System/Volumes/Data',
    '/System/Volumes/VM',
    '/System/Volumes/Preboot',
    '/System/Volumes/Update',
    '/System/Volumes/xarts',
    '/System/Volumes/iSCPreboot',
    '/System/Volumes/Hardware',
}

# Prefijos de rutas del sistema que nunca deben tener comandos de borrado
# Estas se comparan con startswith() para evitar falsos positivos por substring
PROTECTED_PATH_PREFIXES = [
    # Volúmenes del sistema macOS
    '/System/Volumes/',
    '/private/var/vm/',
    '/var/vm/',
    # Bibliotecas y frameworks del sistema
    '/System/Library/',
    '/usr/lib/',
    '/usr/bin/',
    '/usr/sbin/',
    '/Library/Updates/',
    '/private/var/folders/',
]

# Prefijos que protegen internos de apps (Contents/ dentro de un .app o .AppBundle)
# pero NO el .app en sí (el usuario puede borrar una app entera)
PROTECTED_APP_MARKERS = ['.app/', '.AppBundle/']

# Nombres de archivo del sistema (match exacto contra el nombre, no la ruta)
PROTECTED_FILENAMES = {'sleepimage', 'swapfile'}

# Rutas raíz del sistema (match exacto de los primeros componentes)
PROTECTED_ROOT_DIRS = {'/bin', '/sbin'}
