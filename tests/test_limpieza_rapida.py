"""Lo que la app de la barra ofrece borrar sin abrir el analizador.

Es lo único del motor que llega a un menú sin pasar por la hoja de revisión de
la web, así que el filtro tiene que ser estricto: nada que solo liste, nada que
haya que volver a descargar, y nada sin comando.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from disk_analyzer_core import CONSECUENCIAS, limpiezas_rapidas

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
    assert ids == {i for i, c in CONSECUENCIAS.items() if c in ('regenera', 'permanente')}
    assert 'docker' not in ids, "lo que hay que redescargar se queda en el analizador"


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
    assert set(salida[0]) == {'id', 'titulo', 'descripcion', 'space', 'consecuencia', 'command'}


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
        cwd=RAIZ, env={**os.environ, 'HOME': str(home)},
        capture_output=True, text=True, timeout=60)

    assert proc.returncode == 0, proc.stderr
    salida = json.loads(proc.stdout)
    assert [r['id'] for r in salida] == ['logs']
    assert str(logs) in salida[0]['command']
    assert salida[0]['space'] >= 12 * MB

    subprocess.run(['/bin/sh', '-c', salida[0]['command']], check=True)
    assert list(logs.iterdir()) == []
    assert (home / 'Documents' / 'notas.log').exists()
