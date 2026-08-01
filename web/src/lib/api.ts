import { authHeaders, notifyAuthInvalid } from './auth';

const BASE = '/api';

export interface SystemInfo {
  platform: string;
  hostname: string;
  disk_usage: { total: number; used: number; free: number };
}

export interface DriveInfo {
  path: string;
  label: string;
  size?: number;
}

export interface AnalysisRequest {
  paths: string[];
  min_size_mb?: number;
}

export interface AnalysisSession {
  id: string;
  status: 'running' | 'completed' | 'error' | 'cancelled';
  progress: number;
  current_path: string;
  paths: string[];
  started_at: string;
  completed_at?: string;
  error?: string;
}

export interface LargeFile {
  path: string;
  size: number;
  age_days: number;
  extension: string;
  is_cache: boolean;
  is_protected: boolean;
}

export interface Recommendation {
  tier: number;
  priority: string;
  type: string;
  description: string;
  space: number;
  command: string;
}

export interface AnalysisReport {
  summary: {
    total_size: number;
    files_scanned: number;
    large_files_count: number;
    cache_size: number;
    old_files_size: number;
    recoverable_space: number;
    disk_usage: { total: number; used: number; free: number };
    docker_space: number;
    docker_reclaimable: number;
  };
  large_files: LargeFile[];
  cache_locations: { path: string; size: number; type: string }[];
  top_directories: [string, number][];
  file_types: [string, { count: number; size: number }][];
  recommendations: Recommendation[];
  docker: Record<string, any>;
  errors: string[];
}

export interface SessionResult {
  path: string;
  report: AnalysisReport;
  summary: Record<string, any>;
}

export interface SessionResults {
  id: string;
  status: string;
  results: SessionResult[];
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(options?.headers ?? {}) },
  });
  if (res.status === 401) {
    // Stale/invalid token — most commonly because the server was restarted
    // (it mints a new token per run) and this tab still has the old one in
    // sessionStorage. Surface this distinctly instead of letting it look
    // like a generic failure (e.g. "empty dashboard, no explanation").
    notifyAuthInvalid();
    throw new Error(`API 401: invalid or expired token`);
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

/** Pull a filename out of a Content-Disposition header, if the server sent one. */
function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  // RFC 5987 extended form (filename*=UTF-8''...) takes priority when present.
  const extended = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (extended) return decodeURIComponent(extended[1]);
  const simple = header.match(/filename="?([^";]+)"?/i);
  return simple ? simple[1] : null;
}

/**
 * Download an export using an authenticated fetch instead of a plain link.
 *
 * `window.open`/`<a href>` navigation cannot attach the `X-Auth-Token`
 * header, so with auth enabled a direct link to `/api/export/...` always
 * returns 401. Fetching the blob ourselves keeps the token in a header
 * (never in a URL, browser history, or server access log) and lets us
 * trigger a normal browser download via a temporary object URL.
 */
export async function downloadExport(id: string, format: 'json' | 'csv' | 'html'): Promise<void> {
  const res = await fetch(`${BASE}/export/${id}/${format}`, { headers: authHeaders() });
  if (res.status === 401) {
    notifyAuthInvalid();
    throw new Error('Export failed (401): invalid or expired token');
  }
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`Export failed (${res.status}): ${body || res.statusText}`);
  }
  const blob = await res.blob();
  const fallbackPrefix = format === 'html' ? 'disk_report' : 'disk_analysis';
  const filename = filenameFromContentDisposition(res.headers.get('Content-Disposition'))
    ?? `${fallbackPrefix}_${id}.${format}`;

  const objectUrl = URL.createObjectURL(blob);
  try {
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export const api = {
  getSystemInfo: () => request<SystemInfo>('/system/info'),
  getDrives: () => request<any>('/system/drives'),
  startAnalysis: (req: AnalysisRequest) =>
    request<{ session_id: string }>('/analysis/start', {
      method: 'POST',
      body: JSON.stringify(req),
    }),
  getProgress: (id: string) => request<AnalysisSession>(`/analysis/${id}/progress`),
  getResults: (id: string) => request<SessionResults>(`/analysis/${id}/results`),
  cancelAnalysis: (id: string) =>
    request<any>(`/analysis/${id}/cancel`, { method: 'POST' }),
  getSessions: () => request<AnalysisSession[]>('/sessions'),
  previewCleanup: (paths: string[]) =>
    request<any>('/cleanup/preview', {
      method: 'POST',
      body: JSON.stringify({ paths, dry_run: true }),
    }),
  executeCleanup: (paths: string[]) =>
    request<any>('/cleanup/execute', {
      method: 'POST',
      body: JSON.stringify({ paths, dry_run: false }),
    }),
  deleteFile: (path: string) =>
    request<any>('/files/delete', {
      method: 'DELETE',
      body: JSON.stringify({ path }),
    }),
  createTerminal: (command?: string) =>
    request<{ pty_id: string; created_at: string }>('/terminal/create', {
      method: 'POST',
      body: JSON.stringify({ command }),
    }),
  resizeTerminal: (ptyId: string, cols: number, rows: number) =>
    request<any>(`/terminal/${ptyId}/resize`, {
      method: 'POST',
      body: JSON.stringify({ cols, rows }),
    }),
  killTerminal: (ptyId: string) =>
    request<any>(`/terminal/${ptyId}`, { method: 'DELETE' }),
  getTerminalSessions: () =>
    request<any[]>('/terminal/sessions'),
  getPersona: () => request<any>('/persona'),
};
