import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { formatBytes } from '../lib/format';
import { on } from '../lib/events';

export default function TrendChart() {
  const [points, setPoints] = useState<{date: string; used: number; total: number}[]>([]);

  const loadTrend = async () => {
    try {
      const sessions = await api.getSessions();
      const list = Array.isArray(sessions) ? sessions : (sessions as any).sessions || [];
      const withDisk = list
        .filter((s: any) => s.status === 'completed' && s.disk_used)
        .sort((a: any, b: any) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime())
        .slice(-10);

      setPoints(withDisk.map((s: any) => ({
        date: new Date(s.started_at).toLocaleDateString(),
        used: s.disk_used,
        total: s.disk_total || 0,
      })));
    } catch (e) {
      console.error('Trend load failed:', e);
    }
  };

  useEffect(() => {
    loadTrend();
    const off = on('analysis:completed', () => setTimeout(loadTrend, 1000));
    return off;
  }, []);

  if (points.length === 0) return null;

  const latest = points[points.length - 1];
  const first = points[0];
  const delta = latest.used - first.used;
  const growing = delta > 0;

  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>Disk Trend</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {points.length} scans · {first.date} → {latest.date}
          </div>
        </div>
        {points.length >= 2 && (
          <div style={{
            fontSize: '0.85rem', fontWeight: 600,
            color: growing ? 'var(--danger)' : 'var(--success)',
          }}>
            {growing ? '\u2191' : '\u2193'} {formatBytes(Math.abs(delta))}
          </div>
        )}
      </div>
      {/* Simple bar visualization */}
      <div style={{ display: 'flex', gap: '2px', marginTop: '0.75rem', height: '40px', alignItems: 'flex-end' }}>
        {points.map((p, i) => {
          const pct = p.total > 0 ? (p.used / p.total) * 100 : 50;
          return (
            <div key={i} title={`${p.date}: ${formatBytes(p.used)}`}
              style={{
                flex: 1, borderRadius: '3px 3px 0 0',
                height: `${Math.max(pct * 0.4, 4)}px`,
                background: i === points.length - 1 ? 'var(--primary)' : 'var(--border)',
                transition: 'height 0.3s',
              }}
            />
          );
        })}
      </div>
    </div>
  );
}
