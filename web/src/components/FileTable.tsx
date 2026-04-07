import { useState, useEffect, useRef, useMemo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { on, emit } from '../lib/events';
import { api, type LargeFile, type SessionResults } from '../lib/api';
import { formatBytes, formatAge } from '../lib/format';

type SortKey = 'size' | 'age_days' | 'path';
type SortDir = 'asc' | 'desc';

export default function FileTable() {
  const initialSearch = typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search).get('path') || ''
    : '';

  const [files, setFiles] = useState<LargeFile[]>([]);
  const [search, setSearch] = useState(initialSearch);
  const [sortKey, setSortKey] = useState<SortKey>('size');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<'flat' | 'grouped'>('flat');
  const parentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      const allFiles = data.results.flatMap(r => r.report.large_files);
      setFiles(allFiles);
    });
    return off;
  }, []);

  useEffect(() => {
    const off = on('navigate:files', (data: any) => {
      if (data?.path) setSearch(data.path);
    });
    return off;
  }, []);

  const filtered = useMemo(() => {
    let result = files;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(f => f.path.toLowerCase().includes(q) || f.extension.toLowerCase().includes(q));
    }
    result.sort((a, b) => {
      const mul = sortDir === 'asc' ? 1 : -1;
      if (sortKey === 'path') return mul * a.path.localeCompare(b.path);
      return mul * ((a[sortKey] as number) - (b[sortKey] as number));
    });
    return result;
  }, [files, search, sortKey, sortDir]);

  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 44,
    overscan: 20,
  });

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const toggleSelect = (path: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(path) ? next.delete(path) : next.add(path);
      return next;
    });
  };

  const deleteSelected = async () => {
    if (selected.size === 0) return;
    if (!window.confirm(`Delete ${selected.size} file(s)? They will be moved to Trash.`)) return;
    for (const path of selected) {
      try {
        await api.deleteFile(path);
        setFiles(prev => prev.filter(f => f.path !== path));
      } catch (e) {
        console.error(`Failed to delete ${path}:`, e);
      }
    }
    setSelected(new Set());
  };

  const sortIndicator = (key: SortKey) => sortKey !== key ? '' : sortDir === 'asc' ? ' ↑' : ' ↓';

  function getCategory(path: string): string {
    const p = path.toLowerCase();
    if (p.includes('node_modules') || p.includes('.npm') || p.includes('.cargo') || p.includes('.rustup') || p.includes('.gradle') || p.includes('developer/')) return 'Development';
    if (p.includes('docker') || p.includes('Docker.raw')) return 'Docker';
    if (p.includes('/caches/') || p.includes('/cache/') || p.includes('/tmp/') || p.includes('/logs/')) return 'Caches & Logs';
    if (p.includes('/library/')) return 'System Library';
    if (p.includes('/documents/') || p.includes('/desktop/') || p.includes('/downloads/')) return 'Documents';
    if (p.match(/\.(mp4|mov|avi|mkv|mp3|wav|flac|jpg|jpeg|png|gif|psd|raw)$/i)) return 'Media';
    return 'Other';
  }

  if (files.length === 0) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>📁</div>
        <div style={{ marginBottom: '0.5rem', fontWeight: 500 }}>No files to display</div>
        <p style={{ fontSize: '0.85rem', marginBottom: '1.5rem' }}>Scan your disk to get started.</p>
        <button className="btn btn-primary" onClick={() => emit('analysis:new')}>
          + New Analysis
        </button>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', alignItems: 'center' }}>
        <input type="text" placeholder="Search files..." value={search} onChange={e => setSearch(e.target.value)}
          style={{ flex: 1, padding: '0.5rem 0.75rem', border: '1px solid var(--border)', borderRadius: '8px', background: 'var(--card-bg)', color: 'var(--text)', fontSize: '0.875rem' }} />
        <div style={{ display: 'flex', gap: '2px', borderRadius: '8px', border: '1px solid var(--border)', overflow: 'hidden' }}>
          <button onClick={() => setViewMode('flat')}
            style={{ padding: '0.4rem 0.6rem', fontSize: '0.75rem', border: 'none', cursor: 'pointer',
              background: viewMode === 'flat' ? 'var(--primary)' : 'var(--card-bg)', color: viewMode === 'flat' ? 'white' : 'var(--text)' }}>
            List
          </button>
          <button onClick={() => setViewMode('grouped')}
            style={{ padding: '0.4rem 0.6rem', fontSize: '0.75rem', border: 'none', cursor: 'pointer',
              background: viewMode === 'grouped' ? 'var(--primary)' : 'var(--card-bg)', color: viewMode === 'grouped' ? 'white' : 'var(--text)' }}>
            Grouped
          </button>
        </div>
        {selected.size > 0 && (
          <button className="btn btn-primary" onClick={deleteSelected} style={{ background: 'var(--danger)' }}>
            Delete {selected.size} file(s)
          </button>
        )}
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{filtered.length.toLocaleString()} files</span>
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: '32px 1fr 100px 70px 70px',
        gap: '0.5rem', padding: '0.5rem 0.75rem', fontWeight: 600, fontSize: '0.8rem',
        borderBottom: '2px solid var(--border)', color: 'var(--text-muted)',
      }}>
        <div></div>
        <div onClick={() => toggleSort('path')} style={{ cursor: 'pointer' }}>Path{sortIndicator('path')}</div>
        <div onClick={() => toggleSort('size')} style={{ cursor: 'pointer', textAlign: 'right' }}>Size{sortIndicator('size')}</div>
        <div onClick={() => toggleSort('age_days')} style={{ cursor: 'pointer', textAlign: 'right' }}>Age{sortIndicator('age_days')}</div>
        <div style={{ textAlign: 'center' }}>Status</div>
      </div>

      {viewMode === 'grouped' ? (
        <div style={{ height: 'calc(100vh - 280px)', overflow: 'auto' }}>
          {Object.entries(
            filtered.reduce((acc, f) => {
              const cat = getCategory(f.path);
              if (!acc[cat]) acc[cat] = { files: [], totalSize: 0 };
              acc[cat].files.push(f);
              acc[cat].totalSize += f.size;
              return acc;
            }, {} as Record<string, { files: LargeFile[]; totalSize: number }>)
          )
            .sort(([, a], [, b]) => b.totalSize - a.totalSize)
            .map(([category, { files: catFiles, totalSize }]) => (
              <details key={category} open={catFiles.length <= 20} style={{ marginBottom: '0.5rem' }}>
                <summary style={{
                  padding: '0.6rem 0.75rem', cursor: 'pointer', fontWeight: 600,
                  fontSize: '0.85rem', background: 'var(--card-bg)', borderRadius: '8px',
                  border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between',
                  listStyle: 'none',
                }}>
                  <span>{category} ({catFiles.length} files)</span>
                  <span style={{ color: 'var(--primary)' }}>{formatBytes(totalSize)}</span>
                </summary>
                <div style={{ padding: '0.25rem 0' }}>
                  {catFiles.slice(0, 50).map(file => (
                    <div key={file.path} style={{
                      display: 'grid', gridTemplateColumns: '32px 1fr 100px 70px',
                      gap: '0.5rem', padding: '0.4rem 0.75rem', fontSize: '0.8rem',
                      borderBottom: '1px solid var(--border)',
                    }}>
                      <input type="checkbox" checked={selected.has(file.path)}
                        disabled={file.is_protected} onChange={() => toggleSelect(file.path)} />
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={file.path}>{file.path}</div>
                      <div style={{ textAlign: 'right', fontWeight: 500 }}>{formatBytes(file.size)}</div>
                      <div style={{ textAlign: 'center' }}>
                        {file.is_protected ? '🔒' : file.is_cache ? '🗑️' : '📄'}
                      </div>
                    </div>
                  ))}
                  {catFiles.length > 50 && (
                    <div style={{ padding: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center' }}>
                      ...and {catFiles.length - 50} more files
                    </div>
                  )}
                </div>
              </details>
            ))}
        </div>
      ) : (
        <div ref={parentRef} style={{ height: 'calc(100vh - 280px)', overflow: 'auto' }}>
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {virtualizer.getVirtualItems().map(row => {
              const file = filtered[row.index];
              return (
                <div key={file.path} style={{
                  position: 'absolute', top: 0, left: 0, width: '100%',
                  transform: `translateY(${row.start}px)`, height: row.size,
                  display: 'grid', gridTemplateColumns: '32px 1fr 100px 70px 70px',
                  gap: '0.5rem', padding: '0.5rem 0.75rem', alignItems: 'center',
                  fontSize: '0.8rem', borderBottom: '1px solid var(--border)',
                  background: selected.has(file.path) ? 'var(--primary)10' : 'transparent',
                }}>
                  <input type="checkbox" checked={selected.has(file.path)} disabled={file.is_protected} onChange={() => toggleSelect(file.path)} />
                  <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={file.path}>{file.path}</div>
                  <div style={{ textAlign: 'right', fontWeight: 500 }}>{formatBytes(file.size)}</div>
                  <div style={{ textAlign: 'right', color: 'var(--text-muted)' }}>{formatAge(file.age_days)}</div>
                  <div style={{ textAlign: 'center' }}>{file.is_protected ? '🔒' : file.is_cache ? '🗑️' : '📄'}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
