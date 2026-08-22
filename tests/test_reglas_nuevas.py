"""Las reglas que dejaban fuera el 80% de lo encontrado.

Contexto medido en la máquina de referencia: 101,85 GB en cachés, pero solo
17,6 GB recomendados y solo 4,01 GB de nivel 1. Docker (39,6 GB),
~/Library/Caches (21,4 GB) y la papelera se quedaban fuera. Este módulo fija
las reglas que cierran ese hueco, más la verja de borrado
(analyzer.protection.puede_borrarse) que hasta ahora nadie fuera de sus
propios tests llamaba.
"""
import os
import sys

sys.path.insert(0, '.')
from disk_analyzer_core import DiskAnalyzerCore
from analyzer import cache_types
from analyzer import comandos
from analyzer.protection import puede_borrarse

GB = 1024 ** 3
MB = 1024 ** 2


def _core_con(locs, docker=None):
    core = DiskAnalyzerCore('.')
    core.cache_locations = locs
    core.large_files = []
    core.docker_stats = docker
    return core


def test_las_caches_de_library_se_recomiendan():
    """21,4 GB reales en la máquina de desarrollo, sin ninguna regla."""
    ruta = os.path.expanduser('~/Library/Caches')
    core = _core_con([{'type': cache_types.GENERAL, 'path': ruta,
                       'size': 21 * GB}])
    ids = {r['id'] for r in core.generate_recommendations()}
    assert 'caches_de_apps' in ids


def test_la_papelera_se_recomienda():
    ruta = os.path.expanduser('~/.Trash')
    core = _core_con([{'type': cache_types.TRASH, 'path': ruta,
                       'size': 3 * GB}])
    recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'papelera' in recs
    assert recs['papelera']['tier'] == 1, "vaciar la papelera es seguro"


def test_docker_aparece_solo_con_docker_stats():
    """No debe exigir un escaneo del disco completo: `docker system df` basta."""
    core = _core_con([], docker={'available': True, 'reclaimable': 39 * GB})
    recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'docker' in recs
    assert recs['docker']['efecto'] == 'irreversible'


def test_las_caches_de_apps_no_incluyen_datos_de_usuario():
    """La regla no puede arrastrar nada que no sea caché."""
    core = _core_con([{'type': cache_types.GENERAL,
                       'path': os.path.expanduser('~/Library/Caches'),
                       'size': 21 * GB}])
    for r in core.generate_recommendations():
        if r['id'] == 'caches_de_apps':
            assert puede_borrarse(os.path.expanduser('~/Library/Caches'))


# -- Norma innegociable del task: ninguna regla filtra solo por `type`, tiene
# que acotar también por ruta. cache_types.GENERAL agrupa ~/Library/Caches
# (lo que la regla SÍ debe tocar) junto con
# ~/Library/Developer/CoreSimulator/Devices (simuladores instalados, no una
# caché) y /private/var/folders (lo gestiona macOS). Mismo defecto que casi
# se publica una vez con cache_types.XCODE mezclando DerivedData y Archives:
# el comando de 'caches_de_apps' no puede mencionar ninguna de las dos, aunque
# ambas estén presentes en cache_locations junto a la caché real. --

def test_caches_de_apps_no_arrastra_coresimulator_ni_var_folders():
    coresim = os.path.expanduser('~/Library/Developer/CoreSimulator/Devices')
    varfolders = '/private/var/folders'
    caches = os.path.expanduser('~/Library/Caches')
    core = _core_con([
        {'type': cache_types.GENERAL, 'path': caches, 'size': 21 * GB},
        {'type': cache_types.GENERAL, 'path': coresim, 'size': 15 * GB},
        {'type': cache_types.GENERAL, 'path': varfolders, 'size': 4 * GB},
    ])
    recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'caches_de_apps' in recs
    cmd = recs['caches_de_apps']['command']
    assert coresim not in cmd, "arrastró simuladores instalados a un 'borra'"
    assert varfolders not in cmd, "arrastró /private/var/folders, lo gestiona macOS"
    assert caches in cmd


# -- Requisito añadido: instalar la verja de borrado en comandos.py. --

def test_una_ruta_prohibida_se_descarta_aunque_se_pase():
    """~/Documents nunca puede acabar en un comando de borrado, ni aunque
    una regla (con un bug, o de forma maliciosa) intente pasarla."""
    documents = os.path.expanduser('~/Documents')
    assert comandos.borrar_contenido([documents]) == ""
    assert comandos.borrar_rutas([documents]) == ""


def test_las_caches_conocidas_siguen_generando_comando():
    """La verja no puede convertirse en una lista negra que también bloquee
    lo legítimo: las cachés reales de la whitelist siguen pasando."""
    caches = os.path.expanduser('~/Library/Caches')
    assert caches in comandos.borrar_contenido([caches])

    trash = os.path.expanduser('~/.Trash')
    assert trash in comandos.borrar_contenido([trash])


def test_xcode_archives_sigue_generando_comando_con_la_verja_instalada():
    """detect_smart_recommendations() (disk_analyzer.py, id
    'xcode_archives_antiguos') ya construía su comando con
    comandos.borrar_contenido sobre ~/Library/Developer/Xcode/Archives antes
    de este task. Sin añadir esa ruta a la whitelist de protection.py, la
    verja recién instalada la habría descartado en silencio -- ninguno de
    los tests existentes (test_efecto_recomendaciones.py) lo habría cazado
    porque solo comprueban 'efecto', no el contenido del comando."""
    archives = os.path.expanduser('~/Library/Developer/Xcode/Archives')
    assert puede_borrarse(archives)
    assert archives in comandos.borrar_contenido([archives])
