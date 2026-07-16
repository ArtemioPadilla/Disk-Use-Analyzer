import { useState, useEffect } from 'react';
import { on } from '../lib/events';
import { formatBytes } from '../lib/format';

interface SavingsData {
  lifetime: number;
  thisWeek: number;
  thisMonth: number;
  cleanupCount: number;
  weekStart: string;
  monthStart: string;
}

function loadSavings(): SavingsData {
  try {
    const raw = localStorage.getItem('disk-analyzer-savings');
    if (raw) {
      const data = JSON.parse(raw);
      const now = new Date();
      const weekStart = new Date(now); weekStart.setDate(now.getDate() - now.getDay());
      const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);

      // Reset weekly/monthly if period changed
      if (data.weekStart !== weekStart.toISOString().slice(0, 10)) {
        data.thisWeek = 0;
        data.weekStart = weekStart.toISOString().slice(0, 10);
      }
      if (data.monthStart !== monthStart.toISOString().slice(0, 7)) {
        data.thisMonth = 0;
        data.monthStart = monthStart.toISOString().slice(0, 7);
      }
      return data;
    }
  } catch {}
  const now = new Date();
  return {
    lifetime: 0, thisWeek: 0, thisMonth: 0, cleanupCount: 0,
    weekStart: new Date(now.getFullYear(), now.getMonth(), now.getDate() - now.getDay()).toISOString().slice(0, 10),
    monthStart: now.toISOString().slice(0, 7),
  };
}

function saveSavings(data: SavingsData) {
  localStorage.setItem('disk-analyzer-savings', JSON.stringify(data));
}

export default function SavingsTracker() {
  const [savings, setSavings] = useState<SavingsData>(loadSavings);

  useEffect(() => {
    const off = on('cleanup:completed', (data: any) => {
      const freed = data.space || 0;
      if (freed <= 0) return;

      setSavings(prev => {
        const updated = {
          ...prev,
          lifetime: prev.lifetime + freed,
          thisWeek: prev.thisWeek + freed,
          thisMonth: prev.thisMonth + freed,
          cleanupCount: prev.cleanupCount + 1,
        };
        saveSavings(updated);
        return updated;
      });
    });
    return off;
  }, []);

  if (savings.lifetime === 0) return null;

  return (
    <div className="card" style={{ marginBottom: '0.75rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
        <span style={{ fontSize: '1.2rem' }}>🏆</span>
        <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Space Savings</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.5rem', textAlign: 'center' }}>
        <div style={{ background: 'var(--page-bg)', borderRadius: '8px', padding: '0.5rem' }}>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--success)' }}>{formatBytes(savings.lifetime)}</div>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Lifetime</div>
        </div>
        <div style={{ background: 'var(--page-bg)', borderRadius: '8px', padding: '0.5rem' }}>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--primary)' }}>{formatBytes(savings.thisMonth)}</div>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>This month</div>
        </div>
        <div style={{ background: 'var(--page-bg)', borderRadius: '8px', padding: '0.5rem' }}>
          <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>{savings.cleanupCount}</div>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Cleanups</div>
        </div>
      </div>
    </div>
  );
}
