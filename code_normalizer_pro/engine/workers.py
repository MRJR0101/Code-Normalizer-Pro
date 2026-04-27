"""ProcessPoolExecutor worker functions for parallel file processing.

Both functions must be at module level (picklable) for ProcessPoolExecutor.
``CodeNormalizer`` is imported lazily inside ``process_file_worker`` to avoid
a circular import: workers.py → normalizer.py → workers.py.
"""

from __future__ import annotations

import traceback as _traceback
from pathlib import Path
from typing import Optional, Tuple

from loguru import logger


def _init_worker(log_file: Optional[Path]) -> None:
    """ProcessPoolExecutor initializer: configure the log sink once per worker process.

    Runs at worker startup regardless of how many files the worker handles.
    Using the initializer (not a per-call global) is correct on both Windows
    (spawn) and Linux/macOS (fork) start methods.
    """
    if log_file:
        logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
            level="INFO",
            enqueue=True,
        )


def process_file_worker(
    file_path: Path,
    dry_run: bool,
    in_place: bool,
    create_backup: bool,
    check_syntax: bool,
    syntax_timeout: int = 10,
    expand_tabs: int = 0,
    max_lines: int = 0,
) -> Tuple[bool, dict, str]:
    """Normalize a single file in a worker process (log sink set up by _init_worker)."""
    try:
        # Lazy import avoids the circular dependency at module load time.
        from code_normalizer_pro.engine.normalizer import CodeNormalizer

        normalizer = CodeNormalizer(
            dry_run=dry_run,
            in_place=in_place,
            create_backup=create_backup,
            use_cache=False,
            interactive=False,
            parallel=False,
            syntax_timeout=syntax_timeout,
            expand_tabs=expand_tabs,
            max_lines=max_lines,
        )

        success = normalizer.process_file(file_path, check_syntax=check_syntax)

        stats_update = {
            "processed": normalizer.stats.processed,
            "skipped": normalizer.stats.skipped,
            "encoding_changes": normalizer.stats.encoding_changes,
            "newline_fixes": normalizer.stats.newline_fixes,
            "whitespace_fixes": normalizer.stats.whitespace_fixes,
            "bytes_removed": normalizer.stats.bytes_removed,
            "syntax_checks_passed": normalizer.stats.syntax_checks_passed,
            "syntax_checks_failed": normalizer.stats.syntax_checks_failed,
        }

        error = normalizer.errors[0][1] if normalizer.errors else ""
        return success, stats_update, error

    except Exception:
        tb_str = _traceback.format_exc()
        empty_stats = {
            "processed": 0, "skipped": 0, "encoding_changes": 0,
            "newline_fixes": 0, "whitespace_fixes": 0, "bytes_removed": 0,
            "syntax_checks_passed": 0, "syntax_checks_failed": 0,
        }
        return False, empty_stats, f"Worker Crash:\n{tb_str}"
