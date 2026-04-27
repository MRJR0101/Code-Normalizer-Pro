"""ConfigLoader: merge pyproject.toml → env vars → CLI flags.

Merge priority (highest wins):
  CLI flags  >  environment variables  >  pyproject.toml  >  built-in defaults

Usage::

    cfg = ConfigLoader.from_pyproject().apply_env()
    ext = cfg.get("ext", [".py"])

Supported environment variables
--------------------------------
CNP_EXT              Comma-separated extensions, e.g. ".py,.js"
CNP_WORKERS          Integer worker count
CNP_EXPAND_TABS      Tab width (0 = disabled)
CNP_MAX_LINES        Max lines per file (0 = unlimited)
CNP_LOG_FILE         Path to log file
CNP_COMPRESS_LOGS    "1" / "true" / "yes" to enable
CNP_NO_BACKUP        "1" / "true" / "yes" to enable
CNP_PARALLEL         "1" / "true" / "yes" to enable
CNP_SYNTAX_TIMEOUT   Integer seconds
CNP_TELEMETRY        "1" / "true" / "yes" to opt in
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, Any] = {
    "ext": [".py"],
    "workers": None,
    "expand_tabs": 0,
    "max_lines": 0,
    "log_file": None,
    "compress_logs": False,
    "no_backup": False,
    "parallel": False,
    "respect_gitignore": True,
    "syntax_timeout": 10,
    "telemetry": False,
}

# (env_var, config_key, transform)
_ENV_MAP: Tuple[Tuple[str, str, Callable], ...] = (
    ("CNP_EXT",            "ext",            lambda v: [e.strip() for e in v.split(",") if e.strip()]),
    ("CNP_WORKERS",        "workers",        int),
    ("CNP_EXPAND_TABS",    "expand_tabs",    int),
    ("CNP_MAX_LINES",      "max_lines",      int),
    ("CNP_LOG_FILE",       "log_file",       str),
    ("CNP_COMPRESS_LOGS",  "compress_logs",  lambda v: v.lower() in ("1", "true", "yes")),
    ("CNP_NO_BACKUP",      "no_backup",      lambda v: v.lower() in ("1", "true", "yes")),
    ("CNP_PARALLEL",       "parallel",       lambda v: v.lower() in ("1", "true", "yes")),
    ("CNP_SYNTAX_TIMEOUT", "syntax_timeout", int),
    ("CNP_TELEMETRY",      "telemetry",      lambda v: v.lower() in ("1", "true", "yes")),
)


# ---------------------------------------------------------------------------
# ConfigLoader
# ---------------------------------------------------------------------------

class ConfigLoader:
    """Load and merge configuration from pyproject.toml and environment variables.

    Typical usage in cli.py::

        cfg = ConfigLoader.from_pyproject().apply_env()
        ext = ext or cfg.get("ext", [".py"])
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
    # Env var overlay
    # ------------------------------------------------------------------

    def apply_env(self) -> "ConfigLoader":
        """Overlay CNP_* environment variables (higher priority than pyproject.toml).

        Returns *self* for chaining::

            cfg = ConfigLoader.from_pyproject().apply_env()
        """
        for env_key, cfg_key, transform in _ENV_MAP:
            val = os.environ.get(env_key)
            if val is not None:
                try:
                    self._data[cfg_key] = transform(val)
                except Exception:
                    pass
        return self

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
