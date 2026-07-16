# Roadmap de Mejoras — Disk-Use-Analyzer

Evaluación a profundidad realizada el 2026-07-15 (3 revisiones paralelas: backend Python, frontend web, duplicación de motores). Este documento es el índice: resume los hallazgos verificados y define las fases. Cada fase con código se detalla en su propio plan ejecutable (formato writing-plans).

**Estado de planes:**

| Fase | Plan detallado | Estado |
|---|---|---|
| 0 — Higiene del repo | (comandos abajo, no requiere plan TDD) | pendiente |
| 1 — Bugs críticos backend | `2026-07-15-mejoras-fase1-bugs-criticos.md` | ✅ escrito |
| 2 — Seguridad | pendiente de escribir | pendiente |
| 3 — Motor compartido (dedup) | pendiente de escribir | pendiente |
| 4 — Frontend | pendiente de escribir | pendiente |
| 5 — Tests y CI | pendiente de escribir | pendiente |

---

## Resumen del assessment (hallazgos verificados con código citado)

### Críticos

1. **`/api/cleanup/preview|execute` rotos de punta a punta** (`disk_analyzer_web.py:162-165, 776-842`; `web/src/lib/api.ts:107-116`): el frontend no envía `categories` (requerido) → 422 siempre; `execute` reconstruye el preview sin `paths` → `ValidationError`; instancia `DiskAnalyzerCore()` sin `start_path` → `TypeError`; y el loop de borrado no tiene guard `is_protected_path` ni Papelera. → **Fase 1, Task 1.**
2. **El blocklist del terminal solo aplica al comando inicial** (`pty_manager.py:191-221` vs `disk_analyzer_web.py:1071-1081`): en una sesión interactiva cada keystroke va directo al PTY sin filtro; `rm -rf /` tecleado no pasa por `_check_blocked`. La "protección" documentada en CLAUDE.md es cosmética. → **Fase 2.**
3. **Sin auth + CORS `*` + bind `0.0.0.0`** (`disk_analyzer_web.py:40-46, 1267-1277`): cualquier web abierta en el navegador puede hacer `fetch()` a `DELETE /api/files/delete` o crear terminales (CSRF), y cualquier dispositivo de la LAN tiene acceso directo. → **Fase 2.**
4. **`agents_manager.py` ejecuta `rm -rf ~/Library/Caches/*` y `rm -rf /tmp/*` sin dry-run ni confirmación** (`agents_manager.py:23-32, 111-134`), disparable remotamente vía `POST /api/agents/{id}/toggle`. Contradice el principio "Safety First" de CLAUDE.md. → **Fase 2.**
5. **Cinco flujos de cleanup del frontend con señalización de éxito inconsistente**: solo `QuickActions` espera `terminal:exited` con código 0; `GuidedDeclutter`, `WhatIfSandbox` y `ReverseView` emiten `cleanup:completed` inmediatamente (comando fallido = ahorro contado); `DockerPanel` usa un `setTimeout` de 5 s; `CleanupWizard` nunca emite. Ahorros dobles/fantasma en `SavingsTracker`. → **Fase 4.**

### Altos

6. **`DiskAnalyzerCore.parse_docker_size` devuelve 0 para el output real de Docker** (`disk_analyzer_core.py:574`, exige 2 tokens con espacio; Docker emite `"1.5GB"`). GUI y web reportan Docker en 0. → **Fase 1, Task 2.**
7. **Etiquetas de caché desalineadas**: `categorize_cache` emite `'VS Code Cache'`/`'NPM Cache'` pero `generate_recommendations` filtra `'VS Code'`/`'Node.js/npm'` → esas recomendaciones tier-1 jamás disparan en web/GUI (`disk_analyzer_core.py:403-430` vs `:722-729`). → **Fase 1, Task 3.**
8. **fork sin higiene de fds** (`pty_manager.py:45-71`): cada shell hijo hereda los fds del servidor (otros PTY masters, socket de uvicorn). → **Fase 2.**
9. **`SessionList.loadSession` no carga la sesión elegida**: despacha `analysis:completed` y navega con `window.location.href` (MPA estática — el evento muere con la página); el dashboard muestra `/api/analysis/latest`. → **Fase 4.**
10. **Navegación pierde análisis/terminal en curso**: `AnalysisManager` y `FloatingTerminal` no se re-adjuntan a sesiones activas al montar (contradice el diseño "browse while it scans"). → **Fase 4.**

### Medios

