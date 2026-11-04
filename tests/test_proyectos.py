"""Lo que los proyectos pueden reconstruir: el inventario y su paso por la verja.

Es lo primero que permite borrar en carpetas de trabajo del usuario, así que las
pruebas se centran en lo que NO debe ofrecerse.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from analyzer.protection import es_artefacto, puede_borrarse
from analyzer.proyectos import inventario

MB = 1024 * 1024


@pytest.fixture
def raiz():
    # Inside ~/Library/Caches because the gate rejects /private/var/folders.
    d = Path(tempfile.mkdtemp(dir=Path.home() / 'Library' / 'Caches'))
    yield d
    shutil.rmtree(d)


def _pesado(carpeta: Path) -> Path:
    carpeta.mkdir(parents=True)
    (carpeta / 'pesado').write_bytes(b'x' * (11 * MB))
    return carpeta


def _venv(carpeta: Path) -> Path:
    _pesado(carpeta)
    (carpeta / 'pyvenv.cfg').write_text('home = /usr/bin')
    return carpeta


def _por_ruta(raiz: Path) -> dict:
    return {a['ruta']: a for a in inventario([str(raiz)])}


def _repo(carpeta: Path, ignorar: str = '') -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'init', '-q', str(carpeta)], check=True)
    (carpeta / '.gitignore').write_text(ignorar)
    return carpeta


# -- La verja: el nombre no basta, salvo node_modules --

def test_target_solo_cuenta_con_cargo_toml_al_lado(raiz):
    sin = _pesado(raiz / 'fotos' / 'target')
    con = _pesado(raiz / 'crate' / 'target')
    (raiz / 'crate' / 'Cargo.toml').write_text('')
    assert not es_artefacto(str(sin))
    assert es_artefacto(str(con))


def test_venv_solo_cuenta_con_pyvenv_cfg_dentro(raiz):
    assert not es_artefacto(str(_pesado(raiz / 'a' / '.venv')))
    assert not es_artefacto(str(_pesado(raiz / 'a' / 'venv')))
    assert es_artefacto(str(_venv(raiz / 'b' / '.venv')))


def test_next_solo_cuenta_con_package_json_al_lado(raiz):
    assert not es_artefacto(str(_pesado(raiz / 'a' / '.next')))
    con = _pesado(raiz / 'b' / '.next')
    (raiz / 'b' / 'package.json').write_text('{}')
    assert es_artefacto(str(con))


@pytest.mark.parametrize('nombre', ['dist', 'build', 'out', 'vendor', 'bin'])
def test_nombres_corrientes_nunca_son_artefacto(raiz, nombre):
    carpeta = _pesado(raiz / 'p' / nombre)
    (raiz / 'p' / 'package.json').write_text('{}')
    (raiz / 'p' / 'Cargo.toml').write_text('')
    assert not es_artefacto(str(carpeta))


def test_un_symlink_con_nombre_de_artefacto_no_cuenta(raiz):
    real = _venv(raiz / 'real' / 'datos')
    enlace = raiz / 'p' / '.venv'
    enlace.parent.mkdir()
    enlace.symlink_to(real)
    assert not es_artefacto(str(enlace))


def test_la_verja_no_deja_pasar_datos_de_usuario_sin_evidencia():
    casa = Path.home()
    for ruta in ('Documents/x/target', 'Documents/x/.venv', 'Desktop/venv', 'Documents/x/.next'):
        assert not puede_borrarse(str(casa / ruta)), ruta


# -- El inventario --

def test_encuentra_cada_tipo_con_su_comando(raiz):
    _pesado(raiz / 'web' / 'node_modules')
    (raiz / 'web' / 'package.json').write_text('{}')
    _pesado(raiz / 'crate' / 'target')
    (raiz / 'crate' / 'Cargo.toml').write_text('')
    _venv(raiz / 'py' / '.venv')
    (raiz / 'py' / 'requirements.txt').write_text('')

    a = _por_ruta(raiz)

    assert {Path(r).name for r in a} == {'node_modules', 'target', '.venv'}
    for r, datos in a.items():
        assert datos['command'] == f'rm -rf {r}' or r in datos['command']
        assert datos['space'] >= 10 * MB
        assert datos['consecuencia'] == 'regenera'


def test_el_comando_borra_el_artefacto_y_nada_mas(raiz):
    nm = _pesado(raiz / 'web' / 'node_modules')
    (raiz / 'web' / 'package.json').write_text('{}')
    codigo = raiz / 'web' / 'index.js'
    codigo.write_text('x')

    comando = _por_ruta(raiz)[str(nm)]['command']
    subprocess.run(['/bin/sh', '-c', comando], check=True)

    assert not nm.exists()
    assert codigo.exists()


def test_no_entra_en_un_artefacto(raiz):
    _pesado(raiz / 'web' / 'node_modules' / 'dep' / 'node_modules')
    (raiz / 'web' / 'package.json').write_text('{}')
    a = _por_ruta(raiz)
    assert list(a) == [str(raiz / 'web' / 'node_modules')]


def test_un_venv_sin_definicion_no_se_ofrece(raiz):
    v = _venv(raiz / 'py' / '.venv')
    datos = _por_ruta(raiz)[str(v)]
    assert datos['reproducible'] is False
    assert datos['command'] == ''


def test_un_artefacto_que_git_no_ignora_no_se_ofrece(raiz, monkeypatch):
    """Si git no lo ignora puede estar versionado: no es regenerable."""
    # A global gitignore would ignore node_modules on most developers' machines.
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', '/dev/null')
    repo = _repo(raiz / 'r')
    (repo / 'package.json').write_text('{}')
    nm = _pesado(repo / 'node_modules')
    datos = _por_ruta(raiz)[str(nm)]
    assert datos['ignorado'] is False
    assert datos['command'] == ''


def test_un_artefacto_ignorado_se_ofrece_y_dice_su_repo(raiz):
    repo = _repo(raiz / 'r', 'node_modules\n')
    (repo / 'package.json').write_text('{}')
    nm = _pesado(repo / 'node_modules')
    datos = _por_ruta(raiz)[str(nm)]
    assert datos['ignorado'] is True
    assert datos['proyecto'] == 'r'
    assert str(nm) in datos['command']


def test_un_worktree_se_marca_y_su_artefacto_es_otro(raiz):
    repo = _repo(raiz / 'r', 'node_modules\n.claude\n')
    (repo / 'package.json').write_text('{}')
    entorno = {'GIT_AUTHOR_NAME': 'a', 'GIT_AUTHOR_EMAIL': 'a@a', 'GIT_COMMITTER_NAME': 'a',
               'GIT_COMMITTER_EMAIL': 'a@a', 'PATH': '/usr/bin:/bin:/opt/homebrew/bin'}
    subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(repo), 'commit', '-qm', 'x'], check=True, env=entorno)
    wt = repo / '.claude' / 'worktrees' / 'w'
    subprocess.run(['git', '-C', str(repo), 'worktree', 'add', '-q', str(wt)], check=True, env=entorno)
    nm = _pesado(wt / 'node_modules')

    datos = _por_ruta(raiz)[str(nm)]

    assert datos['worktree'] is True
    assert datos['proyecto'] == 'w'


def test_no_sigue_symlinks_de_carpetas(raiz):
    fuera = Path(tempfile.mkdtemp(dir=Path.home() / 'Library' / 'Caches'))
    try:
        _pesado(fuera / 'web' / 'node_modules')
        (raiz / 'enlace').symlink_to(fuera)
        assert _por_ruta(raiz) == {}
    finally:
        shutil.rmtree(fuera)


def test_lo_diminuto_no_se_lista(raiz):
    (raiz / 'web' / 'node_modules').mkdir(parents=True)
    assert _por_ruta(raiz) == {}


def test_una_raiz_que_no_existe_no_rompe():
    assert inventario(['/no/existe/en/ningun/mac']) == []
