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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
import uvicorn

# Import our core analyzer
from disk_analyzer_core import DiskAnalyzerCore, MB, GB, IS_MACOS, IS_WINDOWS
from pty_manager import PTYManager

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
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global storage for analysis sessions
analysis_sessions: Dict[str, Dict] = {}
websocket_connections: Dict[str, List[WebSocket]] = {}
executor = ThreadPoolExecutor(max_workers=4)

# Terminal management
pty_manager = PTYManager(max_sessions=3, idle_timeout=600)

# Session persistence
SESSIONS_FILE = Path("sessions_metadata.json")
RESULTS_DIR = Path.home() / ".disk-analyzer" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
MAX_STORED_RESULTS = 10

def save_session_metadata():
    """Save session metadata to disk"""
    try:
        metadata = []
        for session_id, session in analysis_sessions.items():
            # Only save basic metadata, not results
            metadata.append({
                "id": session_id,
                "status": session["status"],
                "paths": session["paths"],
                "started_at": session["started_at"],
                "completed_at": session.get("completed_at"),
                "error": session.get("error")
            })
        
        with open(SESSIONS_FILE, "w") as f:
            json.dump(metadata, f)
    except Exception as e:
        print(f"Error saving session metadata: {e}")

def load_session_metadata():
    """Load session metadata from disk"""
    try:
        if SESSIONS_FILE.exists():
            with open(SESSIONS_FILE, "r") as f:
                metadata = json.load(f)

            for session_meta in metadata:
                session_id = session_meta["id"]
                # Restore session without results
                analysis_sessions[session_id] = {
                    "id": session_id,
                    "status": session_meta["status"],
                    "progress": 100 if session_meta["status"] == "completed" else 0,
                    "current_path": "",
                    "paths": session_meta["paths"],
                    "started_at": session_meta["started_at"],
                    "completed_at": session_meta.get("completed_at"),
                    "results": None,  # Results loaded on demand
                    "error": session_meta.get("error")
                }
    except Exception as e:
        print(f"Error loading session metadata: {e}")


def save_analysis_results(session_id: str, results: list):
    """Save full analysis results to disk."""
    try:
        result_file = RESULTS_DIR / f"{session_id}.json"
        with open(result_file, 'w') as f:
            json.dump(results, f)
        # Prune old results
        result_files = sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old_file in result_files[MAX_STORED_RESULTS:]:
            old_file.unlink()
    except Exception as e:
        print(f"Warning: Could not save results for {session_id}: {e}")


