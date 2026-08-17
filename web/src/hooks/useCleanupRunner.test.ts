import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useCleanupRunner, __resetCleanupRunnerForTests } from './useCleanupRunner';
import { emit } from '../lib/events';
import { api } from '../lib/api';

vi.mock('../lib/api', () => ({
  api: { createTerminal: vi.fn() },
}));

const mockedCreate = vi.mocked(api.createTerminal);

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.useRealTimers();
  __resetCleanupRunnerForTests();
  mockedCreate.mockResolvedValue({ pty_id: 'pty-1', created_at: '2026-01-01T00:00:00Z' } as any);
});

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

  it('shares the completed set across instances via localStorage', async () => {
    const first = renderHook(() => useCleanupRunner());
    act(() => { first.result.current.run({ command: 'npm cache clean', space: 7 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
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

  it('two mounted instances calling run() with the same command create only one PTY', async () => {
    const a = renderHook(() => useCleanupRunner());
    const b = renderHook(() => useCleanupRunner());

    act(() => {
      a.result.current.run({ command: 'shared-cmd', space: 5 });
      b.result.current.run({ command: 'shared-cmd', space: 5 });
    });

    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));
    // Give any (incorrect) second createTerminal call a chance to happen.
    await new Promise(r => setTimeout(r, 0));
    expect(mockedCreate).toHaveBeenCalledTimes(1);

    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() => expect(a.result.current.completed.has('shared-cmd')).toBe(true));
    expect(b.result.current.completed.has('shared-cmd')).toBe(true);
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

  it('ignores an exit for a pty it is not waiting on, without disturbing the active job or the queue', async () => {
    mockedCreate.mockResolvedValue({ pty_id: 'real-pty', created_at: 't' } as any);
    const { result } = renderHook(() => useCleanupRunner());
    act(() => { result.current.run({ command: 'real-cmd', space: 9 }); });
    await waitFor(() => expect(mockedCreate).toHaveBeenCalledTimes(1));

    // A stray exit for some other, untracked pty (e.g. a manually opened
    // shell elsewhere on the page) must not be mistaken for this job's exit,
    // and must not leave the queue stuck as if it were waiting on the wrong id.
    act(() => { emit('terminal:exited', { pty_id: 'unrelated-pty', code: 0 }); });
    expect(result.current.running.has('real-cmd')).toBe(true);
    expect(result.current.completed.has('real-cmd')).toBe(false);

    // The real job's own exit still resolves normally afterward — proving
    // the stray event didn't wedge anything.
    act(() => { emit('terminal:exited', { pty_id: 'real-pty', code: 0 }); });
    await waitFor(() => expect(result.current.completed.has('real-cmd')).toBe(true));
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
});
