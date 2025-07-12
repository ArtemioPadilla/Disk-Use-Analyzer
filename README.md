# 🚀 Disk Use Analyzer

<div align="center">
![Python](https://img.shields.io/badge/python-3.6+-blue.svg)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)

*A powerful macOS disk space analyzer with zero dependencies*

[Features](#features) • [Quick Start](#quick-start) • [Usage](#usage) • [Examples](#examples) • [FAQ](docs/FAQ.md)

</div>

## 🎯 Overview

**Disk Use Analyzer** is a standalone Python tool that helps you understand and manage your macOS disk space. It generates beautiful interactive HTML reports and provides smart cleanup suggestions - all without requiring any external dependencies!

### ✨ Key Features

| Feature | Description |
|---------|-------------|
| 📊 **Interactive Reports** | Beautiful HTML visualizations with Chart.js |
| 🐳 **Docker Support** | Analyze Docker volumes, images, and containers |
| 🧹 **Smart Cleanup** | Safe cleanup suggestions with risk levels |
| 📂 **Category Analysis** | Organized views by file type and location |
| ⚡ **Performance Mode** | Handles millions of files efficiently |
| 🔒 **Safety First** | Dry-run mode and confirmation prompts |
| 🌐 **100% Offline** | No internet connection required |

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/disk-use-analyzer.git
cd disk-use-analyzer

# Check dependencies (Python 3.6+ only!)
make check

# Run your first analysis
make analyze
```

That's it! No `pip install`, no virtual environments, no hassle.

## 📋 Requirements

- **macOS** (10.14 or later)
- **Python 3.6+** (included with macOS)
- **Docker Desktop** (optional, for Docker analysis)

## 🛠️ Usage

### Basic Commands

```bash
# Standard analysis (files > 10MB)
make analyze

# Quick analysis (files > 50MB)
make quick

# Full analysis with HTML report
make full

# Generate interactive HTML report
make report
```

### Cleanup Operations

```bash
# Always preview first!
make clean-preview

# Clean system caches
make clean-cache

# Clean Docker resources
make clean-docker

# Clean everything (with confirmation)
make clean-all
```

### Analyze Specific Locations

```bash
# Common directories
make apps        # /Applications
make downloads   # ~/Downloads
make dev         # ~/Developer
make documents   # ~/Documents

# Custom path with size filter
make custom path=/path/to/analyze min_size=100
```

## 📊 Report Features

The HTML report includes:

- **Disk Usage Overview** - Visual representation of your disk usage
- **Interactive Sankey Diagrams** - Flow visualization of space distribution
- **Category Breakdown** - Files organized by type (Development, Documents, etc.)
- **Top Space Consumers** - Largest files and directories at a glance
- **Smart Cleanup Suggestions** - Categorized by risk level (Low/Medium/High)
- **Detailed File Lists** - Searchable tables with sorting

## 🏗️ Architecture

```
disk-use-analyzer/
├── disk_analyzer.py      # Single-file analyzer (no dependencies!)
├── Makefile             # User-friendly commands
├── README.md            # You are here
├── CLAUDE.md            # Development guide
├── LICENSE              # MIT License
├── docs/                # Documentation
│   ├── FAQ.md          # Frequently Asked Questions
│   └── examples/       # Usage examples
└── utils/              # Helper scripts
```

### How It Works

1. **Scanning** - Recursively analyzes directories using Python's `os` module
2. **Analysis** - Calculates real disk usage using block sizes
3. **Categorization** - Smart file type detection and grouping
4. **Visualization** - Generates self-contained HTML with embedded Chart.js
5. **Cleanup** - Suggests safe deletions based on file types and locations

## 🔍 Examples

### Find Large Old Files
```bash
# Analyze downloads folder for files > 100MB
make custom path=~/Downloads min_size=100

# Find files not accessed in 6 months
find ~/Downloads -atime +180 -size +10M
```

### Clean Development Projects
```bash
# Remove old node_modules
find ~/projects -name "node_modules" -mtime +30 -exec rm -rf {} +

# Clean Python caches
find ~/projects -name "__pycache__" -exec rm -rf {} +
```

### Docker Cleanup
```bash
# Preview Docker cleanup
make clean-docker

# Force clean all Docker resources
docker system prune -a --volumes -f
```

## 🚨 Safety Features

- **Never deletes system files** - Protected paths are excluded
- **Dry-run by default** - Preview before any deletion
- **Confirmation required** - No accidental deletions
- **Risk classification** - Know what's safe to delete
- **Detailed previews** - See exactly what will be removed

## 📈 Performance Tips

For large filesystems (>1M files):

1. **Use minimum size filter**: `make analyze min_size=50`
2. **Analyze specific directories**: `make downloads`
3. **Use quick mode**: `make quick`
4. **Run during low activity periods**

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Test your changes thoroughly
4. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with love for the macOS community
- Special thanks to all contributors

---

<div align="center">

Made with ❤️ by the Disk Use Analyzer team

[Report Issue](https://github.com/yourusername/disk-use-analyzer/issues) • [Documentation](docs/) • [Examples](docs/examples/)

</div>