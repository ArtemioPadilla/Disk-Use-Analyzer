"""Detect user persona from disk contents and generate adaptive recommendations."""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


PERSONA_DEFINITIONS = {
    "developer": {
        "name": "Developer",
        "icon": "👨‍💻",
        "description": "Code, build tools, and development environments",
        "indicators": {
            "apps": ["Xcode", "Docker", "Visual Studio Code", "IntelliJ", "PyCharm", "iTerm"],
            "paths": ["/node_modules/", "/.npm/", "/.cargo/", "/.rustup/", "/Developer/",
                      "/.gradle/", "/.m2/", "/venv/", "/.venv/", "/.pyenv/", "/go/pkg/"],
            "extensions": [".py", ".js", ".ts", ".rs", ".go", ".java", ".swift"],
        },
    },
    "gamer": {
        "name": "Gamer",
        "icon": "🎮",
        "description": "Games, saves, mods, and recordings",
        "indicators": {
            "apps": ["Steam", "Epic Games Launcher", "GOG Galaxy", "Battle.net", "Minecraft"],
            "paths": ["/Steam/steamapps/", "/Epic Games/", "/GOG Galaxy/", "/Battle.net/",
                      "/minecraft/", "/Application Support/Steam/"],
            "extensions": [".sav", ".replay"],
        },
    },
    "creative_video": {
        "name": "Video/Photo Creator",
        "icon": "🎬",
        "description": "Video editing, photography, and visual production",
        "indicators": {
            "apps": ["Final Cut Pro", "Adobe Premiere Pro", "DaVinci Resolve", "Lightroom",
                     "Photoshop", "After Effects", "Capture One"],
            "paths": ["/Final Cut/", "/Premiere Pro/", "/DaVinci Resolve/", "/Lightroom/",
                      "/Photos Library.photoslibrary", "/Render Files/", "/DCIM/"],
            "extensions": [".mov", ".mp4", ".avi", ".mkv", ".raw", ".cr2", ".nef", ".arw",
                          ".prproj", ".fcpbundle", ".drp", ".psd"],
        },
    },
    "music_producer": {
        "name": "Music Producer",
        "icon": "🎵",
        "description": "Music creation, samples, and audio plugins",
        "indicators": {
            "apps": ["Logic Pro", "Ableton Live", "Pro Tools", "FL Studio", "GarageBand"],
            "paths": ["/Audio Music Apps/", "/Native Instruments/", "/Splice/", "/Kontakt/",
                      "/Ableton/", "/Logic/", "/GarageBand/"],
            "extensions": [".wav", ".aif", ".flac", ".als", ".logicx", ".ptx", ".nki"],
        },
    },
    "designer": {
        "name": "Designer",
        "icon": "🎨",
        "description": "Design files, fonts, and creative assets",
        "indicators": {
            "apps": ["Figma", "Sketch", "Adobe Illustrator", "Adobe XD", "Canva", "Affinity Designer"],
            "paths": ["/Sketch/", "/Figma/", "/Adobe Illustrator/", "/Fonts/"],
            "extensions": [".sketch", ".fig", ".ai", ".eps", ".svg", ".xd"],
        },
    },
    "data_scientist": {
        "name": "Data / ML Engineer",
        "icon": "🧠",
        "description": "Models, datasets, and computation environments",
        "indicators": {
            "apps": ["Jupyter Notebook", "Anaconda-Navigator", "RStudio"],
            "paths": ["/.cache/huggingface/", "/anaconda3/", "/miniconda3/", "/.conda/",
                      "/models/", "/datasets/", "/.jupyter/", "/torch/"],
            "extensions": [".ipynb", ".h5", ".pkl", ".onnx", ".safetensors", ".parquet"],
        },
    },
    "student": {
        "name": "Student",
        "icon": "📚",
        "description": "Course materials, notes, and study resources",
        "indicators": {
            "apps": ["Notion", "Obsidian", "Zoom", "Microsoft Word", "Pages", "Notability"],
            "paths": ["/Zoom/", "/zoom/", "/Recordings/", "/Lecture/", "/Course/",
                      "/Assignment/", "/Homework/", "/Semester/"],
            "extensions": [".docx", ".pptx", ".xlsx", ".pages", ".key", ".numbers"],
        },
    },
    "writer": {
        "name": "Writer",
        "icon": "✍️",
        "description": "Documents, manuscripts, and research",
        "indicators": {
            "apps": ["Scrivener", "Ulysses", "iA Writer", "Bear", "Microsoft Word"],
            "paths": ["/Scrivener/", "/Ulysses/", "/Manuscripts/", "/Writing/"],
            "extensions": [".scriv", ".docx", ".md", ".rtf", ".tex"],
        },
    },
    "casual": {
        "name": "Casual User",
        "icon": "🏠",
        "description": "Photos, downloads, documents, and everyday files",
        "indicators": {
            "apps": [],
            "paths": ["/Photos Library", "/Downloads/", "/Movies/", "/Music/iTunes/"],
            "extensions": [".jpg", ".jpeg", ".png", ".heic", ".pdf"],
        },
    },
}


