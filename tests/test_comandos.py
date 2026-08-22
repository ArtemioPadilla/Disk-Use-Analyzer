"""El constructor de comandos de borrado.

Los dos fallos que estos tests fijan estaban en producción y se reprodujeron:
una carpeta con un apóstrofe en el nombre ejecutaba comandos arbitrarios, y el
glob entrecomillado hacía que el borrado no borrara nada y saliera con éxito.
"""
import contextlib
import io
import os
import subprocess
import tempfile

from analyzer.comandos import borrar_contenido, borrar_rutas, escapar

# Desde que comandos.py instala la verja de protection.puede_borrarse
# (Task 7), un sandbox bajo el directorio temporal del sistema
# (tempfile.TemporaryDirectory() por defecto, que en macOS resuelve a
# /private/var/folders/...) ya no genera comando: esa ruta está protegida a
# propósito (ver tests/test_puede_borrarse.py::test_los_temporales_del_sistema_los_gestiona_macos).
# Los tests de este módulo verifican el escapado de shell, no la política de
# qué es borrable, así que el sandbox se crea dentro de una caché real y
# conocida (~/Library/Caches) para que siga pasando la verja.
_RAIZ_SANDBOX = os.path.expanduser("~/Library/Caches")


def _sandbox():
    os.makedirs(_RAIZ_SANDBOX, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=_RAIZ_SANDBOX)


def _ejecutar(cmd: str, cwd: str) -> int:
    return subprocess.run(["/bin/sh", "-c", cmd], cwd=cwd,
                          capture_output=True).returncode


def test_una_ruta_maliciosa_no_ejecuta_comandos_extra():
    """El nombre de una carpeta no puede ser código.

    Reproducido en producción: `x' ; rm -rf victim ; touch pwned '` con la
    plantilla vieja generaba tres comandos y borraba una carpeta ajena.
    """
    with _sandbox() as box:
        os.makedirs(os.path.join(box, "victima"))
        malicioso = os.path.join(box, "x' ; rm -rf victima ; touch pwned '")
        os.makedirs(malicioso)

        _ejecutar(borrar_contenido([malicioso]), cwd=box)

        assert os.path.isdir(os.path.join(box, "victima")), (
            "el nombre de otra carpeta consiguió borrar la víctima"
        )
        assert not os.path.exists(os.path.join(box, "pwned")), (
            "se ejecutó un comando arbitrario embebido en el nombre"
        )


def test_borrar_contenido_borra_de_verdad():
    """El glob tiene que quedar FUERA de las comillas o no expande.

    Con `rm -rf 'dir/*'` el shell trata el asterisco como literal, `rm -f` sale
    0 y no borra nada. La interfaz acreditaba el ahorro por ese 0.
    """
    with _sandbox() as box:
        objetivo = os.path.join(box, "cache")
        os.makedirs(objetivo)
        open(os.path.join(objetivo, "a.log"), "w").write("x")
        open(os.path.join(objetivo, "b.log"), "w").write("x")

        _ejecutar(borrar_contenido([objetivo]), cwd=box)

        assert os.listdir(objetivo) == [], "el contenido sobrevivió al borrado"
        assert os.path.isdir(objetivo), "borró el directorio, no su contenido"


def test_borrar_rutas_borra_el_directorio_entero():
    with _sandbox() as box:
        objetivo = os.path.join(box, "basura")
        os.makedirs(objetivo)
        _ejecutar(borrar_rutas([objetivo]), cwd=box)
        assert not os.path.exists(objetivo)


def test_escapar_sobrevive_al_viaje_de_ida_y_vuelta():
    """Escapar y volver a parsear tiene que devolver la ruta original.

    Es la propiedad que importa: da igual cómo se escape mientras el shell
    reconstruya exactamente la ruta que le dimos, ni un carácter más.
    """
    import shlex
    for peligro in ["a'b", "a b", "a;b", "a&&b", "a$(id)b", "a`id`b",
                    "a\nb", "a*b", "a|b", "~/algo", "-rf"]:
        assert shlex.split(escapar(peligro)) == [peligro]


def test_una_ruta_vacia_no_produce_comando():
    """Una ruta vacía convertiría `rm -rf ''/*` en algo impredecible."""
    assert borrar_contenido([]) == ""
    assert borrar_contenido([""]) == ""
    assert borrar_rutas(["   "]) == ""


def test_la_raiz_nunca_genera_comando():
    """Salvaguarda de último recurso: nada construye un borrado de `/`."""
    assert borrar_contenido(["/"]) == ""
    assert borrar_rutas(["/"]) == ""


# -- Ronda de arreglo 1: tres sitios que el grep del brief no cazaba porque
# ninguno usa `rm -rf`. Misma clase de bug (interpolación sin escapar en un
# 'command' que se ejecuta con sh -c), así que entran en el alcance del task. --

import shlex
from pathlib import Path

from disk_analyzer import DiskAnalyzer


