"""Docker por nombre, con un `docker` falso: nada aquí puede tocar un volumen."""
import json
import os
from pathlib import Path

import pytest

from analyzer.docker_detalle import EN_USO, VOLUMEN, _bytes, inventario

IMAGENES = [
    {'ID': 'aaa111', 'Repository': 'postgres', 'Tag': '16', 'Size': '400MB'},
    {'ID': 'bbb222', 'Repository': 'app', 'Tag': 'latest', 'Size': '1.5GB'},
]
DF = {'Volumes': [{'Name': 'datos_db', 'Size': '3GB'}]}


def _falso(tmp_path, monkeypatch, version=0):
    d = tmp_path / 'bin'
    d.mkdir()
    lineas = '\n'.join(json.dumps(i) for i in IMAGENES)
    guion = d / 'docker'
    guion.write_text(f"""#!/bin/sh
case "$1 $2" in
  version*) exit {version} ;;
  "ps -a") echo postgres:16 ;;
  "image ls") cat <<'FIN'
{lineas}
FIN
  ;;
  "system df") cat <<'FIN'
{json.dumps(DF)}
FIN
  ;;
esac
""")
    guion.chmod(0o755)
    monkeypatch.setenv('PATH', f"{d}:{os.environ['PATH']}")


def test_una_imagen_sin_usar_se_ofrece_sin_forzar(tmp_path, monkeypatch):
    _falso(tmp_path, monkeypatch)
    f = {x['id']: x for x in inventario()}['docker:imagen:bbb222:app:latest']
    assert f['titulo'] == 'app:latest'
    assert f['command'] == 'docker image rm app:latest'
    assert f['consecuencia'] == 'redescarga'
    assert f['space'] == 1_500_000_000


def test_una_imagen_en_uso_no_se_ofrece(tmp_path, monkeypatch):
    _falso(tmp_path, monkeypatch)
    f = {x['id']: x for x in inventario()}['docker:imagen:aaa111:postgres:16']
    assert f['command'] == ''
    assert f['motivo'] == EN_USO


def test_un_volumen_solo_se_lista(tmp_path, monkeypatch):
    _falso(tmp_path, monkeypatch)
    f = {x['id']: x for x in inventario()}['docker:volumen:datos_db']
    assert f['command'] == ''
    assert f['motivo'] == VOLUMEN
    assert f['consecuencia'] == 'solo_lista'


def test_ningun_comando_toca_volumenes_ni_fuerza(tmp_path, monkeypatch):
    _falso(tmp_path, monkeypatch)
    for f in inventario():
        assert 'volume' not in f['command']
        assert ' -f' not in f['command'] and '--force' not in f['command']


def test_con_el_daemon_apagado_no_hay_lista(tmp_path, monkeypatch):
    _falso(tmp_path, monkeypatch, version=1)
    assert inventario() == []


def test_sin_docker_instalado_no_rompe(monkeypatch, tmp_path):
    monkeypatch.setenv('PATH', str(tmp_path))
    assert inventario() == []


@pytest.mark.parametrize('texto,esperado', [('12.5GB', 12_500_000_000), ('1.2kB', 1200), ('0B', 0), ('raro', 0)])
def test_lee_los_tamanos_de_docker(texto, esperado):
    assert _bytes(texto) == esperado


def test_una_imagen_con_varias_etiquetas_no_duplica_ids(tmp_path, monkeypatch):
    IMAGENES.append({'ID': 'bbb222', 'Repository': 'app', 'Tag': 'v1', 'Size': '1.5GB'})
    try:
        _falso(tmp_path, monkeypatch)
        ids = [x['id'] for x in inventario()]
        assert len(ids) == len(set(ids))
    finally:
        IMAGENES.pop()
