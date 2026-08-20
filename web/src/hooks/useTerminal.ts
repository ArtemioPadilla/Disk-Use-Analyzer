import { useState, useCallback, useRef, useEffect } from 'react';
import { api } from '../lib/api';
import { withToken, notifyAuthInvalid } from '../lib/auth';
import { emit } from '../lib/events';

// sessionStorage (not localStorage) is deliberate: a live terminal only
// makes sense for the lifetime of this browser tab. A pty_id surviving a
// full browser restart would almost certainly point at a session the server
// (restarted or not) no longer has, or a tab the user no longer cares about.
const PTY_STORAGE_KEY = 'disk-analyzer-active-pty';

function getPersistedPtyId(): string | null {
  try { return sessionStorage.getItem(PTY_STORAGE_KEY); } catch { return null; }
}

function persistPtyId(id: string | null) {
  try {
    if (id) sessionStorage.setItem(PTY_STORAGE_KEY, id);
    else sessionStorage.removeItem(PTY_STORAGE_KEY);
  } catch { /* storage disabled (e.g. private browsing) — nothing to persist to */ }
}

export function useTerminal() {
  const [ptyId, setPtyId] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const onDataRef = useRef<((data: string | ArrayBuffer) => void) | null>(null);

  const connect = useCallback((id: string) => {
    // Switching to a different pty (or reconnecting) must not leave the old
    // socket dangling — close it first so its onclose/onerror can't fire
    // after we've already moved state on to the new session.
    wsRef.current?.close();

    const wsUrl = withToken(`ws://${window.location.host}/ws/terminal/${id}`);
    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'exit') {
            emit('terminal:exited', { pty_id: id, code: msg.code });
            setConnected(false);
            persistPtyId(null);
            return;
          }
        } catch {}
        onDataRef.current?.(event.data);
      } else {
        onDataRef.current?.(event.data);
      }
    };
    ws.onclose = (event) => {
      setConnected(false);
      // No reconnect loop here to short-circuit (this hook doesn't retry),
      // but still surface the same explanation as everywhere else if the
      // token was the reason the terminal socket got rejected.
      if (event.code === 1008) notifyAuthInvalid();
    };
    ws.onerror = () => ws.close();
  }, []);

  /**
   * Attach to a PTY session that already exists (created elsewhere, e.g. by
   * useCleanupRunner's own api.createTerminal call) instead of creating a new
   * one. This is what lets the floating terminal show the exact process whose
   * exit code a caller is tracking, rather than spawning a second, invisible
   * copy of the same command.
   */
  const attach = useCallback((id: string, command?: string) => {
    setPtyId(id);
    persistPtyId(id);
    connect(id);
    emit('terminal:started', { pty_id: id, command });
    return id;
  }, [connect]);

  const spawn = useCallback(async (command?: string) => {
    const { pty_id } = await api.createTerminal(command);
    return attach(pty_id, command);
  }, [attach]);

  const send = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(data);
  }, []);

  const resize = useCallback((cols: number, rows: number) => {
    if (ptyId) api.resizeTerminal(ptyId, cols, rows).catch(console.error);
  }, [ptyId]);

  const kill = useCallback(async () => {
    if (ptyId) {
      await api.killTerminal(ptyId).catch(console.error);
      wsRef.current?.close();
      setPtyId(null);
      setConnected(false);
      persistPtyId(null);
    }
  }, [ptyId]);

  useEffect(() => { return () => { wsRef.current?.close(); }; }, []);

  // Reattach to a live PTY on mount. A full page navigation remounts this
  // hook (it lives inside FloatingTerminal, which MainLayout mounts fresh on
  // every page), which would otherwise silently drop a terminal session the
  // user still had open. A persisted pty_id alone isn't proof the session is
  // still real — the server may have restarted since it was saved — so its
  // liveness is checked against the server's own list before reconnecting.
  useEffect(() => {
    const persisted = getPersistedPtyId();
    if (!persisted) return;

    api.getTerminalSessions()
      .then(sessions => {
        const stillAlive = sessions.some(s => s.pty_id === persisted && s.alive);
        if (stillAlive) {
          attach(persisted);
        } else {
          persistPtyId(null);
        }
      })
      .catch(() => {
        // Can't confirm liveness (e.g. server unreachable) — don't attach on
        // a guess. This is best-effort reconnection, not something that
        // should surface an error to the user.
      });
    // Intentionally mount-only: `attach` is stable across renders (useCallback).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ptyId, connected, spawn, attach, send, resize, kill, onDataRef };
}
