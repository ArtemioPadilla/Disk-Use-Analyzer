// Disk Analyzer Web App
const API_BASE = '/api';
let currentSession = null;
let selectedPaths = [];
let ws = null;
let analysisResults = null;
let lastProgressPercent = 0;  // Track last progress to prevent going backwards
let allLargeFiles = [];  // Cached large files for search/sort

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    loadSystemInfo();
    checkSavedSessions();
    initializeEventListeners();
});

// Event Listeners
function initializeEventListeners() {
    // Theme toggle
    const savedTheme = localStorage.getItem('theme') || 'light';
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-theme');
        document.querySelector('.theme-toggle i').classList.replace('fa-moon', 'fa-sun');
    }

    // Slider
    const slider = document.getElementById('min-size');
    if (slider) {
        slider.addEventListener('input', (e) => {
            document.getElementById('min-size-value').textContent = `${e.target.value} MB`;
        });
    }

    // File search
    const fileSearch = document.getElementById('file-search');
    if (fileSearch) {
        fileSearch.addEventListener('input', () => {
            renderFilteredFiles();
        });
    }

    // File sort
    const fileSort = document.getElementById('file-sort');
    if (fileSort) {
        fileSort.addEventListener('change', () => {
            sortLargeFiles();
            renderFilteredFiles();
        });
    }
}

// Theme Toggle
function toggleTheme() {
    document.body.classList.toggle('dark-theme');
    const icon = document.querySelector('.theme-toggle i');
    
    if (document.body.classList.contains('dark-theme')) {
        icon.classList.replace('fa-moon', 'fa-sun');
        localStorage.setItem('theme', 'dark');
    } else {
        icon.classList.replace('fa-sun', 'fa-moon');
        localStorage.setItem('theme', 'light');
    }
}

// View Management
function showView(viewId) {
    document.querySelectorAll('.view').forEach(view => {
        view.style.display = 'none';
    });
    document.getElementById(viewId).style.display = 'block';
}

// System Info
async function loadSystemInfo() {
    try {
        const response = await fetch(`${API_BASE}/system/info`);
        const data = await response.json();
        
        const info = `${data.platform} | ${formatSize(data.disk_usage.free)} free`;
        document.getElementById('system-info').textContent = info;
    } catch (error) {
        console.error('Failed to load system info:', error);
    }
}

// Session Management
async function checkSavedSessions() {
    try {
        // First check API for server sessions
        const response = await fetch(`${API_BASE}/sessions`);
        if (response.ok) {
            const data = await response.json();
            if (data.sessions && data.sessions.length > 0) {
                displayRecentAnalyses(data.sessions);
                return;
            }
        }
    } catch (error) {
        console.error('Failed to fetch sessions from API:', error);
    }
    
    // Fall back to localStorage
    const sessions = JSON.parse(localStorage.getItem('analysis_sessions') || '[]');
    if (sessions.length > 0) {
        displayRecentAnalyses(sessions);
    }
}

function displayRecentAnalyses(sessions) {
    const container = document.getElementById('recent-analyses');
    const list = document.getElementById('recent-list');
    
    list.innerHTML = sessions.slice(0, 5).map(session => {
        const date = new Date(session.started_at || session.date);
        const status = session.status || 'completed';
        const hasResults = session.results !== null && session.results !== undefined;
        
        let statusIcon, statusClass, statusText;
        if (status === 'completed') {
            if (hasResults) {
                statusIcon = '✓';
                statusClass = 'text-success';
                statusText = 'Complete';
            } else {
                statusIcon = '⚠';
                statusClass = 'text-warning';
                statusText = 'No data';
            }
        } else if (status === 'running') {
            statusIcon = '⟳';
            statusClass = 'text-primary';
            statusText = 'Running';
        } else {
            statusIcon = '✗';
            statusClass = 'text-danger';
            statusText = 'Failed';
        }
        
        return `
        <div class="recent-item">
            <span>${date.toLocaleDateString()}</span>
            <span>${session.paths.join(', ')}</span>
            <span class="${statusClass}" title="${statusText}">${statusIcon}</span>
            <button class="btn btn-sm" onclick="loadSession('${session.id}')">View</button>
        </div>
        `;
    }).join('');
    
    container.style.display = 'block';
}

