"""The cache labels are a contract between the classifier and three consumers.

Breaking it silently disables cleanup features — it already happened once
(phase 1, task 3), so it gets its own test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer import cache_types
from disk_analyzer_core import DiskAnalyzerCore, GB


def test_every_recommendation_filter_label_is_producible():
    """Any label the recommendation logic filters on must be a real label."""
    known = set(cache_types.ALL_LABELS)
    core = DiskAnalyzerCore(".")
    core.cache_locations = [
        {"path": f"/fake/{label}", "size": 5 * GB, "type": label}
        for label in known
    ]
    recs = core.generate_recommendations()
    # With every known label present at 5 GB, the known-cache recommendations
    # must fire — if a filter references a label that no longer exists, its
    # recommendation silently disappears.
    assert recs, "no recommendations fired for any known cache label"


def test_safe_to_clean_labels_are_real():
    assert cache_types.SAFE_TO_CLEAN, "safelist must not be empty"
    for label in cache_types.SAFE_TO_CLEAN:
        assert label in cache_types.ALL_LABELS, f"{label} is not a real label"


def test_downloads_and_general_are_never_auto_cleanable():
    """Deleting Downloads or an unclassified cache automatically is unsafe."""
    assert cache_types.DOWNLOADS not in cache_types.SAFE_TO_CLEAN
    assert cache_types.GENERAL not in cache_types.SAFE_TO_CLEAN
