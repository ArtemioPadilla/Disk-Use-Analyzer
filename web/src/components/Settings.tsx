import { useState, useEffect } from 'react';
import { api } from '../lib/api';

export default function Settings() {
  const [minSize, setMinSize] = useState(10);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    // Load from localStorage first, then server default
    const local = localStorage.getItem('disk-analyzer-min-size');
    if (local !== null) {
      setMinSize(Number(local));
    } else {
      api.getSystemInfo().then((info: any) => {
        if (info.default_min_size_mb !== undefined) {
          setMinSize(info.default_min_size_mb);
        }
      }).catch(console.error);
    }
  }, []);

  const save = () => {
    localStorage.setItem('disk-analyzer-min-size', String(minSize));
    // Broadcast so NewAnalysisModal picks it up
    window.dispatchEvent(new CustomEvent('settings:updated', { detail: { minSize } }));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div style={{ maxWidth: 600 }}>
      <div className="card" style={{ marginBottom: '1rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>Analysis Defaults</h3>

        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>
            Default minimum file size: {minSize} MB
            {minSize === 0 && <span style={{ color: 'var(--warning)', fontSize: '0.75rem', marginLeft: '0.5rem' }}>(all files — may be slow)</span>}
          </label>
          <input
            type="range" min={0} max={500} value={minSize}
            onChange={e => setMinSize(Number(e.target.value))}
            style={{ width: '100%' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            <span>0 MB (all files)</span>
            <span>500 MB</span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button className="btn btn-primary" onClick={save}>Save</button>
          {saved && <span style={{ color: 'var(--success)', fontSize: '0.85rem' }}>Saved!</span>}
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: '1rem' }}>CLI Override</h3>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
          You can also set the default from the command line:
        </p>
        <code style={{
          display: 'block', background: 'var(--page-bg)', padding: '0.5rem 0.75rem',
          borderRadius: '6px', fontSize: '0.8rem',
        }}>
          sudo make web min_size=0
        </code>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
          UI settings override the CLI flag. Clear browser storage to revert to CLI default.
        </p>
      </div>
    </div>
  );
}
