"""Los ambientes: solo conda ofrece limpiar, y con sus propios comandos."""
import subprocess
from pathlib import Path

import pytest

import analyzer.ambientes as ambientes

MB = 1024 * 1024


def _pesado(carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / 'pesado').write_bytes(b'x' * (11 * MB))
    return carpeta


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(ambientes, 'VERSIONES', ())
    monkeypatch.setattr(ambientes, 'CELLAR', str(tmp_path / 'sin-cellar'))
    monkeypatch.setattr(ambientes, 'GLOBALES_NPM', str(tmp_path / 'sin-globales'))
    b = tmp_path / "ana conda"
    (b / 'bin').mkdir(parents=True)
    (b / 'bin' / 'conda').write_text('#!/bin/sh\necho "$@" > "$(dirname "$0")/llamada"\n')
    (b / 'bin' / 'conda').chmod(0o755)
    return b


def _por_id(b):
    return {f['id']: f for f in ambientes.inventario((str(b),))}


def test_la_cache_de_conda_se_limpia_con_conda(base):
    _pesado(base / 'pkgs')
    fila = _por_id(base)['ambiente:ana conda-pkgs']
    assert fila['consecuencia'] == 'redescarga'
    subprocess.run(['/bin/sh', '-c', fila['command']], check=True)
    assert (base / 'bin' / 'llamada').read_text().strip() == 'clean --all -y'


def test_un_entorno_se_quita_con_conda_por_ruta_y_nombrado(base):
    env = _pesado(base / 'envs' / 'ml')
    (env / 'conda-meta').mkdir()
    fila = _por_id(base)['ambiente:ana conda-env-ml']
    assert fila['titulo'] == 'Entorno conda ml'
    assert fila['dias'] == 0
    subprocess.run(['/bin/sh', '-c', fila['command']], check=True)
    assert (base / 'bin' / 'llamada').read_text().strip() == f'env remove -y -p {env}'


def test_una_carpeta_en_envs_sin_conda_meta_no_es_un_entorno(base):
    _pesado(base / 'envs' / 'datos')
    assert 'ambiente:ana conda-env-datos' not in _por_id(base)


def test_una_ruta_con_comillas_no_inyecta_nada(base):
    env = _pesado(base / 'envs' / "x'; touch pwned; '")
    (env / 'conda-meta').mkdir()
    fila = next(f for f in _por_id(base).values() if 'env-x' in f['id'])
    subprocess.run(['/bin/sh', '-c', fila['command']], check=True, cwd=base)
    assert not (base / 'pwned').exists()


def test_sin_conda_no_se_ofrece_nada_de_esa_base(base):
    (base / 'bin' / 'conda').unlink()
    _pesado(base / 'pkgs')
    assert _por_id(base) == {}


def test_las_versiones_y_homebrew_solo_informan(tmp_path, monkeypatch):
    pyenv = _pesado(tmp_path / 'pyenv' / '3.11.0').parent
    cellar = tmp_path / 'Cellar'
    _pesado(cellar / 'python@3.11')
    _pesado(cellar / 'wget')
    monkeypatch.setattr(ambientes, 'VERSIONES', (('pyenv', str(pyenv)),))
    monkeypatch.setattr(ambientes, 'CELLAR', str(cellar))
    monkeypatch.setattr(ambientes, 'GLOBALES_NPM', str(_pesado(tmp_path / 'globales')))

    filas = {f['titulo']: f for f in ambientes.inventario(())}

    assert set(filas) == {'3.11.0 (pyenv)', 'python@3.11 (Homebrew)', 'Paquetes globales de npm'}
    for f in filas.values():
        assert f['command'] == ''
        assert f['motivo'] == ambientes.SOLO_INFORMA


def test_lo_que_se_puede_limpiar_va_primero(base, tmp_path, monkeypatch):
    _pesado(base / 'pkgs')
    grande = _pesado(tmp_path / 'globales')
    (grande / 'mas').write_bytes(b'x' * (40 * MB))
    monkeypatch.setattr(ambientes, 'GLOBALES_NPM', str(grande))
    filas = ambientes.inventario((str(base),))
    assert filas[0]['command'] and not filas[1]['command']
