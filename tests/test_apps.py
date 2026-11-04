"""El tamaño real de cada app: nunca se ofrece borrar nada de esto."""
import plistlib
from pathlib import Path

from analyzer.apps import inventario

MB = 1024 * 1024


def _pesado(carpeta: Path, mb: int = 11) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / 'pesado').write_bytes(b'x' * (mb * MB))
    return carpeta


def _app(ruta: Path, bid: str, nombre: str) -> Path:
    _pesado(ruta / 'Contents' / 'MacOS')
    with open(ruta / 'Contents' / 'Info.plist', 'wb') as f:
        plistlib.dump({'CFBundleIdentifier': bid, 'CFBundleName': nombre}, f)
    return ruta


def test_suma_los_datos_por_identificador_exacto(tmp_path):
    apps = tmp_path / 'Applications'
    bib = tmp_path / 'Library'
    _app(apps / 'Editor.app', 'com.x.editor', 'Editor')
    _pesado(bib / 'Containers' / 'com.x.editor', 20)
    _pesado(bib / 'Containers' / 'com.x.editor.helper', 50)
    _pesado(bib / 'Application Support' / 'Editor', 5)
    _pesado(bib / 'Application Support' / 'Editor Pro', 50)

    fila, = inventario((str(apps),), bib)

    assert fila['titulo'] == 'Editor'
    assert 24 * MB < fila['tam_datos'] < 27 * MB, 'solo lo que coincide exacto'
    assert fila['space'] == fila['tam_app'] + fila['tam_datos']


def test_una_app_en_su_propia_carpeta_cuenta_toda_la_carpeta(tmp_path):
    juego = tmp_path / 'Applications' / 'Juego'
    _app(juego / 'Juego.app', 'com.x.juego', 'Juego')
    _pesado(juego / 'Datos', 30)
    fila, = inventario((str(tmp_path / 'Applications'),), None)
    assert fila['titulo'] == 'Juego'
    assert fila['tam_app'] > 40 * MB


def test_sin_permiso_no_lee_library(tmp_path, monkeypatch):
    apps = tmp_path / 'Applications'
    _app(apps / 'Editor.app', 'com.x.editor', 'Editor')
    monkeypatch.delenv('DISK_ANALYZER_ACCESO_TOTAL', raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    _pesado(tmp_path / 'Library' / 'Containers' / 'com.x.editor', 20)
    fila, = inventario((str(apps),))
    assert fila['tam_datos'] == 0


def test_nada_se_ofrece_borrar(tmp_path):
    apps = tmp_path / 'Applications'
    _app(apps / 'Editor.app', 'com.x.editor', 'Editor')
    fila, = inventario((str(apps),), None)
    assert fila['command'] == ''
    assert fila['consecuencia'] == 'solo_lista'


def test_un_plist_roto_no_rompe_y_la_carpeta_sin_app_no_cuenta(tmp_path):
    apps = tmp_path / 'Applications'
    roto = _pesado(apps / 'Roto.app' / 'Contents')
    (roto / 'Info.plist').write_text('no es un plist')
    _pesado(apps / 'SinApp')
    assert [f['titulo'] for f in inventario((str(apps),), tmp_path / 'Library')] == ['Roto']
