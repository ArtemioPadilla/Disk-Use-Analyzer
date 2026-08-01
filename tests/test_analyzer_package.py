"""Checks for the shared `analyzer` package extracted in Phase 3 Task 2.

Kept in its own file (rather than test_engine_characterization.py) to avoid
colliding with concurrent edits to that file.
"""
import os
import sys
from pathlib import Path


class TestPackaging:
    def test_analyzer_package_is_stdlib_only(self):
        """The CLI must keep working without any pip install."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c", "import analyzer.constants"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent)},
        )
        assert result.returncode == 0, result.stderr
