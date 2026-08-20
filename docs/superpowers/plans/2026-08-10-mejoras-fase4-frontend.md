# Plan de Mejoras — Fase 4: Frontend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la interfaz web diga la verdad: que el espacio liberado que muestra corresponda a comandos que de verdad terminaron bien, que cargar una sesión histórica cargue esa sesión, y que navegar entre páginas no pierda el análisis en curso.

**Architecture:** Primero se monta la infraestructura mínima de tests de JavaScript (hoy no hay ninguna) y con ella se construye un único `useCleanupRunner` que centraliza el patrón correcto; luego se migran a él los seis flujos de limpieza que hoy hacen seis cosas distintas. Después, las correcciones de navegación y estado, y por último la limpieza de duplicación y código muerto.

**Tech Stack:** Astro 4, React 18, TypeScript, Vitest + Testing Library (nuevo), GitHub Actions (ya existente).

## Global Constraints

- **El texto de la interfaz está en inglés.** Es la convención de este frontend (verificado: no hay cadenas en español en `web/src`), aunque el CLI y la GUI sean en español. Los comentarios de código, en inglés.
- Verificación obligatoria antes de cada commit: `cd web && npm run check && npm run build`, y desde la Task 1 en adelante también `npm test`.
- El backend no se toca. Si algo parece exigir un cambio de backend, es un hallazgo que se reporta, no se implementa.
- La suite de Python debe seguir en verde: `venv-web/bin/python -m pytest tests/ -q` → 151 passed.
- Un commit por task.
- **Ningún cambio de comportamiento que el usuario note debe entrar sin estar en este plan.** Esta fase corrige números que hoy se muestran mal; cambiar además el diseño visual mezclaría dos cosas distintas.

## Contexto: qué está roto y por qué importa

Verificado sobre `main` (commit `01e5f9e`).

### Seis flujos de limpieza, seis comportamientos distintos

La app ejecuta la limpieza abriendo una sesión de terminal (PTY) con el comando y
observando su salida. El patrón correcto es: guardar `pty_id → {command, space}`,
esperar el evento `terminal:exited`, y acreditar el ahorro **solo si el código de
salida es 0**. Estado real:

| Componente | ¿Escucha `terminal:exited`? | ¿Emite `cleanup:completed`? | Consecuencia |
|---|---|---|---|
| `QuickActions` | Sí | Sí, con código 0 | **Correcto. Es la referencia.** |
| `CleanupWizard` | Sí, pero solo para limpiar su estado | No | Limpiar desde el asistente principal nunca suma al ahorro |
| `GuidedDeclutter` | No | Sí, inmediatamente | Acredita el espacio aunque el comando falle |
| `WhatIfSandbox` | No | Sí, inmediatamente | Igual |
| `ReverseView` | No | Sí, inmediatamente | Igual |
| `DockerPanel` | No | Sí, tras un `setTimeout` de 5 s | Marca "✓ Pruned" aunque el prune siga corriendo o haya fallado |

El resultado es que el contador de ahorro acumulado (`SavingsTracker`), las
tarjetas de estadísticas y la barra de disco muestran cifras que no corresponden
a lo que pasó. Y como no hay deduplicación entre componentes, la misma
recomendación puede acreditarse varias veces desde sitios distintos.

### Navegación y estado

- **`SessionList` no carga la sesión que eliges.** Hace
  `window.dispatchEvent(...)` e inmediatamente `window.location.href = '/'`
  (`SessionList.tsx:24-25`). Esto es un sitio estático multipágina: la navegación
  destruye el árbol de React antes de que nadie pueda escuchar el evento. El
  dashboard acaba pidiendo `/api/analysis/latest`, así que **muestra el análisis
  más reciente, no el que pediste**, sin error visible.
- **Navegar entre páginas pierde el análisis en curso.** `AnalysisManager`
  arranca con `sessionId` en `null` en cada montaje
  (`AnalysisManager.tsx:12`) y nunca pregunta si hay un análisis corriendo. Como
  cada navegación remonta el árbol, el WebSocket de la página anterior se cierra
  y el nuevo nunca se suscribe. Lo mismo con la terminal: no se persiste el
  `pty_id`, así que se pierde la salida en vivo.