def test_conda_env_remove_escapa_el_nombre_del_entorno():
    """disk_analyzer.py:723 interpolaba `env_name` sin comillas ni escapado.

    `env_name` es el nombre de un subdirectorio de un envs-dir de conda,
    tan controlable como cualquier otra ruta del escaneo. Antes del arreglo
    ni siquiera había comillas que romper: `conda env remove -n {env_name}`
    era interpolación directa.
    """
    analyzer = DiskAnalyzer(".")
    home = str(Path.home())
    base = f"{home}/miniconda3/envs"
    env_name = "x'; touch pwned; echo '"
    dir_path = f"{base}/{env_name}"

    analyzer.directory_sizes[dir_path] = 10 * 1024 * 1024
    analyzer.large_files = [
        {"path": f"{dir_path}/lib/x", "size": 1024, "age_days": 200}
    ]

    recs = analyzer.detect_smart_recommendations()
    conda_recs = [r for r in recs if r["type"] == "Entorno Conda Obsoleto"]
    assert conda_recs, "la recomendación de conda no se generó (fixture desalineado)"

    cmd = conda_recs[0]["command"]
    # Si el nombre volviera a interpolarse sin escapar, `shlex.split` partiría
    # el comando en piezas extra en vez de tratar el nombre como un solo token.
    assert shlex.split(cmd) == ["conda", "env", "remove", "-n", env_name]


def test_git_gc_escapa_la_ruta_del_repo():
    """disk_analyzer.py:813 usaba comillas simples manuales sin escapar
    el contenido -- el mismo patrón exacto del bug original.
    """
    analyzer = DiskAnalyzer(".")
    repo_path = "/tmp/x' ; touch pwned ; echo '/repo"
    analyzer.large_files = [
        {
            "path": f"{repo_path}/.git/objects/pack/pack-abc.pack",
            "size": 200 * 1024 * 1024,
        }
    ]

    recs = analyzer.detect_smart_recommendations()
    git_recs = [r for r in recs if r["type"] == "Git Pack Files Grandes"]
    assert git_recs, "la recomendación de git gc no se generó (fixture desalineado)"

    cmd = git_recs[0]["command"]
    assert shlex.split(cmd) == ["cd", repo_path, "&&", "git", "gc", "--aggressive"]


def test_du_sh_otros_escapa_la_ruta_y_de_verdad_lista_el_contenido():
    """disk_analyzer.py:3974 interpolaba `path` dentro de comillas dobles, que
    no neutralizan `$(...)`: dentro de comillas dobles POSIX, la sustitución
    de comandos SÍ se expande (a diferencia de las comillas simples). Con la
    plantilla vieja, un nombre de carpeta con `$(touch pwned)` ejecutaba
    `touch pwned` al construir el argumento de `du`, antes incluso de que
    `du` se ejecutara.
    """
    analyzer = DiskAnalyzer(".")
    with tempfile.TemporaryDirectory() as box:
        peligroso = os.path.join(box, "x$(touch pwned)y")
        os.makedirs(peligroso)
        open(os.path.join(peligroso, "a"), "w").write("x" * 1024)

        commands = analyzer._generate_category_cleanup_commands(
            "Otros", [(peligroso, 2 * 1024 * 1024 * 1024)]
        )
        assert commands, "no se generó comando para 'Otros' (fixture desalineado)"
        cmd = commands[0]["command"]

        _ejecutar(cmd, cwd=box)

        assert not os.path.exists(os.path.join(box, "pwned")), (
            "se ejecutó un comando arbitrario embebido en el nombre de la carpeta"
        )


def test_print_report_escapa_el_rm_f_sugerido_para_cache():
    """disk_analyzer.py:1354 imprimía `rm -f '{f['path']}'` en el reporte de
    consola (sección "COMANDOS DE LIMPIEZA SUGERIDOS") con comillas simples
    manuales sin escapar -- el mismo patrón que el bug original, solo que
    aquí nadie lo ejecuta automáticamente: el CLI se lo ofrece a un humano
    para copiar y pegar. El aviso de "revisa antes de ejecutar" no protege
    de nada porque nadie audita el entrecomillado a ojo, así que cuenta como
    el mismo defecto.
    """
    analyzer = DiskAnalyzer(".")
    peligroso = "/tmp/x' ; touch pwned ; echo '/cache.db"

    report = {
        'summary': {
            'total_size': 0, 'files_scanned': 0, 'large_files_count': 1,
            'recoverable_space': 0,
        },
        'docker': None,
        'recommendations': [],
        'top_directories': [],
        'top_file_types': [],
        'large_files': [
            {'path': peligroso, 'size': 1024, 'age_days': 5, 'is_cache': True},
        ],
        'cache_locations': [],
    }

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        analyzer.print_report(report)
    salida = buffer.getvalue()

    lineas_rm = [l.strip() for l in salida.splitlines() if l.strip().startswith('rm -f')]
    assert lineas_rm, "no se imprimió ninguna línea 'rm -f' (fixture desalineado)"

    # Si el nombre volviera a interpolarse sin escapar, shlex.split trocearía
    # el comando en piezas de más en vez de tratar la ruta como un solo token.
    assert shlex.split(lineas_rm[0]) == ["rm", "-f", peligroso]
