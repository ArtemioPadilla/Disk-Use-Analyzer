import { useEffect, useState } from 'react';
import { emit } from '../lib/events';

export default function KeyboardShortcuts() {
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't trigger in inputs/textareas
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      // Ctrl/Cmd + key shortcuts
      if (e.metaKey || e.ctrlKey) {
        switch (e.key) {
          case 'n': e.preventDefault(); emit('analysis:new'); break;
          case 't': e.preventDefault(); emit('terminal:toggle'); break;
          case 'k': e.preventDefault(); document.getElementById('globalSearch')?.focus(); break;
        }
        return;
      }

      // Number keys for navigation (no modifier)
      switch (e.key) {
        case '1': window.location.href = '/'; break;
        case '2': window.location.href = '/files'; break;
        case '3': window.location.href = '/cleanup'; break;
        case '4': window.location.href = '/export'; break;
        case '5': window.location.href = '/history'; break;
        case '?': setShowHelp(prev => !prev); break;
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  if (!showHelp) return null;

  const shortcuts = [
    { keys: '1-5', desc: 'Navigate pages' },
    { keys: 'Ctrl+N', desc: 'New analysis' },
    { keys: 'Ctrl+T', desc: 'Toggle terminal' },
    { keys: 'Ctrl+K', desc: 'Focus search' },
    { keys: '?', desc: 'Toggle this help' },
  ];

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10001,
    }} onClick={() => setShowHelp(false)}>
      <div className="card" style={{ width: 320 }} onClick={e => e.stopPropagation()}>
        <h3 style={{ marginBottom: '0.75rem' }}>Keyboard Shortcuts</h3>
        {shortcuts.map(s => (
          <div key={s.keys} style={{
            display: 'flex', justifyContent: 'space-between', padding: '0.4rem 0',
            borderBottom: '1px solid var(--border)', fontSize: '0.85rem',
          }}>
            <kbd style={{
              background: 'var(--page-bg)', padding: '0.15rem 0.5rem',
              borderRadius: '4px', fontFamily: 'monospace', fontSize: '0.8rem',
            }}>{s.keys}</kbd>
            <span style={{ color: 'var(--text-muted)' }}>{s.desc}</span>
          </div>
        ))}
        <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center' }}>
          Press ? to close
        </div>
      </div>
    </div>
  );
}
