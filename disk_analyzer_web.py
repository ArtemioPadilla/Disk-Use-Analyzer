#!/usr/bin/env python3
"""
Disk Analyzer Web API
FastAPI-based web interface for disk analysis
"""

import os
import sys
import uuid
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
import uvicorn

# Import our core analyzer
from disk_analyzer_core import DiskAnalyzerCore, MB, GB

# Create FastAPI app
app = FastAPI(
    title="Disk Analyzer API",
    description="Web API for cross-platform disk space analysis",
    version="1.0.0"
)

# Enable CORS for web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global storage for analysis sessions
analysis_sessions: Dict[str, Dict] = {}
websocket_connections: Dict[str, List[WebSocket]] = {}
executor = ThreadPoolExecutor(max_workers=4)

# Pydantic models for API
class AnalysisRequest(BaseModel):
    paths: List[str] = Field(..., description="Paths to analyze")
    min_size_mb: float = Field(10, description="Minimum file size in MB")
    categories: Dict[str, bool] = Field(
        default_factory=lambda: {
            "cache": True,
            "development": True,
            "docker": True,
            "media": True,
            "downloads": True,
            "temp": True
        }
    )

class AnalysisResponse(BaseModel):
    id: str
    status: str
    message: str

class CleanupRequest(BaseModel):
    paths: List[str]
    categories: List[str]
    dry_run: bool = True

# Serve static files (frontend)
static_dir = Path(__file__).parent / "static"
if not static_dir.exists():
    static_dir.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
async def root():
    """Serve the main HTML page"""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Disk Analyzer Web API", "docs": "/docs"}

@app.get("/api/system/info")
async def get_system_info():
    """Get system information"""
    import platform
    import shutil
    
    # Get disk usage for root
    if platform.system() == "Windows":
        usage = shutil.disk_usage("C:\\")
    else:
        usage = shutil.disk_usage("/")
    
    return {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "disk_usage": {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": (usage.used / usage.total * 100) if usage.total > 0 else 0
        }
    }

@app.get("/api/system/drives")
async def get_drives():
    """Get available drives/mount points"""
    analyzer = DiskAnalyzerCore(".")
    drives = analyzer.get_all_drives()
    
    # Add common directories
    common_paths = []
    home = Path.home()
    
    for name, path in [
        ("Home", str(home)),
        ("Downloads", str(home / "Downloads")),
        ("Documents", str(home / "Documents")),
        ("Desktop", str(home / "Desktop") if (home / "Desktop").exists() else None),
    ]:
        if path and Path(path).exists():
            common_paths.append({
                "name": name,
                "path": path,
                "type": "directory"
            })
    
    return {
        "drives": drives,
        "common_paths": common_paths,
        "platform": analyzer.system
    }

@app.post("/api/analysis/start")
async def start_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks
) -> AnalysisResponse:
    """Start a new disk analysis"""
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    
    # Initialize session
    analysis_sessions[session_id] = {
        "id": session_id,
        "status": "running",
        "progress": 0,
        "current_path": "",
        "paths": request.paths,
        "started_at": datetime.now().isoformat(),
        "results": None,
        "error": None
    }
    
    # Start analysis in background
    background_tasks.add_task(
        run_analysis,
        session_id,
        request.paths,
        request.min_size_mb,
        request.categories
    )
    
    return AnalysisResponse(
        id=session_id,
        status="started",
        message=f"Analysis started for {len(request.paths)} path(s)"
    )

async def run_analysis(
    session_id: str,
    paths: List[str],
    min_size_mb: float,
    categories: Dict[str, bool]
):
    """Run analysis in background thread"""
    try:
        all_results = []
        total_paths = len(paths)
        
        for idx, path in enumerate(paths):
            # Update session progress
            analysis_sessions[session_id]["current_path"] = path
            analysis_sessions[session_id]["progress"] = (idx / total_paths) * 100
            
            # Notify WebSocket clients
            await notify_progress(session_id, {
                "type": "progress",
                "session_id": session_id,
                "current_path": path,
                "overall_progress": (idx / total_paths) * 100,
                "path_index": idx + 1,
                "total_paths": total_paths
            })
            
            # Create analyzer with progress callback
            def progress_callback(info):
                asyncio.create_task(notify_progress(session_id, {
                    "type": "file_progress",
                    "session_id": session_id,
                    **info
                }))
            
            analyzer = DiskAnalyzerCore(
                path,
                min_size_mb,
                progress_callback=progress_callback
            )
            
            # Run analysis
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            result = await loop.run_in_executor(
                executor,
                analyzer.analyze
            )
            
            if result:
                report = analyzer.generate_report()
                all_results.append({
                    "path": path,
                    "report": report,
                    "summary": {
                        "total_size": report["summary"]["total_size"],
                        "files_scanned": report["summary"]["files_scanned"],
                        "large_files": len(report["large_files"]),
                        "cache_size": report["summary"]["cache_size"],
                        "recoverable": report["summary"]["recoverable_space"]
                    }
                })
        
        # Update session with results
        analysis_sessions[session_id]["status"] = "completed"
        analysis_sessions[session_id]["progress"] = 100
        analysis_sessions[session_id]["results"] = all_results
        analysis_sessions[session_id]["completed_at"] = datetime.now().isoformat()
        
        # Notify completion
        await notify_progress(session_id, {
            "type": "completed",
            "session_id": session_id,
            "results_summary": {
                "paths_analyzed": len(all_results),
                "total_files": sum(r["summary"]["files_scanned"] for r in all_results),
                "total_size": sum(r["summary"]["total_size"] for r in all_results)
            }
        })
        
    except Exception as e:
        analysis_sessions[session_id]["status"] = "error"
        analysis_sessions[session_id]["error"] = str(e)
        
        await notify_progress(session_id, {
            "type": "error",
            "session_id": session_id,
            "error": str(e)
        })

