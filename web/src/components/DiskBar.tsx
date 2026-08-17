import { useState, useEffect } from 'react';
import { on } from '../lib/events';
import { formatBytes } from '../lib/format';
import { api } from '../lib/api';
import type { SessionResults } from '../lib/api';
import { getCategory, CATEGORY_COLORS } from '../lib/categories';

export default function DiskBar() {
  const [segments, setSegments] = useState<{category: string; size: number; pct: number}[]>([]);
  const [diskTotal, setDiskTotal] = useState(0);
  const [diskUsed, setDiskUsed] = useState(0);
  const [diskFree, setDiskFree] = useState(0);

  useEffect(() => {
    // Get disk info immediately
    api.getSystemInfo().then(info => {
      setDiskTotal(info.disk_usage.total);
      setDiskUsed(info.disk_usage.used);
      setDiskFree(info.disk_usage.free);
    }).catch(console.error);

    const off = on('analysis:completed', (data: SessionResults) => {
      const report = data.results?.[0]?.report;
      if (!report) return;

      const total = report.summary?.disk_usage?.total || 1;
      setDiskTotal(total);
      setDiskUsed(report.summary?.disk_usage?.used || 0);
      setDiskFree(report.summary?.disk_usage?.free || 0);

      // Categorize top directories
      const categoryTotals: Record<string, number> = {};
      (report.top_directories || []).forEach(([path, size]: [string, number]) => {
        const cat = getCategory(path);
        categoryTotals[cat] = (categoryTotals[cat] || 0) + size;
      });

      const segs = Object.entries(categoryTotals)
        .map(([category, size]) => ({
          category,
          size,
          pct: Math.min((size / total) * 100, 100),
        }))
        .filter(s => s.pct >= 0.5) // hide tiny segments
        .sort((a, b) => b.size - a.size);

      setSegments(segs);
    });

    const offCleanup = on('cleanup:completed', () => {
      api.getSystemInfo().then(info => {
        setDiskTotal(info.disk_usage.total);
        setDiskUsed(info.disk_usage.used);
        setDiskFree(info.disk_usage.free);
      }).catch(console.error);
    });

    return () => { off(); offCleanup(); };
  }, []);

  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Storage</span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          {formatBytes(diskUsed)} used of {formatBytes(diskTotal)}
          {diskFree > 0 && ` · ${formatBytes(diskFree)} free`}
        </span>
      </div>

      {/* Bar */}
      <div style={{
        height: 24, borderRadius: 6, overflow: 'hidden',
        display: 'flex', background: 'var(--border)',
      }}>
        {segments.length > 0 ? (
          segments.map((seg) => (
            <div key={seg.category} title={`${seg.category}: ${formatBytes(seg.size)}`}
              style={{
                width: `${seg.pct}%`,
                background: CATEGORY_COLORS[seg.category] || '#6b7280',
                transition: 'width 0.5s ease',
                minWidth: seg.pct > 0 ? 2 : 0,
              }}
            />
          ))
        ) : (
          <div style={{
            width: `${diskTotal > 0 ? (diskUsed / diskTotal) * 100 : 0}%`,
            background: 'var(--primary)',
            transition: 'width 0.5s ease',
          }} />
        )}
      </div>

      {/* Legend */}
      {segments.length > 0 && (
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: '0.5rem 1rem',
          marginTop: '0.5rem', fontSize: '0.7rem',
        }}>
          {segments.map(seg => (
            <div key={seg.category} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <div style={{
                width: 8, height: 8, borderRadius: 2,
                background: CATEGORY_COLORS[seg.category] || '#6b7280',
              }} />
              <span style={{ color: 'var(--text-muted)' }}>{seg.category}</span>
              <span style={{ fontWeight: 500 }}>{formatBytes(seg.size)}</span>
            </div>
          ))}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <div style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--border)' }} />
            <span style={{ color: 'var(--text-muted)' }}>Free</span>
            <span style={{ fontWeight: 500 }}>{formatBytes(diskFree)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
