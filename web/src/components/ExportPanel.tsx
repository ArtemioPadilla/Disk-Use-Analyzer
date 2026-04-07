import { useState, useEffect } from 'react';
import { api, type SessionResults } from '../lib/api';
import { on } from '../lib/events';

export default function ExportPanel() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<any[]>([]);

  useEffect(() => {
    api.getSessions()
      .then((data: any) => {
        const list = Array.isArray(data) ? data : data.sessions ?? [];
        setSessions(list);
      })
      .catch(console.error);

    const off = on('analysis:completed', (data: SessionResults) => {
      setSessionId(data.id);
      api.getSessions()
        .then((d: any) => {
          const list = Array.isArray(d) ? d : d.sessions ?? [];
          setSessions(list);
        })
        .catch(console.error);
    });
    return off;
  }, []);

  const download = (format: 'html' | 'json' | 'csv') => {
    if (!sessionId) return;
    window.open(api.getExportUrl(sessionId, format), '_blank');
  };

  const formats = [
    { id: 'html' as const, icon: '\u{1F310}', title: 'Standalone HTML Report', desc: 'Self-contained interactive report with charts. Opens offline in any browser.' },
    { id: 'json' as const, icon: '\u{1F4CB}', title: 'JSON Data', desc: 'Raw analysis data for scripting or further processing.' },
    { id: 'csv' as const, icon: '\u{1F4CA}', title: 'CSV Spreadsheet', desc: 'Top files exported for use in Excel or Google Sheets.' },
  ];

  return (
    <div>
      <div className="card" style={{ marginBottom: '1rem' }}>
        <label style={{ fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>Select Session</label>
        <select value={sessionId || ''} onChange={e => setSessionId(e.target.value || null)}
          style={{ width: '100%', padding: '0.5rem', borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text)' }}>
          <option value="">— Select an analysis session —</option>
          {sessions.filter(s => s.status === 'completed').map(s => (
            <option key={s.id} value={s.id}>{s.paths?.join(', ') || s.id} — {new Date(s.started_at).toLocaleString()}</option>
          ))}
        </select>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.75rem' }}>
        {formats.map(f => (
          <div key={f.id} className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>{f.icon}</div>
            <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{f.title}</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', flex: 1, marginBottom: '0.75rem' }}>{f.desc}</div>
            <button className="btn btn-primary" onClick={() => download(f.id)} disabled={!sessionId} style={{ alignSelf: 'flex-start' }}>
              Download {f.id.toUpperCase()}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