// Load a previous session
async function loadSession(sessionId) {
    try {
        // First check if session results are available
        const response = await fetch(`${API_BASE}/analysis/${sessionId}/results`);
        
        if (response.ok) {
            currentSession = sessionId;
            analysisResults = await response.json();
            
            // Show results view
            showView('results-view');
            displayResults();
        } else if (response.status === 410) {
            // Results no longer available (server restarted)
            const errorData = await response.json();
            alert(errorData.detail || 'Session results no longer available. Please run a new analysis.');
        } else if (response.status === 400) {
            // Analysis not completed, check progress
            const progressResponse = await fetch(`${API_BASE}/analysis/${sessionId}/progress`);
            if (progressResponse.ok) {
                const progress = await progressResponse.json();
                
                if (progress.status === 'running') {
                    // Analysis still running, reconnect to WebSocket
                    currentSession = sessionId;
                    showView('wizard-view');
                    
                    // Move to progress step
                    document.querySelectorAll('.wizard-content').forEach(content => {
                        content.style.display = 'none';
                    });
                    document.querySelectorAll('.step').forEach(step => {
                        step.classList.remove('active');
                        step.classList.remove('completed');
                    });
                    
                    const step3 = document.querySelector('.step[data-step="3"]');
                    step3.classList.add('active');
                    document.getElementById('step-3').style.display = 'block';
                    
                    // Connect WebSocket to resume progress updates
                    connectWebSocket(sessionId);
                } else if (progress.status === 'error') {
                    alert('Analysis failed: ' + (progress.error || 'Unknown error'));
                } else {
                    alert('Analysis status: ' + progress.status);
                }
            } else {
                alert('Unable to check analysis progress.');
            }
        } else if (response.status === 404) {
            alert('Session not found.');
        } else {
            const errorData = await response.json();
            alert(errorData.detail || 'Failed to load session.');
        }
    } catch (error) {
        console.error('Failed to load session:', error);
        alert('Failed to load session. Please try again.');
    }
}

// Analysis Wizard
function startAnalysis() {
    showView('wizard-view');
    loadDrivesAndPaths();
}

