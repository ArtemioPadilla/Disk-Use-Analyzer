"""Shared directory-size measurement.

Task 5 reconciliation: the CLI used to shell out to `du -sk` while the core
engine walked the tree with `rglob` and summed `st_blocks * 512`. The two
could give different answers for the same directory (see the git history of
disk_analyzer.py's old get_directory_size for the `du`-based version). We
keep the core's approach -- it's consistent with how the rest of the engine
measures disk usage (scan_directory also uses st_blocks) and it doesn't
depend on a subprocess -- and both the CLI and the core now delegate here.

Known consequence: this walk sums every directory entry's on-disk blocks,
so a file with multiple hard links is counted once per link, whereas `du`
dedupes by inode and counts it once. Sparse files and symlinks are also
handled differently than `du` might. This is an accepted trade-off: the
goal was ONE answer shared across the engine, not bit-for-bit parity with
`du`.

Standard library only -- analyzer/ must not depend on third-party packages.
"""
from pathlib import Path


def get_directory_size(directory: Path) -> int:
    """Calcula el tamaño de un directorio sumando el uso real en disco
    (bloques asignados), no el tamaño lógico de los archivos."""
    total_size = 0
    try:
        for entry in directory.rglob('*'):
            if entry.is_file(follow_symlinks=False):
                try:
                    stat = entry.stat(follow_symlinks=False)
                    total_size += stat.st_blocks * 512 if hasattr(stat, 'st_blocks') else stat.st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total_size
