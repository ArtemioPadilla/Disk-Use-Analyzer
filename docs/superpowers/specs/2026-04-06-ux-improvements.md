# UX Improvements Spec

**Date:** 2026-04-06
**Status:** Draft
**Scope:** Improve first-run experience, visual exploration, and cleanup flow in the hosted web UI

## Current Pain Points

### 1. Cold start is dead
Every page says "Run an analysis first." The user sees empty cards, empty charts, empty file list. There's no guidance, no momentum. They have to figure out: click New Analysis → pick paths → set size → wait. That's 4 steps before seeing any value.

### 2. No visual exploration
DaisyDisk, GrandPerspective, and WinDirStat are popular because of one thing: a clickable visual map where you can *see* what's eating your disk and drill into it. Our file browser is a flat table. The treemap on the dashboard is passive — you can't click into a directory.

### 3. Cleanup is intimidating
The Cleanup page shows terminal commands with a "Run" button. Most users don't want to see `rm -rf` or `brew cleanup --prune=all`. They want a "Free 18 GB" button with a confirmation.

### 4. No feedback loop
After cleaning, nothing updates. The dashboard still shows the old numbers. There's no "You freed 3.2 GB!" moment. No before/after comparison.

### 5. Analysis progress is invisible from the dashboard
The TaskList component updates, but there's no prominent progress bar. If the scan takes 5 minutes, the user doesn't know if it's 10% or 90% done.

### 6. Results vanish on restart
Server restarts = all results gone. Only session metadata is persisted, not full analysis results.

## Ideas

### High Impact, Moderate Effort

#### A. One-click "Scan My Mac" on first visit
If no previous analysis exists, the dashboard shows a big hero card: "Scan your home directory" with a single button. No modal, no path picking. Just go. Advanced options available but not required.

- Default path: `~/`
- Default min_size: from settings or server flag
- One button: "Scan My Mac"
- Small link below: "Advanced options" opens the existing modal

#### B. Interactive treemap/sunburst
Replace the passive treemap with a clickable one. Click a directory to drill in. Breadcrumb trail at top. This is the "wow" feature that makes disk analyzers feel useful.

- Plotly treemap supports click events (`plotly_click`)
- On click: filter to that directory's children, update breadcrumb
- Breadcrumb: `/ > Users > artemio > Library > Caches` (clickable at each level)
- Color by category (Development, Cache, Docker, Documents, etc.)
- Hover shows: directory name, size, % of parent

#### C. One-click cleanup with summary
Instead of showing commands, show: "Free 4.2 GB of caches" with a single button. Behind the scenes it runs the commands, shows a progress bar, and reports what was freed. Terminal is still available for power users but isn't the default.

- Dashboard cleanup card: "You can free X GB" with tier breakdown
- "Clean Safe Items" button (tier 1 only) — no confirmation needed
- "Clean All" button — shows confirmation with tier breakdown
- Progress bar during cleanup
- Completion toast: "Freed 3.2 GB! Dashboard updated."
- "Show commands" toggle for power users who want to see what ran

#### D. Live progress bar on dashboard
A prominent animated bar across the top of the content area during analysis, showing percent, files scanned, current directory.

- Full-width bar below the TopBar, visible from any page
- Shows: progress %, files scanned count, current directory path (truncated)
- Animated gradient fill
- Disappears when analysis completes
- Listens to `analysis:progress` events

### Medium Impact, Low Effort

#### E. Auto-refresh after cleanup
After any cleanup action completes, re-scan affected paths and update the dashboard numbers. Show a "before → after" comparison toast.

- After cleanup API returns, trigger a lightweight re-scan of affected paths
- Show toast: "Before: 245.3 GB used → After: 241.1 GB used (freed 4.2 GB)"
- Update StatsCards and charts without full page reload

#### F. Quick-action cards on dashboard
Below the stats, show 2-3 cards like "2.1 GB of npm caches", "1.8 GB of Xcode simulators" with a "Clean" button right there. No need to navigate to the Cleanup page.

- Show top 3 recommendations from tier 1 (safe) as cards
- Each card: icon, description, space recoverable, "Clean" button
- On click: run cleanup, show progress, update card to "Cleaned ✓"
- Only visible after analysis completes

#### G. Browser notification when analysis completes
`Notification.requestPermission()` + notify when done. Users can switch tabs while scanning.

- Request permission on first analysis start
- Fire notification on `analysis:completed` event
- Title: "Disk Analysis Complete"
- Body: "Found X GB recoverable space across Y files"

#### H. Persist results to disk
Save full analysis results as JSON, not just metadata. Survive server restarts.

- On analysis completion, write results to `~/.disk-analyzer/results/{session_id}.json`
- On server startup, load most recent result
- Dashboard shows last result immediately on load (no cold start)
- History page can load any past result from disk
- Auto-prune: keep last 10 results, delete older ones

### Lower Priority

#### I. Mobile-responsive layout
Collapse sidebar to hamburger menu on small screens. People will access from phones on the same LAN.

- Media query at 768px breakpoint
- Sidebar becomes slide-out drawer with hamburger button
- Stats cards stack vertically
- File table becomes a card list on mobile
- Floating terminal becomes full-width bottom sheet

#### J. Scheduled scans
"Run every Sunday at 2am" with a summary saved to history.

- Settings page: cron-style schedule picker
- Background task on the server using `asyncio` scheduler
- Results saved to disk (uses feature H)
- Dashboard shows "Last scan: 2 days ago" with a "Scan now" button

#### K. Comparison view
Pick two sessions from history, show what changed (new large files, freed space, growth trends).

- History page: checkbox to select two sessions
- "Compare" button opens side-by-side view
- Shows: total size delta, new/removed large files, category changes
- Useful for tracking disk growth over time

## Recommended Implementation Order

**Phase 1 — Fix the first 60 seconds (A + D + H):**
One-click scan, live progress, persist results so the dashboard isn't empty on restart.

**Phase 2 — Make cleanup effortless (C + F + E):**
One-click cleanup cards, auto-refresh, before/after feedback.

**Phase 3 — Visual exploration (B + G):**
Interactive treemap with drill-down, browser notifications.

**Phase 4 — Polish (I + J + K):**
Mobile layout, scheduled scans, comparison view.
