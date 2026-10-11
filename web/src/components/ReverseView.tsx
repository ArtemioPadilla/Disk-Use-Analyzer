import { useState, useEffect } from 'react';
import { on } from '../lib/events';
import { api, type SessionResults } from '../lib/api';
import { formatBytes } from '../lib/format';
import { useLiberadoMedido } from '../hooks/useLiberadoMedido';
import { CONSECUENCIAS, TEXTO_CONSECUENCIA, pedirLimpieza, planDe, totalEstimado, type Plan } from '../lib/limpieza';

/**
 * Dashboard summary of what can be freed. It only summarises and opens the
 * review sheet: it never runs anything itself.
 */
export default function ReverseView() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [diskUsed, setDiskUsed] = useState(0);
  const [diskTotal, setDiskTotal] = useState(0);
  const liberado = useLiberadoMedido();

  useEffect(() => {
    const offs = [
      on('analysis:completed', (data: SessionResults) => {
        const report = data.results?.[0]?.report;
        if (!report) return;
        const disk = report.summary?.disk_usage;
        if (disk) { setDiskUsed(disk.used); setDiskTotal(disk.total); }
        setPlan(planDe((data.results || []).flatMap(r => r.report?.recommendations || [])));
      }),
      // The bar shows the real disk after a cleanup, not an estimate of it.
      on('cleanup:completed', () => {
        api.getSystemInfo().then(info => {
          setDiskUsed(info.disk_usage.used);
          setDiskTotal(info.disk_usage.total);
        }).catch(console.error);
      }),
    ];
    return () => offs.forEach(off => off());
  }, []);

  if (!plan) return null;
  const total = totalEstimado(plan.acciones);
  if (total === 0 && !plan.informeAntiguo) return null;
  const pct = diskTotal > 0 ? (diskUsed / diskTotal) * 100 : 0;

  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1rem', flexWrap: 'wrap' }}>
        <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>
          {plan.informeAntiguo && total === 0 ? 'Run a new analysis to clean up' : `You can free about ${formatBytes(total)}`}
        </div>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Disk {pct.toFixed(0)}% full</div>
      </div>
      <div style={{ height: 10, background: 'var(--border)', borderRadius: 5, overflow: 'hidden', margin: '0.5rem 0 0.75rem' }}>
        <div style={{
          height: '100%', width: `${pct}%`, borderRadius: 5, transition: 'width 0.5s ease',
          background: pct > 90 ? 'var(--danger)' : pct > 75 ? 'var(--warning)' : 'var(--success)',
        }} />
      </div>

      {plan.informeAntiguo && (
        <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '0.6rem' }}>
          ⚠️ This report comes from an older version whose commands were not checked for safety, so they won't run.
        </div>
      )}

      {CONSECUENCIAS.map(c => {
        const grupo = plan.acciones.filter(a => a.consecuencia === c);
        if (grupo.length === 0) return null;
        const t = TEXTO_CONSECUENCIA[c];
        return (
          <div key={c} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0', fontSize: '0.85rem' }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: t.color, display: 'inline-block', flexShrink: 0 }} />
            <span style={{ fontWeight: 600 }}>{t.titulo}</span>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {grupo.map(a => a.titulo).join(', ')}
            </span>
            <span style={{ marginLeft: 'auto', fontWeight: 600, whiteSpace: 'nowrap' }}>~{formatBytes(totalEstimado(grupo))}</span>
          </div>
        );
      })}

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
        {plan.acciones.length > 0 && (
          <button className="btn btn-primary" onClick={() => pedirLimpieza({ acciones: plan.acciones })}>
            Review &amp; free space…
          </button>
        )}
        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          {liberado > 0
            ? <span style={{ color: 'var(--success)', fontWeight: 600 }}>{formatBytes(liberado)} freed this session (measured)</span>
            : 'Nothing is deleted until you confirm.'}
        </span>
      </div>
    </div>
  );
}
