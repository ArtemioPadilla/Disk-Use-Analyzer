import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useTerminal } from './useTerminal';
import { api } from '../lib/api';

vi.mock('../lib/api', () => ({
  api: { createTerminal: vi.fn(), resizeTerminal: vi.fn(), killTerminal: vi.fn() },
}));

const mockedCreate = vi.mocked(api.createTerminal);

// Minimal fake WebSocket: no real network, just enough surface (onopen/
// onmessage/onclose/close/readyState) for useTerminal to drive, plus a
// registry so tests can reach in and simulate server events.
class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];
  url: string;
  readyState = 0;
  binaryType = '';
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: any }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  sent: any[] = [];
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  send(data: any) { this.sent.push(data); }
  close() { this.closed = true; this.readyState = 3; }
  simulateOpen() { this.readyState = FakeWebSocket.OPEN; this.onopen?.(); }
  simulateExit(code: number) { this.onmessage?.({ data: JSON.stringify({ type: 'exit', code }) }); }
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeWebSocket.instances = [];
  (globalThis as any).WebSocket = FakeWebSocket;
  mockedCreate.mockResolvedValue({ pty_id: 'pty-spawned', created_at: '2026-01-01T00:00:00Z' } as any);
});

describe('useTerminal', () => {
  it('spawn() creates a new PTY and connects a socket to it', async () => {
    const { result } = renderHook(() => useTerminal());
    await act(async () => { await result.current.spawn('echo hi'); });

    expect(mockedCreate).toHaveBeenCalledTimes(1);
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain('pty-spawned');
    expect(result.current.ptyId).toBe('pty-spawned');
  });

  it('attach() connects to an existing PTY without creating a new one', async () => {
    const { result } = renderHook(() => useTerminal());
    await act(async () => { result.current.attach('pty-external', 'rm -rf /tmp/x'); });

    // This is the regression this test guards: a terminal:open carrying a
    // pty_id must not result in a second api.createTerminal call — that
    // would spawn (and re-run) the command a second time.
    expect(mockedCreate).not.toHaveBeenCalled();
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain('pty-external');
    expect(result.current.ptyId).toBe('pty-external');
  });

  it('attach() emits terminal:started for the attached pty so TaskList can track it', async () => {
    const onStarted = vi.fn();
    window.addEventListener('terminal:started', onStarted);

    const { result } = renderHook(() => useTerminal());
    await act(async () => { result.current.attach('pty-external', 'brew cleanup'); });

    expect(onStarted).toHaveBeenCalledTimes(1);
    const detail = (onStarted.mock.calls[0][0] as CustomEvent).detail;
    expect(detail).toEqual({ pty_id: 'pty-external', command: 'brew cleanup' });

    window.removeEventListener('terminal:started', onStarted);
  });

  it('switching pty via attach() closes the previous socket', async () => {
    const { result } = renderHook(() => useTerminal());
    await act(async () => { result.current.attach('pty-a'); });
    const first = FakeWebSocket.instances[0];
    expect(first.closed).toBe(false);

    await act(async () => { result.current.attach('pty-b'); });

    expect(first.closed).toBe(true);
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(result.current.ptyId).toBe('pty-b');
  });

  it('surfaces terminal:exited with the attached pty_id, not a spawned one', async () => {
    const onExited = vi.fn();
    window.addEventListener('terminal:exited', onExited);

    const { result } = renderHook(() => useTerminal());
    await act(async () => { result.current.attach('pty-external'); });
    const ws = FakeWebSocket.instances[0];
    act(() => { ws.simulateOpen(); ws.simulateExit(0); });

    await waitFor(() => expect(onExited).toHaveBeenCalledTimes(1));
    const detail = (onExited.mock.calls[0][0] as CustomEvent).detail;
    expect(detail).toEqual({ pty_id: 'pty-external', code: 0 });

    window.removeEventListener('terminal:exited', onExited);
  });
});
