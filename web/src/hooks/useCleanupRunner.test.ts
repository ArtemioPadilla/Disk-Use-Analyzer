import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useCleanupRunner, __resetCleanupRunnerForTests } from './useCleanupRunner';
import { emit, on } from '../lib/events';
import { api } from '../lib/api';

vi.mock('../lib/api', () => ({
  api: { createTerminal: vi.fn(), getSystemInfo: vi.fn() },
}));

const mockedCreate = vi.mocked(api.createTerminal);
const mockedGetSystemInfo = vi.mocked(api.getSystemInfo);

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.useRealTimers();
  __resetCleanupRunnerForTests();
  mockedCreate.mockResolvedValue({ pty_id: 'pty-1', created_at: '2026-01-01T00:00:00Z' } as any);
  // Default: the disk measurement is unavailable, so completed jobs fall
  // back to the recommendation's own estimate — this is what every test
  // below that doesn't care about disk measurement relies on. Tests that
  // do care override this per-call with mockResolvedValueOnce.
  mockedGetSystemInfo.mockRejectedValue(new Error('getSystemInfo not mocked in this test'));
});

/**
 * Queue `job`, let it start (mockedCreate always resolves to pty-1 unless a
 * test overrides it), fire its exit with `code`, and wait for the queue to
 * settle before returning.
 */
async function ejecutarYCompletar(job: { command: string; space: number }, code: number): Promise<void> {
  const { result } = renderHook(() => useCleanupRunner());
  act(() => { result.current.run(job); });
  await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
  act(() => { emit('terminal:exited', { pty_id: 'pty-1', code }); });
  await waitFor(() => expect(result.current.running.has(job.command)).toBe(false));
}