def detect_personas(large_files: list, top_directories: list, cache_locations: list) -> Dict:
    """Analyze disk contents and detect user personas with confidence scores."""
    scores: Dict[str, float] = {pid: 0.0 for pid in PERSONA_DEFINITIONS}

    # Collect all paths
    all_paths = []
    all_extensions = []

    for f in large_files:
        path = f.get("path", "") if isinstance(f, dict) else str(f)
        all_paths.append(path.lower())
        ext = Path(path).suffix.lower()
        if ext:
            all_extensions.append(ext)

    for d in top_directories:
        path = d[0] if isinstance(d, (list, tuple)) else str(d)
        all_paths.append(path.lower())

    for c in cache_locations:
        path = c.get("path", "") if isinstance(c, dict) else str(c)
        all_paths.append(path.lower())

    # Check installed apps
    apps_dir = Path("/Applications")
    installed_apps = set()
    if apps_dir.exists():
        try:
            installed_apps = {p.stem for p in apps_dir.iterdir() if p.suffix == ".app"}
        except PermissionError:
            pass

    # Score each persona
    for persona_id, defn in PERSONA_DEFINITIONS.items():
        indicators = defn["indicators"]

        # App matches (strong signal)
        for app in indicators["apps"]:
            if app in installed_apps:
                scores[persona_id] += 3.0

        # Path pattern matches
        for pattern in indicators["paths"]:
            matches = sum(1 for p in all_paths if pattern.lower() in p)
            scores[persona_id] += min(matches * 0.5, 5.0)  # Cap at 5

        # Extension matches
        for ext in indicators["extensions"]:
            matches = sum(1 for e in all_extensions if e == ext)
            scores[persona_id] += min(matches * 0.2, 3.0)  # Cap at 3

    # Normalize to percentages
    total = sum(scores.values()) or 1
    profiles = []
    for persona_id, score in sorted(scores.items(), key=lambda x: -x[1]):
        if score > 0:
            defn = PERSONA_DEFINITIONS[persona_id]
            profiles.append({
                "id": persona_id,
                "name": defn["name"],
                "icon": defn["icon"],
                "description": defn["description"],
                "score": round(score, 1),
                "confidence": round((score / total) * 100, 1),
            })

    primary = profiles[0] if profiles else {"id": "casual", "name": "Casual User", "icon": "🏠", "confidence": 100}

    return {
        "primary": primary,
        "all_profiles": profiles[:5],  # Top 5
    }