### Duplicación y restos

- `getCategory` está duplicada palabra por palabra en `DiskBar.tsx` y
  `FileTable.tsx`.
- La metadata de niveles de riesgo está repartida entre `CleanupWizard.tsx` y
  `WhatIfSandbox.tsx`, con etiquetas que no coinciden ("Deep Clean" frente a
  "Deep"), y `ReverseView.tsx` deriva sus propios tres grupos por su cuenta.
- `useAnalysis.ts` y `useWebSocket.ts` son una implementación paralela del
  WebSocket de análisis que **no monta nadie** (lo real es `AnalysisManager`).
  `formatPercent` en `lib/format.ts` tampoco lo usa nadie.
- `FloatingTerminal.tsx:55` carga el CSS de xterm desde un CDN en tiempo de
  ejecución, así que la terminal se ve rota sin internet — justo el caso de uso
  de LAN aislada que documenta el proyecto. Además reinyecta el `<link>` en cada
  apertura.
- `global.css:72` tiene `left: -var(--sidebar-width)`, que **no es CSS válido**:
  el navegador descarta la declaración y el menú lateral móvil no arranca fuera
  de pantalla.
- `format.ts` devuelve `'Hoy'`, `'sem'` — cadenas en español dentro de una
  interfaz que por lo demás está toda en inglés. (Es el archivo que da la edad de
  los archivos en la tabla.)

### Lo que ya no hace falta arreglar

Fases anteriores se llevaron por delante varios hallazgos del roadmap original:
`DiskDonut.tsx` ya está borrado, los tipos de `SystemInfo`/`AnalysisSession`
(incluido `'interrupted'`) ya están corregidos, y el bug de contrato de
`getSessions()` ya está resuelto. No volver a planificarlos.

---

### Task 1: Infraestructura de tests y el `useCleanupRunner`

Esta fase corrige lógica que produce números equivocados. Arreglarla "a ojo",
que es como se introdujeron los bugs, sería repetir el error: hace falta poder
probarla. El proyecto no tiene ninguna infraestructura de test de JavaScript, así
que este task la monta y la estrena con la pieza central.

**Files:**
- Create: `web/vitest.config.ts`, `web/src/hooks/useCleanupRunner.ts`, `web/src/hooks/useCleanupRunner.test.ts`
- Modify: `web/package.json` (dependencias y script `test`)

**Interfaces:**
- Consumes: `api.createTerminal(command)` de `lib/api.ts`; `emit`/`on` de `lib/events.ts`
- Produces:

```typescript
export interface CleanupJob {
  command: string;
  space: number;
  label?: string;
}

export interface CleanupRunner {
  /** Spawn the command in a PTY and track it to completion. */
  run: (job: CleanupJob) => Promise<void>;
  /** Commands currently running (by command string). */
  running: Set<string>;
  /** Commands that already completed successfully, ever (persisted). */
  completed: Set<string>;
  /** Last error, or null. */
  error: string | null;
}

export function useCleanupRunner(): CleanupRunner;
```

Reglas que el hook implementa y que los tests fijan:
1. `run()` abre el PTY, registra `pty_id → job` y emite `terminal:open`.
2. `cleanup:completed` se emite **solo** al recibir `terminal:exited` con
   `code === 0`, y **una sola vez** por ejecución.
3. Un `code !== 0` no acredita nada y deja `error` con un mensaje.
4. Un comando ya presente en `completed` no se vuelve a ejecutar (evita el doble
   conteo entre componentes).
5. `completed` se persiste en **una sola** clave de `localStorage`,
   `disk-analyzer-cleaned`, compartida por todos los componentes.

- [ ] **Step 1: Instalar Vitest y añadir el script**

```bash
cd web && npm install --save-dev vitest @testing-library/react @testing-library/jest-dom jsdom
```

En `web/package.json`, añadir a `scripts`:

```json
    "test": "vitest run"
```

Crear `web/vitest.config.ts`:

```typescript
/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    // Only our own sources — never the Astro build output.
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
```

