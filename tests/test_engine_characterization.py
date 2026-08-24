"""Characterization tests: pin the engine's CURRENT behavior before refactoring.

These describe what the code does today, not what it ideally should do.
A failure here during the shared-engine extraction means the refactor changed
behavior -- fix the refactor, not the test.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from disk_analyzer_core import DiskAnalyzerCore, KB, MB, GB


@pytest.fixture
def tree(tmp_path):
    """A small, predictable directory tree."""
    (tmp_path / "big.bin").write_bytes(b"x" * (3 * 1024 * 1024))   # 3 MB
    (tmp_path / "small.txt").write_text("hello")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.bin").write_bytes(b"y" * (2 * 1024 * 1024))     # 2 MB
    ignored = tmp_path / "node_modules"
    ignored.mkdir()
    (ignored / "junk.bin").write_bytes(b"z" * (5 * 1024 * 1024))
    return tmp_path


class TestFormatSize:
    def test_bytes(self):
        core = DiskAnalyzerCore(".")
        assert core.format_size(0) == "0.00 B"

    def test_kilobytes(self):
        core = DiskAnalyzerCore(".")
        assert core.format_size(1536).endswith("KB")

    def test_gigabytes(self):
        core = DiskAnalyzerCore(".")
        assert core.format_size(5 * GB).startswith("5.00")


class TestScanDirectory:
    def test_finds_large_files_above_min_size(self, tree):
        core = DiskAnalyzerCore(str(tree), min_size_mb=1)
        core.scan_directory(tree)
        names = {Path(f["path"]).name for f in core.large_files}
        assert "big.bin" in names
        assert "small.txt" not in names

    def test_uses_real_disk_blocks_not_logical_size(self, tree):
        # Pad a file with a sparse hole so logical size and on-disk size
        # provably diverge -- this makes the test fail loudly if scan_directory
        # is ever changed to use st_size instead of st_blocks * 512.
        sparse = tree / "sparse.bin"
        with open(sparse, "wb") as fh:
            fh.write(b"a" * (1024 * 1024))  # 1 MB of real data
            fh.truncate(20 * 1024 * 1024)   # logical size 20 MB, mostly a hole

        core = DiskAnalyzerCore(str(tree), min_size_mb=1)
        core.scan_directory(tree)
        entry = next(f for f in core.large_files if Path(f["path"]).name == "sparse.bin")
        stat = sparse.stat()
        on_disk = stat.st_blocks * 512 if hasattr(stat, "st_blocks") else stat.st_size
        assert entry["size"] == on_disk
        # The whole point of using st_blocks: on a sparse file, on-disk size
        # must be materially smaller than the logical size it was truncated to.
        if hasattr(stat, "st_blocks"):
            assert entry["size"] < stat.st_size

    def test_skips_ignored_directories(self, tree):
        core = DiskAnalyzerCore(str(tree), min_size_mb=1)
        core.scan_directory(tree)
        paths = " ".join(f["path"] for f in core.large_files)
        assert "node_modules" not in paths

    def test_does_not_follow_symlinks(self, tmp_path):
        target = tmp_path / "real"
        target.mkdir()
        (target / "file.bin").write_bytes(b"a" * (2 * 1024 * 1024))
        link = tmp_path / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks not supported here")
        core = DiskAnalyzerCore(str(tmp_path), min_size_mb=1)
        core.scan_directory(tmp_path)
        # The file is found once (through the real dir), not twice via the link
        matches = [f for f in core.large_files if Path(f["path"]).name == "file.bin"]
        assert len(matches) == 1

    def test_records_file_type_stats(self, tree):
        core = DiskAnalyzerCore(str(tree), min_size_mb=1)
        core.scan_directory(tree)
        assert ".bin" in core.file_type_stats


class TestProtectedPaths:
    @pytest.mark.parametrize("path,expected", [
        ("/System/Library/Kernels/kernel", True),
        ("/usr/lib/libSystem.dylib", True),
        ("/bin", True),
        ("/sbin", True),
        ("/Applications/Foo.app/Contents/MacOS/Foo", True),
        ("/private/var/vm/sleepimage", True),
        (str(Path.home() / "Downloads" / "movie.mp4"), False),
        (str(Path.home() / "Library" / "Caches" / "something"), False),
    ])
    def test_protection_table(self, path, expected):
        core = DiskAnalyzerCore(".")
        assert core.is_protected_path(path) is expected

    def test_prefix_match_not_substring(self):
        """A path merely CONTAINING a protected prefix is not protected."""
        core = DiskAnalyzerCore(".")
        assert core.is_protected_path(str(Path.home() / "my/System/notes.txt")) is False

    def test_full_prefix_as_inner_substring_not_protected(self):
        """A path that embeds a COMPLETE protected-prefix string
        ('/System/Library/') as an inner substring, without starting with it,
        must not be protected. `my/System/notes.txt` above never contains a
        full prefix string (only a partial '/System/' fragment), so it can't
        catch a `startswith(prefix)` -> `prefix in file_path` regression --
        this one can, because '/System/Library/' does appear verbatim inside
        the path.
        """
        core = DiskAnalyzerCore(".")
        path = str(Path.home() / "backup/System/Library/notes.txt")
        assert core.is_protected_path(path) is False

    def test_root_dir_as_inner_path_segment_not_protected(self):
        """A path containing '/bin' as a non-root, inner path segment must
        not be protected -- only an exact top-level '/bin' or '/sbin'
        component counts. Catches a PROTECTED_ROOT_DIRS exact-match ->
        substring regression that neither of the two tests above exercises.
        """
        core = DiskAnalyzerCore(".")
        path = str(Path.home() / "trash/bin/file.txt")
        assert core.is_protected_path(path) is False


class TestCacheClassification:
    """Task 4 unified both classifiers behind analyzer.cache_types.classify().

    These tests used to pin the pre-unification divergence between the CLI's
    classify_cache and the core's categorize_cache (different label sets, and
    a precedence bug in the core's classifier -- see below). That divergence
    is now deliberately gone: this is the ONE authorized characterization-test
    change in this phase, and it is intentional, not a regression.
    """

    @pytest.mark.parametrize("path,expected", [
        (Path.home() / "Library/Caches/com.docker.docker", "Docker"),
        # FIXED by Task 4 (was a real bug): categorize_cache used to check the
        # 'code'/'vscode' substring BEFORE the 'xcode' substring, and "xcode"
        # itself contains the substring "code". So DerivedData was
        # misclassified as "VS Code Cache" and the 'xcode' branch was
        # unreachable. analyzer.cache_types.classify() checks 'xcode' first,
        # so this now correctly returns "Xcode Cache".
        (Path.home() / "Library/Developer/Xcode/DerivedData", "Xcode Cache"),
        (Path.home() / "Library/Caches/com.microsoft.VSCode", "VS Code Cache"),
        (Path.home() / ".npm", "NPM Cache"),
        (Path.home() / ".Trash", "Papelera"),
    ])
    def test_core_labels(self, path, expected):
        core = DiskAnalyzerCore(".")
        assert core.categorize_cache(path) == expected

    def test_cli_and_core_labels_now_match(self):
        """Was test_cli_labels_differ_from_core, which documented the
        pre-unification divergence. Task 4 made both classes delegate to the
        same analyzer.cache_types.classify(), so they now agree -- this test
        is renamed and its assertion flipped on purpose."""
        from disk_analyzer import DiskAnalyzer
        cli = DiskAnalyzer(".")
        core = DiskAnalyzerCore(".")
        vscode = Path.home() / "Library/Caches/com.microsoft.VSCode"
        assert cli.classify_cache(vscode) == core.categorize_cache(vscode) == "VS Code Cache"

    def test_xcode_bug_is_fixed_for_both_cli_and_core(self):
        """Was test_cli_does_not_have_the_xcode_bug, which asserted the CLI's
        OLD label ('Xcode Development') to document that only the CLI's
        classifier had correct 'xcode'-before-'code' precedence. Task 4
        unified both classifiers behind the fixed analyzer.cache_types.classify(),
        so now BOTH correctly return the shared 'Xcode Cache' label -- the bug
        is fixed everywhere, not just avoided in one implementation.
        """
        from disk_analyzer import DiskAnalyzer
        cli = DiskAnalyzer(".")
        core = DiskAnalyzerCore(".")
        xcode = Path.home() / "Library/Developer/Xcode/DerivedData"
        assert cli.classify_cache(xcode) == core.categorize_cache(xcode) == "Xcode Cache"


class TestRecommendations:
    def test_recommendations_have_required_shape(self):
        core = DiskAnalyzerCore(".")
        # Paths match the real cache locations the npm/vscode rules scope to
        # (Task 4 of the final review pass) -- an arbitrary '/fake/...' path
        # no longer fires either rule.
        core.cache_locations = [
            {"path": "/fake/.npm", "size": 3 * GB, "type": "NPM Cache"},
            {"path": "/fake/Library/Application Support/Code/Cache", "size": 2 * GB, "type": "VS Code Cache"},
        ]
        recs = core.generate_recommendations()
        assert recs, "expected recommendations for large known caches"
        for rec in recs:
            assert "type" in rec
            assert "space" in rec
            assert "tier" in rec

    def test_recommendations_sorted_by_tier_then_size(self):
        # Tier 1 total (12 GB) exceeds the Tier 2 Docker entry (a lone 20 GB
        # reclaim) so a naive "sort by size" would put Docker first. Real
        # sort key is (tier, -space): tier wins, size only breaks ties within
        # a tier. This is what would break if someone "simplified" the sort
        # to `key=lambda x: -x['space']` during the refactor.
        #
        # Sizes are picked so insertion order and sorted order DIFFER: the
        # source code's TIER 1 block appends the VS Code Cache entry before
        # the NPM Cache entry regardless of size (see generate_recommendations
        # in disk_analyzer_core.py), so making npm the larger of the two
        # means the correctly-sorted output (npm first, by size descending)
        # is the *opposite* of append order. That is what makes this test
        # able to catch `sorted(...)` being deleted outright, not just
        # replaced with the wrong key -- verified by mutation (see report).
        core = DiskAnalyzerCore(".")
        core.cache_locations = [
            {"path": "/fake/.npm", "size": 9 * GB, "type": "NPM Cache"},
            {"path": "/fake/Library/Application Support/Code/Cache", "size": 3 * GB, "type": "VS Code Cache"},
        ]
        core.docker_stats = {"available": True, "reclaimable": 20 * GB}
        recs = core.generate_recommendations()

        tiers = [r["tier"] for r in recs]
        assert tiers == sorted(tiers)
        # Tier 1 items (smaller, combined) must all precede the larger Tier 2 item.
        assert [r["type"] for r in recs] == ["Cache de npm", "Cache de VS Code", "Docker"]
        # Within tier 1, the larger entry (npm, 9 GB) sorts before the
        # smaller one (VS Code, 3 GB): descending by space, not insertion
        # order (insertion order appends VS Code first).
        tier1 = [r for r in recs if r["tier"] == 1]
        assert [r["space"] for r in tier1] == sorted((r["space"] for r in tier1), reverse=True)
