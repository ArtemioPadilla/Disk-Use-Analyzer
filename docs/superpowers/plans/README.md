# Plan de mejoras — punto de entrada

Este directorio contiene el plan de mejoras del proyecto, dividido en fases
ejecutables. Si retomas el trabajo (persona nueva, agente nuevo o workflow
automatizado), **lee este archivo primero**: te dice en qué estado está todo,
cuál es la siguiente acción y cómo ejecutarla.

## Estado de un vistazo

Última actualización: 1 de agosto de 2026. Tests: **151 passed en ~4 s**, con
CI en GitHub Actions.

| Fase | Alcance | Plan | Estado |
|---|---|---|---|
| 0 | Higiene del repo (destrackear `.pyc`, borrar ~12 MB de reportes) | En el roadmap, sin plan TDD | Pendiente |
| 1 | Bugs críticos del backend (6 fixes) | [Fase 1](2026-07-15-mejoras-fase1-bugs-criticos.md) | ✅ Completa, mergeada a `main` (PR #5) |
| 2 | Seguridad (auth, CORS, agents, fds del PTY) | [Fase 2](2026-07-15-mejoras-fase2-seguridad.md) | ✅ Completa, mergeada a `main` (PR #6) |
| 3 | Motor compartido (deduplicar CLI vs core) | [Fase 3](2026-07-30-mejoras-fase3-motor-compartido.md) | ✅ Completa, mergeada a `main` (PR #7) |
| 4 | Frontend (cleanup runner, sesiones, tipos, código muerto) | Solo esbozo en el roadmap | Pendiente |
| 5 | Tests del motor y CI | [Fase 5](2026-08-01-mejoras-fase5-tests-y-ci.md) | ✅ Completa, mergeada a `main` (PR #8) |

Documentos de referencia:

- **[Roadmap](2026-07-15-roadmap-mejoras.md)** — la evaluación a profundidad
  (19 hallazgos verificados con `archivo:línea`) y el alcance de las 6 fases.
  Empieza aquí si necesitas el *por qué* de cualquier fase.
- **[Registro de ejecución](2026-07-15-registro-ejecucion.md)** — qué se
  implementó realmente, con qué commits, qué desviaciones del plan se aprobaron
  y por qué, y qué hallazgos menores quedaron diferidos.

## Siguiente acción

Las fases 1, 2, 3 y 5 están mergeadas a `main`, con CI verificando cada push y
cada pull request. Quedan dos cosas:

1. **Fase 4 (frontend).** La única fase grande que falta, y necesita que se le
   escriba su plan detallado antes de ejecutarse: unificar los cinco flujos de
   limpieza (hoy solo uno comprueba de verdad que el comando terminó bien),
   arreglar la carga de sesiones históricas, reconectar el análisis al navegar
   entre páginas y quitar el código muerto restante. Su alcance está en el
   [roadmap](2026-07-15-roadmap-mejoras.md).
2. **Fase 0 (higiene).** Quince minutos, sin plan, pero necesita `sudo`: hay
   archivos en el repo y en `~/.disk-analyzer/` que quedaron propiedad de `root`
   por corridas anteriores con `sudo`, y eso ya provocó un fallo real (un 500 al
   no poder escribir el log de agents).

### Decisiones abiertas

- **¿Se protege la rama `main`?** El comando está preparado en el Task 6 del
  [plan de la Fase 5](2026-08-01-mejoras-fase5-tests-y-ci.md) pero **no se
  aplicó**: exigir los checks antes de mergear cambia cómo trabaja cualquiera en
  el repo. Sin esto, el CI informa pero no impide nada.
- **¿Debe `--clean-cache` borrar las cachés de Python?** Hoy no lo hace, igual
  que antes del refactor. El contexto completo está en el
  [registro de ejecución](2026-07-15-registro-ejecucion.md#la-decisión-sobre-las-cachés-de-python).
- **`clean_cache` borra directorios de forma permanente** para todas las
  categorías del safelist, pese a su propio comentario "Mover a Trash en macOS".
  Conviene decidir si se arregla el código o el comentario.

## Cómo ejecutar un plan

Los planes están escritos para el skill `superpowers:subagent-driven-development`
(un subagente por task, con revisión entre tasks). El flujo por task es:

1. Extrae el texto del task a un archivo con el script `task-brief` del skill.
2. Despacha un subagente implementador con ese brief más el contexto que el
   brief no puede conocer (interfaces de tasks anteriores, decisiones tomadas).
3. Genera el paquete de revisión con el script `review-package` del skill.
4. Despacha un subagente revisor con el brief, el reporte del implementador y
   el paquete. No marques el task como completo mientras queden hallazgos
   críticos o importantes.
5. Registra el resultado en el
   [registro de ejecución](2026-07-15-registro-ejecucion.md).

Los scripts viven en
`~/.claude/plugins/cache/claude-plugins-official/superpowers/<versión>/skills/subagent-driven-development/scripts/`.
Sus argumentos cambian entre versiones del skill (por ejemplo, la 6.2.0 le
agregó el archivo del plan como primer argumento a los dos), así que
ejecútalos sin argumentos para ver el uso actual en vez de copiar una firma de
aquí.

También puedes ejecutar los tasks a mano: cada uno trae sus tests y su código
completos, en pasos de 2 a 5 minutos. El skill no es un requisito.

> **Nota:** el skill mantiene un registro de avance local en
> `.superpowers/sdd/progress.md`, junto con los briefs, reportes y diffs de cada
> task. Ese directorio está en `.gitignore` (es scratch efímero y los diffs son
> grandes). La versión duradera de esa información es el registro de ejecución
> versionado. Si el scratch no existe, no perdiste nada: reconstruye el estado
> desde `git log` y el registro de ejecución.

## Verificación

Todos los planes usan el entorno virtual `venv-web`:

```bash
# Suite de tests (debe quedar en verde antes de cada commit)
venv-web/bin/python -m pytest tests/ -v

# Build del frontend
cd web && npm run build
```

La suite pasó de 18 tests (antes de la Fase 1) a 45. Los archivos
`tests/test_cleanup_api.py`, `tests/test_core_engine.py`,
`tests/test_sessions_persistence.py`, `tests/test_auth.py` y
`tests/conftest.py` son nuevos de este plan.

## Gotchas del estado actual

Cosas que sorprenden si no las sabes:

- **Ahora hay que abrir la web con el enlace que imprime el servidor.** Con la
  Fase 2, el arranque imprime `http://localhost:8000/?token=...`. Ese token se
  guarda en `sessionStorage` y se limpia de la URL, así que basta abrirlo una
  vez por sesión del navegador. Si abres `http://localhost:8000` a secas sin
  haber cargado antes el enlace con token, la interfaz da 401. Para saltarte
  todo eso en una red aislada: `disk_analyzer_web.py --no-auth`.
- **El token vive en `sessionStorage`, no en `localStorage`.** Se pierde al
  cerrar la pestaña, a propósito: hay que volver a abrir el enlace con token.
  Es el compromiso elegido para una herramienta local de un solo usuario.
- **Los agents simulan por defecto.** `POST /api/agents/{id}/run` no borra nada
  sin `?confirm=true`, y el planificador de fondo quedó en simulación
  permanente: solo registra en el log qué borraría. El botón "Run now" de la
  interfaz pide confirmación mostrando los comandos exactos antes de ejecutar
  de verdad.
- **El token debe viajar por variable de entorno, no por `app.state`.** El
  servidor corre con `reload=True`, así que uvicorn re-importa el módulo en un
  subproceso: cualquier cosa que definas solo en el bloque `__main__` no llega
  al worker que atiende las peticiones. Usa `DISK_ANALYZER_TOKEN` y
  `DISK_ANALYZER_NO_AUTH`.
- **Los tests corren con la autenticación desactivada.** `tests/conftest.py`
  tiene un fixture `autouse` que la apaga para todos los módulos menos
  `tests/test_auth.py`, que gestiona su propio entorno. Si escribes un test
  nuevo que golpea `/api/*`, ya está cubierto.
- **El middleware HTTP no protege los WebSockets.** Starlette salta los scopes
  de tipo `websocket` en el middleware HTTP. Por eso la autenticación de los WS
  es un task aparte (Task 2) y va con `Depends` o con un chequeo previo a
  `accept()`.
- **Los planes suponen que lees el código antes de aplicar un snippet.** Varios
  pasos traen notas del tipo "verifica el nombre real antes de reemplazar":
  están ahí porque el nombre exacto de una función o la forma de un JSON no se
  pudo confirmar al escribir el plan. Respétalas.

## Convenciones que aplican a estos planes

Estas reglas vienen de `CLAUDE.md` y de las restricciones globales de cada plan:

- Mensajes de cara al usuario en español; comentarios de código en inglés.
- Ninguna operación destructiva sin verificación de rutas protegidas
  (`is_protected_path`) y sin modo de simulación (`dry_run`).
- Desarrollo guiado por tests: el test falla primero, luego el arreglo.
- Un commit por task, con mensaje en español.
- No cambiar las formas del API que consume `web/src/lib/api.ts`, salvo para
  hacer campos opcionales.
