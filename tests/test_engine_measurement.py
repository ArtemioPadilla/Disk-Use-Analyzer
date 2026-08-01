"""Task 5: reconcile the two divergent implementations of directory-size
measurement (CLI's `du -sk` shell-out vs. core's `rglob` + `st_blocks` walk)
and of the cache-size threshold in `find_cache_locations` (core reported
`size > 0`, CLI reported `size > MB`).

Before this task, the CLI and the core engine could give different answers
for the exact same directory. These tests pin the reconciled behavior: one
directory-size implementation shared by both, and one threshold (`> MB`,
the CLI's, since a few-KB cache isn't actionable).
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from disk_analyzer_core import DiskAnalyzerCore, MB


@pytest.fixture
def tree(tmp_path):
    """A small, predictable directory tree (mirrors the fixture used in
    tests/test_engine_characterization.py, duplicated here on purpose so this
    file has no import-time dependency on that file, which another task is
    concurrently editing)."""
    (tmp_path / "big.bin").write_bytes(b"x" * (3 * 1024 * 1024))   # 3 MB
    (tmp_path / "small.txt").write_text("hello")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.bin").write_bytes(b"y" * (2 * 1024 * 1024))    # 2 MB
    return tmp_path


class TestDirectorySize:
    def test_cli_and_core_agree(self, tree):
        """Same directory, same answer -- there must be exactly ONE way to
        measure a directory's size, shared by both entry points."""
        from disk_analyzer import DiskAnalyzer

        core = DiskAnalyzerCore(str(tree))
        cli = DiskAnalyzer(str(tree))

        core_size = core.get_directory_size(tree)
        cli_size = cli.get_directory_size(tree)

        assert core_size > 0, "sanity check: the tree actually has bytes on disk"
        assert cli_size == core_size

    def test_cli_and_core_agree_with_a_hard_link(self, tree):
        """Regular files alone weren't enough to prove this test can fail:
        on APFS, `du -sk` and a naive rglob+st_blocks sum happen to land on
        the exact same number for a tree with no hard links, no sparse
        files, and no symlinks -- verified empirically before writing this
        test. Hard links are where they provably diverge: `du` counts a
        multiply-linked file's disk blocks ONCE (it dedupes by inode),
        while a naive walk that sums every directory entry's st_blocks
        counts the same physical blocks once per link. Before reconciliation
        this made the CLI (`du`-based) and the core (`rglob`-based) disagree
        on this exact tree. After reconciliation both delegate to the same
        walk, so they now agree with EACH OTHER -- even though that shared
        answer double-counts relative to the old `du`-based CLI number. See
        the task report for the measured before/after difference.
        """
        try:
            os.link(str(tree / "big.bin"), str(tree / "hardlink.bin"))
        except OSError:
            pytest.skip("hard links not supported on this filesystem")

        from disk_analyzer import DiskAnalyzer

        core = DiskAnalyzerCore(str(tree))
        cli = DiskAnalyzer(str(tree))

        assert cli.get_directory_size(tree) == core.get_directory_size(tree)


class TestCacheThreshold:
    """`find_cache_locations` reads CACHE_DIRS as a name bound at import time
    into disk_analyzer_core's own module namespace via
    `from analyzer.constants import CACHE_DIRS` -- NOT as an attribute access
    on `analyzer.constants` at call time. So patching
    `analyzer.constants.CACHE_DIRS` (as a naive monkeypatch might attempt)
    would silently fail to intercept anything, since the function looks up
    the module-local name `CACHE_DIRS`, already bound to the original list
    object. The patch below targets `disk_analyzer_core.CACHE_DIRS` instead,
    which is the name actually resolved inside the function.
    """

    def test_tiny_caches_are_not_reported(self, tmp_path, monkeypatch):
        tiny = tmp_path / "tiny_cache"
        tiny.mkdir()
        (tiny / "a.txt").write_text("x")  # a handful of bytes, well under 1 MB

        import disk_analyzer_core
        monkeypatch.setattr(disk_analyzer_core, "CACHE_DIRS", [str(tiny)], raising=False)

        core = DiskAnalyzerCore(str(tmp_path))
        core.find_cache_locations()

        assert core.cache_locations == []

    def test_caches_above_threshold_are_still_reported(self, tmp_path, monkeypatch):
        """Canary for the test above: proves the CACHE_DIRS patch actually
        intercepts (otherwise the previous test would pass vacuously because
        find_cache_locations never even looked at our fake tiny cache)."""
        big = tmp_path / "big_cache"
        big.mkdir()
        (big / "a.bin").write_bytes(b"x" * (2 * MB))

        import disk_analyzer_core
        monkeypatch.setattr(disk_analyzer_core, "CACHE_DIRS", [str(big)], raising=False)

        core = DiskAnalyzerCore(str(tmp_path))
        core.find_cache_locations()

        assert len(core.cache_locations) == 1
        assert core.cache_locations[0]["size"] > MB
