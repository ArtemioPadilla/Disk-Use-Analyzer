#!/usr/bin/env python3
"""
Cross-platform launcher for Disk Analyzer Web Interface
Works on Windows, macOS, and Linux without shell script issues
"""

import sys
import subprocess
import platform
import os

def check_and_install_dependencies():
    """Check if FastAPI is installed and install if needed"""
    try:
        import fastapi
        import uvicorn
        return True
    except ImportError:
        print("📦 Installing web dependencies...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "-r", "requirements-web.txt"
            ])
            print("✅ Dependencies installed successfully!")
            return True
        except subprocess.CalledProcessError:
            print("❌ Failed to install dependencies")
            print("Please run manually:")
            print(f"  {sys.executable} -m pip install -r requirements-web.txt")
            return False

def main():
    """Main launcher function"""
    print("🌐 Disk Analyzer Web Interface Launcher")
    print("=" * 50)
    print(f"Platform: {platform.system()}")
    print(f"Python: {sys.version.split()[0]}")
    print("=" * 50)
    
    # Check dependencies
    if not check_and_install_dependencies():
        sys.exit(1)
    
    # Launch the web server
    print("\n🚀 Starting web server...")
    print("\nTip: You can also run directly with:")
    print(f"  {sys.executable} disk_analyzer_web.py\n")
    
    try:
        # Import and run directly
        os.system(f"{sys.executable} disk_analyzer_web.py")
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()