import { useState, useEffect } from 'react';
import { formatBytes } from '../lib/format';
import { authHeaders } from '../lib/auth';

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

interface RunOutcome {
  dry_run: boolean;
  freed?: number;
  results?: { command: string; success: boolean; error?: string }[];
  error?: string;
}

export default function AgentsPanel() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [lastOutcome, setLastOutcome] = useState<Record<string, RunOutcome>>({});

  const loadAgents = () => {
    fetch('/api/agents', { headers: authHeaders() }).then(r => r.json()).then(setAgents).catch(console.error);
  };

  useEffect(() => { loadAgents(); }, []);

  const toggle = async (id: string, enabled: boolean) => {
    await fetch(`/api/agents/${id}/toggle?enabled=${enabled}`, { method: 'POST', headers: authHeaders() });
    loadAgents();
  };

  const runNow = async (id: string) => {
    setRunning(prev => new Set(prev).add(id));
    try {
      // The endpoint dry-runs by default (no confirm=true) and reports back
      // what it *would* do without touching anything. Use that to build an
      // honest confirmation prompt before actually executing anything — some
      // of these commands (e.g. `rm -rf ~/Library/Caches/*`) are destructive
      // and irreversible.
      const dryRes = await fetch(`/api/agents/${id}/run`, { method: 'POST', headers: authHeaders() });
      if (!dryRes.ok) {
        // Fail closed: if we can't even confirm what this agent would do,
        // never fall through to the destructive confirm=true call.
        setLastOutcome(prev => ({ ...prev, [id]: { dry_run: true, error: `Could not check what this agent would do (HTTP ${dryRes.status}). Run cancelled.` } }));
        return;
      }
      const dry = await dryRes.json();
      if (!Array.isArray(dry.would_run)) {
        // Fail closed: an unexpected response shape is treated the same as a
        // failed probe, NOT as "no commands, safe to skip the confirmation."
        setLastOutcome(prev => ({ ...prev, [id]: { dry_run: true, error: 'Unexpected response while checking this agent. Run cancelled.' } }));
        return;
      }
      const commands: string[] = dry.would_run;

      if (commands.length > 0) {
        const ok = window.confirm(
          `Run "${agents.find(a => a.id === id)?.name ?? id}" for real?\n\n` +
          `This will execute:\n${commands.map(c => `  ${c}`).join('\n')}\n\n` +
          `This cannot be undone. Continue?`
        );
        if (!ok) return;
      }

      const res = await fetch(`/api/agents/${id}/run?confirm=true`, { method: 'POST', headers: authHeaders() });
      const outcome: RunOutcome = await res.json();
      setLastOutcome(prev => ({ ...prev, [id]: outcome }));
      loadAgents();
    } catch (e) {
      console.error(e);
      setLastOutcome(prev => ({ ...prev, [id]: { dry_run: false, error: 'Request failed' } }));
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
            {lastOutcome[agent.id] && (() => {
              const outcome = lastOutcome[agent.id];
              const failed = outcome.results?.filter(r => !r.success) ?? [];
              return (
                <div style={{ fontSize: '0.7rem', marginTop: '0.3rem', marginLeft: '52px' }}>
                  {outcome.error && <span style={{ color: 'var(--danger)' }}>{outcome.error}</span>}
                  {!outcome.error && outcome.results !== undefined && (
                    <span style={{ color: failed.length > 0 ? 'var(--danger)' : 'var(--success)' }}>
                      {outcome.results.length === 0
                        ? 'Ran — no commands to execute for this agent.'
                        : failed.length > 0
                          ? `Ran with ${failed.length} error(s): ${failed.map(r => r.error).join('; ')}`
                          : `Done — freed ${formatBytes(outcome.freed ?? 0)}.`}
                    </span>
                  )}
                </div>
              );
            })()}
          </div>
        ))}
      </div>
    </div>
  );
}
