"""Cache category labels and classification.

These label strings are a contract: the classifier produces them, and
generate_recommendations (CLI and core), clean_cache's safelist and the web
cleanup endpoint all match on them. Changing a string without updating every
consumer silently disables a cleanup feature.

Ported from DiskAnalyzerCore.categorize_cache (disk_analyzer_core.py), which
both DiskAnalyzer.classify_cache (CLI) and DiskAnalyzerCore.categorize_cache
now delegate to (Task 4 of the shared-engine refactor).
"""
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
# This is an exact translation of the CLI's pre-unification clean_cache
# safelist ({'Logs del Sistema', 'VS Code', 'Node.js/npm', 'Xcode Development',
# 'Python Cache'}) to the unified label set -- same five categories, no more,
# no fewer. In particular TEMP ('Archivos Temporales') is deliberately
# excluded: it's a core-only category the old CLI safelist never included, and
# adding a new category to a safelist that deletes files is a behavior change
# that must not happen silently as a side effect of this refactor.
SAFE_TO_CLEAN = frozenset({LOGS, VSCODE, NPM, XCODE, PYTHON})


def classify(path: Path) -> str:
    """Classify a cache location by path. Order matters: first match wins.

    'xcode' is checked before 'code'/'vscode' -- "xcode" contains the
    substring "code", so checking the VS Code pattern first would make every
    Xcode path (e.g. .../Library/Developer/Xcode/DerivedData) match VS Code
    Cache and leave the Xcode branch unreachable. This was a real bug in
    DiskAnalyzerCore.categorize_cache prior to unification (see
    task-4-report.md); fixed here by moving the more specific pattern first.
    All other branch precedence is preserved verbatim from the core's
    original categorize_cache.
    """
    path_str = str(path).lower()

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
