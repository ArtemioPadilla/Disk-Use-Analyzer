# AGENTS.md

This file provides guidance to AI coding agents (GitHub Copilot, Claude, ChatGPT, and other AI development tools) when working with code in this repository.

## Project Summary

**Disk Use Analyzer** is a macOS disk usage analysis tool written in Python. It provides:
- Interactive HTML reports with visualizations
- Docker resource analysis
- Smart cleanup recommendations
- Multiple interfaces: CLI, GUI, and Web

## Repository Structure

```
├── disk_analyzer.py        # Main CLI tool (single-file, no dependencies)
├── disk_analyzer_core.py   # Core analysis logic
├── disk_analyzer_gui.py    # GUI interface (CustomTkinter)
├── disk_analyzer_web.py    # Web interface (FastAPI)
├── Makefile                # User-friendly command interface
├── CLAUDE.md               # Claude-specific AI guidance
├── AGENTS.md               # This file - general AI agent guidance
├── docs/                   # Documentation
│   ├── FAQ.md              # Frequently Asked Questions
│   └── examples/           # Usage examples
├── static/                 # Web static assets
└── utils/                  # Helper scripts
```

## Key Technical Details

### Language & Requirements
- **Python 3.6+** with type hints
- **No external dependencies** for core CLI functionality
- Optional dependencies for GUI (CustomTkinter) and Web (FastAPI)

### Main Entry Points
- `disk_analyzer.py` - Primary CLI application
- `disk_analyzer_gui.py` - GUI application
- `disk_analyzer_web.py` - Web server application

### Coding Conventions
- Single responsibility per file where possible
- Spanish language for user-facing CLI/GUI messages
- English for code comments, documentation, and variable names
- Type hints for function signatures
- Self-contained HTML reports with embedded JavaScript libraries

## Common Tasks

### Running Analysis
```bash
make analyze           # Standard analysis
make quick             # Quick mode (files > 50MB)
make full              # Full analysis with HTML report
```

### Testing Changes
1. Test CLI: `make custom path=./test min_size=1`
2. Test cleanup (dry-run): `make clean-preview`
3. Test HTML report: `make report`
4. Verify Makefile commands work after changes

### Adding New Features
1. Follow existing code patterns in `disk_analyzer.py`
2. Maintain backward compatibility with CLI arguments
3. Update documentation if adding new commands
4. Test all interfaces (CLI, GUI, Web) if modifying core logic

## Important Considerations

### Safety
- Cleanup operations MUST support dry-run mode
- Never delete without user confirmation
- Protect critical system paths

### Performance
- Handle large directories (>100k files) efficiently
- Support minimum file size filtering
- Implement lazy loading for visualizations

### Compatibility
- macOS-specific paths and commands in main analyzer
- Cross-platform considerations in `Makefile.cross-platform`

## Files to Avoid Modifying

- `.git/` - Git internals
- `__pycache__/` - Python cache
- Generated reports (`disk_report_*.html`, `disk_report_*.json`)

## Getting Help

- See `CLAUDE.md` for Claude-specific detailed guidance
- See `docs/FAQ.md` for common questions
- See `README.md` for user documentation
