"""Core normalizer: CodeNormalizer class.

All heavy logic has been extracted to focused engine modules:
  reader.py        — encoding detection and file reading
  editorconfig.py  — .editorconfig resolution
  text_transform.py — pure text normalization
  fileops.py       — atomic write, backup, output path, interactive diff
  workers.py       — ProcessPoolExecutor worker functions
  walker.py        — directory walk and parallel orchestration

This file wires them together and exposes the public CodeNormalizer API.
"""

from __future__ import annotations

import traceback as _traceback
from multiprocessing import cpu_count
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from loguru import logger

from code_normalizer_pro.engine.cache import CacheManager, CACHE_FILE
from code_normalizer_pro.engine.checkers import SYNTAX_CHECKERS, run_syntax_check
from code_normalizer_pro.engine.editorconfig import EditorConfigResolver
from code_normalizer_pro.engine.fileops import (
    atomic_write,
    create_backup_file,
    get_output_path,
    show_diff,
)
from code_normalizer_pro.engine.reader import (
    COMMON_ENCODINGS,
    guess_and_read as _guess_and_read,
)
from code_normalizer_pro.engine.reporter import ProcessStats, print_summary, generate_reports
from code_normalizer_pro.engine.text_transform import normalize_text as _normalize_text
from code_normalizer_pro.engine.walker import walk_and_process as _walk_and_process
from code_normalizer_pro.engine.workers import _init_worker, process_file_worker

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDE_DIRS: Set[str] = {
    ".venv", "venv", "env", ".env",
    "site-packages", "__pycache__",
    ".git", ".hg", ".svn",
    "node_modules",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache",
    "dist", "build", ".eggs",
}


# ---------------------------------------------------------------------------
# CodeNormalizer
# ---------------------------------------------------------------------------

