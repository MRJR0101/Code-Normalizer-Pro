"""Compatibility shim — the real implementation has moved to engine/*.

This file exists so that:
  - ``from code_normalizer_pro import code_normalizer_pro as cnp`` keeps working
  - ``python code_normalizer_pro/code_normalizer_pro.py`` (runpy path in main.py) keeps working
  - The pre-commit hook (which embeds this path) keeps working

Nothing should import from this module in new code.  Import from the engine
sub-packages directly instead.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# sys.path bootstrap for direct-script execution
# ---------------------------------------------------------------------------
# When the hook runs this file directly (python .../code_normalizer_pro.py),
# Python adds the file's *directory* to sys.path, not the project root.
# That makes ``from code_normalizer_pro.engine.*`` fail because
# ``code_normalizer_pro`` resolves to this script instead of the package.
# Inserting the project root (one level up) ensures package imports resolve
# correctly whether this file is run as a script OR imported as a module.
import sys as _sys
from pathlib import Path as _Path

_project_root = str(_Path(__file__).resolve().parent.parent)
if _project_root not in _sys.path:
    _sys.path.insert(0, _project_root)

# ---------------------------------------------------------------------------
# Module-level names exposed for tests that monkeypatch via ``cnp.X``
# ---------------------------------------------------------------------------
# Tests do things like ``monkeypatch.setattr(cnp.os, "replace", ...)`` which
# patches the singleton module object — so the patch is visible everywhere
# os.replace is called, regardless of which engine module actually calls it.
import mmap
import os
import subprocess

from loguru import logger

# ---------------------------------------------------------------------------
# Re-export everything the old monolith exposed
# ---------------------------------------------------------------------------

from code_normalizer_pro.engine.reporter import (
    ProcessStats,
    print_summary,
    generate_reports,
)
from code_normalizer_pro.engine.cache import (
    FileCache,
    CacheManager,
    CACHE_FILE,
    CACHE_SCHEMA_VERSION,
)
from code_normalizer_pro.engine.checkers import (
    SYNTAX_CHECKERS,
    run_syntax_check,
    register as register_checker,
    unregister as unregister_checker,
)
from code_normalizer_pro.engine.telemetry import (
    TelemetryManager,
    TELEMETRY_FILE,
)
from code_normalizer_pro.engine.walker import (
    _is_in_git_repo,
    install_git_hook,
)
from code_normalizer_pro.engine.normalizer import (
    CodeNormalizer,
    COMMON_ENCODINGS,
    DEFAULT_EXCLUDE_DIRS,
    _init_worker,
    process_file_worker,
)
from code_normalizer_pro.cli import (
    app,
    cli_main,
    main,
    _version_callback,
    __version__,
)

__all__ = [
    # Data structures
    "ProcessStats",
    "FileCache",
    # Engine
    "CacheManager",
    "CodeNormalizer",
    # Constants
    "SYNTAX_CHECKERS",
    "CACHE_FILE",
    "CACHE_SCHEMA_VERSION",
    "COMMON_ENCODINGS",
    "DEFAULT_EXCLUDE_DIRS",
    # Utilities
    "install_git_hook",
    "_is_in_git_repo",
    "run_syntax_check",
    "register_checker",
    "unregister_checker",
    # Telemetry
    "TelemetryManager",
    "TELEMETRY_FILE",
    "print_summary",
    "generate_reports",
    "_init_worker",
    "process_file_worker",
    # CLI
    "app",
    "cli_main",
    "main",
    "_version_callback",
    "__version__",
    # Module references (for monkeypatching in tests)
    "logger",
    "os",
    "mmap",
    "subprocess",
]

if __name__ == "__main__":
    main()
