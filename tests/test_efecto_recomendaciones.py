"""Cada recomendación tiene que declarar qué hace su comando.

Hoy se mezclan tres cosas distintas bajo el mismo botón:
- borrados de ficheros, que podrían ir a la papelera;
- invocaciones a herramientas (`docker system prune`, `brew cleanup`), que
  borran por su cuenta y NO tienen papelera posible;
- diagnósticos (`du -sh`, `find -ls`), que no borran nada.

Sin este campo, la interfaz no puede prometer reversibilidad honestamente ni
distinguir "liberó espacio" de "te enseñó una lista".

Hay dos fuentes de recomendaciones que hay que cubrir por separado:
- `disk_analyzer_core.DiskAnalyzerCore.generate_recommendations` (motor
  compartido, usado por la web).
- `disk_analyzer.DiskAnalyzer.detect_smart_recommendations` (patrones
  avanzados de la CLI/app de bandeja: `disk_analyzer.py` es lo que invoca
  `desktop/src-tauri/src/analisis.rs`, no el core). La copia de
  `generate_recommendations` que también vive en `disk_analyzer.py` no se
  cubre aquí a propósito: un task posterior la sustituye por una delegación
  al core y heredará las etiquetas sola.
"""
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, '.')
from disk_analyzer_core import DiskAnalyzerCore
from disk_analyzer import DiskAnalyzer, MB, GB

EFECTOS = {'borra', 'irreversible', 'solo_lista'}


def _recomendaciones():
    core = DiskAnalyzerCore('.')
    core.find_cache_locations()
    return core.generate_recommendations()


def _recomendaciones_inteligentes():
    """Construye un DiskAnalyzer con estado sintético que dispara las 6
    detecciones de detect_smart_recommendations, sin tocar el disco real
    (salvo la llamada a `tmutil`, que se mockea)."""
    home = str(Path.home())
    analyzer = DiskAnalyzer('.')

    # 1. Entorno Conda obsoleto: env sin actividad reciente (>180 días)
    conda_env = f'{home}/miniconda3/envs/entorno_de_prueba'
    analyzer.directory_sizes[conda_env] = 500 * MB
    analyzer.large_files.append({
        'path': f'{conda_env}/lib/python3.11/algo.so',
        'size': 500 * MB, 'age_days': 200,
    })

    # 2. node_modules huérfano: sin .git/HEAD ni package.json en el padre
    node_modules = '/ruta_de_prueba_que_no_existe_xyz/proyecto/node_modules'
    analyzer.directory_sizes[node_modules] = 300 * MB

    # 3. Múltiples instalaciones de Python (Homebrew + Anaconda, ambas >100MB)
    analyzer.directory_sizes['/opt/homebrew/lib/python3.11'] = 150 * MB
    analyzer.directory_sizes['/opt/anaconda3/lib/python3.11'] = 150 * MB

    # 4. Repo git con pack files grandes (>100MB)
    analyzer.large_files.append({
        'path': '/ruta_de_prueba_repo/.git/objects/pack/pack-abc123.pack',
        'size': 150 * MB, 'age_days': 5,
    })

    # 5. Snapshots locales de Time Machine (mockeado, no toca el sistema real)
    fake_tmutil = subprocess.CompletedProcess(
        args=['tmutil', 'listlocalsnapshots', '/'], returncode=0,
        stdout='com.apple.TimeMachine.2024-01-01-000000.local\n',
    )

    # 6. Xcode Archives antiguos (>1GB)
    xcode_archives = f'{home}/Library/Developer/Xcode/Archives'
    analyzer.directory_sizes[f'{xcode_archives}/2024-01-01/App.xcarchive'] = 2 * GB

    with patch('disk_analyzer.subprocess.run', return_value=fake_tmutil):
        return analyzer.detect_smart_recommendations()


def test_toda_recomendacion_declara_su_efecto():
    for r in _recomendaciones():
        assert r.get('efecto') in EFECTOS, (
            f"{r.get('type')} no declara efecto válido: {r.get('efecto')!r}"
        )


def test_los_comandos_que_solo_listan_estan_marcados():
    """`du -sh` y `find -ls` no borran; acreditarles ahorro es mentir."""
    for r in _recomendaciones():
        cmd = r.get('command', '')
        if cmd.startswith('du ') or ' -ls' in cmd:
            assert r['efecto'] == 'solo_lista', (
                f"{r['type']} ejecuta un diagnóstico pero no está marcado"
            )


def test_las_herramientas_externas_son_irreversibles():
    """Nada de esto se puede mandar a la papelera."""
    for r in _recomendaciones():
        cmd = r.get('command', '')
        if any(t in cmd for t in ('docker system prune', 'brew cleanup',
                                  'npm cache clean', 'simctl delete')):
            assert r['efecto'] == 'irreversible', (
                f"{r['type']} invoca una herramienta externa: no hay papelera"
            )


def test_toda_recomendacion_inteligente_declara_su_efecto():
    """detect_smart_recommendations es una fuente propia (CLI + app de
    bandeja, via disk_analyzer.py) y tiene que declarar 'efecto' igual que
    el motor compartido."""
    recs = _recomendaciones_inteligentes()
    tipos_esperados = {
        'Entorno Conda Obsoleto', 'node_modules Huerfano',
        'Multiples Instalaciones Python', 'Git Pack Files Grandes',
        'Snapshots Locales de Time Machine', 'Xcode Archives Antiguos',
    }
    tipos_encontrados = {r['type'] for r in recs}
    assert tipos_esperados <= tipos_encontrados, (
        f"El estado sintético no disparó todas las detecciones esperadas: "
        f"faltan {tipos_esperados - tipos_encontrados}"
    )
    for r in recs:
        assert r.get('efecto') in EFECTOS, (
            f"{r.get('type')} no declara efecto válido: {r.get('efecto')!r}"
        )


def test_recomendaciones_inteligentes_con_efecto_correcto():
    """Cada detección inteligente clasificada según su comando real."""
    esperado = {
        'Entorno Conda Obsoleto': 'irreversible',       # conda env remove
        'node_modules Huerfano': 'borra',                # comandos.borrar_rutas
        'Multiples Instalaciones Python': 'solo_lista',  # comentario, no acción
        'Git Pack Files Grandes': 'irreversible',        # git gc --aggressive
        'Snapshots Locales de Time Machine': 'irreversible',  # tmutil
        'Xcode Archives Antiguos': 'borra',              # comandos.borrar_contenido
    }
    recs = {r['type']: r for r in _recomendaciones_inteligentes()}
    for tipo, efecto in esperado.items():
        assert tipo in recs, f"No se disparó la detección: {tipo}"
        assert recs[tipo]['efecto'] == efecto, (
            f"{tipo}: esperaba efecto={efecto!r}, encontré {recs[tipo].get('efecto')!r}"
        )
