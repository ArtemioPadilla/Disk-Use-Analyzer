# Plan de mejoras — punto de entrada

Este directorio contiene el plan de mejoras del proyecto, dividido en fases
ejecutables. Si retomas el trabajo (persona nueva, agente nuevo o workflow
automatizado), **lee este archivo primero**: te dice en qué estado está todo,
cuál es la siguiente acción y cómo ejecutarla.

## Estado de un vistazo

Última actualización: 15 de julio de 2026. Tests: **45 passed**.

| Fase | Alcance | Plan | Estado |
|---|---|---|---|
| 0 | Higiene del repo (destrackear `.pyc`, borrar ~12 MB de reportes) | En el roadmap, sin plan TDD | Pendiente |
| 1 | Bugs críticos del backend (6 fixes) | [Fase 1](2026-07-15-mejoras-fase1-bugs-criticos.md) | ✅ Completa, mergeada a `main` (PR #5) |
| 2 | Seguridad (auth, CORS, agents, fds del PTY) | [Fase 2](2026-07-15-mejoras-fase2-seguridad.md) | 🔄 En curso: 1 de 6 tasks |
| 3 | Motor compartido (deduplicar CLI vs core) | Solo esbozo en el roadmap | Pendiente |
| 4 | Frontend (cleanup runner, sesiones, tipos, código muerto) | Solo esbozo en el roadmap | Pendiente |
| 5 | Tests del motor y CI | Solo esbozo en el roadmap | Pendiente |

Documentos de referencia:

- **[Roadmap](2026-07-15-roadmap-mejoras.md)** — la evaluación a profundidad
  (19 hallazgos verificados con `archivo:línea`) y el alcance de las 6 fases.
  Empieza aquí si necesitas el *por qué* de cualquier fase.
- **[Registro de ejecución](2026-07-15-registro-ejecucion.md)** — qué se
  implementó realmente, con qué commits, qué desviaciones del plan se aprobaron
  y por qué, y qué hallazgos menores quedaron diferidos.

## Siguiente acción

Ejecutar el **Task 2 de la Fase 2**: autenticación de los dos WebSockets
(validar `?token=` antes de `accept()`, cerrar con código 1008). El texto
completo del task está en el
[plan de la Fase 2](2026-07-15-mejoras-fase2-seguridad.md), sección "Task 2".

Trabaja en la rama `feat/fase2-seguridad`. Los tasks 3 a 6 de esa fase siguen
después, en orden.

## Cómo ejecutar un plan

Los planes están escritos para el skill `superpowers:subagent-driven-development`
(un subagente por task, con revisión entre tasks). El flujo por task es:

1. Extrae el texto del task a un archivo:
   `<skill>/scripts/task-brief docs/superpowers/plans/<plan>.md <N>`
2. Despacha un subagente implementador con ese brief más el contexto que el
   brief no puede conocer (interfaces de tasks anteriores, decisiones tomadas).
3. Genera el paquete de revisión:
   `<skill>/scripts/review-package <BASE> HEAD`
4. Despacha un subagente revisor con el brief, el reporte del implementador y
   el paquete. No marques el task como completo mientras queden hallazgos
   críticos o importantes.
5. Registra el resultado en el
   [registro de ejecución](2026-07-15-registro-ejecucion.md).

`<skill>` es
`~/.claude/plugins/cache/claude-plugins-official/superpowers/<versión>/skills/subagent-driven-development`.

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

- **La UI web devuelve 401 en la rama `feat/fase2-seguridad`.** El Task 1 activó
  la autenticación por token en el backend, pero el frontend todavía no lo
  adjunta: eso es el Task 4. Mientras tanto, arranca con
  `venv-web/bin/python disk_analyzer_web.py --no-auth` para probar la interfaz,
  o llama al API con el header `X-Auth-Token`. Es un estado intermedio
  esperado de la fase, no un bug.
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
