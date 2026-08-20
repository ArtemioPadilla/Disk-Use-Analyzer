// Single source of truth for how a filesystem path is bucketed into a
// display category. Moved verbatim from DiskBar.tsx / FileTable.tsx, where
// this logic was duplicated word-for-word.

export const CATEGORY_COLORS: Record<string, string> = {
  'Development': '#6366f1',
  'Docker': '#3b82f6',
  'Caches & Logs': '#f59e0b',
  'System Library': '#8b5cf6',
  'Documents': '#10b981',
  'Media': '#ec4899',
  'Other': '#6b7280',
};

export function getCategory(path: string): string {
  const p = path.toLowerCase();
  if (p.includes('node_modules') || p.includes('.npm') || p.includes('.cargo') || p.includes('.rustup') || p.includes('.gradle') || p.includes('developer/')) return 'Development';
  if (p.includes('docker') || p.includes('Docker.raw')) return 'Docker';
  if (p.includes('/caches/') || p.includes('/cache/') || p.includes('/tmp/') || p.includes('/logs/')) return 'Caches & Logs';
  if (p.includes('/library/')) return 'System Library';
  if (p.includes('/documents/') || p.includes('/desktop/') || p.includes('/downloads/')) return 'Documents';
  if (p.match(/\.(mp4|mov|avi|mkv|mp3|wav|flac|jpg|jpeg|png|gif|psd|raw)$/i)) return 'Media';
  return 'Other';
}