describe('useCleanupRunner', () => {
  it('credits the saving only after the command exits with code 0', async () => {
    const onCompleted = vi.fn();
    window.addEventListener('cleanup:completed', onCompleted);

    const { result } = renderHook(() => useCleanupRunner());
    act(() => { result.current.run({ command: 'rm -rf /tmp/x', space: 1024 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));

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
    act(() => { result.current.run({ command: 'false', space: 999 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 1 }); });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(onCompleted).not.toHaveBeenCalled();

    window.removeEventListener('cleanup:completed', onCompleted);
  });

  it('emits cleanup:completed exactly once per run', async () => {
    const onCompleted = vi.fn();
    window.addEventListener('cleanup:completed', onCompleted);

    const { result } = renderHook(() => useCleanupRunner());
    act(() => { result.current.run({ command: 'echo hi', space: 10 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    // A duplicate exit event for the same pty must not double-credit
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });

    await waitFor(() => expect(onCompleted).toHaveBeenCalledTimes(1));
    window.removeEventListener('cleanup:completed', onCompleted);
  });

  it('does not re-run a command already completed', async () => {
    const { result } = renderHook(() => useCleanupRunner());
    act(() => { result.current.run({ command: 'brew cleanup', space: 5 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() => expect(result.current.completed.has('brew cleanup')).toBe(true));

    mockedCreate.mockClear();
    act(() => { result.current.run({ command: 'brew cleanup', space: 5 }); });
    expect(mockedCreate).not.toHaveBeenCalled();
  });

  // Renamed from "shares the completed set across instances via localStorage":
  // sharing across instances is now the module singleton (see the Fix round 3
  // tests below), not localStorage — localStorage's actual job is surviving a
  // full page reload, which is what this test verifies directly.
  it('persists completed commands to localStorage so they survive a page reload', async () => {
    const { result } = renderHook(() => useCleanupRunner());
    act(() => { result.current.run({ command: 'npm cache clean', space: 7 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() => expect(result.current.completed.has('npm cache clean')).toBe(true));

    const stored = JSON.parse(localStorage.getItem('disk-analyzer-cleaned') ?? '[]');
    expect(stored).toContain('npm cache clean');
  });

  it('surfaces an error when the terminal cannot be created', async () => {
    mockedCreate.mockRejectedValue(new Error('429 too many sessions'));
    const { result } = renderHook(() => useCleanupRunner());
    act(() => { result.current.run({ command: 'whatever', space: 1 }); });
    await waitFor(() => expect(result.current.error).toContain('429'));
  });

  it('clears the completed set in memory and in storage on reset()', async () => {
    const { result } = renderHook(() => useCleanupRunner());
    act(() => { result.current.run({ command: 'brew cleanup', space: 5 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() => expect(result.current.completed.has('brew cleanup')).toBe(true));

    act(() => { result.current.reset(); });

    expect(result.current.completed.has('brew cleanup')).toBe(false);
    expect(localStorage.getItem('disk-analyzer-cleaned')).toBeNull();

    // A command that was "done" before the reset can run again afterward.
    mockedCreate.mockClear();
    act(() => { result.current.run({ command: 'brew cleanup', space: 5 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
  });

  it('resets automatically when a fresh analysis completes, invisible to a mounted instance otherwise', async () => {
    const { result } = renderHook(() => useCleanupRunner());
    act(() => { result.current.run({ command: 'npm cache clean', space: 7 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() => expect(result.current.completed.has('npm cache clean')).toBe(true));

    act(() => { emit('analysis:completed', { id: 's1', status: 'done', results: [] }); });

    await waitFor(() => expect(result.current.completed.has('npm cache clean')).toBe(false));
    expect(localStorage.getItem('disk-analyzer-cleaned')).toBeNull();
  });

  // ── Fix round 2: shared store + serialized execution ────────────────────

  it('processes a batch of run() calls one PTY at a time, and eventually credits all of them', async () => {
    let n = 0;
    mockedCreate.mockImplementation(async () => ({ pty_id: `batch-pty-${++n}`, created_at: 't' } as any));

    const { result } = renderHook(() => useCleanupRunner());
    act(() => {
      result.current.run({ command: 'cmd-1', space: 10 });
      result.current.run({ command: 'cmd-2', space: 20 });
      result.current.run({ command: 'cmd-3', space: 30 });
    });

    // Only the first command's PTY is created up front — #2 and #3 are
    // queued, not started, while #1 is still in flight.
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    expect(mockedCreate).toHaveBeenCalledTimes(1);

    act(() => { emit('terminal:exited', { pty_id: 'batch-pty-1', code: 0 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(2));
    // #3 still hasn't started while #2 is in flight.
    expect(mockedCreate).toHaveBeenCalledTimes(2);

    act(() => { emit('terminal:exited', { pty_id: 'batch-pty-2', code: 0 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(3));

    act(() => { emit('terminal:exited', { pty_id: 'batch-pty-3', code: 0 }); });

    await waitFor(() => {
      expect(result.current.completed.has('cmd-1')).toBe(true);
      expect(result.current.completed.has('cmd-2')).toBe(true);
      expect(result.current.completed.has('cmd-3')).toBe(true);
    });
    // Exactly one PTY per command, never more.
    expect(mockedCreate).toHaveBeenCalledTimes(3);
  });

  it('two mounted instances calling run() with the same command create only one PTY, even after the first settles', async () => {
    const a = renderHook(() => useCleanupRunner());
    const b = renderHook(() => useCleanupRunner());

    act(() => {
      a.result.current.run({ command: 'shared-cmd', space: 5 });
      b.result.current.run({ command: 'shared-cmd', space: 5 });
    });

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    // Give any (incorrect) second createTerminal call a chance to happen
    // while the first is still in flight.
    await new Promise(r => setTimeout(r, 0));
    expect(mockedCreate).toHaveBeenCalledTimes(1);

    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() => expect(a.result.current.completed.has('shared-cmd')).toBe(true));
    expect(b.result.current.completed.has('shared-cmd')).toBe(true);

    // The dedup guard must hold even once the first job settles and the
    // queue is free to start whatever comes next. A guard that only checks
    // at enqueue time (and lets the serialization queue hide the duplicate
    // behind the first job) would let b's call start its own PTY for the
    // identical command right here — flush microtasks and confirm it never
    // does.
    await new Promise(r => setTimeout(r, 0));
    expect(mockedCreate).toHaveBeenCalledTimes(1);
  });

  it('a second instance treats a command the first instance already completed as already done', async () => {
    const a = renderHook(() => useCleanupRunner());
    act(() => { a.result.current.run({ command: 'brew cleanup', space: 5 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() => expect(a.result.current.completed.has('brew cleanup')).toBe(true));

    mockedCreate.mockClear();
    const b = renderHook(() => useCleanupRunner());
    expect(b.result.current.completed.has('brew cleanup')).toBe(true);

    act(() => { b.result.current.run({ command: 'brew cleanup', space: 5 }); });
    expect(mockedCreate).not.toHaveBeenCalled();
  });

  it('a failing command in a batch does not block the others from being credited', async () => {
    let n = 0;
    mockedCreate.mockImplementation(async () => ({ pty_id: `mix-pty-${++n}`, created_at: 't' } as any));

    const { result } = renderHook(() => useCleanupRunner());
    act(() => {
      result.current.run({ command: 'ok-1', space: 1, label: 'First' });
      result.current.run({ command: 'fails', space: 2, label: 'Middle' });
      result.current.run({ command: 'ok-2', space: 3, label: 'Last' });
    });

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    act(() => { emit('terminal:exited', { pty_id: 'mix-pty-1', code: 0 }); });

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(2));
    act(() => { emit('terminal:exited', { pty_id: 'mix-pty-2', code: 1 }); });

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(3));
    act(() => { emit('terminal:exited', { pty_id: 'mix-pty-3', code: 0 }); });

    await waitFor(() => {
      expect(result.current.completed.has('ok-1')).toBe(true);
      expect(result.current.completed.has('ok-2')).toBe(true);
    });
    expect(result.current.completed.has('fails')).toBe(false);
    expect(result.current.error).toContain('Middle');
  });

  it('ignores an exit for a pty it is not waiting on, and does not let it advance the queue to the next job', async () => {
    let n = 0;
    mockedCreate.mockImplementation(async () => ({ pty_id: `real-pty-${++n}`, created_at: 't' } as any));

    const { result } = renderHook(() => useCleanupRunner());
    act(() => {
      result.current.run({ command: 'real-cmd-1', space: 9 });
      // A second real job queued behind the first — this is what makes the
      // guard observable: with an empty queue, a broken "advance on any
      // exit" implementation has nothing to wrongly start, so it passes
      // trivially. With something queued, it doesn't.
      result.current.run({ command: 'real-cmd-2', space: 11 });
    });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));

    // A stray exit for some other, untracked pty (e.g. a manually opened
    // shell elsewhere on the page) must not be mistaken for the active job's
    // exit. Give a broken implementation a chance to (wrongly) start #2.
    act(() => { emit('terminal:exited', { pty_id: 'unrelated-pty', code: 0 }); });
    await new Promise(r => setTimeout(r, 0));

    expect(mockedCreate).toHaveBeenCalledTimes(1);
    expect(result.current.running.has('real-cmd-1')).toBe(true);
    expect(result.current.completed.has('real-cmd-1')).toBe(false);
    expect(result.current.running.has('real-cmd-2')).toBe(true); // still queued, not started
    expect(result.current.completed.has('real-cmd-2')).toBe(false);

    // The real job's own exit still resolves normally, and only then does
    // the queue advance to the second command — proving the stray event
    // didn't wedge anything, and didn't jump the queue either.
    act(() => { emit('terminal:exited', { pty_id: 'real-pty-1', code: 0 }); });
    await waitFor(() => expect(result.current.completed.has('real-cmd-1')).toBe(true));
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(2));

    act(() => { emit('terminal:exited', { pty_id: 'real-pty-2', code: 0 }); });
    await waitFor(() => expect(result.current.completed.has('real-cmd-2')).toBe(true));
  });

  it('gives up on a job whose exit never arrives, without crediting it, and continues the queue', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    mockedCreate.mockImplementation(async () => ({ pty_id: `stuck-pty-${++n}`, created_at: 't' } as any));

    const { result } = renderHook(() => useCleanupRunner());
    act(() => {
      result.current.run({ command: 'stuck-cmd', space: 4, label: 'Stuck' });
      result.current.run({ command: 'next-cmd', space: 6 });
    });

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));

    // No exit ever arrives for stuck-pty-1 — advance past the watchdog window.
    await act(async () => { await vi.advanceTimersByTimeAsync(10 * 60 * 1000); });

    expect(result.current.completed.has('stuck-cmd')).toBe(false);
    expect(result.current.running.has('stuck-cmd')).toBe(false);
    expect(result.current.error).toContain('Stuck');

    // The queue moved on to the next command instead of deadlocking.
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(2));
    act(() => { emit('terminal:exited', { pty_id: 'stuck-pty-2', code: 0 }); });
    await waitFor(() => expect(result.current.completed.has('next-cmd')).toBe(true));

    vi.useRealTimers();
  });

  // ── Fix round 5: credit what the disk shows, not the exit code ──────────
  //
  // Crediting savings off the exit code is what let a no-op command report
  // "85 MB liberados". `rm -f` returns 0 whether it deleted everything or
  // nothing — the exit code proves nothing about space. Only the disk does.

  it('acredita el espacio realmente liberado, no el estimado', async () => {
    // libre antes: 10 GB; después: 12 GB  →  se liberaron 2 GB
    mockedGetSystemInfo
      .mockResolvedValueOnce({ disk_usage: { free: 10e9 } } as any)
      .mockResolvedValueOnce({ disk_usage: { free: 12e9 } } as any);

    const visto = vi.fn();
    on('cleanup:completed', visto);
    await ejecutarYCompletar({ command: 'rm -rf x', space: 99e9 }, 0);

    expect(visto).toHaveBeenCalledWith(
      expect.objectContaining({ space: 2e9, estimado: 99e9 }),
    );
  });

  it('un comando que no libera nada acredita cero, no su estimación', async () => {
    mockedGetSystemInfo
      .mockResolvedValueOnce({ disk_usage: { free: 10e9 } } as any)
      .mockResolvedValueOnce({ disk_usage: { free: 10e9 } } as any);

    const visto = vi.fn();
    on('cleanup:completed', visto);
    await ejecutarYCompletar({ command: "rm -rf 'x/*'", space: 85e6 }, 0);

    expect(visto).toHaveBeenCalledWith(expect.objectContaining({ space: 0 }));
  });

  it('nunca acredita un ahorro negativo', async () => {
    // Otro proceso escribió mientras corría la limpieza.
    mockedGetSystemInfo
      .mockResolvedValueOnce({ disk_usage: { free: 12e9 } } as any)
      .mockResolvedValueOnce({ disk_usage: { free: 10e9 } } as any);

    const visto = vi.fn();
    on('cleanup:completed', visto);
    await ejecutarYCompletar({ command: 'rm -rf x', space: 1e9 }, 0);

    expect(visto).toHaveBeenCalledWith(expect.objectContaining({ space: 0 }));
  });

  it('si getSystemInfo falla, cae al espacio estimado sin romper la cola', async () => {
    // Ambas llamadas (antes y después) fallan — comportamiento por defecto
    // del beforeEach de este archivo. La limpieza debe seguir acreditándose
    // con la estimación, no quedar colgada ni lanzar.
    const visto = vi.fn();
    on('cleanup:completed', visto);
    await ejecutarYCompletar({ command: 'rm -rf x', space: 42 }, 0);

    expect(visto).toHaveBeenCalledWith(expect.objectContaining({ space: 42, estimado: 42 }));
  });

  it('si la medición "antes" va bien pero "después" falla, cae al estimado', async () => {
    mockedGetSystemInfo
      .mockResolvedValueOnce({ disk_usage: { free: 10e9 } } as any)
      .mockRejectedValueOnce(new Error('offline'));

    const visto = vi.fn();
    on('cleanup:completed', visto);
    await ejecutarYCompletar({ command: 'rm -rf x', space: 20 }, 0);

    expect(visto).toHaveBeenCalledWith(expect.objectContaining({ space: 20, estimado: 20 }));
  });

  it('si la medición "antes" falla, no se intenta medir "después" y cae al estimado', async () => {
    mockedGetSystemInfo.mockRejectedValueOnce(new Error('offline'));

    const visto = vi.fn();
    on('cleanup:completed', visto);
    await ejecutarYCompletar({ command: 'rm -rf x', space: 15 }, 0);

    expect(visto).toHaveBeenCalledWith(expect.objectContaining({ space: 15, estimado: 15 }));
    // libreAntes quedó en null, así que finishActiveJob nunca intenta la
    // segunda medición — solo se llamó a getSystemInfo una vez.
    expect(mockedGetSystemInfo).toHaveBeenCalledTimes(1);
  });

  // ── Fix round 6: la medición no puede colgar la cola ─────────────────────
  //
  // request() (web/src/lib/api.ts) no tiene timeout ni AbortController: un
  // servidor que acepta la conexión y nunca responde (ocupado con un scan,
  // por ejemplo) dejaría el await de la medición sin resolver para siempre.
  // conLimite() acota ambas mediciones a MEASURE_TIMEOUT_MS (3000ms aquí)
  // para que ese escenario caiga al estimado en vez de colgar la cola.

  it('si la medición "antes" se cuelga, expira y no bloquea la cola', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockedGetSystemInfo.mockImplementationOnce(() => new Promise(() => { /* never resolves */ }));

    const visto = vi.fn();
    on('cleanup:completed', visto);

    const { result } = renderHook(() => useCleanupRunner());
    act(() => { result.current.run({ command: 'rm -rf x', space: 7 }); });

    // La medición "antes" nunca resuelve — avanza más allá de su propio
    // límite para que startJob() pueda seguir y crear el terminal.
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() => expect(visto).toHaveBeenCalled());

    expect(visto).toHaveBeenCalledWith(expect.objectContaining({ space: 7, estimado: 7 }));

    vi.useRealTimers();
  });

  it('si la medición "después" se cuelga, expira, credita el estimado y la cola sigue', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockedGetSystemInfo
      .mockResolvedValueOnce({ disk_usage: { free: 10e9 } } as any) // "antes" ok
      .mockImplementationOnce(() => new Promise(() => { /* never resolves */ })); // "después" se cuelga

    const visto = vi.fn();
    on('cleanup:completed', visto);

    const { result } = renderHook(() => useCleanupRunner());
    act(() => { result.current.run({ command: 'rm -rf x', space: 9 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));

    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });

    // La medición "después" nunca resuelve — avanza más allá de su límite
    // para que se acredite en vez de quedarse colgado para siempre.
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });

    await waitFor(() => expect(visto).toHaveBeenCalled());
    expect(visto).toHaveBeenCalledWith(expect.objectContaining({ space: 9, estimado: 9 }));

    // La cola no quedó atascada: un trabajo encolado detrás sigue pudiendo arrancar.
    mockedGetSystemInfo.mockRejectedValue(new Error('offline'));
    act(() => { result.current.run({ command: 'rm -rf y', space: 3 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(2));

    vi.useRealTimers();
  });
});