class CodeNormalizer:
    """Production-grade code normalizer with parallel processing, caching, and
    multi-language syntax checking."""

    def __init__(
        self,
        dry_run: bool = False,
        verbose: bool = False,
        in_place: bool = False,
        create_backup: bool = True,
        use_cache: bool = True,
        interactive: bool = False,
        parallel: bool = False,
        max_workers: Optional[int] = None,
        cache_path: Optional[Path] = None,
        exclude_dirs: Optional[Set[str]] = None,
        syntax_timeout: int = 10,
        report_json: Optional[Path] = None,
        report_html: Optional[Path] = None,
        expand_tabs: int = 0,
        max_lines: int = 0,
        respect_gitignore: bool = True,
        log_file: Optional[Path] = None,
        auto_confirm: bool = False,
    ) -> None:
        self.dry_run = dry_run
        self.verbose = verbose
        self.in_place = in_place
        self.create_backup = create_backup
        self.use_cache = use_cache
        self.interactive = interactive
        self.parallel = parallel
        self.max_workers = max_workers or max(1, cpu_count() - 1)
        self.cache_path_override = cache_path
        self.exclude_dirs: Set[str] = (
            set(exclude_dirs) if exclude_dirs is not None else set(DEFAULT_EXCLUDE_DIRS)
        )
        self.syntax_timeout = max(1, int(syntax_timeout))
        self.report_json = report_json
        self.report_html = report_html
        self.expand_tabs = max(0, int(expand_tabs))
        self.max_lines = max(0, int(max_lines))
        self.respect_gitignore = respect_gitignore
        self.log_file = log_file
        self.auto_confirm = auto_confirm
        self.stats = ProcessStats()
        self.errors: List[Tuple[Path, str]] = []
        self.cache = CacheManager(cache_path) if use_cache and cache_path else None
        self._editorconfig = EditorConfigResolver()

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _resolve_cache_path(self, target: Path) -> Path:
        if self.cache_path_override:
            return self.cache_path_override
        base = target if target.is_dir() else target.parent
        return base / CACHE_FILE

    def _ensure_cache_manager(self, target: Path) -> None:
        if not self.use_cache:
            return
        desired = self._resolve_cache_path(target)
        if self.cache is None or self.cache.cache_path != desired:
            self.cache = CacheManager(desired)

    # ------------------------------------------------------------------
    # Public API — delegating wrappers (kept for backward compatibility)
    # ------------------------------------------------------------------

    def guess_and_read(self, path: Path) -> Tuple[str, str]:
        """Detect encoding and return ``(encoding_name, text)``."""
        return _guess_and_read(path)

    def normalize_text(self, text: str, path: Path) -> Tuple[str, dict]:
        """Normalize *text* and return ``(normalized_text, change_counts)``."""
        tabs_size = self._editorconfig.resolve_indent_size(path, self.expand_tabs)
        return _normalize_text(text, path, tabs_size=tabs_size)

    def _run_syntax_check(
        self, path: Path, content: Optional[str] = None
    ) -> Tuple[bool, str]:
        return run_syntax_check(path, content=content, syntax_timeout=self.syntax_timeout)

    def syntax_check_text(self, path: Path, text: str) -> Tuple[bool, str]:
        return self._run_syntax_check(path, content=text)

    def show_diff(self, path: Path, original: str, normalized: str) -> bool:
        """Show an interactive diff and return True if the user accepts.

        Delegation wrapper kept for backward compatibility and monkeypatching
        in tests (``monkeypatch.setattr(cnp.CodeNormalizer, 'show_diff', ...)``).
        """
        return show_diff(path, original, normalized)

    # ------------------------------------------------------------------
    # Single-file processing
    # ------------------------------------------------------------------

    def process_file(
        self,
        path: Path,
        output_path: Optional[Path] = None,
        check_syntax: bool = False,
    ) -> bool:
        """Normalize a single file.  Returns True on success or clean-skip."""
        self.stats.total_files += 1

        try:
            self._ensure_cache_manager(path)

            if self.use_cache and self.cache and self.cache.is_cached(path):
                if self.verbose:
                    logger.info(f"[C] CACHED {path.name} - unchanged since last run")
                self.stats.cached += 1
                self.stats.skipped += 1
                return True

            enc, text = self.guess_and_read(path)

            if self.max_lines > 0 and text.count("\n") > self.max_lines:
                if self.verbose:
                    logger.info(
                        f"[S] SKIP {path.name} - {text.count(chr(10))} lines "
                        f"exceeds {self.max_lines} max-lines limit"
                    )
                self.stats.skipped += 1
                return True

            normalized, changes = self.normalize_text(text, path)
            out_path = get_output_path(path, output_path, self.in_place)

            if text == normalized and enc == "utf-8":
                if self.verbose:
                    logger.info(f"[S] SKIP {path.name} - already normalized")
                self.stats.skipped += 1
                if self.use_cache and self.cache and not self.dry_run:
                    self.cache.update(path)
                return True

            if self.interactive and not self.dry_run:
                if not self.show_diff(path, text, normalized):
                    logger.info(f"[S] SKIP {path.name} - user declined")
                    self.stats.skipped += 1
                    return True

            if self.dry_run:
                return self._handle_dry_run(path, enc, changes, normalized, check_syntax)

            # Pre-flight syntax check (in-memory, before any file is touched)
            syntax_reason: Optional[str] = None
            if check_syntax:
                ok, reason = self._run_syntax_check(path, content=normalized)
                if ok:
                    self.stats.syntax_checks_passed += 1
                    syntax_reason = reason
                else:
                    self.stats.syntax_checks_failed += 1
                    self.stats.errors += 1
                    self.errors.append((path, f"Syntax check failed: {reason}"))
                    logger.error(f"[X] {path.name} failed syntax check: {reason}")
                    logger.error("    (original preserved, no changes written)")
                    return False

            if normalized == "" and text != "":
                self.stats.errors += 1
                self.errors.append(
                    (path, "normalize_text() returned empty string for non-empty input")
                )
                logger.error(
                    f"[X] {path.name}: normalization produced empty output "
                    "— aborting write (file preserved)"
                )
                return False

            backup_created = None
            if self.in_place and self.create_backup:
                backup_created = create_backup_file(path)

            out_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(out_path, normalized)

            self.stats.processed += 1
            self.stats.bytes_removed += changes["bytes_removed"]
            if enc != "utf-8":
                self.stats.encoding_changes += 1
            if changes["newline_fixes"] > 0:
                self.stats.newline_fixes += 1
            if changes["whitespace_fixes"] > 0:
                self.stats.whitespace_fixes += 1

            msg = (
                f"[+] {path.name} (in-place)"
                if self.in_place
                else f"[+] {path.name} -> {out_path.name}"
            )
            if enc != "utf-8":
                msg += f" [{enc}->utf-8]"
            logger.info(msg)

            if backup_created:
                logger.info(f"  Backup: {backup_created.name}")
            if check_syntax:
                label = f"[OK] ({syntax_reason})" if syntax_reason and syntax_reason != "OK" else "[OK]"
                logger.info(f"  Syntax: {label}")

            if self.use_cache and self.cache:
                self.cache.update(path)

            return True

        except Exception:
            tb_str = _traceback.format_exc()
            self.stats.errors += 1
            self.errors.append((path, tb_str))
            logger.error(f"[X] ERROR {path.name}:\n{tb_str}")
            return False

    def _handle_dry_run(
        self,
        path: Path,
        enc: str,
        changes: dict,
        normalized: str,
        check_syntax: bool,
    ) -> bool:
        logger.info(f"[DRY RUN] Would normalize: {path}")
        if enc != "utf-8":
            logger.info(f"  Encoding: {enc} -> utf-8")
            self.stats.encoding_changes += 1
        if changes["newline_fixes"] > 0:
            logger.info(f"  Newlines: {changes['newline_fixes']} fixes")
            self.stats.newline_fixes += 1
        if changes["whitespace_fixes"] > 0:
            logger.info(f"  Whitespace: {changes['whitespace_fixes']} chars removed")
            self.stats.whitespace_fixes += 1
        if changes["final_newline_added"]:
            logger.info("  Final newline: added")
        if check_syntax:
            ok, reason = self.syntax_check_text(path, normalized)
            status = "[+] OK" if ok else f"[X] {reason}"
            logger.info(f"  Syntax: {status}")
            if ok:
                self.stats.syntax_checks_passed += 1
            else:
                self.stats.syntax_checks_failed += 1
        self.stats.bytes_removed += changes["bytes_removed"]
        self.stats.processed += 1
        return True

    # ------------------------------------------------------------------
    # Directory walk (delegated to walker module)
    # ------------------------------------------------------------------

    def walk_and_process(
        self, root: Path, exts: List[str], check_syntax: bool = False
    ) -> None:
        """Process all matching files under *root*."""
        _walk_and_process(self, root, exts, check_syntax)

    # ------------------------------------------------------------------
    # Summary and reports (delegated to reporter module)
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        print_summary(self.stats, self.errors, use_cache=self.use_cache)

    def generate_reports(self) -> None:
        generate_reports(
            self.stats, self.errors,
            report_json=self.report_json,
            report_html=self.report_html,
        )
