# Registro de ejecución del plan de mejoras

Este documento registra qué se implementó realmente de cada fase: los commits,
las desviaciones del plan que se aprobaron durante la revisión y por qué, y los
hallazgos menores que quedaron diferidos. Es el complemento del
[roadmap](2026-07-15-roadmap-mejoras.md), que describe la intención, y de los
planes por fase, que describen los pasos.

Si retomas el trabajo, empieza por el [punto de entrada](README.md).

## Fase 1 — Bugs críticos del backend

**Estado:** completa. Mergeada a `main` el 15 de julio de 2026 mediante el
PR #5 (commit de merge `6c633df`). Rango: `d9f5542..b9977ae`, 11 commits.
Tests: 18 → 39.

La revisión final de la rama (modelo Fable, alcance whole-branch) dio veredicto
"Ready to merge: Yes", sin hallazgos críticos.

| Task | Qué arregló | Commits |
|---|---|---|
| 1 | Endpoints `/api/cleanup/preview` y `/execute`: `categories` opcional (antes respondían 422 siempre), sin `ValidationError` ni `TypeError`, guard `is_protected_path` antes de borrar | `877aba8` |
| 2 | `parse_docker_size` del core devolvía 0 para el formato real de `docker system df` (sin espacio, como `"1.5GB"`) | `e0f9d6d` |
| 3 | Las recomendaciones de VS Code y npm nunca disparaban en web ni GUI: `categorize_cache` emitía etiquetas distintas de las que filtraba `generate_recommendations` | `62cea1e` |
| 4 | `cleanup_idle()` del gestor de PTY nunca se llamaba, así que el tiempo de inactividad documentado no existía | `6406648`, `f4ceaff` |
| 5 | Las sesiones restauradas como `running` tras un reinicio quedaban colgadas para siempre; ahora pasan a `interrupted` | `6088744` |
| 6 | `PTYSession.kill()` dejaba procesos zombie | `930f465`, `655f1b1`, `cfcdb98`, `54923b5` |
| 7 | Verificación integral y arreglos de la revisión final | `d64a00c` |

### Desviaciones aprobadas

| Task | Desviación | Motivo |
|---|---|---|
| 3 | El test afirma sobre las etiquetas `'Cache de VS Code'` y `'Cache de npm'`, no sobre las claves `'vscode_cache'`/`'npm_cache'` que suponía el plan | Al leer el código, `generate_recommendations` no usa claves de máquina: el campo `type` guarda etiquetas de interfaz. El plan autorizaba adaptar el test a la realidad |
| 4 | El reaper reporta errores con `print()`, no con `logger.warning` | El módulo `disk_analyzer_web.py` no tiene logger configurado; `print(f"Warning: ...")` es la convención existente del archivo |
| 5 | El fixture usa una lista JSON de objetos con campo `id`, no un diccionario indexado por id | Es la forma real que escribe `save_session_metadata`. Con la forma del plan, el test habría fallado al acceder a `session_meta["id"]` |

### Rondas de arreglo durante la revisión

El Task 4 necesitó una ronda y el Task 6 tres. Vale la pena conocerlas porque
documentan trampas reales del código:

- **Task 4, ronda 1:** el test del plan solo comprobaba que existiera el
  atributo `_idle_terminal_reaper`, y habría pasado igual sin registrar la
  tarea en `startup_event`. Se añadió un test de cableado con
  `with TestClient(app):` (que sí dispara el ciclo de vida) y un test de
  comportamiento del bucle.
- **Task 6, ronda 1:** el reap síncrono de 2 segundos corría sosteniendo el lock
  del gestor de PTY y sobre el hilo del event loop, así que podía congelar toda
  la aplicación varios segundos. Se cambió a extraer las sesiones bajo el lock y
  matarlas fuera, más `asyncio.to_thread` en los puntos que corren en el loop.
- **Task 6, ronda 2:** se añadió un atajo para no señalar procesos ya muertos
  (`create_terminal` y `list_terminals` también salieron del event loop).
- **Task 6, ronda 3:** el atajo confiaba en la bandera `self.alive`, pero
  `_read_loop` la apaga ante cualquier `OSError`, no solo cuando el hijo muere.
  Un hijo vivo marcado como muerto se quedaba sin señales, agotaba el plazo de 2
  segundos y perdía su `pid`: una fuga de procesos. Se reemplazó por un
  `waitpid(WNOHANG)` previo como prueba autoritativa.

### Hallazgos menores diferidos

Todos se triaron en la revisión final. Ninguno bloquea:

| Hallazgo | Diferido a |
|---|---|
| `cleanup/execute` borra de forma permanente en vez de mover a la Papelera, como sí hace `DELETE /api/files/delete` | Fase 2 |
| `cleanup/execute` con `dry_run=true` devuelve la forma de `preview`, no la documentada de `execute` | Fase 4 |
| `import re` local en `parse_docker_size` (consistente con el CLI) | Fase 3 |
| El reaper usa `print()` en vez de un logger | Fase 3 |
| `web/src/lib/api.ts:22` no incluye `'interrupted'` en el tipo de estado de sesión | Fase 4 |
| Un test escanea el `Path.home()` real, así que es lento y depende de la máquina | Fase 5 |
| El test de cableado del reaper arranca el ciclo de vida completo (fixture pesada) | Fase 5 |
| Falta un test end-to-end del camino 429 (máximo de sesiones) de `create_terminal` | Fase 5 |
| Reuso del nombre `reaped_pid` para dos fases distintas dentro de `kill()` | Cosmético, sin fase |

