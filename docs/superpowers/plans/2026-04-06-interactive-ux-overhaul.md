# Interactive UX Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the HTML report from a passive data dashboard into an interactive, narrative-driven cleanup experience that answers "what should I delete?" within 5 seconds of opening.

**Architecture:** All changes are in `disk_analyzer.py`'s `generate_html_report()` method. The report is a self-contained HTML file with inlined CSS/JS. No backend needed — all interactivity is client-side JS operating on data already embedded as JSON constants. Changes are organized as: (1) restructure the report layout to lead with the narrative summary, (2) add interactive filtering/grouping to the file table, (3) add the guided cleanup wizard, (4) polish with responsive design and quality-of-life features.

**Tech Stack:** Python (report generator), HTML/CSS/JS (report output), Chart.js + Plotly.js (already loaded)

**Key constraint:** The HTML report is built via Python f-strings (`html += f'''...'''`) and plain strings (`html += '''...'''`). JS inside f-strings must escape `{`/`}` as `{{`/`}}`. JS inside plain strings uses normal braces.

---

## File Structure

All changes are in a single file:

- **Modify:** `disk_analyzer.py` — the `generate_html_report()` method (lines ~1500-3400) and supporting data preparation code

The report has these existing sections (in order):
1. Header + theme toggle
2. Disk usage bar card
3. Scan diff card (if available)
4. Stats grid (4 metric cards)
5. Sankey distribution (tabs)
6. Treemap/Sunburst (tabs)
7. File types chart + Age chart (side by side)
8. App usage card
9. Before/after simulation
10. Tiered cleanup plan
11. Docker card
12. Large files table
13. Duplicates card

The plan reorganizes this into a narrative flow and adds interactivity.

---

### Task 1: One-Sentence Summary Banner

**Files:**
- Modify: `disk_analyzer.py` — `generate_html_report()`, right after the `<div class="header">` block

The first thing the user sees should answer their question. Add a prominent banner between the header and the disk usage bar.

- [ ] **Step 1: Find the header block and add the summary banner after it**

Find the line containing `<p>Análisis realizado el {timestamp}</p>` and the closing `</div>` of the header. Add a banner after it.

The banner should contain:
- One sentence: "Tu disco está al X% de capacidad. Puedes liberar Y GB de forma segura. Tus mayores consumidores: App1 (Z GB), App2 (W GB), App3 (V GB)."
- Use data from: `summary['total_size']`, `disk_usage`, `report['recommendations']` (sum tier 1+2 for "safe" space), `report['app_usage']` (top 3 apps).

```python
# After the header div, before the disk usage card
# Calculate safe recoverable (tier 1 + 2)
safe_recs = [r for r in report.get('recommendations', []) if r.get('tier', 9) <= 2]
safe_space = sum(r['space'] for r in safe_recs)
top_apps = report.get('app_usage', [])[:3]
top_apps_str = ', '.join(f"{a['app']} ({self.format_size(a['size'])})" for a in top_apps)

if report.get('disk_usage') and report['disk_usage']['total'] > 0:
    pct = report['disk_usage']['used'] / report['disk_usage']['total'] * 100
    html += f'''
        <div style="background: linear-gradient(135deg, var(--primary), var(--secondary)); color: white;
                    border-radius: 16px; padding: 1.5rem 2rem; margin-bottom: 2rem;
                    box-shadow: 0 4px 16px rgba(99,102,241,0.3);">
            <p style="font-size: 1.25rem; font-weight: 600; margin-bottom: 0.5rem; line-height: 1.4;">
                Tu disco está al {pct:.0f}% de capacidad.
                {f'Puedes liberar <strong>{self.format_size(safe_space)}</strong> de forma segura.' if safe_space > 100*MB else ''}
            </p>
            {f'<p style="font-size: 1rem; opacity: 0.9;">Mayores consumidores: {top_apps_str}</p>' if top_apps_str else ''}
        </div>'''
```

- [ ] **Step 2: Test by generating a report and verifying the banner appears**

```bash
python3 disk_analyzer.py . --min-size 1 --html --export /tmp/test_banner
open /tmp/test_banner.html
```

Verify: purple gradient banner with the summary sentence appears at the top.

- [ ] **Step 3: Commit**

```bash
git add disk_analyzer.py
git commit -m "feat: one-sentence summary banner at top of HTML report"
```

---

### Task 2: "What Should I Delete?" Filter Mode

**Files:**
- Modify: `disk_analyzer.py` — the large files table section and the JS block

