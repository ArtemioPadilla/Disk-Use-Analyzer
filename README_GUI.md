# Disk Analyzer GUI - Beautiful Cross-Platform Wizard

A modern, beautiful GUI wizard for disk space analysis that works on Windows, macOS, and Linux.

## Features

### 🎨 Beautiful Modern Interface
- **Dark/Light Theme Toggle**: Switch between dark and light modes
- **Smooth Animations**: Progress indicators and transitions
- **Platform-Native Look**: Adapts to your operating system's style
- **High-DPI Support**: Crisp graphics on all displays

### 🚀 Wizard-Based Workflow
1. **Welcome Screen**: Choose between Quick Scan (>50MB) or Full Analysis (>10MB)
2. **Drive Selection**: 
   - Windows: Select multiple drives with usage preview
   - macOS/Linux: Choose common locations or browse
3. **Analysis Options**: Configure file size threshold, categories, and export formats
4. **Real-time Progress**: Watch analysis with live updates and statistics
5. **Interactive Dashboard**: Explore results with charts and recommendations

### 📊 Rich Visualizations
- **Pie Charts**: File type distribution
- **Progress Bars**: Drive usage visualization
- **Tabbed Interface**: Overview, Recommendations, and Details
- **Search Functionality**: Find specific files quickly

### 💾 Export Options
- **HTML Reports**: Beautiful standalone reports
- **JSON Data**: For further processing
- **CSV Summaries**: For spreadsheet analysis

## Installation

### 1. Install Python (3.8 or higher) with tkinter
- Windows: Download from [python.org](https://python.org) (includes tkinter)
- macOS: `brew install python-tk` (or `brew install python3`)
- Linux Ubuntu/Debian: `sudo apt install python3 python3-pip python3-tk`
- Linux Fedora: `sudo dnf install python3 python3-tkinter`
- Linux Arch: `sudo pacman -S python tk`

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

This installs:
- `customtkinter`: Modern UI components
- `matplotlib`: For charts and graphs
- `Pillow`: For image handling

### 3. Run the GUI
```bash
python disk_analyzer_gui.py
```

## Usage Guide

### Quick Start
1. Launch the application
2. Choose "Quick Scan" for a fast analysis of large files
3. Select your main drive (C: on Windows, Home on macOS/Linux)
4. Click "Start Analysis"
5. View results and recommendations

### Advanced Usage
1. Select "Full Analysis" for comprehensive scanning
2. Choose multiple drives or custom paths
3. Adjust minimum file size (1MB - 1GB)
4. Select specific categories to analyze
5. Enable export options as needed

### Understanding Results

#### Overview Tab
- Total space analyzed across all selected paths
- File type distribution pie chart
- Summary statistics

#### Recommendations Tab
- Prioritized cleanup suggestions (High/Medium/Low)
- Estimated space recovery for each action
- Safe cleanup commands preview

#### Details Tab
- List of largest files found
- Full paths and sizes
- Search functionality

## Platform-Specific Features

### Windows
- Drive letter selection (C:, D:, etc.)
- Real-time free space display per drive
- Windows-specific cache locations
- Recycle Bin analysis

### macOS
- Quick access to ~/Library caches
- Application support folders
- Xcode derived data detection
- Trash folder analysis

### Linux
- System-wide temp directories
- Package manager caches
- Hidden configuration folders
- Distribution-specific paths

## Keyboard Shortcuts
- `Ctrl/Cmd + Q`: Quit application
- `Ctrl/Cmd + N`: New analysis
- `Ctrl/Cmd + E`: Export results
- `Tab`: Navigate between controls
- `Enter`: Confirm selection

## Troubleshooting

### GUI doesn't start - "CustomTkinter no está instalado"

This is a common issue when pip installs packages for a different Python version. Try these solutions:

#### Solution 1: Check your installation
```bash
# Run the diagnostic tool
make check-gui

# Or use the Python script
python3 check_gui_deps.py
```

#### Solution 2: Install with specific Python
```bash
# Find your Python path
which python3

# Install using that specific Python
python3 -m pip install -r requirements.txt

# Or install packages directly
python3 -m pip install customtkinter matplotlib Pillow
```

#### Solution 3: Use the same Python for both install and run
```bash
# Install
python3 -m pip install customtkinter

# Run
python3 disk_analyzer_gui.py
```

#### Solution 4: Virtual environment (recommended)
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run GUI
python disk_analyzer_gui.py
```

#### Common issues:
- **Multiple Python versions**: You might have Python from Homebrew, system Python, etc.
- **pip vs pip3**: Make sure you're using the right pip for your Python version
- **Permission issues**: You might need `--user` flag: `pip install --user customtkinter`
- **Missing tkinter on Linux**: Install with: `sudo apt install python3-tk` (Ubuntu/Debian) or `sudo dnf install python3-tkinter` (Fedora)

### Theme issues
- Try toggling between light/dark mode
- Some Linux distributions may need: `sudo apt install python3-tk`

### Performance tips
- Use Quick Scan for faster results
- Analyze specific folders instead of entire drives
- Close other applications during analysis

## Command Line Alternative

If you prefer the command line interface:
```bash
python disk_analyzer.py /path/to/analyze
```

See main README for CLI documentation.

## Screenshots

### Welcome Screen
- Modern gradient background
- Clear mode selection
- System detection display

### Drive Selection (Windows)
- Visual drive usage bars
- Multi-selection support
- Custom path option

### Analysis Progress
- Circular progress indicator
- Real-time file statistics
- Current directory display

### Results Dashboard
- Tabbed interface
- Interactive charts
- Actionable recommendations

## Contributing

Feel free to submit issues and enhancement requests!

## License

Same as the main project - see LICENSE file.

---

Enjoy your beautiful disk analysis experience! 🎉