Nota: `@vitejs/plugin-react` puede no estar instalado (el proyecto usa
`@astrojs/react`, que es distinto). Si `npm run test` falla por eso, instalarlo
como devDependency. Verificar también que `tsconfig.json` sigue excluyendo
`dist` — la Fase 5 lo dejó así porque `astro check` se desborda recorriendo el
build, y añadir tests no debe romper eso.

- [ ] **Step 2: Escribir los tests del hook antes que el hook**

Crear `web/src/hooks/useCleanupRunner.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useCleanupRunner } from './useCleanupRunner';
import { emit } from '../lib/events';
import { api } from '../lib/api';

vi.mock('../lib/api', () => ({
  api: { createTerminal: vi.fn() },
}));

const mockedCreate = vi.mocked(api.createTerminal);

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  mockedCreate.mockResolvedValue({ pty_id: 'pty-1' } as any);
});

describe('useCleanupRunner', () => {
  it('credits the saving only after the command exits with code 0', async () => {
    const onCompleted = vi.fn();
    window.addEventListener('cleanup:completed', onCompleted);

    const { result } = renderHook(() => useCleanupRunner());
    await act(async () => {
      await result.current.run({ command: 'rm -rf /tmp/x', space: 1024 });
    });

    // Nothing credited while the command is still running
    expect(onCompleted).not.toHaveBeenCalled();

    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });

    await waitFor(() => expect(onCompleted).toHaveBeenCalledTimes(1));
    const detail = (onCompleted.mock.calls[0][0] as CustomEvent).detail;
    expect(detail.space).toBe(1024);

    window.removeEventListener('cleanup:completed', onCompleted);
  });

  it('credits nothing when the command fails', async () => {
    const onCompleted = vi.fn();
    window.addEventListener('cleanup:completed', onCompleted);

    const { result } = renderHook(() => useCleanupRunner());
    await act(async () => {
      await result.current.run({ command: 'false', space: 999 });
    });
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 1 }); });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(onCompleted).not.toHaveBeenCalled();

    window.removeEventListener('cleanup:completed', onCompleted);
  });

  it('emits cleanup:completed exactly once per run', async () => {
    const onCompleted = vi.fn();
    window.addEventListener('cleanup:completed', onCompleted);

    const { result } = renderHook(() => useCleanupRunner());
    await act(async () => {
      await result.current.run({ command: 'echo hi', space: 10 });
    });
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    // A duplicate exit event for the same pty must not double-credit
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });

    await waitFor(() => expect(onCompleted).toHaveBeenCalledTimes(1));
    window.removeEventListener('cleanup:completed', onCompleted);
  });

  it('does not re-run a command already completed', async () => {
    const { result } = renderHook(() => useCleanupRunner());
    await act(async () => {
      await result.current.run({ command: 'brew cleanup', space: 5 });
    });
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() => expect(result.current.completed.has('brew cleanup')).toBe(true));

    mockedCreate.mockClear();
    await act(async () => {
      await result.current.run({ command: 'brew cleanup', space: 5 });
    });
    expect(mockedCreate).not.toHaveBeenCalled();
  });

  it('shares the completed set across instances via localStorage', async () => {
    const first = renderHook(() => useCleanupRunner());
    await act(async () => {
      await first.result.current.run({ command: 'npm cache clean', space: 7 });
    });
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() =>
      expect(first.result.current.completed.has('npm cache clean')).toBe(true));

    // A second component mounting later must see it as already done
    const second = renderHook(() => useCleanupRunner());
    expect(second.result.current.completed.has('npm cache clean')).toBe(true);
  });

  it('surfaces an error when the terminal cannot be created', async () => {
    mockedCreate.mockRejectedValue(new Error('429 too many sessions'));
    const { result } = renderHook(() => useCleanupRunner());
    await act(async () => {
      await result.current.run({ command: 'whatever', space: 1 });
    });
    await waitFor(() => expect(result.current.error).toContain('429'));
  });
});
```

