import { useState, useEffect } from 'react';
import { api } from '../lib/api';

interface SessionMeta {
  id: string;
  status: string;
  paths: string[];
  started_at: string;
  completed_at?: string;
}

export default function SessionList() {
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getSessions()
      .then((data: any) => {
        const list: SessionMeta[] = Array.isArray(data) ? data : data.sessions ?? [];
        setSessions(list.sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime()));
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const loadSession = async (id: string) => {
    try {
      const results = await api.getResults(id);
      window.dispatchEvent(new CustomEvent('analysis:completed', { detail: results }));
      window.location.href = '/';
    } catch {
      alert('Could not load session results. They may no longer be in memory.');
    }
  };

  const statusColors: Record<string, string> = { completed: '#10b981', running: '#6366f1', error: '#ef4444' };

  if (loading) return <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>Loading sessions...</div>;

  if (sessions.length === 0) {
    return (<div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
      No analysis history yet. Start your first analysis from the Dashboard.
    </div>);
  }

  return (
    <div>
      {sessions.map(session => (
        <div key={session.id} className="card" style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.25rem' }}>{session.paths?.join(', ') || session.id}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {new Date(session.started_at).toLocaleString()}
              {session.completed_at && ` \u00B7 Completed ${new Date(session.completed_at).toLocaleString()}`}
            </div>
          </div>
          <span style={{
            fontSize: '0.7rem', padding: '0.15rem 0.5rem', borderRadius: '4px',
            background: (statusColors[session.status] || '#6b7280') + '20',
            color: statusColors[session.status] || '#6b7280',
          }}>{session.status}</span>
          {session.status === 'completed' && (
            <button className="btn btn-ghost" onClick={() => loadSession(session.id)} style={{ fontSize: '0.8rem' }}>Load Results</button>
          )}
        </div>
      ))}
    </div>
  );
}
