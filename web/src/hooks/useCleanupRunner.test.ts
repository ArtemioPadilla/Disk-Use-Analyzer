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
  mockedCreate.mockResolvedValue({ pty_id: 'pty-1', created_at: '2026-01-01T00:00:00Z' } as any);
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

  it('clears the completed set in memory and in storage on reset()', async () => {
    const { result } = renderHook(() => useCleanupRunner());
    await act(async () => {
      await result.current.run({ command: 'brew cleanup', space: 5 });
    });
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() => expect(result.current.completed.has('brew cleanup')).toBe(true));

    act(() => { result.current.reset(); });

    expect(result.current.completed.has('brew cleanup')).toBe(false);
    expect(localStorage.getItem('disk-analyzer-cleaned')).toBeNull();

    // A command that was "done" before the reset can run again afterward.
    mockedCreate.mockClear();
    await act(async () => {
      await result.current.run({ command: 'brew cleanup', space: 5 });
    });
    expect(mockedCreate).toHaveBeenCalledTimes(1);
  });

  it('resets automatically when a fresh analysis completes, invisible to a mounted instance otherwise', async () => {
    const { result } = renderHook(() => useCleanupRunner());
    await act(async () => {
      await result.current.run({ command: 'npm cache clean', space: 7 });
    });
    act(() => { emit('terminal:exited', { pty_id: 'pty-1', code: 0 }); });
    await waitFor(() => expect(result.current.completed.has('npm cache clean')).toBe(true));

    act(() => { emit('analysis:completed', { id: 's1', status: 'done', results: [] }); });

    await waitFor(() => expect(result.current.completed.has('npm cache clean')).toBe(false));
    expect(localStorage.getItem('disk-analyzer-cleaned')).toBeNull();
  });
});
