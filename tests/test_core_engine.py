"""Tests for DiskAnalyzerCore engine logic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from disk_analyzer_core import DiskAnalyzerCore, KB, MB, GB


class TestParseDockerSize:
    def setup_method(self):
        self.core = DiskAnalyzerCore(".")

    def test_no_space_gb(self):
        assert self.core.parse_docker_size("1.5GB") == int(1.5 * GB)

    def test_no_space_mb(self):
        assert self.core.parse_docker_size("500MB") == 500 * MB

    def test_lowercase_kb(self):
        # docker emits kB with lowercase k
        assert self.core.parse_docker_size("2.796kB") == int(2.796 * KB)

    def test_with_space(self):
        assert self.core.parse_docker_size("1.5 GB") == int(1.5 * GB)

    def test_zero_bytes(self):
        assert self.core.parse_docker_size("0B") == 0

    def test_with_percentage_suffix(self):
        assert self.core.parse_docker_size("1.5GB (45%)") == int(1.5 * GB)

    def test_garbage_returns_zero(self):
        assert self.core.parse_docker_size("N/A") == 0