async function loadDrivesAndPaths() {
    try {
        const response = await fetch(`${API_BASE}/system/drives`);
        const data = await response.json();
        
        // Display drives
        const drivesList = document.getElementById('drives-list');
        drivesList.innerHTML = data.drives.map(drive => `
            <div class="drive-item" onclick="togglePath('${drive.path}')">
                <div class="drive-info">
                    <strong>${drive.letter || drive.path}</strong>
                    <span>${formatSize(drive.free)} free of ${formatSize(drive.total)}</span>
                </div>
                <div class="drive-usage">
                    <div class="usage-bar">
                        <div class="usage-fill" style="width: ${drive.percent}%"></div>
                    </div>
                    <span>${Math.round(drive.percent)}%</span>
                </div>
            </div>
        `).join('');
        
        // Display common paths
        const commonPaths = document.getElementById('common-paths');
        commonPaths.innerHTML = data.common_paths.map(path => `
            <div class="path-item" onclick="togglePath('${path.path}')">
                <span>${path.name}</span>
                <small>${path.path}</small>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Failed to load drives:', error);
    }
}

function togglePath(path) {
    const index = selectedPaths.indexOf(path);
    if (index > -1) {
        selectedPaths.splice(index, 1);
    } else {
        selectedPaths.push(path);
    }
    updateSelectedPaths();
}

function addCustomPath() {
    const input = document.getElementById('custom-path-input');
    const path = input.value.trim();
    
    if (path && !selectedPaths.includes(path)) {
        selectedPaths.push(path);
        updateSelectedPaths();
        input.value = '';
    }
}

function updateSelectedPaths() {
    const list = document.getElementById('selected-paths-list');
    list.innerHTML = selectedPaths.map(path => `
        <span class="selected-path-tag">
            ${path}
            <i class="fas fa-times" onclick="removePath('${path}')"></i>
        </span>
    `).join('');
    
    // Update UI to show selected items
    document.querySelectorAll('.drive-item, .path-item').forEach(item => {
        const path = item.onclick.toString().match(/'([^']+)'/)[1];
        if (selectedPaths.includes(path)) {
            item.classList.add('selected');
        } else {
            item.classList.remove('selected');
        }
    });
    
    // Enable/disable next button
    document.getElementById('next-step-1').disabled = selectedPaths.length === 0;
}

function removePath(path) {
    selectedPaths = selectedPaths.filter(p => p !== path);
    updateSelectedPaths();
}

// Wizard Navigation
function nextStep() {
    const currentStep = document.querySelector('.step.active');
    const currentContent = document.querySelector('.wizard-content:not([style*="display: none"])');
    const stepNumber = parseInt(currentStep.dataset.step);
    
    if (stepNumber === 1 && selectedPaths.length === 0) {
        alert('Please select at least one path to analyze');
        return;
    }
    
    // Hide current step
    currentContent.style.display = 'none';
    currentStep.classList.remove('active');
    currentStep.classList.add('completed');
    
    // Show next step
    const nextStep = document.querySelector(`.step[data-step="${stepNumber + 1}"]`);
    const nextContent = document.getElementById(`step-${stepNumber + 1}`);
    
    nextStep.classList.add('active');
    nextContent.style.display = 'block';
}

function previousStep() {
    const currentStep = document.querySelector('.step.active');
    const currentContent = document.querySelector('.wizard-content:not([style*="display: none"])');
    const stepNumber = parseInt(currentStep.dataset.step);
    
    // Hide current step
    currentContent.style.display = 'none';
    currentStep.classList.remove('active');
    
    // Show previous step
    const prevStep = document.querySelector(`.step[data-step="${stepNumber - 1}"]`);
    const prevContent = document.getElementById(`step-${stepNumber - 1}`);
    
    prevStep.classList.remove('completed');
    prevStep.classList.add('active');
    prevContent.style.display = 'block';
}

// Start Analysis
async function startAnalysisRun() {
    const minSize = document.getElementById('min-size').value;
    const categories = {};
    
    document.querySelectorAll('input[name="category"]:checked').forEach(cb => {
        categories[cb.value] = true;
    });
    
    // Reset progress tracking
    lastProgressPercent = 0;
    
    // Move to progress step
    nextStep();
    
    // Connect WebSocket first, before starting analysis
    const tempSessionId = 'pending-' + Date.now();
    
    // Start analysis
    try {
        const response = await fetch(`${API_BASE}/analysis/start`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                paths: selectedPaths,
                min_size_mb: parseFloat(minSize),
                categories: categories
            })
        });
        
        const data = await response.json();
        currentSession = data.id;
        
        // Connect WebSocket for progress
        console.log('Starting analysis with session:', currentSession);
        
        // Small delay to ensure backend is ready
        setTimeout(() => {
            connectWebSocket(currentSession);
        }, 100);
        
        // Save session
        saveSession(currentSession, selectedPaths);
        
    } catch (error) {
        console.error('Failed to start analysis:', error);
        alert('Failed to start analysis. Please try again.');
    }
}

// WebSocket Connection
function connectWebSocket(sessionId) {
    const wsUrl = `ws://${window.location.host}/ws/${sessionId}`;
    console.log('Connecting to WebSocket:', wsUrl);
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket connected successfully');
    };
    
    ws.onmessage = (event) => {
        console.log('Raw WebSocket message:', event.data);
        const data = JSON.parse(event.data);
        handleProgressUpdate(data);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    ws.onclose = () => {
        console.log('WebSocket disconnected');
    };
}

// Progress Updates
function handleProgressUpdate(data) {
    console.log('Received WebSocket message:', data);
    
    switch (data.type) {
        case 'status':
            console.log('Initial status received:', data.session);
            break;
        case 'progress':
            console.log('Progress update:', data.overall_progress + '%');
            updateOverallProgress(data);
            break;
        case 'file_progress':
            console.log('File progress:', data);
            updateFileProgress(data);
            // Also check for phase in message
            if (data.message && data.phase) {
                // Update the current path text with the message for non-disk-scan phases
                if (data.phase !== 'disk_scan') {
                    const currentPathText = document.getElementById('current-path-text');
                    currentPathText.textContent = data.message;
                }
            }
            break;
        case 'completed':
            console.log('Analysis completed');
            analysisCompleted(data);
            break;
        case 'error':
            console.error('Analysis error:', data);
            analysisError(data);
            break;
        default:
            console.log('Unknown message type:', data.type);
    }
}

function updateOverallProgress(data) {
    // Only update percentage if it's explicitly provided and not going backwards
    if (data.overall_progress !== undefined && data.overall_progress !== null) {
        const percent = Math.round(data.overall_progress);
        if (percent >= lastProgressPercent) {
            lastProgressPercent = percent;
            document.getElementById('progress-percent').textContent = `${percent}%`;
            
            // Update SVG arc
            const arc = document.getElementById('progress-arc');
            const circumference = 2 * Math.PI * 90;
            const offset = circumference - (percent / 100) * circumference;
            arc.style.strokeDashoffset = offset;
        }
    }
    
    // Update current path with animation
    const currentPathText = document.getElementById('current-path-text');
    const pathDisplay = data.current_path || 'Preparing to scan...';
    
    // Truncate long paths
    if (pathDisplay.length > 60) {
        currentPathText.textContent = '...' + pathDisplay.substring(pathDisplay.length - 57);
    } else {
        currentPathText.textContent = pathDisplay;
    }
    
    // Add subtle animation to stats
    const stats = document.querySelectorAll('.progress-stat');
    stats.forEach(stat => {
        stat.classList.add('updated');
        setTimeout(() => stat.classList.remove('updated'), 500);
    });
    
    // Add progress message
    addProgressMessage(`Analyzing ${data.path_index} of ${data.total_paths}: ${data.current_path}`);
}

function updateFileProgress(data) {
    if (data.files_scanned !== undefined) {
        const filesScanned = document.getElementById('files-scanned');
        filesScanned.textContent = data.files_scanned.toLocaleString();
        filesScanned.parentElement.classList.add('updated');
        setTimeout(() => filesScanned.parentElement.classList.remove('updated'), 500);
    }
    if (data.large_files_found !== undefined) {
        const largeFiles = document.getElementById('large-files');
        largeFiles.textContent = data.large_files_found.toLocaleString();
        largeFiles.parentElement.classList.add('updated');
        setTimeout(() => largeFiles.parentElement.classList.remove('updated'), 500);
    }
    if (data.errors !== undefined) {
        const errors = document.getElementById('errors-count');
        errors.textContent = data.errors.toLocaleString();
        if (data.errors > 0) {
            errors.parentElement.classList.add('updated');
            setTimeout(() => errors.parentElement.classList.remove('updated'), 500);
        }
    }
    
    // Update phase indicator
    if (data.phase) {
        updateAnalysisPhase(data.phase);
    }
    
    if (data.current_file) {
        // Update current path display with the file being scanned
        const currentPathText = document.getElementById('current-path-text');
        const pathDisplay = data.current_file;
        
        // Truncate long paths
        if (pathDisplay.length > 60) {
            currentPathText.textContent = '...' + pathDisplay.substring(pathDisplay.length - 57);
        } else {
            currentPathText.textContent = pathDisplay;
        }
        
        // Add to progress log
        addProgressMessage(data.current_file, true);
    }
    
    // Update progress bar only if percent is provided and it's not going backwards
    if (data.percent !== undefined && data.percent !== null) {
        const percent = Math.round(data.percent);
        // Only update if percentage is increasing or it's a phase update
        if (percent >= lastProgressPercent || data.is_phase_update) {
            lastProgressPercent = percent;
            document.getElementById('progress-percent').textContent = `${percent}%`;
            
            // Update SVG arc
            const arc = document.getElementById('progress-arc');
            const circumference = 2 * Math.PI * 90;
            const offset = circumference - (percent / 100) * circumference;
            arc.style.strokeDashoffset = offset;
        }
    }
}

function addProgressMessage(message, subtle = false) {
    const container = document.getElementById('progress-messages');
    const div = document.createElement('div');
    div.className = subtle ? 'progress-message subtle' : 'progress-message';
    div.textContent = message;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    
    // Keep only last 50 messages
    while (container.children.length > 50) {
        container.removeChild(container.firstChild);
    }
}

async function analysisCompleted(data) {
    console.log('Analysis completed, waiting before showing results...');
    
    // Add a small delay to ensure final progress updates are visible
    setTimeout(async () => {
        // Close WebSocket
        if (ws) {
            ws.close();
        }
        
        // Fetch full results
        try {
            const response = await fetch(`${API_BASE}/analysis/${currentSession}/results`);
            analysisResults = await response.json();
            
            // Show results view
            showView('results-view');
            displayResults();
            
        } catch (error) {
            console.error('Failed to fetch results:', error);
        }
    }, 1000); // 1 second delay to show final progress
}

function analysisError(data) {
    alert(`Analysis failed: ${data.error}`);
    showView('home-view');
}

// Display Results
function displayResults() {
    if (!analysisResults || !analysisResults.results) return;
    
    // Calculate totals
    let totalSize = 0;
    let totalFiles = 0;
    let totalLargeFiles = 0;
    let recoverableSpace = 0;
    let dockerSpace = 0;
    let dockerReclaimable = 0;
    
    analysisResults.results.forEach(result => {
        totalSize += result.summary.total_size;
        totalFiles += result.summary.files_scanned;
        totalLargeFiles += result.summary.large_files;
        recoverableSpace += result.summary.recoverable;
        
        // Check for Docker data
        if (result.report && result.report.docker && result.report.docker.available) {
            dockerSpace += result.report.docker.total_size;
            dockerReclaimable += result.report.docker.reclaimable;
        }
    });
    
    // Update summary cards
    document.getElementById('total-size').textContent = formatSize(totalSize);
    document.getElementById('total-files').textContent = totalFiles.toLocaleString();
    document.getElementById('total-large-files').textContent = totalLargeFiles.toLocaleString();
    document.getElementById('recoverable-space').textContent = formatSize(recoverableSpace);
    
    // Create charts
    createFileTypeChart();
    createDirectoryChart();
    
    // Populate files list
    displayLargeFiles();
    
    // Display recommendations
    displayRecommendations();
    
    // Display Docker info if available
    if (dockerSpace > 0) {
        displayDockerInfo(dockerSpace, dockerReclaimable);
    }
}

// Chart instances storage
let chartInstances = {
    fileTypeChart: null,
    directoryChart: null
};

// Charts
function createFileTypeChart() {
    const ctx = document.getElementById('file-type-chart').getContext('2d');
    
    // Destroy existing chart if it exists
    if (chartInstances.fileTypeChart) {
        chartInstances.fileTypeChart.destroy();
        chartInstances.fileTypeChart = null;
    }
    
    // Aggregate file types
    const fileTypes = {};
    analysisResults.results.forEach(result => {
        result.report.file_types.forEach(([ext, data]) => {
            if (!fileTypes[ext]) {
                fileTypes[ext] = 0;
            }
            fileTypes[ext] += data.size;
        });
    });
    
    // Get top 10
    const sorted = Object.entries(fileTypes)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10);
    
    chartInstances.fileTypeChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: sorted.map(([ext, _]) => ext || 'No Extension'),
            datasets: [{
                data: sorted.map(([_, size]) => size),
                backgroundColor: [
                    '#3498db', '#2ecc71', '#f39c12', '#e74c3c', '#9b59b6',
                    '#1abc9c', '#34495e', '#f1c40f', '#e67e22', '#95a5a6'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: 2,
            plugins: {
                legend: {
                    position: 'right'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = formatSize(context.raw);
                            return `${label}: ${value}`;
                        }
                    }
                }
            }
        }
    });
}

