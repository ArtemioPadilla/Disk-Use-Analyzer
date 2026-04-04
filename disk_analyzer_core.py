#!/usr/bin/env python3
"""
Core disk analysis functionality
Separated from CLI for use in GUI and other interfaces
"""

import os
import sys
import json
import time
import subprocess
import platform
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Callable

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

# Protección de archivos del sistema
PROTECTED_PATH_PREFIXES = [
    '/System/Volumes/', '/private/var/vm/', '/var/vm/',
    '/System/Library/', '/usr/lib/', '/usr/bin/', '/usr/sbin/',
    '/Library/Updates/', '/private/var/folders/',
]
PROTECTED_APP_MARKERS = ['.app/', '.AppBundle/']
PROTECTED_FILENAMES = {'sleepimage', 'swapfile'}
PROTECTED_ROOT_DIRS = {'/bin', '/sbin'}

class DiskAnalyzerCore:
    """Core disk analysis functionality with progress callback support"""
    
    def __init__(self, start_path: str, min_size_mb: float = 10, 
                 progress_callback: Optional[Callable] = None):
        self.start_path = Path(start_path).expanduser()
        self.min_size = min_size_mb * MB
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
        self.progress_callback = progress_callback
        self._cancel_flag = False
        
    def cancel_analysis(self):
        """Cancel the ongoing analysis"""
        self._cancel_flag = True
        
    def _update_progress(self, message: str, percent: float = None, 
                        current_file: str = None, phase: str = None):
        """Update progress through callback if provided"""
        if self.progress_callback and not self._cancel_flag:
            self.progress_callback({
                'message': message,
                'percent': percent,
                'current_file': current_file,
                'files_scanned': self.total_scanned,
                'large_files_found': len(self.large_files),
                'errors': len(self.errors),
                'phase': phase or 'disk_scan'
            })
    
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
        if self.is_windows:
            if path.name in ['pagefile.sys', 'hiberfil.sys', 'swapfile.sys']:
                return True
        if self.is_macos:
            if path_str in MACOS_APFS_SKIP_DIRS:
                return True
        return any(pattern in path_str for pattern in IGNORE_PATTERNS)

    def is_protected_path(self, file_path: str) -> bool:
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
    
    def get_home_dir(self) -> Path:
        """Obtiene el directorio home según el sistema"""
        return Path.home()
    
    def get_all_drives(self) -> List[Dict[str, any]]:
        """Obtiene todas las unidades disponibles con información"""
        drives = []
        if self.is_windows:
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    try:
                        usage = shutil.disk_usage(drive)
                        drives.append({
                            'path': drive,
                            'letter': letter,
                            'total': usage.total,
                            'used': usage.used,
                            'free': usage.free,
                            'percent': (usage.used / usage.total * 100) if usage.total > 0 else 0
                        })
                    except:
                        pass
        else:
            # En Unix-like, usar el sistema de archivos raíz
            usage = shutil.disk_usage('/')
            drives.append({
                'path': '/',
                'letter': '/',
                'total': usage.total,
                'used': usage.used,
                'free': usage.free,
                'percent': (usage.used / usage.total * 100) if usage.total > 0 else 0
            })
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
    
    def scan_directory(self, directory: Path, depth: int = 0, max_depth: int = None) -> int:
        """Escanea un directorio y retorna su tamaño total"""
        if self._cancel_flag:
            return 0
            
        total_size = 0
        
        try:
            items = list(directory.iterdir())
            total_items = len(items)
            
            # Always update progress with current directory
            self._update_progress(
                f"Scanning: {str(directory)}",
                None,  # No percentage during scan
                current_file=str(directory)
            )
            
            for idx, item in enumerate(items):
                if self._cancel_flag:
                    break
                    
                if self.should_ignore(item):
                    continue
                
                # Update progress more frequently
                if idx % 5 == 0 or depth <= 3 or total_items < 50:  # Update every 5 items, for top directories, or small dirs
                    self._update_progress(
                        f"Scanning: {directory.name}",
                        None,  # Don't send percentage during directory scan
                        str(item)
                    )
                    
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
                            if max_depth is None or depth < max_depth:
                                dir_size = self.scan_directory(item, depth + 1, max_depth)
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
        self._update_progress("Searching for cache locations...", 70, phase="cache_scan")
        
        total_cache_dirs = len(CACHE_DIRS)
        for idx, cache_dir in enumerate(CACHE_DIRS):
            if self._cancel_flag:
                break
                
            # Only update percentage at major milestones
            if idx % 5 == 0 or idx == total_cache_dirs - 1:
                percent = 70 + (idx / total_cache_dirs * 20) if total_cache_dirs else 70
            else:
                percent = None
                
            self._update_progress(
                f"Checking cache: {cache_dir}", 
                percent,
                current_file=cache_dir,
                phase="cache_scan"
            )
            
            path = Path(cache_dir).expanduser()
            if path.exists():
                try:
                    self._update_progress(
                        f"Calculating size of: {path.name}",
                        None,  # No percentage during size calculation
                        current_file=str(path),
                        phase="cache_scan"
                    )
                    size = self.get_directory_size(path)
                    if size > 0:
                        cache_type = self.categorize_cache(path)
                        self.cache_locations.append({
                            'path': str(path),
                            'size': size,
                            'type': cache_type
                        })
                        self._update_progress(
                            f"Found {cache_type}: {self.format_size(size)}",
                            None,  # No percentage for individual finds
                            current_file=str(path),
                            phase="cache_scan"
                        )
                except:
                    pass
    
    def get_directory_size(self, directory: Path) -> int:
        """Calcula el tamaño de un directorio"""
        total_size = 0
        try:
            for entry in directory.rglob('*'):
                if entry.is_file(follow_symlinks=False):
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        total_size += stat.st_blocks * 512 if hasattr(stat, 'st_blocks') else stat.st_size
                    except:
                        pass
        except:
            pass
        return total_size
    
    def categorize_cache(self, path: Path) -> str:
        """Categoriza el tipo de cache"""
        path_str = str(path).lower()
        
        if 'code' in path_str or 'vscode' in path_str:
            return 'VS Code Cache'
        elif 'chrome' in path_str:
            return 'Chrome Cache'
        elif 'firefox' in path_str or 'mozilla' in path_str:
            return 'Firefox Cache'
        elif 'npm' in path_str or 'node' in path_str:
            return 'NPM Cache'
        elif 'pip' in path_str or 'python' in path_str:
            return 'Python Cache'
        elif 'xcode' in path_str:
            return 'Xcode Cache'
        elif 'docker' in path_str:
            return 'Docker'
        elif 'trash' in path_str or 'recycle' in path_str:
            return 'Papelera'
        elif 'temp' in path_str or 'tmp' in path_str:
            return 'Archivos Temporales'
        elif 'log' in path_str:
            return 'Logs del Sistema'
        elif 'download' in path_str:
            return 'Downloads'
        else:
            return 'Cache General'
    
    def get_disk_usage(self, path: Optional[str] = None) -> Dict:
        """Obtiene el uso total del disco de forma multiplataforma"""
        try:
            if path is None:
                path = str(self.start_path)
            
            if self.is_windows:
                # En Windows, usar shutil.disk_usage
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
    
    def analyze_docker(self):
        """Analiza el uso de espacio de Docker"""
        self._update_progress("Checking Docker availability...", 90, phase="docker_analysis")
        
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
                        self._update_progress("Docker not found", 95, phase="docker_analysis")
                        return docker_stats
            
            self._update_progress("Connecting to Docker daemon...", 91, phase="docker_analysis")
            result = subprocess.run([docker_cmd, 'version'], capture_output=True, text=True)
            if result.returncode != 0:
                self._update_progress("Docker daemon not running", 95, phase="docker_analysis")
                return docker_stats
                
            docker_stats['available'] = True
            self._update_progress("Docker connected, analyzing resources...", 92, phase="docker_analysis")
            
            # Obtener información del sistema Docker
            self._update_progress("Analyzing Docker resources...", 93, phase="docker_analysis")
            result = subprocess.run([docker_cmd, 'system', 'df'], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # Skip header
                    parts = line.split()
                    if parts and parts[0] == 'Images':
                        docker_stats['images']['size'] = self.parse_docker_size(parts[3])
                        docker_stats['images']['reclaimable'] = self.parse_docker_size(parts[4])
                        self._update_progress(
                            f"Docker images: {parts[3]} (reclaimable: {parts[4]})",
                            None,  # No percentage for individual items
                            phase="docker_analysis"
                        )
                    elif parts and parts[0] == 'Containers':
                        docker_stats['containers']['size'] = self.parse_docker_size(parts[3])
                        docker_stats['containers']['reclaimable'] = self.parse_docker_size(parts[4])
                        self._update_progress(
                            f"Docker containers: {parts[3]} (reclaimable: {parts[4]})",
                            None,  # No percentage for individual items
                            phase="docker_analysis"
                        )
                    elif parts and parts[0] == 'Local' and parts[1] == 'Volumes':
                        docker_stats['volumes']['size'] = self.parse_docker_size(parts[4])
                        docker_stats['volumes']['reclaimable'] = self.parse_docker_size(parts[5])
                        self._update_progress(
                            f"Docker volumes: {parts[4]} (reclaimable: {parts[5]})",
                            None,  # No percentage for individual items
                            phase="docker_analysis"
                        )
                    elif parts and parts[0] == 'Build' and parts[1] == 'Cache':
                        docker_stats['build_cache']['size'] = self.parse_docker_size(parts[3])
                        docker_stats['build_cache']['reclaimable'] = self.parse_docker_size(parts[4])
                        self._update_progress(
                            f"Docker build cache: {parts[3]} (reclaimable: {parts[4]})",
                            None,  # No percentage for individual items
                            phase="docker_analysis"
                        )
            
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
            
            self._update_progress(
                f"Docker total: {self.format_size(docker_stats['total_size'])} (reclaimable: {self.format_size(docker_stats['reclaimable'])})",
                95,  # Final Docker percentage
                phase="docker_analysis"
            )
            
        except Exception as e:
            self.errors.append(f"Error analizando Docker: {e}")
            
        self.docker_stats = docker_stats
        return docker_stats
    
    def parse_docker_size(self, size_str: str) -> int:
        """Convierte el formato de tamaño de Docker a bytes"""
        try:
            # Remove parentheses if present
            size_str = size_str.strip('()')
            
            # Split value and unit
            parts = size_str.split()
            if len(parts) != 2:
                return 0
                
            value = float(parts[0])
            unit = parts[1].upper()
            
            # Convert to bytes
            if unit == 'B':
                return int(value)
            elif unit == 'KB' or unit == 'KB':
                return int(value * KB)
            elif unit == 'MB':
                return int(value * MB)
            elif unit == 'GB':
                return int(value * GB)
            elif unit == 'TB':
                return int(value * GB * 1024)
            else:
                return 0
        except Exception as e:
            return 0
    
    def analyze(self) -> Dict:
        """Ejecuta el análisis completo con soporte para callbacks"""
        self._cancel_flag = False
        start_time = time.time()
        
        # Obtener uso del disco
        self._update_progress("Getting disk usage...", 0)
        self.disk_usage = self.get_disk_usage()
        
        # Escanear directorio principal
        self._update_progress("Starting directory scan...", 5)
        total_size = self.scan_directory(self.start_path)
        self.directory_sizes[str(self.start_path)] = total_size
        
        if self._cancel_flag:
            return None
        
        # Buscar ubicaciones de cache
        self._update_progress("Finding cache locations...", 70)
        self.find_cache_locations()
        
        if self._cancel_flag:
            return None
        
        # Analizar Docker
        self._update_progress("Analyzing Docker...", 90)
        self.analyze_docker()
        
        elapsed_time = time.time() - start_time
        
        self._update_progress("Analysis complete!", 100)
        
        return {
            'total_size': total_size,
            'elapsed_time': elapsed_time,
            'files_scanned': self.total_scanned,
            'errors': len(self.errors)
        }
    
    def generate_report(self) -> Dict:
        """Genera un reporte completo del análisis"""
        # Ordenar archivos grandes por tamaño
        self.large_files.sort(key=lambda x: x['size'], reverse=True)
        
        # Calcular espacio recuperable
        cache_size = sum(loc['size'] for loc in self.cache_locations)
        old_files_size = sum(
            f['size'] for f in self.large_files 
            if f['age_days'] > 180
        )
        
        recoverable_space = cache_size + old_files_size
        
        # Agregar espacio recuperable de Docker
        if self.docker_stats and self.docker_stats['available']:
            recoverable_space += self.docker_stats['reclaimable']
        
        # Top directorios por tamaño
        top_dirs = sorted(
            self.directory_sizes.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:20]
        
        # Top extensiones por tamaño
        top_extensions = sorted(
            self.file_type_stats.items(),
            key=lambda x: x[1]['size'],
            reverse=True
        )[:10]
        
        # Generar recomendaciones
        recommendations = self.generate_recommendations()
        
        return {
            'summary': {
                'total_size': self.directory_sizes.get(str(self.start_path), 0),
                'files_scanned': self.total_scanned,
                'large_files_count': len(self.large_files),
                'cache_size': cache_size,
                'old_files_size': old_files_size,
                'recoverable_space': recoverable_space,
                'errors_count': len(self.errors),
                'disk_usage': self.disk_usage,
                'docker_space': self.docker_stats['total_size'] if self.docker_stats else 0,
                'docker_reclaimable': self.docker_stats['reclaimable'] if self.docker_stats else 0
            },
            'large_files': [
                {**f, 'is_protected': self.is_protected_path(f['path'])}
                for f in self.large_files[:100]
            ],
            'cache_locations': self.cache_locations,
            'top_directories': top_dirs,
            'file_types': top_extensions,
            'recommendations': recommendations,
            'docker': self.docker_stats,
            'errors': self.errors[:50]  # Primeros 50 errores
        }
    
    def generate_recommendations(self) -> List[Dict]:
        """Genera recomendaciones de limpieza"""
        recommendations = []
        
        # Cache del sistema
        cache_size = sum(loc['size'] for loc in self.cache_locations)
        if cache_size > 100 * MB:
            cache_commands = []
            for loc in self.cache_locations:
                if any(safe in loc['type'] for safe in ['Cache General', 'Logs del Sistema']):
                    if self.is_windows:
                        cache_commands.append(f'del /f /s /q "{loc["path"]}\\*"')
                    else:
                        cache_commands.append(f"rm -rf '{loc['path']}/*'")
            
            recommendations.append({
                'priority': 'Alta',
                'type': 'Cache del Sistema',
                'description': f'Puedes liberar {self.format_size(cache_size)} eliminando archivos de cache',
                'action': 'Ejecuta el script con --clean-cache para limpiar automáticamente',
                'space': cache_size,
                'command': ' && '.join(cache_commands[:3]) if cache_commands else 'clean cache'
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
                'command': self._get_cleanup_command_for_downloads()
            })
        
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
        
        return recommendations
    
    def _get_cleanup_command_for_downloads(self) -> str:
        """Get platform-specific cleanup command for downloads"""
        if self.is_windows:
            return f'forfiles /P "%USERPROFILE%\\Downloads" /D -30 /C "cmd /c if @fsize gtr {int(self.min_size)} del @path"'
        else:
            return f"find ~/Downloads -mtime +30 -size +{int(self.min_size/MB)}M -type f -delete"