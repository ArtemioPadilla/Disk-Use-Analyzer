"""Regression test: the server must not crash at import time if
~/.disk-analyzer is root-owned (e.g. left behind by a previous
`sudo make web` run) and results/ doesn't exist under it yet.

This is exactly the situation that caused the agents.log bug documented in
agents_manager.py -- it IS root-owned on the dev machine used to write this
test (`ls -la ~/.disk-analyzer` shows `results/` owned by root).
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import disk_analyzer_web


class TestResultsDirMkdirGuard:
    def test_import_survives_unwritable_disk_analyzer_dir(self, monkeypatch, tmp_path, capsys):
        fake_home = tmp_path
        blocked = fake_home / ".disk-analyzer"
        blocked.mkdir()
        # Read+execute but no write: mkdir("results") inside it must fail
        # with PermissionError, simulating a root-owned ~/.disk-analyzer.
        blocked.chmod(0o500)
        monkeypatch.setenv("DISK_ANALYZER_NO_AUTH", "1")

        try:
            monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
            importlib.reload(disk_analyzer_web)  # must not raise

            assert disk_analyzer_web.RESULTS_DIR == blocked / "results"
            assert not disk_analyzer_web.RESULTS_DIR.exists()
            captured = capsys.readouterr()
            assert "Warning" in captured.out
        finally:
            blocked.chmod(0o700)  # restore so tmp_path cleanup can remove it
            # Undo the Path.home patch now (rather than waiting for pytest's
            # automatic teardown) and reload once more, so disk_analyzer_web's
            # module-level RESULTS_DIR/SESSIONS_FILE globals go back to
            # pointing at the real home directory before any other test file
            # imports this already-loaded module.
            monkeypatch.undo()
            importlib.reload(disk_analyzer_web)

    def test_import_still_creates_dir_when_writable(self, monkeypatch, tmp_path):
        """Sanity check: the guard must not silently skip creation in the
        normal (writable) case."""
        fake_home = tmp_path
        monkeypatch.setenv("DISK_ANALYZER_NO_AUTH", "1")

        try:
            monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
            importlib.reload(disk_analyzer_web)

            assert disk_analyzer_web.RESULTS_DIR.is_dir()
        finally:
            monkeypatch.undo()
            importlib.reload(disk_analyzer_web)
