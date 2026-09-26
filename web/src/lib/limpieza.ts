/**
 * The single model behind every cleanup screen.
 *
 * Recommendations are grouped by what the user loses, not by an abstract risk
 * level: "comes back by itself", "has to be downloaded again", "gone for
 * good". That is the question a person asks before deleting anything, and
 * the answer decides what is pre-selected (only what comes back by itself).
 *
 * Nothing here runs anything. Screens call `pedirLimpieza()`, which opens the
 * review sheet (RevisarLimpieza); that sheet is the only place that hands
 * commands to useCleanupRunner.
 */
import type { Recommendation } from './api';
import { emit } from './events';

export type Consecuencia = 'regenera' | 'redescarga' | 'permanente';

export interface Accion {
  /** Stable key: the rule id when there is one. */
  clave: string;
  titulo: string;
  detalle: string;
  consecuencia: Consecuencia;
  /** The analysis's estimate, in bytes. Never shown as "freed". */
  estimado: number;
  command: string;
}

export interface Plan {
  acciones: Accion[];
  /** Rules that only show a list (old downloads, VMs…): worth a look, but
   *  running them frees nothing, so they are never offered as cleanup. */
  paraRevisar: Recommendation[];
  /** The report predates the safety marks (`efecto`): its commands were
   *  built before the deletion gate and must not run. A new analysis fixes it. */
  informeAntiguo: boolean;
}

export const CONSECUENCIAS: Consecuencia[] = ['regenera', 'redescarga', 'permanente'];

export const TEXTO_CONSECUENCIA: Record<Consecuencia, { titulo: string; ayuda: string; color: string; preseleccion: boolean }> = {
  regenera: {
    titulo: 'Comes back by itself',
    ayuda: 'Caches, logs and build output. Apps recreate them when needed; the next launch or build may be slower.',
    color: 'var(--success)',
    preseleccion: true,
  },
  redescarga: {
    titulo: 'Has to be downloaded again',
    ayuda: 'Nothing personal is lost, but the next time you use it, it has to be downloaded again.',
    color: 'var(--warning)',
    preseleccion: false,
  },
  permanente: {
    titulo: 'Gone for good',
    ayuda: 'Cannot be undone.',
    color: 'var(--danger)',
    preseleccion: false,
  },
};

const ejecutable = (r: Recommendation) => Boolean(r.command) && !r.command.trim().startsWith('#');

export function planDe(recs: Recommendation[]): Plan {
  const acciones: Accion[] = [];
  const paraRevisar: Recommendation[] = [];
  const vistos = new Set<string>();
  let informeAntiguo = false;

  for (const r of recs) {
    if (r.efecto === 'solo_lista' || r.consecuencia === 'solo_lista' || (r.command && !ejecutable(r))) {
      paraRevisar.push(r);
      continue;
    }
    if (!ejecutable(r)) continue;
    if (!r.efecto) {
      informeAntiguo = true;
      continue;
    }
    if (vistos.has(r.command)) continue;
    vistos.add(r.command);
    acciones.push({
      clave: r.id ?? r.command,
      titulo: r.type,
      detalle: r.description,
      // A rule that declares what it does but not what it costs is treated
      // as the worst case: never pre-selected, red warning.
      consecuencia: r.consecuencia ?? 'permanente',
      estimado: r.space || 0,
      command: r.command,
    });
  }
  return { acciones, paraRevisar, informeAntiguo };
}

export function totalEstimado(acciones: Accion[]): number {
  return acciones.reduce((s, a) => s + a.estimado, 0);
}

export function preseleccion(acciones: Accion[]): Set<string> {
  return new Set(acciones.filter(a => TEXTO_CONSECUENCIA[a.consecuencia].preseleccion).map(a => a.clave));
}

export interface PeticionLimpieza {
  acciones: Accion[];
  /** Keys to tick when the sheet opens. Defaults to `preseleccion()`. */
  marcadas?: string[];
}

/** Opens the review sheet. Nothing runs until the user confirms there. */
export function pedirLimpieza(peticion: PeticionLimpieza): void {
  emit('cleanup:review', peticion);
}
