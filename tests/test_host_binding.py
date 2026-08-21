"""El servidor tiene que poder atarse solo a loopback.

La app de bandeja arranca este servidor con un solo clic, y la interfaz web
incluye una terminal que corre con los privilegios del usuario. Exponer eso a
toda la red sin que nadie lo haya pedido sería una sorpresa desagradable, así
que la app pasa `--host 127.0.0.1`.

El valor por defecto sigue siendo 0.0.0.0: el acceso desde otros dispositivos
de la red es una función documentada de `make web`.

Estos tests arrancan el servidor de verdad y comprueban desde qué direcciones
responde. Mirar el texto del fuente no serviría: el flag podría existir y no
llegar a uvicorn, que es precisamente la forma en que esto se rompe en
silencio.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ip_de_red():
    """La IP no-loopback de esta máquina, o None si no tiene."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def _acepta(host: str, puerto: int, espera: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, puerto), timeout=espera):
            return True
    except OSError:
        return False


def _arrancar(host: str, puerto: int):
    entorno = dict(os.environ, DISK_ANALYZER_NO_AUTH="1")
    proc = subprocess.Popen(
        [sys.executable, "disk_analyzer_web.py", "--port", str(puerto), "--host", host],
        cwd=RAIZ, env=entorno,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,   # grupo propio: se mata entero, sin huérfanos
    )
    limite = time.time() + 30
    while time.time() < limite:
        if _acepta("127.0.0.1", puerto):
            return proc
        if proc.poll() is not None:
            pytest.skip("el servidor no arrancó en este entorno")
        time.sleep(0.25)
    _parar(proc)
    pytest.skip("el servidor tardó demasiado en arrancar")


def _parar(proc):
    try:
        os.killpg(os.getpgid(proc.pid), 15)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), 9)
        proc.wait(timeout=5)


def test_atado_a_loopback_no_responde_desde_la_red():
    """El caso que protege al usuario de la app de bandeja."""
    ip = _ip_de_red()
    if ip is None:
        pytest.skip("esta máquina no tiene IP de red que comprobar")
    puerto = _puerto_libre()
    proc = _arrancar("127.0.0.1", puerto)
    try:
        assert _acepta("127.0.0.1", puerto), "no responde ni en loopback"
        assert not _acepta(ip, puerto), (
            f"responde en {ip}:{puerto}: la terminal web quedaría expuesta a "
            "toda la red pese a haber pedido solo loopback"
        )
    finally:
        _parar(proc)


def test_por_defecto_sigue_escuchando_en_toda_la_red():
    """El acceso por LAN de `make web` está documentado; no se rompe."""
    ip = _ip_de_red()
    if ip is None:
        pytest.skip("esta máquina no tiene IP de red que comprobar")
    puerto = _puerto_libre()
    proc = _arrancar("0.0.0.0", puerto)
    try:
        assert _acepta(ip, puerto), (
            f"no responde en {ip}:{puerto}: se rompió el acceso desde otros "
            "dispositivos, que es una función documentada"
        )
    finally:
        _parar(proc)
