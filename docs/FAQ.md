# Frequently Asked Questions

## General Questions

### Q: Is it safe to use?
**A:** Yes! The tool:
- Never deletes system files
- Always asks for confirmation
- Supports dry-run mode
- Shows exactly what will be deleted

### Q: Why does it show different sizes than Finder?
**A:** We calculate real disk usage using block sizes, which is more accurate than logical file sizes. This matches what you see in "About This Mac".

### Q: Can I use it on external drives?
**A:** Yes! Just specify the path:
```bash
make custom path=/Volumes/MyDrive
```

## Performance

### Q: Why is the analysis slow?
**A:** For directories with millions of files, use:
- Higher minimum size: `make analyze min_size=100`
- Quick mode: `make quick`
- Specific directories: `make downloads`

### Q: Can I speed it up?
**A:** Yes:
1. Exclude small files with higher `min_size`
2. Analyze specific directories instead of entire home
3. Use SSD instead of HDD

## Docker Issues

### Q: Docker stats show 0 or errors?
**A:** Make sure:
1. Docker Desktop is running
2. You have permissions: `docker ps`
3. Try: `docker system df` manually

### Q: Can I clean Docker without the tool?
**A:** Yes:
```bash
docker system prune -a --volumes
```

## Report Issues

### Q: HTML report is empty?
**A:** The analysis might have failed. Check:
1. You have read permissions
2. The directory exists
3. Try with `--dry-run` first

### Q: Charts not showing?
**A:** The report works offline. Try:
1. Different browser
2. Disable ad blockers
3. Check browser console for errors

## Cleanup Questions

### Q: What's safe to delete?
**A:** Generally safe:
- Browser caches
- Old downloads
- Log files
- Trash/Recycle bin

**Be careful with:**
- Application support files
- Docker volumes (may contain data)
- Development caches (may slow rebuilds)

### Q: How do I undo deletions?
**A:** You can't! That's why we:
- Show previews first
- Ask for confirmation
- Recommend backups

## Customization

### Q: Can I add custom cache locations?
**A:** Yes, edit the `CACHE_DIRS` list in `disk_analyzer.py`

### Q: Can I change the language?
**A:** Currently Spanish only, but you can modify the strings in the source code

### Q: Can I export to CSV?
**A:** Not directly, but JSON export can be converted:
```bash
python3 disk_analyzer.py ~/ --export data
# Then use jq or Python to convert JSON to CSV
```