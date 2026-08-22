import { useSyncExternalStore } from 'react';
import { api } from '../lib/api';
import { emit, on } from '../lib/events';

const STORAGE_KEY = 'disk-analyzer-cleaned';

// How long to wait for a queued command's exit before giving up on it and
// moving the queue on. This exists purely so a lost exit event (server
// process restarts mid-command, PTY killed some other way) can't wedge the
// queue forever — it never marks the command successful, only un-sticks
// things. Long enough to comfortably outlast any real cleanup command
// (docker prunes and brew cleanups can run for minutes); short enough that
// a genuinely stuck queue recovers within one page visit.
const STUCK_JOB_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes

export interface CleanupJob {
  command: string;
  space: number;
  label?: string;
}

// Internal, queue-only shape: adds the free-space measurement taken right
// before the command started. Kept out of the public CleanupJob so callers
// of run() never have to supply it — it's captured by startJob() itself and
// carried on the job object (not a module-level variable) because several
// jobs can be in flight in the queue over time and a shared variable would
// get clobbered between them.
interface QueuedJob extends CleanupJob {
  libreAntes: number | null;
}

export interface CleanupRunner {
  /** Enqueue the command to run in a PTY once any prior queued command has resolved. */
  run: (job: CleanupJob) => void;
  /** Commands currently running or queued to run (by command string). */
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

function persist(completed: Set<string>): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...completed])); } catch { /* storage full or disabled */ }
}

// ── Module-level shared store ────────────────────────────────────────────
// Every call site of useCleanupRunner() reads and mutates this same state.
// It has to be a singleton rather than per-hook-instance state: index.astro
// mounts QuickActions + ReverseView + DockerPanel together, and cleanup.astro
// mounts several more — their recommendation lists overlap (the same "safe"
// tier commands appear in more than one component from the same analysis),
// so the "is this command already running?" guard in run() only prevents a
// destructive command from firing twice if every component is checking the
// same running set.
interface CleanupState {
  running: Set<string>;
  completed: Set<string>;
  error: string | null;
}

let state: CleanupState = {
  running: new Set(),
  completed: loadCompleted(),
  error: null,
};

// A stable empty-ish snapshot for server rendering (Astro pre-renders React
// islands with client:load to static HTML). useSyncExternalStore requires a
// getServerSnapshot to avoid touching the client store during SSR.
const SERVER_SNAPSHOT: CleanupState = { running: new Set(), completed: new Set(), error: null };

const listeners = new Set<() => void>();

