import { useEffect, useRef, useState } from 'react';
import { on } from '../lib/events';
import { formatBytes } from '../lib/format';
import type { SessionResults } from '../lib/api';

export default function CategoryChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [results, setResults] = useState<SessionResults | null>(null);

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => setResults(data));
    return off;
  }, []);

  useEffect(() => {
    if (!results || !containerRef.current) return;
    const report = results.results[0]?.report;
    if (!report) return;

    const dirs = report.top_directories.slice(0, 15);
    const labels = dirs.map(([path]) => {
      const parts = path.split('/');
      return parts[parts.length - 1] || path;
    });
    const parents = dirs.map(() => '');
    const values = dirs.map(([, size]) => size);
    const text = dirs.map(([path, size]) => `${path}<br>${formatBytes(size)}`);

    import('plotly.js-dist-min').then((Plotly) => {
      Plotly.newPlot(containerRef.current!, [{
        type: 'treemap',
        labels, parents, values, text,
        hoverinfo: 'text',
        textinfo: 'label+percent root',
        marker: {
          colors: values.map((_, i) => {
            const palette = ['#6366f1','#8b5cf6','#a78bfa','#c4b5fd','#10b981','#34d399','#6ee7b7','#f59e0b','#fbbf24','#fcd34d','#ef4444','#f87171','#fca5a5','#3b82f6','#60a5fa'];
            return palette[i % palette.length];
          }),
        },
      }], {
        margin: { t: 10, b: 10, l: 10, r: 10 },
        height: 300,
        paper_bgcolor: 'transparent',
      }, { responsive: true, displayModeBar: false });
    });
  }, [results]);

  return (
    <div className="card" style={{ flex: 2 }}>
      <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Category Breakdown</div>
      {!results ? (
        <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
          Run an analysis to see results
        </div>
      ) : (
        <div ref={containerRef} />
      )}
    </div>
  );
}
