import { useEffect, useRef, useState } from 'react';
import { on } from '../lib/events';
import { formatBytes } from '../lib/format';
import type { SessionResults } from '../lib/api';

interface DirEntry {
  path: string;
  size: number;
  name: string;
}

export default function CategoryChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [results, setResults] = useState<SessionResults | null>(null);
  const [allDirs, setAllDirs] = useState<[string, number][]>([]);
  const [breadcrumb, setBreadcrumb] = useState<string[]>([]);
  const plotlyRef = useRef<any>(null);

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      setResults(data);
      const dirs = data.results?.[0]?.report?.top_directories || [];
      setAllDirs(dirs);
      setBreadcrumb([]);
    });
    return off;
  }, []);

  // Get entries for current breadcrumb level
  const getEntries = (): DirEntry[] => {
    if (allDirs.length === 0) return [];

    const currentPath = breadcrumb.length > 0 ? breadcrumb[breadcrumb.length - 1] : null;

    let entries: DirEntry[];
    if (!currentPath) {
      // Root level: show top directories
      entries = allDirs.slice(0, 20).map(([path, size]) => ({
        path,
        size,
        name: path.split('/').filter(Boolean).pop() || path,
      }));
    } else {
      // Filter to children of currentPath
      const prefix = currentPath.endsWith('/') ? currentPath : currentPath + '/';
      entries = allDirs
        .filter(([p]) => p.startsWith(prefix) && p !== currentPath)
        .map(([path, size]) => {
          // Get the immediate child name
          const rest = path.slice(prefix.length);
          const childName = rest.split('/')[0];
          const childPath = prefix + childName;
          return { path: childPath, size, name: childName };
        })
        // Deduplicate by path (aggregate sizes for same immediate child)
        .reduce((acc, entry) => {
          const existing = acc.find(e => e.path === entry.path);
          if (existing) {
            existing.size = Math.max(existing.size, entry.size);
          } else {
            acc.push({ ...entry });
          }
          return acc;
        }, [] as DirEntry[])
        .sort((a, b) => b.size - a.size)
        .slice(0, 20);
    }

    return entries;
  };

  // Render treemap
  useEffect(() => {
    if (!containerRef.current) return;

    const entries = getEntries();
    if (entries.length === 0) return;

    const labels = entries.map(e => e.name);
    const parents = entries.map(() => '');
    const values = entries.map(e => e.size);
    const ids = entries.map(e => e.path);
    const text = entries.map(e => `${e.name}<br>${formatBytes(e.size)}`);

    const palette = ['#6366f1','#8b5cf6','#a78bfa','#c4b5fd','#10b981','#34d399','#6ee7b7','#f59e0b','#fbbf24','#fcd34d','#ef4444','#f87171','#fca5a5','#3b82f6','#60a5fa','#818cf8','#a5b4fc','#e879f9','#f472b6','#fb923c'];

    import('plotly.js-dist-min').then((Plotly) => {
      plotlyRef.current = Plotly;

      Plotly.newPlot(containerRef.current!, [{
        type: 'treemap',
        labels,
        parents,
        values,
        ids,
        text,
        hoverinfo: 'text',
        textinfo: 'label+percent root',
        marker: {
          colors: values.map((_, i) => palette[i % palette.length]),
        },
        pathbar: { visible: false },
      }], {
        margin: { t: 5, b: 5, l: 5, r: 5 },
        height: 320,
        paper_bgcolor: 'transparent',
      }, { responsive: true, displayModeBar: false });

      // Click handler for drill-down
      (containerRef.current as any).on('plotly_click', (data: any) => {
        const point = data.points?.[0];
        if (point?.id) {
          // Check if this path has children in our data
          const prefix = point.id.endsWith('/') ? point.id : point.id + '/';
          const hasChildren = allDirs.some(([p]) => p.startsWith(prefix) && p !== point.id);
          if (hasChildren) {
            setBreadcrumb(prev => [...prev, point.id]);
          }
        }
      });
    });

    return () => {
      if (containerRef.current && plotlyRef.current) {
        plotlyRef.current.purge(containerRef.current);
      }
    };
  }, [results, breadcrumb, allDirs]);

  const navigateTo = (index: number) => {
    if (index < 0) {
      setBreadcrumb([]);
    } else {
      setBreadcrumb(prev => prev.slice(0, index + 1));
    }
  };

  if (!results) {
    return (
      <div className="card" style={{ flex: 2 }}>
        <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Category Breakdown</div>
        <div style={{ height: 320, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
          Run an analysis to see results
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ flex: 2 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
        <div style={{ fontWeight: 600 }}>Category Breakdown</div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Click to drill down</div>
      </div>

      {/* Breadcrumb */}
      {breadcrumb.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '0.25rem',
          fontSize: '0.75rem', marginBottom: '0.5rem', flexWrap: 'wrap',
          color: 'var(--text-muted)',
        }}>
          <span onClick={() => navigateTo(-1)} style={{ cursor: 'pointer', color: 'var(--primary)' }}>
            Root
          </span>
          {breadcrumb.map((path, i) => (
            <span key={path}>
              <span style={{ margin: '0 0.2rem' }}>/</span>
              <span
                onClick={() => navigateTo(i)}
                style={{
                  cursor: i < breadcrumb.length - 1 ? 'pointer' : 'default',
                  color: i < breadcrumb.length - 1 ? 'var(--primary)' : 'var(--text)',
                  fontWeight: i === breadcrumb.length - 1 ? 600 : 400,
                }}
              >
                {path.split('/').filter(Boolean).pop()}
              </span>
            </span>
          ))}
        </div>
      )}

      <div ref={containerRef} />
    </div>
  );
}
