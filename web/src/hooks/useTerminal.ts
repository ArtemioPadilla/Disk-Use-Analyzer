import { useState, useCallback, useRef, useEffect } from 'react';
import { api } from '../lib/api';
import { emit } from '../lib/events';

export function useTerminal() {
  const [ptyId, setPtyId] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const onDataRef = useRef<((data: string | ArrayBuffer) => void) | null>(null);

  const connect = useCallback((id: string) => {
    const wsUrl = `ws://${window.location.host}/ws/terminal/${id}`;
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
            return;
          }
        } catch {}
        onDataRef.current?.(event.data);
      } else {
        onDataRef.current?.(event.data);
      }
    };
    ws.onclose = () => setConnected(false);
    ws.onerror = () => ws.close();
  }, []);

  const spawn = useCallback(async (command?: string) => {
    const { pty_id } = await api.createTerminal(command);
    setPtyId(pty_id);
    connect(pty_id);
    emit('terminal:started', { pty_id, command });
    return pty_id;
  }, [connect]);

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
    }
  }, [ptyId]);

  useEffect(() => { return () => { wsRef.current?.close(); }; }, []);

  return { ptyId, connected, spawn, send, resize, kill, onDataRef };
}
