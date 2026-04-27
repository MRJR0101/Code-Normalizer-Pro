"""Core normalizer engine: CodeNormalizer class and its parallel-processing helpers.

_init_worker and process_file_worker are kept here (rather than in walker.py) to
avoid a circular import: walker imports CodeNormalizer; if CodeNormalizer imported
from walker the dependency cycle would cause an ImportError.
"""

from __future__ import annotations

import configparser
import fnmatch
import mmap
import os
import shutil
import subprocess
import sys
import traceback as _traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from multiprocessing import cpu_count
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from loguru import logger

from code_normalizer_pro.engine.cache import CacheManager, CACHE_FILE
from code_normalizer_pro.engine.checkers import SYNTAX_CHECKERS, run_syntax_check
from code_normalizer_pro.engine.reporter import ProcessStats, print_summary, generate_reports

# Optional progress bar
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

COMMON_ENCODINGS = [
    "utf-8",
    "utf-8-sig",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "windows-1252",
    "latin-1",
    "iso-8859-1",
]

# Directory names excluded by default during recursive walks. Prevents the
# normalizer from descending into virtual environments, build artifacts, and
# third-party package trees where in-place modification would be destructive.
DEFAULT_EXCLUDE_DIRS: Set[str] = {
    ".venv", "venv", "env", ".env",
    "site-packages", "__pycache__",
    ".git", ".hg", ".svn",
    "node_modules",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache",
    "dist", "build", ".eggs",
}


# ---------------------------------------------------------------------------
# ProcessPoolExecutor worker helpers (module-level — must be picklable)
# ---------------------------------------------------------------------------

