import { useState, useEffect } from 'react';
import { on } from '../lib/events';
import { formatBytes } from '../lib/format';
import type { SessionResults } from '../lib/api';

export default function NarrativeSummary() {
  const [summary, setSummary] = useState<any>(null);
  const [topItems, setTopItems] = useState<{name: string; size: number}[]>([]);

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      const report = data.results?.[0]?.report;
      if (!report) return;
      setSummary(report.summary);

      // Find top 3 space consumers from recommendations + cache locations
      const items: {name: string; size: number}[] = [];

      // From cache locations
      (report.cache_locations || []).forEach((c: any) => {
        items.push({ name: c.type || c.path.split('/').pop() || c.path, size: c.size });
      });

      // From top directories (use last path segment as name)
      (report.top_directories || []).slice(0, 5).forEach(([path, size]: [string, number]) => {
        const name = path.split('/').filter(Boolean).pop() || path;
        if (!items.find(i => i.name === name)) {
          items.push({ name, size });
        }
      });

      items.sort((a, b) => b.size - a.size);
      setTopItems(items.slice(0, 3));
    });
    return off;
  }, []);

  if (!summary) return null;

  const usedPct = summary.disk_usage
    ? ((summary.disk_usage.used / summary.disk_usage.total) * 100).toFixed(0)
    : null;

  const urgency = Number(usedPct) > 90 ? 'critical' : Number(usedPct) > 75 ? 'warning' : 'healthy';
  const urgencyColors = {
    critical: { bg: 'linear-gradient(135deg, #ef4444, #dc2626)', icon: '🔴' },
    warning: { bg: 'linear-gradient(135deg, #f59e0b, #d97706)', icon: '🟡' },
    healthy: { bg: 'linear-gradient(135deg, #10b981, #059669)', icon: '🟢' },
  };
  const style = urgencyColors[urgency];

  return (
    <div style={{
      background: style.bg, color: 'white', borderRadius: '12px',
      padding: '1.25rem 1.5rem', marginBottom: '1rem',
    }}>
      <div style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
        {style.icon} {usedPct
          ? `Your disk is ${usedPct}% full.`
          : `${formatBytes(summary.total_size)} analyzed.`
        }
        {summary.recoverable_space > 0 && (
          <span> {formatBytes(summary.recoverable_space)} can be recovered.</span>
        )}
      </div>

      {topItems.length > 0 && (
        <div style={{ fontSize: '0.9rem', opacity: 0.95 }}>
          Biggest offenders: {topItems.map((item, i) => (
            <span key={i}>
              {i > 0 && (i === topItems.length - 1 ? ', and ' : ', ')}
              <strong>{item.name}</strong> ({formatBytes(item.size)})
            </span>
          ))}.
        </div>
      )}

      {summary.files_scanned > 0 && (
        <div style={{ fontSize: '0.75rem', opacity: 0.7, marginTop: '0.4rem' }}>
          {summary.files_scanned.toLocaleString()} files scanned
          {summary.cache_size > 0 && ` · ${formatBytes(summary.cache_size)} in caches`}
          {summary.docker_space > 0 && ` · ${formatBytes(summary.docker_space)} Docker`}
        </div>
      )}
    </div>
  );
}
