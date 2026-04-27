"""Runtime settings loaded from environment variables.

STATUS: Not yet integrated into the CLI (v3.x uses pyproject.toml for configuration).
This module is a planned enhancement for a future env-var configuration layer (v4.x).
To activate: call load_settings() at the top of cli_main() and use the returned
Settings object to override CLI defaults before the pyproject.toml config block runs.

Environment variables (see .env.example for defaults):
  APP_DEBUG, APP_ENV, DEFAULT_EXTENSIONS, ENABLE_PARALLEL, LOG_DIR, OUTPUT_DIR
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Strongly-typed project configuration."""

    app_name: str
    app_env: str
    app_debug: bool
    project_root: Path
    log_dir: Path
    output_dir: Path
    default_extensions: tuple[str, ...]
    enable_parallel: bool


def _parse_bool(value: str, default: bool = False) -> bool:
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_extensions(value: str) -> tuple[str, ...]:
    if not value:
        return (".py",)
    items = [item.strip() for item in value.split(",") if item.strip()]
    return tuple(items) if items else (".py",)


def load_settings() -> Settings:
    """Load settings from environment with safe defaults."""
    project_root = Path(os.getenv("PROJECT_ROOT", ".")).resolve()
    return Settings(
        app_name=os.getenv("APP_NAME", "code-normalizer-pro"),
        app_env=os.getenv("APP_ENV", "development"),
        app_debug=_parse_bool(os.getenv("APP_DEBUG", ""), default=False),
        project_root=project_root,
        log_dir=project_root / os.getenv("LOG_DIR", "logs"),
        output_dir=project_root / os.getenv("OUTPUT_DIR", "files"),
        default_extensions=_parse_extensions(os.getenv("DEFAULT_EXTENSIONS", ".py")),
        enable_parallel=_parse_bool(os.getenv("ENABLE_PARALLEL", "true"), default=True),
    )

