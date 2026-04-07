/**
 * AnalysisManager — persistent component mounted in MainLayout.
 * Manages WebSocket connection for analysis progress and emits events.
 * Does NOT unmount when modals close.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { api, type AnalysisSession, type SessionResults } from '../lib/api';
import { on, emit } from '../lib/events';

export default function AnalysisManager() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  // Keep ref in sync for use in callbacks
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // Listen for analysis:start-request from NewAnalysisModal
  useEffect(() => {
    const off = on('analysis:start-request', async (data: { paths: string[]; minSizeMb: number }) => {
      try {
        const { session_id } = await api.startAnalysis({
          paths: data.paths,
          min_size_mb: data.minSizeMb,
        });
        setSessionId(session_id);
        emit('analysis:started', {
          id: session_id,
          status: 'running',
          progress: 0,
          current_path: '',
          paths: data.paths,
          started_at: new Date().toISOString(),
        });
      } catch (e: any) {
        emit('analysis:error', { message: e.message || 'Failed to start analysis' });
      }
    });
    return off;
  }, []);

  // Connect WebSocket when we have a session
  useEffect(() => {
    if (!sessionId) return;

    const wsUrl = `ws://${window.location.host}/ws/${sessionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log(`[AnalysisManager] WS connected for session ${sessionId}`);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'progress' || data.type === 'file_progress') {
          emit('analysis:progress', data);
        }

        if (data.type === 'completed') {
          const sid = sessionIdRef.current;
          if (sid) {
            api.getResults(sid).then(r => {
              emit('analysis:completed', r);
              setSessionId(null);
            }).catch(err => {
              emit('analysis:error', { message: 'Failed to fetch results' });
              setSessionId(null);
            });
          }
        }

        if (data.type === 'cancelled') {
          emit('analysis:cancelled', { id: sessionIdRef.current });
          setSessionId(null);
        }

        if (data.type === 'error') {
          emit('analysis:error', data);
          setSessionId(null);
        }
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      console.log(`[AnalysisManager] WS closed for session ${sessionId}`);
    };

    ws.onerror = () => ws.close();

    return () => {
      ws.close();
    };
  }, [sessionId]);

  // No UI — this is a headless component
  return null;
}
