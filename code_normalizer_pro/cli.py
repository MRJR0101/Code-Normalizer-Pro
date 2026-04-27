"""Console entry point: Typer CLI application for code-normalizer-pro.

This module owns the CLI surface only — argument parsing, config merging, logger
setup, and orchestration calls.  All normalization logic lives in engine/*.
"""

from __future__ import annotations

import os
import sys
from multiprocessing import cpu_count
from pathlib import Path
from typing import List, Optional, Set

import typer
from loguru import logger

from code_normalizer_pro.engine.cache import CACHE_FILE
from code_normalizer_pro.engine.normalizer import (
    CodeNormalizer,
    DEFAULT_EXCLUDE_DIRS,
)
from code_normalizer_pro.engine.walker import _is_in_git_repo, install_git_hook

# Version — importlib.metadata avoids circular import when run as a script
try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("code-normalizer-pro")
except Exception:
    __version__ = "unknown"

# Fix Windows console encoding so UTF-8 output doesn't crash on cp1252 terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"


# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

def _version_callback(value: bool) -> None:
    if value:
        print(f"code-normalizer-pro {__version__}")
        raise typer.Exit()


app = typer.Typer(
    help="Code Normalizer Pro - Production-grade normalization tool",
    add_completion=False,
)


@app.command()
def cli_main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True,
        help="Show version and exit",
    ),
    path: Optional[Path] = typer.Argument(None, help="File or directory to process"),
    ext: Optional[List[str]] = typer.Option(None, "-e", "--ext", help="File extensions (e.g. -e .py -e .js)"),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output file (single file mode only)"),
    check: bool = typer.Option(False, "--check", help="Run syntax check on normalized output"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without modifying files"),
    in_place: bool = typer.Option(False, "--in-place", help="Edit files in-place"),
    no_backup: bool = typer.Option(False, "--no-backup", help="Don't create backups (dangerous!)"),
    cache: bool = typer.Option(True, "--cache/--no-cache", help="Enable/disable incremental processing cache"),
    interactive: bool = typer.Option(False, "--interactive", help="Interactive mode (approve each file)"),
    parallel: bool = typer.Option(False, "--parallel", help="Parallel processing (multi-core)"),
    workers: Optional[int] = typer.Option(None, help=f"Number of parallel workers (default: {max(1, cpu_count() - 1)})"),
    exclude: Optional[List[str]] = typer.Option(None, "--exclude", help="Directory name to exclude from walks"),
    no_default_excludes: bool = typer.Option(False, "--no-default-excludes", help="Disable the built-in exclusion set"),
    syntax_timeout: int = typer.Option(10, "--timeout", "--syntax-timeout", help="Timeout per file for --check validation"),
    report_json: Optional[Path] = typer.Option(None, "--report-json", help="Generate a JSON report of the stats"),
    report_html: Optional[Path] = typer.Option(None, "--report-html", help="Generate an HTML report of the stats"),
    expand_tabs: int = typer.Option(0, "--expand-tabs", help="Convert leading and inline tabs to N spaces"),
    max_lines: int = typer.Option(0, "--max-lines", help="Skip files exceeding N lines"),
    no_gitignore: bool = typer.Option(False, "--no-gitignore", help="Do not skip files ignored by .gitignore"),
    install_hook: bool = typer.Option(False, "--install-hook", help="Install git pre-commit hook"),
    log_file: Optional[Path] = typer.Option(None, "--log-file", help="Save execution logs to a file"),
    compress_logs: bool = typer.Option(False, "--compress-logs", help="Compress rotated log files (.gz)"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output"),
    fail_on_changes: bool = typer.Option(False, "--fail-on-changes", help="Exit 1 when --dry-run finds files that need normalization (useful for CI pipelines)"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation prompts (for CI/scripting; also overrides --no-backup git-repo guard)"),
) -> None:

    # ------------------------------------------------------------------
    # pyproject.toml config merging
    # ------------------------------------------------------------------
    cfg: dict = {}
    try:
        pyproj = Path("pyproject.toml")
        if pyproj.exists():
            if sys.version_info >= (3, 11):
                import tomllib
                with open(pyproj, "rb") as f:
                    cfg = tomllib.load(f).get("tool", {}).get("code-normalizer-pro", {})
            else:
                try:
                    import tomli
                    with open(pyproj, "rb") as f:
                        cfg = tomli.load(f).get("tool", {}).get("code-normalizer-pro", {})
                except ImportError:
                    pass
    except Exception as e:
        logger.warning(f"Could not parse pyproject.toml config: {e}")

    ext = ext or cfg.get("ext", [".py"])
    workers = workers or cfg.get("workers", max(1, cpu_count() - 1))
    expand_tabs = expand_tabs or cfg.get("expand_tabs", 0)
    max_lines = max_lines or cfg.get("max_lines", 0)

    if log_file is None and cfg.get("log_file"):
        log_file = Path(cfg.get("log_file"))
    compress_logs = compress_logs or cfg.get("compress_logs", False)

    # ------------------------------------------------------------------
    # Logger setup
    # ------------------------------------------------------------------
    logger.remove()
    logger.add(sys.stdout, format="{message}", level="DEBUG" if verbose else "INFO")

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
            level="DEBUG" if verbose else "INFO",
            rotation="5 MB",
            retention=3,
            compression="gz" if compress_logs else None,
            enqueue=True,
        )

    # ------------------------------------------------------------------
    # Install-hook shortcut
    # ------------------------------------------------------------------
    if install_hook:
        success = install_git_hook()
        sys.exit(0 if success else 1)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    if not path:
        logger.error("Missing argument 'PATH'. Run with --help for usage.")
        sys.exit(1)

    if output and path.is_dir():
        logger.error("--output only works with single file")
        sys.exit(1)

    if no_backup and not in_place:
        logger.warning("--no-backup has no effect without --in-place")

    if no_backup and in_place and not yes and not _is_in_git_repo(path):
        logger.error(
            "[X] --no-backup outside a git repo risks permanent data loss.\n"
            "    Commit your files to git first, or pass --yes to override."
        )
        sys.exit(1)

    if interactive and parallel:
        logger.warning("--interactive disables --parallel")
        parallel = False

    exclude_dirs: Set[str]
    if no_default_excludes:
        exclude_dirs = set(exclude or [])
    else:
        exclude_dirs = set(DEFAULT_EXCLUDE_DIRS) | set(exclude or [])

    # ------------------------------------------------------------------
    # Normalizer instantiation
    # ------------------------------------------------------------------
    normalizer = CodeNormalizer(
        dry_run=dry_run,
        verbose=verbose,
        in_place=in_place,
        create_backup=not no_backup,
        use_cache=cache,
        interactive=interactive,
        parallel=parallel,
        max_workers=workers,
        cache_path=(path / CACHE_FILE) if path and path.is_dir() else (path.parent / CACHE_FILE),
        exclude_dirs=exclude_dirs,
        syntax_timeout=syntax_timeout,
        report_json=report_json,
        report_html=report_html,
        expand_tabs=expand_tabs,
        max_lines=max_lines,
        respect_gitignore=not no_gitignore,
        log_file=log_file,
        auto_confirm=yes,
    )

    logger.info("=" * 70)
    logger.info(f"CODE NORMALIZER PRO v{__version__}")
    logger.info("=" * 70)

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    try:
        if path.is_dir():
            normalizer.walk_and_process(path, ext, check_syntax=check)
        else:
            if not path.exists():
                logger.error(f"File not found: {path}")
                sys.exit(1)
            normalizer.process_file(path, output, check_syntax=check)

        normalizer.print_summary()
        normalizer.generate_reports()

        if fail_on_changes and normalizer.stats.processed > 0:
            sys.exit(1)
        sys.exit(0 if normalizer.stats.errors == 0 else 1)

    except KeyboardInterrupt:
        logger.warning("\n\n[!] Interrupted by user")
        try:
            if normalizer.use_cache and normalizer.cache and not normalizer.dry_run:
                normalizer.cache.save()
                logger.info("[i] Partial cache saved; next run will resume")
        except Exception as save_err:
            logger.error(f"[!] Could not save cache on interrupt: {save_err}")
        normalizer.print_summary()
        normalizer.generate_reports()
        sys.exit(130)

    except Exception as e:
        logger.error(f"\n[X] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        try:
            if normalizer.use_cache and normalizer.cache and not normalizer.dry_run:
                normalizer.cache.save()
        except Exception:
            pass
        sys.exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
