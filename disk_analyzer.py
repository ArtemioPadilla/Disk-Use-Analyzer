#!/usr/bin/env python3
"""
Analizador de Disco Multiplataforma
Herramienta para diagnosticar el uso de espacio en disco en Windows, macOS y Linux
"""

import os
import sys
import json
import time
import argparse
import subprocess
import platform
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

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

class DiskAnalyzer:
    def __init__(self, start_path: str, min_size_mb: float = 10):
        self.start_path = Path(start_path).expanduser()
        # Floor at 1 MB to prevent every file being treated as "large"
        self.min_size = max(min_size_mb, 1) * MB
        self.total_scanned = 0
        self.errors = []
        self.cache_locations = []
        self.large_files = []
        self.directory_sizes = defaultdict(int)
        self.file_type_stats = defaultdict(lambda: {'count': 0, 'size': 0})
        self.docker_stats = None
        self.disk_usage = None
        self.system = SYSTEM
        self.is_windows = IS_WINDOWS
        self.is_macos = IS_MACOS
        self.is_linux = IS_LINUX
        
    def format_size(self, size: int) -> str:
        """Formatea el tamaño en formato legible"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"
    
    def get_file_age(self, path: Path) -> int:
        """Obtiene la edad del archivo en días"""
        try:
            mtime = path.stat().st_mtime
            age = (time.time() - mtime) / (24 * 3600)
            return int(age)
        except:
            return -1
    
    def is_cache_or_temp(self, path: Path) -> bool:
        """Determina si es un archivo de cache o temporal"""
        path_str = str(path).lower()
        cache_indicators = ['cache', 'temp', 'tmp', 'log', 'crash', 'diagnostic']
        return any(indicator in path_str for indicator in cache_indicators)
    
    def should_ignore(self, path: Path) -> bool:
        """Determina si el path debe ser ignorado"""
        path_str = str(path)
        # En Windows, ignorar también archivos del sistema
        if self.is_windows:
            if path.name in ['pagefile.sys', 'hiberfil.sys', 'swapfile.sys']:
                return True
        # En macOS, ignorar volúmenes APFS que duplican contenido via firmlinks
        if self.is_macos:
            if path_str in MACOS_APFS_SKIP_DIRS:
                return True
        return any(pattern in path_str for pattern in IGNORE_PATTERNS)
    
    def get_home_dir(self) -> Path:
        """Obtiene el directorio home según el sistema"""
        return Path.home()
    
    def get_all_drives(self) -> List[str]:
        """Obtiene todas las unidades disponibles en el sistema"""
        drives = []
        if self.is_windows:
            # En Windows, buscar todas las letras de unidad
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    drives.append(drive)
        else:
            # En Unix-like, usar el sistema de archivos raíz
            drives.append('/')
        return drives
    
    def get_temp_dirs(self) -> List[Path]:
        """Obtiene directorios temporales según el sistema"""
        temp_dirs = []
        if self.is_windows:
            temp_dirs.extend([
                Path(os.environ.get('TEMP', '')),
                Path(os.environ.get('TMP', '')),
                Path('C:/Windows/Temp'),
            ])
        elif self.is_macos:
            temp_dirs.extend([
                Path('/tmp'),
                Path('/var/tmp'),
                Path('/private/var/folders'),
            ])
        else:  # Linux
            temp_dirs.extend([
                Path('/tmp'),
                Path('/var/tmp'),
            ])
        return [d for d in temp_dirs if d and d.exists()]
    
    def scan_directory(self, directory: Path) -> int:
        """Escanea un directorio y retorna su tamaño total"""
        total_size = 0
        
        try:
            for item in directory.iterdir():
                if self.should_ignore(item):
                    continue
                    
                try:
                    if item.is_file(follow_symlinks=False):
                        # Usar st_blocks * 512 para obtener el espacio real en disco
                        stat = item.stat(follow_symlinks=False)
                        size = stat.st_blocks * 512 if hasattr(stat, 'st_blocks') else stat.st_size
                        total_size += size
                        self.total_scanned += 1
                        
                        # Registrar archivos grandes
                        if size >= self.min_size:
                            file_info = {
                                'path': str(item),
                                'size': size,
                                'age_days': self.get_file_age(item),
                                'extension': item.suffix.lower(),
                                'is_cache': self.is_cache_or_temp(item)
                            }
                            self.large_files.append(file_info)
                        
                        # Estadísticas por tipo de archivo
                        ext = item.suffix.lower() or 'sin_extension'
                        self.file_type_stats[ext]['count'] += 1
                        self.file_type_stats[ext]['size'] += size
                        
                    elif item.is_dir(follow_symlinks=False):
                        # No seguir enlaces simbólicos a directorios
                        if not item.is_symlink():
                            dir_size = self.scan_directory(item)
                            total_size += dir_size
                            self.directory_sizes[str(item)] = dir_size
                        
                except PermissionError:
                    self.errors.append(f"Sin permisos: {item}")
                except Exception as e:
                    self.errors.append(f"Error en {item}: {str(e)}")
                    
        except PermissionError:
            self.errors.append(f"Sin permisos para leer: {directory}")
        except Exception as e:
            self.errors.append(f"Error escaneando {directory}: {str(e)}")
            
        return total_size
    
    def find_cache_locations(self):
        """Busca ubicaciones de cache conocidas"""
        for cache_dir in CACHE_DIRS:
            path = Path(cache_dir).expanduser()
            if path.exists():
                try:
                    size = self.get_directory_size(path)
                    if size > MB:  # Solo reportar si es mayor a 1MB
                        self.cache_locations.append({
                            'path': str(path),
                            'size': size,
                            'type': self.classify_cache(path)
                        })
                except:
                    pass
    
    def classify_cache(self, path: Path) -> str:
        """Clasifica el tipo de cache"""
        path_str = str(path).lower()
        if 'docker' in path_str:
            return 'Docker'
        elif 'xcode' in path_str:
            return 'Xcode Development'
        elif 'code' in path_str or 'vscode' in path_str:
            return 'VS Code'
        elif 'npm' in path_str or 'node' in path_str:
            return 'Node.js/npm'
        elif 'downloads' in path_str:
            return 'Downloads'
        elif 'trash' in path_str:
            return 'Papelera'
        elif 'logs' in path_str:
            return 'Logs del Sistema'
        else:
            return 'Cache General'
    
    def analyze_docker(self):
        """Analiza el uso de espacio de Docker"""
        print("🐳 Analizando Docker...")
        docker_stats = {
            'available': False,
            'images': {'count': 0, 'size': 0, 'unused': 0},
            'containers': {'count': 0, 'size': 0, 'stopped': 0},
            'volumes': {'count': 0, 'size': 0, 'unused': 0},
            'build_cache': {'size': 0},
            'total_size': 0,
            'reclaimable': 0
        }
        
        try:
            # Verificar si Docker está instalado
            docker_cmd = 'docker'
            if self.is_windows:
                # En Windows, Docker puede estar en diferentes ubicaciones
                if shutil.which('docker') is None:
                    # Intentar con Docker Desktop
                    docker_desktop_path = 'C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe'
                    if os.path.exists(docker_desktop_path):
                        docker_cmd = docker_desktop_path
                    else:
                        return docker_stats
            
            result = subprocess.run([docker_cmd, 'version'], capture_output=True, text=True)
            if result.returncode != 0:
                return docker_stats
                
            docker_stats['available'] = True
            
            # Obtener información del sistema Docker
            result = subprocess.run(['docker', 'system', 'df'], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # Saltar header
                    if line.startswith('Images'):
                        parts = line.split()
                        docker_stats['images']['size'] = self.parse_docker_size(parts[3])
                        docker_stats['images']['reclaimable'] = self.parse_docker_size(parts[4])
                    elif line.startswith('Containers'):
                        parts = line.split()
                        docker_stats['containers']['size'] = self.parse_docker_size(parts[3])
                        docker_stats['containers']['reclaimable'] = self.parse_docker_size(parts[4])
                    elif line.startswith('Local Volumes'):
                        parts = line.split()
                        docker_stats['volumes']['size'] = self.parse_docker_size(parts[4])
                        docker_stats['volumes']['reclaimable'] = self.parse_docker_size(parts[5])
                    elif line.startswith('Build Cache'):
                        parts = line.split()
                        docker_stats['build_cache']['size'] = self.parse_docker_size(parts[3])
                        docker_stats['build_cache']['reclaimable'] = self.parse_docker_size(parts[4])
            
            # Contar imágenes
            result = subprocess.run(['docker', 'images', '-q'], capture_output=True, text=True)
            if result.returncode == 0:
                docker_stats['images']['count'] = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
            
            # Contar contenedores
            result = subprocess.run(['docker', 'ps', '-aq'], capture_output=True, text=True)
            if result.returncode == 0:
                docker_stats['containers']['count'] = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
            
            # Contar contenedores detenidos
            result = subprocess.run(['docker', 'ps', '-aq', '-f', 'status=exited'], capture_output=True, text=True)
            if result.returncode == 0:
                docker_stats['containers']['stopped'] = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
            
            # Contar volúmenes
            result = subprocess.run(['docker', 'volume', 'ls', '-q'], capture_output=True, text=True)
            if result.returncode == 0:
                docker_stats['volumes']['count'] = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
            
            # Calcular totales
            docker_stats['total_size'] = (
                docker_stats['images']['size'] +
                docker_stats['containers']['size'] +
                docker_stats['volumes']['size'] +
                docker_stats['build_cache']['size']
            )
            
            docker_stats['reclaimable'] = (
                docker_stats['images'].get('reclaimable', 0) +
                docker_stats['containers'].get('reclaimable', 0) +
                docker_stats['volumes'].get('reclaimable', 0) +
                docker_stats['build_cache'].get('reclaimable', 0)
            )
            
        except FileNotFoundError:
            print("   ⚠️  Docker no está instalado o no está en el PATH")
        except Exception as e:
            print(f"   ⚠️  Error analizando Docker: {e}")
            
        self.docker_stats = docker_stats
        return docker_stats
    
    def parse_docker_size(self, size_str: str) -> int:
        """Convierte el formato de tamaño de Docker a bytes"""
        size_str = size_str.strip()
        if size_str == '0B':
            return 0
            
        # Remover paréntesis y porcentajes si existen
        size_str = size_str.replace('(', '').replace(')', '').replace('%', '')
        
        try:
            # Buscar número y unidad usando regex
            import re
            match = re.match(r'([\d.]+)([KMGT]?B)', size_str)
            if match:
                number = float(match.group(1))
                unit = match.group(2)
                
                if unit == 'B':
                    return int(number)
                elif unit == 'KB':
                    return int(number * KB)
                elif unit == 'MB':
                    return int(number * MB)
                elif unit == 'GB':
                    return int(number * GB)
                elif unit == 'TB':
                    return int(number * GB * 1024)
            else:
                # Intento alternativo sin regex
                if 'TB' in size_str:
                    number = float(size_str.replace('TB', '').strip())
                    return int(number * GB * 1024)
                elif 'GB' in size_str:
                    number = float(size_str.replace('GB', '').strip())
                    return int(number * GB)
                elif 'MB' in size_str:
                    number = float(size_str.replace('MB', '').strip())
                    return int(number * MB)
                elif 'kB' in size_str or 'KB' in size_str:
                    # Manejar tanto kB como KB
                    number = float(size_str.replace('kB', '').replace('KB', '').strip())
                    return int(number * KB)
                else:
                    return int(float(size_str.replace('B', '').strip()))
        except Exception as e:
            print(f"   ⚠️  Error parsing Docker size '{size_str}': {e}")
            return 0
        return 0
    
    def get_directory_size(self, path: Path) -> int:
        """Obtiene el tamaño de un directorio usando du"""
        try:
            # du -sk es POSIX (macOS + Linux), du -sb es solo GNU/Linux
            result = subprocess.run(
                ['du', '-sk', str(path)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.split()[0]) * 1024
        except:
            pass
        return 0
    
    def get_disk_usage(self, path: Optional[str] = None) -> Dict:
        """Obtiene el uso total del disco de forma multiplataforma"""
        try:
            if path is None:
                path = str(self.start_path)
            
            if self.is_windows:
                # En Windows, usar shutil.disk_usage
                import shutil
                usage = shutil.disk_usage(path)
                return {
                    'total': usage.total,
                    'used': usage.used,
                    'available': usage.free,
                    'percent': (usage.used / usage.total * 100) if usage.total > 0 else 0
                }
            else:
                # En Unix-like, usar df
                result = subprocess.run(['df', '-k', path], capture_output=True, text=True)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        parts = lines[1].split()
                        if len(parts) >= 4:
                            # df -k returns values in 1K blocks
                            total = int(parts[1]) * 1024
                            available = int(parts[3]) * 1024
                            # Calculate used as total - available for accurate APFS reporting
                            used = total - available
                            return {
                                'total': total,
                                'used': used,
                                'available': available,
                                'percent': (used / total * 100) if total > 0 else 0
                            }
        except Exception as e:
            self.errors.append(f"Error obteniendo uso del disco: {str(e)}")
        return {'total': 0, 'used': 0, 'available': 0, 'percent': 0}
    
    def estimate_skipped_apfs_volumes(self) -> int:
        """Estima el tamaño de los volúmenes APFS excluidos usando diskutil.
        Solo cuenta volúmenes de sistema (VM, Preboot, Recovery, System, Update),
        NO el volumen Data ya que su contenido se accede via firmlinks."""
        if not self.is_macos:
            return 0
        import re
        total = 0
        system_roles = {'VM', 'Preboot', 'Recovery', 'System', 'Update'}
        try:
            result = subprocess.run(
                ['diskutil', 'apfs', 'list'],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                current_role = None
                for line in result.stdout.split('\n'):
                    # Match role: "APFS Volume Disk (Role):  disk3s6 (VM)"
                    role_match = re.search(r'\(Role\):\s+\S+\s+\((\w+)\)', line)
                    if not role_match:
                        role_match = re.search(r'Role:\s+\S+\s+\((\w+)\)', line)
                    if role_match:
                        current_role = role_match.group(1)
                    # Match capacity: "Capacity Consumed:  35714965504 B (35.7 GB)"
                    elif 'Capacity Consumed' in line and current_role in system_roles:
                        cap_match = re.search(r'Capacity Consumed:\s+(\d+)\s+B', line)
                        if cap_match:
                            total += int(cap_match.group(1))
                        current_role = None
        except Exception:
            pass
        return total

    def analyze(self):
        """Ejecuta el análisis completo"""
        print(f"🔍 Iniciando análisis de: {self.start_path}")
        print("⏳ Este proceso puede tomar varios minutos...\n")
        
        start_time = time.time()
        
        # Obtener uso del disco
        self.disk_usage = self.get_disk_usage()
        
        # Escanear directorio principal
        total_size = self.scan_directory(self.start_path)
        self.directory_sizes[str(self.start_path)] = total_size
        
        # Buscar ubicaciones de cache
        print("🔍 Buscando archivos de cache y temporales...")
        self.find_cache_locations()
        
        # Analizar Docker
        self.analyze_docker()

        # Estimar tamaño de volúmenes APFS excluidos
        self.skipped_volumes_size = self.estimate_skipped_apfs_volumes()

        elapsed_time = time.time() - start_time

        return {
            'total_size': total_size,
            'elapsed_time': elapsed_time,
            'files_scanned': self.total_scanned
        }
    
    def is_protected_path(self, file_path: str) -> bool:
        """Determina si un archivo es del sistema y no debe borrarse"""
        # Prefijos de rutas del sistema
        if any(file_path.startswith(prefix) for prefix in PROTECTED_PATH_PREFIXES):
            return True
        # Rutas raíz del sistema (/bin, /sbin - no /Users/robin/)
        parts = Path(file_path).parts
        if len(parts) >= 2 and '/' + parts[1] in PROTECTED_ROOT_DIRS:
            return True
        # Internos de aplicaciones (.app/Contents/... o .AppBundle/Contents/...)
        if '/Contents/' in file_path and any(m in file_path for m in PROTECTED_APP_MARKERS):
            return True
        # Nombres de archivo del sistema (match exacto)
        if Path(file_path).name in PROTECTED_FILENAMES:
            return True
        return False

    def _categorize_path(self, dir_path: str) -> str:
        """Asigna una categoría a un directorio basado en su ruta"""
        if '/Applications' in dir_path:
            return 'Applications'
        if '/Library' in dir_path and '/Caches' not in dir_path:
            return 'Library'
        if '/Documents' in dir_path and not any(x in dir_path for x in ['/repos', '/Developer']):
            return 'Documents'
        if '/Downloads' in dir_path:
            return 'Downloads'
        if any(docker in dir_path for docker in ['/.docker', '/Docker', '/Containers/com.docker']):
            return 'Docker'
        if any(dev in dir_path for dev in ['/Developer', '/repos', '/.npm', '/node_modules', '/.continue', '/venv', '/.cargo', '/.rustup']):
            return 'Desarrollo'
        if any(cache in dir_path.lower() for cache in ['/cache', '/caches', '/tmp', '/temp', '/logs']):
            return 'Cache'
        if any(media in dir_path for media in ['/Pictures', '/Movies', '/Music', '/Photos Library']):
            return 'Media'
        if 'Mobile Documents' in dir_path or 'CloudDocs' in dir_path:
            return 'iCloud'
        return 'Otros'

    def generate_delete_command(self, file_path: str) -> str:
        """Genera comando seguro para borrar un archivo"""
        if self.is_protected_path(file_path):
            return f"# ⚠️ ARCHIVO DEL SISTEMA - NO BORRAR: {Path(file_path).name}"
        # Escapar caracteres especiales en la ruta
        escaped_path = file_path.replace("'", "'\"'\"'")
        return f"rm -f '{escaped_path}'"
    
    def generate_recommendations(self) -> List[Dict]:
        """Genera recomendaciones basadas en el análisis"""
        recommendations = []
        
        # Recomendación de Docker
        if self.docker_stats and self.docker_stats['available'] and self.docker_stats['reclaimable'] > 100 * MB:
            recommendations.append({
                'priority': 'Alta',
                'type': 'Docker',
                'description': f'Docker está usando {self.format_size(self.docker_stats["total_size"])} con {self.format_size(self.docker_stats["reclaimable"])} recuperable',
                'action': 'Ejecuta "docker system prune -a" para limpiar imágenes, contenedores y volúmenes no utilizados',
                'space': self.docker_stats['reclaimable'],
                'command': 'docker system prune -a --volumes -f'
            })
        
        # Recomendación de cache — solo caches verdaderamente seguros de limpiar
        # Excluir Docker (tiene su propia recomendación), Cache General (puede ser
        # ~/.cache con modelos ML o CoreSimulator/Devices que no son caches)
        safe_cache_types = {'Logs del Sistema', 'VS Code', 'Xcode Development',
                            'Node.js/npm', 'Papelera'}
        safe_caches = [loc for loc in self.cache_locations if loc['type'] in safe_cache_types]

        safe_cache_size = sum(loc['size'] for loc in safe_caches)
        if safe_cache_size > 100 * MB:
            cache_commands = [f"rm -rf '{loc['path']}/*'" for loc in safe_caches[:3]]
            recommendations.append({
                'priority': 'Media',
                'type': 'Cache del Sistema',
                'description': f'Puedes liberar {self.format_size(safe_cache_size)} de cache seguro de limpiar',
                'action': 'Ejecuta el script con --clean-cache para limpiar automáticamente',
                'space': safe_cache_size,
                'command': ' && '.join(cache_commands) if cache_commands else 'make clean-cache'
            })
        
        # Downloads antiguos
        old_downloads = [
            f for f in self.large_files
            if 'downloads' in f['path'].lower() and f['age_days'] > 30
        ]
        if old_downloads:
            size = sum(f['size'] for f in old_downloads)
            recommendations.append({
                'priority': 'Media',
                'type': 'Descargas Antiguas',
                'description': f'Tienes {len(old_downloads)} archivos en Downloads con más de 30 días',
                'action': 'Revisa y elimina descargas que ya no necesites',
                'space': size,
                'command': f"# Listar primero: find ~/Downloads -mtime +30 -size +{int(self.min_size/MB)}M -type f -ls"
            })
        
        # Archivos muy grandes
        huge_files = [f for f in self.large_files if f['size'] > GB]
        if huge_files:
            recommendations.append({
                'priority': 'Media',
                'type': 'Archivos Gigantes',
                'description': f'Encontré {len(huge_files)} archivos de más de 1GB',
                'action': 'Considera mover estos archivos a un disco externo',
                'space': sum(f['size'] for f in huge_files),
                'command': '# Revisa manualmente estos archivos antes de borrar'
            })
        
        # Archivos de desarrollo
        dev_files = [
            f for f in self.large_files
            if any(ext in f['extension'] for ext in ['.vmdk', '.vdi', '.qcow2'])
        ]
        if dev_files:
            size = sum(f['size'] for f in dev_files)
            recommendations.append({
                'priority': 'Baja',
                'type': 'Máquinas Virtuales',
                'description': f'Tienes {len(dev_files)} archivos de máquinas virtuales',
                'action': 'Elimina VMs que ya no uses o muévelas a almacenamiento externo',
                'space': size,
                'command': '# Lista VMs: find . -name "*.vmdk" -o -name "*.vdi" -size +1G'
            })

        # Homebrew caches
        brew_files = [
            f for f in self.large_files
            if 'Homebrew/downloads' in f['path']
        ]
        if brew_files:
            size = sum(f['size'] for f in brew_files)
            recommendations.append({
                'priority': 'Alta',
                'type': 'Cache de Homebrew',
                'description': f'{len(brew_files)} descargas de Homebrew ocupan {self.format_size(size)}',
                'action': 'Limpia el cache de Homebrew de forma segura',
                'space': size,
                'command': 'brew cleanup --prune=all'
            })

        # Simulator caches
        sim_files = [
            f for f in self.large_files
            if 'CoreSimulator' in f['path'] and not self.is_protected_path(f['path'])
        ]
        if sim_files:
            size = sum(f['size'] for f in sim_files)
            recommendations.append({
                'priority': 'Media',
                'type': 'Cache de Simuladores iOS',
                'description': f'{len(sim_files)} archivos de cache de simuladores ({self.format_size(size)})',
                'action': 'Limpia caches de simuladores antiguos (se regeneran al usar Xcode)',
                'space': size,
                'command': 'xcrun simctl delete unavailable && rm -rf ~/Library/Developer/CoreSimulator/Caches/'
            })

        return sorted(recommendations, key=lambda x: x['space'], reverse=True)
    
    def generate_report(self) -> Dict:
        """Genera el reporte completo"""
        # Ordenar archivos grandes por tamaño
        self.large_files.sort(key=lambda x: x['size'], reverse=True)
        
        # Ordenar directorios por tamaño
        sorted_dirs = sorted(
            self.directory_sizes.items(),
            key=lambda x: x[1],
            reverse=True
        )[:100]  # Top 100 directorios (usado por Sankey y categorización)
        
        # Ordenar tipos de archivo por tamaño total
        sorted_file_types = sorted(
            self.file_type_stats.items(),
            key=lambda x: x[1]['size'],
            reverse=True
        )[:15]  # Top 15 tipos
        
        # Calcular espacio recuperable — solo caches seguros de limpiar
        # No incluir Docker (requiere docker prune), ni Cache General (puede ser ~/.cache con modelos ML)
        safe_recovery_types = {'Logs del Sistema', 'VS Code', 'Xcode Development',
                               'Node.js/npm', 'Papelera', 'Downloads'}
        recoverable_space = sum(
            loc['size'] for loc in self.cache_locations
            if loc['type'] in safe_recovery_types
        )
        old_downloads = sum(
            f['size'] for f in self.large_files
            if 'downloads' in f['path'].lower() and f['age_days'] > 30
        )
        # Homebrew caches
        recoverable_space += sum(
            f['size'] for f in self.large_files
            if 'Homebrew/downloads' in f['path']
        )
        # Simulator caches (non-protected)
        recoverable_space += sum(
            f['size'] for f in self.large_files
            if 'CoreSimulator' in f['path'] and not self.is_protected_path(f['path'])
        )

        # Agregar espacio recuperable de Docker
        if self.docker_stats and self.docker_stats['available']:
            recoverable_space += self.docker_stats['reclaimable']
        
        report = {
            'summary': {
                'total_size': self.directory_sizes.get(str(self.start_path), 0),
                'files_scanned': self.total_scanned,
                'large_files_count': len(self.large_files),
                'recoverable_space': recoverable_space + old_downloads,
                'cache_space': recoverable_space,
                'old_downloads_space': old_downloads,
                'docker_space': self.docker_stats['total_size'] if self.docker_stats else 0,
                'docker_reclaimable': self.docker_stats['reclaimable'] if self.docker_stats else 0
            },
            'top_directories': sorted_dirs,
            'top_file_types': sorted_file_types,
            'large_files': self.large_files[:50],  # Top 50 archivos
            'cache_locations': sorted(self.cache_locations, key=lambda x: x['size'], reverse=True),
            'docker': self.docker_stats,
            'recommendations': self.generate_recommendations(),
            'errors': self.errors[:10],  # Primeros 10 errores
            'delete_commands': self._generate_delete_commands(self.large_files[:50]),
            'disk_usage': self.disk_usage,
            'skipped_volumes_size': getattr(self, 'skipped_volumes_size', 0)
        }
        
        return report
    
    def _generate_delete_commands(self, files: List[Dict]) -> Dict:
        """Genera comandos de borrado para archivos"""
        commands = {
            'cache_files': [],
            'old_downloads': [],
            'large_files': [],
            'all_files': []
        }
        
        for f in files:
            cmd = self.generate_delete_command(f['path'])
            commands['all_files'].append(cmd)
            
            if f['is_cache']:
                commands['cache_files'].append(cmd)
            
            if 'downloads' in f['path'].lower() and f['age_days'] > 30:
                commands['old_downloads'].append(cmd)
            
            if f['size'] > GB:
                commands['large_files'].append(cmd)
        
        return commands
    
    def print_report(self, report: Dict):
        """Imprime el reporte de manera formateada"""
        print("\n" + "="*60)
        print("📊 REPORTE DE ANÁLISIS DE DISCO")
        print("="*60)
        
        # Resumen
        summary = report['summary']
        print(f"\n📈 RESUMEN:")
        print(f"   • Espacio total analizado: {self.format_size(summary['total_size'])}")
        print(f"   • Archivos escaneados: {summary['files_scanned']:,}")
        print(f"   • Archivos grandes encontrados: {summary['large_files_count']}")
        print(f"   • Espacio recuperable estimado: {self.format_size(summary['recoverable_space'])}")
        
        # Docker stats si está disponible
        if report['docker'] and report['docker']['available']:
            print(f"\n🐳 DOCKER:")
            docker = report['docker']
            print(f"   • Espacio total usado: {self.format_size(docker['total_size'])}")
            print(f"   • Espacio recuperable: {self.format_size(docker['reclaimable'])}")
            print(f"   • Imágenes: {docker['images']['count']} ({self.format_size(docker['images']['size'])})")
            print(f"   • Contenedores: {docker['containers']['count']} ({docker['containers']['stopped']} detenidos)")
            print(f"   • Volúmenes: {docker['volumes']['count']} ({self.format_size(docker['volumes']['size'])})")
            print(f"   • Build cache: {self.format_size(docker['build_cache']['size'])}")
        
        # Recomendaciones
        if report['recommendations']:
            print(f"\n💡 RECOMENDACIONES PRINCIPALES:")
            for i, rec in enumerate(report['recommendations'][:5], 1):
                print(f"\n   {i}. [{rec['priority']}] {rec['type']}")
                print(f"      {rec['description']}")
                print(f"      → {rec['action']}")
                print(f"      Espacio recuperable: {self.format_size(rec['space'])}")
                if 'command' in rec and rec['command']:
                    print(f"      📝 Comando: {rec['command']}")
        
        # Top directorios
        print(f"\n📁 TOP 10 DIRECTORIOS MÁS GRANDES:")
        for path, size in report['top_directories'][:10]:
            if str(self.start_path) == '/':
                rel_path = path
            else:
                rel_path = path.replace(str(self.start_path), '.', 1)
            print(f"   {self.format_size(size):>10} - {rel_path}")
        
        # Top tipos de archivo
        print(f"\n📄 TIPOS DE ARCHIVO POR ESPACIO:")
        for ext, stats in report['top_file_types'][:10]:
            print(f"   {self.format_size(stats['size']):>10} - {ext} ({stats['count']} archivos)")
        
        # Archivos más grandes con comandos de borrado
        print(f"\n🗂️  TOP 10 ARCHIVOS MÁS GRANDES:")
        print(f"   {'Tamaño':>12} {'Edad':>10} {'Archivo':<50}")
        print(f"   {'-'*12} {'-'*10} {'-'*50}")
        for f in report['large_files'][:10]:
            age = f"{f['age_days']}d" if f['age_days'] >= 0 else "N/A"
            cache_mark = "🔥" if f['is_cache'] else "  "
            name = Path(f['path']).name[:47] + "..." if len(Path(f['path']).name) > 50 else Path(f['path']).name
            print(f"   {cache_mark} {self.format_size(f['size']):>10} {age:>10} {name:<50}")
            
        # Comandos de borrado sugeridos
        print(f"\n🗑️  COMANDOS DE LIMPIEZA SUGERIDOS:")
        print(f"   # PRECAUCIÓN: Revisa los archivos antes de ejecutar estos comandos")
        
        # Comando para archivos de cache
        cache_files = [f for f in report['large_files'][:20] if f['is_cache']]
        if cache_files:
            print(f"\n   # Limpiar archivos de cache grandes ({len(cache_files)} archivos)")
            for f in cache_files[:5]:
                print(f"   rm -f '{f['path']}'")
            if len(cache_files) > 5:
                print(f"   # ... y {len(cache_files) - 5} archivos más de cache")
        
        # Ubicaciones de cache
        if report['cache_locations']:
            print(f"\n🗑️  UBICACIONES DE CACHE:")
            for loc in report['cache_locations'][:10]:
                print(f"   {self.format_size(loc['size']):>10} - {loc['type']}")
                print(f"                    {loc['path']}")
        
        print("\n" + "="*60)
        print("✅ Análisis completado")
        print("="*60)

        # Aviso de sudo solo si hay errores de permisos reales y se escaneó una porción
        # significativa del disco (>25% del espacio usado). No mostrar cuando se
        # analiza un subdirectorio pequeño como ~/Documents.
        perm_errors = [e for e in self.errors if 'permisos' in e.lower()]
        if self.disk_usage and os.geteuid() != 0 and perm_errors:
            skipped = getattr(self, 'skipped_volumes_size', 0)
            accounted = report['summary']['total_size'] + skipped
            gap = self.disk_usage['used'] - accounted
            scan_coverage = accounted / self.disk_usage['used'] if self.disk_usage['used'] > 0 else 0
            if gap > 10 * GB and scan_coverage > 0.25:
                print(f"\n💡 {self.format_size(int(gap))} no se pudieron analizar por falta de permisos.")
                print("   Para un análisis completo: sudo make full path=/ min_size={int(self.min_size/MB)}")
    
    def export_json(self, report: Dict, filename: str):
        """Exporta el reporte a JSON"""
        # Agregar comandos de borrado al reporte JSON
        enhanced_report = report.copy()
        enhanced_report['generated_at'] = datetime.now().isoformat()
        enhanced_report['analyzer_version'] = '1.0.0'
        
        with open(filename, 'w') as f:
            json.dump(enhanced_report, f, indent=2, default=str)
        print(f"\n📄 Reporte detallado exportado a: {filename}")
    
    def export_html(self, report: Dict, filename: str):
        """Exporta el reporte a HTML interactivo"""
        html_content = self.generate_html_report(report)
        with open(filename, 'w') as f:
            f.write(html_content)
        print(f"\n🌐 Reporte HTML exportado a: {filename}")
    
    def generate_html_report(self, report: Dict) -> str:
        """Genera un reporte HTML hermoso e interactivo con todas las funcionalidades"""
        summary = report['summary']
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Preparar datos para los diagramas Sankey (general y por categoría)
        all_sankey_data = self._prepare_sankey_data_by_category(report)
        
        # Preparar datos para otros gráficos
        file_type_data = [
            {"type": ext, "size": stats['size'], "count": stats['count']} 
            for ext, stats in report['top_file_types'][:10]
        ]
        
        # Datos para timeline de archivos por edad
        age_distribution = defaultdict(lambda: {'count': 0, 'size': 0})
        for f in report['large_files']:
            if f['age_days'] >= 0:
                if f['age_days'] < 7:
                    age_key = '< 1 semana'
                elif f['age_days'] < 30:
                    age_key = '1-4 semanas'
                elif f['age_days'] < 90:
                    age_key = '1-3 meses'
                elif f['age_days'] < 365:
                    age_key = '3-12 meses'
                else:
                    age_key = '> 1 año'
                age_distribution[age_key]['count'] += 1
                age_distribution[age_key]['size'] += f['size']
        
        # Preparar archivos para la tabla interactiva
        files_data = []
        for i, f in enumerate(report['large_files'][:50]):
            protected = self.is_protected_path(f['path'])
            files_data.append({
                'id': i,
                'name': Path(f['path']).name,
                'path': f['path'],
                'size': f['size'],
                'size_formatted': self.format_size(f['size']),
                'age_days': f['age_days'],
                'extension': f['extension'],
                'is_cache': f['is_cache'],
                'is_protected': protected,
                'delete_cmd': self.generate_delete_command(f['path'])
            })
        
        # Generar HTML
        html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Disk Analyzer Dashboard - {timestamp}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        :root {{
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --secondary: #8b5cf6;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --dark: #1f2937;
            --light: #f9fafb;
            --gray: #6b7280;
            --border: #e5e7eb;
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif;
            background: var(--light);
            color: var(--dark);
            line-height: 1.6;
        }}
        
        .container {{ max-width: 1400px; margin: 0 auto; padding: 2rem; }}
        
        .header {{ text-align: center; margin-bottom: 3rem; }}
        .header h1 {{ font-size: 2.5rem; font-weight: 700; color: var(--dark); margin-bottom: 0.5rem; }}
        .header p {{ color: var(--gray); font-size: 1.1rem; }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }}
        
        .stat-card {{
            background: white;
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
            border: 1px solid var(--border);
        }}
        
        .stat-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        
        .stat-card .icon {{
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            margin-bottom: 1rem;
        }}
        
        .stat-card.primary .icon {{ background: rgba(99, 102, 241, 0.1); color: var(--primary); }}
        .stat-card.success .icon {{ background: rgba(16, 185, 129, 0.1); color: var(--success); }}
        .stat-card.warning .icon {{ background: rgba(245, 158, 11, 0.1); color: var(--warning); }}
        .stat-card.danger .icon {{ background: rgba(239, 68, 68, 0.1); color: var(--danger); }}
        
        .stat-card .value {{ font-size: 2rem; font-weight: 700; color: var(--dark); margin-bottom: 0.25rem; }}
        .stat-card .label {{ color: var(--gray); font-size: 0.875rem; font-weight: 500; }}
        
        .dashboard-grid {{
            display: grid;
            grid-template-columns: repeat(12, 1fr);
            gap: 1.5rem;
            margin-bottom: 3rem;
        }}
        
        .card {{
            background: white;
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border: 1px solid var(--border);
        }}
        
        .card h2 {{
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--dark);
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        .col-span-4 {{ grid-column: span 4; }}
        .col-span-6 {{ grid-column: span 6; }}
        .col-span-8 {{ grid-column: span 8; }}
        .col-span-12 {{ grid-column: span 12; }}
        
        .chart-container {{ position: relative; height: 300px; }}
        .chart-container.small {{ height: 200px; }}
        .chart-container.large {{ height: 500px; }}
        
        #sankeyChart {{ width: 100%; height: 500px; }}
        
        .recommendation {{
            background: var(--light);
            border-radius: 12px;
            padding: 1rem;
            margin-bottom: 1rem;
            border: 1px solid var(--border);
            transition: all 0.2s ease;
        }}
        
        .recommendation:hover {{
            border-color: var(--primary);
            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.1);
        }}
        
        .recommendation .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.5rem;
        }}
        
        .priority {{
            padding: 0.25rem 0.75rem;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        
        .priority.alta {{ background: rgba(239, 68, 68, 0.1); color: var(--danger); }}
        .priority.media {{ background: rgba(245, 158, 11, 0.1); color: var(--warning); }}
        .priority.baja {{ background: rgba(16, 185, 129, 0.1); color: var(--success); }}
        
        .command-box {{
            background: var(--dark);
            color: white;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.875rem;
            margin-top: 0.5rem;
            position: relative;
            overflow-x: auto;
        }}
        
        .copy-btn {{
            position: absolute;
            right: 0.5rem;
            top: 50%;
            transform: translateY(-50%);
            background: var(--primary);
            color: white;
            border: none;
            padding: 0.25rem 0.75rem;
            border-radius: 6px;
            font-size: 0.75rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        
        .copy-btn:hover {{ background: var(--primary-dark); }}
        
        .file-table {{ width: 100%; border-collapse: collapse; }}
        .file-table th {{
            background: var(--light);
            padding: 0.75rem;
            text-align: left;
            font-weight: 600;
            color: var(--gray);
            font-size: 0.875rem;
            border-bottom: 2px solid var(--border);
        }}
        .file-table td {{ padding: 0.75rem; border-bottom: 1px solid var(--border); }}
        .file-table tr:hover {{ background: var(--light); }}
        
        .checkbox {{ width: 1.25rem; height: 1.25rem; cursor: pointer; }}
        .file-name {{ font-weight: 500; color: var(--dark); }}
        .file-path {{ font-size: 0.75rem; color: var(--gray); margin-top: 0.25rem; }}
        
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        
        .badge.cache {{ background: rgba(239, 68, 68, 0.1); color: var(--danger); }}
        
        .action-bar {{
            position: sticky;
            bottom: 0;
            background: white;
            border-top: 2px solid var(--border);
            padding: 1rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            box-shadow: 0 -4px 12px rgba(0,0,0,0.1);
        }}
        
        .btn {{
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease;
            font-size: 0.875rem;
        }}
        
        .btn-primary {{ background: var(--primary); color: white; }}
        .btn-primary:hover {{ background: var(--primary-dark); }}
        .btn-danger {{ background: var(--danger); color: white; }}
        .btn-danger:hover {{ background: #dc2626; }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        
        #selectedCount {{ font-weight: 600; color: var(--dark); }}
        #selectedSize {{ color: var(--primary); font-weight: 700; }}
        
        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }}
        
        .modal-content {{
            background: white;
            border-radius: 16px;
            padding: 2rem;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }}
        
        /* Estilos para pestañas */
        .tab-button.active {{
            color: var(--primary) !important;
            border-bottom-color: var(--primary) !important;
        }}
        
        .tab-button:hover {{
            color: var(--primary-dark);
            background: rgba(99, 102, 241, 0.05);
        }}
        
        .sankey-panel {{
            animation: fadeIn 0.3s ease;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
        
        .modal-header {{ margin-bottom: 1.5rem; }}
        .modal-header h3 {{ font-size: 1.5rem; font-weight: 700; color: var(--dark); }}
        
        .disk-usage-bar {{
            width: 100%;
            height: 40px;
            background: #e5e7eb;
            border-radius: 20px;
            overflow: hidden;
            margin: 1rem 0;
            position: relative;
        }}
        
        .disk-usage-fill {{
            height: 100%;
            background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%);
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            transition: width 0.3s ease;
        }}
        
        @media (max-width: 768px) {{
            .dashboard-grid {{ grid-template-columns: 1fr; }}
            .col-span-4, .col-span-6, .col-span-8 {{ grid-column: span 1; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💾 Disk Analyzer Dashboard</h1>
            <p>Análisis realizado el {timestamp}</p>
        </div>'''
        
        # Agregar barra de uso del disco si está disponible
        if report.get('disk_usage') and report['disk_usage']['total'] > 0:
            disk_usage = report['disk_usage']
            percent_used = (disk_usage['used'] / disk_usage['total'] * 100)
            
            # Preparar datos de categorías para la barra segmentada
            categories = []
            colors = {
                'Applications': '#6366f1',
                'Library': '#8b5cf6', 
                'Documents': '#10b981',
                'Downloads': '#f59e0b',
                'Docker': '#ef4444',
                'Desarrollo': '#ec4899',
                'Cache': '#f97316',
                'Media': '#06b6d4',
                'iCloud': '#3b82f6',
                'Otros': '#6b7280',
                'Sin analizar': '#e5e7eb',
                'Libre': '#f3f4f6'
            }
            
            # Calcular tamaños por categoría usando solo hijos directos de start_path
            # para evitar doble conteo de directorios anidados.
            # Para directorios "contenedor" como /Users o /Users/username que no
            # aportan categorización útil, reemplazarlos por sus hijos.
            category_sizes = {}
            analyzed_total = summary.get('total_size', 0)

            # Obtener hijos directos del directorio analizado
            start_path_str = str(self.start_path)
            direct_children = {}
            for dir_path, size in self.directory_sizes.items():
                parent = str(Path(dir_path).parent)
                if parent == start_path_str and dir_path != start_path_str:
                    direct_children[dir_path] = size

            # Expandir directorios "contenedor" que se categorizan como Otros
            # pero tienen hijos con categorías más útiles (ej: /Users -> /Users/me/Library)
            expanded = {}
            for dir_path, size in direct_children.items():
                if self._categorize_path(dir_path) == 'Otros':
                    # Buscar hijos de este directorio para categorizar mejor
                    children_found = {}
                    children_total = 0
                    for sub_path, sub_size in self.directory_sizes.items():
                        sub_parent = str(Path(sub_path).parent)
                        if sub_parent == dir_path:
                            children_found[sub_path] = sub_size
                            children_total += sub_size
                    if children_found:
                        for child_path, child_size in children_found.items():
                            # Recursivamente expandir (ej: /Users -> /Users/me -> /Users/me/Library)
                            if self._categorize_path(child_path) == 'Otros':
                                grandchildren = {}
                                for gp, gs in self.directory_sizes.items():
                                    if str(Path(gp).parent) == child_path:
                                        grandchildren[gp] = gs
                                if grandchildren:
                                    for gp, gs in grandchildren.items():
                                        expanded[gp] = gs
                                    # Espacio de archivos sueltos en el directorio hijo
                                    gc_total = sum(grandchildren.values())
                                    if child_size > gc_total:
                                        expanded[child_path + '/_files'] = child_size - gc_total
                                else:
                                    expanded[child_path] = child_size
                            else:
                                expanded[child_path] = child_size
                        # Espacio de archivos sueltos en el directorio padre
                        if size > children_total:
                            expanded[dir_path + '/_files'] = size - children_total
                    else:
                        expanded[dir_path] = size
                else:
                    expanded[dir_path] = size

            # Categorizar cada entrada (sin solapamiento)
            for dir_path, size in expanded.items():
                category = self._categorize_path(dir_path)
                category_sizes[category] = category_sizes.get(category, 0) + size
            
            # Agregar Docker stats solo si NO fue cubierto por el escaneo de directorios
            # (evitar doble conteo: el scan ya recorre ~/Library/Containers/com.docker.docker)
            if report.get('docker') and report['docker'].get('available'):
                docker_size = report['docker'].get('total_size', 0)
                if docker_size > 0 and 'Docker' not in category_sizes:
                    category_sizes['Docker'] = docker_size
            
            # Calcular porcentajes
            for cat, size in sorted(category_sizes.items(), key=lambda x: x[1], reverse=True):
                if size > 0:
                    percent = (size / disk_usage['total']) * 100
                    categories.append({
                        'name': cat,
                        'size': size,
                        'percent': percent,
                        'color': colors.get(cat, '#6b7280')
                    })
            
            # Agregar volúmenes del sistema excluidos (VM, Preboot, etc.)
            skipped_size = report.get('skipped_volumes_size', 0)
            if skipped_size > 0:
                categories.append({
                    'name': 'Sistema (macOS)',
                    'size': skipped_size,
                    'percent': (skipped_size / disk_usage['total']) * 100,
                    'color': '#94a3b8'
                })

            # Espacio no contabilizado
            accounted = analyzed_total + skipped_size
            unanalyzed = disk_usage['used'] - accounted
            if unanalyzed > 0:
                # Elegir etiqueta según si estamos como root o no
                if os.geteuid() == 0:
                    gap_label = 'APFS purgeable'
                else:
                    gap_label = 'Sin permisos (sudo)'
                categories.append({
                    'name': gap_label,
                    'size': unanalyzed,
                    'percent': (unanalyzed / disk_usage['total']) * 100,
                    'color': colors['Sin analizar']
                })
            
            # Agregar espacio libre
            categories.append({
                'name': 'Libre',
                'size': disk_usage['available'],
                'percent': (disk_usage['available'] / disk_usage['total']) * 100,
                'color': colors['Libre']
            })
            
            html += f'''
        <div class="card" style="margin-bottom: 2rem;">
            <h2>💽 Uso del Disco</h2>
            <div class="disk-usage-bar" style="position: relative; height: 80px; border-radius: 12px; overflow: hidden; margin-bottom: 1rem; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">'''
            
            # Generar segmentos de la barra (con cap a 100%)
            left_position = 0
            segment_id = 0
            for cat in categories:
                remaining = 100.0 - left_position
                if remaining <= 0:
                    break
                segment_width = min(cat['percent'], remaining)
                if segment_width > 0.5:  # Solo mostrar si es más del 0.5%
                    # Determinar si el texto debe mostrarse basado en el ancho
                    show_text = segment_width > 5  # Mostrar texto solo si es más del 5%
                    html += f'''
                <div class="disk-segment" data-category="{cat['name']}" data-size="{cat['size']}" data-percent="{cat['percent']:.1f}"
                     style="position: absolute; left: {left_position}%; width: {segment_width}%; height: 100%; 
                            background: {cat['color']}; display: flex; align-items: center; justify-content: center;
                            border-right: 1px solid rgba(255,255,255,0.2); cursor: pointer; transition: all 0.2s ease;
                            overflow: hidden;" 
                     onmouseover="this.style.filter='brightness(1.1)'; this.style.zIndex='10';" 
                     onmouseout="this.style.filter='brightness(1)'; this.style.zIndex='1';">'''
                    
                    if show_text:
                        html += f'''
                    <div style="text-align: center; padding: 0 4px;">
                        <div style="color: white; font-size: 0.875rem; font-weight: 600; text-shadow: 0 1px 2px rgba(0,0,0,0.5);
                                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            {cat['name']}
                        </div>
                        <div style="color: rgba(255,255,255,0.9); font-size: 0.75rem; text-shadow: 0 1px 2px rgba(0,0,0,0.5);">
                            {self.format_size(cat['size'])}
                        </div>
                        <div style="color: rgba(255,255,255,0.8); font-size: 0.625rem; text-shadow: 0 1px 2px rgba(0,0,0,0.5);">
                            {cat['percent']:.1f}%
                        </div>
                    </div>'''
                    else:
                        # Para segmentos pequeños, solo mostrar porcentaje
                        html += f'''
                    <span style="color: white; font-size: 0.625rem; font-weight: 600; text-shadow: 0 1px 2px rgba(0,0,0,0.5);">
                        {cat['percent']:.1f}%
                    </span>'''
                    
                    html += '''
                </div>'''
                    left_position += segment_width
                    segment_id += 1
            
            html += f'''
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; margin-bottom: 1rem;">'''
            
            # Leyenda de categorías - excluir Libre y gaps de la leyenda principal
            exclude_from_legend = {'Libre', 'Sin permisos (sudo)', 'APFS purgeable'}
            display_categories = [cat for cat in categories if cat['name'] not in exclude_from_legend][:10]
            
            for cat in display_categories:
                # Determinar icono según categoría
                icons = {
                    'Applications': '🚀',
                    'Library': '📚', 
                    'Documents': '📄',
                    'Downloads': '⬇️',
                    'Docker': '🐳',
                    'Desarrollo': '💻',
                    'Cache': '🗑️',
                    'Media': '🎬',
                    'iCloud': '☁️',
                    'Otros': '📦'
                }
                icon = icons.get(cat['name'], '📁')
                
                html += f'''
                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem; border-radius: 8px; 
                            background: rgba(0,0,0,0.02); transition: all 0.2s ease;"
                     onmouseover="this.style.background='rgba(0,0,0,0.05)'"
                     onmouseout="this.style.background='rgba(0,0,0,0.02)'">
                    <div style="width: 20px; height: 20px; background: {cat['color']}; border-radius: 6px; 
                                box-shadow: 0 1px 3px rgba(0,0,0,0.1);"></div>
                    <div style="flex: 1;">
                        <div style="font-size: 0.875rem; font-weight: 600; color: var(--dark);">
                            {icon} {cat['name']}
                        </div>
                        <div style="font-size: 0.75rem; color: var(--gray);">
                            {self.format_size(cat['size'])} • {cat['percent']:.1f}%
                        </div>
                    </div>
                </div>'''
            
            html += f'''
            </div>

            <div style="display: flex; justify-content: space-between; color: var(--gray); font-size: 0.875rem;
                        padding-top: 1rem; border-top: 1px solid var(--border);">
                <span><strong>Usado:</strong> {self.format_size(disk_usage['used'])} ({percent_used:.1f}%)</span>
                <span><strong>Libre:</strong> {self.format_size(disk_usage['available'])} ({100-percent_used:.1f}%)</span>
                <span><strong>Total:</strong> {self.format_size(disk_usage['total'])}</span>
            </div>'''

            # Mostrar aviso de sudo solo si hay errores de permisos reales y cobertura >25%
            accounted_for_hint = analyzed_total + report.get('skipped_volumes_size', 0)
            permission_gap = disk_usage['used'] - accounted_for_hint
            scan_coverage = accounted_for_hint / disk_usage['used'] if disk_usage['used'] > 0 else 0
            perm_errors = [e for e in report.get('errors', []) if 'permisos' in e.lower()]
            if permission_gap > 10 * GB and os.geteuid() != 0 and scan_coverage > 0.25 and perm_errors:
                html += f'''
            <div style="margin-top: 0.75rem; padding: 0.75rem 1rem; background: #fef3c7; border: 1px solid #f59e0b;
                        border-radius: 8px; font-size: 0.8rem; color: #92400e;">
                <strong>💡 Tip:</strong> {self.format_size(int(permission_gap))} del disco no se pudieron analizar por falta de permisos.
                Para un análisis completo ejecuta: <code style="background: #fde68a; padding: 2px 6px; border-radius: 4px;">sudo make full path=/ min_size={int(self.min_size/MB)}</code>
            </div>'''

            html += '''
        </div>'''
        
        html += f'''
        <div class="stats-grid">
            <div class="stat-card primary">
                <div class="icon">📊</div>
                <div class="value">{self.format_size(summary['total_size'])}</div>
                <div class="label">Espacio Analizado</div>
            </div>
            
            <div class="stat-card success">
                <div class="icon">♻️</div>
                <div class="value">{self.format_size(summary['recoverable_space'])}</div>
                <div class="label">Espacio Recuperable</div>
            </div>
            
            <div class="stat-card warning">
                <div class="icon">📁</div>
                <div class="value">{summary['files_scanned']:,}</div>
                <div class="label">Archivos Escaneados</div>
            </div>
            
            <div class="stat-card danger">
                <div class="icon">🗂️</div>
                <div class="value">{summary['large_files_count']}</div>
                <div class="label">Archivos Grandes</div>
            </div>
        </div>
        
        <div class="dashboard-grid">
            <div class="card col-span-12">
                <h2>🌊 Distribución de Espacio</h2>
                
                <!-- Pestañas -->
                <div class="tabs" style="display: flex; gap: 0.5rem; margin-bottom: 1rem; border-bottom: 2px solid var(--border); padding-bottom: 0;">'''
        
        # Agregar pestañas para cada categoría disponible
        for idx, (category_key, sankey_data) in enumerate(all_sankey_data.items()):
            active_class = 'active' if idx == 0 else ''
            category_display = category_key.capitalize()
            if category_key == 'general':
                dir_name = Path(self.start_path).name or str(self.start_path)
                category_display = f'Vista General ({dir_name})'
            
            # Obtener el tamaño total de la categoría
            if category_key != 'general' and 'totalSize' in sankey_data:
                category_display += f' ({self.format_size(sankey_data["totalSize"])})'
            
            html += f'''
                    <button class="tab-button {active_class}" 
                            onclick="showSankeyTab('{category_key}')"
                            data-category="{category_key}"
                            style="padding: 0.75rem 1.5rem; border: none; background: none; 
                                   cursor: pointer; font-weight: 600; color: var(--gray);
                                   border-bottom: 3px solid transparent; transition: all 0.2s ease;
                                   position: relative;">
                        {category_display}
                    </button>'''
        
        html += '''
                </div>
                
                <!-- Contenedores de Sankey -->
                <div id="sankeyContainer" style="position: relative; min-height: 500px;">'''
        
        # Crear un div para cada Sankey
        for idx, (category_key, sankey_data) in enumerate(all_sankey_data.items()):
            display_style = 'block' if idx == 0 else 'none'
            html += f'''
                    <div id="sankey-{category_key}" class="sankey-panel" style="display: {display_style};">
                        <div id="sankeyChart-{category_key}"></div>'''
            
            # Si no es la vista general, agregar información adicional
            if category_key != 'general' and 'details' in sankey_data:
                details = sankey_data['details']
                html += f'''
                        <div style="margin-top: 1rem; padding: 1rem; background: var(--light); border-radius: 8px;">
                            <h3 style="margin: 0 0 1rem 0; color: var(--dark); font-size: 1.1rem;">
                                📊 {sankey_data.get("categoryName", category_key.capitalize())}: {self.format_size(sankey_data.get("totalSize", 0))}
                            </h3>
                            
                            <!-- Comandos de limpieza -->
                            {self._generate_cleanup_section_html(details.get('cleanup_commands', []))}
                            
                            <!-- Archivos grandes de la categoría -->
                            {self._generate_category_files_html(details.get('large_files', []))}
                            
                            <!-- Tipos de archivo -->
                            {self._generate_category_types_html(details.get('file_types', []))}
                        </div>'''
            
            html += '''
                    </div>'''
        
        html += '''
                </div>'''
        
        # Si hay contexto del disco, agregar mini visualización
        general_sankey = all_sankey_data.get('general', {})
        if general_sankey.get('diskContext'):
            ctx = general_sankey['diskContext']
            html += f'''
                <div style="margin-top: 1rem; padding: 1rem; background: var(--light); border-radius: 8px;">
                    <p style="text-align: center; color: var(--gray); margin-bottom: 0.5rem;">
                        Este análisis representa el <strong style="color: var(--primary);">{ctx['percent_of_disk']:.1f}%</strong> del espacio total del disco'''
            
            if ctx.get('warning'):
                html += f'''
                        <br><span style="color: var(--warning);">⚠️ Nota: El análisis encontró más espacio ({self.format_size(ctx['analyzed'])}) que el reportado como usado ({self.format_size(ctx['used'])})</span>'''
            else:
                html += f'''
                        y el <strong style="color: var(--primary);">{ctx['percent_of_used']:.1f}%</strong> del espacio usado'''
                        
            html += f'''
                    </p>
                    <p style="text-align: center; color: var(--gray); font-size: 0.875rem; margin: 0;">
                        Analizado: {self.format_size(ctx['analyzed'])} | 
                        Usado en disco: {self.format_size(ctx['used'])} | 
                        Total del disco: {self.format_size(ctx['total'])}
                    </p>
                </div>'''
        
        html += '''
            </div>
            
            <div class="card col-span-6">
                <h2>📈 Tipos de Archivo</h2>
                <div class="chart-container">
                    <canvas id="typeChart"></canvas>
                </div>
            </div>
            
            <div class="card col-span-6">
                <h2>🕐 Archivos por Antigüedad</h2>
                <div class="chart-container">
                    <canvas id="ageChart"></canvas>
                </div>
            </div>
            
            <div class="card col-span-12">
                <h2>💡 Recomendaciones</h2>
                <div id="recommendations">'''
        
        # Agregar recomendaciones
        for rec in report['recommendations'][:5]:
            priority_class = rec['priority'].lower()
            command = rec.get('command', '')
            html += f'''
                    <div class="recommendation">
                        <div class="header">
                            <div>
                                <span class="priority {priority_class}">{rec['priority']}</span>
                                <strong>{rec['type']}</strong>
                            </div>
                            <span style="color: var(--primary); font-weight: 600;">{self.format_size(rec['space'])}</span>
                        </div>
                        <p style="margin: 0.5rem 0; color: var(--gray);">{rec['description']}</p>'''
            
            if command and not command.startswith('#'):
                html += f'''
                        <div class="command-box">{command}<button class="copy-btn" onclick="copyCommand(this)">Copiar</button></div>'''
            
            html += '''
                    </div>'''
        
        html += '''
                </div>
            </div>'''
        
        # Sección de Docker si está disponible
        if report['docker'] and report['docker']['available']:
            docker = report['docker']
            html += f'''
            <div class="card col-span-12">
                <h2>🐳 Estado de Docker</h2>
                <div class="dashboard-grid" style="margin-top: 1rem;">
                    <div class="col-span-4">
                        <canvas id="dockerChart"></canvas>
                    </div>
                    <div class="col-span-8">
                        <div class="stats-grid" style="margin: 0;">
                            <div class="stat-card">
                                <div class="value">{self.format_size(docker['total_size'])}</div>
                                <div class="label">Uso Total</div>
                            </div>
                            <div class="stat-card">
                                <div class="value">{self.format_size(docker['reclaimable'])}</div>
                                <div class="label">Recuperable</div>
                            </div>
                            <div class="stat-card">
                                <div class="value">{docker['images']['count']}</div>
                                <div class="label">Imágenes</div>
                            </div>
                            <div class="stat-card">
                                <div class="value">{docker['containers']['count']}</div>
                                <div class="label">Contenedores</div>
                            </div>
                        </div>
                        
                        <div style="margin-top: 1rem; background: var(--light); padding: 1rem; border-radius: 8px;">
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem; font-size: 0.875rem;">
                                <div>
                                    <strong>Imágenes:</strong> {self.format_size(docker['images']['size'])} 
                                    <span style="color: var(--danger);">({self.format_size(docker['images'].get('reclaimable', 0))} recuperable)</span>
                                </div>
                                <div>
                                    <strong>Contenedores:</strong> {self.format_size(docker['containers']['size'])}
                                    <span style="color: var(--gray);">({docker['containers'].get('stopped', 0)} detenidos)</span>
                                </div>
                                <div>
                                    <strong>Volúmenes:</strong> {self.format_size(docker['volumes']['size'])}
                                    <span style="color: var(--danger);">({self.format_size(docker['volumes'].get('reclaimable', 0))} recuperable)</span>
                                </div>
                                <div>
                                    <strong>Build Cache:</strong> {self.format_size(docker['build_cache']['size'])}
                                    <span style="color: var(--danger);">({self.format_size(docker['build_cache'].get('reclaimable', 0))} recuperable)</span>
                                </div>
                            </div>
                        </div>
                        
                        <div class="command-box" style="margin-top: 1rem;">
                            docker system prune -a --volumes -f
                            <button class="copy-btn" onclick="copyCommand(this)">Copiar</button>
                        </div>
                    </div>
                </div>
            </div>'''
        
        # Tabla de archivos
        html += '''
            <div class="card col-span-12">
                <h2>🗂️ Archivos Grandes</h2>
                <div style="overflow-x: auto;">
                    <table class="file-table">
                        <thead>
                            <tr>
                                <th style="width: 40px;">
                                    <input type="checkbox" id="selectAll" class="checkbox" onchange="toggleAll(this)">
                                </th>
                                <th>Archivo</th>
                                <th style="width: 100px;">Tamaño</th>
                                <th style="width: 80px;">Edad</th>
                                <th style="width: 80px;">Tipo</th>
                                <th style="width: 60px;">Cache</th>
                            </tr>
                        </thead>
                        <tbody id="fileTableBody">'''
        
        # Agregar archivos a la tabla
        for file_data in files_data:
            age_str = f"{file_data['age_days']}d" if file_data['age_days'] >= 0 else "N/A"
            cache_badge = '<span class="badge cache">Cache</span>' if file_data['is_cache'] else ''
            is_protected = file_data.get('is_protected', False)

            if is_protected:
                protected_badge = '<span class="badge" style="background: #ef4444; color: white;">🔒 Sistema</span>'
                checkbox_html = f'''<input type="checkbox" class="checkbox file-checkbox"
                                           data-id="{file_data['id']}"
                                           data-size="{file_data['size']}"
                                           data-cmd=""
                                           disabled title="Archivo del sistema - no se puede borrar">'''
                row_style = 'opacity: 0.6;'
            else:
                protected_badge = ''
                delete_cmd_escaped = file_data['delete_cmd'].replace('"', '&quot;').replace("'", '&apos;')
                checkbox_html = f'''<input type="checkbox" class="checkbox file-checkbox"
                                           data-id="{file_data['id']}"
                                           data-size="{file_data['size']}"
                                           data-cmd="{delete_cmd_escaped}"
                                           onchange="updateSelection()">'''
                row_style = ''

            html += f'''
                            <tr style="{row_style}">
                                <td>
                                    {checkbox_html}
                                </td>
                                <td>
                                    <div class="file-name">{file_data['name']} {protected_badge}</div>
                                    <div class="file-path">{file_data['path']}</div>
                                </td>
                                <td style="font-weight: 600; color: var(--primary);">{file_data['size_formatted']}</td>
                                <td>{age_str}</td>
                                <td>{file_data['extension'] or 'N/A'}</td>
                                <td>{cache_badge}</td>
                            </tr>'''
        
        html += '''
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <div class="action-bar">
            <div>
                <span id="selectedCount">0</span> archivos seleccionados 
                (<span id="selectedSize">0 B</span>)
            </div>
            <div>
                <button class="btn btn-primary" onclick="generateScript()" disabled id="generateBtn">
                    Generar Script de Borrado
                </button>
                <button class="btn btn-danger" onclick="showDeleteModal()" disabled id="deleteBtn">
                    Ver Comandos de Borrado
                </button>
            </div>
        </div>
    </div>
    
    <div class="modal" id="commandModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>🗑️ Comandos de Borrado</h3>
                <p style="color: var(--danger); margin-top: 0.5rem;">
                    ⚠️ PRECAUCIÓN: Estos comandos borrarán permanentemente los archivos seleccionados
                </p>
            </div>
            <div class="command-box" id="deleteCommands" style="max-height: 300px; overflow-y: auto;">
                # Comandos aparecerán aquí
            </div>
            <div style="margin-top: 1.5rem; display: flex; gap: 1rem; justify-content: flex-end;">
                <button class="btn" onclick="closeModal()" style="background: var(--gray); color: white;">
                    Cerrar
                </button>
                <button class="btn btn-primary" onclick="copyDeleteCommands()">
                    Copiar Todo
                </button>
            </div>
        </div>
    </div>'''
        
        # JavaScript
        html += f'''
    <script>
        // Datos para los gráficos
        const allSankeyData = {json.dumps(all_sankey_data)};
        const fileTypeData = {json.dumps(file_type_data)};
        const ageData = {json.dumps([{"age": k, "size": v['size'], "count": v['count']} for k, v in age_distribution.items()])};
        const filesData = {json.dumps(files_data)};
        
        // Estado de los Sankeys renderizados
        const renderedSankeys = new Set();
        
        // Configuración de Chart.js
        Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif';
        
        // Función para formatear bytes
        function formatBytes(bytes) {{
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            if (bytes === 0 || bytes < 0) return '0 B';
            if (!isFinite(bytes)) return '0 B';
            const i = Math.floor(Math.log(Math.abs(bytes)) / Math.log(1024));
            return (Math.abs(bytes) / Math.pow(1024, i)).toFixed(2) + ' ' + sizes[i];
        }}
        
        // Función para renderizar un Sankey específico
        function renderSankey(categoryKey) {{
            if (renderedSankeys.has(categoryKey)) return;
            
            const sankeyData = allSankeyData[categoryKey];
            if (!sankeyData) return;
            
            const sankeyTrace = {{
                type: "sankey",
                orientation: "h",
                arrangement: "fixed",
                node: {{
                    pad: 15,
                    thickness: 20,
                    line: {{
                        color: "black",
                        width: 0.5
                    }},
                    label: sankeyData.labels,
                    color: sankeyData.colors,
                    x: sankeyData.nodeX || undefined,
                    y: sankeyData.nodeY || undefined,
                    hovertemplate: '%{{label}}<extra></extra>'
                }},
                link: {{
                    source: sankeyData.source,
                    target: sankeyData.target,
                    value: sankeyData.value,
                    color: sankeyData.linkColors,
                    hovertemplate: '%{{source.label}} → %{{target.label}}<br />%{{value}}<extra></extra>',
                    hoverlabel: {{align: 'left'}}
                }},
                textfont: {{
                    size: 11,
                    family: '-apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif'
                }}
            }};
            
            const sankeyLayout = {{
                font: {{
                    size: 12,
                    family: '-apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif'
                }},
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                margin: {{ l: 10, r: 10, t: 10, b: 10 }},
                height: 500
            }};
            
            const config = {{
                responsive: true,
                displayModeBar: false
            }};
            
            // Formatear valores en el Sankey
            sankeyTrace.link.value = sankeyData.value;
            sankeyTrace.link.hovertemplate = sankeyData.source.map((s, i) => {{
                const sourceLabel = sankeyData.labels[s].split('\\n')[0];
                const targetLabel = sankeyData.labels[sankeyData.target[i]].split('\\n')[0];
                return sourceLabel + ' → ' + targetLabel + '<br />' + formatBytes(sankeyData.value[i]) + '<extra></extra>';
            }});
            
            Plotly.newPlot('sankeyChart-' + categoryKey, [sankeyTrace], sankeyLayout, config);
            renderedSankeys.add(categoryKey);
        }}
        
        // Función para cambiar entre pestañas
        function showSankeyTab(categoryKey) {{
            // Ocultar todos los paneles
            document.querySelectorAll('.sankey-panel').forEach(panel => {{
                panel.style.display = 'none';
            }});
            
            // Actualizar estado de pestañas
            document.querySelectorAll('.tab-button').forEach(tab => {{
                tab.classList.remove('active');
            }});
            
            // Mostrar el panel seleccionado
            const selectedPanel = document.getElementById('sankey-' + categoryKey);
            if (selectedPanel) {{
                selectedPanel.style.display = 'block';
            }}
            
            // Activar la pestaña seleccionada
            const selectedTab = document.querySelector(`[data-category="${{categoryKey}}"]`);
            if (selectedTab) {{
                selectedTab.classList.add('active');
            }}
            
            // Renderizar el Sankey si no se ha hecho antes
            renderSankey(categoryKey);
        }}
        
        // Renderizar el primer Sankey (general) al cargar
        document.addEventListener('DOMContentLoaded', function() {{
            renderSankey('general');
        }});
        
        // Gráfico de tipos de archivo
        const typeCtx = document.getElementById('typeChart').getContext('2d');
        new Chart(typeCtx, {{
            type: 'bar',
            data: {{
                labels: fileTypeData.map(d => d.type),
                datasets: [{{
                    label: 'Tamaño',
                    data: fileTypeData.map(d => d.size),
                    backgroundColor: '#6366f1',
                    borderRadius: 6
                }}]
            }},
            options: {{
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                const item = fileTypeData[context.dataIndex];
                                return [
                                    'Tamaño: ' + formatBytes(item.size),
                                    'Archivos: ' + item.count.toLocaleString()
                                ];
                            }}
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        ticks: {{
                            callback: function(value) {{
                                return formatBytes(value);
                            }}
                        }},
                        grid: {{ display: false }}
                    }},
                    y: {{ grid: {{ display: false }} }}
                }}
            }}
        }});
        
        // Gráfico de antigüedad
        const ageCtx = document.getElementById('ageChart').getContext('2d');
        new Chart(ageCtx, {{
            type: 'bar',
            data: {{
                labels: ageData.map(d => d.age),
                datasets: [{{
                    label: 'Archivos',
                    data: ageData.map(d => d.count),
                    backgroundColor: '#8b5cf6',
                    borderRadius: 6
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{ stepSize: 1 }}
                    }}
                }}
            }}
        }});'''
        
        # Agregar gráfico de Docker si está disponible
        if report['docker'] and report['docker']['available']:
            docker = report['docker']
            # Asegurar que used_space nunca sea negativo
            used_space = max(0, docker['total_size'] - docker['reclaimable'])
            html += f'''
        
        // Gráfico de Docker
        const dockerCtx = document.getElementById('dockerChart').getContext('2d');
        new Chart(dockerCtx, {{
            type: 'pie',
            data: {{
                labels: ['En uso', 'Recuperable'],
                datasets: [{{
                    data: [{used_space}, {docker['reclaimable']}],
                    backgroundColor: ['#6366f1', '#ef4444'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: true,
                plugins: {{
                    legend: {{
                        position: 'bottom',
                        labels: {{
                            usePointStyle: true,
                            padding: 12
                        }}
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                return context.label + ': ' + formatBytes(context.raw);
                            }}
                        }}
                    }}
                }}
            }}
        }});'''
        
        html += '''
        
        // Funciones de selección de archivos
        let selectedFiles = new Set();
        let totalSelectedSize = 0;
        
        function toggleAll(checkbox) {
            const checkboxes = document.querySelectorAll('.file-checkbox');
            checkboxes.forEach(cb => {
                if (!cb.disabled) cb.checked = checkbox.checked;
            });
            updateSelection();
        }
        
        function updateSelection() {
            selectedFiles.clear();
            totalSelectedSize = 0;
            
            const checkboxes = document.querySelectorAll('.file-checkbox:checked');
            checkboxes.forEach(cb => {
                const id = cb.dataset.id;
                const size = parseInt(cb.dataset.size);
                const cmd = cb.dataset.cmd;
                selectedFiles.add({id, size, cmd});
                totalSelectedSize += size;
            });
            
            document.getElementById('selectedCount').textContent = selectedFiles.size;
            document.getElementById('selectedSize').textContent = formatBytes(totalSelectedSize);
            
            const hasSelection = selectedFiles.size > 0;
            document.getElementById('generateBtn').disabled = !hasSelection;
            document.getElementById('deleteBtn').disabled = !hasSelection;
        }
        
        function copyCommand(button) {
            const command = button.previousSibling.textContent.trim();
            navigator.clipboard.writeText(command).then(() => {
                const originalText = button.textContent;
                button.textContent = '✓ Copiado';
                button.style.background = '#10b981';
                setTimeout(() => {
                    button.textContent = originalText;
                    button.style.background = '';
                }, 2000);
            });
        }
        
        function generateScript() {
            const commands = [
                '#!/bin/bash',
                '# Script de limpieza generado por Disk Analyzer',
                '# Fecha: ' + new Date().toLocaleString(),
                '',
                '# Total a liberar: ' + formatBytes(totalSelectedSize),
                '',
                '# PRECAUCIÓN: Este script borrará permanentemente los archivos',
                'read -p "¿Estás seguro? (s/n): " confirm',
                'if [ "$confirm" != "s" ]; then exit 1; fi',
                ''
            ];
            
            selectedFiles.forEach(file => {
                if (file.cmd) commands.push(file.cmd.replace(/&quot;/g, '"').replace(/&apos;/g, "'"));
            });
            
            const script = commands.join('\\n');
            const blob = new Blob([script], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'cleanup_script.sh';
            a.click();
            URL.revokeObjectURL(url);
        }
        
        function showDeleteModal() {
            const commands = Array.from(selectedFiles).map(f => 
                f.cmd.replace(/&quot;/g, '"').replace(/&apos;/g, "'")
            ).join('\\n');
            document.getElementById('deleteCommands').textContent = commands;
            document.getElementById('commandModal').style.display = 'flex';
        }
        
        function closeModal() {
            document.getElementById('commandModal').style.display = 'none';
        }
        
        function copyDeleteCommands() {
            const commands = document.getElementById('deleteCommands').textContent;
            navigator.clipboard.writeText(commands).then(() => {
                alert('Comandos copiados al portapapeles');
            });
        }
        
        // Cerrar modal al hacer clic fuera
        window.onclick = function(event) {
            const modal = document.getElementById('commandModal');
            if (event.target === modal) {
                closeModal();
            }
        }
    </script>
</body>
</html>'''
        
        return html
    
    @staticmethod
    def _deduplicate_dirs(dirs: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
        """Filtra directorios anidados: si /a y /a/b están en la lista, solo queda /a."""
        sorted_dirs = sorted(dirs, key=lambda x: x[0])
        result = []
        for path, size in sorted_dirs:
            # Verificar si algún directorio ya agregado es padre de este
            if not any(path.startswith(parent + '/') for parent, _ in result):
                result.append((path, size))
        return result

    def _prepare_sankey_data_by_category(self, report: Dict) -> Dict:
        """Prepara datos Sankey separados por categoría"""
        all_sankeys = {}
        
        # Primero generar el Sankey general
        all_sankeys['general'] = self._prepare_sankey_data(report)
        
        # Si hay demasiados archivos, usar modo lite
        files_scanned = report['summary'].get('files_scanned', 0)
        if files_scanned > 100000:
            # Modo lite: solo categorías principales
            main_categories = ['Desarrollo', 'Otros']
            max_dirs_per_category = 30
        else:
            # Modo normal
            main_categories = ['Desarrollo', 'Docker', 'Library', 'Documents', 'Otros']
            max_dirs_per_category = 50
        
        # Definir categorías a procesar
        categories_to_process = {
            'Desarrollo': ['/Developer', '/repos', '/.npm', '/node_modules', '/.continue', '/venv', '/.cargo', '/.rustup'],
            'Docker': ['/.docker', '/Docker', '/Containers/com.docker'],
            'Library': ['/Library'],
            'Documents': ['/Documents'],
            'Cache': ['/cache', '/caches', '/tmp', '/temp', '/logs'],
            'Downloads': ['/Downloads'],
            'Applications': ['/Applications']
        }
        
        # Para cada categoría principal, generar su propio Sankey
        for category_name in main_categories:
            patterns = categories_to_process.get(category_name, [])
            if not patterns:
                continue
                
            # Filtrar directorios que pertenecen a esta categoría
            category_dirs = []
            dirs_to_check = report.get('top_directories', [])[:min(100, len(report.get('top_directories', [])))]
            
            for path, size in dirs_to_check:
                if any(pattern in path for pattern in patterns):
                    # Excluir algunos patrones de Documents si está en Desarrollo
                    if category_name == 'Documents' and any(dev in path for dev in ['/repos', '/Developer']):
                        continue
                    category_dirs.append((path, size))
                    
                    # Limitar para evitar procesamiento excesivo
                    if len(category_dirs) >= max_dirs_per_category:
                        break
            
            if category_dirs and len(category_dirs) > 2:  # Solo si hay suficientes datos
                # Usar dirs deduplicados para el total (evitar contar /a + /a/b)
                deduped = self._deduplicate_dirs(category_dirs)
                category_report = {
                    'summary': {'total_size': sum(size for _, size in deduped)},
                    'top_directories': category_dirs[:20],  # Limitar a top 20
                    'disk_usage': report.get('disk_usage', {})
                }
                
                # Generar Sankey para esta categoría
                sankey_data = self._prepare_category_sankey(category_report, category_name)
                if sankey_data and len(sankey_data['labels']) > 1:
                    # Agregar detalles de la categoría
                    category_details = self._get_category_details(report, category_name, category_dirs)
                    sankey_data['details'] = category_details
                    all_sankeys[category_name.lower()] = sankey_data
        
        # Procesar categoría "Otros" solo si está en las categorías principales
        if 'Otros' in main_categories:
            otros_dirs = []
            categorized_paths = set()
            
            # Recolectar todos los paths categorizados de manera más eficiente
            dirs_to_check = report.get('top_directories', [])[:min(150, len(report.get('top_directories', [])))]
            
            for path, size in dirs_to_check:
                is_categorized = False
                for patterns in categories_to_process.values():
                    if any(pattern in path for pattern in patterns):
                        is_categorized = True
                        break
                
                # Si no está categorizado y no es la raíz, agregar a Otros
                if not is_categorized and path != str(self.start_path):
                    otros_dirs.append((path, size))
                    
                    # Limitar también la categoría Otros
                    if len(otros_dirs) >= max_dirs_per_category:
                        break
            
            if otros_dirs:
                deduped_otros = self._deduplicate_dirs(otros_dirs)
                otros_report = {
                    'summary': {'total_size': sum(size for _, size in deduped_otros)},
                    'top_directories': otros_dirs[:20],  # Limitar a top 20
                    'disk_usage': report.get('disk_usage', {})
                }
                sankey_data = self._prepare_category_sankey(otros_report, 'Otros')
                if sankey_data and len(sankey_data['labels']) > 1:
                    # Agregar detalles de la categoría
                    category_details = self._get_category_details(report, 'Otros', otros_dirs)
                    sankey_data['details'] = category_details
                    all_sankeys['otros'] = sankey_data
        
        return all_sankeys
    
    def _get_category_details(self, report: Dict, category_name: str, category_dirs: List) -> Dict:
        """Obtiene detalles específicos de una categoría"""
        category_paths = set(path for path, _ in category_dirs)
        
        # Filtrar archivos grandes que pertenecen a esta categoría
        category_files = []
        for file_info in report.get('large_files', []):
            if any(category_path in file_info['path'] for category_path in category_paths):
                category_files.append(file_info)
        
        # Ordenar por tamaño
        category_files.sort(key=lambda x: x['size'], reverse=True)
        
        # Analizar tipos de archivo en esta categoría
        file_types = defaultdict(lambda: {'count': 0, 'size': 0})
        for file_info in category_files:
            ext = file_info.get('extension', 'sin_extension')
            file_types[ext]['count'] += 1
            file_types[ext]['size'] += file_info['size']
        
        # Generar comandos de limpieza específicos
        cleanup_commands = self._generate_category_cleanup_commands(category_name, category_dirs)
        
        return {
            'large_files': category_files[:20],  # Top 20 archivos grandes
            'file_types': sorted(file_types.items(), key=lambda x: x[1]['size'], reverse=True)[:10],
            'cleanup_commands': cleanup_commands,
            'total_files': len(category_files),
            'total_size': sum(size for _, size in category_dirs)
        }
    
    def _generate_category_cleanup_commands(self, category_name: str, category_dirs: List) -> List[Dict]:
        """Genera comandos de limpieza específicos por categoría"""
        commands = []
        
        if category_name == 'Desarrollo':
            # Comandos para limpiar desarrollo
            if self.is_windows:
                commands.extend([
                    {
                        'description': 'Limpiar índices de Continue (archivos > 30 días)',
                        'command': 'forfiles /P "%USERPROFILE%\\.continue\\index" /M *.lance /D -30 /C "cmd /c del @path"',
                        'risk': 'Bajo',
                        'space_estimate': '5-10 GB'
                    },
                    {
                        'description': 'Limpiar logs antiguos',
                        'command': 'forfiles /P "%USERPROFILE%\\Documents\\repos" /M *.log /D -7 /C "cmd /c if @fsize gtr 10485760 del @path"',
                        'risk': 'Bajo',
                        'space_estimate': '1-5 GB'
                    },
                    {
                        'description': 'Limpiar node_modules no utilizados',
                        'command': 'for /d /r "%USERPROFILE%\\Documents\\repos" %%d in (node_modules) do @if exist "%%d" rd /s /q "%%d"',
                        'risk': 'Medio',
                        'space_estimate': '500MB-2GB'
                    }
                ])
            else:
                commands.extend([
                    {
                        'description': 'Limpiar índices de Continue (archivos > 30 días)',
                        'command': 'find ~/.continue/index -name "*.lance" -mtime +30 -exec rm -rf {} +',
                        'risk': 'Bajo',
                        'space_estimate': '5-10 GB'
                    },
                    {
                        'description': 'Limpiar logs antiguos',
                        'command': 'find ~/Documents/repos -name "*.log" -mtime +7 -size +10M -delete',
                        'risk': 'Bajo',
                        'space_estimate': '1-5 GB'
                    },
                    {
                        'description': 'Limpiar node_modules no utilizados',
                        'command': 'find ~/Documents/repos -name "node_modules" -type d -mtime +30 -exec rm -rf {} +',
                        'risk': 'Medio',
                        'space_estimate': '500MB-2GB'
                    }
                ])
        
        elif category_name == 'Docker':
            commands.extend([
                {
                    'description': 'Limpiar imágenes Docker no utilizadas',
                    'command': 'docker image prune -a -f',
                    'risk': 'Medio',
                    'space_estimate': '2-10 GB'
                },
                {
                    'description': 'Limpiar volúmenes Docker no utilizados',
                    'command': 'docker volume prune -f',
                    'risk': 'Alto',
                    'space_estimate': '5-20 GB'
                }
            ])
        
        elif category_name == 'Library':
            if self.is_windows:
                commands.extend([
                    {
                        'description': 'Limpiar caches de aplicaciones',
                        'command': 'del /f /s /q "%LOCALAPPDATA%\\Temp\\*"',
                        'risk': 'Bajo',
                        'space_estimate': '1-5 GB'
                    },
                    {
                        'description': 'Limpiar logs del sistema Windows',
                        'command': 'wevtutil cl Application && wevtutil cl System',
                        'risk': 'Medio',
                        'space_estimate': '100MB-1GB'
                    }
                ])
            elif self.is_macos:
                commands.extend([
                    {
                        'description': 'Limpiar caches de aplicaciones',
                        'command': 'rm -rf ~/Library/Caches/*',
                        'risk': 'Bajo',
                        'space_estimate': '1-5 GB'
                    },
                    {
                        'description': 'Limpiar logs del sistema',
                        'command': 'sudo rm -rf /var/log/*.log',
                        'risk': 'Medio',
                        'space_estimate': '100MB-1GB'
                    }
                ])
            else:  # Linux
                commands.extend([
                    {
                        'description': 'Limpiar caches de aplicaciones',
                        'command': 'rm -rf ~/.cache/*',
                        'risk': 'Bajo',
                        'space_estimate': '1-5 GB'
                    },
                    {
                        'description': 'Limpiar logs del sistema',
                        'command': 'sudo journalctl --vacuum-time=7d',
                        'risk': 'Medio',
                        'space_estimate': '100MB-1GB'
                    }
                ])
        
        elif category_name == 'Otros':
            # Para "Otros", generar comandos solo para directorios del usuario
            # Excluir directorios del sistema que no son accionables
            system_roots = {'/Users', '/System', '/private', '/usr', '/bin', '/sbin',
                            '/var', '/etc', '/tmp', '/cores', '/opt'}
            for path, size in category_dirs[:10]:
                if size > 1 * GB:
                    dir_name = Path(path).name
                    # Solo sugerir directorios que el usuario puede revisar
                    if path in system_roots or Path(path).parent == Path('/'):
                        continue
                    commands.append({
                        'description': f'Revisar directorio grande: {dir_name}',
                        'command': f'du -sh "{path}"/* | sort -hr | head -20',
                        'risk': 'N/A',
                        'space_estimate': self.format_size(size)
                    })
        
        return commands
    
    def _generate_cleanup_section_html(self, cleanup_commands: List[Dict]) -> str:
        """Genera HTML para los comandos de limpieza"""
        if not cleanup_commands:
            return ""
        
        html = '''
            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin: 0 0 0.75rem 0; color: var(--primary); font-size: 1rem;">🗑️ Comandos de Limpieza Sugeridos</h4>
                <div style="display: grid; gap: 0.75rem;">'''
        
        for cmd in cleanup_commands:
            risk_color = {
                'Bajo': 'var(--success)',
                'Medio': 'var(--warning)',
                'Alto': 'var(--danger)',
                'N/A': 'var(--gray)'
            }.get(cmd.get('risk', 'N/A'), 'var(--gray)')
            
            html += f'''
                    <div style="border: 1px solid var(--border); border-radius: 8px; padding: 1rem; background: white;">
                        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;">
                            <strong style="color: var(--dark); font-size: 0.9rem;">{cmd['description']}</strong>
                            <span style="background: {risk_color}; color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem;">
                                {cmd.get('risk', 'N/A')}
                            </span>
                        </div>
                        <div style="background: var(--dark); color: #f1f5f9; padding: 0.75rem; border-radius: 6px; font-family: monospace; font-size: 0.8rem; margin-bottom: 0.5rem;">
                            {cmd['command']}
                        </div>
                        <div style="color: var(--gray); font-size: 0.8rem;">
                            💾 Espacio estimado: <strong>{cmd.get('space_estimate', 'Desconocido')}</strong>
                        </div>
                    </div>'''
        
        html += '''
                </div>
            </div>'''
        
        return html
    
    def _generate_category_files_html(self, large_files: List[Dict]) -> str:
        """Genera HTML para los archivos grandes de la categoría"""
        if not large_files:
            return ""
        
        html = f'''
            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin: 0 0 0.75rem 0; color: var(--primary); font-size: 1rem;">📁 Archivos Más Grandes ({len(large_files)})</h4>
                <div style="background: white; border-radius: 8px; overflow: hidden; border: 1px solid var(--border);">
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead style="background: var(--light);">
                            <tr>
                                <th style="padding: 0.75rem; text-align: left; font-size: 0.8rem; color: var(--gray); border-bottom: 1px solid var(--border);">Archivo</th>
                                <th style="padding: 0.75rem; text-align: right; font-size: 0.8rem; color: var(--gray); border-bottom: 1px solid var(--border);">Tamaño</th>
                                <th style="padding: 0.75rem; text-align: right; font-size: 0.8rem; color: var(--gray); border-bottom: 1px solid var(--border);">Edad</th>
                                <th style="padding: 0.75rem; text-align: center; font-size: 0.8rem; color: var(--gray); border-bottom: 1px solid var(--border);">Tipo</th>
                            </tr>
                        </thead>
                        <tbody>'''
        
        for i, file_info in enumerate(large_files[:10]):  # Mostrar solo top 10
            file_name = Path(file_info['path']).name
            if len(file_name) > 40:
                file_name = file_name[:37] + "..."
            
            age = f"{file_info['age_days']}d" if file_info['age_days'] >= 0 else "N/A"
            cache_badge = '<span style="background: var(--warning); color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.7rem;">Cache</span>' if file_info.get('is_cache') else ''
            
            row_bg = 'background: var(--light);' if i % 2 == 0 else ''
            
            html += f'''
                            <tr style="{row_bg}">
                                <td style="padding: 0.75rem; font-size: 0.85rem;">
                                    <div style="font-weight: 600; color: var(--dark);">{file_name}</div>
                                    <div style="font-size: 0.75rem; color: var(--gray); margin-top: 0.25rem;">{file_info['path']}</div>
                                </td>
                                <td style="padding: 0.75rem; text-align: right; font-weight: 600; color: var(--primary); font-size: 0.85rem;">
                                    {self.format_size(file_info['size'])}
                                </td>
                                <td style="padding: 0.75rem; text-align: right; font-size: 0.85rem; color: var(--gray);">
                                    {age}
                                </td>
                                <td style="padding: 0.75rem; text-align: center; font-size: 0.85rem;">
                                    {cache_badge}
                                </td>
                            </tr>'''
        
        html += '''
                        </tbody>
                    </table>
                </div>
            </div>'''
        
        return html
    
    def _generate_category_types_html(self, file_types: List) -> str:
        """Genera HTML para los tipos de archivo de la categoría"""
        if not file_types:
            return ""
        
        html = f'''
            <div style="margin-bottom: 1rem;">
                <h4 style="margin: 0 0 0.75rem 0; color: var(--primary); font-size: 1rem;">📄 Tipos de Archivo</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.5rem;">'''
        
        for ext, stats in file_types[:8]:  # Mostrar solo top 8
            html += f'''
                    <div style="background: white; border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem;">
                        <div style="font-weight: 600; color: var(--dark); margin-bottom: 0.25rem;">{ext}</div>
                        <div style="font-size: 0.8rem; color: var(--gray);">
                            {self.format_size(stats['size'])} • {stats['count']} archivos
                        </div>
                    </div>'''
        
        html += '''
                </div>
            </div>'''
        
        return html
    
    def _prepare_category_sankey(self, report: Dict, category_name: str) -> Dict:
        """Prepara datos Sankey para una categoría específica"""
        labels = []
        source = []
        target = []
        value = []
        colors = []
        
        # Colores específicos por categoría
        category_colors = {
            'Desarrollo': '#ec4899',
            'Docker': '#ef4444',
            'Library': '#8b5cf6',
            'Documents': '#10b981',
            'Cache': '#f97316',
            'Downloads': '#f59e0b',
            'Applications': '#6366f1',
            'Otros': '#6b7280'
        }
        
        total_size = report['summary']['total_size']
        if total_size == 0:
            return {}
        
        # Nodo raíz de la categoría
        labels.append(f"{category_name}\n{self.format_size(total_size)}")
        colors.append(category_colors.get(category_name, '#6b7280'))
        
        # Procesar directorios de la categoría
        dir_map = {category_name: 0}
        dir_children = defaultdict(list)
        
        # Analizar jerarquía
        all_dirs = {}
        for path, size in report['top_directories']:
            all_dirs[path] = size
            parent_path = str(Path(path).parent)
            dir_children[parent_path].append((path, size))
        
        # Función para agregar directorios
        def add_directory(parent_path, parent_idx, level=0, max_level=2):  # Reducir profundidad
            if level > max_level:
                return
                
            children = dir_children.get(parent_path, [])
            children.sort(key=lambda x: x[1], reverse=True)
            
            max_children = 10 if level == 0 else 5  # Reducir número de hijos
            
            for child_path, child_size in children[:max_children]:
                if child_path in dir_map:
                    continue
                
                # Solo agregar si es significativo (>0.5% del total de la categoría)
                if child_size / total_size < 0.005:
                    continue
                
                dir_name = Path(child_path).name
                
                # Truncar nombres largos
                if len(dir_name) > 25:
                    dir_name = dir_name[:22] + "..."
                
                # Agregar nodo
                node_idx = len(labels)
                labels.append(f"{dir_name}\n{self.format_size(child_size)}")
                colors.append(self._get_dir_color(dir_name, category_colors.get(category_name, '#6b7280')))
                dir_map[child_path] = node_idx
                
                # Agregar enlace
                source.append(parent_idx)
                target.append(node_idx)
                value.append(child_size)
                
                # Recursivamente agregar hijos
                add_directory(child_path, node_idx, level + 1, max_level)
        
        # Construir el árbol - simplificado para mejor rendimiento
        # Primero agregar todos los directorios top-level
        for path, size in report['top_directories'][:10]:  # Limitar a top 10 para rendimiento
            if path not in dir_map:
                dir_name = Path(path).name
                if len(dir_name) > 25:
                    dir_name = dir_name[:22] + "..."
                
                node_idx = len(labels)
                labels.append(f"{dir_name}\n{self.format_size(size)}")
                colors.append(self._get_dir_color(dir_name, category_colors.get(category_name, '#6b7280')))
                dir_map[path] = node_idx
                
                # Conectar directamente a la raíz para simplificar
                source.append(0)
                target.append(node_idx)
                value.append(size)
                
                # Solo agregar un nivel de hijos para los más grandes
                if size > total_size * 0.1:  # Solo si es más del 10% del total
                    add_directory(path, node_idx, 1, 1)
        
        # Colores para enlaces
        link_colors = []
        base_color = category_colors.get(category_name, '#6b7280')
        for i in range(len(source)):
            if source[i] == 0:
                link_colors.append(f'{base_color}40')  # 25% opacity
            else:
                link_colors.append(f'{base_color}30')  # 19% opacity
        
        return {
            'labels': labels,
            'source': source,
            'target': target,
            'value': value,
            'colors': colors,
            'linkColors': link_colors,
            'categoryName': category_name,
            'totalSize': total_size
        }
    
    def _get_dir_color(self, dir_name: str, base_color: str) -> str:
        """Obtiene el color para un directorio basado en su tipo"""
        # Usar variaciones del color base de la categoría
        special_dirs = {
            'cache': '#ef4444',
            'logs': '#f97316',
            'tmp': '#f59e0b',
            'temp': '#f59e0b',
            'node_modules': '#84cc16',
            '.git': '#6366f1',
            'build': '#8b5cf6',
            'dist': '#a855f7'
        }
        
        dir_lower = dir_name.lower()
        for key, color in special_dirs.items():
            if key in dir_lower:
                return color
        
        return base_color
    
    def _prepare_sankey_data(self, report: Dict) -> Dict:
        """Prepara datos para el diagrama Sankey con conservación de flujo.
        Regla: para cada nodo, sum(outflows) == inflow. Si los hijos visibles
        no cubren el total del padre, se agrega un flujo residual 'otros'."""
        labels = []
        source = []
        target = []
        value = []
        colors = []

        color_map = {
            'root': '#1f2937',
            'containers': '#f59e0b',
            'docker': '#0db7ed',
            'cache': '#ef4444',
            'caches': '#ef4444',
            'application support': '#3b82f6',
            'developer': '#a855f7',
            'downloads': '#ec4899',
            'logs': '#f97316',
            'documents': '#10b981',
            'library': '#8b5cf6',
            'default': '#94a3b8'
        }

        root_path = str(Path(self.start_path).resolve())
        root_name = Path(root_path).name or 'Directorio'
        total_analyzed = report['summary']['total_size']

        labels.append(f"{root_name}\n{self.format_size(total_analyzed)}")
        colors.append(color_map.get(root_name.lower(), color_map['root']))

        # Construir mapa de hijos directos desde directory_sizes
        dir_children = defaultdict(list)
        for path, size in report['top_directories']:
            abs_path = str(Path(path).resolve())
            parent_path = str(Path(abs_path).parent)
            if abs_path != root_path:
                dir_children[parent_path].append((abs_path, size))

        dir_map = {root_path: 0}
        node_depths = {0: 0}  # Track depth (column) for each node
        node_sizes = {0: total_analyzed}
        node_parents = {}  # child_idx -> parent_idx

        def get_color(name):
            for key in color_map:
                if key in name.lower():
                    return color_map[key]
            return color_map['default']

        def add_directory(parent_path, parent_idx, parent_size, level=0, max_level=2):
            if level > max_level:
                return

            children = dir_children.get(parent_path, [])
            children.sort(key=lambda x: x[1], reverse=True)

            min_size = parent_size * 0.02
            max_children = 8 if level == 0 else 5

            shown_total = 0
            shown_count = 0

            for child_path, child_size in children:
                if child_path in dir_map:
                    continue
                if child_size < min_size or shown_count >= max_children:
                    break

                dir_name = Path(child_path).name
                if len(dir_name) > 30:
                    dir_name = dir_name[:27] + "..."

                node_idx = len(labels)
                labels.append(f"{dir_name}\n{self.format_size(child_size)}")
                colors.append(get_color(dir_name))
                dir_map[child_path] = node_idx
                node_depths[node_idx] = level + 1
                node_sizes[node_idx] = child_size
                node_parents[node_idx] = parent_idx

                source.append(parent_idx)
                target.append(node_idx)
                value.append(child_size)
                shown_total += child_size
                shown_count += 1

                add_directory(child_path, node_idx, child_size, level + 1, max_level)

            residual = parent_size - shown_total
            if shown_count > 0 and residual > parent_size * 0.05:
                otros_idx = len(labels)
                labels.append(f"otros\n{self.format_size(int(residual))}")
                colors.append('#d1d5db')
                node_depths[otros_idx] = level + 1
                node_sizes[otros_idx] = int(residual)
                node_parents[otros_idx] = parent_idx
                source.append(parent_idx)
                target.append(otros_idx)
                value.append(int(residual))

        add_directory(root_path, 0, total_analyzed)

        # Compute x/y positions to minimize crossings.
        # x = column based on depth, y = position within column sorted by
        # parent position first, then by size descending. This keeps children
        # adjacent to their parent and ordered by size.
        max_depth = max(node_depths.values()) if node_depths else 0
        node_x = {}
        node_y = {}

        if max_depth > 0:
            # Group nodes by depth
            depth_groups = defaultdict(list)
            for idx, depth in node_depths.items():
                depth_groups[depth].append(idx)

            # Sort each column: by parent's y-position, then by size descending
            # This ensures children are near their parent vertically
            for depth in range(max_depth + 1):
                nodes_at_depth = depth_groups[depth]
                if depth == 0:
                    # Root node centered
                    for idx in nodes_at_depth:
                        node_x[idx] = 0.001  # Plotly doesn't like exact 0
                        node_y[idx] = 0.001
                else:
                    # Sort by: parent y-position (primary), then size desc (secondary)
                    nodes_at_depth.sort(key=lambda idx: (
                        node_y.get(node_parents.get(idx, 0), 0),
                        -node_sizes.get(idx, 0)
                    ))

                    x_pos = min(depth / max_depth, 0.999)
                    total_size_at_depth = sum(node_sizes.get(idx, 0) for idx in nodes_at_depth)
                    y_cursor = 0.001

                    for idx in nodes_at_depth:
                        node_x[idx] = x_pos
                        node_y[idx] = min(y_cursor, 0.999)
                        # Space proportional to size
                        if total_size_at_depth > 0:
                            y_cursor += (node_sizes.get(idx, 0) / total_size_at_depth) * 0.998
                        else:
                            y_cursor += 1.0 / len(nodes_at_depth)
        
        # Calcular el contexto del disco
        disk_context = None
        if report.get('disk_usage') and report['disk_usage']['total'] > 0:
            disk_usage = report['disk_usage']
            disk_context = {
                'total': disk_usage['total'],
                'used': disk_usage['used'],
                'free': disk_usage['available'],
                'analyzed': total_analyzed,
                'percent_of_disk': (total_analyzed / disk_usage['total'] * 100) if disk_usage['total'] > 0 else 0,
                'percent_of_used': min((total_analyzed / disk_usage['used'] * 100) if disk_usage['used'] > 0 else 0, 100),
                'warning': total_analyzed > disk_usage['used']
            }
        
        # Si no hay suficientes nodos, agregar tipos de archivo principales
        if len(labels) < 5 and report.get('top_file_types'):
            # Crear un nodo para "Tipos de Archivo"
            file_types_idx = len(labels)
            total_file_size = sum(stats['size'] for _, stats in report['top_file_types'][:5])
            
            if total_file_size > 0:
                labels.append(f"Tipos de Archivo\n{self.format_size(total_file_size)}")
                colors.append('#6366f1')
                
                # Conectar a la raíz
                source.append(0)
                target.append(file_types_idx)
                value.append(total_file_size)
                
                # Agregar los tipos de archivo principales
                for ext, stats in report['top_file_types'][:5]:
                    if stats['size'] > 0:
                        type_idx = len(labels)
                        labels.append(f"{ext}\n{self.format_size(stats['size'])}")
                        colors.append('#94a3b8')
                        
                        source.append(file_types_idx)
                        target.append(type_idx)
                        value.append(stats['size'])
        
        # Colores para los enlaces (con transparencia)
        link_colors = []
        for i in range(len(source)):
            # Usar diferentes transparencias según el nivel
            if source[i] == 0:
                link_colors.append('rgba(99, 102, 241, 0.4)')
            else:
                link_colors.append('rgba(139, 92, 246, 0.3)')
        
        # Build position arrays for all nodes
        x_positions = [node_x.get(i, 0.5) for i in range(len(labels))]
        y_positions = [node_y.get(i, 0.5) for i in range(len(labels))]

        return {
            'labels': labels,
            'source': source,
            'target': target,
            'value': value,
            'colors': colors,
            'linkColors': link_colors,
            'nodeX': x_positions,
            'nodeY': y_positions,
            'diskContext': disk_context
        }
    
    def clean_docker(self, dry_run: bool = True):
        """Limpia recursos de Docker no utilizados"""
        if not self.docker_stats or not self.docker_stats['available']:
            print("🐳 Docker no está disponible en este sistema")
            return
            
        if self.docker_stats['reclaimable'] == 0:
            print("🐳 No hay espacio recuperable en Docker")
            return
            
        if dry_run:
            print("\n🐳 SIMULACIÓN DE LIMPIEZA DE DOCKER (dry-run):")
            print(f"   • Espacio recuperable: {self.format_size(self.docker_stats['reclaimable'])}")
            print("   • Se limpiarían:")
            if self.docker_stats['images'].get('reclaimable', 0) > 0:
                print(f"     - Imágenes no utilizadas: {self.format_size(self.docker_stats['images']['reclaimable'])}")
            if self.docker_stats['containers'].get('reclaimable', 0) > 0:
                print(f"     - Contenedores detenidos: {self.format_size(self.docker_stats['containers']['reclaimable'])}")
            if self.docker_stats['volumes'].get('reclaimable', 0) > 0:
                print(f"     - Volúmenes no utilizados: {self.format_size(self.docker_stats['volumes']['reclaimable'])}")
            if self.docker_stats['build_cache'].get('reclaimable', 0) > 0:
                print(f"     - Build cache: {self.format_size(self.docker_stats['build_cache']['reclaimable'])}")
            print("\n   Para ejecutar la limpieza real, usa --clean-docker sin --dry-run")
        else:
            print("\n🐳 LIMPIANDO DOCKER:")
            try:
                # Limpiar todo con docker system prune
                cmd = ['docker', 'system', 'prune', '-a', '--volumes', '-f']
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print("   ✓ Limpieza de Docker completada")
                    print(f"   ✓ Espacio liberado: ~{self.format_size(self.docker_stats['reclaimable'])}")
                    
                    # Mostrar detalles de la limpieza
                    if result.stdout:
                        lines = result.stdout.strip().split('\n')
                        for line in lines:
                            if 'deleted' in line.lower() or 'removed' in line.lower():
                                print(f"     - {line.strip()}")
                else:
                    print(f"   ✗ Error limpiando Docker: {result.stderr}")
            except Exception as e:
                print(f"   ✗ Error ejecutando limpieza de Docker: {e}")
    
    def clean_cache(self, dry_run: bool = True):
        """Limpia archivos de cache (con opción dry-run)"""
        if dry_run:
            print("\n🔍 SIMULACIÓN DE LIMPIEZA (dry-run):")
        else:
            print("\n🧹 LIMPIANDO ARCHIVOS DE CACHE:")
        
        total_cleaned = 0
        
        for cache_loc in self.cache_locations:
            path = Path(cache_loc['path'])
            
            # Solo limpiar ciertos tipos de cache automáticamente
            safe_to_clean = any(safe in cache_loc['type'] for safe in [
                'Cache General', 'Logs del Sistema', 'Downloads'
            ])
            
            if safe_to_clean and path.exists():
                if dry_run:
                    print(f"   • Limpiaría: {cache_loc['type']} - {self.format_size(cache_loc['size'])}")
                    total_cleaned += cache_loc['size']
                else:
                    try:
                        if path.is_file():
                            path.unlink()
                        else:
                            # Para directorios, solo limpiar contenido, no el directorio mismo
                            for item in path.rglob('*'):
                                if item.is_file():
                                    item.unlink()
                        print(f"   ✓ Limpiado: {cache_loc['type']} - {self.format_size(cache_loc['size'])}")
                        total_cleaned += cache_loc['size']
                    except Exception as e:
                        print(f"   ✗ Error limpiando {cache_loc['type']}: {e}")
        
        if dry_run:
            print(f"\n💡 Espacio que se liberaría: {self.format_size(total_cleaned)}")
            print("   Para ejecutar la limpieza real, usa --clean-cache sin --dry-run")
        else:
            print(f"\n✅ Espacio total liberado: {self.format_size(total_cleaned)}")


def analyze_all_drives():
    """Analiza todas las unidades disponibles en Windows"""
    if not IS_WINDOWS:
        print("❗ Esta función solo está disponible en Windows")
        return
    
    analyzer = DiskAnalyzer('C:\\', min_size_mb=50)
    drives = analyzer.get_all_drives()
    
    print(f"💿 Unidades detectadas: {', '.join(drives)}")
    print("\n" + "="*80 + "\n")
    
    all_reports = []
    
    for drive in drives:
        print(f"\n🔍 ANALIZANDO UNIDAD {drive}")
        print("=" * 40)
        
        try:
            drive_analyzer = DiskAnalyzer(drive, min_size_mb=50)
            report = drive_analyzer.analyze()
            
            if report:
                all_reports.append({
                    'drive': drive,
                    'report': report,
                    'disk_usage': drive_analyzer.disk_usage
                })
                
                # Mostrar resumen de la unidad
                print(f"\n📊 RESUMEN DE {drive}:")
                print(f"   • Espacio total: {drive_analyzer.format_size(drive_analyzer.disk_usage['total'])}")
                print(f"   • Espacio usado: {drive_analyzer.format_size(drive_analyzer.disk_usage['used'])} ({drive_analyzer.disk_usage['percent']:.1f}%)")
                print(f"   • Espacio libre: {drive_analyzer.format_size(drive_analyzer.disk_usage['available'])}")
                print(f"   • Archivos grandes encontrados: {len(drive_analyzer.large_files)}")
                
        except Exception as e:
            print(f"   ⚠️  Error analizando {drive}: {e}")
    
    # Generar reporte combinado
    if all_reports:
        print("\n" + "="*80)
        print("📊 RESUMEN TOTAL DE TODAS LAS UNIDADES:")
        print("=" * 80)
        
        total_used = sum(r['disk_usage']['used'] for r in all_reports)
        total_available = sum(r['disk_usage']['available'] for r in all_reports)
        total_space = sum(r['disk_usage']['total'] for r in all_reports)
        
        # Crear instancia temporal para usar format_size
        temp_analyzer = DiskAnalyzer('.')
        print(f"\n   • Espacio total en todas las unidades: {temp_analyzer.format_size(total_space)}")
        print(f"   • Espacio usado total: {temp_analyzer.format_size(total_used)} ({(total_used/total_space*100):.1f}%)")
        print(f"   • Espacio libre total: {temp_analyzer.format_size(total_available)}")
        
        # Generar HTML con todas las unidades
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = Path(f"disk_analysis_all_drives_{timestamp}.html")
        
        # Combinar todos los archivos grandes
        all_large_files = []
        for r in all_reports:
            analyzer = DiskAnalyzer(r['drive'])
            for f in r['report'].get('large_files', []):
                f['drive'] = r['drive']
                all_large_files.append(f)
        
        # Usar el primer analizador para generar el reporte HTML
        first_analyzer = DiskAnalyzer(drives[0])
        first_analyzer.large_files = all_large_files
        first_analyzer.generate_html_report({
            'total_size': total_used,
            'large_files': all_large_files,
            'summary': {
                'total_space': total_space,
                'total_used': total_used,
                'total_available': total_available,
                'drives_analyzed': len(drives)
            }
        }, report_path)
        
        print(f"\n📦 Reporte HTML generado: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Analizador de uso de disco multiplataforma con soporte para Docker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  %(prog)s ~/                    # Analizar directorio home
  %(prog)s C:\\                   # Analizar unidad C: en Windows
  %(prog)s --all-drives          # Analizar todas las unidades (Windows)
  %(prog)s /Applications         # Analizar aplicaciones
  %(prog)s ~/ --min-size 50      # Solo archivos > 50MB
  %(prog)s ~/ --export report    # Exportar a report.json
  %(prog)s ~/ --clean-cache      # Limpiar cache (con confirmación)
  %(prog)s ~/ --clean-docker     # Limpiar Docker
  %(prog)s ~/ --clean-all        # Limpiar cache y Docker
        """
    )
    
    parser.add_argument('path', nargs='?', default='.', help='Ruta a analizar (default: directorio actual)')
    parser.add_argument('--all-drives', action='store_true',
                        help='Analizar todas las unidades disponibles (solo Windows)')
    parser.add_argument('--min-size', type=float, default=10,
                        help='Tamaño mínimo de archivo a reportar en MB (default: 10)')
    parser.add_argument('--export', help='Exportar reporte a archivo JSON')
    parser.add_argument('--clean-cache', action='store_true',
                        help='Limpiar archivos de cache encontrados')
    parser.add_argument('--clean-docker', action='store_true',
                        help='Limpiar recursos de Docker no utilizados')
    parser.add_argument('--clean-all', action='store_true',
                        help='Limpiar cache y Docker')
    parser.add_argument('--dry-run', action='store_true',
                        help='Simular limpieza sin borrar archivos')
    parser.add_argument('--html', action='store_true',
                        help='Generar reporte HTML interactivo')
    parser.add_argument('--quick', action='store_true',
                        help='Solo generar reporte sin análisis completo')
    
    args = parser.parse_args()
    
    # Si se solicita analizar todas las unidades en Windows
    if args.all_drives:
        if not IS_WINDOWS:
            print("❗ La opción --all-drives solo está disponible en Windows")
            sys.exit(1)
        analyze_all_drives()
        return
    
    # Verificar que la ruta existe
    if not Path(args.path).exists():
        print(f"❌ Error: La ruta '{args.path}' no existe")
        sys.exit(1)
    
    # Crear analizador
    analyzer = DiskAnalyzer(args.path, args.min_size)
    
    # Si no es modo quick, ejecutar análisis
    if not args.quick:
        # Ejecutar análisis
        stats = analyzer.analyze()
        
        # Generar reporte
        report = analyzer.generate_report()
        
        # Mostrar reporte en consola
        analyzer.print_report(report)
        
        # Mostrar estadísticas de ejecución
        print(f"\n⏱️  Tiempo de análisis: {stats['elapsed_time']:.2f} segundos")
    else:
        # Modo quick: solo generar reportes sin análisis
        print("📄 Generando reporte rápido...")
        report = analyzer.generate_report()
    
    # Exportar si se solicita
    if args.export:
        if args.html:
            # Exportar a HTML
            html_filename = f"{args.export}.html" if not args.export.endswith('.html') else args.export
            analyzer.export_html(report, html_filename)
            
            # También exportar JSON para referencia
            json_filename = html_filename.replace('.html', '.json')
            analyzer.export_json(report, json_filename)
        else:
            # Solo exportar JSON
            filename = f"{args.export}.json" if not args.export.endswith('.json') else args.export
            analyzer.export_json(report, filename)
    
    # Limpiar si se solicita
    if args.clean_all or args.clean_cache:
        if not args.dry_run:
            response = input("\n⚠️  ¿Estás seguro de que quieres limpiar los archivos de cache? (s/N): ")
            if response.lower() != 's':
                print("Limpieza de cache cancelada.")
            else:
                analyzer.clean_cache(args.dry_run)
        else:
            analyzer.clean_cache(args.dry_run)
    
    if args.clean_all or args.clean_docker:
        if not args.dry_run:
            response = input("\n⚠️  ¿Estás seguro de que quieres limpiar Docker? (s/N): ")
            if response.lower() != 's':
                print("Limpieza de Docker cancelada.")
            else:
                analyzer.clean_docker(args.dry_run)
        else:
            analyzer.clean_docker(args.dry_run)


if __name__ == "__main__":
    main()