import { useState, useEffect } from 'react';
import { on } from '../lib/events';
import { formatBytes } from '../lib/format';

interface Toast {
  id: number;
  message: string;
  type: 'success' | 'error' | 'info';
}

let nextId = 0;

export default function ToastNotification() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const offs = [
      on('cleanup:completed', (data: any) => {
        const id = nextId++;
        setToasts(prev => [...prev, {
          id,
          message: `Cleaned: ${data.command?.split(' ').slice(0, 3).join(' ') || 'files'}${data.space ? ` \u00b7 ~${formatBytes(data.space)} freed` : ''}`,
          type: 'success',
        }]);
        setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000);
      }),
      on('analysis:completed', (data: any) => {
        const total = data.results?.[0]?.report?.summary?.recoverable_space;
        if (total) {
          const id = nextId++;
          setToasts(prev => [...prev, {
            id,
            message: `Analysis complete! ${formatBytes(total)} recoverable space found.`,
            type: 'info',
          }]);
          setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 5000);
        }
      }),
    ];
    return () => offs.forEach(off => off());
  }, []);

  if (toasts.length === 0) return null;

  const colors = { success: 'var(--success)', error: 'var(--danger)', info: 'var(--primary)' };

  return (
    <div style={{
      position: 'fixed', bottom: '1.5rem', right: '1.5rem', zIndex: 9998,
      display: 'flex', flexDirection: 'column', gap: '0.5rem',
    }}>
      {toasts.map(toast => (
        <div key={toast.id} style={{
          background: 'var(--card-bg)', border: `1px solid ${colors[toast.type]}`,
          borderLeft: `4px solid ${colors[toast.type]}`,
          borderRadius: '8px', padding: '0.75rem 1rem',
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          fontSize: '0.85rem', maxWidth: '350px',
          animation: 'slideIn 0.3s ease',
        }}>
          {toast.message}
        </div>
      ))}
      <style>{`@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }`}</style>
    </div>
  );
}
