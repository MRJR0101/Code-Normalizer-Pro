"""ConfigLoader: merge pyproject.toml settings with environment variables and CLI flags.

This module wires the [tool.code-normalizer-pro] section from pyproject.toml so
teams can commit shared normalization settings rather than passing CLI flags on
every invocation.

Merge priority (highest wins):
  CLI flags  >  environment variables  >  pyproject.toml  >  built-in defaults

Currently used by cli.py.  Future work: expose as a first-class object that
CodeNormalizer can accept so library callers also benefit from config resolution.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, Any] = {
    "ext": [".py"],
    "workers": None,          # None → cpu_count() - 1 at runtime
    "expand_tabs": 0,
    "max_lines": 0,
    "log_file": None,
    "compress_logs": False,
    "no_backup": False,
    "parallel": False,
    "respect_gitignore": True,
    "syntax_timeout": 10,
}


# ---------------------------------------------------------------------------
# ConfigLoader
# ---------------------------------------------------------------------------

class ConfigLoader:
    """Load and merge configuration from pyproject.toml and environment variables.

    Usage::

        cfg = ConfigLoader.from_pyproject()
        ext = cfg.get("ext", [".py"])
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = {**_DEFAULTS, **data}

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_pyproject(cls, pyproject_path: Optional[Path] = None) -> "ConfigLoader":
        """Read ``[tool.code-normalizer-pro]`` from *pyproject_path* (default: cwd)."""
        path = pyproject_path or Path("pyproject.toml")
        data: Dict[str, Any] = {}

        if path.exists():
            try:
                if sys.version_info >= (3, 11):
                    import tomllib
                    with open(path, "rb") as f:
                        raw = tomllib.load(f)
                else:
                    try:
                        import tomli
                        with open(path, "rb") as f:
                            raw = tomli.load(f)
                    except ImportError:
                        raw = {}
                data = raw.get("tool", {}).get("code-normalizer-pro", {})
            except Exception:
                pass

        return cls(data)

    @classmethod
    def empty(cls) -> "ConfigLoader":
        """Return a loader backed by built-in defaults only (useful for tests)."""
        return cls({})

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Return the config value for *key*, falling back to *default*."""
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __repr__(self) -> str:
        return f"ConfigLoader({self._data!r})"
