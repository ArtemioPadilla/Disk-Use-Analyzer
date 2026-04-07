import { useState, useEffect } from 'react';
import { on } from '../lib/events';

export default function ProgressBar() {
  const [active, setActive] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [filesScanned, setFilesScanned] = useState(0);
  const [startTime, setStartTime] = useState<number | null>(null);
  const [eta, setEta] = useState<string>('');

  useEffect(() => {
    const offs = [
      on('analysis:started', () => {
        setActive(true);
        setProgress(0);
        setMessage('Starting analysis...');
        setFilesScanned(0);
        setStartTime(Date.now());
        setEta('');
      }),
      on('analysis:progress', (data: any) => {
        if (data.progress !== undefined) {
          setProgress(data.progress);
          // Calculate ETA once we have enough progress data
          if (data.progress > 5) {
            setStartTime(prev => {
              if (prev) {
                const elapsed = (Date.now() - prev) / 1000;
                const rate = data.progress / elapsed;
                const remaining = (100 - data.progress) / rate;
                if (remaining < 60) setEta(`~${Math.ceil(remaining)}s remaining`);
                else if (remaining < 3600) setEta(`~${Math.ceil(remaining / 60)}min remaining`);
                else setEta(`~${(remaining / 3600).toFixed(1)}h remaining`);
              }
              return prev;
            });
          }
        }
        if (data.current_path) setMessage(data.current_path);
        if (data.files_scanned) setFilesScanned(data.files_scanned);
      }),
      on('analysis:completed', () => {
        setProgress(100);
        setMessage('Analysis complete!');
        setEta('');
        setTimeout(() => setActive(false), 2000);
      }),
      on('analysis:error', () => {
        setMessage('Analysis failed');
        setEta('');
        setTimeout(() => setActive(false), 3000);
      }),
    ];
    return () => offs.forEach(off => off());
  }, []);

  if (!active) return null;

  return (
    <div style={{
      background: 'var(--card-bg)', borderBottom: '1px solid var(--border)',
      padding: '0.5rem 1.5rem', flexShrink: 0,
    }}>
      {/* Progress bar track */}
      <div style={{
        height: 6, background: 'var(--border)', borderRadius: 3,
        overflow: 'hidden', marginBottom: '0.4rem',
      }}>
        <div style={{
          height: '100%', borderRadius: 3,
          width: `${Math.max(progress, 2)}%`,
          background: progress >= 100
            ? 'var(--success)'
            : 'linear-gradient(90deg, var(--primary), var(--secondary))',
          transition: 'width 0.3s ease',
        }} />
      </div>
      {/* Info line */}
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        fontSize: '0.75rem', color: 'var(--text-muted)',
      }}>
        <span style={{
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          maxWidth: '60%',
        }}>
          {message}
        </span>
        <span>
          {progress.toFixed(0)}% &middot; {filesScanned.toLocaleString()} files{eta && ` \u00b7 ${eta}`}
        </span>
      </div>
    </div>
  );
}