function createDirectoryChart() {
    const ctx = document.getElementById('directory-chart').getContext('2d');
    
    // Destroy existing chart if it exists
    if (chartInstances.directoryChart) {
        chartInstances.directoryChart.destroy();
        chartInstances.directoryChart = null;
    }
    
    // Get top directories
    const dirs = [];
    analysisResults.results.forEach(result => {
        result.report.top_directories.slice(0, 5).forEach(([path, size]) => {
            dirs.push({ path: path.split('/').pop() || path, size });
        });
    });
    
    // Sort and get top 10
    dirs.sort((a, b) => b.size - a.size);
    const topDirs = dirs.slice(0, 10);
    
    chartInstances.directoryChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: topDirs.map(d => d.path),
            datasets: [{
                label: 'Size',
                data: topDirs.map(d => d.size),
                backgroundColor: '#3498db'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: 2,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return formatSize(value);
                        }
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return formatSize(context.raw);
                        }
                    }
                }
            }
        }
    });
}

// Display Large Files
function displayLargeFiles() {
    // Aggregate all large files
    allLargeFiles = [];
    analysisResults.results.forEach(result => {
        result.report.large_files.forEach(file => {
            allLargeFiles.push(file);
        });
    });

    // Apply current sort (default: size descending)
    sortLargeFiles();

    // Reset search field
    const searchInput = document.getElementById('file-search');
    if (searchInput) searchInput.value = '';

    renderFilteredFiles();
}