## Fase 2 — Seguridad

**Estado:** completa y mergeada a `main` mediante el PR #6. Rama de origen:
`feat/fase2-seguridad`, creada desde `6c633df`. Tests: 39 → 79.

| Task | Qué hace | Estado |
|---|---|---|
| 1 | Auth por token para `/api/*`, CORS restringido a los orígenes de desarrollo, flag `--no-auth` | ✅ `58debfa` |
| 2 | Validar el token en los dos WebSockets antes de `accept()`, cierre 1008 | ✅ `8f6c799` |
| 3 | Agents en modo simulación por defecto; `/run` exige `confirm=true` | ✅ `2bf082c` |
| 4 | El frontend adjunta el token en REST y WebSockets | ✅ `ff44e7a`, `078915c`, `abbbb2b` |
| 5 | El shell del PTY no hereda descriptores de archivo del servidor | ✅ `e601638` |
| 6 | Verificación integral y revisión final de la rama | ✅ `c7123a0`, `75d90f4`, `77ec058`, `bd70763`, `5ce9416` |

### Lo que encontró la verificación final

Los tests unitarios pasaban en verde mientras dos fallos serios seguían vivos.
Los encontraron la prueba de humo contra un servidor real y la revisión final de
la rama, no la suite:

- **Un 500 en `/api/agents/{id}/run`.** `_log()` reventaba con `PermissionError`
  porque `~/.disk-analyzer/agents.log` había quedado propiedad de `root` por una
  corrida previa con `sudo`. Un fallo al escribir el log tumbaba la operación
  entera. Arreglado en `c7123a0`: escribir el log nunca propaga un error de E/S,
  y los fallos al guardar estado se reportan en la respuesta (`state_saved`,
  `warning`) en vez de fingir éxito.
- **Lectura de archivos arbitrarios sin autenticación (crítico).** La ruta
  catch-all que sirve el SPA unía la ruta de la URL a `web/dist` sin contención,
  y `.is_file()` resuelve los `..` a nivel del sistema. Verificado en vivo contra
  un servidor real: `curl --path-as-is` con suficientes `../` devolvía
  `/etc/hosts` y `sessions_metadata.json`, con 200 y sin token. Como el token se
  imprime por stdout, quien hubiera redirigido esa salida a un archivo lo
  entregaba por el mismo hueco, y con el token se llega al terminal. Arreglado en
  `75d90f4` con `resolve()` más `is_relative_to()`.

  Esto merece registrarse como lección, no solo como arreglo: las restricciones
  del plan afirmaban que las rutas estáticas y del SPA eran seguras de dejar
  abiertas porque "solo sirven JS y CSS". Nadie verificó esa premisa, y era falsa
  — justo la premisa sobre la que se apoyaba todo el diseño de autenticación.
  Además el `TestClient` de Starlette normaliza los `..` de las URLs, así que un
  test normal habría pasado igual contra el código vulnerable: el test de
  regresión construye el scope ASGI a mano.

También se corrigieron en la misma ola: un 500 sin autenticar ante un token con
caracteres no ASCII (`compare_digest` no acepta `str` no ASCII), un `mkdir` sin
protección en tiempo de importación que impedía arrancar si `~/.disk-analyzer`
era de `root`, el `toggle_agent` que ignoraba si el estado se había guardado, el
frontend que ante un token vencido fallaba en silencio y reconectaba sin fin
(`bd70763`), y tres detalles de higiene del PTY (`5ce9416`): el shell ya no ve el
token en su entorno, el `closerange` quedó acotado —`SC_OPEN_MAX` en esta máquina
es 1.048.576, así que eran un millón de `close()` por terminal— y una salida
segura si `execvp` falla.

### Alcance añadido durante la ejecución

Dos cosas que el plan no anticipaba y que se resolvieron dentro de la fase,
porque la propia fase las rompió:

- **El panel de agents quedó como un botón muerto.** El Task 3 hizo que `/run`
  simule si no recibe `confirm=true`, así que el botón "Run now" de
  `AgentsPanel.tsx` dejó de hacer nada visible. Se arregló en el Task 4: el
  botón pide una confirmación al usuario mostrando los comandos exactos que se
  van a ejecutar, y luego manda `confirm=true`. Falla cerrado: si la sonda de
  simulación no responde bien, cancela en vez de ejecutar sin haber mostrado el
  diálogo.
- **Las descargas de export daban 401.** Se abrían con `window.open`, que no
  puede mandar el header del token. Se cambió a descarga por `fetch`
  autenticado más blob (commit `078915c`), y se eliminó `getExportUrl`. Se
  descartó deliberadamente la alternativa de aceptar el token como query param
  en el backend: filtraría el token a los logs del servidor y al historial del
  navegador, y tocar la puerta de autenticación arriesga abrir un bypass.

### Decisiones de diseño de la fase

