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

**Estado:** en curso en la rama `feat/fase2-seguridad`, creada desde `main`
(`6c633df`). Completado 1 de 6 tasks. Tests: 39 → 45.

| Task | Qué hace | Estado |
|---|---|---|
| 1 | Auth por token para `/api/*`, CORS restringido a los orígenes de desarrollo, flag `--no-auth` | ✅ `58debfa` |
| 2 | Validar el token en los dos WebSockets antes de `accept()` | Pendiente |
| 3 | Agents en modo simulación por defecto; `/run` exige `confirm=true` | Pendiente |
| 4 | El frontend adjunta el token en REST y WebSockets | Pendiente |
| 5 | El shell del PTY no hereda descriptores de archivo del servidor | Pendiente |
| 6 | Verificación integral y revisión final de la rama | Pendiente |

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

### Hallazgos menores diferidos

| Hallazgo | Nota |
|---|---|
| `/docs` y `/openapi.json` quedan sin autenticación | Fuera del alcance declarado (solo `/api/*`). Exponen el esquema, no datos |
| El test de rutas abiertas solo cubre `/`, no los montajes `/static` ni `/_astro` | Sin riesgo: están fuera del prefijo que revisa el middleware |
| Falta el salto de línea final en `disk_analyzer_web.py` | Cosmético |

## Fases 0 y 3 a 5

Sin ejecutar. El alcance, la secuencia recomendada y los criterios de
aceptación de cada una están en el
[roadmap](2026-07-15-roadmap-mejoras.md). Las fases 3, 4 y 5 necesitan que se
les escriba su plan detallado antes de ejecutarse, con el mismo formato que las
fases 1 y 2: un task por unidad verificable, con test y código completos.

Nota para la Fase 3 (motor compartido): el paso 1 de esa fase, escribir tests
de caracterización del comportamiento actual, no es opcional. La extracción
mueve lógica de cálculo de tamaños y categorización que hoy no tiene red de
seguridad, y las diferencias entre las dos implementaciones ya están
inventariadas en el roadmap.
