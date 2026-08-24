"""Qué se puede borrar de verdad.

`is_protected_path` es una lista negra del sistema operativo: sirve para "no
toques macOS", no para "esto es seguro de borrar". Verificado: devuelve False
(borrable) para ~/Documents, ~/Desktop, iCloud Drive, /Volumes/... y el propio
$HOME. Con "añadir carpetas propias" eso apuntaría a los datos del usuario.
"""
import os

import pytest

from analyzer.protection import puede_borrarse, _coincide_con_permitidas

CASA = os.path.expanduser("~")


@pytest.fixture
def enlace_de_cache_a_documents():
    """Crea un enlace simbólico real dentro de un directorio permitido
    (~/Library/Caches) que apunta a uno prohibido (~/Documents), y lo borra
    al terminar. No toca el contenido de ~/Documents, solo enlaza a él.

    Reproduce el escape real: `borrar_contenido` ejecuta `rm -rf <ruta>/*`, y
    ese glob SÍ atraviesa un enlace simbólico hacia lo que sea que apunte.
    """
    caches = os.path.join(CASA, "Library/Caches")
    documents = os.path.join(CASA, "Documents")
    if not os.path.isdir(caches) or not os.path.isdir(documents):
        pytest.skip("requiere ~/Library/Caches y ~/Documents reales")
    enlace = os.path.join(caches, f"_test_puede_borrarse_atajo_{os.getpid()}")
    if os.path.islink(enlace) or os.path.exists(enlace):
        os.unlink(enlace)
    os.symlink(documents, enlace)
    try:
        yield enlace
    finally:
        os.unlink(enlace)


@pytest.mark.parametrize("ruta", [
    CASA,
    os.path.join(CASA, "Documents"),
    os.path.join(CASA, "Desktop"),
    os.path.join(CASA, "Pictures"),
    os.path.join(CASA, "Library/Mobile Documents"),          # iCloud Drive
    os.path.join(CASA, "Library/Mobile Documents/algo/mio"),  # y su contenido
    "/Volumes/Backup Time Machine",
    "/Volumes/Backup Time Machine/2026",
    "/System/Library",     # el directorio en sí, no solo su contenido
    "/System",
    "/",
])
def test_los_datos_del_usuario_y_el_sistema_no_se_borran(ruta):
    assert not puede_borrarse(ruta), f"{ruta} salió como borrable"


@pytest.mark.parametrize("ruta", [
    os.path.join(CASA, "Library/Caches/com.apple.Safari"),
    os.path.join(CASA, ".npm/_cacache"),
    os.path.join(CASA, "Library/Logs/algo.log"),
])
def test_las_caches_conocidas_si_se_borran(ruta):
    assert puede_borrarse(ruta), f"{ruta} debería poder limpiarse"


@pytest.mark.parametrize("ruta", [
    os.path.join(CASA, "Downloads"),
    os.path.join(CASA, "Library/Developer/CoreSimulator/Devices"),
    os.path.join(CASA, "Library/Developer/CoreSimulator/Devices/ABCD-1234/data"),
])
def test_las_rutas_que_el_endpoint_web_borraba_igual_siguen_prohibidas(ruta):
    """Revisión final (ola de saneamiento), hallazgo 2: sobre el home real,
    de 10 objetivos que el endpoint de limpieza web mandaba a
    _perform_cleanup_deletes, dos eran cosas que esta verja prohíbe
    explícitamente -- ~/Downloads y
    ~/Library/Developer/CoreSimulator/Devices -- y se borraban igual
    porque ese endpoint solo filtraba con is_protected_path (lista negra
    del sistema operativo), no con puede_borrarse. Esto fija el lado de la
    verja: si alguna vez vuelve a fallar, no es porque puede_borrarse haya
    dejado de rechazarlas."""
    assert not puede_borrarse(ruta), f"{ruta} salió como borrable"


def test_containers_docker_data_ya_no_esta_en_la_whitelist():
    """~/Library/Containers/com.docker.docker/Data estuvo en
    _coincide_con_permitidas, pero ninguna regla de generate_recommendations
    ni de detect_smart_recommendations genera un comando de borrado contra
    esa ruta -- la limpieza de Docker siempre pasa por `docker system
    prune`/`docker volume`/`docker image`. Bajo esa ruta viven los
    volúmenes CON NOMBRE de Docker (bases de datos y otros datos
    persistentes del usuario), así que estar en la whitelist era un
    borrado silencioso de datos de usuario esperando un disparador: el
    endpoint web de limpieza (`_perform_cleanup_deletes`) podía llegar a
    ella a través de find_cache_locations() + una categoría "Docker"
    elegida a mano. Se quitó de la whitelist; este test fija que se queda
    fuera."""
    ruta = os.path.join(CASA, "Library/Containers/com.docker.docker/Data")
    assert not _coincide_con_permitidas(ruta), (
        f"{ruta} sigue en la whitelist de cachés conocidas"
    )
    assert not puede_borrarse(ruta), f"{ruta} salió como borrable"


# -- Segundo eje de la verja: por NOMBRE, no por ubicación (Task 7, ronda de
# arreglo 1). detect_smart_recommendations() encuentra node_modules
# huérfanos en cualquier proyecto del usuario -- rutas arbitrarias, no una
# ubicación fija que se pueda añadir a _coincide_con_permitidas. Decisión de
# producto explícita: node_modules se regenera con `npm install`, así que el
# nombre solo basta, siempre que is_protected_path ya lo haya dejado pasar. --

