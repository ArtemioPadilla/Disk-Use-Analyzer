import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import FileTable from './FileTable';

const archivo = (path: string, size: number, age_days: number) => ({
  path, size, age_days, extension: '', modified: '', is_protected: false,
});

function conResultados(large_files: unknown[]) {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ results: [{ report: { large_files } }] }),
  })));
}

describe('FileTable abierta con un enlace directo', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/files');
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('carga el último análisis sin esperar a que otra página lo emita', async () => {
    conResultados([archivo('/Users/u/grande.bin', 5000, 1)]);
    render(<FileTable />);
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      '/api/analysis/latest',
      expect.anything(),
    ));
    await waitFor(() => expect(screen.queryByText('No files to display')).toBeNull());
  });

  it('entiende ?exts= para un grupo y se puede quitar', async () => {
    window.history.replaceState({}, '', '/files?exts=.mp4,.mov');
    conResultados([archivo('/Users/u/a.mp4', 5000, 1)]);
    render(<FileTable />);
    const quitar = await screen.findByText(/Quitar filtro: .mp4, .mov/);
    fireEvent.click(quitar);
    expect(screen.queryByText(/Quitar filtro/)).toBeNull();
  });

  it('entiende ?path= y ?orden=antiguedad', async () => {
    window.history.replaceState({}, '', '/files?path=/Downloads/&orden=antiguedad');
    conResultados([archivo('/Users/u/Downloads/viejo.dmg', 5000, 400)]);
    render(<FileTable />);
    const buscador = await screen.findByPlaceholderText('Search files...');
    expect((buscador as HTMLInputElement).value).toBe('/Downloads/');
  });
});
