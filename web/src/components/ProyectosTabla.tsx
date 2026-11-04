import { useEffect, useState } from 'react';
import { authHeaders } from '../lib/auth';
import { formatBytes } from '../lib/format';
import { pedirLimpieza, type Accion } from '../lib/limpieza';

export interface Artefacto {
  id: string;
  titulo: string;
  ruta: string;
  space: number;
  dias: number | null;
  worktree: boolean;
  reproducible: boolean;
  ignorado: boolean;
  command: string;
}

/** Why an artifact is not offered, for the rows without a command. */
export function motivo(a: Artefacto): string {
  if (!a.ignorado) return 'git no lo ignora: podría estar versionado';
  if (!a.reproducible) return 'el proyecto no dice cómo reconstruirlo';
  return '';
}

export function accionDe(a: Artefacto): Accion {
  return {
    clave: a.id,
    titulo: a.titulo,
    detalle: `${a.ruta} — hay que reinstalar o volver a compilar`,
    consecuencia: 'regenera',
    estimado: a.space,
    command: a.command,
  };
}

/** Everything goes through the review sheet: this page never runs a command. */
export default function ProyectosTabla() {
  const [lista, setLista] = useState<Artefacto[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch('/api/proyectos', { headers: authHeaders() })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(d => setLista(d.proyectos))
      .catch(() => setError(true));
  }, []);

  if (error) return <p>No se pudo leer la lista de proyectos.</p>;
  if (lista === null) return <p>Midiendo proyectos… puede tardar un poco.</p>;
  if (lista.length === 0) return <p>No se encontró nada que los proyectos puedan reconstruir.</p>;

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <th align="left">Proyecto</th>
          <th align="right">Tamaño</th>
          <th align="right">Sin tocar</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {lista.map(a => (
          <tr key={a.id}>
            <td title={a.ruta}>
              {a.titulo}
              {a.worktree ? ' (worktree)' : ''}
            </td>
            <td align="right">{formatBytes(a.space)}</td>
            <td align="right">{a.dias === null ? '—' : `${a.dias} días`}</td>
            <td align="right">
              {a.command ? (
                <button onClick={() => {
                  const accion = accionDe(a);
                  pedirLimpieza({ acciones: [accion], marcadas: [accion.clave] });
                }}>Limpiar…</button>
              ) : (
                <span>{motivo(a)}</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
