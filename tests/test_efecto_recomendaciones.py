"""Cada recomendación tiene que declarar qué hace su comando.

Hoy se mezclan tres cosas distintas bajo el mismo botón:
- borrados de ficheros, que podrían ir a la papelera;
- invocaciones a herramientas (`docker system prune`, `brew cleanup`), que
  borran por su cuenta y NO tienen papelera posible;
- diagnósticos (`du -sh`, `find -ls`), que no borran nada.

Sin este campo, la interfaz no puede prometer reversibilidad honestamente ni
distinguir "liberó espacio" de "te enseñó una lista".
"""
import sys

sys.path.insert(0, '.')
from disk_analyzer_core import DiskAnalyzerCore

EFECTOS = {'borra', 'irreversible', 'solo_lista'}


def _recomendaciones():
    core = DiskAnalyzerCore('.')
    core.find_cache_locations()
    return core.generate_recommendations()


def test_toda_recomendacion_declara_su_efecto():
    for r in _recomendaciones():
        assert r.get('efecto') in EFECTOS, (
            f"{r.get('type')} no declara efecto válido: {r.get('efecto')!r}"
        )


def test_los_comandos_que_solo_listan_estan_marcados():
    """`du -sh` y `find -ls` no borran; acreditarles ahorro es mentir."""
    for r in _recomendaciones():
        cmd = r.get('command', '')
        if cmd.startswith('du ') or ' -ls' in cmd:
            assert r['efecto'] == 'solo_lista', (
                f"{r['type']} ejecuta un diagnóstico pero no está marcado"
            )


def test_las_herramientas_externas_son_irreversibles():
    """Nada de esto se puede mandar a la papelera."""
    for r in _recomendaciones():
        cmd = r.get('command', '')
        if any(t in cmd for t in ('docker system prune', 'brew cleanup',
                                  'npm cache clean', 'simctl delete')):
            assert r['efecto'] == 'irreversible', (
                f"{r['type']} invoca una herramienta externa: no hay papelera"
            )
