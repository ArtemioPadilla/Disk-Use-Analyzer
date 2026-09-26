import { describe, it, expect } from 'vitest';
import { planDe, preseleccion, totalEstimado } from './limpieza';
import type { Recommendation } from './api';

const rec = (over: Partial<Recommendation>): Recommendation => ({
  tier: 1, priority: '', type: 'Tipo', description: 'desc', space: 1000, command: 'cmd', efecto: 'borra', ...over,
});

describe('planDe', () => {
  it('agrupa por consecuencia y solo preselecciona lo que vuelve solo', () => {
    const plan = planDe([
      rec({ id: 'logs', command: 'rm logs', consecuencia: 'regenera' }),
      rec({ id: 'docker', command: 'docker system prune -a -f', consecuencia: 'redescarga', efecto: 'irreversible' }),
      rec({ id: 'papelera', command: 'rm trash', consecuencia: 'permanente' }),
    ]);
    expect(plan.acciones.map(a => a.consecuencia)).toEqual(['regenera', 'redescarga', 'permanente']);
    expect([...preseleccion(plan.acciones)]).toEqual(['logs']);
  });

  it('lo que solo lista va aparte y no suma como liberable', () => {
    const plan = planDe([
      rec({ id: 'logs', space: 10, consecuencia: 'regenera' }),
      rec({ id: 'descargas', command: 'find ~/Downloads -ls', space: 5000, efecto: 'solo_lista', consecuencia: 'solo_lista' }),
      rec({ id: 'gigantes', command: '# Revisa la lista', space: 9000, efecto: 'solo_lista' }),
    ]);
    expect(plan.acciones.map(a => a.clave)).toEqual(['logs']);
    expect(totalEstimado(plan.acciones)).toBe(10);
    expect(plan.paraRevisar.map(r => r.id)).toEqual(['descargas', 'gigantes']);
  });

  it('un informe sin marcas de seguridad no ofrece nada que ejecutar', () => {
    // Tal cual venía en un informe de abril: el glob entre comillas no borraba nada.
    const plan = planDe([rec({ efecto: undefined, command: "rm -rf '/Users/x/Library/Logs/*'" })]);
    expect(plan.acciones).toEqual([]);
    expect(plan.informeAntiguo).toBe(true);
  });

  it('sin consecuencia declarada se trata como irreversible y no se preselecciona', () => {
    const plan = planDe([rec({ id: 'rara', consecuencia: undefined })]);
    expect(plan.acciones[0].consecuencia).toBe('permanente');
    expect(preseleccion(plan.acciones).size).toBe(0);
  });

  it('no repite un mismo comando', () => {
    const plan = planDe([rec({ id: 'a', consecuencia: 'regenera' }), rec({ id: 'b', consecuencia: 'regenera' })]);
    expect(plan.acciones).toHaveLength(1);
  });
});