Add a toggle button above the file table that switches between "All files" and "Deletable only" views. In "Deletable only" mode, protected files are hidden and files are grouped by category.

- [ ] **Step 1: Add the filter toggle button above the file table**

Find the line `<h2>🗂️ Archivos Grandes</h2>` and add filter controls after it:

```python
html += '''
            <div class="card col-span-12">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h2 style="margin: 0;">🗂️ Archivos Grandes</h2>
                    <div style="display: flex; gap: 0.5rem;">
                        <button id="filterAll" onclick="filterFiles('all')" class="tab-button active"
                            style="padding: 0.4rem 0.8rem; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; background: var(--hover-bg); color: var(--dark); font-size: 0.85rem;">
                            Todos (''' + str(len(files_data)) + ''')
                        </button>
                        <button id="filterDeletable" onclick="filterFiles('deletable')" class="tab-button"
                            style="padding: 0.4rem 0.8rem; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; background: var(--hover-bg); color: var(--dark); font-size: 0.85rem;">
                            🗑️ ¿Qué puedo borrar?
                        </button>
                    </div>
                </div>'''
```

- [ ] **Step 2: Add the filterFiles JS function**

In the plain-string JS section (after the `toggleAll` function), add:

```javascript
function filterFiles(mode) {
    const rows = document.querySelectorAll('#fileTableBody tr');
    rows.forEach(row => {
        if (mode === 'deletable') {
            // Hide protected rows (those with disabled checkbox)
            const cb = row.querySelector('.file-checkbox');
            row.style.display = (cb && cb.disabled) ? 'none' : '';
        } else {
            row.style.display = '';
        }
    });
    // Toggle button active state
    document.getElementById('filterAll').classList.toggle('active', mode === 'all');
    document.getElementById('filterDeletable').classList.toggle('active', mode === 'deletable');
}
```

- [ ] **Step 3: Test filter toggle**

```bash
python3 disk_analyzer.py ~/ --min-size 50 --html --export /tmp/test_filter
open /tmp/test_filter.html
```

Click "¿Qué puedo borrar?" — protected files should disappear. Click "Todos" — they come back.

- [ ] **Step 4: Commit**

```bash
git add disk_analyzer.py
git commit -m "feat: deletable-only filter mode for file table"
```

---

### Task 3: Smart File Grouping

**Files:**
- Modify: `disk_analyzer.py` — JS section (plain string block)

When "¿Qué puedo borrar?" is active, group related files (e.g., all StarCraft data files) into collapsible groups instead of showing them individually.

- [ ] **Step 1: Prepare grouping data in the report**

In the `files_data` preparation loop (around line 1459), add a `group` field to each file based on patterns:

```python
# Add to each file_data dict:
def _get_file_group(self, path: str) -> str:
    """Groups related files together for the UI."""
    if '/StarCraft II/' in path:
        return 'StarCraft II'
    if '/Homebrew/downloads/' in path:
        return 'Homebrew Cache'
    if '/CoreSimulator/' in path:
        return 'iOS Simulator Cache'
    if '/Downloads/' in path:
        return 'Downloads'
    if '.app/' in path or '.AppBundle/' in path:
        return Path(path).parts[Path(path).parts.index(next(p for p in Path(path).parts if '.app' in p or '.AppBundle' in p))] if any('.app' in p or '.AppBundle' in p for p in Path(path).parts) else None
    return None
```

Add `'group': self._get_file_group(f['path'])` to each `files_data` entry.

- [ ] **Step 2: Add grouping JS**

Add a function that dynamically groups table rows when filter mode is 'deletable':

```javascript
function groupFiles() {
    // Read filesData, group by 'group' field, render grouped view
    const groups = {};
    const ungrouped = [];
    filesData.forEach(f => {
        if (f.is_protected) return;
        if (f.group) {
            if (!groups[f.group]) groups[f.group] = { files: [], totalSize: 0 };
            groups[f.group].files.push(f);
            groups[f.group].totalSize += f.size;
        } else {
            ungrouped.push(f);
        }
    });
    // Render: each group as a collapsible header row, ungrouped as normal rows
    // ... (build HTML and replace table body)
}
```

- [ ] **Step 3: Test grouping**

Scan `/` or `~/` and verify StarCraft files collapse into one group row.

- [ ] **Step 4: Commit**

```bash
git add disk_analyzer.py
git commit -m "feat: smart file grouping in deletable-only view"
```

---

### Task 4: Guided Cleanup Wizard