11. `cleanup_idle()` del PTY nunca se llama — el idle timeout no existe en la práctica (**Fase 1, Task 4**).
12. Zombies en `PTYSession.kill()` — un solo `waitpid(WNOHANG)` (**Fase 1, Task 6**).
13. Sesiones restauradas como `"running"` tras restart quedan colgadas (**Fase 1, Task 5**).
14. `GuidedDeclutter` mete recomendaciones tier 3-4 de caché/docker en dos pasos (sin dedup contra `usedIds`) → doble conteo (**Fase 4**).
15. `CleanupWizard` persiste `running` en localStorage pero no `ptyCommands` → botones "Running..." atascados para siempre tras un reload (**Fase 4**).
16. Drift de tipos en `api.ts` (`default_min_size_mb`, `disk_used/disk_total` ausentes) → `any` casts dispersos y un error de tipos latente en `HeroScan` (**Fase 4**).
17. xterm CSS desde CDN de jsDelivr en runtime → terminal sin estilos offline (justo el caso LAN documentado) + `<link>` duplicados por ciclo abrir/cerrar (**Fase 4**).
18. `ResizeObserver` del terminal nunca se engancha en la primera apertura (race con el import dinámico) (**Fase 4**).
19. `TaskList` con colores pastel claros hardcodeados → ilegible en dark mode; `left: -var(--sidebar-width)` es CSS inválido (**Fase 4**).

### Duplicación (base de la Fase 3)

- La duplicación real es **bidireccional** (`DiskAnalyzer` 4,882 líneas vs `DiskAnalyzerCore` 777): la GUI no tiene motor propio, importa el core.
- **Constantes 100% idénticas** en valor (CACHE_DIRS, PROTECTED_*, IGNORE_PATTERNS, etc.) — extraíbles verbatim.
- **Métodos idénticos**: `format_size`, `get_file_age`, `is_cache_or_temp`, `should_ignore`, `is_protected_path`, `get_home_dir`, `get_temp_dirs`, `get_disk_usage`.
- **Divergencias a reconciliar**: `scan_directory` (scaffolding de progreso/cancel), `get_directory_size` (`du -sk` vs `rglob` — dan totales distintos), `get_all_drives` (`List[str]` vs `List[Dict]`), `find_cache_locations` (umbral 1MB vs 0), clasificador de caché (nombres y etiquetas distintas).
- **Única dependencia del monolito**: `disk_analyzer_web.py:890` importa `DiskAnalyzer` solo para `generate_html_report`.
- **Cero tests del motor** — la extracción necesita tests de caracterización primero.
- Frontend: `getCategory` duplicado byte a byte (`DiskBar.tsx:17-26` = `FileTable.tsx:88-97`); `TIER_META` triplicado con semánticas en desacuerdo; código muerto (`DiskDonut.tsx`, `useAnalysis.ts`, `useWebSocket.ts`, `formatPercent`).

---

## Fase 0 — Higiene del repo (15 min, sin plan TDD)

`.gitignore` ya cubre todo; el problema son archivos trackeados antes del ignore y basura local:

```bash
# 1. Destrackear artefactos (quedan en disco, salen de git)
git rm --cached __pycache__/disk_analyzer_core.cpython-310.pyc \
               __pycache__/disk_analyzer_web.cpython-310.pyc \
               .claude/settings.local.json
git commit -m "chore: destrackear .pyc y settings locales cubiertos por .gitignore"

# 2. Basura local (~12 MB, 20 archivos owned by root — requiere sudo)
sudo rm -f disk_report_*.html disk_report_*.json firebase-debug.log
```

Decisión del usuario: los `disk_report_*` root-owned se borran con sudo o se `chown` primero. No borrar `sessions_metadata.json` (estado vivo del servidor web).

## Fase 1 — Bugs críticos backend ✅ plan escrito

Ver `2026-07-15-mejoras-fase1-bugs-criticos.md`. 7 tasks TDD: cleanup endpoints, parse_docker_size, etiquetas de recomendaciones, idle reaper, sesiones interrumpidas, zombies, verificación integral. Hallazgos #1, #6, #7, #11, #12, #13.

## Fase 2 — Seguridad (plan detallado pendiente)

