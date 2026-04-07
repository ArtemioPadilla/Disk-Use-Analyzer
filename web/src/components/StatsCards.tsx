import { useState, useEffect } from 'react';
import { api, type SystemInfo, type SessionResults } from '../lib/api';
import { formatBytes } from '../lib/format';
import { on } from '../lib/events';

export default function StatsCards() {
  const [sysInfo, setSysInfo] = useState<SystemInfo | null>(null);
  const [results, setResults] = useState<SessionResults | null>(null);

  useEffect(() => {
    api.getSystemInfo().then(setSysInfo).catch(console.error);
    const off = on('analysis:completed', (data: SessionResults) => setResults(data));
    const offCleanup = on('cleanup:completed', () => {
      api.getSystemInfo().then(setSysInfo).catch(console.error);
    });
    return () => { off(); offCleanup(); };
  }, []);

  const disk = sysInfo?.disk_usage;
  const summary = results?.results?.[0]?.report?.summary;

  const cards = [
    {
      label: 'Total Disk Used',
      value: disk ? formatBytes(disk.used) : '—',
      sub: disk ? `of ${formatBytes(disk.total)} (${((disk.used / disk.total) * 100).toFixed(0)}%)` : '',
    },
    {
      label: 'Recoverable Space',
      value: summary ? formatBytes(summary.recoverable_space) : '—',
      sub: summary ? `${summary.large_files_count} large files found` : 'Run analysis to see',
      color: 'var(--success)',
    },
    {
      label: 'Files Scanned',
      value: summary ? summary.files_scanned.toLocaleString() : '—',
      sub: summary ? `Cache: ${formatBytes(summary.cache_size)}` : '',
    },
  ];

  return (
    <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
      {cards.map((c, i) => (
        <div key={i} className="card" style={{ flex: 1 }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>{c.label}</div>
          <div style={{ fontWeight: 700, fontSize: '1.5rem', color: c.color }}>{c.value}</div>
          {c.sub && <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{c.sub}</div>}
        </div>
      ))}
    </div>
  );
}