Nota: leer `lib/events.ts` y `lib/api.ts` antes de escribir, y ajustar los
nombres de import y la forma que devuelve `createTerminal` a lo real. Si el
evento `terminal:exited` lleva otras claves que `pty_id`/`code`, usar las reales.

- [ ] **Step 3: Correr los tests y verificar que fallan**

Run: `cd web && npm test`
Expected: FAIL — `useCleanupRunner` no existe todavía.

- [ ] **Step 4: Implementar el hook**

Crear `web/src/hooks/useCleanupRunner.ts`. Debe cumplir las cinco reglas de
arriba. Base de la implementación (el patrón correcto está hoy en
`QuickActions.tsx`, léelo primero):

```typescript
import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { emit, on } from '../lib/events';

const STORAGE_KEY = 'disk-analyzer-cleaned';

export interface CleanupJob {
  command: string;
  space: number;
  label?: string;
}

function loadCompleted(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

export function useCleanupRunner() {
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [completed, setCompleted] = useState<Set<string>>(loadCompleted);
  const [error, setError] = useState<string | null>(null);
  // pty_id -> job. A ref, not state: the exit listener must see the latest map
  // without re-subscribing on every run.
  const jobs = useRef<Record<string, CleanupJob>>({});

  useEffect(() => {
    return on('terminal:exited', (data: any) => {
      const job = jobs.current[data.pty_id];
      if (!job) return;
      // Delete first: a duplicate exit event for the same pty must not
      // credit the saving twice.
      delete jobs.current[data.pty_id];
      setRunning(prev => { const next = new Set(prev); next.delete(job.command); return next; });

      if (data.code === 0) {
        setCompleted(prev => {
          const next = new Set(prev).add(job.command);
          try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...next])); } catch { /* storage full or disabled */ }
          return next;
        });
        emit('cleanup:completed', { command: job.command, space: job.space });
      } else {
        setError(`${job.label ?? job.command} exited with code ${data.code}`);
      }
    });
  }, []);

  const run = async (job: CleanupJob) => {
    if (completed.has(job.command) || running.has(job.command)) return;
    setError(null);
    setRunning(prev => new Set(prev).add(job.command));
    try {
      const { pty_id } = await api.createTerminal(job.command);
      jobs.current[pty_id] = job;
      emit('terminal:open', { pty_id, command: job.command });
    } catch (e: any) {
      setRunning(prev => { const next = new Set(prev); next.delete(job.command); return next; });
      setError(e?.message ?? 'Could not start the cleanup command');
    }
  };

  return { run, running, completed, error };
}
```

- [ ] **Step 5: Verificar verde y commitear**

```bash
cd web && npm test && npm run check && npm run build
```
Expected: los 6 tests en verde, tipos limpios, build correcto.

```bash
git add web/package.json web/package-lock.json web/vitest.config.ts web/src/hooks/useCleanupRunner.ts web/src/hooks/useCleanupRunner.test.ts
git commit -m "feat(web): hook único de limpieza que solo acredita el ahorro si el comando termina bien"
```

---

### Task 2: Migrar los seis flujos de limpieza al hook

Con el hook probado, se sustituyen las seis implementaciones distintas.

**Files:**
- Modify: `web/src/components/QuickActions.tsx`, `CleanupWizard.tsx`, `GuidedDeclutter.tsx`, `WhatIfSandbox.tsx`, `ReverseView.tsx`, `DockerPanel.tsx`

**Interfaces:**
- Consumes: `useCleanupRunner()` de la Task 1, con `run(job)`, `running`, `completed`, `error`

- [ ] **Step 1: Migrar `QuickActions` primero**

Es el que ya hace lo correcto, así que migrarlo es la comprobación de que el
hook cubre el caso bueno sin perder comportamiento. Sustituir su manejo propio de
`ptyCommands`/`terminal:exited` por el hook, conservando su interfaz visual.

Verificar: `npm run check && npm run build`.

- [ ] **Step 2: Migrar `CleanupWizard`**

Hoy escucha `terminal:exited` solo para limpiar su estado y **nunca emite**
`cleanup:completed`, así que limpiar desde aquí no suma al ahorro. Al pasar al
hook, empieza a sumar: eso es el arreglo, no un efecto colateral.

