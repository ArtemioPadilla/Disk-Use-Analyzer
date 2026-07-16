import { useState, useEffect } from 'react';
import { on, emit } from '../lib/events';
import { api, type Recommendation, type SessionResults } from '../lib/api';
import { formatBytes } from '../lib/format';

export default function QuickActions() {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [cleaned, setCleaned] = useState<Set<string>>(new Set());
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [ptyCommands, setPtyCommands] = useState<Record<string, { command: string; space: number }>>({});

  // Load cleaned state from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem('disk-analyzer-cleaned');
      if (saved) setCleaned(new Set(JSON.parse(saved)));
    } catch {}
  }, []);

  // Save cleaned state
  useEffect(() => {
    localStorage.setItem('disk-analyzer-cleaned', JSON.stringify([...cleaned]));
  }, [cleaned]);

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      const safeRecs = data.results
        .flatMap(r => r.report.recommendations)
        .filter(r => (r.tier || 9) === 1 && r.command && !r.command.startsWith('#') && r.space > 0)
        .sort((a, b) => b.space - a.space)
        .slice(0, 3);
      setRecs(safeRecs);
      // New scan = fresh data, clear cleaned state
      setCleaned(new Set());
      localStorage.removeItem('disk-analyzer-cleaned');
    });
    return off;
  }, []);

  // Listen for terminal exit events to mark commands as cleaned
  useEffect(() => {
    const off = on('terminal:exited', (data: any) => {
      const mapping = ptyCommands[data.pty_id];
      if (mapping) {
        if (data.code === 0) {
          setCleaned(prev => {
            const n = new Set(prev).add(mapping.command);
            localStorage.setItem('disk-analyzer-cleaned', JSON.stringify([...n]));
            return n;
          });
          emit('cleanup:completed', { command: mapping.command, space: mapping.space });
        }
        setRunning(prev => { const n = new Set(prev); n.delete(mapping.command); return n; });
        setPtyCommands(prev => { const n = { ...prev }; delete n[data.pty_id]; return n; });
      }
    });
    return off;
  }, [ptyCommands]);

  const runClean = async (rec: Recommendation) => {
    if (running.has(rec.command) || cleaned.has(rec.command)) return;
    setRunning(prev => new Set(prev).add(rec.command));
    try {
      const { pty_id } = await api.createTerminal(rec.command);
      setPtyCommands(prev => ({ ...prev, [pty_id]: { command: rec.command, space: rec.space } }));
      emit('terminal:open', { pty_id, command: rec.command });
      emit('terminal:started', { pty_id, command: rec.command });
    } catch (e) {
      setRunning(prev => { const n = new Set(prev); n.delete(rec.command); return n; });
      console.error('Failed:', e);
    }
  };

  if (recs.length === 0) return null;

  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.9rem' }}>Quick Cleanup</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.5rem' }}>
        {recs.map((rec, i) => {
          const isDone = cleaned.has(rec.command);
          const isRunning = running.has(rec.command);
          return (
            <div key={i} className="card" style={{
              display: 'flex', flexDirection: 'column', gap: '0.5rem',
              opacity: isDone ? 0.6 : 1,
              background: isDone ? 'var(--page-bg)' : 'var(--card-bg)',
            }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{rec.description}</div>
              <div style={{ fontWeight: 700, color: isDone ? 'var(--success)' : 'var(--primary)' }}>
                {isDone ? '\u2713 Cleaned' : formatBytes(rec.space)}
              </div>
              {!isDone && (
                <button className="btn btn-primary" onClick={() => runClean(rec)}
                  disabled={isRunning}
                  style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem', alignSelf: 'flex-start' }}>
                  {isRunning ? 'Cleaning...' : 'Clean'}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