| Decisión | Alternativas | Motivo |
|---|---|---|
| Autenticación activada por defecto | Desactivada por defecto con `--auth` como opt-in | Un servidor que escucha en `0.0.0.0` con acceso a borrado de archivos y terminal debe ser seguro por defecto. `make web` sigue siendo un comando: el banner imprime el enlace con el token |
| Token en el header `X-Auth-Token`, nunca en cookie | Cookie de sesión | Un header propio no es autoridad ambiental: un sitio malicioso no puede adjuntarlo ni leerlo, así que el CSRF queda descartado por construcción. Una cookie lo reintroduciría |
| Middleware HTTP para `/api/*` más chequeo aparte en los WebSockets | Mover las 25 rutas a un `APIRouter` con `dependencies=[Depends(...)]` | El middleware da un diff mucho menor sobre un archivo monolítico de 1.300 líneas. El precio es que los WebSockets necesitan su propio chequeo, que de todas formas era inevitable: Starlette los salta en el middleware HTTP |
| El token viaja por variable de entorno | `app.state` o globals de `__main__` | Con `reload=True`, uvicorn re-importa el módulo en un subproceso worker que no ve nada definido en `__main__` |
| El planificador de agents queda en simulación permanente en esta fase | Ejecución real desatendida con una bandera | Borrar sin supervisión es una decisión de producto, no de seguridad. El usuario puede ejecutar de verdad bajo demanda con `confirm=true` |

### Desviaciones aprobadas

| Task | Desviación | Motivo |
|---|---|---|
| 1 | `tests/conftest.py` parchea los atributos `NO_AUTH` y `AUTH_TOKEN` del módulo con `monkeypatch.setattr`, además de la variable de entorno | La versión del plan (solo entorno) dependía del orden de ejecución: los archivos de test importan `app` al colectarse, antes de que corra cualquier fixture, así que los valores ya estaban calculados. Con el plan literal, `test_cleanup_api.py` y `test_terminal_api.py` fallaban con 401 al correr aislados |
| 1 | El middleware de autenticación se registra antes que el de CORS, al revés de lo que decía el plan | Starlette ejecuta los middlewares en orden inverso al de registro, así que este orden deja el de CORS por fuera y las respuestas 401 llevan sus headers. Verificado empíricamente |
| 2 | El helper de test afirma que el código de cierre sea 1008, no solo que el WebSocket se cierre | Sin esa afirmación el test del WebSocket del terminal era un falso positivo: ya se cerraba con 4004 por la verificación preexistente de `pty_id`, así que habría pasado antes del arreglo. La afirmación del código es lo que prueba que la puerta del token corre primero |
| 5 | El test fuerza un descriptor heredable con `os.set_inheritable(w, True)` en vez de usar el `os.pipe()` simple del plan, y lo sondea con un builtin del shell en vez de `ls -l /dev/fd` | Desde PEP 446 (Python 3.4+), `os.pipe()`, `os.openpty()` y `socket.socket()` ya devuelven descriptores no heredables, así que `exec()` los cierra incluso sin el arreglo: el test del plan habría pasado por la razón equivocada |
| 3 | El hallazgo #4 del roadmap pedía que los agents dejaran de construir strings de shell y pasaran a usar `is_protected_path` y mover a la Papelera en vez de `rm -rf`; solo se implementó la mitad de simulación + confirmación | Reescribir los agents de comandos de shell a operaciones de archivo en Python guardadas es un rediseño que excede el alcance de esta fase. Con `confirm=true`, `agents_manager.py` sigue ejecutando los comandos `rm -rf` crudos vía `subprocess.run(..., shell=True)`, sin guard de ruta protegida y sin paso por Papelera: es irreversible. La mitigación que sí se entregó es que nada corre sin una confirmación explícita que muestra los comandos exactos antes de ejecutarlos. El rediseño completo queda diferido a una fase posterior |

### Hallazgos menores diferidos

| Hallazgo | Nota |
|---|---|
| `/docs` y `/openapi.json` quedan sin autenticación | Fuera del alcance declarado (solo `/api/*`). Exponen el esquema, no datos |
| El test de rutas abiertas solo cubre `/`, no los montajes `/static` ni `/_astro` | Sin riesgo: están fuera del prefijo que revisa el middleware |
| Falta el salto de línea final en `disk_analyzer_web.py` | Cosmético |
| La segunda llamada de `AgentsPanel` (la real, con `confirm=true`) no revisa `res.ok` antes de `res.json()` | No es un bypass: el diálogo ya se mostró. Solo degrada el mensaje de error a uno genérico |
| La lógica de arranque del token está duplicada en `auth.ts` y en el script inline de `MainLayout.astro` | Deliberado: el script inline limpia la URL en el primer render, antes de que hidrate cualquier isla. Hay que mantener las dos copias en sincronía a mano |
| No hay tests de frontend para la lógica de fallo cerrado | El repo no tiene suite de JS. Candidato para la Fase 5 |
| El token viaja en la query string de los WebSockets sobre `ws://` sin cifrar | Inevitable: el `WebSocket` del navegador no puede mandar headers. Asumido por el modelo de confianza de LAN que ya documenta `CLAUDE.md` |

### Nota honesta sobre el alcance real del Task 5

El arreglo de descriptores de archivo es defensa en profundidad, no el cierre de
un agujero explotable hoy. Desde PEP 446, los descriptores que abre el propio
Python (el maestro del PTY, el socket de uvicorn) ya son no heredables por
defecto, así que `exec()` los cerraba de todos modos. El `closerange` protege
contra descriptores que sí sean heredables, presentes o futuros, sin depender de
que cada punto del código recuerde marcarlos. Vale registrarlo así para que
nadie sobrevalore la severidad al leer el historial.

## Fase 3 — Motor compartido