Quitar su clave propia `disk-analyzer-wizard-running` de `localStorage`: el
estado "en ejecución" es transitorio y persistirlo es lo que deja botones
atascados en "Running..." para siempre tras recargar. El hook ya expone
`running` en memoria y `completed` persistido.

- [ ] **Step 3: Migrar `GuidedDeclutter`, `WhatIfSandbox` y `ReverseView`**

Los tres emiten `cleanup:completed` inmediatamente después de lanzar los
comandos, sin esperar. Sustituir por llamadas a `run()` por cada comando y dejar
que el hook acredite. Donde hoy emiten un único evento con el total agregado
(por ejemplo `space: totalChecked`), pasar a un `run()` por comando con su
espacio: así lo que se acredita corresponde a lo que de verdad terminó bien.

En `GuidedDeclutter` hay además un doble conteo propio: las recomendaciones de
nivel 3-4 de caché o Docker entran a la vez en su paso correspondiente y en el
paso "Review", porque `reviewRecs` no se filtra contra el conjunto `usedIds` que
sí usan los demás pasos. Filtrarlo.

- [ ] **Step 4: Migrar `DockerPanel`**

Sustituir el `setTimeout(..., 5000)` que hoy hace de confirmación
(`DockerPanel.tsx:38`) por el hook. Un `docker system prune` puede tardar mucho
más de cinco segundos o fallar, y hoy en ambos casos se marca "✓ Pruned" y se
acredita el espacio.

- [ ] **Step 5: Verificar que no quedan emisiones sueltas**

```bash
cd web && grep -rn "emit('cleanup:completed'" src/
```
Expected: **solo** `src/hooks/useCleanupRunner.ts`. Cualquier otro sitio es una
migración incompleta.

```bash
cd web && grep -rn "disk-analyzer-wizard-running" src/
```
Expected: sin resultados.

- [ ] **Step 6: Verificar y commitear**

```bash
cd web && npm test && npm run check && npm run build
```

```bash
git add web/src/components
git commit -m "fix(web): los seis flujos de limpieza usan el mismo runner y solo acreditan lo que terminó bien"
```

---

### Task 3: Una sola fuente para categorías y niveles de riesgo

**Files:**
- Create: `web/src/lib/categories.ts`, `web/src/lib/tiers.ts`
- Modify: `web/src/components/DiskBar.tsx`, `FileTable.tsx`, `CleanupWizard.tsx`, `WhatIfSandbox.tsx`, `ReverseView.tsx`

**Interfaces:**
- Produces:
  - `categories.ts`: `getCategory(path: string): string` y `CATEGORY_COLORS: Record<string, string>`
  - `tiers.ts`: `TIER_META: Record<number, { label: string; color: string }>` y `getTierBucket(tier: number): 'safe' | 'review' | 'careful'`

- [ ] **Step 1: Extraer `getCategory`**

Está duplicada palabra por palabra en `DiskBar.tsx` y `FileTable.tsx`. Moverla
a `web/src/lib/categories.ts` **verbatim**, junto con `CATEGORY_COLORS` (hoy
solo en `DiskBar.tsx`), e importarla desde ambos. No cambiar la lógica de
clasificación: es un movimiento.

- [ ] **Step 2: Unificar la metadata de niveles**

`CleanupWizard.tsx` y `WhatIfSandbox.tsx` definen cada uno sus colores y
etiquetas, y no coinciden ("Deep Clean" frente a "Deep"). `ReverseView.tsx`
deriva por su cuenta tres grupos (`tier<=1` seguro, `tier===2` revisar,
`tier>=3` cuidado), fundiendo los niveles 3 y 4 que los otros distinguen.

Crear `web/src/lib/tiers.ts` con la metadata de los cuatro niveles como única
fuente, y `getTierBucket` para los tres grupos de `ReverseView`, derivados de
ahí en vez de recodificados. Elegir una etiqueta por nivel y usarla en todas
partes; anotar en el reporte cuál se eligió donde había discrepancia.

- [ ] **Step 3: Verificar y commitear**