function sortLargeFiles() {
    const sortSelect = document.getElementById('file-sort');
    const sortBy = sortSelect ? sortSelect.value : 'size';

    if (sortBy === 'size') {
        allLargeFiles.sort((a, b) => b.size - a.size);
    } else if (sortBy === 'name') {
        allLargeFiles.sort((a, b) => {
            const nameA = (a.path || '').toLowerCase();
            const nameB = (b.path || '').toLowerCase();
            return nameA.localeCompare(nameB);
        });
    } else if (sortBy === 'age') {
        allLargeFiles.sort((a, b) => {
            const ageA = a.age_days >= 0 ? a.age_days : -1;
            const ageB = b.age_days >= 0 ? b.age_days : -1;
            return ageB - ageA;
        });
    }
}

function renderFilteredFiles() {
    const filesList = document.getElementById('files-list');
    const searchInput = document.getElementById('file-search');
    const query = (searchInput ? searchInput.value : '').toLowerCase().trim();

    let filtered = allLargeFiles;
    if (query) {
        filtered = allLargeFiles.filter(file => {
            const filePath = (file.path || '').toLowerCase();
            const fileName = filePath.split('/').pop();
            return filePath.includes(query) || fileName.includes(query);
        });
    }

    // Display top 100
    filesList.innerHTML = filtered.slice(0, 100).map(file => `
        <div class="file-item">
            <div class="file-info">
                <div class="file-path">${file.path}</div>
                <div class="file-meta">
                    ${file.extension || 'No extension'} •
                    ${file.age_days >= 0 ? `${file.age_days} days old` : 'Unknown age'}
                    ${file.is_cache ? ' • Cache file' : ''}
                </div>
            </div>
            <div class="file-actions">
                <span class="file-size">${formatSize(file.size)}</span>
                ${file.is_protected
                    ? '<span class="badge badge-danger" title="System file - cannot delete">🔒</span>'
                    : `<button class="btn btn-sm btn-danger" onclick="deleteFile('${file.path.replace(/'/g, "\\'")}', ${file.size})" title="Delete file">
                        <i class="fas fa-trash"></i>
                    </button>`
                }
            </div>
        </div>
    `).join('');
}

