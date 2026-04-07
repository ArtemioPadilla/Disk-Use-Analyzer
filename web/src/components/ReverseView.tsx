import { useState, useEffect } from 'react';
import { on, emit } from '../lib/events';
import { api, type SessionResults, type Recommendation } from '../lib/api';
import { formatBytes } from '../lib/format';

interface Tier {
  level: 'safe' | 'review' | 'careful';
  label: string;
  icon: string;
  color: string;
  bgColor: string;
  description: string;
  items: Recommendation[];
  totalSpace: number;
}

export default function ReverseView() {
  const [tiers, setTiers] = useState<Tier[]>([]);
  const [diskUsed, setDiskUsed] = useState(0);
  const [diskTotal, setDiskTotal] = useState(0);
  const [freedSpace, setFreedSpace] = useState(0);
  const [expandedTier, setExpandedTier] = useState<string | null>(null);
  const [cleaningTier, setCleaningTier] = useState<string | null>(null);
  const [cleanedTiers, setCleanedTiers] = useState<Set<string>>(new Set());

  useEffect(() => {
    const offs = [
      on('analysis:completed', (data: SessionResults) => {
        const report = data.results?.[0]?.report;
        if (!report) return;

        const disk = report.summary?.disk_usage;
        if (disk) { setDiskUsed(disk.used); setDiskTotal(disk.total); }

        const recs = report.recommendations || [];
        const safeItems = recs.filter(r => (r.tier || 9) <= 1 && r.command && !r.command.startsWith('#'));
        const reviewItems = recs.filter(r => (r.tier || 9) === 2 && r.command && !r.command.startsWith('#'));
        const carefulItems = recs.filter(r => (r.tier || 9) >= 3 && r.command && !r.command.startsWith('#'));

        setTiers([
          {
            level: 'safe', label: 'SAFE', icon: '🟢', color: '#10b981', bgColor: '#10b98115',
            description: 'Caches, logs, trash. Rebuilds automatically.',
            items: safeItems, totalSpace: safeItems.reduce((s, r) => s + (r.space || 0), 0),
          },
          {
            level: 'review', label: 'REVIEW', icon: '🟡', color: '#f59e0b', bgColor: '#f59e0b15',
            description: 'Old project deps, unused Docker images. Probably safe.',
            items: reviewItems, totalSpace: reviewItems.reduce((s, r) => s + (r.space || 0), 0),
          },
          {
            level: 'careful', label: 'CAREFUL', icon: '🔴', color: '#ef4444', bgColor: '#ef444415',
            description: 'Review individually before deleting.',
            items: carefulItems, totalSpace: carefulItems.reduce((s, r) => s + (r.space || 0), 0),
          },
        ].filter(t => t.items.length > 0));

        setFreedSpace(0);
        setCleanedTiers(new Set());
      }),
      on('cleanup:completed', () => {
        api.getSystemInfo().then(info => {
          setDiskUsed(info.disk_usage.used);
          setDiskTotal(info.disk_usage.total);
        }).catch(console.error);
      }),
    ];
    return () => offs.forEach(off => off());
  }, []);

  const totalRecoverable = tiers.reduce((s, t) => s + t.totalSpace, 0);
  const projectedUsed = diskUsed - freedSpace;
  const currentPct = diskTotal > 0 ? (diskUsed / diskTotal) * 100 : 0;
  const projectedPct = diskTotal > 0 ? (projectedUsed / diskTotal) * 100 : 0;

  const cleanTier = async (tier: Tier) => {
    setCleaningTier(tier.level);
    for (const item of tier.items) {
      if (item.command && !item.command.startsWith('#')) {
        try {
          const { pty_id } = await api.createTerminal(item.command);
          emit('terminal:started', { pty_id, command: item.command });
        } catch (e) { console.error(e); }
      }
    }
    setFreedSpace(prev => prev + tier.totalSpace);
    setCleanedTiers(prev => new Set(prev).add(tier.level));
    setCleaningTier(null);
    emit('cleanup:completed', { command: `tier-${tier.level}`, space: tier.totalSpace });
  };

  if (tiers.length === 0 || totalRecoverable === 0) return null;

  return (
    <div className="card" style={{ marginBottom: '1rem', overflow: 'hidden' }}>
      {/* Header with projected bar */}
      <div style={{ padding: '1rem 1rem 0.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.5rem' }}>
          <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>
            You can free {formatBytes(totalRecoverable)}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            {currentPct.toFixed(0)}% → {projectedPct.toFixed(0)}%
          </div>
        </div>
        <div style={{ height: 12, background: 'var(--border)', borderRadius: 6, overflow: 'hidden', position: 'relative' }}>
          {/* Current usage (faded) */}
          <div style={{
            position: 'absolute', height: '100%', borderRadius: 6,
            width: `${currentPct}%`, background: 'var(--primary)', opacity: 0.3,
          }} />
          {/* Projected usage */}
          <div style={{
            position: 'absolute', height: '100%', borderRadius: 6,
            width: `${projectedPct}%`,
            background: projectedPct > 90 ? 'var(--danger)' : projectedPct > 75 ? 'var(--warning)' : 'var(--success)',
            transition: 'width 0.5s ease, background 0.3s',
          }} />
        </div>
      </div>

      {/* Tiers */}
      {tiers.map(tier => {
        const isCleaned = cleanedTiers.has(tier.level);
        const isCleaning = cleaningTier === tier.level;
        const isExpanded = expandedTier === tier.level;

        return (
          <div key={tier.level} style={{ borderTop: '1px solid var(--border)' }}>
            <div style={{
              display: 'flex', alignItems: 'center', padding: '0.75rem 1rem',
              background: isCleaned ? '#10b98108' : tier.bgColor,
              cursor: 'pointer',
            }} onClick={() => setExpandedTier(isExpanded ? null : tier.level)}>
              <span style={{ marginRight: '0.5rem' }}>{tier.icon}</span>
              <div style={{ flex: 1 }}>
                <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{tier.label}</span>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginLeft: '0.5rem' }}>
                  — {tier.description}
                </span>
              </div>
              <span style={{ fontWeight: 700, color: isCleaned ? 'var(--success)' : tier.color, marginRight: '0.75rem' }}>
                {isCleaned ? '✓ Cleaned' : formatBytes(tier.totalSpace)}
              </span>
              {!isCleaned && (
                <button className="btn btn-primary" onClick={(e) => { e.stopPropagation(); cleanTier(tier); }}
                  disabled={isCleaning}
                  style={{ fontSize: '0.75rem', padding: '0.3rem 0.75rem', background: tier.color, whiteSpace: 'nowrap' }}>
                  {isCleaning ? 'Cleaning...' : `Free ${formatBytes(tier.totalSpace)}`}
                </button>
              )}
            </div>
            {isExpanded && (
              <div style={{ padding: '0.25rem 1rem 0.75rem 2.5rem' }}>
                {tier.items.map((item, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.3rem 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    <span>{item.description}</span>
                    {item.space > 0 && <span>{formatBytes(item.space)}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      {/* Freed total */}
      {freedSpace > 0 && (
        <div style={{
          padding: '0.75rem 1rem', borderTop: '1px solid var(--border)',
          textAlign: 'center', color: 'var(--success)', fontWeight: 600,
          animation: 'fadeSlideUp 0.5s ease',
        }}>
          {formatBytes(freedSpace)} freed so far!
        </div>
      )}
      <style>{`@keyframes fadeSlideUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  );
}
