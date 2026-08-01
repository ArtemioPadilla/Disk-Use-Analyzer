# Disk Analyzer Web Interface

A beautiful, modern web-based disk analyzer that works on any platform without GUI dependencies!

## 🚀 Quick Start

```bash
# Install dependencies
make install-web

# Start the web server
make web
```

The server prints a link with a one-time token, for example:

```
🔑 Auth activada. Abre el enlace con token (no lo compartas):

📍 Accede a la interfaz web en:
   Local:   http://localhost:8000/?token=AbCdEf...
```

Open that exact link (not a bare `http://localhost:8000`). The frontend reads
the token from the URL, stores it in `sessionStorage` for the rest of the
browser session, and strips it from the address bar. A new token is generated
every time you restart the server, so after a restart you need to open the
newly printed link again — a tab left open from a previous run has a stale
token and every `/api/*` call from it will fail with 401.

That's it! No tkinter issues, no GUI problems - just a beautiful web interface.

If you use `make web-dev` instead (Astro dev server with hot-reload), the auth
token is still printed by the FastAPI backend's banner against the `:8000`
URL — you need to copy the `?token=...` part of that link onto the `:3000`
URL you actually open (`http://localhost:3000/?token=...`), since the dev
server doesn't print its own token.

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
# Run the server directly on a different port
python disk_analyzer_web.py --port 8080
```

Don't run this with `uvicorn disk_analyzer_web:app --port 8080` — that skips
the `__main__` block that generates and prints the auth token, so
`DISK_ANALYZER_TOKEN` is never set and every `/api/*` request gets a 401 with
no link that would let you in. If you need to launch through `uvicorn`
directly, set `DISK_ANALYZER_TOKEN` yourself first and build the `?token=`
URL by hand:
```bash
export DISK_ANALYZER_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
uvicorn disk_analyzer_web:app --port 8080
# then open http://localhost:8080/?token=$DISK_ANALYZER_TOKEN
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

Token authentication is **on by default**. Every `/api/*` route requires the
`X-Auth-Token` header, and both WebSockets require a `?token=` query
parameter. The server mints a fresh random token on each start and prints it
embedded in the URL (see Quick Start above); the frontend picks it up from the
URL, keeps it only in `sessionStorage`, and never puts it back in the address
bar.

Background cleanup agents are **simulate-by-default**: `POST
/api/agents/{id}/run` only logs what it would do unless you call it with
`?confirm=true`, and the scheduled/automatic runs never pass `confirm=true` —
they always stay in dry-run. The web UI's "Run now" button shows the exact
commands before asking you to confirm.

Run with `--no-auth` to disable all of this — only do that on a network you
fully trust and control, since it means anyone who can reach the port can read
and delete files and open a terminal on your machine.

Honest caveats — don't assume more than this actually gives you:
- The WebSocket token travels in the query string over plain `ws://` (browsers
  can't attach custom headers to a WebSocket handshake), so it can land in
  proxy or `uvicorn` access logs. This is acceptable for a trusted LAN, not for
  an untrusted or public network.
- The floating terminal's dangerous-command blocklist only checks the initial
  command used to spawn the PTY session; it does not filter what you type
  interactively once the shell is open.
- `/docs` and `/openapi.json` are **not** behind auth — they expose the API
  schema (not your data), but anyone who can reach the port can browse them.
- If you expose the server beyond your LAN, add HTTPS/TLS in front of it (for
  example with a reverse proxy) — this project does not terminate TLS itself.

## 📈 Future Enhancements

- [ ] Scheduled scans
- [ ] Historical comparisons
- [ ] Cloud storage analysis
- [ ] Mobile app
- [ ] Electron desktop app

Enjoy your beautiful, cross-platform disk analyzer! 🎉