@pytest.mark.parametrize("ruta", [
    os.path.join(CASA, "Documents/repos/x/node_modules"),
    os.path.join(CASA, "Developer/algun-proyecto/node_modules"),
    "/Volumes/Backup Time Machine/proyecto/node_modules",
])
def test_node_modules_se_puede_borrar_por_nombre_aunque_este_en_datos_de_usuario(ruta):
    assert puede_borrarse(ruta), (
        f"{ruta} debería poder limpiarse: se llama 'node_modules'"
    )


@pytest.mark.parametrize("ruta", [
    os.path.join(CASA, "Documents/repos/x"),
    os.path.join(CASA, "Documents"),
])
def test_el_padre_de_node_modules_no_se_puede_borrar(ruta):
    """El eje por nombre es estrecho a propósito: solo el directorio que se
    llama exactamente 'node_modules', nunca su padre ni el resto de
    ~/Documents."""
    assert not puede_borrarse(ruta), f"{ruta} salió como borrable"


def test_node_modules_sigue_protegido_si_esta_bajo_una_ruta_de_sistema():
    """El eje por nombre no pasa por encima de is_protected_path: la regla
    del brief para instalar la verja era 'siempre que siga pasando
    is_protected_path', no un comodín absoluto."""
    assert not puede_borrarse("/System/Library/node_modules")


def test_una_ruta_relativa_o_vacia_nunca_se_borra(monkeypatch):
    # cwd deliberadamente fuera de cualquier prefijo prohibido: /cores no
    # aparece en RUTAS_DE_DATOS_DE_USUARIO ni en is_protected_path. Si el
    # rechazo de rutas relativas dependiera (por accidente) de que
    # abspath() aterrizara bajo una zona ya protegida -- como pasaba antes,
    # cuando ese chequeo era código muerto -- este cwd lo dejaría al
    # descubierto: con el bug, `relativa/sin/raiz` se convertiría en
    # `/cores/relativa/sin/raiz`, que no está prohibida por ningún otro
    # motivo, y el test fallaría.
    monkeypatch.chdir("/cores")
    assert not puede_borrarse("")
    assert not puede_borrarse("relativa/sin/raiz")


def test_no_se_puede_escapar_con_puntos():
    """`~/Library/Caches/../../Documents` es ~/Documents disfrazado."""
    assert not puede_borrarse(os.path.join(CASA, "Library/Caches/../../Documents"))


def test_los_temporales_del_sistema_los_gestiona_macos():
    """`/private/var/folders` está protegido a propósito.

    Aparece entre las cachés que el escáner encuentra (4,14 GB medidos), pero
    macOS gestiona ese directorio por su cuenta y borrarlo entero es
    arriesgado. Este test existe para que quede claro que la exclusión es
    deliberada y no un olvido.
    """
    assert not puede_borrarse('/private/var/folders')
    assert not puede_borrarse('/private/var/folders/x_/algo/T/tmpabc')


@pytest.mark.parametrize("ruta", [
    "/volumes/Backup Time Machine",            # /Volumes en minúsculas
    "/VOLUMES/BACKUP TIME MACHINE",            # todo en mayúsculas
    os.path.join(CASA.upper(), "DOCUMENTS"),   # ~/Documents con otra caja
])
def test_una_ruta_prohibida_sigue_prohibida_con_otra_caja(ruta):
    """APFS no distingue mayúsculas de minúsculas por defecto: cambiar la
    caja de una ruta prohibida no puede ser una forma de colarla."""
    assert not puede_borrarse(ruta), f"{ruta} salió como borrable (bypass por caja)"


@pytest.mark.parametrize("ruta", [
    os.path.join(CASA, "LIBRARY/CACHES/com.apple.Safari"),
    os.path.join(CASA.upper(), "LIBRARY/CACHES/COM.APPLE.SAFARI"),
    os.path.join(CASA, ".NPM/_cacache"),
])
def test_una_cache_legitima_sigue_limpiable_con_otra_caja(ruta):
    """Lo simétrico del test anterior: normalizar la caja no puede volverse
    tan estricto que una caché real deje de reconocerse.

    La afirmación es sobre `_coincide_con_permitidas`, no sobre
    `puede_borrarse` directamente: `puede_borrarse` tiene un `return True`
    por defecto al final, así que un `True` suyo no prueba que la ruta se
    haya reconocido como caché -- podría estar colándose por la puerta de
    atrás (que es justo el bug que este mismo test debía cazar y, en una de
    sus variantes, no cazaba). `_coincide_con_permitidas` no tiene ese
    "por defecto": si devuelve True es porque hubo coincidencia real.
    """
    assert _coincide_con_permitidas(ruta), (
        f"{ruta} no se reconoció como una caché conocida pese a la caja distinta"
    )
    # Y de paso, el comportamiento público de extremo a extremo también debe
    # sostenerse (esto sí puede pasar "por casualidad" en alguna variante,
    # pero la aserción de arriba ya cierra ese hueco).
    assert puede_borrarse(ruta), f"{ruta} debería poder limpiarse pese a la caja distinta"


def test_un_enlace_simbolico_no_permite_escapar_de_una_cache(enlace_de_cache_a_documents):
    """Un enlace real dentro de ~/Library/Caches (permitida) que apunta a
    ~/Documents (prohibida) no debe ser borrable.

    `borrar_contenido` ejecuta `rm -rf <ruta>/*`, y ese glob atraviesa el
    enlace: `abspath`/`normpath` no lo resuelven, hace falta `realpath`.
    """
    assert not puede_borrarse(enlace_de_cache_a_documents), (
        f"{enlace_de_cache_a_documents} salió como borrable (escapa a ~/Documents)"
    )
