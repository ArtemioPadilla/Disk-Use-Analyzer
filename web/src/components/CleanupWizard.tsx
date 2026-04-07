import { useState, useEffect } from 'react';
import { on, emit } from '../lib/events';
import { api, type Recommendation, type SessionResults } from '../lib/api';
import { formatBytes } from '../lib/format';

const TIER_META: Record<number, { label: string; color: string; icon: string }> = {
  1: { label: 'Safe', color: '#10b981', icon: '✅' },
  2: { label: 'Moderate', color: '#f59e0b', icon: '⚠️' },
  3: { label: 'Aggressive', color: '#ef4444', icon: '🔴' },
  4: { label: 'Deep Clean', color: '#7c3aed', icon: '💀' },
};

export default function CleanupWizard() {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set([1]));
  const [running, setRunning] = useState<Set<string>>(new Set());

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      const allRecs = data.results.flatMap(r => r.report.recommendations);
      setRecs(allRecs);
    });
    return off;
  }, []);

  const toggleTier = (tier: number) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(tier) ? next.delete(tier) : next.add(tier);
      return next;
    });
  };

  const runCommand = async (rec: Recommendation) => {
    if (running.has(rec.command)) return;
    if (rec.command && !rec.command.startsWith('#')) {
      try {
        const { pty_id } = await api.createTerminal(rec.command);
        emit('terminal:open', { pty_id, command: rec.command });
        emit('terminal:started', { pty_id, command: rec.command });
        setRunning(prev => new Set(prev).add(rec.command));
      } catch (e) {
        console.error('Failed to run command:', e);
      }
    }
  };

  const grouped = recs.reduce((acc, rec) => {
    const tier = rec.tier || 1;
    if (!acc[tier]) acc[tier] = [];
    acc[tier].push(rec);
    return acc;
  }, {} as Record<number, Recommendation[]>);

  if (recs.length === 0) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        No cleanup recommendations yet. Run an analysis from the Dashboard first.
      </div>
    );
  }

  return (
    <div>
      {Object.entries(grouped)
        .sort(([a], [b]) => Number(a) - Number(b))
        .map(([tierStr, tierRecs]) => {
          const tier = Number(tierStr);
          const meta = TIER_META[tier] || TIER_META[1];
          const totalSpace = tierRecs.reduce((s, r) => s + (r.space || 0), 0);
          const isOpen = expanded.has(tier);
          return (
            <div key={tier} className="card" style={{ marginBottom: '0.75rem' }}>
              <div
                onClick={() => toggleTier(tier)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  padding: '0.25rem 0',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span>{meta.icon}</span>
                  <span style={{ fontWeight: 600 }}>
                    Tier {tier}: {meta.label}
                  </span>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      padding: '0.15rem 0.5rem',
                      borderRadius: '4px',
                      background: meta.color + '20',
                      color: meta.color,
                    }}
                  >
                    {tierRecs.length} items &middot; {formatBytes(totalSpace)}
                  </span>
                </div>
                <span>{isOpen ? '\u25BE' : '\u25B8'}</span>
              </div>
              {isOpen && (
                <div style={{ marginTop: '0.75rem' }}>
                  {tierRecs.map((rec, i) => (
                    <div
                      key={i}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.75rem',
                        padding: '0.6rem 0',
                        borderTop: i > 0 ? '1px solid var(--border)' : 'none',
                      }}
                    >
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: '0.875rem', fontWeight: 500 }}>
                          {rec.description}
                        </div>
                        {rec.command && !rec.command.startsWith('#') && (
                          <code
                            style={{
                              display: 'block',
                              marginTop: '0.25rem',
                              fontSize: '0.75rem',
                              color: 'var(--text-muted)',
                              background: 'var(--page-bg)',
                              padding: '0.25rem 0.5rem',
                              borderRadius: '4px',
                            }}
                          >
                            {rec.command}
                          </code>
                        )}
                      </div>
                      {rec.space > 0 && (
                        <span
                          style={{
                            fontSize: '0.8rem',
                            fontWeight: 600,
                            color: meta.color,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {formatBytes(rec.space)}
                        </span>
                      )}
                      {rec.command && !rec.command.startsWith('#') && (
                        <button
                          className="btn btn-primary"
                          onClick={() => runCommand(rec)}
                          disabled={running.has(rec.command)}
                          style={{
                            fontSize: '0.75rem',
                            padding: '0.35rem 0.75rem',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {running.has(rec.command) ? 'Running...' : '\u25B6 Run'}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
    </div>
  );
}