**Estado:** completa y mergeada a `main` mediante el PR #7. Rama de origen:
`feat/fase3-motor-compartido`, apilada sobre la de la Fase 2. Tests: 79 → 137.

| Task | Qué hace | Estado |
|---|---|---|
| 1 | Red de tests de caracterización del motor (antes no había ninguno) | ✅ `cbf7bc5`, `5455a18` |
| 2 | Constantes compartidas en `analyzer/constants.py` | ✅ `36b15fe` |
| 3 | `is_protected_path` en `analyzer/protection.py` | ✅ `acd3395` |
| 4 | Una sola clasificación de cachés con etiquetas como constantes | ✅ `102c678`, `871eb6c` |
| 5 | Una sola forma de medir directorios y un solo umbral de cachés | ✅ `0374706` |
| 6 | Verificación integral | ✅ |

Resultado: `disk_analyzer.py` 4.882 → 4.737 líneas, `disk_analyzer_core.py` 762
→ 630, más 281 líneas de paquete `analyzer/` compartido. La cifra neta importa
menos que el hecho de que constantes, protección de rutas, clasificación de
cachés y medición de directorios ahora existen **una sola vez**.

### Lo que encontró la red de caracterización

Escribir los tests antes de mover nada era el paso obligatorio del plan, y se
pagó solo: destapó un bug real en el motor que usan la web y la GUI.
`categorize_cache` evaluaba `'code' in path_str` antes que `'xcode'`, y como
"code" es substring de "xcode", toda ruta de Xcode se clasificaba como
`'VS Code Cache'` y la rama de Xcode era código muerto. Los usuarios de web y
GUI veían sus cachés de Xcode mal etiquetadas y la recomendación específica de
Xcode nunca disparaba. El CLI lo hacía bien. El Task 4 lo arregló al unificar.

También durante la revisión: dos tests de caracterización resultaron ser vacuos
(no fallaban ante la mutación que decían detectar) y se reforzaron; y el Task 3
destapó que `/api/files/delete` usaba `DiskAnalyzerCore.__new__(DiskAnalyzerCore)`
para saltarse el `__init__` entero, un rodeo peor que el que el plan había
detectado.

### Decisiones de diseño de la fase

| Decisión | Alternativas | Motivo |
|---|---|---|
| Conservar el conjunto de 12 etiquetas del core | Las 8 del CLI | Es el más granular y el que ya ven la web y la GUI; las recomendaciones del core se le alinearon en la Fase 1 |
| Medir directorios con `rglob` + `st_blocks` | `du -sk` por subproceso, como hacía el CLI | Coherente con cómo mide el resto del motor y sin depender de un subproceso. Consecuencia medida: sobre este repo da +3,29 % frente a `du`, porque `du` cuenta los enlaces duros una vez y el recorrido los cuenta por cada entrada (npm crea enlaces duros en `node_modules`) |
| Umbral de cachés en `> MB` | El `> 0` del core | Una caché de 3 KB no es accionable y solo ensucia la lista |
| **No** hacer borrables las cachés de Python | Incluir `PYTHON` en `SAFE_TO_CLEAN` | Ver abajo |

### La decisión sobre las cachés de Python

El safelist viejo del CLI contenía literalmente `'Python Cache'`, pero su
clasificador nunca producía esa etiqueta: era una entrada muerta, y las cachés
de Python siempre caían en `'Cache General'` y no se limpiaban nunca. Al
unificar, el clasificador compartido sí produce esa etiqueta, así que incluirla
en el safelist las habría hecho borrables por primera vez.

Se decidió **excluirlas**, y conviene registrar por qué, porque el primer
razonamiento fue equivocado. La justificación inicial para dejarlo pasar era que
`clean_cache` manda a la Papelera en macOS y pide confirmación. Al verificar el
código resultó falso a medias: la rama de Papelera solo aplica a archivos
sueltos; para **directorios** —que es exactamente lo que son las cachés de
Python— hace `item.unlink()`, borrado permanente. Y la confirmación es una sola
para todo el lote, no por categoría.

Así que se restauró la paridad real de comportamiento (lo que el CLI *hacía*, no
lo que su texto muerto decía) y queda como decisión explícita del dueño del
proyecto, no como efecto colateral de un refactor.

### Hallazgo pendiente que vale la pena no perder

`clean_cache` borra directorios con `unlink()` permanente para **todas** las
categorías del safelist, no solo las de Python, y eso contradice su propio
comentario "Mover a Trash en macOS". Afecta a logs, VS Code, npm y Xcode.
Candidato claro para una fase posterior.

## Fase 5 — Tests y CI

**Estado:** completa y mergeada a `main` mediante el PR #8, con **CI en verde**
(backend en macOS 29 s, frontend en Ubuntu 36 s).
Tests: 137 → 151. Tiempo de la suite: **~44 s → ~4 s**.

| Task | Qué hace | Estado |
|---|---|---|
| 1 | La suite deja de escanear las cachés reales de la máquina | ✅ `67ef75c` |
| 2 | Cubrir export, borrado de archivos, digest y último análisis | ✅ `14ddd8b`, `6f66b59` |
| 3 | 429 del terminal end-to-end y fixture de auth aligerada | ✅ `1fa72fe`, `a94f951` |
| 4 | Frontend verificable: `npm run check` y los errores de tipos preexistentes | ✅ `7f191f9` |
| 5 | CI en GitHub Actions y `make test` | ✅ `53fcb7b` |
| 6 | Verificación integral | ✅ |

