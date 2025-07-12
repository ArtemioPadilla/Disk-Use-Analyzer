# Disk Analyzer Web Interface

A beautiful, modern web-based disk analyzer that works on any platform without GUI dependencies!

## 🚀 Quick Start

```bash
# Install dependencies
make install-web

# Start the web server
make web

# Open your browser to http://localhost:8000
```

That's it! No tkinter issues, no GUI problems - just a beautiful web interface.

## ✨ Features

### 🎨 Modern Web Interface
- **Beautiful Design**: Clean, modern UI with dark/light theme
- **Responsive**: Works on desktop, tablet, and mobile
- **Real-time Updates**: WebSocket-based live progress
- **No Dependencies**: Works in any modern browser

### 📊 Rich Visualizations
- **Interactive Charts**: File type distribution with Chart.js
- **Progress Animations**: Beautiful circular progress indicator
- **Visual Disk Usage**: Drive usage bars and statistics

### 🔄 Real-time Analysis
- **Live Progress**: See files being scanned in real-time
- **WebSocket Updates**: Instant feedback on analysis progress
- **Multi-path Support**: Analyze multiple drives/paths simultaneously

### 💾 Export Options
- **JSON Export**: Full analysis data
- **CSV Export**: Spreadsheet-compatible file lists
- **HTML Reports**: Standalone reports (coming soon)

## 🛠️ Technical Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Vanilla JavaScript (no framework dependencies)
- **Real-time**: WebSockets
- **Charts**: Chart.js
- **Styling**: Modern CSS with CSS Grid/Flexbox

## 📱 Usage Guide

### 1. Start Analysis
- Click "Start Analysis" on the home page
- Select drives or paths to analyze
- Configure options (minimum file size, categories)
- Watch real-time progress

### 2. View Results
- **Overview Tab**: Summary and charts
- **Large Files Tab**: Sortable list of biggest files
- **Recommendations Tab**: Smart cleanup suggestions

### 3. Export Data
- Export as JSON for further processing
- Export as CSV for spreadsheet analysis

## 🔧 API Documentation

The web interface includes a full REST API. View the interactive docs at:
```
http://localhost:8000/docs
```

### Key Endpoints

```bash
# Get system info
GET /api/system/info

# List available drives
GET /api/system/drives

# Start analysis
POST /api/analysis/start
{
  "paths": ["/home/user", "D:\\"],
  "min_size_mb": 10,
  "categories": {
    "cache": true,
    "development": true
  }
}

# Get analysis progress
GET /api/analysis/{session_id}/progress

# Get results
GET /api/analysis/{session_id}/results

# WebSocket for real-time updates
WS /ws/{session_id}
```

## 🌐 Network Access

By default, the server runs on `localhost:8000`. To access from other devices on your network:

1. The launch script shows your network IP
2. Access from any device: `http://YOUR_IP:8000`
3. Works on phones, tablets, other computers

## 🐳 Docker Support (Coming Soon)

```bash
# Build Docker image
docker build -t disk-analyzer-web .

# Run container
docker run -p 8000:8000 disk-analyzer-web
```

## 🎨 Customization

### Theme
- Click the moon/sun icon to toggle dark/light theme
- Theme preference is saved locally

### Analysis Options
- Adjust minimum file size (1MB - 1GB)
- Select specific categories to analyze
- Add custom paths manually

## 🚨 Troubleshooting

### Port already in use
```bash
# Change port in launch_web.sh
uvicorn disk_analyzer_web:app --port 8080
```

### Can't access from network
- Check firewall settings
- Ensure you're using the correct IP
- Try `0.0.0.0` instead of `localhost` in the server

### Slow analysis
- The analysis runs in background threads
- Large directories may take time
- Progress is shown in real-time

## 🎯 Advantages Over GUI Version

1. **No GUI Dependencies**: No tkinter, no system packages needed
2. **Cross-Platform**: Identical experience on all platforms
3. **Remote Access**: Analyze remote systems over network
4. **Better Performance**: Async operations, multiple threads
5. **Modern Interface**: Better than traditional desktop GUIs
6. **Easy Deployment**: Can run on servers, containers, etc.

## 🔒 Security Note

For local use only. If exposing to network:
- Add authentication
- Use HTTPS
- Restrict CORS origins
- Validate file paths

## 📈 Future Enhancements

- [ ] User authentication
- [ ] Scheduled scans
- [ ] Historical comparisons
- [ ] Cloud storage analysis
- [ ] Mobile app
- [ ] Electron desktop app

Enjoy your beautiful, cross-platform disk analyzer! 🎉