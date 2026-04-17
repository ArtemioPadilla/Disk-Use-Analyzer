# Hosted Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a modern Astro + React web UI served by the existing FastAPI backend, with a floating terminal for live shell command execution.

**Architecture:** Astro static build in `web/` served by FastAPI from `web/dist/`. React islands for interactive components (charts, file table, terminal). New PTY Manager module on the backend for spawning shell sessions streamed over WebSocket to xterm.js in the browser.

**Tech Stack:** Astro 4+, React 18+, xterm.js, Plotly.js, @tanstack/react-virtual, FastAPI, Python pty module

**Spec:** `docs/superpowers/specs/2026-04-06-hosted-web-ui-design.md`

---

## File Structure

### New Files

```
web/                              # Astro project root
├── astro.config.mjs              # Astro config: React integration, output static
├── package.json                  # Dependencies
├── tsconfig.json                 # TypeScript config
├── src/
│   ├── layouts/
│   │   └── MainLayout.astro      # Shell: sidebar + topbar + terminal slot
│   ├── pages/
│   │   ├── index.astro           # Dashboard
│   │   ├── files.astro           # File Browser
│   │   ├── cleanup.astro         # Cleanup Recommendations
│   │   ├── export.astro          # Export Options
│   │   └── history.astro         # Past Sessions
│   ├── components/
│   │   ├── Sidebar.astro         # Static nav links
│   │   ├── TopBar.astro          # Page header + actions
│   │   ├── StatsCards.tsx        # Summary stat cards
│   │   ├── CategoryChart.tsx     # Plotly Sankey/Treemap
│   │   ├── DiskDonut.tsx         # Plotly donut chart
│   │   ├── TaskList.tsx          # Background task tracker
│   │   ├── FileTable.tsx         # Virtual-scroll file table
│   │   ├── CleanupWizard.tsx     # Tiered cleanup flow
│   │   ├── ExportPanel.tsx       # Export format picker
│   │   ├── SessionList.tsx       # History list + compare
│   │   └── FloatingTerminal.tsx  # xterm.js terminal overlay
│   ├── hooks/
│   │   ├── useWebSocket.ts       # WS connection + auto-reconnect
│   │   ├── useAnalysis.ts        # Analysis session CRUD + progress
│   │   └── useTerminal.ts        # PTY session management
│   └── lib/
│       ├── api.ts                # REST API client (typed)
│       ├── events.ts             # Cross-island event bus
│       └── format.ts             # formatBytes, formatAge utilities
├── public/
│   └── favicon.svg
```

```
pty_manager.py                    # New: PTY session management module
tests/
├── test_pty_manager.py           # PTY manager unit tests
├── test_terminal_api.py          # Terminal endpoint integration tests
```

### Modified Files

```
disk_analyzer_web.py              # Add: terminal endpoints, serve web/dist/, HTML export
.gitignore                        # Add: web/node_modules/, web/dist/, web/.astro/
requirements-web.txt              # No changes needed (pty is stdlib)
```

---

## Task 1: Scaffold Astro Project

**Files:**
- Create: `web/package.json`
- Create: `web/astro.config.mjs`
- Create: `web/tsconfig.json`
- Create: `web/src/pages/index.astro` (placeholder)
- Create: `web/public/favicon.svg`

- [ ] **Step 1: Initialize Astro project**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer
mkdir -p web/src/pages web/src/layouts web/src/components web/src/hooks web/src/lib web/public
```

- [ ] **Step 2: Create package.json**

Create `web/package.json`:

```json
{
  "name": "disk-analyzer-web",
  "type": "module",
  "version": "2.0.0",
  "scripts": {
    "dev": "astro dev --port 3000",
    "build": "astro build",
    "preview": "astro preview"
  },
  "dependencies": {
    "astro": "^4.16.0",
    "@astrojs/react": "^3.6.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "@xterm/xterm": "^5.5.0",
    "@xterm/addon-fit": "^0.10.0",
    "plotly.js-dist-min": "^2.35.0",
    "@tanstack/react-virtual": "^3.10.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "typescript": "^5.6.0"
  }
}
```

- [ ] **Step 3: Create astro.config.mjs**

Create `web/astro.config.mjs`:

```javascript
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

export default defineConfig({
  integrations: [react()],
  output: 'static',
  outDir: './dist',
  server: { port: 3000 },
  vite: {
    server: {
      proxy: {
        '/api': 'http://localhost:8000',
        '/ws': {
          target: 'ws://localhost:8000',
          ws: true,
        },
      },
    },
  },
});
```

- [ ] **Step 4: Create tsconfig.json**

Create `web/tsconfig.json`:

```json
{
  "extends": "astro/tsconfigs/strict",
  "compilerOptions": {
    "jsx": "react-jsx",
    "jsxImportSource": "react"
  }
}
```

- [ ] **Step 5: Create placeholder index page**

Create `web/src/pages/index.astro`:

```astro
---
---
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Disk Analyzer</title>
  </head>
  <body>
    <h1>Disk Analyzer v2</h1>
    <p>Scaffolding works.</p>
  </body>
</html>
```

- [ ] **Step 6: Create favicon**

Create `web/public/favicon.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36"><text y="32" font-size="32">💿</text></svg>
```

- [ ] **Step 7: Update .gitignore**

Append to `.gitignore`:

```
web/node_modules/
web/dist/
web/.astro/
```

- [ ] **Step 8: Install dependencies and verify build**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm install
npm run build
```

Expected: Build succeeds, `web/dist/` directory created with `index.html`.

- [ ] **Step 9: Commit**

```bash
git add web/ .gitignore
git commit -m "feat: scaffold Astro project with React integration"
```

---

## Task 2: Configure FastAPI to Serve Astro Build

**Files:**
- Modify: `disk_analyzer_web.py` (lines 125-130 static mount, lines 801-820 startup)

- [ ] **Step 1: Read current static serving code**

Read `disk_analyzer_web.py` lines 120-135 to understand the current StaticFiles mount.

- [ ] **Step 2: Modify FastAPI to serve Astro build as primary, old static as fallback**

In `disk_analyzer_web.py`, replace the static file mount section (around lines 125-130) and add a catch-all route for Astro's client-side routing. Add these imports at the top if not present:

```python
from fastapi.responses import FileResponse
```

Replace the static mount block:

```python
# Serve new Astro frontend from web/dist/ if it exists, else fall back to static/
astro_dist = Path(__file__).parent / "web" / "dist"
static_dir = Path(__file__).parent / "static"

if astro_dist.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="legacy_static")
    # Mount Astro's built assets (CSS, JS, etc.)
    astro_assets = astro_dist / "_astro"
    if astro_assets.exists():
        app.mount("/_astro", StaticFiles(directory=str(astro_assets)), name="astro_assets")
else:
    if not static_dir.exists():
        static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
```

Then, at the **bottom** of the file (after all API routes but before `if __name__ == "__main__"`), add a catch-all route for Astro pages:

```python
@app.get("/{path:path}")
async def serve_astro(path: str):
    """Serve Astro frontend pages. API routes take priority (registered first)."""
    astro_dist = Path(__file__).parent / "web" / "dist"
    if not astro_dist.exists():
        # Fall back to legacy frontend
        return FileResponse(str(Path(__file__).parent / "static" / "index.html"))
    
    # Try exact file first (e.g., /files → /files/index.html or /files.html)
    for candidate in [
        astro_dist / path / "index.html",
        astro_dist / f"{path}.html",
        astro_dist / path,
    ]:
        if candidate.is_file():
            return FileResponse(str(candidate))
    
    # Default to index
    index = astro_dist / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return FileResponse(str(Path(__file__).parent / "static" / "index.html"))
```

Also add a root route override (place it **before** the catch-all):

```python
@app.get("/", include_in_schema=False)
async def serve_root():
    """Serve the Astro index or legacy index."""
    astro_index = Path(__file__).parent / "web" / "dist" / "index.html"
    if astro_index.is_file():
        return FileResponse(str(astro_index))
    return FileResponse(str(Path(__file__).parent / "static" / "index.html"))
```

- [ ] **Step 3: Test that the server starts and serves the Astro build**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm run build
cd ..
python -c "
from disk_analyzer_web import app
from fastapi.testclient import TestClient
client = TestClient(app)
r = client.get('/')
assert r.status_code == 200
assert 'Disk Analyzer' in r.text
print('Root serves Astro build: OK')

r2 = client.get('/api/system/info')
assert r2.status_code == 200
print('API still works: OK')
"
```

Expected: Both assertions pass.

- [ ] **Step 4: Commit**

```bash
git add disk_analyzer_web.py
git commit -m "feat: serve Astro build from FastAPI with legacy fallback"
```

---

## Task 3: Shared Layout, Sidebar, and TopBar

**Files:**
- Create: `web/src/layouts/MainLayout.astro`
- Create: `web/src/components/Sidebar.astro`
- Create: `web/src/components/TopBar.astro`
- Modify: `web/src/pages/index.astro`

- [ ] **Step 1: Create the global CSS**

Create `web/src/layouts/global.css`:

```css
:root {
  --primary: #6366f1;
  --primary-dark: #4f46e5;
  --secondary: #8b5cf6;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --dark: #1f2937;
  --light: #f9fafb;
  --gray: #6b7280;
  --border: #e5e7eb;
  --card-bg: white;
  --page-bg: #f9fafb;
  --text: #1f2937;
  --text-muted: #6b7280;
  --sidebar-width: 210px;
  --topbar-height: 56px;
}

[data-theme="dark"] {
  --primary: #818cf8;
  --primary-dark: #6366f1;
  --secondary: #a78bfa;
  --dark: #111827;
  --light: #1f2937;
  --border: #374151;
  --card-bg: #1f2937;
  --page-bg: #111827;
  --text: #f9fafb;
  --text-muted: #9ca3af;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--page-bg);
  color: var(--text);
  overflow: hidden;
  height: 100vh;
}

