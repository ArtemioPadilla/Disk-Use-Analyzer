import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { emit } from '../lib/events';
import { formatBytes } from '../lib/format';

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
  const [comparing, setComparing] = useState<string[]>([]);
  const [comparison, setComparison] = useState<any>(null);

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

  const runComparison = async () => {
    try {
      const [r1, r2] = await Promise.all(comparing.map(id => api.getResults(id)));
      const s1 = r1.results?.[0]?.report?.summary;
      const s2 = r2.results?.[0]?.report?.summary;
      if (s1 && s2) {
        setComparison({
          session1: comparing[0],
          session2: comparing[1],
          s1, s2,
          sizeDelta: s2.total_size - s1.total_size,
          filesDelta: s2.files_scanned - s1.files_scanned,
          recoverableDelta: s2.recoverable_space - s1.recoverable_space,
        });
      }
    } catch (e) {
      alert('Could not load results for comparison. Results may no longer be in memory.');
    }
  };

  const statusColors: Record<string, string> = { completed: '#10b981', running: '#6366f1', error: '#ef4444' };

  if (loading) return <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>Loading sessions...</div>;

  if (sessions.length === 0) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🕘</div>
        <div style={{ marginBottom: '0.5rem', fontWeight: 500 }}>No analysis history</div>
        <p style={{ fontSize: '0.85rem', marginBottom: '1.5rem' }}>Scan your disk to get started.</p>
        <button className="btn btn-primary" onClick={() => emit('analysis:new')}>
          + New Analysis
        </button>
      </div>
    );
  }

  return (
    <div>
      {comparing.length === 2 && (
        <div style={{ marginBottom: '1rem' }}>
          <button className="btn btn-primary" onClick={runComparison}>Compare Selected</button>
        </div>
      )}

      {comparison && (
        <div className="card" style={{ marginBottom: '1rem', background: 'var(--page-bg)' }}>
          <h3 style={{ marginBottom: '0.75rem' }}>Comparison</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.5rem', fontSize: '0.85rem' }}>
            <div></div>
            <div style={{ fontWeight: 600, textAlign: 'center' }}>Earlier</div>
            <div style={{ fontWeight: 600, textAlign: 'center' }}>Later</div>

            <div style={{ color: 'var(--text-muted)' }}>Total Size</div>
            <div style={{ textAlign: 'center' }}>{formatBytes(comparison.s1.total_size)}</div>
            <div style={{ textAlign: 'center' }}>
              {formatBytes(comparison.s2.total_size)}
              <span style={{ color: comparison.sizeDelta > 0 ? 'var(--danger)' : 'var(--success)', marginLeft: '0.25rem', fontSize: '0.75rem' }}>
                {comparison.sizeDelta > 0 ? '\u2191' : '\u2193'}{formatBytes(Math.abs(comparison.sizeDelta))}
              </span>
            </div>

            <div style={{ color: 'var(--text-muted)' }}>Files Scanned</div>
            <div style={{ textAlign: 'center' }}>{comparison.s1.files_scanned.toLocaleString()}</div>
            <div style={{ textAlign: 'center' }}>{comparison.s2.files_scanned.toLocaleString()}</div>

            <div style={{ color: 'var(--text-muted)' }}>Recoverable</div>
            <div style={{ textAlign: 'center' }}>{formatBytes(comparison.s1.recoverable_space)}</div>
            <div style={{ textAlign: 'center' }}>
              {formatBytes(comparison.s2.recoverable_space)}
              <span style={{ color: comparison.recoverableDelta > 0 ? 'var(--warning)' : 'var(--success)', marginLeft: '0.25rem', fontSize: '0.75rem' }}>
                {comparison.recoverableDelta > 0 ? '\u2191' : '\u2193'}{formatBytes(Math.abs(comparison.recoverableDelta))}
              </span>
            </div>

            <div style={{ color: 'var(--text-muted)' }}>Cache Size</div>
            <div style={{ textAlign: 'center' }}>{formatBytes(comparison.s1.cache_size)}</div>
            <div style={{ textAlign: 'center' }}>{formatBytes(comparison.s2.cache_size)}</div>
          </div>
        </div>
      )}

      {sessions.map(session => (
        <div key={session.id} className="card" style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {session.status === 'completed' && (
            <input type="checkbox" checked={comparing.includes(session.id)}
              onChange={() => {
                setComparing(prev => {
                  if (prev.includes(session.id)) return prev.filter(id => id !== session.id);
                  if (prev.length >= 2) return [prev[1], session.id];
                  return [...prev, session.id];
                });
              }}
              style={{ marginRight: '0.5rem' }}
            />
          )}
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
