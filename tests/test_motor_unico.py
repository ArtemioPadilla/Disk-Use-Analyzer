"""La CLI y la web tienen que ver las mismas recomendaciones.

Hoy hay dos copias: `disk_analyzer_core.py:561` la usa la web y
`disk_analyzer.py:888` la usan la CLI y la app de bandeja. La app de bandeja
ejecuta `disk_analyzer.py`, así que la barra y la web pueden recomendar cosas
distintas del mismo disco.

Además, ninguna recomendación tiene identificador estable: `type` es una cadena
de display en español y ya difiere entre copias ('Cache de Simuladores' contra
'Cache de Simuladores iOS'). Sin `id` no se puede configurar nada.

Los 12 IDs que produce `DiskAnalyzerCore.generate_recommendations()` hoy:
logs, homebrew, vscode, npm, simuladores, descargas_antiguas, docker,
cache_general, xcode_deriveddata, runtimes_simuladores, archivos_gigantes,
maquinas_virtuales.

Ronda de arreglo 1: `_preparar` original dejaba `large_files = []` y no
poblaba `docker_stats`/`cache_locations` con nada realista, así que la
"comparación completa" solo se verificó a mano en un script desechable que
nunca quedó en el repositorio -- exactamente el hueco que este fixture
cierra. El estado sintético de `_estado_sintetico()` dispara las 12 reglas
a la vez, así que la comparación deja de ser vacua en una máquina/runner sin
cachés reales.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, '.')
from disk_analyzer import DiskAnalyzer, MB, GB
from disk_analyzer_core import DiskAnalyzerCore

IDS_ESPERADOS = {
    'logs', 'homebrew', 'vscode', 'npm', 'simuladores', 'descargas_antiguas',
    'docker', 'cache_general', 'xcode_deriveddata', 'runtimes_simuladores',
    'archivos_gigantes', 'maquinas_virtuales',
}


def _estado_sintetico(home=None):
    """Estado sintético diseñado para disparar las 12 reglas de nivel a la
    vez, sin depender de qué cachés existan de verdad en la máquina que
    corre el test. Devuelve (cache_locations, large_files, docker_stats).

    `home` por defecto es el $HOME real de quien corre el test, no un
    '/Users/prueba' sintético: desde que generate_recommendations() descarta
    toda recomendación con 'command' vacío (Task 7, ronda de arreglo 1), un
    home sintético cae bajo '/Users' (RUTAS_DE_DATOS_DE_USUARIO), su comando
    sale vacío por la verja de protection.puede_borrarse, y la recomendación
    entera desaparece -- exactamente lo que este fixture necesita evitar
    para poder seguir dependiendo de las 12 reglas presentes a la vez. Sigue
    aceptando un `home` explícito para quien quiera aislarse del $HOME real
    a propósito."""
    if home is None:
        home = os.path.expanduser('~')
    cache_locations = [
        {'path': f'{home}/Library/Logs', 'size': 50 * MB, 'type': 'Logs del Sistema'},
        {'path': f'{home}/Library/Application Support/Code/Cache', 'size': 50 * MB, 'type': 'VS Code Cache'},
        {'path': f'{home}/.npm', 'size': 200 * MB, 'type': 'NPM Cache'},
        {'path': f'{home}/.cache/huggingface', 'size': 500 * MB, 'type': 'Cache General'},
        {'path': f'{home}/Library/Developer/Xcode/DerivedData', 'size': 500 * MB, 'type': 'Xcode Cache'},
        # Deliberadamente también incluye Archives, clasificado igual (XCODE)
        # que DerivedData -- ver test_xcode_deriveddata_no_incluye_archives.
        {'path': f'{home}/Library/Developer/Xcode/Archives', 'size': 2 * GB, 'type': 'Xcode Cache'},
    ]
    large_files = [
        {'path': f'{home}/Library/Caches/Homebrew/downloads/foo.tar.gz', 'size': 300 * MB,
         'extension': '.gz', 'age_days': 5},
        {'path': f'{home}/Library/Developer/CoreSimulator/Devices/ABCD/data/foo.bin', 'size': 400 * MB,
         'extension': '.bin', 'age_days': 5},
        {'path': f'{home}/Downloads/old_installer.dmg', 'size': 700 * MB,
         'extension': '.dmg', 'age_days': 60},
        {'path': f'{home}/Library/Developer/CoreSimulator/Profiles/Runtimes/'
                  'iOSSimulatorRuntime.simruntime/big.dat',
         'size': 2 * GB, 'extension': '.dat', 'age_days': 5},
        {'path': '/tmp/huge_video_file.mov', 'size': int(1.5 * GB), 'extension': '.mov', 'age_days': 5},
        {'path': f'{home}/VMs/ubuntu.vmdk', 'size': 3 * GB, 'extension': '.vmdk', 'age_days': 5},
    ]
    docker_stats = {'available': True, 'reclaimable': 500 * MB, 'total_size': 800 * MB}
    return cache_locations, large_files, docker_stats


def _preparar(obj, cache_locations, large_files=None, docker_stats=None):
    obj.cache_locations = list(cache_locations)
    obj.large_files = list(large_files) if large_files is not None else []
    obj.docker_stats = docker_stats
    return obj.generate_recommendations()


def test_las_dos_interfaces_recomiendan_lo_mismo():
    """Estado sintético que dispara las 12 reglas, no un escaneo del disco
    real: así la aserción es la misma en cualquier máquina, tenga o no
    cachés reales.

    detect_smart_recommendations() se neutraliza aquí a propósito: es una
    fuente CLI-only, deliberadamente distinta entre interfaces (ver
    docstring del módulo y tests/test_efecto_recomendaciones.py), así que
    compararla junto a las 12 reglas compartidas mezclaría dos contratos
    distintos. Que la delegación siga llamándola de verdad está cubierto
    por test_la_delegacion_preserva_detect_smart_recommendations más abajo.
    """
    locs, files, docker = _estado_sintetico()

    del_core = _preparar(DiskAnalyzerCore('.'), locs, files, docker)
    with patch.object(DiskAnalyzer, 'detect_smart_recommendations', return_value=[]):
        del_cli = _preparar(DiskAnalyzer('.'), locs, files, docker)

    assert {r['id'] for r in del_core} == IDS_ESPERADOS, sorted(r['id'] for r in del_core)
    assert [r['id'] for r in del_core] == [r['id'] for r in del_cli]
    assert [r['tier'] for r in del_core] == [r['tier'] for r in del_cli]
    assert [r['command'] for r in del_core] == [r['command'] for r in del_cli]


def test_la_delegacion_preserva_detect_smart_recommendations():
    """Trampa 1 del task original: la delegación tiene que seguir llamando
    a detect_smart_recommendations() y anexar su salida, no solo devolver
    lo que presta el core. Si un refactor futuro "simplifica" la delegación
    a un simple `return prestado.generate_recommendations()`, esta prueba
    lo atrapa."""
    cli = DiskAnalyzer('.')
    cli.cache_locations = []
    cli.large_files = []
    cli.docker_stats = None
    cli.directory_sizes['/ruta_de_prueba_que_no_existe_xyz/proyecto/node_modules'] = 300 * MB

    recs = cli.generate_recommendations()
    tipos = [r['type'] for r in recs]
    assert 'node_modules Huerfano' in tipos, (
        "detect_smart_recommendations() ya no se refleja en "
        "generate_recommendations(): la delegación perdió la trampa 1"
    )


def test_los_ids_son_estables_y_no_son_texto_de_interfaz():
    locs, files, docker = _estado_sintetico()
    core = DiskAnalyzerCore('.')
    for r in _preparar(core, locs, files, docker):
        ident = r.get('id', '')
        assert ident, f"{r.get('type')} no tiene id"
        assert ident.islower() and ' ' not in ident, (
            f"{ident!r} parece texto de interfaz, no un identificador"
        )
        assert ident.isascii(), f"{ident!r} no es ascii: no sirve como clave"


def test_los_ids_no_se_repiten():
    locs, files, docker = _estado_sintetico()
    core = DiskAnalyzerCore('.')
    ids = [r['id'] for r in _preparar(core, locs, files, docker)]
    assert len(ids) == len(set(ids)), f"ids duplicados: {ids}"


def test_las_doce_reglas_disparan_con_el_estado_sintetico():
    """Fija la cobertura: si una regla deja de disparar (o una nueva no
    declara su id), este test lo nota aunque la máquina que lo corre no
    tenga ni un solo caché real -- a diferencia de los tests anteriores a
    esta ronda, que dependían del disco real y podían pasar vacíamente."""
    locs, files, docker = _estado_sintetico()
    core = DiskAnalyzerCore('.')
    recs = _preparar(core, locs, files, docker)
    assert len(recs) == 12, f"se esperaban 12 recomendaciones, hubo {len(recs)}: {[r['id'] for r in recs]}"
    assert {r['id'] for r in recs} == IDS_ESPERADOS


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


def test_min_size_cero_no_diverge_entre_cli_y_core():
    """disk_analyzer.DiskAnalyzer siempre puso un piso de 1 MB
    (`max(min_size_mb, 1)`); DiskAnalyzerCore no lo tenía, así que con
    min_size_mb=0 la web generaba '-size +0M' (un filtro que no filtra
    nada) mientras la CLI generaba '-size +1M'. Ambas clases tienen que
    coincidir ahora que comparten la misma regla."""
    core = DiskAnalyzerCore('.', min_size_mb=0)
    core.cache_locations = []
    core.docker_stats = None
    core.large_files = _un_download_viejo()

    cli = DiskAnalyzer('.', min_size_mb=0)
    cli.cache_locations = []
    cli.docker_stats = None
    cli.large_files = _un_download_viejo()
    with patch.object(DiskAnalyzer, 'detect_smart_recommendations', return_value=[]):
        cli_recs = {r['id']: r for r in cli.generate_recommendations()}

    core_recs = {r['id']: r for r in core.generate_recommendations()}

    assert '+1M' in core_recs['descargas_antiguas']['command'], core_recs['descargas_antiguas']['command']
    assert core_recs['descargas_antiguas']['command'] == cli_recs['descargas_antiguas']['command']


def test_xcode_deriveddata_no_incluye_archives():
    """CRÍTICO: cache_types.XCODE clasifica tanto DerivedData como Archives
    (classify() solo mira si 'xcode' aparece en la ruta). Al mover esta
    regla al core, filtrar por type=XCODE a secas metía los .xcarchive --
    builds firmadas y dSYMs de versiones ya publicadas, irreversibles -- en
    un comando 'rm -rf' descrito como "se regeneran al compilar". Este test
    fija que el comando solo toca DerivedData.

    Usa el $HOME real (no '/Users/prueba' como el resto del fixture): desde
    que comandos.py instala la verja de protection.puede_borrarse (Task 7),
    esta genera comandos reales para rutas dentro del HOME real -- un HOME
    sintético cae bajo '/Users' (RUTAS_DE_DATOS_DE_USUARIO) y el comando
    saldría vacío, lo que volvería vacuas las dos aserciones de contenido de
    abajo."""
    home = os.path.expanduser('~')
    core = DiskAnalyzerCore('.')
    core.cache_locations = [
        {'path': f'{home}/Library/Developer/Xcode/DerivedData', 'size': 500 * MB, 'type': 'Xcode Cache'},
        {'path': f'{home}/Library/Developer/Xcode/Archives', 'size': 5 * GB, 'type': 'Xcode Cache'},
    ]
    core.large_files = []
    core.docker_stats = None

    recs = {r['id']: r for r in core.generate_recommendations()}
    assert 'xcode_deriveddata' in recs
    comando = recs['xcode_deriveddata']['command']
    assert 'DerivedData' in comando
    assert 'Archives' not in comando, (
        f"el comando de xcode_deriveddata no debe tocar Archives: {comando!r}"
    )
    # El espacio reportado tampoco debe incluir los Archives (5 GB de la
    # fixture): si el filtro se ampliara otra vez, este assert también lo
    # atraparía aunque alguien reescribiera el comando a mano.
    assert recs['xcode_deriveddata']['space'] == 500 * MB
