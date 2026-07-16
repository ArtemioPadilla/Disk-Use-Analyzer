import { useState, useCallback } from 'react';
import { api, type AnalysisSession, type SessionResults } from '../lib/api';
import { useWebSocket } from './useWebSocket';
import { emit } from '../lib/events';

interface ProgressUpdate {
  type: string;
  progress?: number;
  current_path?: string;
  message?: string;
  files_scanned?: number;
}

export function useAnalysis() {
  const [session, setSession] = useState<AnalysisSession | null>(null);
  const [results, setResults] = useState<SessionResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleMessage = useCallback((data: ProgressUpdate) => {
    if (data.type === 'progress' || data.type === 'file_progress') {
      setSession(prev => prev ? {
        ...prev,
        progress: data.progress ?? prev.progress,
        current_path: data.current_path ?? prev.current_path,
      } : prev);
      emit('analysis:progress', data);
    }
    if (data.type === 'completed') {
      setSession(prev => prev ? { ...prev, status: 'completed', progress: 100 } : prev);
      if (session?.id) {
        api.getResults(session.id).then(r => {
          setResults(r);
          emit('analysis:completed', r);
        });
      }
    }
    if (data.type === 'error') {
      setSession(prev => prev ? { ...prev, status: 'error' } : prev);
      setError(data.message ?? 'Analysis failed');
      emit('analysis:error', data);
    }
  }, [session?.id]);

  const { connected } = useWebSocket({
    url: `/ws/${session?.id}`,
    onMessage: handleMessage,
    enabled: !!session?.id && session.status === 'running',
  });

  const startAnalysis = useCallback(async (paths: string[], minSizeMb = 10) => {
    setError(null);
    setResults(null);
    const { session_id } = await api.startAnalysis({ paths, min_size_mb: minSizeMb });
    const newSession: AnalysisSession = {
      id: session_id,
      status: 'running',
      progress: 0,
      current_path: '',
      paths,
      started_at: new Date().toISOString(),
    };
    setSession(newSession);
    emit('analysis:started', newSession);
    return session_id;
  }, []);

  return { session, results, error, connected, startAnalysis };
}
