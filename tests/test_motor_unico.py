"""La CLI y la web tienen que ver las mismas recomendaciones.

Hoy hay dos copias: `disk_analyzer_core.py:561` la usa la web y
`disk_analyzer.py:888` la usan la CLI y la app de bandeja. La app de bandeja
ejecuta `disk_analyzer.py`, así que la barra y la web pueden recomendar cosas
distintas del mismo disco.

Además, ninguna recomendación tiene identificador estable: `type` es una cadena
de display en español y ya difiere entre copias ('Cache de Simuladores' contra
'Cache de Simuladores iOS'). Sin `id` no se puede configurar nada.
"""
import sys

sys.path.insert(0, '.')
from disk_analyzer import DiskAnalyzer, MB
from disk_analyzer_core import DiskAnalyzerCore


def _preparar(obj, cache_locations, docker_stats=None):
    obj.cache_locations = list(cache_locations)
    obj.large_files = []
    obj.docker_stats = docker_stats
    return obj.generate_recommendations()


def test_las_dos_interfaces_recomiendan_lo_mismo():
    core = DiskAnalyzerCore('.')
    core.find_cache_locations()
    locs, docker = core.cache_locations, core.docker_stats

    del_core = _preparar(DiskAnalyzerCore('.'), locs, docker)
    del_cli = _preparar(DiskAnalyzer('.'), locs, docker)

    assert [r['id'] for r in del_core] == [r['id'] for r in del_cli]
    assert [r['tier'] for r in del_core] == [r['tier'] for r in del_cli]
    assert [r['command'] for r in del_core] == [r['command'] for r in del_cli]


def test_los_ids_son_estables_y_no_son_texto_de_interfaz():
    core = DiskAnalyzerCore('.')
    core.find_cache_locations()
    for r in core.generate_recommendations():
        ident = r.get('id', '')
        assert ident, f"{r.get('type')} no tiene id"
        assert ident.islower() and ' ' not in ident, (
            f"{ident!r} parece texto de interfaz, no un identificador"
        )
        assert ident.isascii(), f"{ident!r} no es ascii: no sirve como clave"


def test_los_ids_no_se_repiten():
    core = DiskAnalyzerCore('.')
    core.find_cache_locations()
    ids = [r['id'] for r in core.generate_recommendations()]
    assert len(ids) == len(set(ids)), f"ids duplicados: {ids}"


def _un_download_viejo():
    return [{'path': '/Users/x/Downloads/old.zip', 'size': 5 * MB,
              'age_days': 45, 'extension': '.zip'}]


def test_descargas_antiguas_respeta_min_size_en_el_core():
    """La regla del core tiene que reflejar self.min_size en el comando, no
    un umbral fijo -- si no, 'Descargas Antiguas' lista hasta los ficheros
    minúsculos, algo mucho menos útil que lo que mostraba la CLI antes de
    la fusión."""
    core = DiskAnalyzerCore('.', min_size_mb=42)
    core.cache_locations = []
    core.docker_stats = None
    core.large_files = _un_download_viejo()
    recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'descargas_antiguas' in recs
    assert '+42M' in recs['descargas_antiguas']['command'], recs['descargas_antiguas']['command']


def test_la_cli_propaga_min_size_al_core_prestado():
    """Regresión: la delegación de disk_analyzer.py olvidaba pasar
    min_size al DiskAnalyzerCore prestado, así que 'Descargas Antiguas'
    dejaba de filtrar por tamaño para la CLI (y para la web, que comparte
    la misma regla) sin que ningún test lo anclara."""
    cli = DiskAnalyzer('.', min_size_mb=77)
    cli.cache_locations = []
    cli.docker_stats = None
    cli.large_files = _un_download_viejo()
    recs = {r['id']: r for r in cli.generate_recommendations()}
    assert 'descargas_antiguas' in recs
    assert '+77M' in recs['descargas_antiguas']['command'], recs['descargas_antiguas']['command']
