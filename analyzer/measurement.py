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

Portability note: `Path.is_file(follow_symlinks=False)` / `Path.stat(follow_symlinks=False)`
only gained the `follow_symlinks` keyword in Python 3.13 -- calling either with that
argument on 3.6-3.12 raises `TypeError`. `Path.lstat()` never follows symlinks (that is
its whole purpose) and has existed since Python 3.4, so it gives the same "don't follow
symlinks" semantics as the two 3.13-only calls combined, in a single syscall, on every
supported version. Do NOT swap this for a bare `entry.is_file()` -- that follows
symlinks by default and would double-count anything a symlink points at, defeating the
reason this walk avoids following them in the first place.
"""
import stat as stat_module
from pathlib import Path


def get_directory_size(directory: Path) -> int:
    """Calcula el tamaño de un directorio sumando el uso real en disco
    (bloques asignados), no el tamaño lógico de los archivos."""
    total_size = 0
    try:
        for entry in directory.rglob('*'):
            try:
                entry_stat = entry.lstat()
            except OSError:
                continue
            if stat_module.S_ISREG(entry_stat.st_mode):
                total_size += entry_stat.st_blocks * 512 if hasattr(entry_stat, 'st_blocks') else entry_stat.st_size
    except OSError:
        pass
    return total_size
