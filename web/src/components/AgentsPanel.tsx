import { useState, useEffect } from 'react';
import { formatBytes } from '../lib/format';

interface Agent {
  id: string;
  name: string;
  description: string;
  interval_hours: number;
  enabled: boolean;
  last_run: string | null;
  last_freed: number;
  total_freed: number;
  run_count: number;
}

export default function AgentsPanel() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [running, setRunning] = useState<Set<string>>(new Set());

  const loadAgents = () => {
    fetch('/api/agents').then(r => r.json()).then(setAgents).catch(console.error);
  };

  useEffect(() => { loadAgents(); }, []);

  const toggle = async (id: string, enabled: boolean) => {
    await fetch(`/api/agents/${id}/toggle?enabled=${enabled}`, { method: 'POST' });
    loadAgents();
  };

  const runNow = async (id: string) => {
    setRunning(prev => new Set(prev).add(id));
    try {
      await fetch(`/api/agents/${id}/run`, { method: 'POST' });
      loadAgents();
    } finally {
      setRunning(prev => { const n = new Set(prev); n.delete(id); return n; });
    }
  };

  const intervalLabel = (hours: number) => {
    if (hours < 24) return `Every ${hours}h`;
    if (hours < 168) return `Every ${Math.round(hours / 24)}d`;
    return 'Weekly';
  };

  return (
    <div style={{ maxWidth: 600 }}>
      <div className="card">
        <h3 style={{ marginBottom: '0.25rem' }}>Background Agents</h3>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
          Automated tasks that keep your disk clean. They run on a schedule while the server is active.
        </p>

        {agents.map(agent => (
          <div key={agent.id} style={{
            padding: '0.75rem 0',
            borderTop: '1px solid var(--border)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <label style={{ position: 'relative', width: 40, height: 22, cursor: 'pointer' }}>
                <input type="checkbox" checked={agent.enabled}
                  onChange={e => toggle(agent.id, e.target.checked)}
                  style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }} />
                <div style={{
                  width: 40, height: 22, borderRadius: 11,
                  background: agent.enabled ? 'var(--success)' : 'var(--border)',
                  transition: 'background 0.2s', position: 'relative',
                }}>
                  <div style={{
                    width: 18, height: 18, borderRadius: '50%', background: 'white',
                    position: 'absolute', top: 2,
                    left: agent.enabled ? 20 : 2,
                    transition: 'left 0.2s',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                  }} />
                </div>
              </label>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{agent.name}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{agent.description}</div>
              </div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{intervalLabel(agent.interval_hours)}</span>
              <button className="btn btn-ghost" onClick={() => runNow(agent.id)}
                disabled={running.has(agent.id)}
                style={{ fontSize: '0.7rem', padding: '0.2rem 0.5rem' }}>
                {running.has(agent.id) ? 'Running...' : 'Run now'}
              </button>
            </div>
            {agent.run_count > 0 && (
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.3rem', marginLeft: '52px' }}>
                Last run: {agent.last_run ? new Date(agent.last_run).toLocaleString() : 'never'}
                {agent.last_freed > 0 && ` · Freed: ${formatBytes(agent.last_freed)}`}
                {agent.total_freed > 0 && ` · Total: ${formatBytes(agent.total_freed)}`}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
