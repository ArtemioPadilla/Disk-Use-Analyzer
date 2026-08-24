"""`clean_cache` borraba `~/Downloads` según cómo se llamara el usuario.

Dos defectos distintos, verificados por separado:

1. `analyzer/cache_types.py::classify` comparaba subcadenas contra la ruta
   completa en minúsculas, nombre de usuario incluido. Con un usuario
   'logan', `~/Downloads` clasificaba como 'Logs del Sistema' -- una
   etiqueta en `SAFE_TO_CLEAN`. Con 'nicode', como 'VS Code Cache'. Con
   'anode', como 'NPM Cache'. Las tres están en `SAFE_TO_CLEAN`.
2. `DiskAnalyzer.clean_cache` (disk_analyzer.py) borraba con
   `path.rglob('*') + unlink()` -- permanente, sin papelera -- para
   cualquier `cache_loc` cuyo `type` estuviera en `SAFE_TO_CLEAN`, sin
   volver a consultar `protection.puede_borrarse`. Es la misma verja que
   `analyzer/comandos.py` instala para todo comando generado (Task 7); este
   método borra directamente, así que quedaba fuera de ella -- "una verja
   construida y no instalada", en la puerta de al lado.

Con los dos defectos activos a la vez, un usuario llamado 'logan' que
ejecutara `make clean-cache` perdía su carpeta de Descargas entera.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, '.')

from analyzer import cache_types
from disk_analyzer import DiskAnalyzer


# -- Dirección 1: classify() no debe dejar que el nombre de usuario decida --

def test_downloads_no_se_clasifica_como_logs_con_usuario_logan():
    assert cache_types.classify(Path('/Users/logan/Downloads')) == cache_types.DOWNLOADS


def test_downloads_no_se_clasifica_como_vscode_con_usuario_nicode():
    assert cache_types.classify(Path('/Users/nicode/Downloads')) == cache_types.DOWNLOADS


def test_downloads_no_se_clasifica_como_npm_con_usuario_anode():
    assert cache_types.classify(Path('/Users/anode/Downloads')) == cache_types.DOWNLOADS


def test_las_clasificaciones_legitimas_siguen_funcionando():
    """El fix de la dirección 1 no puede romper la clasificación real bajo
    el propio $HOME de quien corre el test."""
    home = Path.home()
    assert cache_types.classify(home / 'Library/Logs') == cache_types.LOGS
    assert cache_types.classify(home / '.npm') == cache_types.NPM
    assert cache_types.classify(home / 'Library/Application Support/Code/Cache') == cache_types.VSCODE
    assert cache_types.classify(home / 'Library/Developer/Xcode/DerivedData') == cache_types.XCODE
    assert cache_types.classify(home / '.Trash') == cache_types.TRASH


# -- Dirección 2: clean_cache debe consultar la verja antes de borrar --

def test_clean_cache_se_niega_a_borrar_una_ruta_que_la_verja_prohibe(tmp_path):
    """Reproduce el escenario: una ruta que classify() (con el bug) habría
    marcado como segura, pero que protection.puede_borrarse rechaza porque
    cae bajo una ruta de datos de usuario (~/Downloads vive bajo '~', que
    está en RUTAS_DE_DATOS_DE_USUARIO y no tiene excepción)."""
    analyzer = DiskAnalyzer('.')
    ruta_prohibida = '/Users/logan/Downloads'
    analyzer.cache_locations = [
        {'path': ruta_prohibida, 'size': 1000, 'type': cache_types.LOGS},
    ]

    with patch('disk_analyzer.Path.exists', return_value=True), \
         patch('disk_analyzer.Path.is_file', return_value=False), \
         patch('disk_analyzer.Path.rglob') as mock_rglob:
        analyzer.clean_cache(dry_run=False)
        mock_rglob.assert_not_called()


def test_clean_cache_borra_una_cache_legitima_que_la_verja_permite():
    """Simétrico: si la verja SÍ permite la ruta, clean_cache debe seguir
    intentando borrarla -- que el fix no se convierta en un no-op total."""
    home = str(Path.home())
    analyzer = DiskAnalyzer('.')
    ruta_permitida = f'{home}/Library/Caches/algo'
    analyzer.cache_locations = [
        {'path': ruta_permitida, 'size': 1000, 'type': cache_types.LOGS},
    ]

    with patch('disk_analyzer.Path.exists', return_value=True), \
         patch('disk_analyzer.Path.is_file', return_value=False), \
         patch('disk_analyzer.Path.rglob', return_value=[]) as mock_rglob:
        analyzer.clean_cache(dry_run=False)
        mock_rglob.assert_called_once()


def test_clean_cache_dry_run_tambien_respeta_la_verja(capsys):
    """El dry-run reporta 'se liberaría' sin borrar nada -- pero no debe
    contar una ruta prohibida como espacio recuperable."""
    analyzer = DiskAnalyzer('.')
    analyzer.cache_locations = [
        {'path': '/Users/logan/Downloads', 'size': 5_000_000, 'type': cache_types.LOGS},
    ]
    with patch('disk_analyzer.Path.exists', return_value=True):
        analyzer.clean_cache(dry_run=True)
    salida = capsys.readouterr().out
    assert 'Omitido' in salida
    assert '0.00 B' in salida or '0 B' in salida
