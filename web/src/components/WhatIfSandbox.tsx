import { useState, useEffect, useMemo } from 'react';
import { on, emit } from '../lib/events';
import { api, type Recommendation, type SessionResults } from '../lib/api';
import { formatBytes } from '../lib/format';

export default function WhatIfSandbox() {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [diskUsed, setDiskUsed] = useState(0);
  const [diskTotal, setDiskTotal] = useState(0);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      const report = data.results?.[0]?.report;
      if (!report) return;
      const disk = report.summary?.disk_usage;
      if (disk) { setDiskUsed(disk.used); setDiskTotal(disk.total); }
      const items = (report.recommendations || []).filter(r => r.command && !r.command.startsWith('#') && r.space > 0);
      setRecs(items);
      setChecked(new Set());
      setApplied(false);
    });
    return off;
  }, []);

  const totalChecked = useMemo(() => {
    return [...checked].reduce((s, i) => s + (recs[i]?.space || 0), 0);
  }, [checked, recs]);

  const projectedUsed = diskUsed - totalChecked;
  const currentPct = diskTotal > 0 ? (diskUsed / diskTotal) * 100 : 0;
  const projectedPct = diskTotal > 0 ? Math.max(0, (projectedUsed / diskTotal) * 100) : 0;

  const toggle = (index: number) => {
    setChecked(prev => {
      const next = new Set(prev);
      next.has(index) ? next.delete(index) : next.add(index);
      return next;
    });
  };

  const selectAll = () => setChecked(new Set(recs.map((_, i) => i)));
  const selectNone = () => setChecked(new Set());
  const selectSafe = () => setChecked(new Set(recs.map((r, i) => (r.tier || 9) <= 1 ? i : -1).filter(i => i >= 0)));

  const applyCleanup = async () => {
    setApplying(true);
    const commands = [...checked].map(i => recs[i]?.command).filter(Boolean);
    for (const cmd of commands) {
      try {
        const { pty_id } = await api.createTerminal(cmd!);
        emit('terminal:started', { pty_id, command: cmd });
      } catch (e) { console.error(e); }
    }
    emit('cleanup:completed', { command: 'what-if-sandbox', space: totalChecked });
    setApplying(false);
    setApplied(true);
  };

  if (recs.length === 0) return null;

  const tierColors: Record<number, string> = { 1: '#10b981', 2: '#f59e0b', 3: '#ef4444', 4: '#7c3aed' };
  const tierLabels: Record<number, string> = { 1: 'Safe', 2: 'Moderate', 3: 'Aggressive', 4: 'Deep' };

  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <div style={{ fontWeight: 600 }}>What If Sandbox</div>
        <div style={{ display: 'flex', gap: '0.5rem', fontSize: '0.75rem' }}>
          <button onClick={selectAll} className="btn btn-ghost" style={{ padding: '0.2rem 0.5rem', fontSize: '0.7rem' }}>All</button>
          <button onClick={selectSafe} className="btn btn-ghost" style={{ padding: '0.2rem 0.5rem', fontSize: '0.7rem' }}>Safe only</button>
          <button onClick={selectNone} className="btn btn-ghost" style={{ padding: '0.2rem 0.5rem', fontSize: '0.7rem' }}>None</button>
        </div>
      </div>

      {/* Live projected bar */}
      <div style={{ marginBottom: '0.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
          <span>Simulated cleanup: {checked.size} items ({formatBytes(totalChecked)})</span>
          <span>{currentPct.toFixed(0)}% &rarr; {projectedPct.toFixed(0)}%</span>
        </div>
        <div style={{ height: 16, background: 'var(--border)', borderRadius: 8, overflow: 'hidden', position: 'relative' }}>
          <div style={{
            position: 'absolute', height: '100%',
            width: `${currentPct}%`, background: 'var(--primary)', opacity: 0.2, borderRadius: 8,
          }} />
          <div style={{
            position: 'absolute', height: '100%', borderRadius: 8,
            width: `${projectedPct}%`,
            background: projectedPct > 90 ? 'var(--danger)' : projectedPct > 75 ? 'var(--warning)' : 'var(--success)',
            transition: 'width 0.3s ease, background 0.3s',
          }} />
        </div>
      </div>

      {/* Checkbox list */}
      <div style={{ maxHeight: 300, overflowY: 'auto', marginBottom: '0.75rem' }}>
        {recs.map((rec, i) => (
          <label key={i} style={{
            display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.4rem 0.25rem',
            borderBottom: '1px solid var(--border)', cursor: 'pointer', fontSize: '0.8rem',
            background: checked.has(i) ? (tierColors[rec.tier] || '#6b7280') + '08' : 'transparent',
          }}>
            <input type="checkbox" checked={checked.has(i)} onChange={() => toggle(i)} />
            <span style={{
              fontSize: '0.65rem', padding: '0.1rem 0.35rem', borderRadius: '3px',
              background: (tierColors[rec.tier] || '#6b7280') + '20',
              color: tierColors[rec.tier] || '#6b7280',
            }}>{tierLabels[rec.tier] || '?'}</span>
            <span style={{ flex: 1 }}>{rec.description}</span>
            <span style={{ fontWeight: 500, whiteSpace: 'nowrap', color: checked.has(i) ? 'var(--success)' : 'var(--text-muted)' }}>
              {formatBytes(rec.space)}
            </span>
          </label>
        ))}
      </div>

      {/* Apply button */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
        {applied ? (
          <span style={{ color: 'var(--success)', fontWeight: 600 }}>Cleanup applied!</span>
        ) : (
          <button className="btn btn-primary" onClick={applyCleanup}
            disabled={checked.size === 0 || applying}
            style={{ opacity: checked.size === 0 ? 0.5 : 1 }}>
            {applying ? 'Applying...' : `Apply Cleanup (${formatBytes(totalChecked)})`}
          </button>
        )}
      </div>
    </div>
  );
}
