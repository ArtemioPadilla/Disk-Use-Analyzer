import { useEffect, useRef, useCallback, useState } from 'react';

interface UseWebSocketOptions {
  url: string;
  onMessage: (data: any) => void;
  onClose?: () => void;
  enabled?: boolean;
}

export function useWebSocket({ url, onMessage, onClose, enabled = true }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    if (!enabled) return;
    const wsUrl = `ws://${window.location.host}${url}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      retriesRef.current = 0;
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch {
        onMessage(event.data);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      onClose?.();
      const delay = Math.min(1000 * Math.pow(2, retriesRef.current), 30000);
      retriesRef.current++;
      setTimeout(connect, delay);
    };

    ws.onerror = () => ws.close();
  }, [url, onMessage, onClose, enabled]);

  useEffect(() => {
    connect();
    return () => { wsRef.current?.close(); };
  }, [connect]);

  const send = useCallback((data: string | ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  return { send, connected, ws: wsRef };
}
