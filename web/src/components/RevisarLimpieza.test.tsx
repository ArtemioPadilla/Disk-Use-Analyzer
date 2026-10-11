import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, screen, fireEvent, act } from '@testing-library/react';
import RevisarLimpieza from './RevisarLimpieza';
import { emit } from '../lib/events';
import { pedirLimpieza, type Accion } from '../lib/limpieza';

const run = vi.fn();
vi.mock('../hooks/useCleanupRunner', () => ({
  useCleanupRunner: () => ({ run, completed: new Set<string>(), running: new Set<string>(), error: null, reset: vi.fn() }),
}));

const acc = (clave: string, consecuencia: Accion['consecuencia'], estimado = 1e9): Accion => ({
  clave, titulo: clave, detalle: `detalle ${clave}`, consecuencia, estimado, command: `cmd-${clave}`,
});
const ACCIONES = [acc('logs', 'regenera'), acc('docker', 'redescarga'), acc('papelera', 'permanente')];

beforeEach(() => {
  run.mockClear();
  // Page mode loads the latest analysis on mount; keep that offline.
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
});
afterEach(cleanup);

const abrir = (marcadas?: string[]) => act(() => pedirLimpieza({ acciones: ACCIONES, marcadas }));
const casilla = (nombre: string) => screen.getByRole('checkbox', { name: nombre }) as HTMLInputElement;

describe('RevisarLimpieza (hoja)', () => {
  it('abrirla no ejecuta nada, y solo viene marcado lo que vuelve solo', () => {
    render(<RevisarLimpieza />);
    abrir();
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(casilla('logs').checked).toBe(true);
    expect(casilla('docker').checked).toBe(false);
    expect(casilla('papelera').checked).toBe(false);
    expect(run).not.toHaveBeenCalled();
  });

  it('cancelar no ejecuta nada', () => {
    render(<RevisarLimpieza />);
    abrir();
    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(run).not.toHaveBeenCalled();
  });

  it('solo ejecuta lo marcado, y avisa si algo no se puede deshacer', () => {
    render(<RevisarLimpieza />);
    abrir();
    fireEvent.click(casilla('papelera'));
    expect(screen.getByText('Includes items that cannot be undone.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /^Free ~/ }));
    expect(run.mock.calls.map(c => c[0].command)).toEqual(['cmd-logs', 'cmd-papelera']);
  });

  it('muestra lo medido de cada elemento, no la estimación, y los fallos', () => {
    render(<RevisarLimpieza />);
    abrir(['logs', 'docker']);
    fireEvent.click(screen.getByRole('button', { name: /^Free ~/ }));
    act(() => emit('cleanup:completed', { command: 'cmd-logs', space: 300 * 1024 * 1024, estimado: 1e9 }));
    act(() => emit('cleanup:failed', { command: 'cmd-docker', motivo: 'Exited with code 1' }));
    expect(screen.getByText(/^✓ 300\.00 MB freed$/)).toBeTruthy();
    expect(screen.getByText('✗ Exited with code 1')).toBeTruthy();
    expect(screen.getByText(/freed \(measured\)/)).toBeTruthy();
    expect(screen.getByText('Done')).toBeTruthy();
  });

  it('dice la verdad cuando un comando no liberó nada', () => {
    render(<RevisarLimpieza />);
    abrir(['logs']);
    fireEvent.click(screen.getByRole('button', { name: /^Free ~/ }));
    act(() => emit('cleanup:completed', { command: 'cmd-logs', space: 0, estimado: 1e9 }));
    expect(screen.getByText('✓ Done · nothing measurable freed')).toBeTruthy();
  });
});

describe('RevisarLimpieza (página)', () => {
  it('sin ningún análisis lo dice y ofrece hacer uno', async () => {
    render(<RevisarLimpieza modo="pagina" />);
    expect(await screen.findByText('No analysis yet')).toBeTruthy();
  });

  it('un informe antiguo no ofrece nada que ejecutar y lo explica', () => {
    render(<RevisarLimpieza modo="pagina" />);
    act(() => emit('analysis:completed', {
      results: [{ report: { recommendations: [
        { tier: 1, priority: '', type: 'Logs', description: '', space: 5, command: "rm -rf '/Users/x/Library/Logs/*'" },
      ] } }],
    }));
    expect(screen.getByText(/older version/)).toBeTruthy();
    expect(screen.queryByRole('checkbox')).toBeNull();
  });
});

describe('invariante', () => {
  it('ningún componente salvo la hoja de revisión puede ejecutar limpiezas', () => {
    const fuentes = import.meta.glob(['./*.tsx', './*.ts', '!./*.test.*'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
    expect(Object.keys(fuentes).length).toBeGreaterThan(10);
    const culpables = Object.entries(fuentes)
      .filter(([f]) => f !== './RevisarLimpieza.tsx')
      .filter(([, codigo]) => /\brun\b[^}]*\}\s*=\s*useCleanupRunner\(|useCleanupRunner\(\)\s*\.\s*run\b/.test(codigo))
      .map(([f]) => f);
    expect(culpables).toEqual([]);
  });
});
