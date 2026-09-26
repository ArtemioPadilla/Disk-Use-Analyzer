import { useEffect, useMemo, useRef, useState } from 'react';
import { emit, on } from '../lib/events';
import { api, type Recommendation, type SessionResults } from '../lib/api';
import { authHeaders } from '../lib/auth';
import { formatBytes } from '../lib/format';
import { useCleanupRunner } from '../hooks/useCleanupRunner';
import {
  CONSECUENCIAS, TEXTO_CONSECUENCIA, planDe, preseleccion, totalEstimado,
  type Accion, type PeticionLimpieza,
} from '../lib/limpieza';

/**
 * The review step every cleanup goes through, and the only component that
 * hands commands to useCleanupRunner (a test enforces it).
 *
 * - `hoja`: a modal sheet, mounted once in MainLayout, opened by any button
 *   through `pedirLimpieza()`.
 * - `pagina`: the same list inline, fed by the latest analysis — the Cleanup
 *   page.
 *
 * Nothing is deleted until the user presses the button that states the total.
 * Afterwards each item shows what the disk actually gained, measured by the
 * runner before and after the command, never the estimate.
 */

type Fase = 'revisar' | 'ejecutando' | 'hecho';
type Resultado = { estado: 'esperando' } | { estado: 'ok'; medido: number } | { estado: 'fallo'; motivo: string };