.app-shell {
  display: flex;
  height: 100vh;
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-content {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

.btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn:hover { opacity: 0.9; }

.btn-primary { background: var(--primary); color: white; }
.btn-dark { background: var(--dark); color: var(--success); font-family: monospace; }
.btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); }

.card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1rem;
}
```

- [ ] **Step 2: Create Sidebar component**

Create `web/src/components/Sidebar.astro`:

```astro
---
const { currentPath } = Astro.props;

const navItems = [
  { href: '/', icon: '📊', label: 'Dashboard' },
  { href: '/files', icon: '📁', label: 'File Browser' },
  { href: '/cleanup', icon: '🧹', label: 'Cleanup' },
  { href: '/export', icon: '📤', label: 'Export' },
  { href: '/history', icon: '🕘', label: 'History' },
];
---

<aside class="sidebar">
  <div class="sidebar-header">
    <span class="sidebar-logo">💿</span>
    <span class="sidebar-title">Disk Analyzer</span>
  </div>

  <nav class="sidebar-nav">
    {navItems.map(item => (
      <a
        href={item.href}
        class:list={['nav-item', { active: currentPath === item.href }]}
      >
        <span class="nav-icon">{item.icon}</span>
        <span class="nav-label">{item.label}</span>
      </a>
    ))}
  </nav>

  <div class="sidebar-footer">
    <div class="nav-item" style="opacity: 0.6; font-size: 0.8rem;">⚙️ Settings</div>
    <div class="sidebar-meta" id="sidebar-meta">v2.0 · macOS</div>
  </div>
</aside>

<style>
  .sidebar {
    width: var(--sidebar-width);
    background: var(--dark);
    color: white;
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    padding: 1rem 0.75rem;
  }
  .sidebar-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0 0.5rem 1.25rem;
  }
  .sidebar-logo { font-size: 1.4rem; }
  .sidebar-title { font-weight: 700; font-size: 1rem; }
  .sidebar-nav { flex: 1; display: flex; flex-direction: column; gap: 2px; }
  .nav-item {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.6rem 0.75rem;
    border-radius: 8px;
    color: white;
    text-decoration: none;
    font-size: 0.9rem;
    opacity: 0.7;
    transition: all 0.15s;
  }
  .nav-item:hover { opacity: 1; background: rgba(255,255,255,0.08); }
  .nav-item.active { opacity: 1; background: var(--primary); }
  .sidebar-footer { border-top: 1px solid rgba(255,255,255,0.1); padding-top: 0.75rem; margin-top: 0.5rem; }
  .sidebar-meta { padding: 0.25rem 0.75rem; font-size: 0.65rem; color: rgba(255,255,255,0.4); }
</style>
```

- [ ] **Step 3: Create TopBar component**

Create `web/src/components/TopBar.astro`:

```astro
---
const { title } = Astro.props;
---

<header class="topbar">
  <h1 class="topbar-title">{title}</h1>
  <div class="topbar-actions">
    <a href="/" class="btn btn-primary" id="newAnalysisBtn">+ New Analysis</a>
    <button class="btn btn-dark" id="terminalToggleBtn">⚡ Terminal</button>
    <button class="btn btn-ghost" id="themeToggleBtn" aria-label="Toggle theme">🌙</button>
  </div>
</header>

<style>
  .topbar {
    height: var(--topbar-height);
    padding: 0 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--card-bg);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .topbar-title { font-size: 1.15rem; font-weight: 600; }
  .topbar-actions { display: flex; gap: 0.5rem; align-items: center; }
</style>

<script>
  // Theme toggle
  const themeBtn = document.getElementById('themeToggleBtn');
  function applyTheme() {
    const saved = localStorage.getItem('disk-analyzer-theme');
    const isDarkSystem = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = saved === 'dark' || (!saved && isDarkSystem);
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    if (themeBtn) themeBtn.textContent = isDark ? '☀️' : '🌙';
  }
  applyTheme();
  themeBtn?.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem('disk-analyzer-theme', next);
    document.documentElement.setAttribute('data-theme', next);
    themeBtn.textContent = next === 'dark' ? '☀️' : '🌙';
  });

  // Terminal toggle dispatches custom event (FloatingTerminal listens)
  document.getElementById('terminalToggleBtn')?.addEventListener('click', () => {
    window.dispatchEvent(new CustomEvent('terminal:toggle'));
  });
</script>
```

- [ ] **Step 4: Create MainLayout**

Create `web/src/layouts/MainLayout.astro`:

```astro
---
import Sidebar from '../components/Sidebar.astro';
import TopBar from '../components/TopBar.astro';
import '../layouts/global.css';

const { title, currentPath } = Astro.props;
---

<!DOCTYPE html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title} — Disk Analyzer</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
  </head>
  <body>
    <div class="app-shell">
      <Sidebar currentPath={currentPath} />
      <div class="main-area">
        <TopBar title={title} />
        <main class="page-content">
          <slot />
        </main>
      </div>
    </div>
    <div id="terminal-root"></div>
  </body>
</html>
```

- [ ] **Step 5: Update index.astro to use the layout**

Replace `web/src/pages/index.astro`:

```astro
---
import MainLayout from '../layouts/MainLayout.astro';
---

<MainLayout title="Dashboard" currentPath="/">
  <p>Dashboard content coming in Task 7.</p>
</MainLayout>
```

- [ ] **Step 6: Create stub pages for all routes**

Create `web/src/pages/files.astro`:

```astro
---
import MainLayout from '../layouts/MainLayout.astro';
---

<MainLayout title="File Browser" currentPath="/files">
  <p>File browser coming in Task 8.</p>
</MainLayout>
```

Create `web/src/pages/cleanup.astro`:

```astro
---
import MainLayout from '../layouts/MainLayout.astro';
---

<MainLayout title="Cleanup" currentPath="/cleanup">
  <p>Cleanup wizard coming in Task 9.</p>
</MainLayout>
```

Create `web/src/pages/export.astro`:

```astro
---
import MainLayout from '../layouts/MainLayout.astro';
---

<MainLayout title="Export" currentPath="/export">
  <p>Export panel coming in Task 11.</p>
</MainLayout>
```

Create `web/src/pages/history.astro`:

```astro
---
import MainLayout from '../layouts/MainLayout.astro';
---

<MainLayout title="History" currentPath="/history">
  <p>Session history coming in Task 12.</p>
</MainLayout>
```

- [ ] **Step 7: Build and verify all pages render**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm run build
ls dist/index.html dist/files/index.html dist/cleanup/index.html dist/export/index.html dist/history/index.html
```

Expected: All 5 HTML files exist.

- [ ] **Step 8: Commit**

```bash
git add web/src/
git commit -m "feat: main layout with sidebar navigation and stub pages"
```

---

## Task 4: API Client, Event Bus, and Utility Functions

**Files:**
- Create: `web/src/lib/api.ts`
- Create: `web/src/lib/events.ts`
- Create: `web/src/lib/format.ts`
- Create: `web/src/hooks/useWebSocket.ts`
- Create: `web/src/hooks/useAnalysis.ts`

- [ ] **Step 1: Create format utilities**

Create `web/src/lib/format.ts`:

```typescript
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
```

- [ ] **Step 2: Create event bus for cross-island communication**

Create `web/src/lib/events.ts`:

```typescript
type Listener = (data?: any) => void;

const listeners = new Map<string, Set<Listener>>();

export function emit(event: string, data?: any): void {
  window.dispatchEvent(new CustomEvent(event, { detail: data }));
}

export function on(event: string, listener: Listener): () => void {
  const handler = (e: Event) => listener((e as CustomEvent).detail);

  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event)!.add(handler as any);

  window.addEventListener(event, handler);
  return () => {
    window.removeEventListener(event, handler);
    listeners.get(event)?.delete(handler as any);
  };
}
```

- [ ] **Step 3: Create typed API client**

Create `web/src/lib/api.ts`:

```typescript
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
  // System
  getSystemInfo: () => request<SystemInfo>('/system/info'),
  getDrives: () => request<DriveInfo[]>('/system/drives'),

  // Analysis
  startAnalysis: (req: AnalysisRequest) =>
    request<{ session_id: string }>('/analysis/start', {
      method: 'POST',
      body: JSON.stringify(req),
    }),
  getProgress: (id: string) => request<AnalysisSession>(`/analysis/${id}/progress`),
  getResults: (id: string) => request<SessionResults>(`/analysis/${id}/results`),
  getSessions: () => request<AnalysisSession[]>('/sessions'),

  // Cleanup
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

  // Files
  deleteFile: (path: string) =>
    request<any>('/files/delete', {
      method: 'DELETE',
      body: JSON.stringify({ path }),
    }),

  // Export
  getExportUrl: (id: string, format: 'json' | 'csv' | 'html') =>
    `${BASE}/export/${id}/${format}`,

  // Terminal
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
```

- [ ] **Step 4: Create useWebSocket hook**

Create `web/src/hooks/useWebSocket.ts`:

