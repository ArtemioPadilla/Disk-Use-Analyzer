import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { emit, on } from '../lib/events';

const STORAGE_KEY = 'disk-analyzer-cleaned';

export interface CleanupJob {
  command: string;
  space: number;
  label?: string;
}

export interface CleanupRunner {
  /** Spawn the command in a PTY and track it to completion. */
  run: (job: CleanupJob) => Promise<void>;
  /** Commands currently running (by command string). */
  running: Set<string>;
  /** Commands that already completed successfully, ever (persisted). */
  completed: Set<string>;
  /** Last error, or null. */
  error: string | null;
  /** Clear the completed set, in memory and in storage. Called automatically on a fresh analysis. */
  reset: () => void;
}

function loadCompleted(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

export function useCleanupRunner(): CleanupRunner {
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [completed, setCompleted] = useState<Set<string>>(loadCompleted);
  const [error, setError] = useState<string | null>(null);
  // pty_id -> job. A ref, not state: the exit listener must see the latest map
  // without re-subscribing on every run.
  const jobs = useRef<Record<string, CleanupJob>>({});

  const reset = () => {
    setCompleted(new Set());
    try { localStorage.removeItem(STORAGE_KEY); } catch { /* storage disabled */ }
  };

  // A fresh scan invalidates any prior "already cleaned" state: recommendations
  // are recomputed, and commands that completed against the old scan should not
  // be treated as already-done against the new one. Subscribing here (rather
  // than making every consumer call reset() from its own analysis:completed
  // listener) is the one place this reset belongs, since all six cleanup flows
  // need it identically.
  useEffect(() => {
    return on('analysis:completed', () => reset());
  }, []);

  useEffect(() => {
    return on('terminal:exited', (data: any) => {
      const job = jobs.current[data.pty_id];
      if (!job) return;
      // Delete first: a duplicate exit event for the same pty must not
      // credit the saving twice.
      delete jobs.current[data.pty_id];
      setRunning(prev => { const next = new Set(prev); next.delete(job.command); return next; });

      if (data.code === 0) {
        setCompleted(prev => {
          const next = new Set(prev).add(job.command);
          try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...next])); } catch { /* storage full or disabled */ }
          return next;
        });
        emit('cleanup:completed', { command: job.command, space: job.space });
      } else {
        setError(`${job.label ?? job.command} exited with code ${data.code}`);
      }
    });
  }, []);

  const run = async (job: CleanupJob) => {
    if (completed.has(job.command) || running.has(job.command)) return;
    setError(null);
    setRunning(prev => new Set(prev).add(job.command));
    try {
      const { pty_id } = await api.createTerminal(job.command);
      jobs.current[pty_id] = job;
      emit('terminal:open', { pty_id, command: job.command });
    } catch (e: any) {
      setRunning(prev => { const next = new Set(prev); next.delete(job.command); return next; });
      setError(e?.message ?? 'Could not start the cleanup command');
    }
  };

  return { run, running, completed, error, reset };
}
