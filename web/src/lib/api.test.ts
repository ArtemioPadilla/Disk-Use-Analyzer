/**
 * Qué hace `request()` cuando el API deja de responder.
 *
 * Son dos fallos distintos y hasta ahora solo uno estaba cubierto:
 *
 * - **401**: hay servidor, pero rechaza el token. Ya avisaba.
 * - **Sin conexión**: no hay servidor. `fetch` rechaza antes de que exista
 *   ninguna respuesta que mirar, así que se colaba por debajo de todas las
 *   ramas: la pestaña llenaba la consola de ERR_CONNECTION_REFUSED y la
 *   página parecía colgada, sin decir nada.
 *
 * El segundo caso pasa de forma rutinaria: la app de bandeja arranca este
 * servidor y lo mata al salir, dejando las pestañas abiertas apuntando a un
 * puerto muerto.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api, SERVER_DOWN_EVENT } from './api';
import { AUTH_INVALID_EVENT } from './auth';

function espiarEvento(nombre: string) {
  const espia = vi.fn();
  window.addEventListener(nombre, espia);
  return { espia, quitar: () => window.removeEventListener(nombre, espia) };
}

describe('request cuando el API no responde', () => {
  beforeEach(() => {
    vi.resetModules();
    sessionStorage.clear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // Va el primero a propósito: el aviso de servidor caído se deduplica por
  // carga de página, así que si este test corriera después, el "no se avisó"
  // pasaría por el deduplicado en vez de por la lógica.
  it('un 401 sigue avisando de token inválido, no de servidor caído', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ status: 401, ok: false, text: async () => '' }),
    );
    const { espia: espiaAuth, quitar: q1 } = espiarEvento(AUTH_INVALID_EVENT);
    const { espia: espiaCaido, quitar: q2 } = espiarEvento(SERVER_DOWN_EVENT);
    try {
      await expect(api.createTerminal()).rejects.toThrow(/401/);
      expect(espiaAuth).toHaveBeenCalled();
      expect(espiaCaido).not.toHaveBeenCalled();
    } finally {
      q1();
      q2();
    }
  });

  it('avisa de que el servidor no está cuando fetch ni siquiera conecta', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    );
    const { espia, quitar } = espiarEvento(SERVER_DOWN_EVENT);
    try {
      await expect(api.createTerminal()).rejects.toThrow(
        /No se pudo conectar con el servidor/,
      );
      expect(espia).toHaveBeenCalled();
    } finally {
      quitar();
    }
  });

  it('no confunde un servidor caído con un token caducado', async () => {
    // Decir "sesión caducada" cuando no hay nadie escuchando manda al usuario
    // a buscar el problema donde no está.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    );
    const { espia: espiaAuth, quitar } = espiarEvento(AUTH_INVALID_EVENT);
    try {
      await expect(api.createTerminal()).rejects.toThrow();
      expect(espiaAuth).not.toHaveBeenCalled();
    } finally {
      quitar();
    }
  });

});