```bash
cd web && npm test && npm run check && npm run build
grep -rn "function getCategory" src/   # debe aparecer solo en lib/categories.ts
```

```bash
git add web/src/lib/categories.ts web/src/lib/tiers.ts web/src/components
git commit -m "refactor(web): una sola definición de categorías y de niveles de riesgo"
```

---

### Task 4: Cargar la sesión que se pide y no perder el análisis al navegar

**Files:**
- Modify: `web/src/components/SessionList.tsx`, `web/src/components/HeroScan.tsx`, `web/src/components/AnalysisManager.tsx`, `web/src/hooks/useTerminal.ts`, `web/src/components/FloatingTerminal.tsx`

**Interfaces:**
- Consumes: `api.getResults(id)`, `api.getSessions()` (devuelve `{ sessions: AnalysisSession[] }`, corregido en la Fase 5), `api.listTerminals()`
- Produces: el dashboard acepta `?session=<id>`; `AnalysisManager` se reengancha a un análisis en curso al montar; `FloatingTerminal` se reengancha a su PTY

- [ ] **Step 1: Arreglar la carga de sesiones históricas**

`SessionList.tsx:24-25` despacha un evento y navega en la misma vuelta; el
evento muere con la página. Cambiar a navegar con el id en la URL:

```typescript
const loadSession = (id: string) => {
  window.location.href = `/?session=${encodeURIComponent(id)}`;
};
```

Y en `HeroScan.tsx` (que hoy pide `/api/analysis/latest` al montar), leer primero
el parámetro y pedir esa sesión concreta:

```typescript
const params = new URLSearchParams(window.location.search);
const requested = params.get('session');
const results = requested
  ? await api.getResults(requested)
  : await fetch('/api/analysis/latest', { headers: authHeaders() }).then(r => r.json());
```

Nota: leer `HeroScan.tsx` antes de editar — puede que su llamada actual sea un
`fetch` directo con `authHeaders()` en vez de pasar por `api`. Mantener el estilo
del archivo, y que el caso sin parámetro siga funcionando exactamente igual.

- [ ] **Step 2: Reenganchar el análisis en curso**

En `AnalysisManager.tsx`, al montar, preguntar si hay un análisis corriendo y
reabrir su WebSocket:

```typescript
useEffect(() => {
  // A full page navigation remounts this island with sessionId = null, so an
  // analysis started on another page would lose its progress stream.
  (async () => {
    try {
      const { sessions } = await api.getSessions();
      const active = sessions.find(s => s.status === 'running');
      if (active) setSessionId(active.id);
    } catch { /* no active session, nothing to reattach */ }
  })();
}, []);
```

Verificar que el efecto ya existente que abre el WebSocket reacciona a
`sessionId` y por tanto se conecta solo.

- [ ] **Step 3: Reenganchar la terminal**

`useTerminal.ts` no persiste el `pty_id`, así que al navegar se pierde la salida
en vivo. Guardarlo en `sessionStorage` al abrir, borrarlo al cerrar o al recibir
`terminal:exited`, y al montar reconectar si sigue vivo. Comprobar la vida real
contra el backend con `api.listTerminals()` en vez de fiarse de lo guardado: un
`pty_id` de un servidor ya reiniciado no existe.

- [ ] **Step 4: Verificar y commitear**

Estos cambios son de integración y no se pueden probar bien con Vitest sin
montar un servidor falso, así que la verificación es de tipos, build y una
comprobación manual descrita en el reporte. Ser explícito sobre qué **no** se
pudo verificar automáticamente.

```bash
cd web && npm test && npm run check && npm run build
```

```bash
git add web/src
git commit -m "fix(web): cargar la sesión pedida y reenganchar análisis y terminal al navegar"
```

---

### Task 5: Terminal sin CDN, CSS válido y limpieza de restos

Correcciones acotadas, cada una con un fallo concreto detrás.

**Files:**
- Modify: `web/src/components/FloatingTerminal.tsx`, `web/src/layouts/global.css`, `web/src/components/TaskList.tsx`, `web/src/lib/format.ts`
- Delete: `web/src/hooks/useAnalysis.ts`, `web/src/hooks/useWebSocket.ts`

