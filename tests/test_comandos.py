"""El constructor de comandos de borrado.

Los dos fallos que estos tests fijan estaban en producción y se reprodujeron:
una carpeta con un apóstrofe en el nombre ejecutaba comandos arbitrarios, y el
glob entrecomillado hacía que el borrado no borrara nada y saliera con éxito.
"""
import os
import subprocess
import tempfile

from analyzer.comandos import borrar_contenido, borrar_rutas, escapar


def _ejecutar(cmd: str, cwd: str) -> int:
    return subprocess.run(["/bin/sh", "-c", cmd], cwd=cwd,
                          capture_output=True).returncode


def test_una_ruta_maliciosa_no_ejecuta_comandos_extra():
    """El nombre de una carpeta no puede ser código.

    Reproducido en producción: `x' ; rm -rf victim ; touch pwned '` con la
    plantilla vieja generaba tres comandos y borraba una carpeta ajena.
    """
    with tempfile.TemporaryDirectory() as box:
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
    with tempfile.TemporaryDirectory() as box:
        objetivo = os.path.join(box, "cache")
        os.makedirs(objetivo)
        open(os.path.join(objetivo, "a.log"), "w").write("x")
        open(os.path.join(objetivo, "b.log"), "w").write("x")

        _ejecutar(borrar_contenido([objetivo]), cwd=box)

        assert os.listdir(objetivo) == [], "el contenido sobrevivió al borrado"
        assert os.path.isdir(objetivo), "borró el directorio, no su contenido"


def test_borrar_rutas_borra_el_directorio_entero():
    with tempfile.TemporaryDirectory() as box:
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
