/**
 * AuthErrorBanner — persistent component mounted in MainLayout.
 *
 * Shows a fixed top banner for the two ways the API stops answering: the
 * server rejects the token in sessionStorage (HTTP 401, or WebSocket close
 * code 1008), or the server is not reachable at all (the fetch rejects before
 * there is any response).
 * This is the ordinary "restart the server, reload the tab" flow — the
 * server mints a fresh token per run, so the browser's cached one goes
 * stale and every request/socket fails until the user opens the new
 * token link.
 *
 * A toast (see ToastNotification) auto-dismisses after a few seconds,
 * which is wrong for this message: the user has to go find the new link
 * the server printed, which takes longer than that. A banner that stays
 * until dismissed is more appropriate here.
 */
import { useState, useEffect } from 'react';
import { on } from '../lib/events';
import { AUTH_INVALID_EVENT } from '../lib/auth';
import { SERVER_DOWN_EVENT } from '../lib/api';

// Both messages point at the same remedy — reopen the link — but naming the
// actual cause matters: "sesión caducada" sends the user looking for a login
// that does not exist, when the real problem is that nothing is listening.
const MENSAJE_SESION =
  'Sesión caducada o token inválido. El servidor genera un enlace con un token nuevo cada vez que arranca: vuelve a abrir ese enlace para reconectar.';

const MENSAJE_SERVIDOR_CAIDO =
  'No hay conexión con el servidor: no está corriendo. Si lo abriste desde el icono de la barra, vuelve a pulsar "Abrir analizador completo" — el servidor se cierra junto con la app, y al arrancar de nuevo genera otro token, así que esta pestaña ya no vale.';

export default function AuthErrorBanner() {
  const [mensaje, setMensaje] = useState<string | null>(null);

  useEffect(() => on(AUTH_INVALID_EVENT, () => setMensaje(MENSAJE_SESION)), []);
  // El servidor caído gana: si no hay nadie escuchando, hablar de tokens
  // manda al usuario a buscar el problema donde no está.
  useEffect(() => on(SERVER_DOWN_EVENT, () => setMensaje(MENSAJE_SERVIDOR_CAIDO)), []);

  if (!mensaje) return null;

  return (
    <div
      role="alert"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '1rem',
        background: 'var(--danger)',
        color: 'white',
        padding: '0.75rem 1.25rem',
        fontSize: '0.9rem',
        fontWeight: 500,
        boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
      }}
    >
      <span>{mensaje}</span>
      <button
        onClick={() => setMensaje(null)}
        aria-label="Descartar"
        style={{
          background: 'transparent',
          border: '1px solid rgba(255,255,255,0.6)',
          borderRadius: '4px',
          color: 'white',
          cursor: 'pointer',
          padding: '0.15rem 0.5rem',
          lineHeight: 1,
          flexShrink: 0,
        }}
      >
        ×
      </button>
    </div>
  );
}