def load_analysis_results(session_id: str) -> list | None:
    """Load analysis results from disk."""
    try:
        result_file = RESULTS_DIR / f"{session_id}.json"
        if result_file.exists():
            with open(result_file, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load results for {session_id}: {e}")
    return None

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

class TerminalCreateRequest(BaseModel):
    command: Optional[str] = None

class TerminalResizeRequest(BaseModel):
    cols: int
    rows: int

class DeleteFileRequest(BaseModel):
    path: str = Field(..., description="Path of the file to delete")

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

@app.get("/", include_in_schema=False)
async def serve_root():
    """Serve the Astro index or legacy index."""
    astro_index = Path(__file__).parent / "web" / "dist" / "index.html"
    if astro_index.is_file():
        return FileResponse(str(astro_index))
    return FileResponse(str(Path(__file__).parent / "static" / "index.html"))

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
        },
        "default_min_size_mb": getattr(app.state, 'default_min_size_mb', 10),
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
    request: AnalysisRequest
) -> AnalysisResponse:
    """Start a new disk analysis"""
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    
    print(f"Starting analysis session: {session_id}")
    print(f"Paths to analyze: {request.paths}")
    
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
    
    # Save session metadata
    save_session_metadata()
    
    # Start analysis using asyncio.create_task
    task = asyncio.create_task(
        run_analysis(
            session_id,
            request.paths,
            request.min_size_mb,
            request.categories
        )
    )
    
    # Store task reference (optional, for cancellation support)
    analysis_sessions[session_id]["task"] = task
    
    print(f"Analysis task created for session: {session_id}")
    
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
    print(f"run_analysis started for session: {session_id}")
    
    try:
        # Send initial progress update
        await notify_progress(session_id, {
            "type": "progress",
            "session_id": session_id,
            "current_path": "Initializing analysis...",
            "overall_progress": 0,
            "path_index": 0,
            "total_paths": len(paths)
        })
        
        all_results = []
        total_paths = len(paths)
        
        print(f"Starting to analyze {total_paths} paths")
        
        for idx, path in enumerate(paths):
            print(f"Analyzing path {idx + 1}/{total_paths}: {path}")
            
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
            
            # Small delay to ensure WebSocket message is sent
            await asyncio.sleep(0.1)
            
            # Create a queue for progress updates from the sync context
            import queue
            progress_queue = queue.Queue()
            
            # Create analyzer with progress callback that uses the queue
            def progress_callback(info):
                progress_queue.put(info)
            
            analyzer = DiskAnalyzerCore(
                path,
                min_size_mb=min_size_mb,
                progress_callback=progress_callback
            )
            
            # Start a task to process progress updates concurrently
            async def process_progress_updates():
                while True:
                    try:
                        # Process updates in batches
                        batch = []
                        for _ in range(5):  # Process up to 5 updates at a time
                            try:
                                info = progress_queue.get_nowait()
                                batch.append(info)
                            except queue.Empty:
                                break
                        
                        if batch:
                            for info in batch:
                                await notify_progress(session_id, {
                                    "type": "file_progress",
                                    "session_id": session_id,
                                    **info
                                })
                            # Small delay between batches
                            await asyncio.sleep(0.05)
                        else:
                            # No updates, wait a bit
                            await asyncio.sleep(0.1)
                    except Exception as e:
                        print(f"Error processing progress updates: {e}")
                        break
            
            # Start progress update task BEFORE running analysis
            progress_task = asyncio.create_task(process_progress_updates())
            
            # Run analysis in executor
            loop = asyncio.get_event_loop()
            
            # Run the blocking analysis in a thread
            def run_blocking_analysis():
                try:
                    print(f"Starting blocking analysis for: {path}")
                    # Run each phase separately to allow progress updates
                    
                    # Phase 1: Directory scan
                    progress_queue.put({
                        'message': 'Starting directory scan...',
                        'phase': 'disk_scan',
                        'percent': 5,
                        'is_phase_update': True
                    })
                    analyzer.disk_usage = analyzer.get_disk_usage()
                    
                    # Set progress to 10% after disk usage
                    progress_queue.put({
                        'message': 'Scanning directories...',
                        'phase': 'disk_scan',
                        'percent': 10,
                        'is_phase_update': True
                    })
                    
                    total_size = analyzer.scan_directory(analyzer.start_path)
                    analyzer.directory_sizes[str(analyzer.start_path)] = total_size
                    
                    # Phase 2: Cache locations
                    progress_queue.put({
                        'message': 'Searching for cache locations...',
                        'phase': 'cache_scan',
                        'percent': 70,
                        'is_phase_update': True
                    })
                    analyzer.find_cache_locations()
                    
                    # Phase 3: Docker analysis
                    progress_queue.put({
                        'message': 'Analyzing Docker resources...',
                        'phase': 'docker_analysis',
                        'percent': 90,
                        'is_phase_update': True
                    })
                    analyzer.analyze_docker()
                    
                    progress_queue.put({
                        'message': 'Analysis complete!',
                        'phase': 'completed',
                        'percent': 100,
                        'is_phase_update': True
                    })
                    
                    return {
                        'total_size': total_size,
                        'files_scanned': analyzer.total_scanned,
                        'errors': len(analyzer.errors)
                    }
                except Exception as e:
                    print(f"Analysis error for {path}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    return False
            
            print(f"Submitting analysis to executor for: {path}")
            result = await loop.run_in_executor(
                executor,
                run_blocking_analysis
            )
            print(f"Executor returned result for {path}: {result}")
            
            # Cancel progress task AFTER analysis completes
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass
            
            # Process any remaining updates
            while not progress_queue.empty():
                try:
                    info = progress_queue.get_nowait()
                    await notify_progress(session_id, {
                        "type": "file_progress",
                        "session_id": session_id,
                        **info
                    })
                except queue.Empty:
                    break
            
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
                        "recoverable": report["summary"]["recoverable_space"],
                        "docker_space": report["summary"].get("docker_space", 0),
                        "docker_reclaimable": report["summary"].get("docker_reclaimable", 0)
                    }
                })
        
        # Update session with results
        analysis_sessions[session_id]["status"] = "completed"
        analysis_sessions[session_id]["progress"] = 100
        analysis_sessions[session_id]["results"] = all_results
        analysis_sessions[session_id]["completed_at"] = datetime.now().isoformat()

        # Save session metadata and full results to disk
        save_session_metadata()
        save_analysis_results(session_id, all_results)
        
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
        print(f"Analysis error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        analysis_sessions[session_id]["status"] = "error"
        analysis_sessions[session_id]["error"] = str(e)
        
        # Save session metadata
        save_session_metadata()
        
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
    
    # Try loading results from disk if not in memory
    if not session.get("results"):
        session["results"] = load_analysis_results(session_id)
    if not session.get("results"):
        raise HTTPException(
            status_code=410,
            detail="Session results no longer available. Please run a new analysis."
        )
    
    return {
        "id": session_id,
        "status": session["status"],
        "results": session["results"],
        "started_at": session["started_at"],
        "completed_at": session["completed_at"]
    }

@app.get("/api/sessions")
async def get_sessions():
    """Get list of analysis sessions"""
    sessions_list = []
    for session_id, session in analysis_sessions.items():
        sessions_list.append({
            "id": session_id,
            "status": session["status"],
            "paths": session["paths"],
            "started_at": session["started_at"],
            "completed_at": session.get("completed_at"),
            "progress": session["progress"]
        })
    
    # Sort by start time, newest first
    sessions_list.sort(key=lambda x: x["started_at"], reverse=True)
    
    return {"sessions": sessions_list[:20]}  # Return last 20 sessions

@app.get("/api/analysis/latest")
async def get_latest_results():
    """Get the most recent completed analysis results."""
    # Check in-memory first
    completed = [s for s in analysis_sessions.values() if s.get("status") == "completed" and s.get("results")]
    if completed:
        latest = max(completed, key=lambda s: s.get("completed_at", s.get("started_at", "")))
        return {"id": latest["id"], "status": latest["status"], "results": latest["results"]}

    # Try loading from disk
    result_files = sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if result_files:
        sid = result_files[0].stem
        results = load_analysis_results(sid)
        if results:
            return {"id": sid, "status": "completed", "results": results}

    raise HTTPException(status_code=404, detail="No completed analysis found")

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for real-time progress updates"""
    await websocket.accept()
    
    # Add to connection pool
    if session_id not in websocket_connections:
        websocket_connections[session_id] = []
    websocket_connections[session_id].append(websocket)
    
    try:
        # Send initial status (filter out non-serializable fields)
        if session_id in analysis_sessions:
            session_data = analysis_sessions[session_id].copy()
            # Remove non-serializable fields
            session_data.pop('task', None)
            
            await websocket.send_json({
                "type": "status",
                "session": session_data
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
                # Force flush by sending a small keepalive message
                # This helps prevent buffering in some network configurations
                await asyncio.sleep(0.001)  # Tiny delay to ensure message is sent
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
    
    # Safety: always preview first so callers see what would be deleted
    preview = await preview_cleanup(
        CleanupRequest(categories=request.categories, dry_run=True)
    )

    # Perform actual cleanup
    analyzer = DiskAnalyzerCore()
    deleted: list[dict] = []
    errors: list[dict] = []
    freed_size = 0

    for action in preview.get("actions", []):
        target = Path(action["path"])
        try:
            if target.is_file():
                size = target.stat().st_size
                target.unlink()
                deleted.append({"path": str(target), "size": size})
                freed_size += size
            elif target.is_dir():
                import shutil
                size = action.get("size", 0)
                shutil.rmtree(str(target))
                deleted.append({"path": str(target), "size": size})
                freed_size += size
        except Exception as e:
            errors.append({"path": str(target), "error": str(e)})

    return {
        "deleted": deleted,
        "errors": errors,
        "freed_size": freed_size,
        "dry_run": False
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
    elif format == "html":
        # Generate standalone HTML report
        try:
            from disk_analyzer import DiskAnalyzer
            analyzer = DiskAnalyzer(str(Path.home()))
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
    else:
        raise HTTPException(status_code=400, detail="Unsupported format")

@app.delete("/api/files/delete")
async def delete_file(request: DeleteFileRequest):
    """Delete a file from the filesystem"""
    try:
        file_path = Path(request.path)
        
        # Security validations
        # 1. Check if path is absolute
        if not file_path.is_absolute():
            raise HTTPException(status_code=400, detail="Path must be absolute")
        
        # 2. Resolve path to prevent directory traversal
        try:
            resolved_path = file_path.resolve(strict=True)
        except (OSError, RuntimeError):
            raise HTTPException(status_code=404, detail="File not found")
        
        # 3. Check if file exists and is a file (not directory)
        if not resolved_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        if not resolved_path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")
        
        # 4. Prevent deletion of system files using shared protection logic
        from disk_analyzer_core import DiskAnalyzerCore
        checker = DiskAnalyzerCore.__new__(DiskAnalyzerCore)
        path_str = str(resolved_path)
        if checker.is_protected_path(path_str):
            raise HTTPException(
                status_code=403,
                detail="Cannot delete system files"
            )
        
        # Get file size before deletion
        file_size = resolved_path.stat().st_size
        
        # Attempt to delete the file
        try:
            if IS_MACOS:
                # Move to trash on macOS
                import subprocess
                result = subprocess.run(
                    ['osascript', '-e', f'tell application "Finder" to delete POSIX file "{str(resolved_path)}"'],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    # Fallback to permanent deletion
                    resolved_path.unlink()
            elif IS_WINDOWS:
                # Use Windows recycle bin
                import ctypes
                from ctypes import wintypes
                # Move to recycle bin using SHFileOperation
                # For now, just delete permanently
                resolved_path.unlink()
            else:
                # Linux: move to trash if available
                trash_dir = Path.home() / '.local/share/Trash/files'
                if trash_dir.exists():
                    import shutil
                    trash_dest = trash_dir / resolved_path.name
                    # Add timestamp if file exists in trash
                    if trash_dest.exists():
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        trash_dest = trash_dir / f"{resolved_path.stem}_{timestamp}{resolved_path.suffix}"
                    shutil.move(str(resolved_path), str(trash_dest))
                else:
                    # No trash, delete permanently
                    resolved_path.unlink()
            
            return {
                "success": True,
                "message": f"File deleted successfully",
                "path": str(resolved_path),
                "size": file_size
            }
            
        except PermissionError:
            raise HTTPException(
                status_code=403,
                detail="Permission denied. Cannot delete this file."
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete file: {str(e)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )

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
    """Bidirectional WebSocket: stdin from browser -> PTY, stdout from PTY -> browser."""
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


@app.on_event("startup")
async def startup_event():
    """Initialize the application"""
    # Create static directory structure for legacy frontend
    if not static_dir.exists():
        static_dir.mkdir(exist_ok=True)
    for subdir in ["css", "js", "img"]:
        (static_dir / subdir).mkdir(exist_ok=True)

    # Load previous session metadata
    load_session_metadata()

    # Load results for completed sessions
    for sid, session in analysis_sessions.items():
        if session.get("status") == "completed" and not session.get("results"):
            results = load_analysis_results(sid)
            if results:
                session["results"] = results
                print(f"  Loaded cached results for session {sid}")

    print("✅ Web server started successfully")
    if astro_dist.exists():
        print(f"📁 Astro frontend served from: {astro_dist}")
    else:
        print(f"📁 Legacy frontend served from: {static_dir}")
    print(f"🔍 API endpoints available at /api/*")
    print(f"📊 Loaded {len(analysis_sessions)} previous sessions")

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

    # Cleanup PTY sessions
    pty_manager.cleanup_all()

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

@app.get("/{path:path}")
async def serve_astro(path: str):
    """Serve Astro frontend pages. API routes take priority (registered first)."""
    astro_dist = Path(__file__).parent / "web" / "dist"
    if not astro_dist.exists():
        return FileResponse(str(Path(__file__).parent / "static" / "index.html"))

    for candidate in [
        astro_dist / path / "index.html",
        astro_dist / f"{path}.html",
        astro_dist / path,
    ]:
        if candidate.is_file():
            return FileResponse(str(candidate))

    index = astro_dist / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return FileResponse(str(Path(__file__).parent / "static" / "index.html"))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Disk Analyzer Web Server")
    parser.add_argument("--min-size", type=float, default=10,
                        help="Default minimum file size in MB (default: 10, use 0 for all files)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    args = parser.parse_args()

    # Store default min_size so the API can serve it
    app.state.default_min_size_mb = args.min_size

    # Print startup information
    print("\n" + "="*60)
    print("🌐 Disk Analyzer Web Server")
    print("="*60)

    # Get local IP
    local_ip = get_local_ip()
    
    print(f"\n⚙️  Default min file size: {args.min_size} MB")
    print("\n🚀 Server starting...")
    print(f"\n📍 Access the web interface at:")
    print(f"   Local:   http://localhost:{args.port}")
    if local_ip != "localhost":
        print(f"   Network: http://{local_ip}:{args.port}")
    print(f"\n📚 API documentation:")
    print(f"   http://localhost:{args.port}/docs")
    print(f"\nℹ️  Press Ctrl+C to stop the server")
    print("="*60 + "\n")
    
    # Run the server
    uvicorn.run(
        "disk_analyzer_web:app",
        host="0.0.0.0",
        port=args.port,
        reload=True,
        log_level="info",
        # WebSocket settings to reduce buffering
        ws_ping_interval=20,
        ws_ping_timeout=20,
        ws_max_size=16777216  # 16MB
    )