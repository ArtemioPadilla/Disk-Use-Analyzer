import { useEffect, useState } from 'react';
import { on } from '../lib/events';

/**
 * Space actually freed since this page loaded: the sum of what the runner
 * measured on disk around each cleanup (`cleanup:completed`'s `space`).
 *
 * Replaces the old "freed so far" figures, which added up the analysis's
 * estimates for every command that had ever exited 0 — including commands
 * that only list files, and commands run in earlier sessions. On the
 * development machine it claimed 15.8 GB for a run that freed 0.3 GB.
 */
export function useLiberadoMedido(): number {
  const [total, setTotal] = useState(0);
  useEffect(() => on('cleanup:completed', (d: { space?: number }) => setTotal(t => t + Math.max(0, d?.space || 0))), []);
  return total;
}