export default function RevisarLimpieza({ modo = 'hoja' }: { modo?: 'hoja' | 'pagina' }) {
  const { run, completed } = useCleanupRunner();
  const [abierta, setAbierta] = useState(modo === 'pagina');
  const [acciones, setAcciones] = useState<Accion[]>([]);
  const [paraRevisar, setParaRevisar] = useState<Recommendation[]>([]);
  const [informeAntiguo, setInformeAntiguo] = useState(false);
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [comandos, setComandos] = useState<Set<string>>(new Set());
  const [fase, setFase] = useState<Fase>('revisar');
  const [resultados, setResultados] = useState<Record<string, Resultado>>({});
  // Page mode only: whether an analysis was found to review.
  const [sinAnalisis, setSinAnalisis] = useState(false);
  const primerBoton = useRef<HTMLButtonElement>(null);

  const cargar = (lista: Accion[], marcar: Iterable<string>) => {
    setAcciones(lista);
    setMarcadas(new Set(marcar));
    setComandos(new Set());
    setResultados({});
    setFase('revisar');
  };

  useEffect(() => {
    const offs = [
      on('cleanup:completed', (d: { command: string; space: number }) =>
        setResultados(prev => (prev[d.command] ? { ...prev, [d.command]: { estado: 'ok', medido: d.space || 0 } } : prev))),
      on('cleanup:failed', (d: { command: string; motivo: string }) =>
        setResultados(prev => (prev[d.command] ? { ...prev, [d.command]: { estado: 'fallo', motivo: d.motivo } } : prev))),
    ];
    if (modo === 'hoja') {
      offs.push(on('cleanup:review', (p: PeticionLimpieza) => {
        cargar(p.acciones, p.marcadas ?? preseleccion(p.acciones));
        setParaRevisar([]);
        setInformeAntiguo(false);
        setAbierta(true);
      }));
    } else {
      const mostrar = (data: SessionResults) => {
        const plan = planDe((data.results || []).flatMap(r => r.report?.recommendations || []));
        cargar(plan.acciones, preseleccion(plan.acciones));
        setParaRevisar(plan.paraRevisar);
        setInformeAntiguo(plan.informeAntiguo);
        setSinAnalisis(false);
      };
      offs.push(on('analysis:completed', mostrar));
      // Only the Dashboard loads results on its own; without this the
      // Cleanup page was empty unless an analysis ran on it. Same source as
      // the Dashboard: the requested session, or the latest one.
      const sesion = new URLSearchParams(window.location.search).get('session');
      const carga: Promise<SessionResults | null> = sesion
        ? api.getResults(sesion)
        : fetch('/api/analysis/latest', { headers: authHeaders() }).then(r => (r.ok ? r.json() : null));
      carga.then(d => (d ? mostrar(d) : setSinAnalisis(true))).catch(() => setSinAnalisis(true));
    }
    return () => offs.forEach(off => off());
  }, [modo]);

  // Once every launched item has resolved, the run is over.
  useEffect(() => {
    if (fase !== 'ejecutando') return;
    const todos = Object.values(resultados);
    if (todos.length > 0 && todos.every(r => r.estado !== 'esperando')) setFase('hecho');
  }, [resultados, fase]);

  useEffect(() => {
    if (modo !== 'hoja' || !abierta) return;
    primerBoton.current?.focus();
    const teclas = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAbierta(false);
    };
    document.addEventListener('keydown', teclas);
    return () => document.removeEventListener('keydown', teclas);
  }, [modo, abierta]);

  const hechoAntes = (a: Accion) => completed.has(a.command) && !resultados[a.command];
  const seleccion = useMemo(
    () => acciones.filter(a => marcadas.has(a.clave) && !hechoAntes(a)),
    [acciones, marcadas, completed, resultados],
  );
  const estimado = totalEstimado(seleccion);
  const hayPermanente = seleccion.some(a => a.consecuencia === 'permanente');
  const medido = Object.values(resultados).reduce((s, r) => s + (r.estado === 'ok' ? r.medido : 0), 0);
  const fallos = Object.values(resultados).filter(r => r.estado === 'fallo').length;

  const alternar = (clave: string) => setMarcadas(prev => {
    const n = new Set(prev);
    n.has(clave) ? n.delete(clave) : n.add(clave);
    return n;
  });
  const verComando = (clave: string) => setComandos(prev => {
    const n = new Set(prev);
    n.has(clave) ? n.delete(clave) : n.add(clave);
    return n;
  });

  const liberar = () => {
    if (seleccion.length === 0) return;
    setResultados(Object.fromEntries(seleccion.map(a => [a.command, { estado: 'esperando' } as Resultado])));
    setFase('ejecutando');
    for (const a of seleccion) run({ command: a.command, space: a.estimado, label: a.titulo });
  };

  if (!abierta) return null;
  if (modo === 'pagina' && acciones.length === 0 && paraRevisar.length === 0 && !informeAntiguo) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🧹</div>
        <div style={{ marginBottom: '0.5rem', fontWeight: 500 }}>{sinAnalisis ? 'No analysis yet' : 'Nothing to clean up'}</div>
        <p style={{ fontSize: '0.85rem', marginBottom: '1.5rem' }}>Scan your disk to see what can be freed.</p>
        <button className="btn btn-primary" onClick={() => emit('analysis:new')}>+ New Analysis</button>
      </div>
    );
  }

  const fila = (a: Accion) => {
    const r = resultados[a.command];
    const antes = hechoAntes(a);
    const bloqueada = fase !== 'revisar' || antes;
    return (
      <div key={a.clave} style={{ padding: '0.55rem 0', borderTop: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem' }}>
          <input
            type="checkbox"
            aria-label={a.titulo}
            checked={marcadas.has(a.clave) && !antes}
            disabled={bloqueada}
            onChange={() => alternar(a.clave)}
            style={{ marginTop: '0.2rem' }}
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{a.titulo}</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{a.detalle}</div>
            <button
              type="button"
              onClick={() => verComando(a.clave)}
              style={{ background: 'none', border: 'none', padding: 0, marginTop: '0.2rem', color: 'var(--text-muted)', fontSize: '0.72rem', cursor: 'pointer', textDecoration: 'underline' }}
            >
              {comandos.has(a.clave) ? 'Hide command' : 'Show command'}
            </button>
            {comandos.has(a.clave) && (
              <code style={{ display: 'block', marginTop: '0.25rem', fontSize: '0.72rem', background: 'var(--page-bg)', padding: '0.3rem 0.5rem', borderRadius: 4, wordBreak: 'break-all' }}>
                {a.command}
              </code>
            )}
          </div>
          <div style={{ textAlign: 'right', whiteSpace: 'nowrap', fontSize: '0.8rem' }}>
            {!r && !antes && <span style={{ color: 'var(--text-muted)' }}>~{formatBytes(a.estimado)}</span>}
            {antes && <span style={{ color: 'var(--text-muted)' }}>Done earlier</span>}
            {r?.estado === 'esperando' && <span style={{ color: 'var(--text-muted)' }}>Running…</span>}
            {r?.estado === 'ok' && (
              <span style={{ color: 'var(--success)', fontWeight: 600 }}>
                {r.medido > 0 ? `✓ ${formatBytes(r.medido)} freed` : '✓ Done · nothing measurable freed'}
              </span>
            )}
            {r?.estado === 'fallo' && <span style={{ color: 'var(--danger)', fontWeight: 600 }}>{`✗ ${r.motivo}`}</span>}
          </div>
        </div>
      </div>
    );
  };

  const cuerpo = (
    <>
      {informeAntiguo && (
        <div style={{ padding: '0.75rem', borderRadius: 8, background: 'var(--page-bg)', fontSize: '0.85rem', marginBottom: '0.75rem' }}>
          ⚠️ This report was made by an older version whose commands were not checked for safety, so none of them can run.
          Run a new analysis to clean up.
        </div>
      )}

      {CONSECUENCIAS.map(c => {
        const grupo = acciones.filter(a => a.consecuencia === c);
        if (grupo.length === 0) return null;
        const t = TEXTO_CONSECUENCIA[c];
        return (
          <section key={c} style={{ marginBottom: '0.9rem' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: t.color, display: 'inline-block', flexShrink: 0 }} />
              <span style={{ fontWeight: 700 }}>{t.titulo}</span>
              <span style={{ marginLeft: 'auto', fontSize: '0.8rem', color: 'var(--text-muted)' }}>~{formatBytes(totalEstimado(grupo))}</span>
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '0.15rem 0 0.25rem 1.1rem' }}>{t.ayuda}</div>
            {grupo.map(fila)}
          </section>
        );
      })}

      {paraRevisar.length > 0 && (
        <section style={{ marginTop: '0.5rem' }}>
          <div style={{ fontWeight: 700 }}>Worth a look yourself</div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
            Nothing here is deleted automatically: it may hold things you want to keep. Review them in the File Browser.
          </div>
          {paraRevisar.map((r, i) => (
            <div key={r.id ?? i} style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', padding: '0.4rem 0', borderTop: '1px solid var(--border)', fontSize: '0.8rem' }}>
              <span><b>{r.type}</b> <span style={{ color: 'var(--text-muted)' }}>{r.description}</span></span>
              {r.space > 0 && <span style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>~{formatBytes(r.space)}</span>}
            </div>
          ))}
        </section>
      )}
    </>
  );

  const pie = (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', borderTop: '1px solid var(--border)', paddingTop: '0.75rem' }}>
      <div style={{ flex: 1, fontSize: '0.82rem', color: 'var(--text-muted)', minWidth: 180 }}>
        {fase === 'revisar' && (
          <>
            {seleccion.length} selected · ~{formatBytes(estimado)} estimated
            {hayPermanente && <div style={{ color: 'var(--danger)', fontWeight: 600 }}>Includes items that cannot be undone.</div>}
          </>
        )}
        {fase !== 'revisar' && (
          <span style={{ color: 'var(--success)', fontWeight: 600 }}>
            {formatBytes(medido)} freed (measured){fase === 'ejecutando' ? ' so far…' : ''}
            {fallos > 0 && <span style={{ color: 'var(--danger)' }}> · {fallos} failed</span>}
          </span>
        )}
      </div>
      {modo === 'hoja' && (
        <button ref={primerBoton} type="button" className="btn btn-ghost" onClick={() => setAbierta(false)}>
          {fase === 'revisar' ? 'Cancel' : fase === 'ejecutando' ? 'Hide (keeps running)' : 'Close'}
        </button>
      )}
      {fase === 'revisar' && (
        <button
          type="button"
          className="btn"
          disabled={seleccion.length === 0}
          onClick={liberar}
          style={{ background: hayPermanente ? 'var(--danger)' : 'var(--primary)', color: 'white', opacity: seleccion.length === 0 ? 0.5 : 1 }}
        >
          Free ~{formatBytes(estimado)}
        </button>
      )}
      {modo === 'pagina' && fase === 'hecho' && (
        <button type="button" className="btn btn-ghost" onClick={() => cargar(acciones, [])}>Review again</button>
      )}
    </div>
  );

  if (modo === 'pagina') {
    return (
      <div className="card">
        <div style={{ fontWeight: 700, fontSize: '1.1rem', marginBottom: '0.25rem' }}>Free up space</div>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.9rem' }}>
          Pick what to remove. Only what comes back by itself is selected for you; nothing runs until you press the button.
        </div>
        {cuerpo}
        {acciones.length > 0 && pie}
      </div>
    );
  }

  return (
    <div
      onClick={e => { if (e.target === e.currentTarget && fase !== 'ejecutando') setAbierta(false); }}
      style={{ position: 'fixed', inset: 0, zIndex: 9000, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}
    >
      <div role="dialog" aria-modal="true" aria-labelledby="revisar-limpieza-titulo" className="card"
        style={{ width: '100%', maxWidth: 640, maxHeight: '85vh', display: 'flex', flexDirection: 'column', padding: '1.1rem', boxShadow: '0 20px 50px rgba(0,0,0,.35)' }}>
        <div id="revisar-limpieza-titulo" style={{ fontWeight: 700, fontSize: '1.1rem', marginBottom: '0.75rem' }}>
          {fase === 'revisar' ? 'Review before freeing space' : fase === 'ejecutando' ? 'Freeing space…' : 'Done'}
        </div>
        <div style={{ overflowY: 'auto', flex: 1, marginBottom: '0.75rem' }}>{cuerpo}</div>
        {pie}
      </div>
    </div>
  );
}