**Files:**
- Modify: `disk_analyzer.py` — add a new card section and JS

Add a step-by-step cleanup wizard that walks the user through each recommendation interactively.

- [ ] **Step 1: Add the wizard card in the HTML**

Place it right after the summary banner (Task 1) and before the disk usage bar. It should be the second thing the user sees.

```python
# Wizard card
recs = report.get('recommendations', [])
if recs:
    html += f'''
        <div class="card" style="margin-bottom: 2rem; border: 2px solid var(--primary);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <h2 style="margin: 0;">🧹 Limpieza Guiada</h2>
                <span id="wizardProgress" style="color: var(--gray); font-size: 0.9rem;">Paso 1 de {len(recs[:8])}</span>
            </div>
            <div id="wizardFreed" style="text-align: center; padding: 0.75rem; background: var(--hover-bg);
                        border-radius: 8px; margin-bottom: 1rem; font-size: 1.1rem; color: var(--success); font-weight: 600;">
                Espacio liberado: 0 B
            </div>
            <div id="wizardContent">
                <!-- Populated by JS -->
            </div>
            <div style="display: flex; justify-content: space-between; margin-top: 1rem;">
                <button onclick="wizardPrev()" id="wizardPrevBtn" class="btn" disabled
                    style="padding: 0.5rem 1.5rem; border: 1px solid var(--border); border-radius: 8px;
                           cursor: pointer; background: var(--card-bg); color: var(--dark);">← Anterior</button>
                <button onclick="wizardNext()" id="wizardNextBtn" class="btn"
                    style="padding: 0.5rem 1.5rem; border: none; border-radius: 8px;
                           cursor: pointer; background: var(--primary); color: white; font-weight: 600;">Siguiente →</button>
            </div>
        </div>'''
```

- [ ] **Step 2: Add the wizard JS**

In the plain-string JS section:

```javascript
// Wizard state
const wizardRecs = /* injected JSON of recommendations */;
let wizardStep = 0;
let wizardFreed = 0;
const wizardSkipped = new Set();

function renderWizardStep() {
    const rec = wizardRecs[wizardStep];
    const tierIcons = {1:'🟢', 2:'🟡', 3:'🟠', 4:'🔴'};
    const content = document.getElementById('wizardContent');
    content.innerHTML = `
        <div style="padding: 1rem; border: 1px solid var(--border); border-radius: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <span style="font-size: 1.3rem;">${tierIcons[rec.tier] || '⚪'}</span>
                <strong style="flex: 1; margin-left: 0.75rem; font-size: 1.1rem;">${rec.type}</strong>
                <span style="font-weight: 700; color: var(--primary); font-size: 1.2rem;">${formatBytes(rec.space)}</span>
            </div>
            <p style="color: var(--gray); margin: 0.5rem 0;">${rec.description}</p>
            ${rec.command && !rec.command.startsWith('#') ? `
                <div style="background: var(--code-bg); color: #e2e8f0; padding: 0.75rem; border-radius: 8px;
                            font-family: monospace; font-size: 0.85rem; margin: 0.75rem 0; cursor: pointer;"
                     onclick="navigator.clipboard.writeText(this.textContent.trim())" title="Click to copy">
                    ${rec.command}
                </div>` : ''}
            <div style="display: flex; gap: 0.5rem; margin-top: 1rem;">
                <button onclick="wizardApply()" style="flex: 1; padding: 0.6rem; border: none; border-radius: 8px;
                    background: var(--success); color: white; cursor: pointer; font-weight: 600; font-size: 0.95rem;">
                    ✓ Limpiar (${formatBytes(rec.space)})
                </button>
                <button onclick="wizardSkip()" style="flex: 1; padding: 0.6rem; border: 1px solid var(--border);
                    border-radius: 8px; background: var(--card-bg); color: var(--gray); cursor: pointer; font-size: 0.95rem;">
                    Omitir
                </button>
            </div>
        </div>`;
    document.getElementById('wizardProgress').textContent =
        `Paso ${wizardStep + 1} de ${wizardRecs.length}`;
    document.getElementById('wizardPrevBtn').disabled = wizardStep === 0;
    document.getElementById('wizardNextBtn').textContent =
        wizardStep >= wizardRecs.length - 1 ? '✓ Listo' : 'Siguiente →';
}

function wizardApply() {
    wizardFreed += wizardRecs[wizardStep].space;
    document.getElementById('wizardFreed').textContent =
        'Espacio liberado: ' + formatBytes(wizardFreed);
    wizardNext();
}

function wizardSkip() {
    wizardSkipped.add(wizardStep);
    wizardNext();
}

function wizardNext() {
    if (wizardStep < wizardRecs.length - 1) {
        wizardStep++;
        renderWizardStep();
    } else {
        // Done - show summary
        document.getElementById('wizardContent').innerHTML = `
            <div style="text-align: center; padding: 2rem;">
                <div style="font-size: 3rem; margin-bottom: 1rem;">🎉</div>
                <p style="font-size: 1.2rem; font-weight: 600; color: var(--dark);">
                    ${wizardFreed > 0 ? 'Marcados ' + formatBytes(wizardFreed) + ' para limpiar' : 'No se seleccionó nada para limpiar'}
                </p>
                <p style="color: var(--gray);">Ejecuta los comandos copiados en tu terminal</p>
            </div>`;
    }
}

function wizardPrev() {
    if (wizardStep > 0) {
        wizardStep--;
        renderWizardStep();
    }
}

// Initialize
if (wizardRecs.length > 0) renderWizardStep();
```

