# tests/conftest.py
import os
import pytest


@pytest.fixture(autouse=True)
def _default_no_auth(monkeypatch, request):
    # test_auth.py manages its own auth env explicitly; leave it alone.
    if request.module.__name__.endswith("test_auth"):
        return
    monkeypatch.setenv("DISK_ANALYZER_NO_AUTH", "1")

    # Setting the env var alone is not enough: test_cleanup_api.py and
    # test_terminal_api.py import disk_analyzer_web directly at module scope
    # (no importlib.reload), and that import can happen during pytest's
    # collection phase -- before this fixture ever runs -- so NO_AUTH/AUTH_TOKEN
    # get frozen from whatever the env was at collection time (often unset).
    # test_auth.py's importlib.reload() later mutates the *same* module
    # namespace in place (module objects are cached in sys.modules and reload
    # re-executes into the existing __dict__), so relying on env-var timing
    # alone makes the whole suite's outcome depend on which test happened to
    # run last and in what order -- verified by running test_cleanup_api.py /
    # test_terminal_api.py in isolation, which failed with 401s under the
    # env-only approach. Patching the module's globals directly here removes
    # that ordering dependency.
    import disk_analyzer_web
    monkeypatch.setattr(disk_analyzer_web, "NO_AUTH", True, raising=False)
    monkeypatch.setattr(disk_analyzer_web, "AUTH_TOKEN", None, raising=False)