### Por qué el orden no fue el del roadmap

El roadmap ponía el CI primero. Se dejó de penúltimo a propósito: automatizar una
suite de 44 segundos que además depende de lo que cada quien tenga instalado
produce CI que la gente aprende a ignorar. Primero se arregla, luego se
automatiza.

Dos tests consumían 39 de esos 44 segundos porque pasaban `Path.home()` al
endpoint de limpieza, que acaba recorriendo las cachés reales. En CI, con un
`$HOME` vacío, habrían probado algo distinto en silencio.

### Lo que apareció por el camino

- **Bug de contrato entre frontend y backend:** `api.getSessions()` estaba tipado
  como `AnalysisSession[]`, pero el backend devuelve `{"sessions": [...]}`. Los
  tres sitios que la llamaban habían redescubierto el problema por separado y lo
  tapaban con `any`. Lo destapó tipar el frontend, no un test.
- **`astro check` ve cinco errores que `tsc` no:** están en archivos `.astro`
  (globales de `window` compartidas entre islas, un `EventTarget` sin tipar). Y
  necesita que `tsconfig.json` excluya `dist`, o se desborda la pila de V8
  recorriendo el build.
- **`DiskDonut.tsx` era código muerto**, superado por `DiskBar.tsx`. Borrado.
- **La fixture de auth dependía del orden de ejecución:** pasaba en la suite
  completa y aislada, pero fallaba con `--lf` o con selección de tests por
  nombre. Peor: algunas aserciones habrían pasado en silencio con el módulo en
  el estado equivocado. Se hizo correcta en cualquier orden, verificándolo al
  reproducir el fallo primero.
- **Varios de los tests que este mismo plan proponía** habrían dependido del
  `$HOME` real (el directorio de resultados y el log de agents). Se detectaron al
  implementarlos.

### Decisiones del CI

| Decisión | Motivo |
|---|---|
| El job de backend corre en `macos-latest` | El proyecto es específico de macOS y los tests de PTY dependen de `pty.openpty()`, `os.fork()` y el `waitpid` de Darwin. En Ubuntu probarían otra cosa |
| El de frontend corre en `ubuntu-latest` | Es solo Node: más rápido y más barato ahí |
| Se reprodujo el entorno de CI en un venv limpio antes de subirlo | Para que un `pip install` que solo funciona en local por acumulación no se descubra en el primer fallo de CI. Confirmó que `requirements-web.txt` está completo |

### Pendiente que necesita decisión del dueño

La **protección de la rama `main`** quedó preparada pero **sin aplicar**: exigir
los checks antes de mergear cambia cómo trabaja cualquiera en el repo, así que no
se toca sin permiso. El comando está en el Task 6 del
[plan de la Fase 5](2026-08-01-mejoras-fase5-tests-y-ci.md). Hasta que se
aplique, un `--auto` seguirá fusionando en cuanto los checks pasen, pero nada
impide un merge directo saltándoselos.

## Fase 4 — Frontend

**Estado:** completa. Rama de origen: `feat/fase4-frontend`, apilada sobre
`main` tras la Fase 5. Plan detallado:
[Fase 4](2026-08-10-mejoras-fase4-frontend.md). Tests de frontend: **0 → 66**
(no existía suite de JS antes de esta fase). Tests de backend: 151 → 151, sin
cambio de alcance, más un fix de compatibilidad encontrado por el camino (ver
abajo).

| Task | Qué hace | Commits |
|---|---|---|
| 1 | Infraestructura de tests JS (Vitest + Testing Library + jsdom) y `useCleanupRunner`, el hook que solo acredita el ahorro cuando el comando termina con código de salida 0 | ✅ `f638b99` |
| 2 | Migrar los seis flujos de limpieza (`QuickActions`, `CleanupWizard`, `GuidedDeclutter`, `WhatIfSandbox`, `ReverseView`, `DockerPanel`) al hook compartido; arreglar la doble ejecución de comandos destructivos y el estancamiento de las limpiezas en lote | ✅ `5df450c`, `9dc2530`, `be1f9c2`, `ce0f1cf` |
| 3 | Una sola definición de categorías (`getCategory`/`CATEGORY_COLORS` en `lib/categories.ts`) y de niveles de riesgo (`TIER_META`/`getTierBucket` en `lib/tiers.ts`), antes duplicadas entre componentes | ✅ `5c63f8b` |
| 4 | Cargar la sesión pedida desde Historial (antes siempre mostraba la última), y reenganchar el progreso del análisis y la terminal flotante al navegar entre páginas | ✅ `a2ec0d0` |
| 5 | Terminal sin CSS servido desde un CDN externo, CSS inválido del menú corregido, colores de `TaskList` legibles en modo oscuro, código muerto eliminado (`useAnalysis`, `useWebSocket`, `formatPercent`) | ✅ `12707dd` |
| 6 | Tests de frontend cableados al CI y a `make test`; cierre del registro | ✅ `c05ffbe` |

