# Custom Analysis Examples

## Analyzing Specific Project Types

### Node.js Projects
```bash
# Find large node_modules
make custom path=~/projects min_size=1

# Clean old node_modules
find ~/projects -name "node_modules" -type d -mtime +30 -exec rm -rf {} +
```

### Python Projects
```bash
# Find large virtual environments
make custom path=~/projects min_size=50

# Look for .venv, env, venv folders
find ~/projects -name "venv" -o -name ".venv" -o -name "env" -type d
```

### Docker Projects
```bash
# Analyze Docker directory
make custom path=~/.docker min_size=100

# Clean Docker completely
docker system prune -a --volumes -f
```

## Advanced Filtering

### By File Type
```bash
# Find large videos
find ~/ -name "*.mp4" -o -name "*.mov" -size +100M

# Find large disk images
find ~/ -name "*.dmg" -o -name "*.iso" -size +500M
```

### By Age
```bash
# Files not accessed in 6 months
find ~/Downloads -atime +180 -size +10M

# Old log files
find ~/Library/Logs -name "*.log" -mtime +30
```

## Automation Scripts

### Weekly Cleanup
```bash
#!/bin/bash
# Save as ~/bin/weekly-cleanup.sh

cd ~/disk-use-analyzer

# Generate report
make report

# Clean safe items
make clean-cache FORCE=true

# Show summary
echo "Cleanup complete!"
```

### Project Cleanup
```bash
#!/bin/bash
# Clean development projects

# Remove old node_modules
find ~/projects -name "node_modules" -mtime +60 -exec rm -rf {} +

# Remove Python caches
find ~/projects -name "__pycache__" -exec rm -rf {} +

# Remove .DS_Store files
find ~/projects -name ".DS_Store" -delete
```