"""Tests for the shared protection module (analyzer/protection.py).

`is_protected_path` used to be duplicated verbatim in DiskAnalyzer and
DiskAnalyzerCore. It now lives as a free function in analyzer/protection.py,
with both classes delegating a one-line method to it. This file owns
protection testing: it checks the free function directly, and checks that
both class methods still agree with it (regression guard for the delegation).

See tests/test_engine_characterization.py::TestProtectedPaths for the
pre-existing table of behaviors pinned against DiskAnalyzerCore.is_protected_path
-- that class is not duplicated here.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer.protection import is_protected_path
from disk_analyzer_core import DiskAnalyzerCore
from disk_analyzer import DiskAnalyzer


class TestFreeFunctionMatchesMethods:
    """Both classes must delegate to the free function without drift."""

    @pytest.mark.parametrize("path", [
        "/System/Library/x",
        "/bin",
        "/sbin",
        "/usr/lib/libSystem.dylib",
        "/Applications/Foo.app/Contents/MacOS/Foo",
        "/private/var/vm/sleepimage",
        str(Path.home() / "Downloads/a.mp4"),
        str(Path.home() / "Library/Caches/something"),
    ])
    def test_core_method_matches_free_function(self, path):
        core = DiskAnalyzerCore(".")
        assert core.is_protected_path(path) == is_protected_path(path)

    @pytest.mark.parametrize("path", [
        "/System/Library/x",
        "/bin",
        "/Applications/Foo.app/Contents/MacOS/Foo",
        str(Path.home() / "Downloads/a.mp4"),
    ])
    def test_cli_method_matches_free_function(self, path):
        analyzer = DiskAnalyzer(".")
        assert analyzer.is_protected_path(path) == is_protected_path(path)


class TestFreeFunctionBehaviors:
    """Direct assertions against the free function, independent of any class."""

    @pytest.mark.parametrize("path", [
        "/System/Library/Kernels/kernel",
        "/usr/lib/libSystem.dylib",
        "/private/var/vm/sleepimage",
    ])
    def test_system_prefixes_are_protected(self, path):
        assert is_protected_path(path) is True

    @pytest.mark.parametrize("path", ["/bin", "/sbin"])
    def test_root_dirs_are_protected(self, path):
        assert is_protected_path(path) is True

    def test_app_contents_marker_is_protected(self):
        assert is_protected_path("/Applications/Foo.app/Contents/MacOS/Foo") is True

    @pytest.mark.parametrize("filename", ["sleepimage", "swapfile"])
    def test_protected_filenames_anywhere(self, filename):
        assert is_protected_path(str(Path.home() / "somewhere" / filename)) is True

    def test_normal_user_file_is_not_protected(self):
        assert is_protected_path(str(Path.home() / "Downloads" / "movie.mp4")) is False


class TestCaseInsensitivity:
    """APFS no distingue mayúsculas de minúsculas por defecto: '/bin' y
    '/BIN' son el mismo directorio. Verificado que, antes de este fix,
    `/BIN` no lo capturaba `PROTECTED_ROOT_DIRS` (comparación case-sensitive
    contra {'/bin', '/sbin'}), y como ni '/bin' ni '/sbin' están en
    RUTAS_DE_DATOS_DE_USUARIO, `puede_borrarse('/BIN')` caía en su
    `return True` final -- en un filesystem que no distingue caja, eso es
    literalmente /bin.
    """

    @pytest.mark.parametrize("path", ["/BIN", "/Bin", "/bIn/ls", "/SBIN"])
    def test_root_dirs_protected_regardless_of_case(self, path):
        assert is_protected_path(path) is True

    @pytest.mark.parametrize("path", [
        "/system/library/x",
        "/SYSTEM/LIBRARY/X",
        "/System/library",   # el directorio en sí, sin barra final, caja mixta
        "/SYSTEM/LIBRARY",
    ])
    def test_system_prefixes_protected_regardless_of_case(self, path):
        assert is_protected_path(path) is True

    @pytest.mark.parametrize("path", [
        "/Applications/Foo.APP/Contents/MacOS/Foo",
        "/Applications/Foo.app/CONTENTS/MacOS/Foo",
        "/APPLICATIONS/FOO.APP/CONTENTS/MACOS/FOO",
    ])
    def test_app_contents_marker_protected_regardless_of_case(self, path):
        assert is_protected_path(path) is True

    @pytest.mark.parametrize("filename", ["SLEEPIMAGE", "SwapFile"])
    def test_protected_filenames_protected_regardless_of_case(self, filename):
        assert is_protected_path(str(Path.home() / "somewhere" / filename)) is True
