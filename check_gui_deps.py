#!/usr/bin/env python3
"""
Check GUI dependencies for Disk Analyzer
"""

import sys
import subprocess
import importlib.util

def check_package(package_name):
    """Check if a package is installed"""
    spec = importlib.util.find_spec(package_name)
    return spec is not None

def main():
    print("🔍 Checking GUI Dependencies for Disk Analyzer")
    print("=" * 50)
    
    print(f"\nPython Version: {sys.version}")
    print(f"Python Executable: {sys.executable}")
    
    print("\n📦 Required Packages:")
    
    packages = {
        'tkinter': 'Base GUI library (system package)',
        'customtkinter': 'Modern GUI framework',
        'matplotlib': 'Charts and graphs',
        'PIL': 'Image handling (Pillow)'
    }
    
    all_installed = True
    
    for package, description in packages.items():
        installed = check_package(package)
        status = "✅ Installed" if installed else "❌ Not installed"
        print(f"  {package:<15} - {description:<20} {status}")
        if not installed:
            all_installed = False
            
    if not all_installed:
        print("\n❌ Some packages are missing!")
        
        # Check specifically for tkinter
        if not check_package('tkinter'):
            print("\n🔴 IMPORTANT: tkinter is not installed!")
            print("   tkinter is a system package and cannot be installed with pip.")
            print("\n   Install it using your system package manager:")
            print("   - Ubuntu/Debian: sudo apt install python3-tk")
            print("   - Fedora: sudo dnf install python3-tkinter")
            print("   - Arch: sudo pacman -S tk")
            print("   - macOS: brew install python-tk")
            
        print("\n💡 To install pip packages, run:")
        print(f"   {sys.executable} -m pip install -r requirements.txt")
        print("\n   Or if that doesn't work:")
        print(f"   {sys.executable} -m pip install customtkinter matplotlib Pillow")
    else:
        print("\n✅ All dependencies are installed!")
        print("\n🚀 You can run the GUI with:")
        print(f"   {sys.executable} disk_analyzer_gui.py")
        
    # Try to get package versions
    print("\n📋 Installed versions:")
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'list'], 
            capture_output=True, 
            text=True
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if any(pkg in line.lower() for pkg in ['customtkinter', 'matplotlib', 'pillow']):
                    print(f"   {line}")
    except:
        print("   Could not get version information")

if __name__ == "__main__":
    main()