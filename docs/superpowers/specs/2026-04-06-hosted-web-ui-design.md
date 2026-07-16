# Hosted Web UI Design Spec

**Date:** 2026-04-06
**Status:** Approved
**Scope:** Local network-hosted web UI for Disk Use Analyzer with background command execution

## Overview

Enhance the existing FastAPI + vanilla JS web interface into a modern Astro + React application served by the same FastAPI backend. The key additions are: a floating terminal for executing shell commands in real time, background task management, and an export-as-standalone-HTML feature.

## Architecture

**Approach:** Astro static build served by FastAPI (Approach A from brainstorming).

- **Frontend:** Astro framework with React islands for interactive components
- **Backend:** Existing FastAPI server (`disk_analyzer_web.py`), enhanced with PTY management endpoints
- **Core Engine:** `disk_analyzer_core.py` remains unchanged
- **Deployment:** Single process — `python disk_analyzer_web.py` serves both API and Astro build from `web/dist/`
- **Migration:** The existing `static/` frontend (index.html, app.js, style.css) is replaced by the Astro build. The old files remain for backwards compatibility but are no longer served by default.
- **Network:** Binds to `0.0.0.0:8000`, accessible from any device on the LAN

### Frontend Directory Structure

```
web/                          # New Astro project
├── astro.config.mjs
├── package.json
├── src/
│   ├── layouts/
│   │   └── MainLayout.astro  # Sidebar + TopBar + FloatingTerminal shell
│   ├── pages/
│   │   ├── index.astro       # Dashboard
│   │   ├── files.astro       # File Browser
│   │   ├── cleanup.astro     # Cleanup Recommendations
│   │   ├── export.astro      # Export Options
│   │   └── history.astro     # Past Sessions
│   ├── components/
│   │   ├── Sidebar.astro     # Static navigation (no React needed)
│   │   ├── TopBar.astro      # Terminal toggle, new analysis, theme switch
│   │   ├── StatsCards.tsx     # React island — summary stat cards
│   │   ├── CategoryChart.tsx  # React island — Sankey/Treemap
│   │   ├── DiskDonut.tsx      # React island — donut chart
│   │   ├── TaskList.tsx       # React island — background task tracker
│   │   ├── FileTable.tsx      # React island — virtual-scroll file list
│   │   ├── FileActions.tsx    # React island — select/delete actions
│   │   ├── CleanupWizard.tsx  # React island — tiered cleanup flow
│   │   ├── RecommendationList.tsx  # React island — recommendation cards
│   │   ├── ExportPanel.tsx    # React island — export format picker
│   │   ├── SessionList.tsx    # React island — history list
│   │   └── FloatingTerminal.tsx  # React island — xterm.js terminal
│   ├── hooks/
│   │   ├── useWebSocket.ts    # WebSocket connection + reconnect logic
│   │   ├── useAnalysis.ts     # Analysis session management
│   │   └── useTerminal.ts     # PTY session management
│   └── lib/
│       ├── api.ts             # REST API client
│       └── events.ts          # Vanilla JS event bus for cross-island communication
└── public/
    └── favicon.svg
```

## UI Layout

**Sidebar navigation** (persistent left panel) + **floating terminal** (toggleable overlay, bottom-right).

### Sidebar (210px, dark background)
- Logo + app name
- Nav items: Dashboard, File Browser, Cleanup, Export, History
- Bottom: Settings link, version info, LAN IP display

### Top Bar (per-page header)
- Page title (left)
- Actions (right): "New Analysis" button, "Terminal" toggle, theme switch

### Floating Terminal
- Overlays bottom-right of the content area
- Draggable, resizable
- Minimize/maximize/close controls
- Uses xterm.js connected via WebSocket to server-side PTY
- Accessible from any page via the TopBar toggle
- Shows active command name in the title bar

### Dashboard Page
- Stats cards: Disk Used, Recoverable Space, Files Scanned
- Charts row: Category Breakdown (Sankey/Treemap, 2/3 width) + Disk Usage (Donut, 1/3 width)
- Background Tasks panel: list of running/completed analysis and command jobs

## Pages

### Dashboard (`/`)
Summary view. Stats cards, charts, background task list. Entry point for new analysis.

### File Browser (`/files`)
Sortable, filterable table of large files found during analysis. Virtual scroll for 100k+ rows. Columns: name, path, size, age, category, protected status. Bulk select + delete actions. Search/filter bar.

### Cleanup (`/cleanup`)
Tiered recommendation list (4 tiers: Safe, Moderate, Aggressive, Deep Clean). Each recommendation shows: command, space recoverable, risk level. "Preview" button runs dry-run. "Execute" button runs the command (opens in floating terminal for shell commands, or calls cleanup API for file deletions).

### Export (`/export`)
Export current analysis results as:
- Standalone HTML report (reuses `generate_html_report` logic from `disk_analyzer.py`)
- JSON file
- CSV file

### History (`/history`)
List of past analysis sessions with metadata (date, paths, duration, space found). Click to reload results. Compare two sessions side by side.

## Backend Additions

### New Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/terminal/create` | POST | Spawn a new PTY session. Body: `{command?: string}`. Returns `{pty_id, created_at}`. If `command` is omitted, opens an interactive shell. |
| `/ws/terminal/{pty_id}` | WebSocket | Bidirectional: browser sends stdin bytes, server sends stdout/stderr bytes. Also sends `{type: "exit", code: N}` when process terminates. |
| `/api/terminal/{pty_id}/resize` | POST | Resize PTY. Body: `{cols: int, rows: int}`. |
| `/api/terminal/{pty_id}` | DELETE | Kill PTY session and its child processes. |
| `/api/terminal/sessions` | GET | List active terminal sessions with metadata. |
| `/api/export/{session_id}/html` | GET | Generate and return standalone HTML report. |

