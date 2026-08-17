import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useTerminal } from './useTerminal';
import { api } from '../lib/api';

vi.mock('../lib/api', () => ({
  api: {
    createTerminal: vi.fn(),
    resizeTerminal: vi.fn(),
    killTerminal: vi.fn(),
    getTerminalSessions: vi.fn(),
  },
}));

const mockedCreate = vi.mocked(api.createTerminal);
const mockedGetSessions = vi.mocked(api.getTerminalSessions);

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
  vi.mocked(api.killTerminal).mockResolvedValue({} as any);
  // No PTY reachable by default, so the mount-time reattach effect (see
  // "reattach on mount" describe block below) is a no-op unless a test
  // explicitly sets up a persisted id + a matching alive session.
  mockedGetSessions.mockResolvedValue([]);
  sessionStorage.clear();
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

  describe('pty_id persistence (sessionStorage)', () => {
    it('attach() persists the pty_id so a later mount can find it', async () => {
      const { result } = renderHook(() => useTerminal());
      await act(async () => { result.current.attach('pty-external'); });

      expect(sessionStorage.getItem('disk-analyzer-active-pty')).toBe('pty-external');
    });

    it('kill() clears the persisted pty_id', async () => {
      const { result } = renderHook(() => useTerminal());
      await act(async () => { result.current.attach('pty-external'); });
      expect(sessionStorage.getItem('disk-analyzer-active-pty')).toBe('pty-external');

      await act(async () => { await result.current.kill(); });

      expect(sessionStorage.getItem('disk-analyzer-active-pty')).toBeNull();
    });

    it('terminal:exited clears the persisted pty_id', async () => {
      const { result } = renderHook(() => useTerminal());
      await act(async () => { result.current.attach('pty-external'); });
      const ws = FakeWebSocket.instances[0];
      act(() => { ws.simulateOpen(); ws.simulateExit(0); });

      await waitFor(() => expect(sessionStorage.getItem('disk-analyzer-active-pty')).toBeNull());
    });
  });

  describe('reattach on mount', () => {
    it('does not attach to a persisted pty_id the server no longer reports as alive', async () => {
      sessionStorage.setItem('disk-analyzer-active-pty', 'pty-dead');
      // Server confirms this pty_id doesn't exist (a since-restarted server
      // would report nothing for it, or another session entirely).
      mockedGetSessions.mockResolvedValue([]);

      const { result } = renderHook(() => useTerminal());

      // Give the mount effect's promise a tick to resolve.
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      expect(FakeWebSocket.instances).toHaveLength(0);
      expect(result.current.ptyId).toBeNull();
      // The stale entry is cleaned up, not left around to be retried forever.
      expect(sessionStorage.getItem('disk-analyzer-active-pty')).toBeNull();
    });

    it('does not attach to a persisted pty_id the server reports as no longer alive', async () => {
      sessionStorage.setItem('disk-analyzer-active-pty', 'pty-exited');
      mockedGetSessions.mockResolvedValue([
        { pty_id: 'pty-exited', command: 'zsh', created_at: '2026-01-01T00:00:00Z', alive: false },
      ] as any);

      const { result } = renderHook(() => useTerminal());
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      expect(FakeWebSocket.instances).toHaveLength(0);
      expect(result.current.ptyId).toBeNull();
    });

    it('reattaches to a persisted pty_id the server confirms is still alive', async () => {
      sessionStorage.setItem('disk-analyzer-active-pty', 'pty-alive');
      mockedGetSessions.mockResolvedValue([
        { pty_id: 'pty-alive', command: 'zsh', created_at: '2026-01-01T00:00:00Z', alive: true },
      ] as any);

      const { result } = renderHook(() => useTerminal());
      await waitFor(() => expect(result.current.ptyId).toBe('pty-alive'));

      expect(mockedCreate).not.toHaveBeenCalled();
      expect(FakeWebSocket.instances).toHaveLength(1);
      expect(FakeWebSocket.instances[0].url).toContain('pty-alive');
    });

    it('does nothing when no pty_id was persisted', async () => {
      renderHook(() => useTerminal());
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      expect(mockedGetSessions).not.toHaveBeenCalled();
      expect(FakeWebSocket.instances).toHaveLength(0);
    });
  });
});
