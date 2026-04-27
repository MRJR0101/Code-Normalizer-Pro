"""Opt-in local usage telemetry — counts only, no network, no file content.

Enable via any of:
  CLI flag:  --telemetry
  Config:    [tool.code-normalizer-pro] telemetry = true
  Env var:   CNP_TELEMETRY=1

View stats:  code-normalizer-pro --telemetry-report
Reset stats: code-normalizer-pro --telemetry-reset

What is recorded (locally only):
  - Total number of invocations
  - Total files processed
  - Total bytes removed
  - Total errors encountered
  - Timestamp of last run
  - Tool version

What is NEVER recorded:
  - File names or paths
  - File contents
  - Any personally identifiable information
  - Anything sent over the network
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Use platformdirs when available; fall back to ~/.config for minimal deps
try:
    from platformdirs import user_config_dir as _user_config_dir
    _BASE = Path(_user_config_dir("code-normalizer-pro"))
except ImportError:
    _BASE = Path.home() / ".config" / "code-normalizer-pro"

TELEMETRY_FILE: Path = _BASE / "telemetry.json"


class TelemetryManager:
    """Manages opt-in local usage statistics.

    Usage in cli.py::

        tm = TelemetryManager(enabled=telemetry_flag)
        # ... after run ...
        tm.record(
            files_processed=normalizer.stats.processed,
            bytes_removed=normalizer.stats.bytes_removed,
            errors=normalizer.stats.errors,
            version=__version__,
        )
    """

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._data: dict = {}

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        files_processed: int,
        bytes_removed: int,
        errors: int,
        version: str,
    ) -> None:
        """Append one invocation's stats to the local counter file."""
        if not self.enabled:
            return
        self._load()
        self._data["total_runs"] = self._data.get("total_runs", 0) + 1
        self._data["total_files_processed"] = (
            self._data.get("total_files_processed", 0) + files_processed
        )
        self._data["total_bytes_removed"] = (
            self._data.get("total_bytes_removed", 0) + bytes_removed
        )
        self._data["total_errors"] = self._data.get("total_errors", 0) + errors
        self._data["last_run"] = datetime.now(timezone.utc).isoformat()
        self._data["version"] = version
        self._save()

    def report(self) -> str:
        """Return a human-readable summary of recorded stats."""
        self._load(force=True)
        if not self._data:
            return (
                "No telemetry data recorded yet.\n"
                "Run with --telemetry to start collecting local usage stats."
            )
        lines = [
            "Code Normalizer Pro — Local Telemetry Report",
            "─" * 46,
            f"  Total runs:            {self._data.get('total_runs', 0):,}",
            f"  Total files processed: {self._data.get('total_files_processed', 0):,}",
            f"  Total bytes removed:   {self._data.get('total_bytes_removed', 0):,}",
            f"  Total errors:          {self._data.get('total_errors', 0):,}",
            f"  Last run:              {self._data.get('last_run', 'never')}",
            f"  Version:               {self._data.get('version', 'unknown')}",
            "",
            f"  Stored at: {TELEMETRY_FILE}",
        ]
        return "\n".join(lines)

    def reset(self) -> None:
        """Erase all recorded telemetry data."""
        self._data = {}
        self._save()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self, force: bool = False) -> None:
        """Load from disk (no-op if not enabled, unless *force* is True)."""
        if not (self.enabled or force):
            return
        if TELEMETRY_FILE.exists():
            try:
                self._data = json.loads(
                    TELEMETRY_FILE.read_text(encoding="utf-8")
                )
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        try:
            TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
            TELEMETRY_FILE.write_text(
                json.dumps(self._data, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