### PTY Manager

New module in the backend that manages pseudo-terminal sessions.

- Uses Python's `pty.openpty()` + `subprocess.Popen` to spawn real shell processes
- Each session gets a unique `pty_id`
- stdout/stderr read in a thread, forwarded to WebSocket clients
- stdin received from WebSocket, written to PTY
- Max 3 concurrent PTY sessions
- Auto-kill after 10 minutes of inactivity
- All commands logged to `~/.disk-analyzer/terminal.log`

### Existing Endpoints (unchanged)
- `POST /api/analysis/start` — start analysis
- `GET /api/analysis/{session_id}/progress` — poll progress
- `GET /api/analysis/{session_id}/results` — fetch results
- `WS /ws/{session_id}` — analysis progress stream
- `POST /api/cleanup/preview` — dry-run cleanup
- `POST /api/cleanup/execute` — execute cleanup
- `DELETE /api/files/delete` — delete single file
- `GET /api/system/info` — system info
- `GET /api/system/drives` — available drives
- `GET /api/sessions` — session list
- `GET /api/export/{session_id}/json` — JSON export
- `GET /api/export/{session_id}/csv` — CSV export

## Data Flow

### Analysis
1. User clicks "New Analysis" → `POST /api/analysis/start` with paths and min_size
2. Server spawns async task, returns `session_id`
3. Browser connects `WS /ws/{session_id}`
4. Server streams progress: `{percent, current_path, files_scanned}`
5. Analysis completes → `GET /api/analysis/{session_id}/results`
6. React islands render charts, file table, recommendations

### Cleanup
1. User views recommendations on Cleanup page
2. Clicks "Preview" → `POST /api/cleanup/preview` (dry_run=true)
3. UI shows what would be deleted + space freed
4. Clicks "Execute" → for file deletions: `POST /api/cleanup/execute`. For shell commands: opens in FloatingTerminal via PTY.
5. Dashboard stats update after completion

### Terminal Commands
1. User clicks "Run" on a recommendation (e.g., `brew cleanup --prune=all`)
2. `POST /api/terminal/create` with command → returns `pty_id`
3. Browser opens `WS /ws/terminal/{pty_id}`
4. FloatingTerminal auto-opens, renders live output via xterm.js
5. User can type into terminal (stdin flows back over WS)
6. Command finishes → TaskList updates status to "Completed"

### Export
1. User clicks "Export as HTML" on Export page
2. `GET /api/export/{session_id}/html`
3. Server generates self-contained HTML report (reusing `generate_html_report` from `disk_analyzer.py`)
4. Browser triggers file download

### State Management
- **Server-side:** `analysis_sessions` dict (existing) + new `terminal_sessions` dict
- **Client-side:** Each React island receives data via props (initial load) + WebSocket/fetch for updates. No global state library. Cross-island communication (e.g., "terminal opened") uses a vanilla JS event bus on `window`.

## Safety

### Terminal Safety
- **Recommended commands execute directly** — they come from the analyzer and are pre-vetted
- **Free-form commands require confirmation** — terminal shows "Run `<command>`? [y/N]" before executing
- **Blocked patterns:** `rm -rf /`, `rm -rf ~`, `mkfs`, `dd if=`, `:(){ :|:& };:` — rejected before reaching PTY
- **Command logging:** Every command logged to `~/.disk-analyzer/terminal.log` with timestamp
- **PTY timeout:** Auto-kill after 10 minutes of inactivity
- **Max 3 concurrent PTY sessions**
- **No sudo by default:** Commands needing sudo show a warning badge; user must explicitly opt in

### Cleanup Safety
- **Existing protections remain:** `is_protected_path()`, dry-run preview, system file badges with disabled checkboxes
- **Trash integration:** macOS deletions go to Trash (not permanent) via existing `osascript` logic
- **Batch confirmation:** Deleting >10 files or >1 GB triggers a confirmation modal

### Network Safety
- **Bind `0.0.0.0:8000`** — accessible on LAN, not exposed to internet
- **No auth for v1** — single-user local tool; auth can be added later
- **CORS restricted** to `localhost` + LAN IP range

### Error Handling
- **Analysis fails:** Session status → "error" with message. User can retry.
- **PTY process dies:** WebSocket sends `{type: "exit", code: N}`. Terminal shows exit status.
- **WebSocket disconnects:** Auto-reconnect with exponential backoff (1s, 2s, 4s, max 30s). Toast notification while disconnected.
- **Server crash recovery:** `sessions_metadata.json` persists session history. In-progress analyses marked "interrupted" on next startup.

## Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Static pages | Astro |
| Interactive islands | React 18+ |
| Terminal emulator | xterm.js + xterm-addon-fit |
| Charts | Plotly.js (already used in existing reports) |
| Virtual scroll | @tanstack/react-virtual |
| Backend | FastAPI + Uvicorn |
| PTY management | Python `pty` + `subprocess` |
| WebSocket | FastAPI WebSocket (existing) + new terminal WS |
| Build | `npm run build` → static files served by FastAPI |

## Out of Scope (v1)

- Authentication / multi-user
- Remote machine scanning (SSH agents)
- Database-backed session storage (in-memory + JSON file is sufficient)
- Mobile-native app
- Auto-update mechanism