Al margen de los tasks numerados, durante el Task 1 se encontró y arregló un
bug real de compatibilidad con Python 3.11 (`analyzer/measurement.py`,
`disk_analyzer_core.py` y `disk_analyzer.py` usaban
`Path.is_file(follow_symlinks=False)`, que solo existe desde Python 3.13;
reemplazado por `Path.lstat()` + `stat.S_ISREG`/`S_ISDIR`, semánticamente
idéntico y disponible desde Python 3.4): `a33beee`, `4d17879`. No es parte del
alcance de la fase (es backend, y esta fase no toca backend), pero se aceptó
porque sin él la suite completa daba 9 falsos negativos en cualquier máquina
donde `python` resuelva a 3.11 en vez de al `venv-web` de 3.13 — que es
exactamente lo que le pasó al primer implementador de esta fase.

### Lo que encontró la migración de limpieza (Task 2)

Migrar los seis flujos al mismo hook no fue solo una deduplicación: destapó
tres bugs de verdad, dos de ellos con comandos destructivos de por medio.

- **Comandos destructivos ejecutándose dos veces.** `FloatingTerminal` escuchaba
  `terminal:open` pero ignoraba el `pty_id` que el evento ya traía (el PTY que
  `useCleanupRunner.run()` acababa de crear y estaba vigilando). Si no había
  terminal abierta, `FloatingTerminal` creaba **una segunda** con
  `api.createTerminal(data.command)` — para un comando destructivo
  (`docker system prune`, variantes de `rm -rf` en la limpieza de cachés) eso
  es doble ejecución real, no solo doble UI. Si ya había una terminal abierta,
  pasaba lo contrario: no se conectaba a nada, el comando corría invisible en
  el servidor y, como ningún WebSocket se pegaba a ese `pty_id`, su
  `terminal:exited` nunca llegaba — `useCleanupRunner` nunca lo acreditaba.
  Arreglado separando `useTerminal.spawn()` (crear + conectar) de un
  `attach(id, command)` nuevo (solo conectar a un PTY que ya existe), y
  haciendo que `FloatingTerminal` use `attach` cuando el evento trae
  `pty_id`.
- **Limpiezas en lote que se quedaban en "Running…" para siempre.** Las cuatro
  acciones en lote (`WhatIfSandbox.applyCleanup`, `CleanupWizard.cleanSafeItems`,
  `GuidedDeclutter.cleanStep`, `ReverseView.cleanTier`) lanzaban `run()` en
  bucles sin esperar. Con un PTY por comando y la terminal flotante mostrando
  uno solo, conectar el segundo mataba el socket del primero — de un lote de
  3 comandos, solo se veía el `terminal:exited` del último; los otros dos
  terminaban bien en el servidor pero no se acreditaban nunca y sus botones
  quedaban en "Running…" permanentemente. Arreglado moviendo el estado de
  `useCleanupRunner` a un singleton de módulo (`useSyncExternalStore`) con una
  **cola serializada**: un job a la vez, el siguiente solo arranca cuando el
  anterior resuelve su `terminal:exited` (o un watchdog de 10 minutos se rinde
  sin acreditar nada).
- **El mismo comando destructivo lanzado dos veces en paralelo.** Antes del
  singleton, cada `useCleanupRunner()` montado tenía su propio estado. En
  `index.astro` (`QuickActions` + `ReverseView` + `DockerPanel`) y en
  `cleanup.astro`, los conjuntos de recomendaciones de distintos componentes se
  solapan (el tier "safe" de `ReverseView` es superconjunto del top-3 de
  `QuickActions` para el mismo análisis), así que hacer clic en la misma
  recomendación desde dos componentes distintos disparaba `api.createTerminal`
  dos veces para el comando idéntico. El estado compartido cierra esto: el
  guard "ya en ejecución/completado" ahora es real entre componentes, no solo
  dentro de uno.
- Además, antes de esta fase: `DockerPanel` acreditaba el ahorro con un
  `setTimeout` de 5 segundos sin comprobar si el prune había terminado de
  verdad; `GuidedDeclutter`, `WhatIfSandbox` y `ReverseView` acreditaban el
  total agregado del lote al instante, antes de que corriera un solo comando,
  así que un lote donde todo fallaba igual se contaba como ahorro; y
  `CleanupWizard` persistía su propio estado "Running…" en
  `localStorage['disk-analyzer-wizard-running']` (sobrevivía a un reload aunque
  el comando ya hubiera terminado o fallado) y nunca emitía
  `cleanup:completed` — limpiar desde el wizard nunca contaba para el ahorro
  mostrado en el resto de la interfaz. Los seis flujos ahora comparten
  exactamente la misma regla: se acredita lo que terminó con código 0, ni más
  ni menos.

### Lo que encontraron los demás tasks

- **Task 3:** las dos copias de `getCategory` (`DiskBar.tsx`, `FileTable.tsx`)
  resultaron ser idénticas carácter por carácter (verificado con un diff
  insensible a espacios) — puro riesgo de que divergieran en el futuro, no un
  bug activo. Los cuatro niveles de riesgo coincidían en color pero no en
  etiqueta: el tier 4 era "Deep Clean" en `CleanupWizard` y "Deep" en
  `WhatIfSandbox`.
- **Task 4:** `SessionList.loadSession` pedía los resultados y emitía
  `analysis:completed` **antes** de navegar — el evento moría con la página, así
  que elegir una sesión histórica en Historial siempre acababa mostrando la
  más reciente, nunca la elegida. El progreso del análisis y la terminal
  flotante tampoco sobrevivían a navegar entre páginas: no había ningún efecto
  de reenganche al montar. Arreglado con `?session=<id>` en la URL más un
  efecto de reenganche en `AnalysisManager` (busca una sesión `running` vía
  `getSessions()`) y otro en `useTerminal` (persiste el `pty_id` activo en
  `sessionStorage`, solo reengancha si el servidor confirma que sigue vivo).
