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


class TestRecommendationLabels:
    """generate_recommendations must filter on the labels categorize_cache
    actually produces ('VS Code Cache' / 'NPM Cache'), not the CLI's
    separate labels ('VS Code' / 'Node.js/npm'). Otherwise these tier-1
    recommendations can never fire for web/GUI users.
    """

    def setup_method(self):
        self.core = DiskAnalyzerCore(".")

    def test_vscode_and_npm_recommendations_fire(self):
        # Labels exactly as categorize_cache produces them.
        self.core.cache_locations = [
            {"path": "/fake/Code/Cache", "size": 2 * GB, "type": "VS Code Cache"},
            {"path": "/fake/.npm", "size": 3 * GB, "type": "NPM Cache"},
        ]
        recs = self.core.generate_recommendations()
        # generate_recommendations does not define a separate machine-readable
        # identifier for these tier-1 entries; the 'type' key holds the
        # human-readable label used for display. Assert on that real key.
        types = {r.get("type") for r in recs}
        assert "Cache de VS Code" in types, f"missing vscode rec, got {types}"
        assert "Cache de npm" in types, f"missing npm rec, got {types}"

    def test_categorize_cache_labels_are_covered(self):
        # Guard: every label that generate_recommendations filters on
        # must be producible by categorize_cache.
        assert self.core.categorize_cache(Path("/Users/x/Library/Caches/Code")) == "VS Code Cache"
        assert self.core.categorize_cache(Path("/Users/x/.npm")) == "NPM Cache"
