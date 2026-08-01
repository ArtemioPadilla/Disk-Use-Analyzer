/**
 * AuthErrorBanner — persistent component mounted in MainLayout.
 *
 * Shows a fixed top banner when the server rejects the token in
 * sessionStorage (HTTP 401 on a REST call, or WebSocket close code 1008).
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

const MESSAGE =
  'Session expired or invalid token. The server prints a new link with a fresh token every time it starts — open that link again to reconnect.';

export default function AuthErrorBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => on(AUTH_INVALID_EVENT, () => setVisible(true)), []);

  if (!visible) return null;

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
      <span>{MESSAGE}</span>
      <button
        onClick={() => setVisible(false)}
        aria-label="Dismiss"
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
