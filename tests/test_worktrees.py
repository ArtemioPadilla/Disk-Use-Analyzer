"""Los worktrees que se pueden quitar: solo los que no pierden nada."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from analyzer.worktrees import del_repo, inventario


@pytest.fixture(autouse=True)
def identidad(monkeypatch):
    for k, v in (('GIT_AUTHOR_NAME', 'a'), ('GIT_AUTHOR_EMAIL', 'a@a'),
                 ('GIT_COMMITTER_NAME', 'a'), ('GIT_COMMITTER_EMAIL', 'a@a'),
                 ('GIT_CONFIG_GLOBAL', '/dev/null')):
        monkeypatch.setenv(k, v)


def g(repo: Path, *args: str) -> None:
    subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / 'repo'
    r.mkdir()
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(r)], check=True)
    (r / 'a').write_text('1')
    g(r, 'add', '.')
    g(r, 'commit', '-qm', 'uno')
    return r


def _uno(repo, en_uso=frozenset()):
    filas = del_repo(repo, set(en_uso))
    assert len(filas) == 1
    return filas[0]


def _worktree(repo: Path, nombre: str = 'w', nuevo_commit: bool = False) -> Path:
    w = repo.parent / nombre
    g(repo, 'worktree', 'add', '-q', '-b', nombre, str(w))
    if nuevo_commit:
        (w / 'b').write_text('2')
        g(w, 'add', '.')
        g(w, 'commit', '-qm', 'dos')
    return w


def test_el_repo_principal_no_cuenta_como_worktree(repo):
    assert del_repo(repo, set()) == []


def test_limpio_y_mergeado_se_ofrece_y_se_quita_de_verdad(repo):
    w = _worktree(repo)
    f = _uno(repo)
    assert f['mergeada'] is True
    assert f['motivo'] == ''
    assert '--force' not in f['command']
    subprocess.run(['/bin/sh', '-c', f['command']], check=True)
    assert not w.exists()
    assert del_repo(repo, set()) == []
    # The branch stays: only the working copy goes.
    g(repo, 'rev-parse', '--verify', 'w')


def test_con_cambios_no_se_ofrece(repo):
    w = _worktree(repo)
    (w / 'a').write_text('cambio')
    f = _uno(repo)
    assert f['command'] == ''
    assert f['motivo'] == 'tiene cambios sin commit'


def test_con_archivos_sin_seguimiento_no_se_ofrece(repo):
    w = _worktree(repo)
    (w / 'nuevo').write_text('x')
    assert _uno(repo)['command'] == ''


def test_sin_mergear_no_se_ofrece(repo):
    _worktree(repo, nuevo_commit=True)
    f = _uno(repo)
    assert f['mergeada'] is False
    assert f['command'] == ''
    assert f['motivo'] == 'la rama no está mergeada'


def test_un_squash_cuenta_como_no_mergeado(repo):
    w = _worktree(repo, nuevo_commit=True)
    g(repo, 'merge', '--squash', 'w')
    g(repo, 'commit', '-qm', 'squash')
    assert _uno(repo)['command'] == ''
    assert w.exists()


def test_con_un_proceso_dentro_no_se_ofrece(repo):
    w = _worktree(repo)
    f = _uno(repo, {str(w / 'sub')})
    assert f['en_uso'] is True
    assert f['command'] == ''


def test_otro_directorio_con_prefijo_parecido_no_cuenta_como_en_uso(repo):
    w = _worktree(repo)
    assert _uno(repo, {f'{w}-otro'})['en_uso'] is False


def test_bloqueado_no_se_ofrece(repo):
    w = _worktree(repo)
    g(repo, 'worktree', 'lock', str(w))
    assert _uno(repo)['motivo'] == 'está bloqueado'


def test_el_comando_revalida_si_algo_cambia_despues_de_medir(repo):
    w = _worktree(repo)
    f = _uno(repo)
    (w / 'b').write_text('2')
    g(w, 'add', '.')
    g(w, 'commit', '-qm', 'dos')
    # The commit it checks is the measured one, but git still refuses dirty trees:
    (w / 'c').write_text('sin guardar')
    r = subprocess.run(['/bin/sh', '-c', f['command']], capture_output=True)
    assert r.returncode != 0
    assert (w / 'c').exists()


def test_uno_roto_se_ofrece_con_prune_y_no_con_rm(repo):
    w = _worktree(repo)
    shutil.rmtree(w)
    f = _uno(repo)
    assert f['rota'] is True
    assert f['command'].endswith('worktree prune')
    assert 'rm ' not in f['command']
    subprocess.run(['/bin/sh', '-c', f['command']], check=True)
    assert del_repo(repo, set()) == []


def test_una_ruta_con_comillas_no_inyecta_nada(repo, tmp_path):
    w = tmp_path / "wt'; touch pwned; '"
    g(repo, 'worktree', 'add', '-q', '-b', 'raro', str(w))
    subprocess.run(['/bin/sh', '-c', _uno(repo)['command']], check=True, cwd=tmp_path)
    assert not (tmp_path / 'pwned').exists()
    assert not w.exists()


def test_inventario_encuentra_los_repos_bajo_la_raiz(repo, tmp_path):
    _worktree(repo)
    assert [f['rama'] for f in inventario([str(tmp_path)])] == ['w']


def test_una_raiz_que_no_existe_no_rompe():
    assert inventario(['/no/existe/en/ningun/mac']) == []
