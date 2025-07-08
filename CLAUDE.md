# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **macOS Disk Usage Analyzer** - a powerful standalone Python tool for analyzing disk usage on macOS systems with advanced visualization capabilities, smart cleanup recommendations, and special support for Docker resources. The tool generates beautiful interactive HTML reports with tabbed navigation and category-specific analysis.

## Key Commands

### Development and Testing
```bash
# Check dependencies and verify installation
make check

# Run standard disk analysis
make analyze

# Quick analysis (files > 50MB)
make quick

# Full analysis with HTML report
make full

# Generate HTML report (runs full analysis)
make report
```

### Cleanup Operations
```bash
# Preview what can be cleaned (dry-run mode - ALWAYS use first)
make clean-preview

# Clean system cache
make clean-cache

# Clean Docker resources
make clean-docker

# Clean everything (cache + Docker)
make clean-all
```

### Custom Analysis
```bash
# Analyze specific path
make custom path=/path/to/analyze min_size=100

# Analyze common directories
make apps        # /Applications
make downloads   # ~/Downloads
make dev         # ~/Developer
make documents   # ~/Documents
```

## Architecture

This is a single-file Python application with no external dependencies:

- **`disk_analyzer.py`** (2,644 lines) - Contains all analysis logic in a single `DiskAnalyzer` class
- **`Makefile`** - Provides user-friendly command interface
- **No external Python packages** - Uses only Python standard library

### Key Components in disk_analyzer.py

1. **DiskAnalyzer class** - Main analysis engine with methods for:
   - `analyze_directory()` - Recursive directory scanning using real disk blocks
   - `analyze_docker()` - Docker resource analysis with improved parsing
   - `generate_html_report()` - Interactive report with tabbed navigation
   - `clean_cache()`, `clean_docker()` - Cleanup functionality
   - `_prepare_sankey_data_by_category()` - Multi-category Sankey visualization
   - `_get_category_details()` - Category-specific file analysis
   - `_generate_category_cleanup_commands()` - Smart cleanup suggestions

2. **Advanced Visualization Features**:
   - **Tabbed Sankey Diagrams**: Separate views for each category (Development, Docker, Library, etc.)
   - **Enhanced Disk Usage Bar**: Segmented bar showing category breakdown with icons
   - **Category-Specific Analysis**: Detailed file lists, cleanup commands per category
   - **Interactive Elements**: Hover effects, smooth transitions, lazy loading

3. **Report Generation**:
   - Embeds Chart.js and Plotly.js for rich visualizations
   - Responsive design with modern UI
   - Offline viewing capability
   - Export to JSON for further processing

4. **Safety Features**:
   - Always requires confirmation before deletion
   - Supports dry-run mode for all cleanup operations
   - Never deletes critical system files
   - Risk levels for cleanup commands (Low/Medium/High)

## Important Notes

- **Language**: Documentation and user-facing messages are in Spanish
- **Platform**: macOS-specific (uses macOS paths and commands)
- **Python Version**: Requires Python 3.6+ with type hints
- **No pip install needed**: Uses only standard library modules
- **Docker**: Optional dependency for Docker analysis features

## Testing Changes

When modifying the code:
1. Always test with dry-run first: `make clean-preview`
2. Test analysis on a small directory first: `make custom path=./test min_size=1`
3. Verify HTML report generation: `make report`
4. Check that all Makefile commands still work after changes

## Known Issues & Limitations

- **Template String Escaping**: When embedding JavaScript template literals in Python f-strings, Plotly template syntax like `%{label}` must be escaped as `%{{label}}` to avoid Python format string errors.
- **Empty Reports**: The `--quick` flag was removed from the Makefile's `report` command as it would skip analysis and generate empty reports. Always run analysis before generating reports.
- **Duplicate Methods**: Be careful not to create duplicate method definitions. If a method appears incomplete due to a docstring error, verify the method structure before adding code.
- **Large Directory Timeouts**: Full home directory analysis may timeout on systems with >500k files. Use `make quick` or analyze specific directories instead.
- **Category Detection**: Some directories may be miscategorized. The algorithm uses path patterns which may not always be accurate.

## Recent Features & Fixes

### New Features (2025)

- **Tabbed Sankey Navigation**: Multiple Sankey diagrams with tabs for different categories:
  - Vista General (Overview) - Complete directory analysis
  - Desarrollo - Development files (.continue, repos, node_modules)
  - Docker - Docker-specific resources
  - Library - System libraries and caches
  - Documents - User documents
  - Otros - Uncategorized large directories
  
- **Enhanced Disk Usage Bar**: Segmented visualization showing:
  - Category breakdown with colors matching the main UI
  - Hover effects and tooltips
  - Icons for each category
  - Responsive legend with usage details

- **Category-Specific Analysis**: Each tab now shows:
  - Smart cleanup commands with risk levels
  - Top files in that category
  - File type distribution
  - Estimated recoverable space

- **Performance Optimizations**:
  - Lite mode for directories with >100k files
  - Lazy loading for Sankey diagrams
  - Limited directory depth to prevent timeouts

### Bug Fixes

- **Sankey Diagram Missing**: Fixed by removing a duplicate `generate_html_report` method that was overriding the correct implementation with Sankey support.
- **Disk Usage Bar**: Fixed overflow issue when disk usage percentage exceeds 100%. Bar width is now capped at 100% visually.
- **Sankey Organization**: Improved by grouping small directories (<2% of total) into "Otros" node and increasing minimum threshold to 1%.
- **Disk Space Calculation**: Fixed major issue where analysis reported much more space than actually used:
  - Now uses `st_blocks * 512` to get real disk usage instead of logical file size
  - Excludes Docker.raw sparse files
  - Doesn't follow symbolic links to avoid counting files multiple times
  - Shows warning when analyzed space exceeds reported disk usage
- **APFS Disk Usage**: Fixed calculation to use `total - available` instead of reading used directly from df, as APFS reports purgeable space incorrectly
- **Docker Size Parsing**: Fixed parsing of Docker sizes with 'kB' units and improved error handling