Alcance y dirección (hallazgos #2, #3, #4, #8):

1. **Token de sesión**: generar token aleatorio al arrancar, imprimirlo en la URL de inicio (`http://host:8000/?token=...`), middleware que exige el token (header `X-Auth-Token` o cookie) en toda ruta mutante (`POST/DELETE`) y en los WebSockets; el frontend lo guarda de la query a localStorage y lo adjunta en `api.ts`. Flag `--no-auth` para conservar el comportamiento actual explícitamente.
2. **CORS**: restringir `allow_origins` al origen propio (mismo host/puerto) en producción; mantener `localhost:3000` para `make web-dev`.
3. **Agents**: `run_agent(dry_run=True)` por defecto; reemplazar los `rm -rf` crudos por rutas verificadas con `is_protected_path` + envío a Papelera; el toggle NO dispara ejecución inmediata sin `confirm=true`; registrar en el log lo que se borraría vs borró.
4. **Terminal**: documentar honestamente que el blocklist es cosmético en modo interactivo; gate del feature detrás de `--enable-terminal` (off por defecto cuando hay `--no-auth` o bind no-loopback); `os.set_inheritable(False)`/`FD_CLOEXEC` en fds del servidor antes del fork, y cerrar fds ajenos en el hijo.
5. **Sesión "running" + restart** ya cubierto en Fase 1.

Criterio de aceptación: sin token, toda mutación devuelve 401; `curl` desde otro origen no puede borrar archivos; `agents` en dry-run por defecto; tests de middleware con TestClient.

## Fase 3 — Motor compartido (plan detallado pendiente; el más grande)

Objetivo: una sola fuente de verdad del motor de análisis. Secuencia:

1. **Tests de caracterización primero** sobre el comportamiento actual del core (fixture de árbol de archivos temporal): `scan_directory` (tamaños st_blocks, ignore patterns, profundidad), `is_protected_path` (tabla de casos), `classify/categorize_cache` (tabla path→etiqueta), `generate_recommendations`, `get_disk_usage` mockeando `df`.
2. **Extraer `analyzer/constants.py`** (constantes idénticas verbatim) e importarlas desde ambos módulos — cambio mecánico sin comportamiento.
3. **Extraer `analyzer/protection.py`** (`is_protected_path` como función libre) — ya la usa el web con una instancia dummy.
4. **Consolidar en `DiskAnalyzerCore`** como único motor: portar del monolito lo que falta (`find_duplicates`, `estimate_skipped_apfs_volumes`, `_categorize_path`, `get_app_usage`, historia/diff), parametrizar el progreso (callback opcional; el CLI pasa uno que imprime a TTY).
5. **Reconciliar divergencias** decididas: `get_directory_size` → versión `rglob` + `st_blocks` (consistente con el resto del motor); `find_cache_locations` → umbral 1MB; `get_all_drives` → `List[Dict]`; etiquetas de caché → un solo conjunto (enum/constantes) consumido por clasificador, recomendaciones, safelist de `clean_cache` y matching del endpoint de cleanup.
6. **`disk_analyzer.py` queda como CLI + reporting**: argparse, `print_report`, `generate_html_report`/Sankey (idealmente movidos a `analyzer/report_html.py`), delegando el análisis al core. El web deja de importar el monolito.

Riesgo principal: regresiones sutiles de tamaños/categorías → por eso el paso 1 es obligatorio antes de mover nada. Cada paso es commiteable de forma independiente.

## Fase 4 — Frontend (plan detallado pendiente)

Hallazgos #5, #9, #10, #14-19 más limpieza:

1. **Hook compartido `useCleanupRunner`** (patrón QuickActions): mapa `pty_id → {command, space}`, éxito solo con `terminal:exited` código 0, emisión única de `cleanup:completed`, registro compartido de comandos ya ejecutados (una sola clave de localStorage). Migrar los 6 componentes (CleanupWizard, QuickActions, GuidedDeclutter, WhatIfSandbox, ReverseView, DockerPanel — este último elimina el `setTimeout(5000)`).
2. **`lib/categories.ts` y `lib/tiers.ts`**: `getCategory` + `CATEGORY_COLORS` + `TIER_META` únicos; `ReverseView` deriva sus 3 buckets de la misma fuente.
3. **Carga de sesión histórica**: `SessionList` navega a `/?session=<id>`; el dashboard lee el query param y pide esa sesión específica en vez de `latest`.
4. **Re-attach al montar**: `AnalysisManager` consulta `/api/sessions` por una sesión `running` y reabre su WS; `FloatingTerminal`/`useTerminal` persisten `pty_id` activo (sessionStorage) y se reconectan.
5. **Terminal**: `import '@xterm/xterm/css/xterm.css'` bundleado (fuera el CDN), guard de `<link>` duplicado sobra al bundlear, flag `xtermReady` para el `ResizeObserver`.
6. **Fixes puntuales**: dedup de `reviewRecs` en GuidedDeclutter; no persistir `running` transitorio en CleanupWizard; tipos de `api.ts` (`default_min_size_mb`, `disk_used/disk_total`) y quitar los `any`; `TaskList` con variables de tema; `left: calc(-1 * var(--sidebar-width))`; `formatAge` en inglés (UI web es inglesa); borrar `DiskDonut.tsx`, `useAnalysis.ts`, `useWebSocket.ts`, `formatPercent`.
7. Verificación: `npm run build` + `astro check` (agregarlo como script) sin errores.

## Fase 5 — Tests y CI (plan detallado pendiente)

1. Los tests de caracterización de Fase 3 quedan como suite permanente del motor.
2. Tests de API restantes: export (json/csv/html), delete_file (traversal, protegidos), digest, latest.
3. GitHub Actions: job Python (`pytest`) + job web (`npm ci && npm run build && astro check`) en push/PR.
4. `make test` que corra ambos.

---

## Orden recomendado y dependencias

```
Fase 0 (15 min) → Fase 1 (bugs, ~1 día) → Fase 2 (seguridad, ~1-2 días)
                                        ↘ Fase 4 (frontend, ~2 días, independiente de 2 y 3)
Fase 3 (motor, ~2-3 días, después de 1 para heredar sus tests) → Fase 5 (CI, ~½ día)
```

Fase 4 puede correr en paralelo con 2/3 (no comparten archivos salvo `api.ts` ↔ token de Fase 2; coordinar ese punto).