def _init_worker(log_file: Optional[Path]) -> None:
    """ProcessPoolExecutor initializer: runs once per worker process at startup.

    Sets up the log sink exactly once, regardless of how many files the worker
    handles.  Using the initializer (rather than a per-call global) is correct
    on both Windows (spawn) and Linux/macOS (fork) start methods.
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
    """Worker function for parallel processing (log sink set up by _init_worker)."""
    try:
        normalizer = CodeNormalizer(
            dry_run=dry_run,
            in_place=in_place,
            create_backup=create_backup,
            use_cache=False,  # cache managed by main process
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
            "processed": 0, "skipped": 0, "encoding_changes": 0, "newline_fixes": 0,
            "whitespace_fixes": 0, "bytes_removed": 0, "syntax_checks_passed": 0,
            "syntax_checks_failed": 0,
        }
        return False, empty_stats, f"Worker Crash:\n{tb_str}"


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
        self._editorconfig_cache: Dict[Path, Optional[configparser.ConfigParser]] = {}

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _resolve_cache_path(self, target: Path) -> Path:
        """Place cache beside the project or file being processed."""
        if self.cache_path_override:
            return self.cache_path_override
        base = target if target.is_dir() else target.parent
        return base / CACHE_FILE

    def _ensure_cache_manager(self, target: Path) -> None:
        """Bind cache storage to the current processing target."""
        if not self.use_cache:
            return
        desired_path = self._resolve_cache_path(target)
        if self.cache is None or self.cache.cache_path != desired_path:
            self.cache = CacheManager(desired_path)

    # ------------------------------------------------------------------
    # Progress / display helpers
    # ------------------------------------------------------------------

    def _should_show_progress(self) -> bool:
        """Avoid tqdm collisions with verbose per-file output."""
        return HAS_TQDM and not self.interactive and not self.verbose

    # ------------------------------------------------------------------
    # Encoding detection
    # ------------------------------------------------------------------

    def _looks_like_utf16_text(self, data: bytes) -> bool:
        """Best-effort check for UTF-16 text before binary rejection."""
        if not data:
            return False
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            return True
        sample = data[:256]
        if len(sample) < 4:
            return False
        for enc in ("utf-16-le", "utf-16-be"):
            try:
                decoded = sample.decode(enc)
            except UnicodeDecodeError:
                continue
            if not decoded:
                continue
            printable = sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t")
            alpha = sum(1 for ch in decoded if ch.isalpha())
            printable_ratio = printable / len(decoded)
            if printable_ratio >= 0.85 and alpha >= max(1, len(decoded) // 20):
                return True
        return False

    def guess_and_read(self, path: Path) -> Tuple[str, str]:
        """Detect encoding and read file content."""
        max_size = 50 * 1024 * 1024  # 50 MB
        if path.stat().st_size > max_size:
            raise ValueError("File exceeds maximum size limit of 50MB for in-memory processing")

        try:
            if path.stat().st_size > 0:
                with open(path, "rb") as f:
                    with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                        if b"\x00" in mm:
                            sample = mm[:256]
                            if not self._looks_like_utf16_text(sample):
                                raise ValueError("File appears to be binary")
        except ValueError:
            raise
        except Exception:
            pass

        data = path.read_bytes()

        if b"\x00" in data and not self._looks_like_utf16_text(data):
            raise ValueError("File appears to be binary")

        if data.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig", data[3:].decode("utf-8")

        last_error = None
        for enc in COMMON_ENCODINGS:
            try:
                text = data.decode(enc)
                return enc, text
            except UnicodeDecodeError as e:
                last_error = e
                continue

        raise UnicodeError("Could not decode with common encodings") from last_error

    # ------------------------------------------------------------------
    # EditorConfig resolution
    # ------------------------------------------------------------------

    def _expand_braces(self, pattern: str) -> List[str]:
        """Expand editorconfig brace patterns like *.{js,py} into multiple globs."""
        end = pattern.find("}")
        if end != -1:
            start = pattern.rfind("{", 0, end)
            if start != -1:
                pre = pattern[:start]
                post = pattern[end + 1:]
                options = pattern[start + 1:end].split(",")
                expanded = []
                for opt in options:
                    expanded.extend(self._expand_braces(pre + opt + post))
                return expanded
        return [pattern]

    def _editorconfig_match(self, filename: str, pattern: str) -> bool:
        """Match a filename against an .editorconfig glob, supporting {a,b} expansion."""
        for expanded_pattern in self._expand_braces(pattern):
            if fnmatch.fnmatch(filename, expanded_pattern):
                return True
        return False

    def _get_editorconfig(self, dir_path: Path) -> Optional[configparser.ConfigParser]:
        if dir_path in self._editorconfig_cache:
            return self._editorconfig_cache[dir_path]

        ec_path = dir_path / ".editorconfig"
        if ec_path.exists():
            try:
                raw = ec_path.read_text(encoding="utf-8")
                if raw.lstrip() and not raw.lstrip().startswith("["):
                    raw = "[__preamble__]\n" + raw
                parser = configparser.ConfigParser(interpolation=None)
                parser.read_string(raw)
                self._editorconfig_cache[dir_path] = parser
                return parser
            except Exception:
                pass

        self._editorconfig_cache[dir_path] = None
        return None

    def _resolve_indent_size(self, path: Path) -> int:
        """Hierarchically resolve the correct tab expansion size for a file."""
        if self.expand_tabs > 0:
            return self.expand_tabs

        current = path.parent
        while True:
            parser = self._get_editorconfig(current)
            if parser:
                found, indent_size = False, 0
                for section in parser.sections():
                    if self._editorconfig_match(path.name, section):
                        if "indent_size" in parser[section]:
                            val = parser[section]["indent_size"]
                            if val.isdigit():
                                indent_size = int(val)
                                found = True
                if found:
                    return indent_size
                preamble_root = (
                    parser.has_section("__preamble__")
                    and parser["__preamble__"].get("root", "").lower() == "true"
                )
                if preamble_root or parser.defaults().get("root", "").lower() == "true":
                    break
            if current == current.parent:
                break
            current = current.parent

        return 0

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def normalize_text(self, text: str, path: Path) -> Tuple[str, dict]:
        """Normalize text content and return (normalized_text, change_counts)."""
        changes = {
            "newline_fixes": 0,
            "whitespace_fixes": 0,
            "bytes_removed": 0,
            "final_newline_added": False,
        }

        if "cnp-ignore-file" in text:
            return text, changes

        original = text
        original_size = len(text.encode("utf-8"))

        tabs_to_spaces = self._resolve_indent_size(path)
        if tabs_to_spaces > 0 and "\t" in text:
            text = text.expandtabs(tabs_to_spaces)

        if "\r\n" in text or "\r" in text:
            changes["newline_fixes"] = original.count("\r")
            text = text.replace("\r\n", "\n").replace("\r", "\n")

        lines = text.split("\n")
        stripped_lines = []
        is_markdown = path.suffix.lower() in {".md", ".markdown"}
        ignoring = False

        for orig_line in lines:
            if "cnp: off" in orig_line:
                ignoring = True
            elif "cnp: on" in orig_line:
                ignoring = False

            if ignoring:
                stripped_lines.append(orig_line)
            else:
                stripped = orig_line.rstrip()
                if is_markdown and orig_line.endswith("  "):
                    stripped += "  "
                stripped_lines.append(stripped)

        whitespace_removed = sum(
            len(orig) - len(stripped)
            for orig, stripped in zip(lines, stripped_lines)
        )
        changes["whitespace_fixes"] = whitespace_removed

        text = "\n".join(stripped_lines)

        if not text.endswith("\n"):
            text += "\n"
            changes["final_newline_added"] = True

        new_size = len(text.encode("utf-8"))
        changes["bytes_removed"] = original_size - new_size

        return text, changes

    # ------------------------------------------------------------------
    # Syntax checking (delegates to checkers module)
    # ------------------------------------------------------------------

    def _run_syntax_check(
        self, path: Path, content: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Delegate to the standalone run_syntax_check() in the checkers module."""
        return run_syntax_check(path, content=content, syntax_timeout=self.syntax_timeout)

    def syntax_check_text(self, path: Path, text: str) -> Tuple[bool, str]:
        """Syntax check normalized content without writing it to the real file."""
        return self._run_syntax_check(path, content=text)

    # ------------------------------------------------------------------
    # File I/O helpers
    # ------------------------------------------------------------------

    def create_backup_file(self, path: Path) -> Path:
        """Create a timestamped backup (microsecond granularity — parallel-safe)."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = path.with_suffix(f".backup_{timestamp}{path.suffix}")
        shutil.copy2(path, backup_path)
        return backup_path

    def get_output_path(self, input_path: Path, output_path: Optional[Path]) -> Path:
        """Determine the destination path for normalized output."""
        if output_path:
            return output_path
        if self.in_place:
            return input_path
        return input_path.with_name(input_path.stem + "_clean" + input_path.suffix)

    def show_diff(self, path: Path, original: str, normalized: str) -> bool:
        """Show a line-by-line diff and prompt for user approval (interactive mode)."""
        print(f"\n{'=' * 70}")
        print(f"File: {path}")
        print(f"{'=' * 70}")

        orig_lines = original.split("\n")
        norm_lines = normalized.split("\n")
        changes = [
            (i, orig, norm)
            for i, (orig, norm) in enumerate(zip(orig_lines, norm_lines), 1)
            if orig != norm
        ]

        for line_num, orig, norm in changes[:10]:
            print(f"\nLine {line_num}:")
            print(f"  - {repr(orig)}")
            print(f"  + {repr(norm)}")

        if len(changes) > 10:
            print(f"\n... and {len(changes) - 10} more changes")

        print(f"\n{'=' * 70}")

        while True:
            choice = input("Apply changes? [y]es / [n]o / [d]iff all / [q]uit: ").lower()
            if choice in ("y", "yes"):
                return True
            elif choice in ("n", "no"):
                return False
            elif choice in ("d", "diff"):
                for line_num, orig, norm in changes:
                    print(f"\nLine {line_num}:")
                    print(f"  - {repr(orig)}")
                    print(f"  + {repr(norm)}")
            elif choice in ("q", "quit"):
                print("Quitting...")
                sys.exit(0)
            else:
                print("Invalid choice. Please enter y, n, d, or q.")

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

            if self.max_lines > 0:
                if text.count("\n") > self.max_lines:
                    if self.verbose:
                        line_count = text.count("\n")
                        logger.info(
                            f"[S] SKIP {path.name} - {line_count} lines "
                            f"exceeds {self.max_lines} max-lines limit"
                        )
                    self.stats.skipped += 1
                    return True

            normalized, changes = self.normalize_text(text, path)
            out_path = self.get_output_path(path, output_path)

            needs_encoding_fix = enc != "utf-8"
            needs_content_fix = text != normalized

            if not needs_content_fix and not needs_encoding_fix:
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

            # Pre-flight syntax check — runs against in-memory normalized text
            # BEFORE any file is touched.  Abort cleanly on failure.
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

            # Empty-output guard
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
                backup_created = self.create_backup_file(path)

            # Atomic write: stage to temp sibling → os.replace
            out_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = out_path.with_name(out_path.name + ".cnp-tmp")
            try:
                tmp_path.write_text(normalized, encoding="utf-8", newline="\n")
                if out_path.exists():
                    shutil.copymode(out_path, tmp_path)
                try:
                    os.replace(str(tmp_path), str(out_path))
                except OSError as replace_err:
                    if out_path.exists():
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        fallback_bak = out_path.with_name(
                            f"{out_path.name}.bak_pre_{timestamp}"
                        )
                        os.rename(str(out_path), str(fallback_bak))
                        try:
                            os.rename(str(tmp_path), str(out_path))
                            fallback_bak.unlink(missing_ok=True)
                        except Exception as e:
                            os.rename(str(fallback_bak), str(out_path))
                            raise e from replace_err
                    else:
                        os.rename(str(tmp_path), str(out_path))
            except Exception:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise

            self.stats.processed += 1
            self.stats.bytes_removed += changes["bytes_removed"]
            if enc != "utf-8":
                self.stats.encoding_changes += 1
            if changes["newline_fixes"] > 0:
                self.stats.newline_fixes += 1
            if changes["whitespace_fixes"] > 0:
                self.stats.whitespace_fixes += 1

            msg = f"[+] {path.name} (in-place)" if self.in_place else f"[+] {path.name} -> {out_path.name}"
            if enc != "utf-8":
                msg += f" [{enc}->utf-8]"
            logger.info(msg)

            if backup_created:
                logger.info(f"  Backup: {backup_created.name}")

            if check_syntax:
                if syntax_reason and syntax_reason != "OK":
                    logger.info(f"  Syntax: [OK] ({syntax_reason})")
                else:
                    logger.info("  Syntax: [OK]")

            if self.use_cache and self.cache:
                self.cache.update(path)

            return True

        except Exception:
            tb_str = _traceback.format_exc()
            self.stats.errors += 1
            self.errors.append((path, tb_str))
            logger.error(f"[X] ERROR {path.name}:\n{tb_str}")
            return False

    # ------------------------------------------------------------------
    # Directory walk and parallel processing
    # ------------------------------------------------------------------

    def walk_and_process(
        self, root: Path, exts: List[str], check_syntax: bool = False
    ) -> None:
        """Process all matching files under *root*, respecting exclusions and gitignore."""
        self._ensure_cache_manager(root)

        files: List[Path] = []
        ext_set = {e.lower() for e in exts}
        visited_real: Set[str] = set()
        pruned_dirs = 0

        for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
            try:
                real = os.path.realpath(dirpath)
            except OSError:
                dirnames[:] = []
                continue
            if real in visited_real:
                dirnames[:] = []
                continue
            visited_real.add(real)

            before = len(dirnames)
            dirnames[:] = [d for d in dirnames if d not in self.exclude_dirs]
            pruned_dirs += before - len(dirnames)

            for fname in filenames:
                lower = fname.lower()
                if any(lower.endswith(ext) for ext in ext_set):
                    file_path = Path(dirpath) / fname
                    if not file_path.is_symlink():
                        files.append(file_path)

        if pruned_dirs and self.verbose:
            logger.info(f"[i] Pruned {pruned_dirs} excluded subdirectories from walk")

        if self.respect_gitignore and files:
            try:
                git_cmd = ["git", "check-ignore", "-z", "--stdin"]
                input_data = b"\0".join(
                    str(f.absolute()).encode("utf-8") for f in files
                ) + b"\0"
                res = subprocess.run(git_cmd, input=input_data, capture_output=True, cwd=root)
                if res.returncode in (0, 1):
                    ignored = {p for p in res.stdout.split(b"\0") if p}
                    original_count = len(files)
                    files = [
                        f for f in files
                        if str(f.absolute()).encode("utf-8") not in ignored
                    ]
                    if (pruned_git := original_count - len(files)) and self.verbose:
                        logger.info(f"[i] Pruned {pruned_git} file(s) ignored by .gitignore")
            except Exception:
                pass

        if not files:
            logger.info(f"No files with extensions {exts} found in {root}")
            return

        files_to_process = files
        if self.use_cache and self.cache:
            uncached_files = []
            cached_hits = 0
            for file_path in files:
                if self.cache.is_cached(file_path):
                    cached_hits += 1
                    self.stats.cached += 1
                    self.stats.skipped += 1
                    self.stats.total_files += 1
                    if self.verbose:
                        logger.info(f"[C] CACHED {file_path.name} - unchanged since last run")
                else:
                    uncached_files.append(file_path)
            files_to_process = uncached_files
            if cached_hits and self.verbose:
                logger.info(f"[C] Cache prefilter skipped {cached_hits} unchanged file(s)")

        logger.info(f"\n[*] Found {len(files)} file(s) to process")
        logger.info(f"   Extensions: {', '.join(exts)}")
        mode_desc = "DRY RUN" if self.dry_run else "IN-PLACE" if self.in_place else "CLEAN COPY"
        if self.parallel:
            mode_desc += f" (PARALLEL {self.max_workers} workers)"
        if self.use_cache:
            mode_desc += " (CACHED)"
        if self.interactive:
            mode_desc += " (INTERACTIVE)"
        logger.info(f"   Mode: {mode_desc}")

        if not files_to_process:
            logger.info("All discovered files were unchanged and skipped by cache.")
            return

        if not self.dry_run and self.in_place and not self.interactive:
            if self.auto_confirm:
                logger.info("[!] Skipping confirmation prompt (--yes)")
            else:
                try:
                    response = input(
                        f"\n[!] In-place editing will scan {len(files_to_process)} file(s) "
                        "and modify only files that need changes. Continue? (y/N): "
                    )
                except EOFError:
                    logger.info("Cancelled (non-interactive stdin — use --yes to skip prompt)")
                    return
                if response.strip().lower() not in ("y", "yes"):
                    logger.info("Cancelled")
                    return

        if self.parallel and not self.interactive:
            self._process_parallel(files_to_process, check_syntax)
        else:
            self._process_sequential(files_to_process, check_syntax)

        if self.use_cache and self.cache and not self.dry_run:
            self.cache.save()

    def _process_sequential(self, files: List[Path], check_syntax: bool) -> None:
        """Process files one at a time with optional tqdm progress bar."""
        iterator = tqdm(files, desc="Processing") if self._should_show_progress() else files
        for file_path in iterator:
            self.process_file(file_path, check_syntax=check_syntax)

    def _process_parallel(self, files: List[Path], check_syntax: bool) -> None:
        """Submit files to a ProcessPoolExecutor and collect results."""
        logger.info(f"\n[>>] Parallel processing with {self.max_workers} workers...\n")

        with ProcessPoolExecutor(
            max_workers=self.max_workers,
            initializer=_init_worker,
            initargs=(self.log_file,),
        ) as executor:
            futures = {
                executor.submit(
                    process_file_worker,
                    file_path,
                    self.dry_run,
                    self.in_place,
                    self.create_backup,
                    check_syntax,
                    self.syntax_timeout,
                    self.expand_tabs,
                    self.max_lines,
                ): file_path
                for file_path in files
            }

            iterator = as_completed(futures)
            if self._should_show_progress():
                iterator = tqdm(iterator, total=len(files), desc="Processing")

            for future in iterator:
                file_path = futures[future]
                try:
                    success, stats_update, error = future.result()
                    self.stats.total_files += 1
                    if success:
                        self.stats.processed += stats_update["processed"]
                        self.stats.skipped += stats_update["skipped"]
                        self.stats.encoding_changes += stats_update["encoding_changes"]
                        self.stats.newline_fixes += stats_update["newline_fixes"]
                        self.stats.whitespace_fixes += stats_update["whitespace_fixes"]
                        self.stats.bytes_removed += stats_update["bytes_removed"]
                        self.stats.syntax_checks_passed += stats_update["syntax_checks_passed"]
                        self.stats.syntax_checks_failed += stats_update["syntax_checks_failed"]
                        if self.use_cache and self.cache and not self.dry_run:
                            self.cache.update(file_path)
                    else:
                        self.stats.errors += 1
                        self.stats.syntax_checks_failed += stats_update.get("syntax_checks_failed", 0)
                        self.stats.syntax_checks_passed += stats_update.get("syntax_checks_passed", 0)
                        self.errors.append((file_path, error))
                except Exception:
                    tb_str = _traceback.format_exc()
                    self.stats.errors += 1
                    self.errors.append((file_path, f"Future failed:\n{tb_str}"))

    # ------------------------------------------------------------------
    # Summary and report (delegate to reporter module)
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        """Print the processing summary via the reporter module."""
        print_summary(self.stats, self.errors, use_cache=self.use_cache)

    def generate_reports(self) -> None:
        """Generate JSON and/or HTML reports via the reporter module."""
        generate_reports(
            self.stats,
            self.errors,
            report_json=self.report_json,
            report_html=self.report_html,
        )
