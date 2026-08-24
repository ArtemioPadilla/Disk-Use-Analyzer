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
from unittest.mock import patch

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


# -- Ronda de arreglo 1: el test que pedía el brief para "la regla no puede
# arrastrar nada que no sea caché" era vacuo -- su único assert vive dentro de
# un `if r['id'] == 'caches_de_apps':` sin `else` que falle si la regla no
# dispara, así que pasaba igual sin la regla presente. Se borra en vez de
# arreglarse: test_caches_de_apps_no_arrastra_coresimulator_ni_var_folders de
# abajo cubre la misma intención con aserciones estrictas (falla si la regla
# no aparece, falla si arrastra las rutas que no debe). --

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


# -- Ronda de arreglo 1, punto 1: decisión de producto explícita -- node_modules
# se borra por NOMBRE (segundo eje de la verja en protection.py), no porque
# ~/Documents/repos/... esté en ninguna whitelist de rutas. La alternativa
# (dejar el comando vacío) es peor que no tener la regla: una recomendación
# que promete decenas de GB y cuyo botón no hace nada. --

def test_node_modules_huerfano_genera_comando_real_con_la_verja_instalada():
    """detect_smart_recommendations() (disk_analyzer.py, id
    'node_modules_huerfano') construye su comando con comandos.borrar_rutas
    sobre una ruta arbitraria del usuario -- no hay una ubicación fija que
    añadir a protection.py, así que la verja necesitaba el eje por nombre
    para no vaciar este comando en silencio."""
    from disk_analyzer import DiskAnalyzer

    analyzer = DiskAnalyzer('.')
    home = os.path.expanduser('~')
    dir_path = f'{home}/Documents/repos/proyecto-abandonado/node_modules'
    analyzer.directory_sizes[dir_path] = 300 * MB
    # Sin .git/HEAD ni package.json en el padre -> se considera huérfano.

    recs = {r['id']: r for r in analyzer.detect_smart_recommendations()}
    assert 'node_modules_huerfano' in recs
    cmd = recs['node_modules_huerfano']['command']
    assert cmd.strip(), "el comando salió vacío: la verja bloqueó la ruta"
    assert dir_path in cmd


# -- Ronda de arreglo 1, punto 2: la red de seguridad genérica. Si la verja
# bloquea TODAS las rutas de una regla, la recomendación entera tiene que
# desaparecer -- no quedarse en la lista con 'command': "", que es un botón
# que promete espacio y no hace nada. --

def test_una_regla_totalmente_bloqueada_por_la_verja_no_aparece():
    """Si protection.puede_borrarse descarta todas las rutas que una regla
    junta, generate_recommendations() no debe devolver esa recomendación con
    comando vacío: tiene que desaparecer de la lista por completo."""
    ruta_prohibida = os.path.expanduser('~/Documents')
    core = _core_con([
        {'type': cache_types.LOGS, 'path': ruta_prohibida, 'size': 50 * MB},
    ])
    recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'logs' not in recs, (
        "la regla 'logs' apareció con una ruta que la verja debería haber "
        "descartado por completo -- si esto es intencional, contradice la "
        "garantía de que ninguna recomendación sale con 'command' vacío"
    )


# -- Revisión final, hallazgo 4: las cuatro reglas de nivel 1 (logs, vscode,
# npm, papelera) filtraban solo por `type`, incumpliendo la norma que este
# mismo módulo ya fija para caches_de_apps (arriba). Misma causa raíz que el
# hallazgo 1: si cache_types.classify() etiqueta ~/Library/Caches como
# VSCODE -- lo que pasaba, antes de arreglar classify(), con cualquier
# nombre de usuario que contuviera la subcadena 'code' -- la regla vscode
# (nivel 1, sin revisión) se llevaba esos GB en vez de caches_de_apps (nivel
# 2, la que de verdad le corresponde). Estas pruebas no dependen de que
# classify() tenga el bug: construyen directamente una cache_location con el
# `type` "equivocado" para comprobar que cada regla se defiende también por
# ruta, no solo confiando en el `type` que le pasan.
#
# `puede_borrarse` se parchea a "todo pasa" en las cuatro: una ruta sintética
# como '/Users/nicode/...' no cae bajo el $HOME real de quien corre el test,
# así que la verja la rechazaría por esa razón AJENA (cualquier ruta bajo
# '/Users' que no sea una de las cachés conocidas del HOME real -- ver
# protection.py) y el assert "no aparece" pasaría igual sin que el fix de
# ESTE hallazgo tuviera nada que ver. Parcheando la verja, lo único que
# puede hacer desaparecer la recomendación es el acotado por ruta de la
# regla misma -- que es justo lo que se quiere probar aquí. --

def test_home_con_code_no_termina_en_la_regla_vscode():
    ruta = '/Users/nicode/Library/Caches'
    core = _core_con([
        {'type': cache_types.VSCODE, 'path': ruta, 'size': 21 * GB},
    ])
    with patch('analyzer.comandos.puede_borrarse', return_value=True):
        recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'vscode' not in recs, (
        f"~/Library/Caches se coló en la regla vscode: {recs.get('vscode')}"
    )


def test_home_con_log_no_termina_en_la_regla_logs():
    ruta = '/Users/logan/Downloads'
    core = _core_con([
        {'type': cache_types.LOGS, 'path': ruta, 'size': 5 * GB},
    ])
    with patch('analyzer.comandos.puede_borrarse', return_value=True):
        recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'logs' not in recs, (
        f"~/Downloads se coló en la regla logs: {recs.get('logs')}"
    )


def test_home_con_node_no_termina_en_la_regla_npm():
    ruta = '/Users/anode/Downloads'
    core = _core_con([
        {'type': cache_types.NPM, 'path': ruta, 'size': 5 * GB},
    ])
    with patch('analyzer.comandos.puede_borrarse', return_value=True):
        recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'npm' not in recs, (
        f"~/Downloads se coló en la regla npm: {recs.get('npm')}"
    )


def test_una_ruta_ajena_no_termina_en_la_regla_papelera():
    ruta = '/Users/x/Documents/algo_que_no_es_la_papelera'
    core = _core_con([
        {'type': cache_types.TRASH, 'path': ruta, 'size': 5 * GB},
    ])
    with patch('analyzer.comandos.puede_borrarse', return_value=True):
        recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'papelera' not in recs, (
        f"una ruta que no es ~/.Trash se coló en la regla papelera: {recs.get('papelera')}"
    )


def test_ninguna_recomendacion_del_core_sale_con_comando_vacio():
    """Red de seguridad genérica, sin depender de una regla concreta: para
    cualquier estado sintético razonable, cada recomendación que sale de
    generate_recommendations() tiene un 'command' no vacío."""
    core = _core_con([
        {'type': cache_types.LOGS, 'path': os.path.expanduser('~/Documents'), 'size': 50 * MB},
        {'type': cache_types.GENERAL, 'path': os.path.expanduser('~/Library/Caches'), 'size': 21 * GB},
        {'type': cache_types.TRASH, 'path': os.path.expanduser('~/.Trash'), 'size': 3 * GB},
    ], docker={'available': True, 'reclaimable': 5 * GB})
    for r in core.generate_recommendations():
        assert (r.get('command') or '').strip(), (
            f"{r['id']!r} salió con 'command' vacío"
        )
