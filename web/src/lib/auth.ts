// Token bootstrap + helpers for authenticated API/WS access.
//
// The server prints a `http://host:8000/?token=XXXX` link at startup. On first
// load we pull that token out of the URL, stash it in sessionStorage, and
// strip it from the address bar/history so it doesn't linger in bookmarks,
// browser history, or get accidentally shared. Every REST call and WebSocket
// connection afterwards reads the token back out of sessionStorage.
//
// NOTE: this module's bootstrap() also runs from an inline <script> in
// MainLayout.astro's <head> (see that file for why) so the token is stripped
// from the URL on first paint, before any island hydrates. Both copies are
// idempotent — by the time this module-level bootstrap() runs, the URL has
// usually already been cleaned by the inline script, so `urlToken` is null
// and this is a no-op.
const KEY = 'da_token';

// Event fired when the server rejects the current token (HTTP 401 on a REST
// call, or WebSocket close code 1008). The server mints a brand-new token on
// every restart while the browser keeps the old one in sessionStorage, so
// this fires on the ordinary "restart the server, reload the tab" flow.
export const AUTH_INVALID_EVENT = 'auth:invalid';

// Several requests/sockets can fail around the same moment (e.g. a handful
// of parallel REST calls right after a server restart), so dedupe to a
// single notification per page load instead of one per failed call. This
// resets naturally on navigation/reload since it's plain module state and
// the app is a multi-page Astro site (see MainLayout.astro).
let authInvalidNotified = false;

export function notifyAuthInvalid(): void {
  if (typeof window === 'undefined' || authInvalidNotified) return;
  authInvalidNotified = true;
  window.dispatchEvent(new CustomEvent(AUTH_INVALID_EVENT));
}

function bootstrap(): void {
  if (typeof window === 'undefined') return;
  const params = new URLSearchParams(window.location.search);
  const urlToken = params.get('token');
  if (urlToken) {
    sessionStorage.setItem(KEY, urlToken);
    params.delete('token');
    const qs = params.toString();
    const clean = window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash;
    window.history.replaceState({}, '', clean);
  }
}

bootstrap();

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return sessionStorage.getItem(KEY);
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { 'X-Auth-Token': t } : {};
}

export function withToken(url: string): string {
  const t = getToken();
  if (!t) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}token=${encodeURIComponent(t)}`;
}
