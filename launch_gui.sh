#!/bin/bash
# Launcher script for Disk Analyzer GUI
# Automatically finds the right Python with customtkinter installed

echo "🚀 Launching Disk Analyzer GUI..."

# Try different Python commands
for PYTHON_CMD in python3 python python3.11 python3.10 python3.9 python3.8; do
    if command -v $PYTHON_CMD &> /dev/null; then
        echo "Trying $PYTHON_CMD..."
        if $PYTHON_CMD -c "import customtkinter" 2>/dev/null; then
            echo "✅ Found working Python: $PYTHON_CMD"
            echo "Starting GUI..."
            exec $PYTHON_CMD disk_analyzer_gui.py
            exit 0
        fi
    fi
done

# If we get here, no working Python was found
echo "❌ Error: Could not find Python with customtkinter installed"
echo ""
echo "Please install dependencies first:"
echo "  python3 -m pip install -r requirements.txt"
echo ""
echo "Or run the diagnostic:"
echo "  python3 check_gui_deps.py"
exit 1