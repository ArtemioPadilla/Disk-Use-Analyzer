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
  status: 'running' | 'completed' | 'error';
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
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
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
  getExportUrl: (id: string, format: 'json' | 'csv' | 'html') =>
    `${BASE}/export/${id}/${format}`,
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
};
