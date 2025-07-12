// Disk Analyzer Web App
const API_BASE = '/api';
let currentSession = null;
let selectedPaths = [];
let ws = null;
let analysisResults = null;

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
function checkSavedSessions() {
    const sessions = JSON.parse(localStorage.getItem('analysis_sessions') || '[]');
    if (sessions.length > 0) {
        displayRecentAnalyses(sessions);
    }
}

function displayRecentAnalyses(sessions) {
    const container = document.getElementById('recent-analyses');
    const list = document.getElementById('recent-list');
    
    list.innerHTML = sessions.slice(0, 5).map(session => `
        <div class="recent-item">
            <span>${new Date(session.date).toLocaleDateString()}</span>
            <span>${session.paths.join(', ')}</span>
            <button class="btn btn-sm" onclick="loadSession('${session.id}')">View</button>
        </div>
    `).join('');
    
    container.style.display = 'block';
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
    
    // Move to progress step
    nextStep();
    
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
        connectWebSocket(currentSession);
        
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
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
    };
    
    ws.onmessage = (event) => {
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
    switch (data.type) {
        case 'progress':
            updateOverallProgress(data);
            break;
        case 'file_progress':
            updateFileProgress(data);
            break;
        case 'completed':
            analysisCompleted(data);
            break;
        case 'error':
            analysisError(data);
            break;
    }
}

function updateOverallProgress(data) {
    const percent = Math.round(data.overall_progress);
    document.getElementById('progress-percent').textContent = `${percent}%`;
    
    // Update SVG arc
    const arc = document.getElementById('progress-arc');
    const circumference = 2 * Math.PI * 90;
    const offset = circumference - (percent / 100) * circumference;
    arc.style.strokeDashoffset = offset;
    
    // Update current path
    document.getElementById('current-path').textContent = data.current_path || '-';
    
    // Add progress message
    addProgressMessage(`Analyzing ${data.path_index} of ${data.total_paths}: ${data.current_path}`);
}

function updateFileProgress(data) {
    if (data.files_scanned !== undefined) {
        document.getElementById('files-scanned').textContent = data.files_scanned.toLocaleString();
    }
    if (data.large_files_found !== undefined) {
        document.getElementById('large-files').textContent = data.large_files_found.toLocaleString();
    }
    if (data.errors !== undefined) {
        document.getElementById('errors-count').textContent = data.errors.toLocaleString();
    }
    
    if (data.current_file) {
        addProgressMessage(data.current_file, true);
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
    
    analysisResults.results.forEach(result => {
        totalSize += result.summary.total_size;
        totalFiles += result.summary.files_scanned;
        totalLargeFiles += result.summary.large_files;
        recoverableSpace += result.summary.recoverable;
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
}

// Charts
function createFileTypeChart() {
    const ctx = document.getElementById('file-type-chart').getContext('2d');
    
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
    
    new Chart(ctx, {
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
            maintainAspectRatio: false,
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
    
    new Chart(ctx, {
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
            maintainAspectRatio: false,
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
    const filesList = document.getElementById('files-list');
    
    // Aggregate all large files
    const allFiles = [];
    analysisResults.results.forEach(result => {
        result.report.large_files.forEach(file => {
            allFiles.push(file);
        });
    });
    
    // Sort by size
    allFiles.sort((a, b) => b.size - a.size);
    
    // Display top 100
    filesList.innerHTML = allFiles.slice(0, 100).map(file => `
        <div class="file-item">
            <div class="file-info">
                <div class="file-path">${file.path}</div>
                <div class="file-meta">
                    ${file.extension || 'No extension'} • 
                    ${file.age_days >= 0 ? `${file.age_days} days old` : 'Unknown age'}
                    ${file.is_cache ? ' • Cache file' : ''}
                </div>
            </div>
            <div class="file-size">${formatSize(file.size)}</div>
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
    
    // Sort by space
    allRecs.sort((a, b) => b.space - a.space);
    
    recList.innerHTML = allRecs.map(rec => `
        <div class="recommendation-item">
            <span class="recommendation-priority priority-${rec.priority.toLowerCase()}">${rec.priority}</span>
            <div class="recommendation-info">
                <div class="recommendation-type">${rec.type}</div>
                <div class="recommendation-description">${rec.description}</div>
            </div>
            <span class="recommendation-space">${formatSize(rec.space)}</span>
            <button class="btn btn-secondary" onclick="previewCleanup('${rec.command}')">
                Preview
            </button>
        </div>
    `).join('');
}

// Tab Management
function showTab(tabName) {
    // Update buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
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

function previewCleanup(command) {
    alert(`Cleanup command:\n\n${command}\n\nThis would be executed in the actual implementation.`);
}

function cancelAnalysis() {
    if (ws) {
        ws.close();
    }
    showView('home-view');
}