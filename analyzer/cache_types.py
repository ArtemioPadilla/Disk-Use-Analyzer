"""Cache category labels and classification.

These label strings are a contract: the classifier produces them, and
generate_recommendations (CLI and core), clean_cache's safelist and the web
cleanup endpoint all match on them. Changing a string without updating every
consumer silently disables a cleanup feature.

Ported from DiskAnalyzerCore.categorize_cache (disk_analyzer_core.py), which
both DiskAnalyzer.classify_cache (CLI) and DiskAnalyzerCore.categorize_cache
now delegate to (Task 4 of the shared-engine refactor).
"""
import os
from pathlib import Path

DOCKER = 'Docker'
XCODE = 'Xcode Cache'
VSCODE = 'VS Code Cache'
NPM = 'NPM Cache'
PYTHON = 'Python Cache'
CHROME = 'Chrome Cache'
FIREFOX = 'Firefox Cache'
TRASH = 'Papelera'
TEMP = 'Archivos Temporales'
LOGS = 'Logs del Sistema'
DOWNLOADS = 'Downloads'
GENERAL = 'Cache General'

ALL_LABELS = (
    DOCKER, XCODE, VSCODE, NPM, PYTHON, CHROME, FIREFOX,
    TRASH, TEMP, LOGS, DOWNLOADS, GENERAL,
)

# Categories safe to delete without human review. Downloads holds user data and
# GENERAL is by definition unclassified, so neither is ever auto-cleanable.
#
# This restores true behavioral parity with what the old CLI actually DID,
# not with what its dead safelist text said. The pre-unification clean_cache
# safelist was {'Logs del Sistema', 'VS Code', 'Node.js/npm',
# 'Xcode Development', 'Python Cache'} -- but the old CLI's classify_cache
# had no python-specific branch, so it never produced 'Python Cache' for
# anything; python paths always fell through to 'Cache General' and were
# never cleaned. Now that PYTHON is a real, reachable label (from the
# unified classifier), including it here would newly enable actual deletion
# of python caches -- and clean_cache's directory branch does a permanent
# rglob().unlink(), not a move to Trash (see task-4-report.md, "Fix round
# 1"), so this would be irreversible. That's a real behavior change and is
# deliberately deferred to an explicit owner decision, not introduced as a
# side effect of this refactor. Do not add PYTHON back without that decision
# -- see the test that pins its absence in tests/test_cache_labels.py.
#
# TEMP ('Archivos Temporales') is excluded for the same reason: it's a
# core-only category the old CLI safelist never included at all.
SAFE_TO_CLEAN = frozenset({LOGS, VSCODE, NPM, XCODE})


def _sin_nombre_de_usuario(path_str: str) -> str:
    """Strips the home directory -- and with it, the username -- from a path
    before classification looks at it.

    `classify` matches on substrings of the *whole* lowercased path. A
    macOS home directory is `/Users/<username>`, so before this stripping a
    username that happens to contain 'log', 'code' or 'node' (e.g. 'logan',
    'nicode', 'anode') made every single path under that user's home --
    including `~/Downloads` -- match LOGS/VSCODE/NPM respectively, landing
    it in SAFE_TO_CLEAN. Verified: user 'logan' -> `~/Downloads` classified
    as LOGS.

    Two strategies, tried in order:
    1. Strip the real `$HOME` prefix, if the path is under it (covers the
       common case, including non-`/Users` homes).
    2. Generic fallback: if the path looks like `/Users/<name>/...` or
       `/home/<name>/...` (a synthetic username that isn't the real $HOME,
       as in tests and in multi-user scans), drop that two-component
       prefix too.

    Classification then runs on what's left -- 'Library/Logs', '.npm', etc
    -- never on the username itself.
    """
    partes = Path(path_str).parts
    home_partes = Path(os.path.expanduser('~')).parts
    if len(partes) >= len(home_partes) and partes[:len(home_partes)] == home_partes:
        resto = partes[len(home_partes):]
        return str(Path(*resto)) if resto else ''
    if len(partes) >= 3 and partes[1].lower() in ('users', 'home'):
        resto = partes[3:]
        return str(Path(*resto)) if resto else ''
    return path_str


def classify(path: Path) -> str:
    """Classify a cache location by path. Order matters: first match wins.

    'xcode' is checked before 'code'/'vscode' -- "xcode" contains the
    substring "code", so checking the VS Code pattern first would make every
    Xcode path (e.g. .../Library/Developer/Xcode/DerivedData) match VS Code
    Cache and leave the Xcode branch unreachable. This was a real bug in
    DiskAnalyzerCore.categorize_cache prior to unification (see
    task-4-report.md); fixed here by moving the more specific pattern first.
    The relative order of the other 11 branches is preserved verbatim from
    the core's original categorize_cache. Note this is NOT a no-op for every
    path, though: a path matching both 'xcode' and a later keyword (e.g. an
    Xcode project with node_modules copied into DerivedData, matching both
    'xcode' and 'node') now resolves to XCODE where the pre-fix code would
    have hit that later branch (e.g. NPM) instead. Only single-keyword paths
    are guaranteed unaffected by moving 'xcode' to the front.

    The path is stripped of its home directory (username) before any of
    this matching happens -- see `_sin_nombre_de_usuario`.
    """
    path_str = _sin_nombre_de_usuario(str(path)).lower()

    if 'xcode' in path_str:
        return XCODE
    elif 'code' in path_str or 'vscode' in path_str:
        return VSCODE
    elif 'chrome' in path_str:
        return CHROME
    elif 'firefox' in path_str or 'mozilla' in path_str:
        return FIREFOX
    elif 'npm' in path_str or 'node' in path_str:
        return NPM
    elif 'pip' in path_str or 'python' in path_str:
        return PYTHON
    elif 'docker' in path_str:
        return DOCKER
    elif 'trash' in path_str or 'recycle' in path_str:
        return TRASH
    elif 'temp' in path_str or 'tmp' in path_str:
        return TEMP
    elif 'log' in path_str:
        return LOGS
    elif 'download' in path_str:
        return DOWNLOADS
    else:
        return GENERAL
