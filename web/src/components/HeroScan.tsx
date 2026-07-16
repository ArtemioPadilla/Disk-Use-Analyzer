import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { on, emit } from '../lib/events';

export default function HeroScan() {
  const [hasResults, setHasResults] = useState<boolean | null>(null);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    // Check if there are any completed results
    fetch('/api/analysis/latest').then(r => {
      if (r.ok) {
        r.json().then(data => {
          setHasResults(true);
          // Broadcast so other components load the data
          emit('analysis:completed', data);
        });
      } else {
        setHasResults(false);
      }
    }).catch(() => setHasResults(false));

    const offs = [
      on('analysis:started', () => setScanning(true)),
      on('analysis:completed', () => { setHasResults(true); setScanning(false); }),
      on('analysis:error', () => setScanning(false)),
    ];
    return () => offs.forEach(off => off());
  }, []);

  if (hasResults === null) return null; // loading
  if (hasResults) return null; // results exist, dashboard components handle it

  const startQuickScan = async () => {
    const info = await api.getSystemInfo();
    const minSize = Number(localStorage.getItem('disk-analyzer-min-size') ?? info.default_min_size_mb ?? 10);
    // Use ~ expansion - the backend handles it
    emit('analysis:start-request', { paths: ['~'], minSizeMb: minSize });
  };

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      minHeight: '60vh', textAlign: 'center', padding: '2rem',
    }}>
      <div style={{ fontSize: '4rem', marginBottom: '1rem' }}>&#x1F4BF;</div>
      <h2 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '0.5rem' }}>
        {scanning ? 'Scanning your Mac...' : 'Analyze Your Disk'}
      </h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: '2rem', maxWidth: '400px' }}>
        {scanning
          ? 'This may take a few minutes. You can watch progress above.'
          : "Find out what's eating your disk space. One click to scan your home directory."}
      </p>
      {!scanning && (
        <>
          <button className="btn btn-primary" onClick={startQuickScan}
            style={{ fontSize: '1.1rem', padding: '0.75rem 2rem', borderRadius: '12px' }}>
            Scan My Mac
          </button>
          <button className="btn btn-ghost" onClick={() => emit('analysis:new')}
            style={{ marginTop: '0.75rem', fontSize: '0.85rem' }}>
            Advanced options...
          </button>
        </>
      )}
      {scanning && (
        <div style={{
          width: 40, height: 40, border: '3px solid var(--border)',
          borderTopColor: 'var(--primary)', borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }} />
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
