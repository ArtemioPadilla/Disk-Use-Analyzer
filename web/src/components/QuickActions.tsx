import { useState, useEffect } from 'react';
import { on } from '../lib/events';
import { type SessionResults } from '../lib/api';
import { formatBytes } from '../lib/format';
import { pedirLimpieza, planDe, type Accion } from '../lib/limpieza';

/**
 * The three biggest things that come back by themselves. A click opens the
 * review sheet with just that item: it never runs anything directly.
 */
export default function QuickActions() {
  const [acciones, setAcciones] = useState<Accion[]>([]);

  useEffect(() => on('analysis:completed', (data: SessionResults) => {
    const plan = planDe((data.results || []).flatMap(r => r.report?.recommendations || []));
    setAcciones(plan.acciones
      .filter(a => a.consecuencia === 'regenera' && a.estimado > 0)
      .sort((a, b) => b.estimado - a.estimado)
      .slice(0, 3));
  }), []);

  if (acciones.length === 0) return null;

  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.9rem' }}>Quick Cleanup</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.5rem' }}>
        {acciones.map(a => (
          <div key={a.clave} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{a.titulo}</div>
            <div style={{ fontWeight: 700, color: 'var(--primary)' }}>~{formatBytes(a.estimado)}</div>
            <button className="btn btn-primary"
              onClick={() => pedirLimpieza({ acciones: [a], marcadas: [a.clave] })}
              style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem', alignSelf: 'flex-start' }}>
              Review…
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
