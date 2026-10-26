"""El progreso que el motor deja en un fichero mientras analiza.

La app de la barra lo lee cada segundo para decir cuánto lleva y cuánto falta.
"""
import json
import os
from pathlib import Path

import pytest

from disk_analyzer import DiskAnalyzer

GB = 1024 ** 3


@pytest.fixture
def casa(tmp_path, monkeypatch):
    """Un HOME vacío: sin cachés que medir ni historial previo."""
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    return home


def _analizar(ruta: Path, progreso: Path) -> dict:
    a = DiskAnalyzer(str(ruta), 1)
    a._progreso_ruta = str(progreso)
    a.analyze()
    return json.loads(progreso.read_text())


def test_al_terminar_el_progreso_cuenta_todo_lo_escaneado(tmp_path, casa):
    datos = tmp_path / 'datos'
    datos.mkdir()
    for i in range(3):
        (datos / f'f{i}').write_bytes(os.urandom(5000))

    p = _analizar(datos, tmp_path / 'progreso.json')

    assert p['fase'] == 'informe'
    assert p['archivos'] == 3
    assert p['bytes'] >= 15000
    assert p['segundos'] >= 0
    assert p['objetivo'] is None, "sin historial no hay de dónde estimar el total"


def test_el_objetivo_sale_de_la_proporcion_del_ultimo_escaneo(tmp_path, casa):
    datos = tmp_path / 'datos'
    datos.mkdir()
    historial = casa / '.disk-analyzer' / 'history.json'
    historial.parent.mkdir()
    historial.write_text(json.dumps([
        {'path': '/otra', 'total_size': 1 * GB, 'disk_used': 100 * GB},
        {'path': str(datos), 'total_size': 60 * GB, 'disk_used': 200 * GB},
    ]))

    a = DiskAnalyzer(str(datos), 1)
    usado = a.get_disk_usage()['used']
    p = _analizar(datos, tmp_path / 'progreso.json')

    assert p['objetivo'] == pytest.approx(usado * 0.3, rel=0.01)


def test_sin_fichero_de_progreso_no_se_escribe_nada(tmp_path, casa):
    datos = tmp_path / 'datos'
    datos.mkdir()
    (datos / 'f').write_bytes(b'x')
    DiskAnalyzer(str(datos), 1).analyze()
    assert not any(tmp_path.glob('*.json'))
