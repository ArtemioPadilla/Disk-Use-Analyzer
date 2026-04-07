import { useEffect, useRef, useState } from 'react';
import { api, type SystemInfo } from '../lib/api';
import { formatBytes } from '../lib/format';

export default function DiskDonut() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sysInfo, setSysInfo] = useState<SystemInfo | null>(null);

  useEffect(() => {
    api.getSystemInfo().then(setSysInfo).catch(console.error);
  }, []);

  useEffect(() => {
    if (!sysInfo || !containerRef.current) return;
    const { used, free } = sysInfo.disk_usage;
    import('plotly.js-dist-min').then((Plotly) => {
      Plotly.newPlot(containerRef.current!, [{
        type: 'pie', hole: 0.6,
        values: [used, free], labels: ['Used', 'Free'],
        marker: { colors: ['#6366f1', '#e5e7eb'] },
        textinfo: 'label+percent',
        hovertemplate: '%{label}: %{value}<extra></extra>',
      }], {
        margin: { t: 10, b: 10, l: 10, r: 10 },
        height: 300, showlegend: false, paper_bgcolor: 'transparent',
        annotations: [{ text: formatBytes(used), showarrow: false, font: { size: 18, color: '#6366f1' } }],
      }, { responsive: true, displayModeBar: false });
    });
  }, [sysInfo]);

  return (
    <div className="card" style={{ flex: 1 }}>
      <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Disk Usage</div>
      <div ref={containerRef} />
    </div>
  );
}
