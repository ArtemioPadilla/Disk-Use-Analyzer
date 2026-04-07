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
  const [showCommands, setShowCommands] = useState(false);
  const [ptyCommands, setPtyCommands] = useState<Record<string, string>>({});

  // Load running (completed commands) state from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem('disk-analyzer-wizard-running');
      if (saved) setRunning(new Set(JSON.parse(saved)));
    } catch {}
  }, []);

  // Save running state
  useEffect(() => {
    localStorage.setItem('disk-analyzer-wizard-running', JSON.stringify([...running]));
  }, [running]);

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      const allRecs = data.results.flatMap(r => r.report.recommendations);
      setRecs(allRecs);
      // New scan = fresh data, clear completed commands
      setRunning(new Set());
      localStorage.removeItem('disk-analyzer-wizard-running');
    });
    return off;
  }, []);

  // Listen for terminal exit events to mark commands as finished
  useEffect(() => {
    const off = on('terminal:exited', (data: any) => {
      const cmd = ptyCommands[data.pty_id];
      if (cmd) {
        setRunning(prev => { const n = new Set(prev); n.delete(cmd); return n; });
        setPtyCommands(prev => { const n = { ...prev }; delete n[data.pty_id]; return n; });
      }
    });
    return off;
  }, [ptyCommands]);

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
        setPtyCommands(prev => ({ ...prev, [pty_id]: rec.command }));
        emit('terminal:open', { pty_id, command: rec.command });
        emit('terminal:started', { pty_id, command: rec.command });
        setRunning(prev => new Set(prev).add(rec.command));
      } catch (e) {
        console.error('Failed to run command:', e);
      }
    }
  };

  const totalRecoverable = recs.reduce((s, r) => s + (r.space || 0), 0);
  const safeTotalSpace = recs.filter(r => (r.tier || 1) === 1).reduce((s, r) => s + (r.space || 0), 0);

  const cleanSafeItems = async () => {
    const safeRecs = recs.filter(r => (r.tier || 1) === 1 && r.command && !r.command.startsWith('#'));
    for (const rec of safeRecs) {
      try {
        const { pty_id } = await api.createTerminal(rec.command);
        setPtyCommands(prev => ({ ...prev, [pty_id]: rec.command }));
        emit('terminal:open', { pty_id, command: rec.command });
        emit('terminal:started', { pty_id, command: rec.command });
        setRunning(prev => new Set(prev).add(rec.command));
      } catch (e) { console.error('Failed:', e); }
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
        <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🧹</div>
        <div style={{ marginBottom: '0.5rem', fontWeight: 500 }}>No cleanup recommendations</div>
        <p style={{ fontSize: '0.85rem', marginBottom: '1.5rem' }}>Scan your disk to get started.</p>
        <button className="btn btn-primary" onClick={() => emit('analysis:new')}>
          + New Analysis
        </button>
      </div>
    );
  }

  return (
    <div>
      {/* Summary card */}
      <div className="card" style={{ marginBottom: '1rem', background: 'linear-gradient(135deg, var(--primary), var(--secondary))', color: 'white', border: 'none' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ fontSize: '0.85rem', opacity: 0.9 }}>Total recoverable space</div>
            <div style={{ fontSize: '2rem', fontWeight: 700 }}>{formatBytes(totalRecoverable)}</div>
            <div style={{ fontSize: '0.8rem', opacity: 0.8 }}>{recs.length} cleanup actions available</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {safeTotalSpace > 0 && (
              <button onClick={cleanSafeItems} disabled={running.size > 0}
                style={{ background: 'white', color: 'var(--primary)', border: 'none', padding: '0.6rem 1.5rem', borderRadius: '8px', fontWeight: 600, fontSize: '0.9rem', cursor: 'pointer' }}>
                {running.size > 0 ? 'Cleaning...' : `Clean Safe Items (${formatBytes(safeTotalSpace)})`}
              </button>
            )}
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.75rem', opacity: 0.9, cursor: 'pointer' }}>
              <input type="checkbox" checked={showCommands} onChange={e => setShowCommands(e.target.checked)} />
              Show terminal commands
            </label>
          </div>
        </div>
      </div>
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
                        {showCommands && rec.command && !rec.command.startsWith('#') && (
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