- **Task 5:** el CSS de xterm.js se cargaba desde `cdn.jsdelivr.net` en cada
  apertura de la terminal — roto sin red, y una dependencia externa que no
  pega con el resto del build offline-first. El menú lateral usaba
  `left: -var(--sidebar-width)`, CSS inválido (la sintaxis `-var()` no existe;
  los navegadores descartan la declaración entera), así que "el menú debe
  empezar fuera de pantalla" no era cierto pese a que el código lo sugería.
  `TaskList` usaba fondos pastel fijos (`#eff6ff`, etc.) que son casi
  ilegibles contra texto claro en modo oscuro.

### Decisiones de diseño de la fase

| Decisión | Alternativas | Motivo |
|---|---|---|
| Estado de `useCleanupRunner` como singleton de módulo vía `useSyncExternalStore`, no `useState` por instancia | Un hook independiente por componente montado | Varios componentes pueden mostrar el mismo comando a la vez (`index.astro`, `cleanup.astro`); sin estado compartido, el guard "ya en ejecución/completado" no ve lo que hacen los demás y el mismo comando destructivo puede lanzarse dos veces |
| Cola serializada — un job a la vez | Un PTY por `run()`, en paralelo | La terminal flotante solo puede mostrar un PTY a la vez; con varios en paralelo, conectar el último mata el socket de los anteriores y sus `terminal:exited` se pierden — la causa exacta del estancamiento en lote |
| Un fallo a mitad de lote no aborta el resto de la cola | Abortar el lote entero ante el primer error | Los comandos restantes son independientes y pueden tener éxito igual; abortarlos dejaría trabajo sin hacer por una razón que no tiene que ver con ellos |
| Watchdog de 10 minutos que desatasca un job sin acreditarlo nunca | Sin timeout, o uno más corto | Cubre un `terminal:exited` que de verdad se pierde (reinicio del servidor); 10 minutos deja margen a comandos reales largos (`docker system prune`, `brew cleanup`) sin bloquear la cola para siempre si algo se atasca. Un timeout solo desatasca, nunca acredita |
| `TIER_META` usa "Deep Clean" (etiqueta de `CleanupWizard`) para el tier 4 | "Deep" (etiqueta de `WhatIfSandbox`) | `CleanupWizard` es la superficie canónica de frase completa; "Deep Clean" describe mejor el tier del que hay que ser más cauteloso, y el badge de `WhatIfSandbox` tiene espacio de sobra para la etiqueta larga |
| `?session=<id>` no se limpia de la URL tras cargar una sesión histórica | Limpiarlo, como se hace con el token de auth | El token se limpia por seguridad; el id de sesión no es sensible, y dejarlo hace la URL bookmarkeable/compartible |
| El `pty_id` activo se persiste en `sessionStorage`, no en `localStorage` | `localStorage` | Una terminal viva no debería sobrevivir a un reinicio completo del navegador — mismo criterio que el token de auth (Fase 2) |

### Hallazgos menores diferidos

| Hallazgo | Nota |
|---|---|
| `cleanup/execute` con `dry_run=true` devuelve la forma de `preview`, no la documentada de `execute` | Sigue diferido: es un cambio de backend y esta fase no lo tocó (registrado desde la Fase 1) |
| `p.includes('Docker.raw')` en `lib/categories.ts` es código muerto (la ruta ya está en minúsculas por `path.toLowerCase()`, así que un literal con mayúsculas nunca puede coincidir) | Sin efecto observable — queda sombreado por `p.includes('docker')` en la misma línea. Se dejó tal cual al mover el código verbatim (Task 3 no era una reescritura) |
| Un test de `formatAge` (`switches to weeks at the 7-day boundary`) falló una vez durante la verificación de este task y pasó en 9 corridas posteriores consecutivas | No se pudo reproducir una segunda vez; no bloqueó el cierre de la fase, pero vale vigilarlo si reaparece en CI |
| `web/src/lib/api.ts` no incluye `'interrupted'` en el tipo de estado de sesión | Seguía diferido desde la Fase 1; no se tocó en esta fase |

### Fuera de alcance, declarado en el plan

