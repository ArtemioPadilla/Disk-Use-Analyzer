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
import stat as stat_module
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Callable

from analyzer.constants import (
    KB, MB, GB, SYSTEM, IS_WINDOWS, IS_MACOS, IS_LINUX,
    CACHE_DIRS, LARGE_FILE_EXTENSIONS, IGNORE_PATTERNS, MACOS_APFS_SKIP_DIRS,
)
from analyzer import protection
from analyzer import cache_types
from analyzer import measurement
from analyzer import comandos

class DiskAnalyzerCore:
    """Core disk analysis functionality with progress callback support"""
    
    def __init__(self, start_path: str, min_size_mb: float = 10, 
                 progress_callback: Optional[Callable] = None):
        self.start_path = Path(start_path).expanduser()
        # Floor at 1 MB, matching disk_analyzer.DiskAnalyzer -- a min_size
        # of 0 would treat every file as "large" and also produces a
        # nonsensical 'find ... -size +0M' filter in the Descargas Antiguas
        # command (matches everything, defeating the point of the filter).
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
        """Delegates to the shared implementation (kept for callers)."""
        return protection.is_protected_path(file_path)
    
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
                    # lstat() nunca sigue symlinks (a diferencia de is_file()/stat()
                    # sin argumentos), y no depende del kwarg follow_symlinks= que
                    # solo existe en pathlib desde Python 3.13.
                    item_stat = item.lstat()
                    if stat_module.S_ISREG(item_stat.st_mode):
                        # Usar st_blocks * 512 para obtener el espacio real en disco
                        size = item_stat.st_blocks * 512 if hasattr(item_stat, 'st_blocks') else item_stat.st_size
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

                    elif stat_module.S_ISDIR(item_stat.st_mode):
                        # No seguir enlaces simbólicos a directorios: lstat() ya
                        # reporta el enlace en sí (no el destino), así que un
                        # symlink a directorio nunca cumple S_ISDIR aquí.
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
                    if size > MB:  # Solo reportar si es mayor a 1MB (igual que el CLI)
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
        """Calcula el tamaño de un directorio (delega en analyzer.measurement,
        la misma implementación que usa el CLI)."""
        return measurement.get_directory_size(directory)
    
    def categorize_cache(self, path: Path) -> str:
        """Categoriza el tipo de cache. Delega en el clasificador compartido
        (analyzer.cache_types) para que CLI, web y GUI usen las mismas
        etiquetas."""
        return cache_types.classify(path)
    
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
        """Parse docker size strings like '1.5GB', '2.796kB', '500MB (45%)' to bytes"""
        import re
        try:
            clean = size_str.strip().split('(')[0].strip()
            match = re.match(r'([\d.]+)\s*([KMGTk]?B)', clean)
            if not match:
                return 0
            value = float(match.group(1))
            unit = match.group(2).upper()
            multipliers = {'B': 1, 'KB': KB, 'MB': MB, 'GB': GB, 'TB': GB * 1024}
            return int(value * multipliers.get(unit, 1))
        except (ValueError, AttributeError):
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
        """Genera recomendaciones agrupadas por nivel de agresividad (4 tiers).

        This is the single source of these tiered rules. It used to be
        duplicated in disk_analyzer.py (CLI + menu-bar app), and the two
        copies had already drifted -- the web UI and the menu-bar app could
        recommend different things for the same disk. disk_analyzer.py now
        delegates here; its own detect_smart_recommendations() (advanced
        pattern-based detections: stale conda envs, orphan node_modules,
        etc.) stays CLI-only and is appended on top of what this returns.

        Every recommendation carries a stable 'id' slug so callers (and
        future per-rule config) don't have to match on the Spanish display
        'type' string, which can change and already differed between the
        two former copies.
        """
        recommendations = []

        # TIER 1: Seguro
        log_locs = [l for l in self.cache_locations if l['type'] == cache_types.LOGS]
        if log_locs and sum(l['size'] for l in log_locs) > 10 * MB:
            recommendations.append({'id': 'logs', 'tier': 1, 'priority': 'Seguro', 'type': cache_types.LOGS,
                'description': f'{self.format_size(sum(l["size"] for l in log_locs))} en logs',
                'space': sum(l['size'] for l in log_locs),
                'command': comandos.borrar_contenido([l['path'] for l in log_locs]),
                'efecto': 'borra'})

        brew_files = [f for f in self.large_files if 'Homebrew/downloads' in f['path']]
        if brew_files:
            size = sum(f['size'] for f in brew_files)
            recommendations.append({'id': 'homebrew', 'tier': 1, 'priority': 'Seguro', 'type': 'Cache de Homebrew',
                'description': f'{len(brew_files)} descargas ({self.format_size(size)})',
                'space': size, 'command': 'brew cleanup --prune=all',
                'efecto': 'irreversible'})

        vscode_locs = [l for l in self.cache_locations if l['type'] == cache_types.VSCODE]
        if vscode_locs and sum(l['size'] for l in vscode_locs) > 10 * MB:
            recommendations.append({'id': 'vscode', 'tier': 1, 'priority': 'Seguro', 'type': 'Cache de VS Code',
                'description': f'{self.format_size(sum(l["size"] for l in vscode_locs))} en cache',
                'space': sum(l['size'] for l in vscode_locs),
                'command': comandos.borrar_contenido([l['path'] for l in vscode_locs]),
                'efecto': 'borra'})

        npm_locs = [l for l in self.cache_locations if l['type'] == cache_types.NPM]
        if npm_locs and sum(l['size'] for l in npm_locs) > 50 * MB:
            recommendations.append({'id': 'npm', 'tier': 1, 'priority': 'Seguro', 'type': 'Cache de npm',
                'description': f'{self.format_size(sum(l["size"] for l in npm_locs))} en cache de npm (se regenera con npm install)',
                'space': sum(l['size'] for l in npm_locs), 'command': 'npm cache clean --force',
                'efecto': 'irreversible'})

        # TIER 2: Moderado
        # This rule used to exist in both copies under different display
        # names ('Cache de Simuladores' here, 'Cache de Simuladores iOS' in
        # the CLI) but with the identical condition, tier and command --
        # same rule, drifted label. Unified under the core's label.
        sim_files = [f for f in self.large_files
                     if 'CoreSimulator' in f['path'] and not self.is_protected_path(f['path'])]
        if sim_files:
            recommendations.append({'id': 'simuladores', 'tier': 2, 'priority': 'Moderado', 'type': 'Cache de Simuladores',
                'description': f'{len(sim_files)} archivos ({self.format_size(sum(f["size"] for f in sim_files))})',
                'space': sum(f['size'] for f in sim_files),
                'command': 'xcrun simctl delete unavailable && rm -rf ~/Library/Developer/CoreSimulator/Caches/',
                'efecto': 'irreversible'})

        old_downloads = [f for f in self.large_files if '/Downloads/' in f['path'] and f['age_days'] > 30]
        if old_downloads:
            size = sum(f['size'] for f in old_downloads)
            # Fold in the user's configured min_size (self.min_size, in bytes,
            # set in __init__ with a 10 MB default) so the diagnostic only
            # lists files worth reviewing -- without this, "old downloads"
            # includes every tiny file older than 30 days, which is a
            # longer and less useful list than what the CLI used to show.
            min_size_mb = int(self.min_size / MB)
            recommendations.append({'id': 'descargas_antiguas', 'tier': 2, 'priority': 'Moderado', 'type': 'Descargas Antiguas',
                'description': f'{len(old_downloads)} archivos en Downloads con más de 30 días ({self.format_size(size)})',
                'space': size, 'command': f'find ~/Downloads -mtime +30 -size +{min_size_mb}M -type f -ls',
                'efecto': 'solo_lista'})

        if self.docker_stats and self.docker_stats['available'] and self.docker_stats['reclaimable'] > 100 * MB:
            recommendations.append({'id': 'docker', 'tier': 2, 'priority': 'Moderado', 'type': 'Docker',
                'description': f'{self.format_size(self.docker_stats["reclaimable"])} recuperable de {self.format_size(self.docker_stats.get("total_size", 0))} total',
                'space': self.docker_stats['reclaimable'], 'command': 'docker system prune -a -f',
                'efecto': 'irreversible'})

        # TIER 3: Agresivo
        cache_general = [l for l in self.cache_locations if l['type'] == cache_types.GENERAL and '/.cache' in l['path']]
        if cache_general and sum(l['size'] for l in cache_general) > 100 * MB:
            recommendations.append({'id': 'cache_general', 'tier': 3, 'priority': 'Agresivo', 'type': 'Cache General (~/.cache)',
                'description': f'{self.format_size(sum(l["size"] for l in cache_general))} en ~/.cache (modelos ML, pip, etc. — se re-descargan)',
                'space': sum(l['size'] for l in cache_general),
                'command': 'du -sh ~/.cache/*/ | sort -hr | head -20',
                'efecto': 'solo_lista'})

        # Moved here from the CLI-only copy of this method (it existed only
        # there, so it would have silently disappeared for web users -- and
        # from the menu-bar app too, once the CLI stopped duplicating it).
        #
        # IMPORTANT: cache_types.XCODE covers BOTH
        # ~/Library/Developer/Xcode/DerivedData AND .../Xcode/Archives
        # (classify() matches on the substring 'xcode' anywhere in the path,
        # see analyzer/cache_types.py). Archives hold signed builds and
        # dSYMs needed to symbolicate crashes from already-shipped versions
        # -- they do NOT regenerate on build, unlike DerivedData. Filtering
        # cache_locations by type alone here would silently fold Archives
        # into an 'efecto: borra' rule described as "se regeneran al
        # compilar", which is false and irreversible for real archived
        # builds. detect_smart_recommendations() already has an honest,
        # size-gated rule for Archives ('Xcode Archives Antiguos', id
        # 'xcode_archives_antiguos'), so this rule stays scoped to
        # DerivedData only -- widening it to Archives would also
        # double-count recoverable space against that other rule.
        xcode_locs = [l for l in self.cache_locations
                      if l['type'] == cache_types.XCODE and 'DerivedData' in l['path']]
        if xcode_locs and sum(l['size'] for l in xcode_locs) > 100 * MB:
            recommendations.append({'id': 'xcode_deriveddata', 'tier': 3, 'priority': 'Agresivo', 'type': 'Xcode DerivedData',
                'description': f'{self.format_size(sum(l["size"] for l in xcode_locs))} en datos de compilación (se regeneran al compilar)',
                'space': sum(l['size'] for l in xcode_locs),
                'command': comandos.borrar_contenido([l['path'] for l in xcode_locs]),
                'efecto': 'borra'})

        # Moved here from the CLI-only copy (see comment above).
        sim_runtimes = [f for f in self.large_files
                        if 'iOSSimulatorRuntime' in f['path'] or 'SimRuntime' in f['path']]
        if sim_runtimes and sum(f['size'] for f in sim_runtimes) > GB:
            recommendations.append({'id': 'runtimes_simuladores', 'tier': 3, 'priority': 'Agresivo', 'type': 'Runtimes de Simuladores',
                'description': f'{self.format_size(sum(f["size"] for f in sim_runtimes))} en runtimes de iOS Simulator (eliminar desde Xcode > Settings > Platforms)',
                'space': sum(f['size'] for f in sim_runtimes),
                'command': 'xcrun simctl runtime list',
                'efecto': 'solo_lista'})

        # TIER 4: Máximo
        huge = [f for f in self.large_files if f['size'] > GB and not self.is_protected_path(f['path'])]
        if huge:
            recommendations.append({'id': 'archivos_gigantes', 'tier': 4, 'priority': 'Máximo', 'type': 'Archivos Gigantes',
                'description': f'{len(huge)} archivos > 1GB ({self.format_size(sum(f["size"] for f in huge))})',
                'space': sum(f['size'] for f in huge), 'command': '# Revisa la lista de archivos grandes',
                'efecto': 'solo_lista'})

        # Moved here from the CLI-only copy (see comment above).
        vm_files = [f for f in self.large_files
                    if any(ext in f['extension'] for ext in ['.vmdk', '.vdi', '.qcow2'])]
        if vm_files:
            recommendations.append({'id': 'maquinas_virtuales', 'tier': 4, 'priority': 'Máximo', 'type': 'Máquinas Virtuales',
                'description': f'{len(vm_files)} archivos de VMs ({self.format_size(sum(f["size"] for f in vm_files))})',
                'space': sum(f['size'] for f in vm_files),
                'command': 'find / -name "*.vmdk" -o -name "*.vdi" -o -name "*.qcow2" 2>/dev/null | head -20',
                'efecto': 'solo_lista'})

        return sorted(recommendations, key=lambda x: (x['tier'], -x['space']))
    
    def _get_cleanup_command_for_downloads(self) -> str:
        """Get platform-specific cleanup command for downloads"""
        if self.is_windows:
            return f'forfiles /P "%USERPROFILE%\\Downloads" /D -30 /C "cmd /c if @fsize gtr {int(self.min_size)} del @path"'
        else:
            return f"find ~/Downloads -mtime +30 -size +{int(self.min_size/MB)}M -type f -delete"