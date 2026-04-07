import { useState, useEffect, useRef } from 'react';
import { api } from '../lib/api';
import { formatBytes } from '../lib/format';

export default function LivePulse() {
  const [used, setUsed] = useState<number | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [delta, setDelta] = useState<number>(0);
  const [active, setActive] = useState(false);
  const prevUsed = useRef<number | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const poll = async () => {
    try {
      const info = await api.getSystemInfo();
      const newUsed = info.disk_usage.used;
      setTotal(info.disk_usage.total);

      if (prevUsed.current !== null) {
        const d = newUsed - prevUsed.current;
        if (d !== 0) setDelta(d);
      }

      prevUsed.current = newUsed;
      setUsed(newUsed);
    } catch {}
  };

  const toggleMonitor = () => {
    if (active) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = null;
      setActive(false);
    } else {
      poll();
      intervalRef.current = setInterval(poll, 5000);
      setActive(true);
    }
  };

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const pct = used !== null && total ? ((used / total) * 100).toFixed(1) : '—';

  return (
    <div className="card" style={{ marginBottom: '0.75rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: active ? '0.5rem' : 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '1rem' }}>💿</span>
          <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Live Monitor</span>
          {active && (
            <span style={{
              width: 8, height: 8, borderRadius: '50%', background: '#10b981',
              display: 'inline-block', animation: 'pulse 1.5s infinite',
            }} />
          )}
        </div>
        <button className="btn btn-ghost" onClick={toggleMonitor}
          style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}>
          {active ? 'Stop' : 'Start'}
        </button>
      </div>

      {active && used !== null && (
        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginBottom: '0.4rem' }}>
            <span style={{ fontSize: '1.4rem', fontWeight: 700 }}>{formatBytes(used)}</span>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>used ({pct}%)</span>
            {delta !== 0 && (
              <span style={{
                fontSize: '0.75rem', fontWeight: 600,
                color: delta > 0 ? 'var(--danger)' : 'var(--success)',
                animation: 'fadeSlideUp 0.3s ease',
              }}>
                {delta > 0 ? '↑' : '↓'} {formatBytes(Math.abs(delta))}
              </span>
            )}
          </div>
          <div style={{ height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 3, transition: 'width 0.5s',
              width: `${pct}%`,
              background: Number(pct) > 90 ? 'var(--danger)' : Number(pct) > 75 ? 'var(--warning)' : 'var(--primary)',
            }} />
          </div>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '0.3rem' }}>
            Polling every 5s · {total ? `${formatBytes(total - used)} free` : ''}
          </div>
        </div>
      )}
      <style>{`
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
        @keyframes fadeSlideUp { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }
      `}</style>
    </div>
  );
}
