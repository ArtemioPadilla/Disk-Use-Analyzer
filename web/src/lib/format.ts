const UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const val = bytes / Math.pow(1024, i);
  return `${val.toFixed(i === 0 ? 0 : 2)} ${UNITS[i]}`;
}

export function formatAge(days: number): string {
  if (days < 1) return 'Hoy';
  if (days < 7) return `${days}d`;
  if (days < 30) return `${Math.floor(days / 7)}sem`;
  if (days < 365) return `${Math.floor(days / 30)}m`;
  return `${(days / 365).toFixed(1)}a`;
}

export function formatPercent(value: number, total: number): string {
  if (total === 0) return '0%';
  return `${((value / total) * 100).toFixed(1)}%`;
}

const PATH_DESCRIPTIONS: [RegExp, string][] = [
  [/\/Library\/Developer\/CoreSimulator\/Caches/i, 'Xcode Simulator Caches'],
  [/\/Library\/Developer\/CoreSimulator\/Devices/i, 'Xcode Simulator Devices'],
  [/\/Library\/Caches\/com\.apple\.dt\.Xcode/i, 'Xcode Build Cache'],
  [/\/Library\/Developer\/Xcode\/DerivedData/i, 'Xcode Derived Data'],
  [/\/Library\/Developer\/Xcode\/Archives/i, 'Xcode Archives'],
  [/\/Library\/Developer\/Xcode\/iOS DeviceSupport/i, 'Xcode Device Support'],
  [/\.npm\/_cacache/i, 'npm Package Cache'],
  [/\/node_modules/i, 'Node.js Dependencies'],
  [/\.cache\/yarn/i, 'Yarn Package Cache'],
  [/\.pnpm-store/i, 'pnpm Package Store'],
  [/\/Library\/Caches\/Homebrew/i, 'Homebrew Cache'],
  [/\/Library\/Caches\/pip/i, 'Python pip Cache'],
  [/\.cargo\/registry/i, 'Rust Cargo Cache'],
  [/\.gradle\/caches/i, 'Gradle Build Cache'],
  [/\.m2\/repository/i, 'Maven Repository Cache'],
  [/\/Library\/Caches\/Google\/Chrome/i, 'Chrome Browser Cache'],
  [/\/Library\/Caches\/com\.spotify/i, 'Spotify Cache'],
  [/\/Library\/Caches\/com\.microsoft\.VSCode/i, 'VS Code Cache'],
  [/\/Library\/Application Support\/Docker/i, 'Docker Desktop Data'],
  [/Docker\.raw/i, 'Docker Disk Image'],
  [/\/Library\/Application Support\/Slack/i, 'Slack App Data'],
  [/\/Library\/Application Support\/discord/i, 'Discord App Data'],
  [/\/Library\/Logs/i, 'System Logs'],
  [/\/Library\/Caches\/CloudKit/i, 'iCloud Cache'],
  [/\/Library\/Caches\/com\.apple\.Safari/i, 'Safari Cache'],
  [/\/\.Trash/i, 'Trash'],
  [/\/Downloads\//i, 'Downloads'],
  [/\/Library\/Mail/i, 'Mail App Data'],
  [/\/Music\/Music\/Media/i, 'Music Library'],
  [/\/Photos Library/i, 'Photos Library'],
  [/\/Library\/Application Support\/MobileSync/i, 'iOS Backups'],
  [/\/Library\/Containers/i, 'App Sandbox Data'],
  [/\/\.continue/i, 'Continue AI Cache'],
  [/\/\.vscode/i, 'VS Code Settings'],
  [/\/.local\/share\/Trash/i, 'Trash (Linux)'],
];

export function describePath(path: string): string | null {
  for (const [pattern, description] of PATH_DESCRIPTIONS) {
    if (pattern.test(path)) return description;
  }
  return null;
}