- [ ] **Step 3: Inject wizardRecs data**

In the f-string JS data section, add:
```python
const wizardRecs = {json.dumps(report.get('recommendations', [])[:8])};
```

- [ ] **Step 4: Test the wizard**

```bash
python3 disk_analyzer.py ~/ --min-size 10 --html --export /tmp/test_wizard
open /tmp/test_wizard.html
```

Verify: wizard shows step 1, clicking "Limpiar" advances and adds to the counter, clicking "Omitir" advances without adding.

- [ ] **Step 5: Commit**

```bash
git add disk_analyzer.py
git commit -m "feat: guided cleanup wizard in HTML report"
```

---

### Task 5: Narrative "Why Is My Disk Full?" Section

**Files:**
- Modify: `disk_analyzer.py` — add a new card section

Replace the app usage cards with a narrative paragraph that tells the story of where space goes.

- [ ] **Step 1: Build the narrative from existing data**

After the stats grid and before the Sankey, add a storytelling card:

```python
# Build narrative
narrative_parts = []
if report.get('disk_usage'):
    du = report['disk_usage']
    # System
    skipped = report.get('skipped_volumes_size', 0)
    if skipped > 1 * GB:
        narrative_parts.append(f"<strong>macOS</strong> ocupa {self.format_size(skipped)} (sistema, swap, boot)")

# Categories from the disk bar
for cat in categories:
    if cat['name'] in ('Libre', 'Sin permisos (sudo)', 'APFS purgeable', 'Sistema (macOS)'):
        continue
    if cat['size'] > 1 * GB:
        narrative_parts.append(f"<strong>{cat['name']}</strong> ocupa {self.format_size(cat['size'])} ({cat['percent']:.0f}%)")

if narrative_parts:
    html += f'''
        <div class="card" style="margin-bottom: 2rem;">
            <h2>📖 ¿Por qué está lleno tu disco?</h2>
            <div style="font-size: 1rem; line-height: 1.8; color: var(--dark);">
                {"<br>".join(f"• {p}" for p in narrative_parts)}
            </div>
        </div>'''
```

- [ ] **Step 2: Test and commit**

```bash
python3 disk_analyzer.py . --min-size 1 --html --export /tmp/test_narrative
open /tmp/test_narrative.html
git add disk_analyzer.py
git commit -m "feat: narrative 'why is your disk full' section"
```

---

### Task 6: Actionability-Colored Disk Bar

**Files:**
- Modify: `disk_analyzer.py` — the disk usage bar generation code

Add a second disk bar (below the existing one) that colors segments by actionability instead of category.

- [ ] **Step 1: Compute actionability segments**

