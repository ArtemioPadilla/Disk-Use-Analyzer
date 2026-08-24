import { useState, useEffect } from 'react';
import { on, emit } from '../lib/events';
import { type Recommendation, type SessionResults } from '../lib/api';
import { formatBytes } from '../lib/format';
import { useCleanupRunner } from '../hooks/useCleanupRunner';
import { TIER_META } from '../lib/tiers';

/**
 * El nivel de riesgo de una recomendación, o el más restrictivo si no se
 * puede saber.
 *
 * El código anterior hacía `r.tier || 1`, que convertía `undefined`, `null` y
 * `0` en Seguro — y Seguro es justo lo que el botón de "ejecutar todo" lanza
 * sin revisión. Ante una recomendación malformada, lo correcto es lo contrario.
 *
 * Verifica el tipo ANTES de coercionar. Rechaza: booleans (Number(true)===1),
 * arrays (Number([1])===1), strings ("1" !== 1), y números no-enteros.
 */
export function nivelDe(rec: { tier?: unknown }): number {
  const n = rec?.tier;
  return typeof n === 'number' && Number.isInteger(n) && n >= 1 && n <= 4 ? n : 4;
}

export default function CleanupWizard() {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set([1]));
  const [showCommands, setShowCommands] = useState(false);
  const { run, running, completed } = useCleanupRunner();

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

  const runCommand = (rec: Recommendation) => {
    if (rec.command && !rec.command.startsWith('#')) {
      run({ command: rec.command, space: rec.space, label: rec.description });
    }
  };

  const totalRecoverable = recs.reduce((s, r) => s + (r.space || 0), 0);
  const safeTotalSpace = recs.filter(r => nivelDe(r) === 1).reduce((s, r) => s + (r.space || 0), 0);

  const cleanSafeItems = () => {
    const safeRecs = recs.filter(r => nivelDe(r) === 1 && r.command && !r.command.startsWith('#'));
    for (const rec of safeRecs) {
      run({ command: rec.command, space: rec.space, label: rec.description });
    }
  };

  const safeRecsRunnable = recs.filter(r => nivelDe(r) === 1 && r.command && !r.command.startsWith('#'));
  const safeRunning = safeRecsRunnable.some(r => running.has(r.command));

  const grouped = recs.reduce((acc, rec) => {
    const tier = nivelDe(rec);
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
              <button onClick={cleanSafeItems} disabled={safeRunning}
                style={{ background: 'white', color: 'var(--primary)', border: 'none', padding: '0.6rem 1.5rem', borderRadius: '8px', fontWeight: 600, fontSize: '0.9rem', cursor: 'pointer' }}>
                {safeRunning ? 'Cleaning...' : `Clean Safe Items (${formatBytes(safeTotalSpace)})`}
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
                <span>{isOpen ? '▾' : '▸'}</span>
              </div>
              {isOpen && (
                <div style={{ marginTop: '0.75rem' }}>
                  {tierRecs.map((rec, i) => {
                    const isRunning = running.has(rec.command);
                    const isDone = completed.has(rec.command);
                    return (
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
                          disabled={isRunning || isDone}
                          style={{
                            fontSize: '0.75rem',
                            padding: '0.35rem 0.75rem',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {isDone ? '✓ Done' : isRunning ? 'Running...' : '▶ Run'}
                        </button>
                      )}
                    </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
    </div>
  );
}