@app.get("/api/analysis/{session_id}/progress")
async def get_analysis_progress(session_id: str):
    """Get analysis progress"""
    if session_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = analysis_sessions[session_id]
    return {
        "id": session_id,
        "status": session["status"],
        "progress": session["progress"],
        "current_path": session["current_path"],
        "started_at": session["started_at"],
        "completed_at": session.get("completed_at")
    }

@app.get("/api/analysis/{session_id}/results")
async def get_analysis_results(session_id: str):
    """Get analysis results"""
    if session_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = analysis_sessions[session_id]
    if session["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analysis not completed")
    
    return {
        "id": session_id,
        "status": session["status"],
        "results": session["results"],
        "started_at": session["started_at"],
        "completed_at": session["completed_at"]
    }

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for real-time progress updates"""
    await websocket.accept()
    
    # Add to connection pool
    if session_id not in websocket_connections:
        websocket_connections[session_id] = []
    websocket_connections[session_id].append(websocket)
    
    try:
        # Send initial status
        if session_id in analysis_sessions:
            await websocket.send_json({
                "type": "status",
                "session": analysis_sessions[session_id]
            })
        
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            # Echo back or handle commands
            if data == "ping":
                await websocket.send_text("pong")
                
    except WebSocketDisconnect:
        # Remove from connection pool
        if session_id in websocket_connections:
            websocket_connections[session_id].remove(websocket)
            if not websocket_connections[session_id]:
                del websocket_connections[session_id]

async def notify_progress(session_id: str, message: Dict):
    """Notify all WebSocket clients about progress"""
    if session_id in websocket_connections:
        disconnected = []
        for websocket in websocket_connections[session_id]:
            try:
                await websocket.send_json(message)
            except:
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for ws in disconnected:
            websocket_connections[session_id].remove(ws)

@app.post("/api/cleanup/preview")
async def preview_cleanup(request: CleanupRequest):
    """Preview cleanup actions"""
    cleanup_actions = []
    total_size = 0
    
    for path in request.paths:
        analyzer = DiskAnalyzerCore(path)
        # Quick scan for cache locations only
        analyzer.find_cache_locations()
        
        for cache_loc in analyzer.cache_locations:
            if cache_loc['type'].lower() in request.categories:
                cleanup_actions.append({
                    "path": cache_loc['path'],
                    "size": cache_loc['size'],
                    "type": cache_loc['type'],
                    "action": "delete"
                })
                total_size += cache_loc['size']
    
    return {
        "actions": cleanup_actions,
        "total_size": total_size,
        "dry_run": request.dry_run
    }

@app.post("/api/cleanup/execute")
async def execute_cleanup(request: CleanupRequest):
    """Execute cleanup actions"""
    if request.dry_run:
        return await preview_cleanup(request)
    
    # In production, implement actual cleanup with safety checks
    return {
        "message": "Cleanup execution not implemented in demo",
        "dry_run": request.dry_run
    }

@app.get("/api/export/{session_id}/{format}")
async def export_results(session_id: str, format: str):
    """Export results in various formats"""
    if session_id not in analysis_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = analysis_sessions[session_id]
    if session["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analysis not completed")
    
    if format == "json":
        return JSONResponse(
            content=session["results"],
            headers={
                "Content-Disposition": f"attachment; filename=disk_analysis_{session_id}.json"
            }
        )
    elif format == "csv":
        # Generate CSV
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Path", "Size", "Type", "Age (days)", "Is Cache"])
        
        for result in session["results"]:
            for file in result["report"]["large_files"][:100]:  # Top 100 files
                writer.writerow([
                    file["path"],
                    file["size"],
                    file["extension"],
                    file["age_days"],
                    file["is_cache"]
                ])
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=disk_analysis_{session_id}.csv"
            }
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported format")

@app.on_event("startup")
async def startup_event():
    """Initialize the application"""
    # Create static directory structure
    for subdir in ["css", "js", "img"]:
        (static_dir / subdir).mkdir(exist_ok=True)
    
    # Create default index.html if it doesn't exist
    index_file = static_dir / "index.html"
    if not index_file.exists():
        # We'll create this in the next step
        pass

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    # Close all WebSocket connections
    for session_id, connections in websocket_connections.items():
        for ws in connections:
            try:
                await ws.close()
            except:
                pass
    
    # Shutdown executor
    executor.shutdown(wait=True)

def get_local_ip():
    """Get local IP address for network access"""
    import socket
    try:
        # Create a socket to determine the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

if __name__ == "__main__":
    # Print startup information
    print("\n" + "="*60)
    print("🌐 Disk Analyzer Web Server")
    print("="*60)
    
    # Get local IP
    local_ip = get_local_ip()
    
    print("\n🚀 Server starting...")
    print(f"\n📍 Access the web interface at:")
    print(f"   Local:   http://localhost:8000")
    if local_ip != "localhost":
        print(f"   Network: http://{local_ip}:8000")
    print(f"\n📚 API documentation:")
    print(f"   http://localhost:8000/docs")
    print(f"\nℹ️  Press Ctrl+C to stop the server")
    print("="*60 + "\n")
    
    # Run the server
    uvicorn.run(
        "disk_analyzer_web:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )