import { useState, useEffect } from 'react';
import { on } from '../lib/events';
import { type Recommendation, type SessionResults } from '../lib/api';
import { formatBytes } from '../lib/format';
import { useCleanupRunner } from '../hooks/useCleanupRunner';

export default function QuickActions() {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const { run, running, completed } = useCleanupRunner();

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      const safeRecs = data.results
        .flatMap(r => r.report.recommendations)
        .filter(r => (r.tier || 9) === 1 && r.command && !r.command.startsWith('#') && r.space > 0)
        .sort((a, b) => b.space - a.space)
        .slice(0, 3);
      setRecs(safeRecs);
    });
    return off;
  }, []);

  if (recs.length === 0) return null;

  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.9rem' }}>Quick Cleanup</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.5rem' }}>
        {recs.map((rec, i) => {
          const isDone = completed.has(rec.command);
          const isRunning = running.has(rec.command);
          return (
            <div key={i} className="card" style={{
              display: 'flex', flexDirection: 'column', gap: '0.5rem',
              opacity: isDone ? 0.6 : 1,
              background: isDone ? 'var(--page-bg)' : 'var(--card-bg)',
            }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{rec.description}</div>
              <div style={{ fontWeight: 700, color: isDone ? 'var(--success)' : 'var(--primary)' }}>
                {isDone ? '✓ Cleaned' : formatBytes(rec.space)}
              </div>
              {!isDone && (
                <button className="btn btn-primary"
                  onClick={() => run({ command: rec.command, space: rec.space, label: rec.description })}
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