```typescript
import { useEffect, useRef, useCallback, useState } from 'react';

interface UseWebSocketOptions {
  url: string;
  onMessage: (data: any) => void;
  onClose?: () => void;
  enabled?: boolean;
}

export function useWebSocket({ url, onMessage, onClose, enabled = true }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    if (!enabled) return;

    const wsUrl = `ws://${window.location.host}${url}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      retriesRef.current = 0;
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch {
        // Binary data (terminal) — pass raw
        onMessage(event.data);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      onClose?.();
      // Exponential backoff reconnect
      const delay = Math.min(1000 * Math.pow(2, retriesRef.current), 30000);
      retriesRef.current++;
      setTimeout(connect, delay);
    };

    ws.onerror = () => ws.close();
  }, [url, onMessage, onClose, enabled]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((data: string | ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  return { send, connected, ws: wsRef };
}
```

- [ ] **Step 5: Create useAnalysis hook**

Create `web/src/hooks/useAnalysis.ts`:

```typescript
import { useState, useCallback } from 'react';
import { api, type AnalysisSession, type SessionResults } from '../lib/api';
import { useWebSocket } from './useWebSocket';
import { emit } from '../lib/events';

interface ProgressUpdate {
  type: string;
  progress?: number;
  current_path?: string;
  message?: string;
  files_scanned?: number;
}

export function useAnalysis() {
  const [session, setSession] = useState<AnalysisSession | null>(null);
  const [results, setResults] = useState<SessionResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleMessage = useCallback((data: ProgressUpdate) => {
    if (data.type === 'progress' || data.type === 'file_progress') {
      setSession(prev => prev ? {
        ...prev,
        progress: data.progress ?? prev.progress,
        current_path: data.current_path ?? prev.current_path,
      } : prev);
      emit('analysis:progress', data);
    }
    if (data.type === 'completed') {
      setSession(prev => prev ? { ...prev, status: 'completed', progress: 100 } : prev);
      // Fetch full results
      if (session?.id) {
        api.getResults(session.id).then(r => {
          setResults(r);
          emit('analysis:completed', r);
        });
      }
    }
    if (data.type === 'error') {
      setSession(prev => prev ? { ...prev, status: 'error' } : prev);
      setError(data.message ?? 'Analysis failed');
      emit('analysis:error', data);
    }
  }, [session?.id]);

  const { connected } = useWebSocket({
    url: `/ws/${session?.id}`,
    onMessage: handleMessage,
    enabled: !!session?.id && session.status === 'running',
  });

  const startAnalysis = useCallback(async (paths: string[], minSizeMb = 10) => {
    setError(null);
    setResults(null);
    const { session_id } = await api.startAnalysis({ paths, min_size_mb: minSizeMb });
    const newSession: AnalysisSession = {
      id: session_id,
      status: 'running',
      progress: 0,
      current_path: '',
      paths,
      started_at: new Date().toISOString(),
    };
    setSession(newSession);
    emit('analysis:started', newSession);
    return session_id;
  }, []);

  return { session, results, error, connected, startAnalysis };
}
```

- [ ] **Step 6: Build to verify types compile**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/ web/src/hooks/
git commit -m "feat: API client, event bus, WebSocket hook, and analysis hook"
```

---

## Task 5: PTY Manager Backend Module

**Files:**
- Create: `pty_manager.py`
- Create: `tests/test_pty_manager.py`

- [ ] **Step 1: Write failing tests for PTY Manager**

Create `tests/__init__.py` (empty file) and `tests/test_pty_manager.py`:

```python
import pytest
import time
import os
from pathlib import Path

# Ensure project root is importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from pty_manager import PTYManager, PTYSession


class TestPTYManager:
    def setup_method(self):
        self.manager = PTYManager(max_sessions=2, idle_timeout=5)

    def teardown_method(self):
        self.manager.cleanup_all()

    def test_create_session_returns_pty_id(self):
        pty_id = self.manager.create_session()
        assert pty_id is not None
        assert isinstance(pty_id, str)
        assert len(pty_id) > 0

    def test_create_session_with_command(self):
        pty_id = self.manager.create_session(command="echo hello")
        assert pty_id in self.manager.sessions

    def test_max_sessions_enforced(self):
        self.manager.create_session()
        self.manager.create_session()
        with pytest.raises(RuntimeError, match="Maximum.*sessions"):
            self.manager.create_session()

    def test_read_output(self):
        pty_id = self.manager.create_session(command="echo test_output_marker")
        time.sleep(0.5)
        output = self.manager.read_output(pty_id)
        assert "test_output_marker" in output

    def test_write_input(self):
        pty_id = self.manager.create_session()
        # Write a command and read the echo
        self.manager.write_input(pty_id, "echo pty_write_test\n")
        time.sleep(0.5)
        output = self.manager.read_output(pty_id)
        assert "pty_write_test" in output

    def test_resize(self):
        pty_id = self.manager.create_session()
        # Should not raise
        self.manager.resize(pty_id, cols=120, rows=40)

    def test_kill_session(self):
        pty_id = self.manager.create_session()
        self.manager.kill_session(pty_id)
        assert pty_id not in self.manager.sessions

    def test_kill_nonexistent_raises(self):
        with pytest.raises(KeyError):
            self.manager.kill_session("nonexistent")

    def test_list_sessions(self):
        id1 = self.manager.create_session()
        id2 = self.manager.create_session(command="echo hi")
        sessions = self.manager.list_sessions()
        assert len(sessions) == 2
        ids = [s['pty_id'] for s in sessions]
        assert id1 in ids
        assert id2 in ids

    def test_blocked_command_rejected(self):
        with pytest.raises(ValueError, match="[Bb]locked"):
            self.manager.create_session(command="rm -rf /")

    def test_command_logging(self, tmp_path):
        log_file = tmp_path / "terminal.log"
        manager = PTYManager(max_sessions=2, log_file=str(log_file))
        manager.create_session(command="echo logged_cmd")
        time.sleep(0.2)
        manager.cleanup_all()
        log_content = log_file.read_text()
        assert "echo logged_cmd" in log_content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer
python -m pytest tests/test_pty_manager.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'pty_manager'`

- [ ] **Step 3: Implement PTY Manager**

Create `pty_manager.py`:

```python
"""PTY Manager: Spawns and manages pseudo-terminal sessions for the web UI."""

import os
import pty
import fcntl
import struct
import signal
import select
import subprocess
import termios
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


BLOCKED_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    "> /dev/sda",
]


class PTYSession:
    """A single pseudo-terminal session."""

    def __init__(self, pty_id: str, command: Optional[str] = None):
        self.pty_id = pty_id
        self.command = command
        self.created_at = datetime.now().isoformat()
        self.last_activity = time.time()
        self.master_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self.alive = False
        self._output_buffer = bytearray()
        self._lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None

    def start(self):
        """Spawn the PTY process."""
        master_fd, slave_fd = pty.openpty()
        self.master_fd = master_fd

        # Set non-blocking on master
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        shell = os.environ.get('SHELL', '/bin/zsh')
        if self.command:
            args = [shell, '-c', self.command]
        else:
            args = [shell, '-l']

        self.pid = os.fork()
        if self.pid == 0:
            # Child process
            os.close(master_fd)
            os.setsid()

            # Set slave as controlling terminal
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ,
                        struct.pack('HHHH', 24, 80, 0, 0))

            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)

            os.execvp(args[0], args)
        else:
            # Parent process
            os.close(slave_fd)
            self.alive = True
            self._reader_thread = threading.Thread(
                target=self._read_loop, daemon=True
            )
            self._reader_thread.start()

    def _read_loop(self):
        """Continuously read from PTY master fd into buffer."""
        while self.alive and self.master_fd is not None:
            try:
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                if ready:
                    data = os.read(self.master_fd, 4096)
                    if data:
                        with self._lock:
                            self._output_buffer.extend(data)
                        self.last_activity = time.time()
                    else:
                        # EOF
                        self.alive = False
                        break
            except OSError:
                self.alive = False
                break

    def read_output(self) -> str:
        """Read and drain the output buffer."""
        with self._lock:
            data = bytes(self._output_buffer)
            self._output_buffer.clear()
        return data.decode('utf-8', errors='replace')

    def read_output_bytes(self) -> bytes:
        """Read and drain the output buffer as raw bytes."""
        with self._lock:
            data = bytes(self._output_buffer)
            self._output_buffer.clear()
        return data

    def write_input(self, data: str):
        """Write to the PTY stdin."""
        if self.master_fd is not None and self.alive:
            os.write(self.master_fd, data.encode('utf-8'))
            self.last_activity = time.time()

    def write_input_bytes(self, data: bytes):
        """Write raw bytes to PTY stdin."""
        if self.master_fd is not None and self.alive:
            os.write(self.master_fd, data)
            self.last_activity = time.time()

    def resize(self, cols: int, rows: int):
        """Resize the PTY window."""
        if self.master_fd is not None:
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def kill(self):
        """Kill the PTY process and clean up."""
        self.alive = False
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGTERM)
                # Wait briefly, then force kill
                time.sleep(0.1)
                try:
                    os.kill(self.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(self.pid, os.WNOHANG)
                except ChildProcessError:
                    pass
            except ProcessLookupError:
                pass
            self.pid = None
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

    def get_exit_code(self) -> Optional[int]:
        """Check if process has exited and return exit code."""
        if self.pid is None:
            return None
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid != 0:
                self.alive = False
                return os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
        except ChildProcessError:
            self.alive = False
            return -1
        return None


class PTYManager:
    """Manages multiple PTY sessions with safety limits."""

    def __init__(
        self,
        max_sessions: int = 3,
        idle_timeout: int = 600,
        log_file: Optional[str] = None,
    ):
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self.sessions: Dict[str, PTYSession] = {}
        self._lock = threading.Lock()

        if log_file:
            self.log_path = Path(log_file)
        else:
            self.log_path = Path.home() / ".disk-analyzer" / "terminal.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _check_blocked(self, command: str):
        """Reject dangerous commands."""
        normalized = command.strip().lower()
        for pattern in BLOCKED_PATTERNS:
            if pattern.lower() in normalized:
                raise ValueError(f"Blocked command pattern: {pattern}")

    def _log_command(self, pty_id: str, command: Optional[str]):
        """Log command execution."""
        timestamp = datetime.now().isoformat()
        entry = f"[{timestamp}] pty={pty_id} command={command or 'interactive shell'}\n"
        with open(self.log_path, 'a') as f:
            f.write(entry)

    def create_session(self, command: Optional[str] = None) -> str:
        """Create a new PTY session. Returns pty_id."""
        with self._lock:
            # Clean up dead sessions first
            self._reap_dead()

            if len(self.sessions) >= self.max_sessions:
                raise RuntimeError(
                    f"Maximum {self.max_sessions} sessions reached. "
                    "Kill an existing session first."
                )

            if command:
                self._check_blocked(command)

            pty_id = uuid.uuid4().hex[:12]
            session = PTYSession(pty_id, command)
            session.start()
            self.sessions[pty_id] = session
            self._log_command(pty_id, command)
            return pty_id

    def read_output(self, pty_id: str) -> str:
        """Read buffered output from a session."""
        return self._get_session(pty_id).read_output()

    def read_output_bytes(self, pty_id: str) -> bytes:
        """Read buffered output as raw bytes."""
        return self._get_session(pty_id).read_output_bytes()

    def write_input(self, pty_id: str, data: str):
        """Write to a session's stdin."""
        self._get_session(pty_id).write_input(data)

    def write_input_bytes(self, pty_id: str, data: bytes):
        """Write raw bytes to a session's stdin."""
        self._get_session(pty_id).write_input_bytes(data)

    def resize(self, pty_id: str, cols: int, rows: int):
        """Resize a session's terminal."""
        self._get_session(pty_id).resize(cols, rows)

    def kill_session(self, pty_id: str):
        """Kill and remove a session."""
        with self._lock:
            if pty_id not in self.sessions:
                raise KeyError(f"No session: {pty_id}")
            session = self.sessions.pop(pty_id)
        session.kill()

    def list_sessions(self) -> List[Dict]:
        """List all active sessions."""
        with self._lock:
            self._reap_dead()
            return [
                {
                    'pty_id': s.pty_id,
                    'command': s.command,
                    'created_at': s.created_at,
                    'alive': s.alive,
                }
                for s in self.sessions.values()
            ]

    def cleanup_all(self):
        """Kill all sessions."""
        with self._lock:
            for session in list(self.sessions.values()):
                session.kill()
            self.sessions.clear()

    def cleanup_idle(self):
        """Kill sessions that have been idle longer than timeout."""
        now = time.time()
        with self._lock:
            for pty_id, session in list(self.sessions.items()):
                if now - session.last_activity > self.idle_timeout:
                    session.kill()
                    del self.sessions[pty_id]

    def _get_session(self, pty_id: str) -> PTYSession:
        with self._lock:
            if pty_id not in self.sessions:
                raise KeyError(f"No session: {pty_id}")
            return self.sessions[pty_id]

    def _reap_dead(self):
        """Remove sessions whose processes have exited."""
        for pty_id in list(self.sessions.keys()):
            session = self.sessions[pty_id]
            if not session.alive:
                session.kill()
                del self.sessions[pty_id]
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer
python -m pytest tests/test_pty_manager.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add pty_manager.py tests/
git commit -m "feat: PTY manager module with session lifecycle and safety"
```

---

## Task 6: Terminal API Endpoints

**Files:**
- Modify: `disk_analyzer_web.py` (add terminal routes + WebSocket)
- Create: `tests/test_terminal_api.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/test_terminal_api.py`:

```python
import pytest
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from disk_analyzer_web import app


class TestTerminalAPI:
    def setup_method(self):
        self.client = TestClient(app)

    def test_create_terminal_session(self):
        r = self.client.post('/api/terminal/create', json={})
        assert r.status_code == 200
        data = r.json()
        assert 'pty_id' in data
        assert 'created_at' in data
        # Cleanup
        self.client.delete(f'/api/terminal/{data["pty_id"]}')

    def test_create_terminal_with_command(self):
        r = self.client.post('/api/terminal/create', json={'command': 'echo hello'})
        assert r.status_code == 200
        data = r.json()
        assert 'pty_id' in data
        self.client.delete(f'/api/terminal/{data["pty_id"]}')

    def test_create_terminal_blocked_command(self):
        r = self.client.post('/api/terminal/create', json={'command': 'rm -rf /'})
        assert r.status_code == 400
        assert 'locked' in r.json()['detail'].lower() or 'block' in r.json()['detail'].lower()

    def test_list_terminal_sessions(self):
        r1 = self.client.post('/api/terminal/create', json={})
        pty_id = r1.json()['pty_id']

        r2 = self.client.get('/api/terminal/sessions')
        assert r2.status_code == 200
        sessions = r2.json()
        assert any(s['pty_id'] == pty_id for s in sessions)

        self.client.delete(f'/api/terminal/{pty_id}')

    def test_resize_terminal(self):
        r = self.client.post('/api/terminal/create', json={})
        pty_id = r.json()['pty_id']

        r2 = self.client.post(f'/api/terminal/{pty_id}/resize', json={'cols': 120, 'rows': 40})
        assert r2.status_code == 200

        self.client.delete(f'/api/terminal/{pty_id}')

    def test_kill_terminal(self):
        r = self.client.post('/api/terminal/create', json={})
        pty_id = r.json()['pty_id']

        r2 = self.client.delete(f'/api/terminal/{pty_id}')
        assert r2.status_code == 200

        # Should be gone
        r3 = self.client.delete(f'/api/terminal/{pty_id}')
        assert r3.status_code == 404

    def test_kill_nonexistent(self):
        r = self.client.delete('/api/terminal/nonexistent')
        assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_terminal_api.py -v 2>&1 | head -20
```

Expected: 404 or routing errors (endpoints don't exist yet).

- [ ] **Step 3: Add terminal endpoints to disk_analyzer_web.py**

Add these imports near the top of `disk_analyzer_web.py`:

```python
from pty_manager import PTYManager
```

Add this after the existing global variables (after the `executor = ThreadPoolExecutor(...)` line):

```python
# Terminal management
pty_manager = PTYManager(max_sessions=3, idle_timeout=600)
```

Add these Pydantic models alongside the existing models:

```python
class TerminalCreateRequest(BaseModel):
    command: Optional[str] = None

class TerminalResizeRequest(BaseModel):
    cols: int
    rows: int
```

Add these routes (before the catch-all route if it exists, after other API routes):

```python
# ─── Terminal Endpoints ───────────────────────────────────────────────────────

@app.post("/api/terminal/create")
async def create_terminal(request: TerminalCreateRequest):
    """Spawn a new PTY session."""
    try:
        pty_id = pty_manager.create_session(command=request.command)
        session = pty_manager.sessions[pty_id]
        return {"pty_id": pty_id, "created_at": session.created_at}
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/terminal/sessions")
async def list_terminals():
    """List active terminal sessions."""
    return pty_manager.list_sessions()


@app.post("/api/terminal/{pty_id}/resize")
async def resize_terminal(pty_id: str, request: TerminalResizeRequest):
    """Resize a terminal session."""
    try:
        pty_manager.resize(pty_id, request.cols, request.rows)
        return {"status": "ok"}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No session: {pty_id}")


@app.delete("/api/terminal/{pty_id}")
async def kill_terminal(pty_id: str):
    """Kill a terminal session."""
    try:
        pty_manager.kill_session(pty_id)
        return {"status": "killed"}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No session: {pty_id}")


@app.websocket("/ws/terminal/{pty_id}")
async def terminal_websocket(websocket: WebSocket, pty_id: str):
    """Bidirectional WebSocket: stdin from browser → PTY, stdout from PTY → browser."""
    if pty_id not in pty_manager.sessions:
        await websocket.close(code=4004, reason="No such session")
        return

    await websocket.accept()
    session = pty_manager.sessions[pty_id]

    async def send_output():
        """Read PTY output and send to browser."""
        while session.alive:
            data = session.read_output_bytes()
            if data:
                await websocket.send_bytes(data)
            else:
                await asyncio.sleep(0.05)
        # Send exit notification
        exit_code = session.get_exit_code()
        try:
            await websocket.send_json({"type": "exit", "code": exit_code or 0})
        except Exception:
            pass

    output_task = asyncio.create_task(send_output())

    try:
        while True:
            data = await websocket.receive()
            if "text" in data:
                session.write_input(data["text"])
            elif "bytes" in data:
                session.write_input_bytes(data["bytes"])
    except WebSocketDisconnect:
        pass
    finally:
        output_task.cancel()
```

Add cleanup to the existing shutdown event:

```python
# In the existing shutdown handler, add:
pty_manager.cleanup_all()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_terminal_api.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add disk_analyzer_web.py tests/test_terminal_api.py
git commit -m "feat: terminal API endpoints with PTY WebSocket streaming"
```

---

## Task 7: Dashboard Page (Stats + Charts + Task List)

**Files:**
- Create: `web/src/components/StatsCards.tsx`
- Create: `web/src/components/CategoryChart.tsx`
- Create: `web/src/components/DiskDonut.tsx`
- Create: `web/src/components/TaskList.tsx`
- Modify: `web/src/pages/index.astro`

- [ ] **Step 1: Create StatsCards component**

Create `web/src/components/StatsCards.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { api, type SystemInfo, type SessionResults } from '../lib/api';
import { formatBytes } from '../lib/format';
import { on } from '../lib/events';

export default function StatsCards() {
  const [sysInfo, setSysInfo] = useState<SystemInfo | null>(null);
  const [results, setResults] = useState<SessionResults | null>(null);

  useEffect(() => {
    api.getSystemInfo().then(setSysInfo).catch(console.error);
    const off = on('analysis:completed', (data: SessionResults) => setResults(data));
    return off;
  }, []);

  const disk = sysInfo?.disk_usage;
  const summary = results?.results?.[0]?.report?.summary;

  const cards = [
    {
      label: 'Total Disk Used',
      value: disk ? formatBytes(disk.used) : '—',
      sub: disk ? `of ${formatBytes(disk.total)} (${((disk.used / disk.total) * 100).toFixed(0)}%)` : '',
    },
    {
      label: 'Recoverable Space',
      value: summary ? formatBytes(summary.recoverable_space) : '—',
      sub: summary ? `${summary.large_files_count} large files found` : 'Run analysis to see',
      color: 'var(--success)',
    },
    {
      label: 'Files Scanned',
      value: summary ? summary.files_scanned.toLocaleString() : '—',
      sub: summary ? `Cache: ${formatBytes(summary.cache_size)}` : '',
    },
  ];

  return (
    <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
      {cards.map((c, i) => (
        <div key={i} className="card" style={{ flex: 1 }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
            {c.label}
          </div>
          <div style={{ fontWeight: 700, fontSize: '1.5rem', color: c.color }}>
            {c.value}
          </div>
          {c.sub && <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{c.sub}</div>}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create CategoryChart component (Plotly Treemap)**

Create `web/src/components/CategoryChart.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react';
import { on } from '../lib/events';
import { formatBytes } from '../lib/format';
import type { SessionResults } from '../lib/api';

export default function CategoryChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [results, setResults] = useState<SessionResults | null>(null);

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => setResults(data));
    return off;
  }, []);

  useEffect(() => {
    if (!results || !containerRef.current) return;

    const report = results.results[0]?.report;
    if (!report) return;

    const dirs = report.top_directories.slice(0, 15);
    const labels = dirs.map(([path]) => {
      const parts = path.split('/');
      return parts[parts.length - 1] || path;
    });
    const parents = dirs.map(() => '');
    const values = dirs.map(([, size]) => size);
    const text = dirs.map(([path, size]) => `${path}<br>${formatBytes(size)}`);

    import('plotly.js-dist-min').then((Plotly) => {
      Plotly.newPlot(containerRef.current!, [{
        type: 'treemap',
        labels,
        parents,
        values,
        text,
        hoverinfo: 'text',
        textinfo: 'label+percent root',
        marker: {
          colors: values.map((_, i) => {
            const palette = ['#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#10b981', '#34d399', '#6ee7b7', '#f59e0b', '#fbbf24', '#fcd34d', '#ef4444', '#f87171', '#fca5a5', '#3b82f6', '#60a5fa'];
            return palette[i % palette.length];
          }),
        },
      }], {
        margin: { t: 10, b: 10, l: 10, r: 10 },
        height: 300,
        paper_bgcolor: 'transparent',
      }, { responsive: true, displayModeBar: false });
    });
  }, [results]);

  return (
    <div className="card" style={{ flex: 2 }}>
      <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Category Breakdown</div>
      {!results ? (
        <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
          Run an analysis to see results
        </div>
      ) : (
        <div ref={containerRef} />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create DiskDonut component**

Create `web/src/components/DiskDonut.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react';
import { api, type SystemInfo } from '../lib/api';
import { formatBytes } from '../lib/format';

export default function DiskDonut() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sysInfo, setSysInfo] = useState<SystemInfo | null>(null);

  useEffect(() => {
    api.getSystemInfo().then(setSysInfo).catch(console.error);
  }, []);

  useEffect(() => {
    if (!sysInfo || !containerRef.current) return;
    const { used, free } = sysInfo.disk_usage;

    import('plotly.js-dist-min').then((Plotly) => {
      Plotly.newPlot(containerRef.current!, [{
        type: 'pie',
        hole: 0.6,
        values: [used, free],
        labels: ['Used', 'Free'],
        marker: { colors: ['#6366f1', '#e5e7eb'] },
        textinfo: 'label+percent',
        hovertemplate: '%{label}: %{value}<extra></extra>',
      }], {
        margin: { t: 10, b: 10, l: 10, r: 10 },
        height: 300,
        showlegend: false,
        paper_bgcolor: 'transparent',
        annotations: [{
          text: formatBytes(used),
          showarrow: false,
          font: { size: 18, color: '#6366f1' },
        }],
      }, { responsive: true, displayModeBar: false });
    });
  }, [sysInfo]);

  return (
    <div className="card" style={{ flex: 1 }}>
      <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Disk Usage</div>
      <div ref={containerRef} />
    </div>
  );
}
```

- [ ] **Step 4: Create TaskList component**

Create `web/src/components/TaskList.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { on } from '../lib/events';
import { formatBytes } from '../lib/format';

interface Task {
  id: string;
  label: string;
  status: 'running' | 'completed' | 'error';
  detail?: string;
}

export default function TaskList() {
  const [tasks, setTasks] = useState<Task[]>([]);

  useEffect(() => {
    const offs = [
      on('analysis:started', (session: any) => {
        setTasks(prev => [...prev, {
          id: session.id,
          label: `Analysis of ${session.paths.join(', ')}`,
          status: 'running',
        }]);
      }),
      on('analysis:progress', (data: any) => {
        setTasks(prev => prev.map(t =>
          t.status === 'running' && data.current_path
            ? { ...t, detail: `${data.progress ?? 0}% — ${data.current_path}` }
            : t
        ));
      }),
      on('analysis:completed', (data: any) => {
        setTasks(prev => prev.map(t =>
          t.id === data.id ? { ...t, status: 'completed', detail: undefined } : t
        ));
      }),
      on('analysis:error', (data: any) => {
        setTasks(prev => prev.map(t =>
          t.status === 'running' ? { ...t, status: 'error', detail: data.message } : t
        ));
      }),
      on('terminal:started', (data: any) => {
        setTasks(prev => [...prev, {
          id: data.pty_id,
          label: `Running: ${data.command || 'interactive shell'}`,
          status: 'running',
        }]);
      }),
      on('terminal:exited', (data: any) => {
        setTasks(prev => prev.map(t =>
          t.id === data.pty_id ? { ...t, status: data.code === 0 ? 'completed' : 'error' } : t
        ));
      }),
    ];
    return () => offs.forEach(off => off());
  }, []);

  if (tasks.length === 0) {
    return (
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Background Tasks</div>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.875rem', padding: '0.5rem 0' }}>
          No active tasks. Start an analysis or run a command.
        </div>
      </div>
    );
  }

  const statusColors: Record<string, string> = {
    running: '#6366f1',
    completed: '#10b981',
    error: '#ef4444',
  };

  const statusLabels: Record<string, string> = {
    running: 'In Progress',
    completed: 'Completed',
    error: 'Error',
  };

  return (
    <div className="card">
      <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Background Tasks</div>
      {tasks.map(task => (
        <div key={task.id} style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          padding: '0.5rem', borderRadius: '6px', marginBottom: '0.35rem',
          background: task.status === 'running' ? '#eff6ff' : task.status === 'completed' ? '#f0fdf4' : '#fef2f2',
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: statusColors[task.status],
            animation: task.status === 'running' ? 'pulse 1.5s infinite' : 'none',
          }} />
          <span style={{ flex: 1, fontSize: '0.875rem' }}>
            {task.label}
            {task.detail && <span style={{ color: 'var(--text-muted)', marginLeft: '0.5rem', fontSize: '0.75rem' }}>{task.detail}</span>}
          </span>
          <span style={{
            fontSize: '0.7rem', padding: '0.2rem 0.5rem', borderRadius: '4px',
            background: statusColors[task.status] + '20', color: statusColors[task.status],
          }}>
            {statusLabels[task.status]}
          </span>
        </div>
      ))}
      <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }`}</style>
    </div>
  );
}
```

- [ ] **Step 5: Wire up the Dashboard page**

Replace `web/src/pages/index.astro`:

```astro
---
import MainLayout from '../layouts/MainLayout.astro';
import StatsCards from '../components/StatsCards.tsx';
import CategoryChart from '../components/CategoryChart.tsx';
import DiskDonut from '../components/DiskDonut.tsx';
import TaskList from '../components/TaskList.tsx';
---