// Display Recommendations
function displayRecommendations() {
    const recList = document.getElementById('recommendations-list');

    // Aggregate recommendations
    const allRecs = [];
    analysisResults.results.forEach(result => {
        result.report.recommendations.forEach(rec => {
            allRecs.push(rec);
        });
    });

    // Sort by tier then size
    allRecs.sort((a, b) => (a.tier || 9) - (b.tier || 9) || b.space - a.space);

    const tierMeta = {
        1: { icon: '🟢', name: 'Seguro', desc: 'Sin riesgo, se regenera automáticamente', color: 'var(--success)' },
        2: { icon: '🟡', name: 'Moderado', desc: 'Revisar antes de ejecutar', color: 'var(--warning)' },
        3: { icon: '🟠', name: 'Agresivo', desc: 'Puede requerir re-descargas', color: '#f97316' },
        4: { icon: '🔴', name: 'Máximo', desc: 'Requiere decisiones del usuario', color: 'var(--danger)' }
    };

    // Group by tier
    const tiers = {};
    allRecs.forEach(rec => {
        const t = rec.tier || 9;
        if (!tiers[t]) tiers[t] = [];
        tiers[t].push(rec);
    });

    let cumulative = 0;
    let html = '';
    Object.keys(tiers).sort().forEach(tierNum => {
        const recs = tiers[tierNum];
        const info = tierMeta[tierNum] || { icon: '⚪', name: `Nivel ${tierNum}`, desc: '', color: 'var(--gray)' };
        const tierTotal = recs.reduce((sum, r) => sum + r.space, 0);
        cumulative += tierTotal;

        html += `
        <div style="margin-bottom: 1rem; border: 1px solid var(--border); border-radius: 12px; overflow: hidden;">
            <div style="padding: 0.75rem 1rem; background: var(--bg-secondary); border-bottom: 1px solid var(--border);
                        display: flex; justify-content: space-between; align-items: center; cursor: pointer;"
                 onclick="this.parentElement.querySelector('.tier-body').style.display = this.parentElement.querySelector('.tier-body').style.display === 'none' ? 'block' : 'none'">
                <div>
                    <span style="font-size: 1.1rem;">${info.icon}</span>
                    <strong style="margin-left: 0.5rem;">Nivel ${tierNum}: ${info.name}</strong>
                    <span style="color: var(--text-secondary); margin-left: 0.5rem; font-size: 0.85rem;">— ${info.desc}</span>
                </div>
                <div style="text-align: right;">
                    <span style="font-weight: 700; color: ${info.color}; font-size: 1.05rem;">${formatSize(tierTotal)}</span>
                    <div style="font-size: 0.7rem; color: var(--text-secondary);">Acumulado: ${formatSize(cumulative)}</div>
                </div>
            </div>
            <div class="tier-body" style="padding: 0.75rem 1rem;">
                ${recs.map(rec => `
                    <div class="recommendation-item" style="border-bottom: 1px solid var(--border); padding: 0.5rem 0;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div class="recommendation-type">${rec.type}</div>
                                <div class="recommendation-description">${rec.description}</div>
                            </div>
                            <span class="recommendation-space">${formatSize(rec.space)}</span>
                        </div>
                        ${rec.command && !rec.command.startsWith('#') ? `
                            <div style="margin-top: 0.5rem; background: var(--bg-tertiary, #1e293b); color: #e2e8f0;
                                        padding: 0.5rem 0.75rem; border-radius: 6px; font-family: monospace; font-size: 0.8rem;
                                        cursor: pointer;" onclick="navigator.clipboard.writeText(this.textContent.trim())" title="Click to copy">
                                ${rec.command}
                            </div>` : ''}
                    </div>
                `).join('')}
            </div>
        </div>`;
    });

    recList.innerHTML = html || '<p style="text-align: center; color: var(--text-secondary);">No hay recomendaciones disponibles</p>';
}

