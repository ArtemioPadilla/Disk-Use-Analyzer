import { useState, useEffect, useRef } from 'react';
import { api, type DriveInfo } from '../lib/api';
import { on, emit } from '../lib/events';
import { useAnalysis } from '../hooks/useAnalysis';

export default function NewAnalysisModal() {
  const [open, setOpen] = useState(false);
  const [drives, setDrives] = useState<DriveInfo[]>([]);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [customPath, setCustomPath] = useState('');
  const [minSize, setMinSize] = useState(10);
  const defaultLoaded = useRef(false);
  const { startAnalysis } = useAnalysis();

  // Load min_size: localStorage (UI setting) > server CLI flag > 10
  useEffect(() => {
    if (!defaultLoaded.current) {
      const local = localStorage.getItem('disk-analyzer-min-size');
      if (local !== null) {
        setMinSize(Number(local));
        defaultLoaded.current = true;
      } else {
        api.getSystemInfo().then((info: any) => {
          if (info.default_min_size_mb !== undefined) {
            setMinSize(info.default_min_size_mb);
          }
          defaultLoaded.current = true;
        }).catch(console.error);
      }
    }

    // Listen for settings changes
    const off = on('settings:updated', (data: any) => {
      if (data?.minSize !== undefined) setMinSize(data.minSize);
    });
    return off;
  }, []);

  useEffect(() => {
    const off = on('analysis:new', () => {
      setOpen(true);
      api.getDrives().then((data: any) => {
        const driveItems = (data.drives || []).map((d: any) => ({ path: d.path, label: d.path }));
        const commonItems = (data.common_paths || []).map((d: any) => ({ path: d.path, label: d.name || d.path }));
        setDrives([...driveItems, ...commonItems]);
      }).catch(console.error);
    });
    return off;
  }, []);

  const togglePath = (path: string) => {
    setSelectedPaths(prev => prev.includes(path) ? prev.filter(p => p !== path) : [...prev, path]);
  };

  const addCustomPath = () => {
    if (customPath && !selectedPaths.includes(customPath)) {
      setSelectedPaths(prev => [...prev, customPath]);
      setCustomPath('');
    }
  };

  const submit = async () => {
    if (selectedPaths.length === 0) return;
    await startAnalysis(selectedPaths, minSize);
    setOpen(false);
    setSelectedPaths([]);
  };

  if (!open) return null;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 10000,
    }} onClick={() => setOpen(false)}>
      <div className="card" style={{ width: 500, maxHeight: '80vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
        <h2 style={{ marginBottom: '1rem' }}>New Analysis</h2>
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>Select paths to analyze</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {drives.map(d => (
              <button key={d.path} className={`btn ${selectedPaths.includes(d.path) ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => togglePath(d.path)} style={{ fontSize: '0.8rem' }}>
                {d.label || d.path}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          <input type="text" placeholder="/custom/path" value={customPath}
            onChange={e => setCustomPath(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addCustomPath()}
            style={{ flex: 1, padding: '0.5rem', borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text)' }} />
          <button className="btn btn-ghost" onClick={addCustomPath}>Add</button>
        </div>
        {selectedPaths.length > 0 && (
          <div style={{ marginBottom: '1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>Selected: {selectedPaths.join(', ')}</div>
        )}
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>Minimum file size: {minSize} MB {minSize === 0 && <span style={{ color: 'var(--warning)', fontSize: '0.75rem' }}>(all files — may be slow)</span>}</label>
          <input type="range" min={0} max={500} value={minSize} onChange={e => setMinSize(Number(e.target.value))} style={{ width: '100%' }} />
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
          <button className="btn btn-primary" onClick={submit} disabled={selectedPaths.length === 0}>Start Analysis</button>
        </div>
      </div>
    </div>
  );
}
