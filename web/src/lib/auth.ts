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