// Tab Management
function showTab(tabName, evt) {
    // Update buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    // Use the event if provided; otherwise find the button whose onclick matches
    if (evt && evt.currentTarget) {
        evt.currentTarget.classList.add('active');
    } else {
        // Fallback: mark the button whose tab matches
        document.querySelectorAll('.tab-button').forEach(btn => {
            if (btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(`'${tabName}'`)) {
                btn.classList.add('active');
            }
        });
    }

    // Update content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.style.display = 'none';
    });
    document.getElementById(`${tabName}-tab`).style.display = 'block';
}

// Export Results
async function exportResults(format) {
    if (!currentSession) return;
    
    try {
        const response = await fetch(`${API_BASE}/export/${currentSession}/${format}`);
        const blob = await response.blob();
        
        // Create download link
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `disk_analysis_${currentSession}.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
    } catch (error) {
        console.error('Export failed:', error);
    }
}

// Utility Functions
function formatSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function saveSession(sessionId, paths) {
    const sessions = JSON.parse(localStorage.getItem('analysis_sessions') || '[]');
    sessions.unshift({
        id: sessionId,
        date: new Date().toISOString(),
        paths: paths
    });
    
    // Keep only last 10 sessions
    localStorage.setItem('analysis_sessions', JSON.stringify(sessions.slice(0, 10)));
}

// Cleanup Modal Functions
let currentCleanupCommand = null;

function previewCleanup(command) {
    currentCleanupCommand = command;
    
    // Show loading state
    document.getElementById('cleanup-details').innerHTML = '<p>Loading cleanup preview...</p>';
    document.getElementById('cleanup-modal').style.display = 'flex';
    
    // For now, show the command details
    // TODO: Make API call to get actual files that would be affected
    const details = `
        <div class="cleanup-preview">
            <h3>Command to Execute:</h3>
            <pre>${command}</pre>
            
            <div class="warning-box">
                <i class="fas fa-exclamation-triangle"></i>
                <p>This action will permanently delete files. Make sure you have backups if needed.</p>
            </div>
            
            <p class="mt-2">This cleanup operation will help recover disk space by removing temporary and cache files.</p>
        </div>
    `;
    
    document.getElementById('cleanup-details').innerHTML = details;
}

function closeCleanupModal() {
    document.getElementById('cleanup-modal').style.display = 'none';
    currentCleanupCommand = null;
}

function executeCleanup() {
    if (!currentCleanupCommand) return;
    
    // TODO: Implement actual cleanup execution via API
    alert('Cleanup execution not yet implemented. Command: ' + currentCleanupCommand);
    closeCleanupModal();
}

// File Deletion Functions
let fileToDelete = null;
let fileSize = 0;

function deleteFile(filePath, size) {
    fileToDelete = filePath;
    fileSize = size;
    
    document.querySelector('.file-to-delete').textContent = filePath;
    document.getElementById('delete-modal').style.display = 'flex';
}

function closeDeleteModal() {
    document.getElementById('delete-modal').style.display = 'none';
    fileToDelete = null;
    fileSize = 0;
}

async function confirmDelete() {
    if (!fileToDelete) return;
    
    try {
        const response = await fetch('/api/files/delete', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ path: fileToDelete })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Show success message
            alert(`File deleted successfully. Freed ${formatSize(data.size)} of space.`);
            
            // Remove the file from the display without reloading
            const fileElements = document.querySelectorAll('.file-item');
            fileElements.forEach(element => {
                if (element.querySelector('.file-path').textContent === fileToDelete) {
                    element.remove();
                }
            });
            
            // Update recoverable space if visible
            const recoverableElement = document.getElementById('recoverable-space');
            if (recoverableElement && fileSize) {
                const currentText = recoverableElement.textContent;
                // This is a simplified update - in production, you'd recalculate properly
                recoverableElement.parentElement.classList.add('updated');
                setTimeout(() => recoverableElement.parentElement.classList.remove('updated'), 1000);
            }
        } else {
            // Show specific error message
            alert(data.detail || 'Failed to delete file.');
        }
    } catch (error) {
        console.error('Delete error:', error);
        alert('Error deleting file: ' + error.message);
    }
    
    closeDeleteModal();
}

// Click outside modal to close
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        if (event.target.id === 'cleanup-modal') {
            closeCleanupModal();
        } else if (event.target.id === 'delete-modal') {
            closeDeleteModal();
        }
    }
}

function cancelAnalysis() {
    if (ws) {
        ws.close();
    }
    showView('home-view');
}

// Update analysis phase display
function updateAnalysisPhase(phase) {
    const phaseInfo = {
        'disk_scan': {
            icon: 'fa-folder-open',
            text: 'Scanning files and directories',
            color: '#3498db'
        },
        'cache_scan': {
            icon: 'fa-database',
            text: 'Searching cache locations',
            color: '#f39c12'
        },
        'docker_analysis': {
            icon: 'fab fa-docker',
            text: 'Analyzing Docker resources',
            color: '#0db7ed'
        },
        'completed': {
            icon: 'fa-check-circle',
            text: 'Analysis complete!',
            color: '#2ecc71'
        }
    };
    
    const info = phaseInfo[phase] || phaseInfo['disk_scan'];
    
    // Update phase indicator
    let phaseIndicator = document.getElementById('phase-indicator');
    if (!phaseIndicator) {
        // Create phase indicator if it doesn't exist
        const progressContainer = document.querySelector('.progress-container');
        const phaseDiv = document.createElement('div');
        phaseDiv.id = 'phase-indicator';
        phaseDiv.className = 'phase-indicator';
        phaseDiv.innerHTML = `
            <i class="fas ${info.icon}" style="color: ${info.color};"></i>
            <span>${info.text}</span>
        `;
        progressContainer.insertBefore(phaseDiv, progressContainer.querySelector('.current-path-display'));
        phaseIndicator = phaseDiv;
    } else {
        // Update existing indicator
        phaseIndicator.innerHTML = `
            <i class="fas ${info.icon}" style="color: ${info.color};"></i>
            <span>${info.text}</span>
        `;
    }
    
    // Add phase change to progress log
    if (phase !== 'disk_scan') {
        addProgressMessage(`➤ ${info.text}`, false);
    }
}

// Display Docker Information
function displayDockerInfo(totalSize, reclaimable) {
    // Add Docker card to overview if not already present
    const summaryCards = document.querySelector('.summary-cards');
    let dockerCard = document.getElementById('docker-summary-card');
    
    if (!dockerCard) {
        dockerCard = document.createElement('div');
        dockerCard.id = 'docker-summary-card';
        dockerCard.className = 'summary-card';
        dockerCard.innerHTML = `
            <i class="fab fa-docker" style="color: #0db7ed;"></i>
            <h4>Docker Usage</h4>
            <p id="docker-size">-</p>
        `;
        summaryCards.appendChild(dockerCard);
    }
    
    document.getElementById('docker-size').textContent = formatSize(totalSize);
    
    // Add Docker section to overview tab if significant
    if (totalSize > 100 * 1024 * 1024) { // More than 100MB
        const overviewTab = document.getElementById('overview-tab');
        let dockerSection = document.getElementById('docker-section');
        
        if (!dockerSection) {
            dockerSection = document.createElement('div');
            dockerSection.id = 'docker-section';
            dockerSection.className = 'docker-section mt-3';
            dockerSection.innerHTML = `
                <h3><i class="fab fa-docker"></i> Docker Resources</h3>
                <div class="docker-details">
                    <p>Docker is using <strong>${formatSize(totalSize)}</strong> of disk space.</p>
                    <p>You can reclaim <strong>${formatSize(reclaimable)}</strong> by cleaning unused resources.</p>
                    <button class="btn btn-secondary" onclick="previewCleanup('docker system prune -a --volumes -f')">
                        <i class="fas fa-broom"></i> Clean Docker Resources
                    </button>
                </div>
            `;
            overviewTab.appendChild(dockerSection);
        } else {
            // Update existing section
            dockerSection.querySelector('.docker-details').innerHTML = `
                <p>Docker is using <strong>${formatSize(totalSize)}</strong> of disk space.</p>
                <p>You can reclaim <strong>${formatSize(reclaimable)}</strong> by cleaning unused resources.</p>
                <button class="btn btn-secondary" onclick="previewCleanup('docker system prune -a --volumes -f')">
                    <i class="fas fa-broom"></i> Clean Docker Resources
                </button>
            `;
        }
    }
}