- [ ] **Step 1: Empaquetar el CSS de xterm**

`FloatingTerminal.tsx:55` inyecta un `<link>` a jsDelivr en cada apertura. Sin
internet la terminal se ve rota — el caso de LAN aislada que el proyecto
documenta — y abrir y cerrar acumula etiquetas en el `<head>`.

Sustituir por el import empaquetado, junto al import dinámico de xterm que ya
existe en ese archivo:

```typescript
import '@xterm/xterm/css/xterm.css';
```

`@xterm/xterm` ya es dependencia, así que no hace falta instalar nada. Eliminar
todo el bloque que crea e inyecta el `<link>`.

- [ ] **Step 2: Arreglar el `ResizeObserver` que nunca se engancha**

En el mismo archivo, el efecto que observa el tamaño sale por `return` temprano
porque `fitAddonRef.current` todavía es `null`: se rellena dentro del `.then()`
del import dinámico, que resuelve después. Y como sus dependencias son
`[visible, minimized]`, no se vuelve a ejecutar. Añadir un estado
`xtermReady` que se ponga a `true` dentro del `.then()` e incluirlo en las
dependencias del efecto.

- [ ] **Step 3: Arreglar el CSS inválido del menú lateral**

`global.css:72`: `left: -var(--sidebar-width)` no es CSS válido — no se puede
aplicar un menos unario a `var()`. El navegador descarta la declaración, así que
en móvil el menú no arranca fuera de pantalla. Cambiar a:

```css
    left: calc(-1 * var(--sidebar-width));
```

- [ ] **Step 4: Arreglar los colores fijos de `TaskList`**

`TaskList.tsx` usa fondos pastel claros fijos (`#eff6ff`, `#f0fdf4`, `#fef2f2`)
mientras el texto hereda `--text`, que en modo oscuro es casi blanco: texto
blanco sobre fondo casi blanco. Sustituir por colores derivados de las variables
del tema, como hace `ReverseView`.

- [ ] **Step 5: Poner `formatAge` en inglés y borrar lo muerto**

`lib/format.ts` devuelve `'Hoy'`, `'sem'`, `'m'`, `'a'` dentro de una interfaz
que está toda en inglés, bajo una columna que se llama "Age". Cambiar a
`'Today'`, `'w'`, `'mo'`, `'y'`. Borrar también `formatPercent`, que no usa
nadie.

Borrar `web/src/hooks/useAnalysis.ts` y `web/src/hooks/useWebSocket.ts`: son una
implementación paralela del WebSocket de análisis que no monta ningún
componente (lo real es `AnalysisManager`). Confirmar antes de borrar:

```bash
cd web && grep -rn "useAnalysis\|useWebSocket\|formatPercent" src/ --include=*.tsx --include=*.astro
```
Expected: sin resultados fuera de los propios archivos que se van a borrar.

- [ ] **Step 6: Verificar y commitear**

```bash
cd web && npm test && npm run check && npm run build
grep -rn "jsdelivr" src/    # sin resultados
grep -rn "left: -var" src/  # sin resultados
```

```bash
git add web/src
git commit -m "fix(web): xterm sin CDN, CSS del menú válido, colores de TaskList con tema y borrar código muerto"
```

---

### Task 6: Verificación integral y CI

**Files:**
- Modify: `.github/workflows/ci.yml`, `Makefile`

- [ ] **Step 1: Añadir los tests de frontend al CI**

El workflow de la Fase 5 corre `npm run check` y `npm run build` en el job
`frontend`. Añadir el paso de tests, antes del build:

```yaml
      - name: Test
        run: npm test
```

Y en el target `test` del `Makefile`, añadir `npm test` junto al `npm run check`
que ya está, para que `make test` y el CI sigan corriendo lo mismo.

- [ ] **Step 2: Verificación completa en local**

```bash
cd web && npm ci && npm test && npm run check && npm run build
venv-web/bin/python -m pytest tests/ -q
make test
```
Expected: todo en verde.

