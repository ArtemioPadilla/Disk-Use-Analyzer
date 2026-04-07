import { useState, useEffect } from 'react';
import { api, type DriveInfo } from '../lib/api';
import { on, emit } from '../lib/events';
import { useAnalysis } from '../hooks/useAnalysis';

export default function NewAnalysisModal() {
  const [open, setOpen] = useState(false);
  const [drives, setDrives] = useState<DriveInfo[]>([]);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [customPath, setCustomPath] = useState('');
  const [minSize, setMinSize] = useState(10);
  const { startAnalysis } = useAnalysis();

  useEffect(() => {
    const off = on('analysis:new', () => {
      setOpen(true);
      api.getDrives().then(setDrives).catch(console.error);
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
          <label style={{ fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>Minimum file size: {minSize} MB</label>
          <input type="range" min={1} max={500} value={minSize} onChange={e => setMinSize(Number(e.target.value))} style={{ width: '100%' }} />
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
          <button className="btn btn-primary" onClick={submit} disabled={selectedPaths.length === 0}>Start Analysis</button>
        </div>
      </div>
    </div>
  );
}