After the existing category bar, compute 4 segments:
- **Green** (cleanable now): sum of tier 1+2 recommendations
- **Orange** (worth investigating): sum of tier 3+4 recommendations
- **Blue** (your stuff): documents, media, downloads (non-old)
- **Gray** (can't change): system, apps, protected

```python
safe_clean = sum(r['space'] for r in report.get('recommendations', []) if r.get('tier', 9) <= 2)
investigate = sum(r['space'] for r in report.get('recommendations', []) if r.get('tier', 9) in (3, 4))
system_space = skipped_size + category_sizes.get('Applications', 0)
your_stuff = analyzed_total - safe_clean - investigate - system_space
your_stuff = max(0, your_stuff)

action_segments = [
    {'name': 'Limpiable ahora', 'size': safe_clean, 'color': '#10b981'},
    {'name': 'Vale investigar', 'size': investigate, 'color': '#f97316'},
    {'name': 'Tus archivos', 'size': max(your_stuff, 0), 'color': '#3b82f6'},
    {'name': 'Sistema/Apps', 'size': system_space, 'color': '#94a3b8'},
]
```

- [ ] **Step 2: Render the second bar**

Render it in the same card as the existing disk bar, below it, with a label "Vista por acción":

```python
html += '''
    <p style="color: var(--gray); font-size: 0.8rem; margin: 1rem 0 0.5rem; font-weight: 600;">Vista por acción:</p>
    <div style="height: 30px; border-radius: 15px; overflow: hidden; display: flex;">'''
for seg in action_segments:
    if seg['size'] > 0:
        w = seg['size'] / disk_usage['total'] * 100
        html += f'''
        <div style="width: {w:.1f}%; background: {seg['color']}; display: flex; align-items: center;
                    justify-content: center; font-size: 0.7rem; color: white; font-weight: 600;
                    text-shadow: 0 1px 2px rgba(0,0,0,0.3);">
            {seg['name'] if w > 8 else ''}
        </div>'''
html += '</div>'
```

- [ ] **Step 3: Test and commit**

```bash
python3 disk_analyzer.py ~/ --min-size 10 --html --export /tmp/test_actionbar
open /tmp/test_actionbar.html
git add disk_analyzer.py
git commit -m "feat: actionability-colored disk bar"
```

---

### Task 7: Responsive Mobile Layout

**Files:**
- Modify: `disk_analyzer.py` — CSS section

- [ ] **Step 1: Add responsive breakpoints**

Find the existing `@media (max-width: 768px)` block and expand it:

```css
@media (max-width: 768px) {
    .container { padding: 1rem; }
    .header h1 { font-size: 1.5rem; }
    .dashboard-grid { grid-template-columns: 1fr; }
    .col-span-4, .col-span-6, .col-span-8, .col-span-12 { grid-column: span 1; }
    .stats-grid { grid-template-columns: repeat(2, 1fr); gap: 0.75rem; }
    .stat-card .value { font-size: 1.3rem; }
    .file-table { font-size: 0.8rem; }
    .file-table th:nth-child(4), .file-table td:nth-child(4),
    .file-table th:nth-child(5), .file-table td:nth-child(5) { display: none; }
    .command-box { font-size: 0.75rem; }
    .theme-toggle { top: 0.5rem; right: 0.5rem; padding: 0.4rem 0.7rem; }
    .action-bar { flex-direction: column; gap: 0.5rem; }
    .tier-content { padding: 0.5rem !important; }
}
```

- [ ] **Step 2: Test on mobile viewport and commit**

Open the report in Chrome, use Device Toolbar (Cmd+Shift+M), test iPhone and iPad sizes.

```bash
git add disk_analyzer.py
git commit -m "feat: responsive mobile layout for HTML report"
```

---

### Task 8: Sound Notification + Time Estimate

**Files:**
- Modify: `disk_analyzer.py` — the `analyze()` method and `scan_directory()`

- [ ] **Step 1: Add time estimate to progress**

In `scan_directory`, after updating `pct`, estimate remaining time:

```python
if pct > 5 and hasattr(self, '_scan_start_time'):
    elapsed = time.time() - self._scan_start_time
    estimated_total = elapsed / (pct / 100)
    remaining = estimated_total - elapsed
    mins = int(remaining // 60)
    secs = int(remaining % 60)
    time_str = f" (~{mins}m {secs}s restantes)" if mins > 0 else f" (~{secs}s restantes)"
else:
    time_str = ""
```

Set `self._scan_start_time = time.time()` at the start of `analyze()`.

- [ ] **Step 2: Add macOS notification sound when scan completes**

At the end of `analyze()`, after the Docker analysis:

```python
# Sound notification on macOS
if self.is_macos:
    try:
        subprocess.run(['afplay', '/System/Library/Sounds/Glass.aiff'], capture_output=True, timeout=5)
    except Exception:
        pass
```

- [ ] **Step 3: Commit**

```bash
git add disk_analyzer.py
git commit -m "feat: time estimate during scan + completion sound"
```

---

### Task 9: "Copy All Safe Commands" Button

**Files:**
- Modify: `disk_analyzer.py` — the tiered cleanup plan section and JS

- [ ] **Step 1: Add a "Copy all safe commands" button at the top of the cleanup plan**

After the `<h2>💡 Plan de Limpieza</h2>` line:

```python
# Collect all tier 1+2 commands
safe_commands = [r['command'] for r in recs if r.get('tier', 9) <= 2
                 and r.get('command') and not r['command'].startswith('#')]
if safe_commands:
    all_cmds_json = json.dumps(' && '.join(safe_commands))
    html += f'''
        <div style="margin-bottom: 1rem; display: flex; gap: 0.5rem;">
            <button onclick="navigator.clipboard.writeText({all_cmds_json}); this.textContent='✓ Copiado!'; setTimeout(() => this.textContent='📋 Copiar comandos seguros', 2000)"
                style="padding: 0.5rem 1rem; border: 1px solid var(--success); border-radius: 8px;
                       background: rgba(16,185,129,0.1); color: var(--success); cursor: pointer; font-weight: 600;">
                📋 Copiar comandos seguros (Nivel 1+2)
            </button>
        </div>'''
```

- [ ] **Step 2: Test and commit**

```bash
python3 disk_analyzer.py ~/ --min-size 10 --html --export /tmp/test_copyall
open /tmp/test_copyall.html
git add disk_analyzer.py
git commit -m "feat: copy-all-safe-commands button in cleanup plan"
```

---

### Task 10: Dismissed Items Memory

**Files:**
- Modify: `disk_analyzer.py` — JS section

Add localStorage-based dismissal so the wizard remembers what the user skipped.

- [ ] **Step 1: Add dismiss/remember logic to the wizard**

In the wizard JS:

```javascript
// Load dismissed items
const dismissed = JSON.parse(localStorage.getItem('disk-analyzer-dismissed') || '{}');
const now = Date.now();
// Clean expired dismissals (>30 days)
Object.keys(dismissed).forEach(k => {
    if (now - dismissed[k] > 30 * 24 * 60 * 60 * 1000) delete dismissed[k];
});

function wizardSkip() {
    const rec = wizardRecs[wizardStep];
    dismissed[rec.type] = Date.now();
    localStorage.setItem('disk-analyzer-dismissed', JSON.stringify(dismissed));
    wizardNext();
}

// Filter wizard recs to exclude recently dismissed
const activeWizardRecs = wizardRecs.filter(r => !dismissed[r.type]);
```

- [ ] **Step 2: Test and commit**

Open report, skip an item, close, regenerate report, verify the item is still skipped. Wait (or manually set localStorage date to 31 days ago) and verify it comes back.

```bash
git add disk_analyzer.py
git commit -m "feat: wizard remembers dismissed items for 30 days"
```

---

### Task 11: Final Polish and Integration Test

**Files:**
- Modify: `disk_analyzer.py` — reorder sections for narrative flow

- [ ] **Step 1: Reorder the HTML report sections for narrative flow**

The ideal order (top to bottom):
1. Header + theme toggle
2. **Summary banner** (Task 1) — "Your disk is 92% full..."
3. **Guided wizard** (Task 4) — "Step 1: Clean Homebrew cache?"
4. Disk usage bar + **actionability bar** (Task 6)
5. Stats grid
6. Scan diff (if available)
7. **Narrative** (Task 5) — "Why is your disk full?"
8. App usage cards
9. Before/after simulation
10. Tiered cleanup plan + **copy all** (Task 9)
11. Treemap/Sunburst
12. Sankey
13. File type chart + Age chart
14. File table with **filter** (Task 2) and **grouping** (Task 3)
15. Duplicates
16. Docker

- [ ] **Step 2: Full integration test**

```bash
# Test with home directory
python3 disk_analyzer.py ~/ --min-size 10 --html --export /tmp/test_final
open /tmp/test_final.html

# Test with root (sudo)
sudo python3 disk_analyzer.py / --min-size 50 --html --export /tmp/test_root
open /tmp/test_root.html

# Test with small directory
python3 disk_analyzer.py . --min-size 1 --html --export /tmp/test_small
open /tmp/test_small.html
```

Verify for each:
- Summary banner shows correct numbers
- Wizard works (next, skip, apply, done state)
- Both disk bars render correctly (category + actionability)
- Filter toggle shows/hides protected files
- Mobile layout works (Chrome Device Toolbar)
- Dark mode works on all new elements
- Scan diff shows (if not first scan)
- Time estimate shows during scan
- Sound plays on completion

- [ ] **Step 3: Final commit**

```bash
git add disk_analyzer.py
git commit -m "feat: reorder report for narrative flow + integration test"
```
