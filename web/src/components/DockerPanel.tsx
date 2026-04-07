import { useState, useEffect } from 'react';
import { on, emit } from '../lib/events';
import { api, type SessionResults } from '../lib/api';
import { formatBytes } from '../lib/format';

interface DockerStats {
  images: { count: number; size: number };
  containers: { count: number; stopped: number; size: number };
  volumes: { count: number; size: number };
  buildCache?: { size: number };
  total_space?: number;
  reclaimable?: number;
}

export default function DockerPanel() {
  const [docker, setDocker] = useState<DockerStats | null>(null);
  const [pruning, setPruning] = useState(false);
  const [pruned, setPruned] = useState(false);

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      const dockerData = data.results?.[0]?.report?.docker;
      if (dockerData && Object.keys(dockerData).length > 0) {
        setDocker(dockerData as DockerStats);
        setPruned(false);
      }
    });
    return off;
  }, []);

  const pruneDocker = async () => {
    setPruning(true);
    try {
      const { pty_id } = await api.createTerminal('docker system prune -af --volumes');
      emit('terminal:open', { pty_id, command: 'docker system prune' });
      emit('terminal:started', { pty_id, command: 'docker system prune -af --volumes' });
      // Mark as done after delay
      setTimeout(() => {
        setPruning(false);
        setPruned(true);
        emit('cleanup:completed', { command: 'docker system prune', space: docker?.reclaimable || 0 });
      }, 5000);
    } catch (e) {
      setPruning(false);
      console.error('Docker prune failed:', e);
    }
  };

  if (!docker) return null;

  const totalSpace = docker.total_space ||
    (docker.images?.size || 0) + (docker.containers?.size || 0) +
    (docker.volumes?.size || 0) + (docker.buildCache?.size || 0);

  if (totalSpace === 0) return null;

  const items = [
    { icon: '🖼️', label: 'Images', count: docker.images?.count || 0, size: docker.images?.size || 0, extra: undefined as string | undefined },
    { icon: '📦', label: 'Containers', count: docker.containers?.count || 0, size: docker.containers?.size || 0, extra: docker.containers?.stopped ? `${docker.containers.stopped} stopped` : undefined },
    { icon: '💾', label: 'Volumes', count: docker.volumes?.count || 0, size: docker.volumes?.size || 0, extra: undefined as string | undefined },
  ];
  if (docker.buildCache?.size) {
    items.push({ icon: '🔨', label: 'Build Cache', count: 0, size: docker.buildCache.size, extra: undefined });
  }

  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '1.2rem' }}>🐳</span>
          <span style={{ fontWeight: 600 }}>Docker</span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{formatBytes(totalSpace)}</span>
        </div>
        {!pruned ? (
          <button className="btn btn-primary" onClick={pruneDocker} disabled={pruning}
            style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}>
            {pruning ? 'Pruning...' : 'Prune Unused'}
          </button>
        ) : (
          <span style={{ color: 'var(--success)', fontSize: '0.8rem', fontWeight: 600 }}>✓ Pruned</span>
        )}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '0.5rem' }}>
        {items.filter(i => i.size > 0 || i.count > 0).map((item, idx) => (
          <div key={idx} style={{
            background: 'var(--page-bg)', borderRadius: '8px', padding: '0.6rem',
          }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
              {item.icon} {item.label}
            </div>
            <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{formatBytes(item.size)}</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              {item.count > 0 ? `${item.count} items` : ''}
              {item.extra ? ` · ${item.extra}` : ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