- [ ] **Step 3: Comprobación manual de lo que los tests no cubren**

Los tres arreglos de integración (carga de sesión, reenganche del análisis,
reenganche de la terminal) y los visuales (modo oscuro, menú móvil) necesitan
ojos. Arrancar el servidor y comprobar, anotando el resultado de cada punto:

```bash
venv-web/bin/python disk_analyzer_web.py
```

1. Abrir el enlace con token que imprime el arranque.
2. Lanzar un análisis y, mientras corre, navegar a otra página: la barra de
   progreso debe seguir viva.
3. Ir a Historial, elegir una sesión **que no sea la más reciente** y cargarla:
   el dashboard debe mostrar **esa**, no la última.
4. Abrir la terminal, lanzar una limpieza y comprobar que el ahorro solo se suma
   cuando el comando termina; probar también un comando que falle (`false`) y
   comprobar que **no** suma nada.
5. Cambiar a modo oscuro y mirar `TaskList`: el texto debe leerse.
6. Estrechar la ventana por debajo de 768 px: el menú lateral debe empezar fuera
   de pantalla.
7. Desconectar la red y abrir la terminal: debe verse con estilos.

- [ ] **Step 4: Actualizar la documentación**

En `docs/superpowers/plans/2026-07-15-registro-ejecucion.md`, añadir la sección
de la Fase 4 con la tabla de tasks y sus commits, y lo que se encontró.

En `docs/superpowers/plans/README.md`, actualizar estado, número de tests y
siguiente acción.

En `CLAUDE.md`, mencionar que el frontend ahora tiene tests (`npm test` en
`web/`) y que la limpieza pasa por `useCleanupRunner`.

- [ ] **Step 5: Commit final**

```bash
git add .github/workflows/ci.yml Makefile docs/ CLAUDE.md
git commit -m "ci: correr los tests de frontend, y cerrar el registro de la Fase 4"
```

---

## Fuera del alcance de esta fase

- **Rediseño visual.** Esta fase corrige números que se muestran mal y estados
  que se pierden; tocar además el diseño mezclaría dos cosas que conviene poder
  revisar por separado.
- **Cobertura de tests del resto del frontend.** La Task 1 monta la
  infraestructura y prueba la pieza con lógica de verdad. Extenderla al resto de
  componentes es un trabajo posterior que ahora ya es barato.
- **`cleanup/execute` con `dry_run=true` devuelve la forma de `preview`.**
  Registrado desde la Fase 1. Es un cambio de backend, y esta fase no toca
  backend.

## Self-Review (ejecutado al escribir el plan)

1. **Cobertura:** los hallazgos vivos del roadmap para el frontend tienen task —
   los seis flujos de limpieza (Tasks 1 y 2), duplicación de categorías y niveles
   (Task 3), sesiones y reenganche (Task 4), terminal, CSS, tema, código muerto y
   `formatAge` (Task 5). Los que fases anteriores ya resolvieron (`DiskDonut`,
   tipos de `SystemInfo`/`AnalysisSession`, contrato de `getSessions`) están
   listados como "ya no hace falta" para que nadie los replanifique.
2. **Placeholders:** los "leer antes de editar" marcan puntos donde el nombre o
   la forma real debe confirmarse en el código; el código de intención está
   completo en cada paso, incluido el hook entero y sus seis tests.
3. **Consistencia:** `useCleanupRunner()` devuelve `{run, running, completed,
   error}` en la Task 1 y así lo consumen los seis componentes de la Task 2;
   `getCategory`/`CATEGORY_COLORS` y `TIER_META`/`getTierBucket` se definen en la
   Task 3 y se consumen ahí mismo; la clave `disk-analyzer-cleaned` es la única
   que persiste comandos completados, y la Task 2 elimina la competidora
   `disk-analyzer-wizard-running`.
4. **Riesgo principal:** es la primera fase que toca comportamiento visible sin
   poder probarlo del todo automáticamente. Por eso la Task 1 monta Vitest antes
   de tocar nada, y la Task 6 lleva una lista de comprobación manual explícita en
   vez de dar por bueno lo que no se puede verificar.