def generate_persona_recommendations(persona_id: str, large_files: list,
                                       top_directories: list, cache_locations: list) -> List[Dict]:
    """Generate persona-specific cleanup recommendations."""
    recs = []

    if persona_id == "developer":
        # Find node_modules
        nm_dirs = [(f["path"], f["size"]) for f in large_files
                   if isinstance(f, dict) and "node_modules" in f.get("path", "")]
        if nm_dirs:
            total = sum(s for _, s in nm_dirs)
            recs.append({
                "title": "Node.js Dependencies",
                "description": f"{len(nm_dirs)} node_modules directories found",
                "space": total,
                "confidence": 95,
                "action": "Clean inactive project dependencies (reinstall with npm install)",
                "commands": ["find ~ -name 'node_modules' -type d -maxdepth 5 -exec rm -rf {} +"],
                "persona": "developer",
            })

        # Docker
        docker_files = [f for f in large_files if isinstance(f, dict) and "docker" in f.get("path", "").lower()]
        if docker_files:
            total = sum(f.get("size", 0) for f in docker_files)
            recs.append({
                "title": "Docker Resources",
                "description": "Unused images, containers, and build cache",
                "space": total,
                "confidence": 85,
                "action": "Prune unused Docker resources",
                "commands": ["docker system prune -af --volumes"],
                "persona": "developer",
            })

        # Xcode
        xcode_paths = [f for f in large_files if isinstance(f, dict) and
                       any(x in f.get("path", "").lower() for x in ["deriveddata", "coresimulator", "xcode"])]
        if xcode_paths:
            total = sum(f.get("size", 0) for f in xcode_paths)
            recs.append({
                "title": "Xcode Build Data",
                "description": "Derived data, simulator caches, and device support",
                "space": total,
                "confidence": 90,
                "action": "Clean Xcode build artifacts",
                "commands": [
                    "rm -rf ~/Library/Developer/Xcode/DerivedData/*",
                    "xcrun simctl delete unavailable",
                ],
                "persona": "developer",
            })

    elif persona_id == "gamer":
        # Find game directories
        game_patterns = ["steam", "epic games", "gog", "battle.net", "minecraft"]
        game_files = [f for f in large_files if isinstance(f, dict) and
                      any(p in f.get("path", "").lower() for p in game_patterns)]
        if game_files:
            total = sum(f.get("size", 0) for f in game_files)
            recs.append({
                "title": "Game Files",
                "description": f"Games and related data ({len(game_files)} items)",
                "space": total,
                "confidence": 70,
                "action": "Review installed games — uninstall ones you no longer play",
                "commands": [],
                "persona": "gamer",
            })

        # Screenshots/recordings
        recording_exts = {".mov", ".mp4", ".avi", ".mkv", ".png", ".jpg"}
        recordings = [f for f in large_files if isinstance(f, dict) and
                      Path(f.get("path", "")).suffix.lower() in recording_exts and
                      any(x in f.get("path", "").lower() for x in ["screenshot", "recording", "capture", "replay"])]
        if recordings:
            total = sum(f.get("size", 0) for f in recordings)
            recs.append({
                "title": "Game Recordings & Screenshots",
                "description": f"{len(recordings)} capture files",
                "space": total,
                "confidence": 80,
                "action": "Review and delete old game captures",
                "commands": [],
                "persona": "gamer",
            })

    elif persona_id == "creative_video":
        # Render caches
        render_patterns = ["render files", "render cache", "media cache", "peak files", "cache-audio", "cache-video"]
        render_files = [f for f in large_files if isinstance(f, dict) and
                        any(p in f.get("path", "").lower() for p in render_patterns)]
        if render_files:
            total = sum(f.get("size", 0) for f in render_files)
            recs.append({
                "title": "Render & Media Caches",
                "description": "Video editing render files and media caches (rebuild automatically)",
                "space": total,
                "confidence": 95,
                "action": "Clean render caches — they rebuild when you open the project",
                "commands": [
                    "rm -rf ~/Movies/*/Render\\ Files/*",
                    "rm -rf ~/Library/Caches/com.apple.FinalCut*",
                ],
                "persona": "creative_video",
            })

        # Large video files
        video_exts = {".mov", ".mp4", ".avi", ".mkv", ".mxf", ".r3d"}
        videos = [f for f in large_files if isinstance(f, dict) and
                  Path(f.get("path", "")).suffix.lower() in video_exts]
        if videos:
            total = sum(f.get("size", 0) for f in videos)
            recs.append({
                "title": "Video Files",
                "description": f"{len(videos)} video files across your projects",
                "space": total,
                "confidence": 50,
                "action": "Review old video projects — archive completed ones to external storage",
                "commands": [],
                "persona": "creative_video",
            })

    elif persona_id == "music_producer":
        # Sample libraries
        sample_patterns = ["kontakt", "native instruments", "splice", "samples", "sound library", "audio music apps"]
        samples = [f for f in large_files if isinstance(f, dict) and
                   any(p in f.get("path", "").lower() for p in sample_patterns)]
        if samples:
            total = sum(f.get("size", 0) for f in samples)
            recs.append({
                "title": "Sample Libraries",
                "description": f"Audio sample libraries and instruments",
                "space": total,
                "confidence": 60,
                "action": "Review unused sample libraries — move rarely used ones to external drive",
                "commands": [],
                "persona": "music_producer",
            })

    elif persona_id == "data_scientist":
        # Model caches
        model_patterns = ["huggingface", "torch", "tensorflow", ".cache/pip", "models/", ".safetensors", "conda"]
        model_files = [f for f in large_files if isinstance(f, dict) and
                       any(p in f.get("path", "").lower() for p in model_patterns)]
        if model_files:
            total = sum(f.get("size", 0) for f in model_files)
            recs.append({
                "title": "ML Models & Caches",
                "description": "Model weights, datasets, and package caches",
                "space": total,
                "confidence": 85,
                "action": "Clean unused model caches and old environments",
                "commands": [
                    "rm -rf ~/.cache/huggingface/hub/models--*/.no_exist.*",
                    "conda clean --all -y",
                ],
                "persona": "data_scientist",
            })

    elif persona_id == "student":
        # Old downloads (PDFs, docs)
        doc_exts = {".pdf", ".docx", ".pptx", ".xlsx", ".pages", ".key"}
        old_docs = [f for f in large_files if isinstance(f, dict) and
                    Path(f.get("path", "")).suffix.lower() in doc_exts and
                    f.get("age_days", 0) > 180]
        if old_docs:
            total = sum(f.get("size", 0) for f in old_docs)
            recs.append({
                "title": "Old Course Materials",
                "description": f"{len(old_docs)} documents older than 6 months",
                "space": total,
                "confidence": 70,
                "action": "Archive old semester files to external storage or cloud",
                "commands": [],
                "persona": "student",
            })

    # Universal recommendations
    # Duplicate downloads
    downloads_dir = Path.home() / "Downloads"
    if downloads_dir.exists():
        dl_files = [f for f in large_files if isinstance(f, dict) and
                    str(downloads_dir) in f.get("path", "")]
        if dl_files:
            total = sum(f.get("size", 0) for f in dl_files)
            dmgs = [f for f in dl_files if f.get("path", "").endswith((".dmg", ".pkg"))]
            dmg_total = sum(f.get("size", 0) for f in dmgs)
            if dmg_total > 0:
                recs.append({
                    "title": "Installer Files in Downloads",
                    "description": f"{len(dmgs)} .dmg/.pkg files (already installed apps)",
                    "space": dmg_total,
                    "confidence": 95,
                    "action": "Delete installer files — the apps are already installed",
                    "commands": ["find ~/Downloads -name '*.dmg' -o -name '*.pkg' | xargs rm -f"],
                    "persona": "universal",
                })

    # Old large files
    old_large = [f for f in large_files if isinstance(f, dict) and
                 f.get("age_days", 0) > 365 and f.get("size", 0) > 100_000_000]
    if old_large:
        total = sum(f.get("size", 0) for f in old_large)
        recs.append({
            "title": "Files Not Touched in Over a Year",
            "description": f"{len(old_large)} large files (>100 MB) untouched for 12+ months",
            "space": total,
            "confidence": 65,
            "action": "Review these files — archive or delete if no longer needed",
            "commands": [],
            "persona": "universal",
        })

    return sorted(recs, key=lambda r: -r["space"])