<MainLayout title="Dashboard" currentPath="/">
  <StatsCards client:load />

  <div style="display: flex; gap: 0.75rem; margin-bottom: 1rem;">
    <CategoryChart client:idle />
    <DiskDonut client:idle />
  </div>

  <TaskList client:load />
</MainLayout>
```

- [ ] **Step 6: Build and verify**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm run build
```

Expected: Build succeeds.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/StatsCards.tsx web/src/components/CategoryChart.tsx web/src/components/DiskDonut.tsx web/src/components/TaskList.tsx web/src/pages/index.astro
git commit -m "feat: dashboard page with stats, charts, and task list"
```

---

## Task 8: File Browser Page

**Files:**
- Create: `web/src/components/FileTable.tsx`
- Modify: `web/src/pages/files.astro`

- [ ] **Step 1: Create FileTable component with virtual scroll**

Create `web/src/components/FileTable.tsx`:

```tsx
import { useState, useEffect, useRef, useMemo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { on, emit } from '../lib/events';
import { api, type LargeFile, type SessionResults } from '../lib/api';
import { formatBytes, formatAge } from '../lib/format';

type SortKey = 'size' | 'age_days' | 'path';
type SortDir = 'asc' | 'desc';

export default function FileTable() {
  const [files, setFiles] = useState<LargeFile[]>([]);
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('size');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const parentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      const allFiles = data.results.flatMap(r => r.report.large_files);
      setFiles(allFiles);
    });
    return off;
  }, []);

  const filtered = useMemo(() => {
    let result = files;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(f => f.path.toLowerCase().includes(q) || f.extension.toLowerCase().includes(q));
    }
    result.sort((a, b) => {
      const mul = sortDir === 'asc' ? 1 : -1;
      if (sortKey === 'path') return mul * a.path.localeCompare(b.path);
      return mul * ((a[sortKey] as number) - (b[sortKey] as number));
    });
    return result;
  }, [files, search, sortKey, sortDir]);

  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 44,
    overscan: 20,
  });

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const toggleSelect = (path: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(path) ? next.delete(path) : next.add(path);
      return next;
    });
  };

  const deleteSelected = async () => {
    if (selected.size === 0) return;
    const confirmed = window.confirm(
      `Delete ${selected.size} file(s)? They will be moved to Trash.`
    );
    if (!confirmed) return;
    for (const path of selected) {
      try {
        await api.deleteFile(path);
        setFiles(prev => prev.filter(f => f.path !== path));
      } catch (e) {
        console.error(`Failed to delete ${path}:`, e);
      }
    }
    setSelected(new Set());
  };

  const sortIndicator = (key: SortKey) => {
    if (sortKey !== key) return '';
    return sortDir === 'asc' ? ' ↑' : ' ↓';
  };

  if (files.length === 0) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        No files to display. Run an analysis from the Dashboard first.
      </div>
    );
  }

  return (
    <div>
      {/* Toolbar */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', alignItems: 'center' }}>
        <input
          type="text"
          placeholder="Search files..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            flex: 1, padding: '0.5rem 0.75rem', border: '1px solid var(--border)',
            borderRadius: '8px', background: 'var(--card-bg)', color: 'var(--text)',
            fontSize: '0.875rem',
          }}
        />
        {selected.size > 0 && (
          <button className="btn btn-primary" onClick={deleteSelected} style={{ background: 'var(--danger)' }}>
            Delete {selected.size} file(s)
          </button>
        )}
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          {filtered.length.toLocaleString()} files
        </span>
      </div>

      {/* Header */}
      <div style={{
        display: 'grid', gridTemplateColumns: '32px 1fr 100px 70px 70px',
        gap: '0.5rem', padding: '0.5rem 0.75rem', fontWeight: 600, fontSize: '0.8rem',
        borderBottom: '2px solid var(--border)', color: 'var(--text-muted)',
      }}>
        <div></div>
        <div onClick={() => toggleSort('path')} style={{ cursor: 'pointer' }}>Path{sortIndicator('path')}</div>
        <div onClick={() => toggleSort('size')} style={{ cursor: 'pointer', textAlign: 'right' }}>Size{sortIndicator('size')}</div>
        <div onClick={() => toggleSort('age_days')} style={{ cursor: 'pointer', textAlign: 'right' }}>Age{sortIndicator('age_days')}</div>
        <div style={{ textAlign: 'center' }}>Status</div>
      </div>

      {/* Virtual list */}
      <div ref={parentRef} style={{ height: 'calc(100vh - 280px)', overflow: 'auto' }}>
        <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
          {virtualizer.getVirtualItems().map(row => {
            const file = filtered[row.index];
            return (
              <div
                key={file.path}
                style={{
                  position: 'absolute', top: 0, left: 0, width: '100%',
                  transform: `translateY(${row.start}px)`,
                  height: row.size,
                  display: 'grid', gridTemplateColumns: '32px 1fr 100px 70px 70px',
                  gap: '0.5rem', padding: '0.5rem 0.75rem', alignItems: 'center',
                  fontSize: '0.8rem', borderBottom: '1px solid var(--border)',
                  background: selected.has(file.path) ? 'var(--primary)10' : 'transparent',
                }}
              >
                <input
                  type="checkbox"
                  checked={selected.has(file.path)}
                  disabled={file.is_protected}
                  onChange={() => toggleSelect(file.path)}
                />
                <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={file.path}>
                  {file.path}
                </div>
                <div style={{ textAlign: 'right', fontWeight: 500 }}>{formatBytes(file.size)}</div>
                <div style={{ textAlign: 'right', color: 'var(--text-muted)' }}>{formatAge(file.age_days)}</div>
                <div style={{ textAlign: 'center' }}>
                  {file.is_protected ? '🔒' : file.is_cache ? '🗑️' : '📄'}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire up the files page**

Replace `web/src/pages/files.astro`:

```astro
---
import MainLayout from '../layouts/MainLayout.astro';
import FileTable from '../components/FileTable.tsx';
---

<MainLayout title="File Browser" currentPath="/files">
  <FileTable client:load />
</MainLayout>
```

- [ ] **Step 3: Build and verify**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm run build
```

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/FileTable.tsx web/src/pages/files.astro
git commit -m "feat: file browser page with virtual scroll and bulk delete"
```

---

## Task 9: Cleanup Page

**Files:**
- Create: `web/src/components/CleanupWizard.tsx`
- Modify: `web/src/pages/cleanup.astro`

- [ ] **Step 1: Create CleanupWizard component**

Create `web/src/components/CleanupWizard.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { on, emit } from '../lib/events';
import { api, type Recommendation, type SessionResults } from '../lib/api';
import { formatBytes } from '../lib/format';

const TIER_META: Record<number, { label: string; color: string; icon: string }> = {
  1: { label: 'Safe', color: '#10b981', icon: '✅' },
  2: { label: 'Moderate', color: '#f59e0b', icon: '⚠️' },
  3: { label: 'Aggressive', color: '#ef4444', icon: '🔴' },
  4: { label: 'Deep Clean', color: '#7c3aed', icon: '💀' },
};

export default function CleanupWizard() {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set([1]));
  const [running, setRunning] = useState<Set<string>>(new Set());

  useEffect(() => {
    const off = on('analysis:completed', (data: SessionResults) => {
      const allRecs = data.results.flatMap(r => r.report.recommendations);
      setRecs(allRecs);
    });
    return off;
  }, []);

  const toggleTier = (tier: number) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(tier) ? next.delete(tier) : next.add(tier);
      return next;
    });
  };

  const runCommand = async (rec: Recommendation) => {
    const key = rec.command;
    if (running.has(key)) return;

    // Shell commands → open in terminal
    if (rec.command && !rec.command.startsWith('#')) {
      try {
        const { pty_id } = await api.createTerminal(rec.command);
        emit('terminal:open', { pty_id, command: rec.command });
        emit('terminal:started', { pty_id, command: rec.command });
        setRunning(prev => new Set(prev).add(key));
      } catch (e) {
        console.error('Failed to run command:', e);
      }
    }
  };

  const previewCleanup = async () => {
    try {
      const result = await api.previewCleanup([]);
      console.log('Preview result:', result);
    } catch (e) {
      console.error('Preview failed:', e);
    }
  };

  const grouped = recs.reduce((acc, rec) => {
    const tier = rec.tier || 1;
    if (!acc[tier]) acc[tier] = [];
    acc[tier].push(rec);
    return acc;
  }, {} as Record<number, Recommendation[]>);

  if (recs.length === 0) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        No cleanup recommendations yet. Run an analysis from the Dashboard first.
      </div>
    );
  }

  return (
    <div>
      {Object.entries(grouped)
        .sort(([a], [b]) => Number(a) - Number(b))
        .map(([tierStr, tierRecs]) => {
          const tier = Number(tierStr);
          const meta = TIER_META[tier] || TIER_META[1];
          const totalSpace = tierRecs.reduce((s, r) => s + (r.space || 0), 0);
          const isOpen = expanded.has(tier);

          return (
            <div key={tier} className="card" style={{ marginBottom: '0.75rem' }}>
              <div
                onClick={() => toggleTier(tier)}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  cursor: 'pointer', padding: '0.25rem 0',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span>{meta.icon}</span>
                  <span style={{ fontWeight: 600 }}>Tier {tier}: {meta.label}</span>
                  <span style={{
                    fontSize: '0.75rem', padding: '0.15rem 0.5rem', borderRadius: '4px',
                    background: meta.color + '20', color: meta.color,
                  }}>
                    {tierRecs.length} items · {formatBytes(totalSpace)}
                  </span>
                </div>
                <span>{isOpen ? '▾' : '▸'}</span>
              </div>

              {isOpen && (
                <div style={{ marginTop: '0.75rem' }}>
                  {tierRecs.map((rec, i) => (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'center', gap: '0.75rem',
                      padding: '0.6rem 0', borderTop: i > 0 ? '1px solid var(--border)' : 'none',
                    }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: '0.875rem', fontWeight: 500 }}>{rec.description}</div>
                        {rec.command && !rec.command.startsWith('#') && (
                          <code style={{
                            display: 'block', marginTop: '0.25rem', fontSize: '0.75rem',
                            color: 'var(--text-muted)', background: 'var(--page-bg)',
                            padding: '0.25rem 0.5rem', borderRadius: '4px',
                          }}>
                            {rec.command}
                          </code>
                        )}
                      </div>
                      {rec.space > 0 && (
                        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: meta.color, whiteSpace: 'nowrap' }}>
                          {formatBytes(rec.space)}
                        </span>
                      )}
                      {rec.command && !rec.command.startsWith('#') && (
                        <button
                          className="btn btn-primary"
                          onClick={() => runCommand(rec)}
                          disabled={running.has(rec.command)}
                          style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem', whiteSpace: 'nowrap' }}
                        >
                          {running.has(rec.command) ? 'Running...' : '▶ Run'}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
    </div>
  );
}
```

- [ ] **Step 2: Wire up the cleanup page**

Replace `web/src/pages/cleanup.astro`:

```astro
---
import MainLayout from '../layouts/MainLayout.astro';
import CleanupWizard from '../components/CleanupWizard.tsx';
---

<MainLayout title="Cleanup" currentPath="/cleanup">
  <CleanupWizard client:load />
</MainLayout>
```

- [ ] **Step 3: Build and verify**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm run build
```

- [ ] **Step 4: Commit**

```bash
git add web/src/components/CleanupWizard.tsx web/src/pages/cleanup.astro
git commit -m "feat: cleanup page with tiered recommendations and run-in-terminal"
```

---

## Task 10: Floating Terminal (xterm.js)

**Files:**
- Create: `web/src/components/FloatingTerminal.tsx`
- Create: `web/src/hooks/useTerminal.ts`
- Modify: `web/src/layouts/MainLayout.astro`

- [ ] **Step 1: Create useTerminal hook**

Create `web/src/hooks/useTerminal.ts`:

```typescript
import { useState, useCallback, useRef, useEffect } from 'react';
import { api } from '../lib/api';
import { emit } from '../lib/events';

export function useTerminal() {
  const [ptyId, setPtyId] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const onDataRef = useRef<((data: string | ArrayBuffer) => void) | null>(null);

  const connect = useCallback((id: string) => {
    const wsUrl = `ws://${window.location.host}/ws/terminal/${id}`;
    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'exit') {
            emit('terminal:exited', { pty_id: id, code: msg.code });
            setConnected(false);
            return;
          }
        } catch {}
        onDataRef.current?.(event.data);
      } else {
        onDataRef.current?.(event.data);
      }
    };

    ws.onclose = () => setConnected(false);
    ws.onerror = () => ws.close();
  }, []);

  const spawn = useCallback(async (command?: string) => {
    const { pty_id } = await api.createTerminal(command);
    setPtyId(pty_id);
    connect(pty_id);
    emit('terminal:started', { pty_id, command });
    return pty_id;
  }, [connect]);

  const send = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  const resize = useCallback((cols: number, rows: number) => {
    if (ptyId) {
      api.resizeTerminal(ptyId, cols, rows).catch(console.error);
    }
  }, [ptyId]);

  const kill = useCallback(async () => {
    if (ptyId) {
      await api.killTerminal(ptyId).catch(console.error);
      wsRef.current?.close();
      setPtyId(null);
      setConnected(false);
    }
  }, [ptyId]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  return { ptyId, connected, spawn, send, resize, kill, onDataRef };
}
```

- [ ] **Step 2: Create FloatingTerminal component**

Create `web/src/components/FloatingTerminal.tsx`:

```tsx
import { useState, useEffect, useRef, useCallback } from 'react';
import { on, emit } from '../lib/events';
import { useTerminal } from '../hooks/useTerminal';

export default function FloatingTerminal() {
  const [visible, setVisible] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [position, setPosition] = useState({ x: -1, y: -1 });
  const termRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<any>(null);
  const fitAddonRef = useRef<any>(null);
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const { ptyId, connected, spawn, send, resize, kill, onDataRef } = useTerminal();

  // Initialize position on first show
  useEffect(() => {
    if (visible && position.x === -1) {
      setPosition({
        x: window.innerWidth - 620,
        y: window.innerHeight - 340,
      });
    }
  }, [visible]);

  // Initialize xterm.js
  useEffect(() => {
    if (!visible || minimized || !termRef.current || xtermRef.current) return;

    let cancelled = false;

    Promise.all([
      import('@xterm/xterm'),
      import('@xterm/addon-fit'),
    ]).then(([xtermModule, fitModule]) => {
      if (cancelled || !termRef.current) return;

      // Import CSS
      import('@xterm/xterm/css/xterm.css');

      const term = new xtermModule.Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: 'Menlo, Monaco, monospace',
        theme: {
          background: '#1f2937',
          foreground: '#d1d5db',
          cursor: '#10b981',
          selectionBackground: '#6366f140',
        },
        cols: 80,
        rows: 20,
      });

      const fitAddon = new fitModule.FitAddon();
      term.loadAddon(fitAddon);
      term.open(termRef.current);
      fitAddon.fit();

      xtermRef.current = term;
      fitAddonRef.current = fitAddon;

      // User types → send to PTY
      term.onData((data: string) => send(data));

      // PTY output → write to terminal
      onDataRef.current = (data: string | ArrayBuffer) => {
        if (data instanceof ArrayBuffer) {
          term.write(new Uint8Array(data));
        } else {
          term.write(data);
        }
      };

      // Report size to backend
      resize(term.cols, term.rows);
      term.onResize(({ cols, rows }: { cols: number; rows: number }) => resize(cols, rows));
    });

    return () => { cancelled = true; };
  }, [visible, minimized, send, resize]);

  // Cleanup xterm on hide
  useEffect(() => {
    if (!visible && xtermRef.current) {
      xtermRef.current.dispose();
      xtermRef.current = null;
      fitAddonRef.current = null;
      onDataRef.current = null;
    }
  }, [visible]);

  // Resize observer
  useEffect(() => {
    if (!fitAddonRef.current) return;
    const observer = new ResizeObserver(() => fitAddonRef.current?.fit());
    if (termRef.current) observer.observe(termRef.current);
    return () => observer.disconnect();
  }, [visible, minimized]);

  // Event listeners
  useEffect(() => {
    const offs = [
      on('terminal:toggle', () => {
        setVisible(v => !v);
        setMinimized(false);
      }),
      on('terminal:open', async (data: { pty_id?: string; command?: string }) => {
        setVisible(true);
        setMinimized(false);
        if (!ptyId) {
          // Spawn new session if none active
          await spawn(data.command);
        }
      }),
    ];
    return () => offs.forEach(off => off());
  }, [ptyId, spawn]);

  // Auto-spawn on first open if no session
  useEffect(() => {
    if (visible && !minimized && !ptyId) {
      spawn();
    }
  }, [visible, minimized, ptyId, spawn]);

  // Drag handlers
  const onDragStart = (e: React.MouseEvent) => {
    dragRef.current = { startX: e.clientX, startY: e.clientY, origX: position.x, origY: position.y };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      setPosition({
        x: dragRef.current.origX + (ev.clientX - dragRef.current.startX),
        y: dragRef.current.origY + (ev.clientY - dragRef.current.startY),
      });
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  if (!visible) return null;

  return (
    <div style={{
      position: 'fixed',
      left: position.x,
      top: position.y,
      width: minimized ? 280 : 600,
      zIndex: 9999,
      background: '#1f2937',
      borderRadius: '10px',
      boxShadow: '0 8px 30px rgba(0,0,0,0.35)',
      overflow: 'hidden',
      resize: minimized ? 'none' : 'both',
      minWidth: 300,
      minHeight: minimized ? 36 : 200,
    }}>
      {/* Title bar */}
      <div
        onMouseDown={onDragStart}
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '0.4rem 0.75rem', background: '#111827', cursor: 'move',
          userSelect: 'none',
        }}
      >
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', fontSize: '0.75rem', color: '#9ca3af' }}>
          <span style={{ color: '#10b981', fontWeight: 600 }}>⚡ Terminal</span>
          {connected && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981', display: 'inline-block' }} />}
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.8rem', color: '#9ca3af' }}>
          <span onClick={() => setMinimized(m => !m)} style={{ cursor: 'pointer' }} title="Minimize">─</span>
          <span onClick={async () => { await kill(); setVisible(false); }} style={{ cursor: 'pointer' }} title="Close">✕</span>
        </div>
      </div>

      {/* Terminal body */}
      {!minimized && (
        <div ref={termRef} style={{ padding: '4px', height: 'calc(100% - 36px)' }} />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Mount FloatingTerminal in MainLayout**

Modify `web/src/layouts/MainLayout.astro` — add the FloatingTerminal import and mount it in the `#terminal-root` div:

Add at the top of the frontmatter:

```astro
---
import Sidebar from '../components/Sidebar.astro';
import TopBar from '../components/TopBar.astro';
import FloatingTerminal from '../components/FloatingTerminal.tsx';
import '../layouts/global.css';

const { title, currentPath } = Astro.props;
---
```

Replace `<div id="terminal-root"></div>` with:

```astro
<FloatingTerminal client:idle />
```

- [ ] **Step 4: Build and verify**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm run build
```

Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/FloatingTerminal.tsx web/src/hooks/useTerminal.ts web/src/layouts/MainLayout.astro
git commit -m "feat: floating terminal with xterm.js and PTY WebSocket"
```

---

## Task 11: Export Page + HTML Export Endpoint

**Files:**
- Create: `web/src/components/ExportPanel.tsx`
- Modify: `web/src/pages/export.astro`
- Modify: `disk_analyzer_web.py` (add HTML export endpoint)

- [ ] **Step 1: Add HTML export endpoint to backend**

In `disk_analyzer_web.py`, add this route near the existing export routes:

```python
@app.get("/api/export/{session_id}/html")
async def export_html(session_id: str):
    """Generate and return a standalone HTML report."""
    if session_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = analysis_sessions[session_id]
    if session["status"] != "completed" or not session.get("results"):
        raise HTTPException(status_code=400, detail="Analysis not completed")

    # Use the main DiskAnalyzer's report generator
    try:
        from disk_analyzer import DiskAnalyzer
        analyzer = DiskAnalyzer(str(Path.home()))

        # Merge all path results into a single report
        merged_report = session["results"][0]["report"] if session["results"] else {}

        html_content = analyzer.generate_html_report(merged_report)
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": f'attachment; filename="disk_report_{session_id}.html"'
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")
```

Add `Response` to the imports if not present:

```python
from fastapi.responses import FileResponse, Response
```

- [ ] **Step 2: Create ExportPanel component**

Create `web/src/components/ExportPanel.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { api, type SessionResults } from '../lib/api';
import { on } from '../lib/events';
import { formatBytes } from '../lib/format';

export default function ExportPanel() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<any[]>([]);

  useEffect(() => {
    api.getSessions().then(setSessions).catch(console.error);
    const off = on('analysis:completed', (data: SessionResults) => {
      setSessionId(data.id);
      api.getSessions().then(setSessions).catch(console.error);
    });
    return off;
  }, []);

  const download = (format: 'html' | 'json' | 'csv') => {
    const id = sessionId;
    if (!id) return;
    const url = api.getExportUrl(id, format);
    window.open(url, '_blank');
  };

  const formats = [
    {
      id: 'html' as const,
      icon: '🌐',
      title: 'Standalone HTML Report',
      desc: 'Self-contained interactive report with charts. Opens offline in any browser.',
    },
    {
      id: 'json' as const,
      icon: '📋',
      title: 'JSON Data',
      desc: 'Raw analysis data for scripting or further processing.',
    },
    {
      id: 'csv' as const,
      icon: '📊',
      title: 'CSV Spreadsheet',
      desc: 'Top files exported for use in Excel or Google Sheets.',
    },
  ];

  return (
    <div>
      {/* Session selector */}
      <div className="card" style={{ marginBottom: '1rem' }}>
        <label style={{ fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>Select Session</label>
        <select
          value={sessionId || ''}
          onChange={e => setSessionId(e.target.value || null)}
          style={{
            width: '100%', padding: '0.5rem', borderRadius: '8px',
            border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text)',
          }}
        >
          <option value="">— Select an analysis session —</option>
          {sessions
            .filter(s => s.status === 'completed')
            .map(s => (
              <option key={s.id} value={s.id}>
                {s.paths?.join(', ') || s.id} — {new Date(s.started_at).toLocaleString()}
              </option>
            ))}
        </select>
      </div>

      {/* Export format cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.75rem' }}>
        {formats.map(f => (
          <div key={f.id} className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>{f.icon}</div>
            <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{f.title}</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', flex: 1, marginBottom: '0.75rem' }}>{f.desc}</div>
            <button
              className="btn btn-primary"
              onClick={() => download(f.id)}
              disabled={!sessionId}
              style={{ alignSelf: 'flex-start' }}
            >
              Download {f.id.toUpperCase()}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire up the export page**

Replace `web/src/pages/export.astro`:

```astro
---
import MainLayout from '../layouts/MainLayout.astro';
import ExportPanel from '../components/ExportPanel.tsx';
---

<MainLayout title="Export" currentPath="/export">
  <ExportPanel client:load />
</MainLayout>
```

- [ ] **Step 4: Build and verify**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm run build
```

- [ ] **Step 5: Commit**

```bash
git add disk_analyzer_web.py web/src/components/ExportPanel.tsx web/src/pages/export.astro
git commit -m "feat: export page with HTML/JSON/CSV download and HTML export endpoint"
```

---

## Task 12: History Page

**Files:**
- Create: `web/src/components/SessionList.tsx`
- Modify: `web/src/pages/history.astro`

- [ ] **Step 1: Create SessionList component**

Create `web/src/components/SessionList.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import { formatBytes } from '../lib/format';

interface SessionMeta {
  id: string;
  status: string;
  paths: string[];
  started_at: string;
  completed_at?: string;
}

export default function SessionList() {
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getSessions()
      .then(data => {
        setSessions(data.sort((a: any, b: any) =>
          new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
        ));
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const loadSession = async (id: string) => {
    try {
      const results = await api.getResults(id);
      // Navigate to dashboard with results loaded
      window.dispatchEvent(new CustomEvent('analysis:completed', { detail: results }));
      window.location.href = '/';
    } catch (e) {
      alert('Could not load session results. They may no longer be in memory.');
    }
  };

  const statusBadge = (status: string) => {
    const colors: Record<string, string> = {
      completed: '#10b981',
      running: '#6366f1',
      error: '#ef4444',
    };
    return (
      <span style={{
        fontSize: '0.7rem', padding: '0.15rem 0.5rem', borderRadius: '4px',
        background: (colors[status] || '#6b7280') + '20',
        color: colors[status] || '#6b7280',
      }}>
        {status}
      </span>
    );
  };

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>Loading sessions...</div>;
  }

  if (sessions.length === 0) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        No analysis history yet. Start your first analysis from the Dashboard.
      </div>
    );
  }

  return (
    <div>
      {sessions.map(session => (
        <div key={session.id} className="card" style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.25rem' }}>
              {session.paths?.join(', ') || session.id}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {new Date(session.started_at).toLocaleString()}
              {session.completed_at && ` · Completed ${new Date(session.completed_at).toLocaleString()}`}
            </div>
          </div>
          {statusBadge(session.status)}
          {session.status === 'completed' && (
            <button
              className="btn btn-ghost"
              onClick={() => loadSession(session.id)}
              style={{ fontSize: '0.8rem' }}
            >
              Load Results
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Wire up the history page**

Replace `web/src/pages/history.astro`:

```astro
---
import MainLayout from '../layouts/MainLayout.astro';
import SessionList from '../components/SessionList.tsx';
---

<MainLayout title="History" currentPath="/history">
  <SessionList client:load />
</MainLayout>
```

- [ ] **Step 3: Build and verify**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm run build
```

- [ ] **Step 4: Commit**

```bash
git add web/src/components/SessionList.tsx web/src/pages/history.astro
git commit -m "feat: history page with session list and result reloading"
```

---

## Task 13: New Analysis Flow (Dashboard Integration)

**Files:**
- Create: `web/src/components/NewAnalysisModal.tsx`
- Modify: `web/src/components/StatsCards.tsx`
- Modify: `web/src/components/TopBar.astro`

- [ ] **Step 1: Create NewAnalysisModal component**

Create `web/src/components/NewAnalysisModal.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { api, type DriveInfo } from '../lib/api';
import { on, emit } from '../lib/events';
import { useAnalysis } from '../hooks/useAnalysis';

export default function NewAnalysisModal() {
  const [open, setOpen] = useState(false);
  const [drives, setDrives] = useState<DriveInfo[]>([]);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [customPath, setCustomPath] = useState('');
  const [minSize, setMinSize] = useState(10);
  const { startAnalysis, session } = useAnalysis();

  useEffect(() => {
    const off = on('analysis:new', () => {
      setOpen(true);
      api.getDrives().then(setDrives).catch(console.error);
    });
    return off;
  }, []);

  const togglePath = (path: string) => {
    setSelectedPaths(prev =>
      prev.includes(path) ? prev.filter(p => p !== path) : [...prev, path]
    );
  };

  const addCustomPath = () => {
    if (customPath && !selectedPaths.includes(customPath)) {
      setSelectedPaths(prev => [...prev, customPath]);
      setCustomPath('');
    }
  };

  const submit = async () => {
    if (selectedPaths.length === 0) return;
    await startAnalysis(selectedPaths, minSize);
    setOpen(false);
    setSelectedPaths([]);
  };

  if (!open) return null;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 10000,
    }} onClick={() => setOpen(false)}>
      <div className="card" style={{ width: 500, maxHeight: '80vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
        <h2 style={{ marginBottom: '1rem' }}>New Analysis</h2>

        <div style={{ marginBottom: '1rem' }}>
          <label style={{ fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>Select paths to analyze</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {drives.map(d => (
              <button
                key={d.path}
                className={`btn ${selectedPaths.includes(d.path) ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => togglePath(d.path)}
                style={{ fontSize: '0.8rem' }}
              >
                {d.label || d.path}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          <input
            type="text"
            placeholder="/custom/path"
            value={customPath}
            onChange={e => setCustomPath(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addCustomPath()}
            style={{
              flex: 1, padding: '0.5rem', borderRadius: '8px',
              border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text)',
            }}
          />
          <button className="btn btn-ghost" onClick={addCustomPath}>Add</button>
        </div>

        {selectedPaths.length > 0 && (
          <div style={{ marginBottom: '1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Selected: {selectedPaths.join(', ')}
          </div>
        )}

        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>
            Minimum file size: {minSize} MB
          </label>
          <input
            type="range"
            min={1}
            max={500}
            value={minSize}
            onChange={e => setMinSize(Number(e.target.value))}
            style={{ width: '100%' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
          <button className="btn btn-primary" onClick={submit} disabled={selectedPaths.length === 0}>
            Start Analysis
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update TopBar to emit event**

In `web/src/components/TopBar.astro`, update the script section to add:

```javascript
document.getElementById('newAnalysisBtn')?.addEventListener('click', (e) => {
  e.preventDefault();
  window.dispatchEvent(new CustomEvent('analysis:new'));
});
```

- [ ] **Step 3: Mount NewAnalysisModal in MainLayout**

In `web/src/layouts/MainLayout.astro`, add the import:

```astro
import NewAnalysisModal from '../components/NewAnalysisModal.tsx';
```

Add before the closing `</div>` of app-shell:

```astro
<NewAnalysisModal client:idle />
```

- [ ] **Step 4: Build and verify**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm run build
```

- [ ] **Step 5: Commit**

```bash
git add web/src/components/NewAnalysisModal.tsx web/src/components/TopBar.astro web/src/layouts/MainLayout.astro
git commit -m "feat: new analysis modal with path selection and size slider"
```

---

## Task 14: End-to-End Integration Test

**Files:**
- No new files, testing existing integration

- [ ] **Step 1: Build the full Astro project**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer/web
npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 2: Verify FastAPI serves all pages**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer
python -c "
from fastapi.testclient import TestClient
from disk_analyzer_web import app

client = TestClient(app)

# All pages should return 200
for path in ['/', '/files', '/cleanup', '/export', '/history']:
    r = client.get(path)
    assert r.status_code == 200, f'{path} returned {r.status_code}'
    assert 'Disk Analyzer' in r.text, f'{path} missing title'
    print(f'{path}: OK')

# API endpoints still work
r = client.get('/api/system/info')
assert r.status_code == 200
print('/api/system/info: OK')

r = client.get('/api/system/drives')
assert r.status_code == 200
print('/api/system/drives: OK')

# Terminal endpoints work
r = client.post('/api/terminal/create', json={})
assert r.status_code == 200
pty_id = r.json()['pty_id']
print(f'Terminal created: {pty_id}')

r = client.get('/api/terminal/sessions')
assert r.status_code == 200
assert len(r.json()) >= 1
print('Terminal sessions: OK')

r = client.delete(f'/api/terminal/{pty_id}')
assert r.status_code == 200
print('Terminal killed: OK')

print('\\nAll integration checks passed!')
"
```

- [ ] **Step 3: Run all backend tests**

```bash
cd /Users/artemiopadilla/Documents/repos/GitHub/personal/Disk-Use-Analyzer
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit final state**

```bash
git add -A
git commit -m "feat: complete hosted web UI with Astro, React islands, and terminal"
```

---

## Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | Scaffold Astro project | `web/package.json`, `web/astro.config.mjs` |
| 2 | FastAPI serves Astro build | `disk_analyzer_web.py` |
| 3 | Layout, Sidebar, TopBar | `MainLayout.astro`, `Sidebar.astro`, `TopBar.astro` |
| 4 | API client, hooks, utilities | `api.ts`, `events.ts`, `useWebSocket.ts`, `useAnalysis.ts` |
| 5 | PTY Manager module | `pty_manager.py`, `tests/test_pty_manager.py` |
| 6 | Terminal API endpoints | `disk_analyzer_web.py`, `tests/test_terminal_api.py` |
| 7 | Dashboard page | `StatsCards.tsx`, `CategoryChart.tsx`, `DiskDonut.tsx`, `TaskList.tsx` |
| 8 | File Browser page | `FileTable.tsx` |
| 9 | Cleanup page | `CleanupWizard.tsx` |
| 10 | Floating Terminal | `FloatingTerminal.tsx`, `useTerminal.ts` |
| 11 | Export page + HTML endpoint | `ExportPanel.tsx`, `disk_analyzer_web.py` |
| 12 | History page | `SessionList.tsx` |
| 13 | New Analysis modal | `NewAnalysisModal.tsx` |
| 14 | End-to-end integration test | All files |
