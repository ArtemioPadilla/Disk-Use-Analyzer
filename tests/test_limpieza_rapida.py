"""Lo que la app de la barra ofrece borrar sin abrir el analizador.

Es lo único del motor que llega a un menú sin pasar por la hoja de revisión de
la web, así que el filtro tiene que ser estricto: nada que solo liste, nada que
haya que volver a descargar, y nada sin comando.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from analyzer import cache_types
from disk_analyzer_core import (
    CATEGORIAS_RAPIDAS, COMANDO_SIMULADORES_SISTEMA, CONSECUENCIAS, DiskAnalyzerCore,
    limpiezas_rapidas,
)

RAIZ = Path(__file__).resolve().parent.parent
MB = 1024 * 1024


def _rec(id_: str, **extra):
    r = {'id': id_, 'type': id_, 'description': 'd', 'space': 5 * MB,
         'command': f'echo {id_}', 'efecto': 'borra',
         'consecuencia': CONSECUENCIAS[id_]}
    r.update(extra)
    return r


def test_solo_pasa_lo_que_vuelve_solo_y_la_papelera():
    recs = [_rec(i) for i in CONSECUENCIAS]
    ids = {r['id'] for r in limpiezas_rapidas(recs)}
    assert ids == set(CATEGORIAS_RAPIDAS)
    assert 'descargas_antiguas' not in ids
    assert 'docker' not in ids, "docker system prune -a mezcla y solo va con revisión"


def test_cada_limpieza_dice_bajo_que_categoria_del_menu_va():
    recs = [_rec(i) for i in CONSECUENCIAS]
    por_id = {r['id']: r['categoria'] for r in limpiezas_rapidas(recs)}
    assert por_id['npm'] == 'caches'
    assert por_id['papelera'] == 'tuyo'
    assert por_id['xcode_deriveddata'] == 'resto'
    assert set(por_id.values()) <= {'docker', 'caches', 'tuyo', 'resto'}
    assert set(por_id) == {i for i in CATEGORIAS_RAPIDAS if i in por_id}


def test_lo_que_solo_lista_o_no_tiene_comando_no_llega_al_menu():
    recs = [
        _rec('logs', efecto='solo_lista'),
        _rec('vscode', command=''),
        _rec('npm', command='# revisa a mano'),
        _rec('xcode_deriveddata'),
    ]
    assert [r['id'] for r in limpiezas_rapidas(recs)] == ['xcode_deriveddata']


def test_lo_que_vuelve_solo_va_primero_y_la_papelera_al_final():
    recs = [_rec('papelera'), _rec('logs', space=1 * MB), _rec('caches_de_apps', space=9 * MB)]
    salida = limpiezas_rapidas(recs)
    assert [r['id'] for r in salida] == ['caches_de_apps', 'logs', 'papelera']
    assert set(salida[0]) == {'id', 'titulo', 'descripcion', 'space', 'consecuencia', 'categoria', 'requiere_admin', 'command'}


def test_la_cli_mide_un_home_y_devuelve_json_con_comandos_que_pasan_la_verja():
    # Bajo la caché real y no en el temporal del sistema: /private/var/folders
    # está protegido, y ahí la verja dejaría la regla sin comando (ver
    # tests/test_comandos.py::_sandbox).
    raiz = Path.home() / 'Library' / 'Caches'
    raiz.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=raiz) as caja:
        _comprobar_cli(Path(caja) / 'home')


def _comprobar_cli(home: Path):
    logs = home / 'Library' / 'Logs'
    logs.mkdir(parents=True)
    (logs / 'grande.log').write_bytes(os.urandom(12 * MB))
    # Lo que la regla de logs no puede ver: una carpeta ajena con otro log.
    (home / 'Documents').mkdir()
    (home / 'Documents' / 'notas.log').write_bytes(b'x')

    proc = subprocess.run(
        [sys.executable, str(RAIZ / 'disk_analyzer.py'), '--limpieza-rapida'],
        cwd=RAIZ, env={**os.environ, 'HOME': str(home), 'PATH': '/usr/bin:/bin'},
        capture_output=True, text=True, timeout=60)

    assert proc.returncode == 0, proc.stderr
    salida = json.loads(proc.stdout)
    # What needs a password depends on the machine, not on this fake HOME.
    salida = [r for r in salida if not r['requiere_admin']]
    assert [r['id'] for r in salida] == ['logs']
    assert str(logs) in salida[0]['command']
    assert salida[0]['space'] >= 12 * MB

    subprocess.run(['/bin/sh', '-c', salida[0]['command']], check=True)
    assert list(logs.iterdir()) == []
    assert (home / 'Documents' / 'notas.log').exists()


DF = """TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          10        2         20GB      14GB (70%)
Containers      3         1         1GB       512MB (50%)
Local Volumes   5         1         30GB      25GB (83%)
Build Cache     40        0         8GB       8GB
"""


def _con_docker_falso(tmp_path, monkeypatch, salida_version=0):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    falso = bin_dir / 'docker'
    falso.write_text(
        '#!/bin/sh\n'
        f'if [ "$1" = version ]; then exit {salida_version}; fi\n'
        f"cat <<'FIN'\n{DF}FIN\n")
    falso.chmod(0o755)
    monkeypatch.setenv('PATH', f"{bin_dir}:{os.environ['PATH']}")


def _reglas_docker():
    return DiskAnalyzerCore(str(Path.home()))._reglas_docker_rapidas()


def test_docker_se_ofrece_en_dos_partes_que_no_se_solapan(tmp_path, monkeypatch):
    _con_docker_falso(tmp_path, monkeypatch)
    reglas = {r['id']: r for r in _reglas_docker()}

    assert set(reglas) == {'docker_build', 'docker_imagenes'}
    assert reglas['docker_build']['consecuencia'] == 'regenera'
    assert reglas['docker_build']['command'].startswith('docker builder prune')
    assert reglas['docker_imagenes']['consecuencia'] == 'redescarga'
    assert 'builder' not in reglas['docker_imagenes']['command']


def test_la_cifra_de_docker_no_cuenta_los_volumenes(tmp_path, monkeypatch):
    _con_docker_falso(tmp_path, monkeypatch)
    reglas = {r['id']: r for r in _reglas_docker()}
    assert reglas['docker_imagenes']['space'] < 15 * 1024 * MB


def test_nada_del_menu_toca_un_volumen_de_docker(tmp_path, monkeypatch):
    _con_docker_falso(tmp_path, monkeypatch)
    for r in _reglas_docker():
        assert 'volume' not in r['command']
        assert 'system prune' not in r['command']


def test_con_el_daemon_apagado_no_se_ofrece_nada_de_docker(tmp_path, monkeypatch):
    _con_docker_falso(tmp_path, monkeypatch, salida_version=1)
    assert _reglas_docker() == []


def _core_con_caches(*ubicaciones):
    core = DiskAnalyzerCore(str(Path.home()))
    core.cache_locations = [{'path': p, 'size': t, 'type': cache_types.NPM} for p, t in ubicaciones]
    return {r['id']: r for r in core.generate_recommendations()}


def test_npm_no_promete_lo_que_su_comando_no_borra():
    """`npm cache clean` deja _npx: contarlo hacía que se ofreciera para siempre."""
    casa = str(Path.home())
    reglas = _core_con_caches((f'{casa}/.npm/_cacache', 200 * MB), (f'{casa}/.npm/_npx', 300 * MB))

    assert reglas['npm']['space'] == 200 * MB
    assert reglas['npm']['command'] == 'npm cache clean --force'
    assert reglas['npx']['space'] == 300 * MB
    assert reglas['npx']['consecuencia'] == 'regenera'
    assert f'{casa}/.npm/_npx' in reglas['npx']['command']
    assert '_cacache' not in reglas['npx']['command']


def test_sin_npx_no_hay_regla_npx():
    casa = str(Path.home())
    assert 'npx' not in _core_con_caches((f'{casa}/.npm/_cacache', 200 * MB))


def _casa_con(tmp_path, monkeypatch, *carpetas):
    # Inside ~/Library/Caches because the gate rejects /private/var/folders.
    base = tempfile.mkdtemp(dir=Path.home() / 'Library' / 'Caches')
    for c in carpetas:
        d = Path(base) / c
        d.mkdir(parents=True)
        (d / 'pesado').write_bytes(b'x' * (60 * MB))
    monkeypatch.setenv('HOME', base)
    return Path(base)


def test_cada_herramienta_de_dot_cache_tiene_su_regla(tmp_path, monkeypatch):
    casa = _casa_con(tmp_path, monkeypatch, '.cache/huggingface/hub', '.cache/act')
    try:
        reglas = {r['id']: r for r in DiskAnalyzerCore(str(casa))._reglas_de_herramientas()}
        assert set(reglas) == {'cache_huggingface', 'cache_act'}
        assert reglas['cache_huggingface']['consecuencia'] == 'redescarga'
        assert reglas['cache_act']['consecuencia'] == 'regenera'
    finally:
        shutil.rmtree(casa)


def test_el_token_de_hugging_face_no_se_toca(tmp_path, monkeypatch):
    casa = _casa_con(tmp_path, monkeypatch, '.cache/huggingface/hub')
    token = casa / '.cache/huggingface/token'
    token.write_text('secreto')
    try:
        regla, = DiskAnalyzerCore(str(casa))._reglas_de_herramientas()
        subprocess.run(['/bin/sh', '-c', regla['command']], check=True)
        assert not (casa / '.cache/huggingface/hub/pesado').exists()
        assert token.read_text() == 'secreto'
    finally:
        shutil.rmtree(casa)


def test_sin_el_comando_de_la_herramienta_no_se_ofrece(tmp_path, monkeypatch):
    casa = _casa_con(tmp_path, monkeypatch, '.cache/uv')
    monkeypatch.setenv('PATH', '/usr/bin:/bin')
    try:
        assert DiskAnalyzerCore(str(casa))._reglas_de_herramientas() == []
    finally:
        shutil.rmtree(casa)


def test_lo_que_pide_contrasena_es_un_comando_fijo_que_se_declara(monkeypatch):
    recs = [_rec('simuladores_sistema', requiere_admin=True,
                 command=COMANDO_SIMULADORES_SISTEMA)]
    regla, = limpiezas_rapidas(recs)
    assert regla['requiere_admin'] is True
    assert regla['categoria'] == 'resto'
    assert regla['command'].startswith('find /Library/Developer/CoreSimulator/Caches -mindepth 1')


def test_lo_demas_no_pide_contrasena():
    regla, = limpiezas_rapidas([_rec('logs')])
    assert regla['requiere_admin'] is False


def test_la_copia_del_comando_en_la_app_no_se_desincroniza():
    """La app comprueba el comando contra su propia copia antes de pedir contraseña."""
    rust = (RAIZ / 'desktop' / 'src-tauri' / 'src' / 'liberar.rs').read_text()
    assert f'"{COMANDO_SIMULADORES_SISTEMA}"' in rust
