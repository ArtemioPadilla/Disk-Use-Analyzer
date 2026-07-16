import { useState, useEffect } from 'react';
import { formatBytes } from '../lib/format';

interface Digest {
  generated_at: string;
  scans_this_week: number;
  total_scans: number;
  disk: { used: number; total: number; free: number; percent: number };
  growth: { bytes: number; direction: string; days_until_full: number | null };
  agents_log: string[];
}

export default function WeeklyDigest() {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/digest')
      .then(r => r.json())
      .then(setDigest)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>Loading digest...</div>;
  if (!digest) return <div className="card" style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>Could not generate digest.</div>;

  const growing = digest.growth.direction === 'up';
  const shrinking = digest.growth.direction === 'down';

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
        color: 'white', borderRadius: '12px', padding: '1.5rem', marginBottom: '1rem',
        textAlign: 'center',
      }}>
        <div style={{ fontSize: '0.8rem', opacity: 0.8, marginBottom: '0.5rem' }}>Weekly Disk Report</div>
        <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{digest.disk.percent}% used</div>
        <div style={{ fontSize: '0.9rem', opacity: 0.9 }}>
          {formatBytes(digest.disk.used)} of {formatBytes(digest.disk.total)}
          {' '}&middot; {formatBytes(digest.disk.free)} free
        </div>
      </div>

      {/* Growth */}
      <div className="card" style={{ marginBottom: '0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span style={{ fontSize: '1.5rem' }}>{growing ? '\u{1F4C8}' : shrinking ? '\u{1F4C9}' : '\u27A1\uFE0F'}</span>
          <div>
            <div style={{ fontWeight: 600 }}>
              {growing && `Disk grew by ${formatBytes(digest.growth.bytes)}`}
              {shrinking && `Disk shrank by ${formatBytes(Math.abs(digest.growth.bytes))}`}
              {!growing && !shrinking && 'Disk usage is stable'}
            </div>
            {digest.growth.days_until_full && (
              <div style={{
                fontSize: '0.8rem',
                color: digest.growth.days_until_full < 30 ? 'var(--danger)' : digest.growth.days_until_full < 90 ? 'var(--warning)' : 'var(--text-muted)',
              }}>
                At this rate, disk will be full in ~{digest.growth.days_until_full} days
                {digest.growth.days_until_full < 30 && ' \u26A0\uFE0F'}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Activity */}
      <div className="card" style={{ marginBottom: '0.75rem' }}>
        <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Activity</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
          <div style={{ background: 'var(--page-bg)', borderRadius: '8px', padding: '0.6rem', textAlign: 'center' }}>
            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--primary)' }}>{digest.scans_this_week}</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Scans this week</div>
          </div>
          <div style={{ background: 'var(--page-bg)', borderRadius: '8px', padding: '0.6rem', textAlign: 'center' }}>
            <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>{digest.total_scans}</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Total scans</div>
          </div>
        </div>
      </div>

      {/* Agent log */}
      {digest.agents_log.length > 0 && (
        <div className="card" style={{ marginBottom: '0.75rem' }}>
          <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Agent Activity</div>
          <div style={{ maxHeight: 150, overflowY: 'auto', fontSize: '0.75rem', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
            {digest.agents_log.map((line, i) => (
              <div key={i} style={{ padding: '0.15rem 0' }}>{line}</div>
            ))}
          </div>
        </div>
      )}

      {/* Recommendation */}
      <div className="card" style={{ background: 'var(--page-bg)', textAlign: 'center' }}>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
          {digest.disk.percent > 85
            ? 'Your disk is getting full. Consider running a cleanup.'
            : 'Your disk is looking healthy. Keep it up!'}
        </div>
        <a href="/cleanup" className="btn btn-primary" style={{ textDecoration: 'none' }}>
          {digest.disk.percent > 85 ? 'Run Cleanup' : 'View Cleanup Options'}
        </a>
      </div>
    </div>
  );
}
