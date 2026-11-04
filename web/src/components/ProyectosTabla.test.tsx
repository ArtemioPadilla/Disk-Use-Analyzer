import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import ProyectosTabla, { type Artefacto } from './ProyectosTabla';
import { pedirLimpieza } from '../lib/limpieza';

vi.mock('../lib/limpieza', () => ({ pedirLimpieza: vi.fn() }));

const art = (extra: Partial<Artefacto>): Artefacto => ({
  id: 'proyecto:/p/node_modules',
  titulo: 'p · node_modules',
  ruta: '/p/node_modules',
  space: 5000,
  dias: 40,
  worktree: false,
  reproducible: true,
  ignorado: true,
  command: 'rm -rf /p/node_modules',
  ...extra,
});

function conLista(proyectos: Artefacto[]) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ proyectos }) })));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('ProyectosTabla', () => {
  it('limpiar pasa por la hoja de revisión, nunca ejecuta nada', async () => {
    conLista([art({})]);
    render(<ProyectosTabla />);
    fireEvent.click(await screen.findByText('Limpiar…'));
    expect(pedirLimpieza).toHaveBeenCalledTimes(1);
    const { acciones } = vi.mocked(pedirLimpieza).mock.calls[0][0];
    expect(acciones[0].consecuencia).toBe('regenera');
    expect(acciones[0].command).toBe('rm -rf /p/node_modules');
  });

  it('lo que no se ofrece dice por qué, sin botón', async () => {
    conLista([art({ command: '', ignorado: false })]);
    render(<ProyectosTabla />);
    expect(await screen.findByText(/git no lo ignora/)).toBeTruthy();
    expect(screen.queryByText('Limpiar…')).toBeNull();
  });
});
