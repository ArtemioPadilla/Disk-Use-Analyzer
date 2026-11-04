"""Los archivos grandes del último análisis, y que el analizador vea los del menú."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from analyzer.archivos import agrupar, guardar, inventario

RAIZ = Path(__file__).resolve().parent.parent
MB = 1024 * 1024


def _a(path, size=MB, ext=None):
    return {'path': path, 'size': size, 'extension': ext or Path(path).suffix}


@pytest.fixture
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    return tmp_path


def test_agrupa_por_extension_y_el_mayor_va_primero():
    filas = agrupar([
        _a('/Users/u/Movies/a.MKV', 5 * MB),
        _a('/Users/u/Desktop/b.mov', 5 * MB),
        _a('/Users/u/Downloads/c.dmg', 20 * MB),
    ])
    assert [f['titulo'] for f in filas] == ['Imágenes de disco (1)', 'Videos (2)']
    assert filas[1]['space'] == 10 * MB


def test_lo_que_vive_dentro_de_apps_o_proyectos_no_cuenta():
    assert agrupar([
        _a('/Users/u/Library/Containers/x/a.mp4'),
        _a('/Users/u/p/node_modules/x/a.mp4'),
        _a('/Applications/X.app/a.mp4'),
        _a('/Users/u/.cache/huggingface/a.safetensors'),
    ]) == []


def test_nada_se_ofrece_borrar_y_cada_grupo_lleva_a_su_lista():
    f, = agrupar([_a('/Users/u/Movies/a.mp4')])
    assert f['command'] == ''
    assert f['consecuencia'] == 'solo_lista'
    assert f['destino'].startswith('/files?exts=.mp4,')


def test_sin_analisis_previo_no_hay_grupos(casa):
    assert inventario() == []


def test_guardar_y_leer_ignora_lo_que_ya_no_existe(casa, monkeypatch):
    # tmp_path lives under /private, which the groups leave out.
    monkeypatch.setattr('analyzer.archivos.RAICES_FUERA', ())
    real = casa / 'Movies' / 'a.mp4'
    real.parent.mkdir()
    real.write_bytes(b'x')
    guardar('/', {'summary': {}, 'large_files': [
        _a(str(real)), _a(str(casa / 'Movies' / 'borrado.mp4')),
    ]})
    f, = inventario()
    assert f['titulo'] == 'Videos (1)'


def test_guardar_reemplaza_el_anterior_del_menu_y_no_los_de_la_web(casa):
    carpeta = casa / '.disk-analyzer' / 'results'
    carpeta.mkdir(parents=True)
    (carpeta / 'sesion-web.json').write_text('[]')
    (carpeta / 'menu-1.json').write_text('[]')
    destino = guardar('/', {'summary': {}, 'large_files': []})
    assert {p.name for p in carpeta.iterdir()} == {'sesion-web.json', destino.name}


def test_el_analizador_lee_un_analisis_hecho_con_el_motor(casa, monkeypatch, tmp_path):
    """De punta a punta: lo que escribe --guardar-resultado lo sirve la web."""
    datos = tmp_path / 'datos'
    datos.mkdir()
    (datos / 'grande.mp4').write_bytes(os.urandom(2 * MB))
    proc = subprocess.run(
        [sys.executable, str(RAIZ / 'disk_analyzer.py'), str(datos), '--min-size', '1',
         '--guardar-resultado'],
        cwd=RAIZ, env={**os.environ, 'HOME': str(casa)},
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    guardado, = (casa / '.disk-analyzer' / 'results').glob('menu-*.json')

    import importlib
    from fastapi.testclient import TestClient
    import disk_analyzer_web
    monkeypatch.setenv('DISK_ANALYZER_NO_AUTH', '1')
    importlib.reload(disk_analyzer_web)
    monkeypatch.setattr(disk_analyzer_web, 'RESULTS_DIR', guardado.parent)
    disk_analyzer_web.analysis_sessions.clear()
    r = TestClient(disk_analyzer_web.app).get('/api/analysis/latest')

    assert r.status_code == 200
    archivos = r.json()['results'][0]['report']['large_files']
    assert any(a['path'].endswith('grande.mp4') and a['extension'] == '.mp4' for a in archivos)
    assert json.loads(guardado.read_text())[0]['path'] == str(datos)
