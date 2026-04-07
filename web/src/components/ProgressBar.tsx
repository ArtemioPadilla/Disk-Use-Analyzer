import { useState, useEffect } from 'react';
import { on } from '../lib/events';

export default function ProgressBar() {
  const [active, setActive] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [filesScanned, setFilesScanned] = useState(0);

  useEffect(() => {
    const offs = [
      on('analysis:started', () => {
        setActive(true);
        setProgress(0);
        setMessage('Starting analysis...');
        setFilesScanned(0);
      }),
      on('analysis:progress', (data: any) => {
        if (data.progress !== undefined) setProgress(data.progress);
        if (data.current_path) setMessage(data.current_path);
        if (data.files_scanned) setFilesScanned(data.files_scanned);
      }),
      on('analysis:completed', () => {
        setProgress(100);
        setMessage('Analysis complete!');
        setTimeout(() => setActive(false), 2000);
      }),
      on('analysis:error', () => {
        setMessage('Analysis failed');
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
          {progress.toFixed(0)}% &middot; {filesScanned.toLocaleString()} files
        </span>
      </div>
    </div>
  );
}