El rediseño visual y extender la cobertura de tests al resto del frontend
quedaron fuera a propósito — ver
[el plan de la Fase 4](2026-08-10-mejoras-fase4-frontend.md#fuera-del-alcance-de-esta-fase)
para el razonamiento completo.

## Fase 0

Sin ejecutar. El alcance, la secuencia recomendada y los criterios de
aceptación están en el [roadmap](2026-07-15-roadmap-mejoras.md).

## App de bandeja — rebanada A (20 de agosto de 2026)

Trabajo aparte del plan de mejoras: una app nativa de macOS anclada en la barra
superior que muestra el estado del disco en tiempo real. El diseño está en
[el spec](../specs/2026-08-19-app-bandeja-tauri-design.md) y los tasks en
[el plan de la rebanada A](2026-08-20-app-bandeja-rebanada-a.md).

Rama `feat/app-bandeja-tauri`. Tauri 2 + Rust, en `desktop/`.

| Task | Qué entregó | Commit |
|---|---|---|
| 1 | Decisiones D1–D4 cerradas | `docs:` en el plan |
| 2 | Andamiaje de Tauri, política de accesorio, permisos | — |
| 3 | `disk.rs` + test de consistencia contra el motor Python | `b4d371e` |
| 4 | `estado.rs` (umbrales) y generador de iconos | `c86d591` |
| 5 | Menú vivo y análisis cancelable, un proceso a la vez | `d286a06` |
| 6 | `.app` empaquetada y runbook de firma | `4456ac4` |
| 7 | CI de Rust y cierre de la documentación | este commit |

### Lo que cambió respecto al plan

**PyInstaller quedó descartado a mitad de ejecución.** El antivirus de la
máquina puso en cuarentena los tres binarios que produjo, con una firma genérica
de malware — un falso positivo conocido del *bootloader* autoextraíble de
PyInstaller. La hipótesis inicial de arreglo (cambiar `--onefile` por `--onedir`)
era **incorrecta**: el bootloader está en los dos modos.

Consecuencia declarada: la app **no es autocontenida y no se puede distribuir**.
Invoca `venv-web/bin/python` por ruta absoluta. El indicador de disco no depende
de Python y sigue funcionando aunque el motor falte.

**La firma y la notarización siguen pendientes** (decisión D4, sin cuenta de
Apple). La `.app` va firmada ad hoc. El certificado autofirmado que D4 preveía
—para que el permiso de Acceso a disco completo sobreviva a las recompilaciones—
necesita la contraseña del llavero desde la interfaz; el procedimiento exacto
está en el [runbook](../../runbooks/app-bandeja.md).

### Tres defectos encontrados revisando el Task 5

El subagente entregó código correcto en lo grueso, con tres fallos reales:

1. Los ficheros temporales se nombraban con el PID de la app, **igual para todos
   los escaneos**: un segundo escaneo abría con `File::create` el `stderr` del
   primero y se lo truncaba en marcha. Ahora llevan número de serie.
2. `cancelado` se reseteaba **tras** soltar el candado de `pid`, dejando una
   ventana en la que un `cancel()` ya enganchado a ese pid ponía la bandera y se
   la borrábamos: el escaneo moría de nuestro propio SIGTERM pero se reportaba
   como fallo en vez de como cancelado.
3. No había ningún test de la parte capaz de dejar procesos huérfanos.

**Los primeros tests que escribí para (3) no servían.** Pasaban igual de
contentos contra un `kill(pid)` que nunca toca al grupo de procesos. La causa:
cancelaban justo después de `spawn`, y a esa velocidad `sh` todavía no ha
forkeado nada, así que no existe ningún nieto que pueda quedar huérfano. Ahora el
hijo de prueba deja un fichero-marca *después* de crear su proceso en segundo
plano y el test espera esa marca. Verificado por mutación: con la espera, cambiar
`kill(-pid)` por `kill(pid)` tumba las tres pruebas; sin ella, esa misma versión
rota pasaba.

Es el motivo de que la verificación por mutación esté anotada en el propio
código: un test de limpieza de procesos que nunca ha visto un proceso sucio no
prueba nada.

### Verificación manual (20 de agosto de 2026, macOS 26.5.1)

Hecha sobre la `.app` de release, no en modo desarrollo:

| # | Comprobación | Resultado |
|---|---|---|
| 1 | Icono legible en tema claro y oscuro | ✅ Verificado componiendo los tres estados sobre ambos fondos |
| 2 | Legible con "Reducir transparencia" | ⚠️ **Sin verificar**: exige cambiar un ajuste de accesibilidad del sistema |
| 3 | Legible sobre fondo de escritorio claro y oscuro | ✅ Verificado |
| 4 | Encaja con el estilo de iconos de macOS 26 | ✅ Legible en la barra real; es el único icono **en color**, que es justo lo que se busca en un indicador de estado |
| 5 | El estado cambia al liberar o llenar espacio | ⚠️ **Parcial**: la clasificación tiene tests unitarios, pero no se probó en vivo — el disco está al 99% y liberar 70 GB para cruzar el umbral no era razonable |
| 6 | No aparece en el Dock ni en Cmd+Tab | ✅ Verificado: `LSUIElement` más la política de accesorio |
| 7 | Al salir no queda ningún proceso vivo | ✅ Verificado **con un análisis a medias**: se lanzó, se confirmó que corría con grupo de procesos propio, se pulsó "Salir" y no sobrevivió nada |

Además, el menú vivo se contrastó contra el motor: mostraba
`Uso: 453.8 GB / 460.4 GB (99%)` y `Libre: 6.7 GB` frente a los 454.0 GB y
6.5 GB del motor Python — la diferencia es la escritura real del disco entre las
dos lecturas, muy dentro de la tolerancia del 1% del test de consistencia.

### Lo que queda fuera de esta rebanada

Vigilancia de carpetas, la ventana del panel, Linux y Windows: declarado fuera en
el spec. `analisis.rs` usa `process_group` y señales POSIX, así que hoy **solo
compila en Unix**; portarlo es parte del trabajo de Windows, no una deuda oculta.

### Deuda menor anotada

- `capabilities/default.json` declara `"windows": ["main"]`, un ámbito huérfano
  de la plantilla: no existe ninguna ventana con ese nombre. Inerte mientras no
  haya webview, pero **no debe copiarse a la rebanada C**, que sí abre ventana.
- `tauri-plugin-opener` se declaró antes de usarse; hoy sí lo usa
  "Abrir analizador completo".
- `desktop/README.md` sigue siendo la plantilla genérica.