function setState(patch: Partial<CleanupState>): void {
  state = { ...state, ...patch };
  listeners.forEach(l => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function getSnapshot(): CleanupState {
  return state;
}

function getServerSnapshot(): CleanupState {
  return SERVER_SNAPSHOT;
}

// ── Sequential execution ─────────────────────────────────────────────────
// The floating terminal can only ever display one PTY at a time
// (useTerminal.attach() tears down the previous socket before connecting the
// next), so the PTY this module tracks for an exit code must always be the
// one the user can see. Bulk actions (GuidedDeclutter, WhatIfSandbox,
// ReverseView, CleanupWizard's "clean safe items") call run() in tight,
// un-awaited loops; run() enqueues rather than starting immediately, and
// this module starts at most one command at a time, crediting (or failing)
// each before starting the next.
const queue: CleanupJob[] = [];
const jobs: Record<string, QueuedJob> = {}; // pty_id -> the one active job, while one is in flight
let processing = false;
let watchdog: ReturnType<typeof setTimeout> | null = null;

function clearWatchdog(): void {
  if (watchdog !== null) { clearTimeout(watchdog); watchdog = null; }
}

function scheduleNext(): void {
  if (processing) return;
  const job = queue.shift();
  if (!job) return;
  // Set synchronously, before the await inside startJob: two run() calls in
  // the same synchronous loop must not both see processing === false and
  // both start a job.
  processing = true;
  startJob(job);
}

async function startJob(job: CleanupJob): Promise<void> {
  // Measure free disk space before the command runs, so the eventual credit
  // reflects what the command actually freed instead of trusting its
  // estimate. Stored on the job itself (not a module variable) since several
  // jobs pass through this queue over the page's lifetime.
  const libreAntes = await api.getSystemInfo()
    .then(i => i.disk_usage?.free ?? null)
    .catch(() => null);
  const queuedJob: QueuedJob = { ...job, libreAntes };
  try {
    const { pty_id } = await api.createTerminal(job.command);
    jobs[pty_id] = queuedJob;
    emit('terminal:open', { pty_id, command: job.command });
    watchdog = setTimeout(() => giveUpOn(pty_id), STUCK_JOB_TIMEOUT_MS);
  } catch (e: any) {
    const nextRunning = new Set(state.running);
    nextRunning.delete(job.command);
    setState({ running: nextRunning, error: e?.message ?? 'Could not start the cleanup command' });
    processing = false;
    scheduleNext();
  }
}

// The active job's exit was never seen (lost event, PTY killed, server
// restart). Stop waiting on it and move the queue on — but never credit it:
// whether it actually succeeded is unknown.
function giveUpOn(ptyId: string): void {
  const job = jobs[ptyId];
  if (!job) return; // already resolved normally in the meantime
  delete jobs[ptyId];
  watchdog = null;
  const nextRunning = new Set(state.running);
  nextRunning.delete(job.command);
  setState({ running: nextRunning, error: `${job.label ?? job.command}: no response from the terminal` });
  processing = false;
  scheduleNext();
}

async function finishActiveJob(ptyId: string, code: number | null): Promise<void> {
  const job = jobs[ptyId];
  // An exit for a pty this module isn't tracking — either something
  // unrelated (a manually opened shell) or a duplicate event for a job
  // already resolved — must not touch the queue. The job actually in
  // flight (if any) is unaffected and will still resolve on its own exit.
  if (!job) return;
  // Delete first: a duplicate exit event for the same pty must not credit
  // (or advance the queue for) the same job twice.
  delete jobs[ptyId];
  clearWatchdog();

  const nextRunning = new Set(state.running);
  nextRunning.delete(job.command);

  if (code === 0) {
    const nextCompleted = new Set(state.completed).add(job.command);
    persist(nextCompleted);
    setState({ running: nextRunning, completed: nextCompleted });

    // The exit code proves nothing about the space freed: `rm -f` returns 0
    // whether it deleted everything or nothing. Measure the disk instead,
    // and only fall back to the recommendation's own estimate when the
    // measurement itself isn't available.
    let liberado = job.space;
    if (job.libreAntes != null) {
      const libreDespues = await api.getSystemInfo()
        .then(i => i.disk_usage?.free ?? null)
        .catch(() => null);
      if (libreDespues != null) {
        // Another process can write to disk while cleanup runs; never
        // credit a negative saving.
        liberado = Math.max(0, libreDespues - job.libreAntes);
      }
    }
    emit('cleanup:completed', { command: job.command, space: liberado, estimado: job.space });
  } else {
    setState({ running: nextRunning, error: `${job.label ?? job.command} exited with code ${code}` });
  }

  processing = false;
  scheduleNext();
}

function reset(): void {
  setState({ completed: new Set() });
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* storage disabled */ }
}

function run(job: CleanupJob): void {
  if (state.completed.has(job.command) || state.running.has(job.command)) return;
  // Mark running immediately (synchronously), not once the PTY actually
  // starts: this is the guard that makes two components clicking the same
  // recommendation a no-op for the second click, and it only works if it's
  // visible to every useCleanupRunner() call site the instant the first
  // click happens — hence the module-level state above.
  setState({ running: new Set(state.running).add(job.command), error: null });
  queue.push(job);
  scheduleNext();
}

// Only registered once, when this module is first evaluated — not per
// useCleanupRunner() call — since the state above is a page-wide singleton.
// Guarded for SSR: Astro pre-renders client:load islands to static HTML in
// Node, where `window` doesn't exist.
if (typeof window !== 'undefined') {
  on('terminal:exited', (data: any) => finishActiveJob(data.pty_id, data.code));
  // A fresh scan invalidates any prior "already cleaned" state: recommendations
  // are recomputed, and commands that completed against the old scan should not
  // be treated as already-done against the new one.
  on('analysis:completed', () => reset());
}

export function useCleanupRunner(): CleanupRunner {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return { run, running: snapshot.running, completed: snapshot.completed, error: snapshot.error, reset };
}

/**
 * Test-only: fully reset the module's singleton state between tests. This
 * state is intentionally shared and page-lifetime-scoped in production —
 * application code should never call this.
 */
export function __resetCleanupRunnerForTests(): void {
  queue.length = 0;
  for (const key of Object.keys(jobs)) delete jobs[key];
  processing = false;
  clearWatchdog();
  state = { running: new Set(), completed: new Set(), error: null };
  listeners.clear();
}
