import { useState, useEffect } from 'react';
import { on } from '../lib/events';

interface Task {
  id: string;
  label: string;
  status: 'running' | 'completed' | 'error';
  detail?: string;
}

export default function TaskList() {
  const [tasks, setTasks] = useState<Task[]>([]);

  useEffect(() => {
    const offs = [
      on('analysis:started', (session: any) => {
        setTasks(prev => [...prev, { id: session.id, label: `Analysis of ${session.paths.join(', ')}`, status: 'running' }]);
      }),
      on('analysis:progress', (data: any) => {
        setTasks(prev => prev.map(t =>
          t.status === 'running' && data.current_path
            ? { ...t, detail: `${data.progress ?? 0}% — ${data.current_path}` } : t
        ));
      }),
      on('analysis:completed', (data: any) => {
        setTasks(prev => prev.map(t => t.id === data.id ? { ...t, status: 'completed', detail: undefined } : t));
      }),
      on('analysis:error', (data: any) => {
        setTasks(prev => prev.map(t => t.status === 'running' ? { ...t, status: 'error', detail: data.message } : t));
      }),
      on('terminal:started', (data: any) => {
        setTasks(prev => [...prev, { id: data.pty_id, label: `Running: ${data.command || 'interactive shell'}`, status: 'running' }]);
      }),
      on('terminal:exited', (data: any) => {
        setTasks(prev => prev.map(t => t.id === data.pty_id ? { ...t, status: data.code === 0 ? 'completed' : 'error' } : t));
      }),
    ];
    return () => offs.forEach(off => off());
  }, []);

  const statusColors: Record<string, string> = { running: '#6366f1', completed: '#10b981', error: '#ef4444' };
  const statusLabels: Record<string, string> = { running: 'In Progress', completed: 'Completed', error: 'Error' };

  if (tasks.length === 0) {
    return (
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Background Tasks</div>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem', padding: '0.5rem 0' }}>
          No active tasks. Start an analysis or run a command.
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Background Tasks</div>
      {tasks.map(task => (
        <div key={task.id} style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          padding: '0.5rem', borderRadius: '6px', marginBottom: '0.35rem',
          background: task.status === 'running' ? '#eff6ff' : task.status === 'completed' ? '#f0fdf4' : '#fef2f2',
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%', background: statusColors[task.status],
            animation: task.status === 'running' ? 'pulse 1.5s infinite' : 'none',
          }} />
          <span style={{ flex: 1, fontSize: '0.875rem' }}>
            {task.label}
            {task.detail && <span style={{ color: 'var(--text-muted)', marginLeft: '0.5rem', fontSize: '0.75rem' }}>{task.detail}</span>}
          </span>
          <span style={{
            fontSize: '0.7rem', padding: '0.2rem 0.5rem', borderRadius: '4px',
            background: statusColors[task.status] + '20', color: statusColors[task.status],
          }}>{statusLabels[task.status]}</span>
        </div>
      ))}
      <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }`}</style>
    </div>
  );
}
