#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Code Normalizer Pro - Production-Grade Code Normalization Tool
================================================================

High-Impact Features:
- Parallel Processing (multi-core performance)
- Pre-Commit Hook Generation
- Incremental Processing (hash-based caching)
- Multi-Language Syntax Checking
- Interactive Mode (file-by-file approval)

Plus all v2.0 features:
- Dry-run mode, In-place editing, Automatic backups
- Progress tracking, Detailed statistics, Error handling

New in v3.1.0:
- Default exclusion set (.venv, __pycache__, node_modules, etc.)
- --exclude DIR and --no-default-excludes CLI flags
- Symlink / junction cycle detection in recursive walks
- Atomic write via temp+rename; --check now gates the write entirely
- Cache persisted on Ctrl-C so interrupted runs resume
- --syntax-timeout SECONDS flag for slow first-run tsc/gcc/rustc
- Microsecond-resolution backup filenames (parallel-safe)
- Subprocess calls use explicit UTF-8 encoding (no more cp1252 crashes)
- Plain ASCII output (no Unicode console symbols)

New in v3.1.1 (bug fixes from self-review of 3.1.0):
- Parallel path now correctly merges syntax_checks_failed stats
  from workers that returned success=False (was under-reporting)
- Post-write "Syntax: [OK]" now surfaces the reason string from
  the pre-flight check (exposes "gcc not installed" cases)
- Removed dead syntax_check() method (internal code uses
  _run_syntax_check directly)
- Fixed "[!]  " double-space typo in confirmation prompt and
  git hook template
- Confirmation prompt now accepts "yes" as well as "y"
- --cache help text now accurately describes it as a no-op

Author: MR
Date: 2026-02-09
Version: 3.1.1
"""

import typer
import subprocess
import sys
import os
import hashlib
import json
import tempfile
import shutil
import mmap
import fnmatch
import configparser
from loguru import logger
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Set
from dataclasses import dataclass, asdict
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Optional dependencies
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

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
# Callers may add to this set via --exclude, or disable it entirely with
# --no-default-excludes (intended for surgical single-directory runs).
DEFAULT_EXCLUDE_DIRS: Set[str] = {
    ".venv", "venv", "env", ".env",
    "site-packages", "__pycache__",
    ".git", ".hg", ".svn",
    "node_modules",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache",
    "dist", "build", ".eggs",
}

# Multi-language syntax checkers
SYNTAX_CHECKERS = {
    ".py": {
        "command": [sys.executable, "-m", "py_compile"],
        "stdin": False,
        "file_arg": True,
    },
    ".js": {
        "command": ["node", "--check"],
        "stdin": False,
        "file_arg": True,
    },
    ".ts": {
        "command": ["tsc", "--noEmit"],
        "stdin": False,
        "file_arg": True,
    },
    ".go": {
        "command": ["gofmt", "-e"],
        "stdin": True,
        "file_arg": False,
    },
    ".rs": {
        "command": ["rustc", "--crate-type", "lib", "-"],
        "stdin": True,
        "file_arg": False,
    },
    ".c": {
        "command": ["gcc", "-fsyntax-only", "-x", "c"],
        "stdin": False,
        "file_arg": True,
    },
    ".cpp": {
        "command": ["g++", "-fsyntax-only", "-x", "c++"],
        "stdin": False,
        "file_arg": True,
    },
    ".java": {
        "command": ["javac", "-Xstdout"],
        "stdin": False,
        "file_arg": True,
    },
    ".json": {
        "command": [sys.executable, "-m", "json.tool"],
        "stdin": True,
        "file_arg": False,
    },
    ".sh": {
        "command": ["bash", "-n"],
        "stdin": False,
        "file_arg": True,
    },
    ".rb": {
        "command": ["ruby", "-c"],
        "stdin": False,
        "file_arg": True,
    },
    ".php": {
        "command": ["php", "-l"],
        "stdin": False,
        "file_arg": True,
    },
    ".pl": {
        "command": ["perl", "-c"],
        "stdin": False,
        "file_arg": True,
    },
    ".lua": {
        "command": ["luac", "-p"],
        "stdin": False,
        "file_arg": True,
    },
}

CACHE_FILE = ".normalize-cache.json"


@dataclass
class FileCache:
    """Cache entry for a file"""
    path: str
    hash: str
    last_normalized: str
    size: int
    mtime: float = 0.0


@dataclass
class ProcessStats:
    """Statistics for processing session"""
    total_files: int = 0
    processed: int = 0
    skipped: int = 0
    cached: int = 0
    errors: int = 0
    encoding_changes: int = 0
    newline_fixes: int = 0
    whitespace_fixes: int = 0
    syntax_checks_passed: int = 0
    syntax_checks_failed: int = 0
    bytes_removed: int = 0


class CacheManager:
    """Manages file hash cache for incremental processing"""

    def __init__(self, cache_path: Optional[Path] = None):
        self.cache_path = cache_path or Path(CACHE_FILE)
        self.cache: Dict[str, FileCache] = {}
        self.load()

    def load(self):
        """Load cache from disk"""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.cache = {}
                    for k, v in data.items():
                        if 'mtime' not in v:
                            v['mtime'] = 0.0
                        self.cache[k] = FileCache(**v)
            except Exception as e:
                logger.warning(f"Could not load cache: {e}")
                self.cache = {}

    def save(self):
        """Save cache to disk"""
        try:
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                data = {k: asdict(v) for k, v in self.cache.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")

    def get_file_hash(self, path: Path) -> str:
        """Calculate SHA256 hash of file"""
        sha256 = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def is_cached(self, path: Path) -> bool:
        """Check if file is in cache and unchanged"""
        path_str = str(path)
        if path_str not in self.cache:
            return False

        cached = self.cache[path_str]

        # Check if file still exists
        if not path.exists():
            return False

        stat = path.stat()

        # Check size first (fast check)
        if stat.st_size != cached.size:
            return False

        # Check mtime (fastest check, avoids reading file bytes if unchanged)
        if cached.mtime and stat.st_mtime == cached.mtime:
            return True

        # Check hash (slower but accurate)
        current_hash = self.get_file_hash(path)
        return current_hash == cached.hash

    def update(self, path: Path):
        """Update cache entry for file"""
        path_str = str(path)
        stat = path.stat()
        self.cache[path_str] = FileCache(
            path=path_str,
            hash=self.get_file_hash(path),
            last_normalized=datetime.now().isoformat(),
            size=stat.st_size,
            mtime=stat.st_mtime
        )


class CodeNormalizer:
    """Production-grade code normalizer with advanced features"""

    def __init__(self,
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
                 log_file: Optional[Path] = None):
        self.dry_run = dry_run
        self.verbose = verbose
        self.in_place = in_place
        self.create_backup = create_backup
        self.use_cache = use_cache
        self.interactive = interactive
        self.parallel = parallel
        self.max_workers = max_workers or max(1, cpu_count() - 1)
        self.cache_path_override = cache_path
        self.exclude_dirs: Set[str] = set(exclude_dirs) if exclude_dirs is not None else set(DEFAULT_EXCLUDE_DIRS)
        self.syntax_timeout = max(1, int(syntax_timeout))
        self.report_json = report_json
        self.report_html = report_html
        self.expand_tabs = max(0, int(expand_tabs))
        self.max_lines = max(0, int(max_lines))
        self.respect_gitignore = respect_gitignore
        self.log_file = log_file
        self.stats = ProcessStats()
        self.errors: List[Tuple[Path, str]] = []
        self.cache = CacheManager(cache_path) if use_cache and cache_path else None
        self._editorconfig_cache: Dict[Path, Optional[configparser.ConfigParser]] = {}

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

    def _should_show_progress(self) -> bool:
        """Avoid tqdm collisions with verbose per-file output."""
        return HAS_TQDM and not self.interactive and not self.verbose

    def _looks_like_utf16_text(self, data: bytes) -> bool:
        """Best-effort check for UTF-16 text before binary rejection."""
        if not data:
            return False

        # BOM signatures
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

            # Require mostly printable content and at least some alphabetic text.
            if printable_ratio >= 0.85 and alpha >= max(1, len(decoded) // 20):
                return True

        return False

    def guess_and_read(self, path: Path) -> Tuple[str, str]:
        """Detect encoding and read file"""
        # Safety check: prevent memory exhaustion from massive files
        max_size = 50 * 1024 * 1024  # 50 MB
        if path.stat().st_size > max_size:
            raise ValueError(f"File exceeds maximum size limit of 50MB for in-memory processing")

        # Fast binary check using mmap (zero-copy, highly memory efficient)
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
            raise ValueError(f"File appears to be binary")

        # Explicit UTF-8 BOM detection.  Python's plain "utf-8" codec treats
        # the three BOM bytes (EF BB BF) as the valid U+FEFF codepoint rather
        # than stripping them, so "utf-8" always wins the codec loop and the
        # BOM is silently preserved.  We check the raw prefix first so the
        # encoding is correctly identified as "utf-8-sig" and the BOM is
        # removed on the next in-place write (needs_encoding_fix = True).
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

        raise UnicodeError(
            f"Could not decode with common encodings"
        ) from last_error

    def _expand_braces(self, pattern: str) -> List[str]:
        """Expand editorconfig brace patterns like *.{js,py} into multiple standard globs."""
        end = pattern.find('}')
        if end != -1:
            start = pattern.rfind('{', 0, end)
            if start != -1:
                pre = pattern[:start]
                post = pattern[end+1:]
                options = pattern[start+1:end].split(',')
                expanded = []
                for opt in options:
                    expanded.extend(self._expand_braces(pre + opt + post))
                return expanded
        return [pattern]

    def _editorconfig_match(self, filename: str, pattern: str) -> bool:
        """Match a filename against an .editorconfig glob pattern, supporting {a,b} brace expansion."""
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
                # editorconfig allows global key=value pairs before any section
                # header (e.g. "root = true").  configparser raises
                # MissingSectionHeaderError for such content, which silently
                # discards the whole file.  Prepend a sentinel section so those
                # top-level keys are stored in [__preamble__] instead.
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
            return self.expand_tabs  # Explicit CLI override wins
            
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
                # "root = true" may be in the preamble sentinel section or in
                # the configparser DEFAULTS dict, depending on file structure.
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

    def normalize_text(self, text: str, path: Path) -> Tuple[str, dict]:
        """Normalize text and track changes"""
        changes = {
            'newline_fixes': 0,
            'whitespace_fixes': 0,
            'bytes_removed': 0,
            'final_newline_added': False
        }

        # Inline Ignore: Skip file entirely
        if "cnp-ignore-file" in text:
            return text, changes

        original = text
        original_size = len(text.encode('utf-8'))

        # Expand tabs
        tabs_to_spaces = self._resolve_indent_size(path)
        if tabs_to_spaces > 0 and '\t' in text:
            text = text.expandtabs(tabs_to_spaces)

        # Normalize newlines. Every \r in the original text will be removed
        # or converted to \n by the two replacements below, so counting \r
        # occurrences gives the exact number of line-ending characters
        # touched regardless of whether they were CRLF pairs or lone CRs.
        if '\r\n' in text or '\r' in text:
            changes['newline_fixes'] = original.count('\r')
            text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Strip trailing whitespace with Markdown & Inline Ignore awareness
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
                # Markdown hard break preservation (clean >=2 spaces down to exactly 2)
                if is_markdown and orig_line.endswith("  "):
                    stripped += "  "
                stripped_lines.append(stripped)

        whitespace_removed = sum(
            len(orig) - len(stripped)
            for orig, stripped in zip(lines, stripped_lines)
        )
        changes['whitespace_fixes'] = whitespace_removed

        text = "\n".join(stripped_lines)

        # Ensure final newline
        if not text.endswith("\n"):
            text += "\n"
            changes['final_newline_added'] = True

        # Calculate bytes removed
        new_size = len(text.encode('utf-8'))
        changes['bytes_removed'] = original_size - new_size

        return text, changes

    def _run_syntax_check(self, path: Path, content: Optional[str] = None) -> Tuple[bool, str]:
        """Run a syntax checker against a file or normalized text buffer."""
        ext = path.suffix.lower()

        if ext not in SYNTAX_CHECKERS:
            return True, "No checker available"

        checker = SYNTAX_CHECKERS[ext]
        cmd = checker['command'].copy()
        temp_path: Optional[Path] = None
        temp_dir: Optional[tempfile.TemporaryDirectory] = None

        try:
            if checker['file_arg']:
                target_path = path
                if content is not None:
                    temp_dir = tempfile.TemporaryDirectory()
                    temp_path = Path(temp_dir.name) / path.name
                    temp_path.write_text(content, encoding="utf-8", newline="\n")
                    target_path = temp_path

                # Absolute path prevents filenames starting with '-' from being parsed as flags by the checker
                cmd.append(str(target_path.absolute()))
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=self.syntax_timeout,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            else:
                # Read file and pass via stdin
                if content is None:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                result = subprocess.run(
                    cmd,
                    input=content,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=self.syntax_timeout,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

            if result.returncode == 0:
                return True, "OK"
            else:
                return False, (result.stderr or "").strip()[:100]

        except FileNotFoundError:
            return True, f"{checker['command'][0]} not installed"
        except subprocess.TimeoutExpired:
            return False, f"Timeout after {self.syntax_timeout}s"
        except Exception as e:
            return False, str(e)[:100]
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()

    def syntax_check_text(self, path: Path, text: str) -> Tuple[bool, str]:
        """Syntax check normalized content without writing it to the real file."""
        return self._run_syntax_check(path, content=text)

    def create_backup_file(self, path: Path) -> Path:
        """Create timestamped backup.

        Uses microsecond granularity so two calls made in the same second
        (possible under --parallel) cannot silently overwrite each other.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = path.with_suffix(f".backup_{timestamp}{path.suffix}")
        shutil.copy2(path, backup_path)
        return backup_path

    def get_output_path(self, input_path: Path, output_path: Optional[Path]) -> Path:
        """Determine output path"""
        if output_path:
            return output_path
        if self.in_place:
            return input_path
        return input_path.with_name(input_path.stem + "_clean" + input_path.suffix)

    def show_diff(self, path: Path, original: str, normalized: str) -> bool:
        """Show diff and get user approval (interactive mode)"""
        print(f"\n{'='*70}")
        print(f"File: {path}")
        print(f"{'='*70}")

        # Simple line-by-line diff
        orig_lines = original.split('\n')
        norm_lines = normalized.split('\n')

        changes = []
        for i, (orig, norm) in enumerate(zip(orig_lines, norm_lines), 1):
            if orig != norm:
                changes.append((i, orig, norm))

        # Show first 10 changes
        for line_num, orig, norm in changes[:10]:
            print(f"\nLine {line_num}:")
            print(f"  - {repr(orig)}")
            print(f"  + {repr(norm)}")

        if len(changes) > 10:
            print(f"\n... and {len(changes) - 10} more changes")

        print(f"\n{'='*70}")

        # Get user input
        while True:
            choice = input("Apply changes? [y]es / [n]o / [d]iff all / [q]uit: ").lower()

            if choice in ('y', 'yes'):
                return True
            elif choice in ('n', 'no'):
                return False
            elif choice in ('d', 'diff'):
                # Show all changes
                for line_num, orig, norm in changes:
                    print(f"\nLine {line_num}:")
                    print(f"  - {repr(orig)}")
                    print(f"  + {repr(norm)}")
            elif choice in ('q', 'quit'):
                print("Quitting...")
                sys.exit(0)
            else:
                print("Invalid choice. Please enter y, n, d, or q.")

    def process_file(self, path: Path, output_path: Optional[Path] = None,
                    check_syntax: bool = False) -> bool:
        """Process a single file"""
        self.stats.total_files += 1

        try:
            self._ensure_cache_manager(path)

            # Check cache first (incremental processing)
            if self.use_cache and self.cache and self.cache.is_cached(path):
                if self.verbose:
                    logger.info(f"[C] CACHED {path.name} - unchanged since last run")
                self.stats.cached += 1
                self.stats.skipped += 1
                return True

            # Read and detect encoding
            enc, text = self.guess_and_read(path)

            # Check line count limit
            if self.max_lines > 0:
                if text.count('\n') > self.max_lines:
                    if self.verbose:
                        logger.info(f"[S] SKIP {path.name} - {text.count('\n')} lines exceeds {self.max_lines} max-lines limit")
                    self.stats.skipped += 1
                    return True

            # Normalize
            normalized, changes = self.normalize_text(text, path)

            # Determine output
            out_path = self.get_output_path(path, output_path)

            needs_encoding_fix = enc != "utf-8"
            needs_content_fix = text != normalized

            # Check if any normalization work is needed
            if not needs_content_fix and not needs_encoding_fix:
                if self.verbose:
                    logger.info(f"[S] SKIP {path.name} - already normalized")
                self.stats.skipped += 1

                # Update cache even for unchanged files
                if self.use_cache and self.cache:
                    self.cache.update(path)

                return True

            # Interactive mode
            if self.interactive and not self.dry_run:
                if not self.show_diff(path, text, normalized):
                    logger.info(f"[S] SKIP {path.name} - user declined")
                    self.stats.skipped += 1
                    return True

            # Dry run mode
            if self.dry_run:
                logger.info(f"[DRY RUN] Would normalize: {path}")
                if enc != "utf-8":
                    logger.info(f"  Encoding: {enc} -> utf-8")
                    self.stats.encoding_changes += 1
                if changes['newline_fixes'] > 0:
                    logger.info(f"  Newlines: {changes['newline_fixes']} fixes")
                    self.stats.newline_fixes += 1
                if changes['whitespace_fixes'] > 0:
                    logger.info(f"  Whitespace: {changes['whitespace_fixes']} chars removed")
                    self.stats.whitespace_fixes += 1
                if changes['final_newline_added']:
                    logger.info(f"  Final newline: added")

                if check_syntax:
                    ok, reason = self.syntax_check_text(path, normalized)
                    status = "[+] OK" if ok else f"[X] {reason}"
                    logger.info(f"  Syntax: {status}")
                    if ok:
                        self.stats.syntax_checks_passed += 1
                    else:
                        self.stats.syntax_checks_failed += 1

                self.stats.bytes_removed += changes['bytes_removed']
                self.stats.processed += 1
                return True

            # Pre-flight syntax check: run against the normalized text in
            # memory BEFORE any file is touched. If the check fails we abort
            # with the original file completely untouched -- no backup, no
            # rollback, no partial state. This is the whole point of H3 from
            # the code review.
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

            # Create backup if needed
            backup_created = None
            if self.in_place and self.create_backup:
                backup_created = self.create_backup_file(path)

            # Atomic write: stage to a temp sibling, then os.replace to the
            # real path. os.replace is atomic on POSIX and on Windows as long
            # as both paths are on the same filesystem, which they always are
            # because we use the same parent directory.
            out_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = out_path.with_name(out_path.name + ".cnp-tmp")
            try:
                tmp_path.write_text(normalized, encoding="utf-8", newline="\n")
                # Preserve original file permissions (e.g., executable bits on shell scripts)
                if out_path.exists():
                    shutil.copymode(out_path, tmp_path)
                
                try:
                    os.replace(str(tmp_path), str(out_path))
                except OSError as replace_err:
                    # Fallback for strict Windows file locks or non-atomic filesystem mounts
                    if out_path.exists():
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        fallback_bak = out_path.with_name(f"{out_path.name}.bak_pre_{timestamp}")
                        
                        # 1. Move original out of the way
                        os.rename(str(out_path), str(fallback_bak))
                        try:
                            # 2. Put new file in place
                            os.rename(str(tmp_path), str(out_path))
                            # 3. Clean up the fallback
                            fallback_bak.unlink(missing_ok=True)
                        except Exception as e:
                            # Rollback: restore the original file if step 2 fails
                            os.rename(str(fallback_bak), str(out_path))
                            raise e from replace_err
                    else:
                        os.rename(str(tmp_path), str(out_path))
            except Exception:
                # Never leave a temp file behind
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise

            # Update stats
            self.stats.processed += 1
            self.stats.bytes_removed += changes['bytes_removed']
            if enc != "utf-8":
                self.stats.encoding_changes += 1
            if changes['newline_fixes'] > 0:
                self.stats.newline_fixes += 1
            if changes['whitespace_fixes'] > 0:
                self.stats.whitespace_fixes += 1

            # Report
            if self.in_place:
                msg = f"[+] {path.name} (in-place)"
            else:
                msg = f"[+] {path.name} -> {out_path.name}"

            if enc != "utf-8":
                msg += f" [{enc}->utf-8]"

            logger.info(msg)

            if backup_created:
                logger.info(f"  Backup: {backup_created.name}")

            if check_syntax:
                # We already incremented syntax_checks_passed above, and the
                # file is guaranteed to match the in-memory content that
                # passed the check. Surface the reason string so users can
                # see when the "pass" was actually "no checker available"
                # or "gcc not installed" rather than a real validation.
                if syntax_reason and syntax_reason != "OK":
                    logger.info(f"  Syntax: [OK] ({syntax_reason})")
                else:
                    logger.info("  Syntax: [OK]")

            # Update cache
            if self.use_cache and self.cache:
                self.cache.update(path)

            return True

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.stats.errors += 1
            self.errors.append((path, tb_str))
            logger.error(f"[X] ERROR {path.name}:\n{tb_str}")
            return False

    def walk_and_process(self, root: Path, exts: List[str],
                        check_syntax: bool = False) -> None:
        """Process all files in directory tree"""
        self._ensure_cache_manager(root)

        # Collect files with exclusion pruning and symlink-cycle detection.
        # Uses os.walk so we can mutate dirnames in-place to prune branches
        # before descending, which is significantly faster than walking the
        # whole tree and filtering afterwards. followlinks=False plus the
        # realpath visited-set handles both POSIX symlinks and Windows
        # junction points that could otherwise create recursion cycles.
        files: List[Path] = []
        ext_set = {e.lower() for e in exts}
        visited_real: Set[str] = set()
        pruned_dirs = 0

        for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
            # Symlink / junction cycle guard
            try:
                real = os.path.realpath(dirpath)
            except OSError:
                dirnames[:] = []
                continue
            if real in visited_real:
                dirnames[:] = []
                continue
            visited_real.add(real)

            # Prune excluded directory names in place so os.walk will not
            # descend into them on the next iteration
            before = len(dirnames)
            dirnames[:] = [d for d in dirnames if d not in self.exclude_dirs]
            pruned_dirs += before - len(dirnames)

            # Collect matching files from this directory level
            for fname in filenames:
                lower = fname.lower()
                if any(lower.endswith(ext) for ext in ext_set):
                    file_path = Path(dirpath) / fname
                    if not file_path.is_symlink():
                        files.append(file_path)

        if pruned_dirs and self.verbose:
            logger.info(f"[i] Pruned {pruned_dirs} excluded subdirectories from walk")

        # Filter out files ignored by Git
        if self.respect_gitignore and files:
            try:
                git_cmd = ["git", "check-ignore", "-z", "--stdin"]
                input_data = b"\0".join(str(f.absolute()).encode('utf-8') for f in files) + b"\0"
                res = subprocess.run(git_cmd, input=input_data, capture_output=True, cwd=root)
                if res.returncode in (0, 1):
                    ignored = {p for p in res.stdout.split(b'\0') if p}
                    original_count = len(files)
                    files = [f for f in files if str(f.absolute()).encode('utf-8') not in ignored]
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

        # Confirmation
        if not self.dry_run and self.in_place and not self.interactive:
            response = input(
                f"\n[!] In-place editing will scan {len(files_to_process)} file(s) "
                "and modify only files that need changes. Continue? (y/N): "
            )
            if response.strip().lower() not in ("y", "yes"):
                logger.info("Cancelled")
                return

        # Process files

        if self.parallel and not self.interactive:
            self._process_parallel(files_to_process, check_syntax)
        else:
            self._process_sequential(files_to_process, check_syntax)

        # Save cache
        if self.use_cache and self.cache and not self.dry_run:
            self.cache.save()

    def _process_sequential(self, files: List[Path], check_syntax: bool):
        """Process files sequentially"""
        iterator = tqdm(files, desc="Processing") if self._should_show_progress() else files

        for file_path in iterator:
            self.process_file(file_path, check_syntax=check_syntax)

    def _process_parallel(self, files: List[Path], check_syntax: bool):
        """Process files in parallel"""
        logger.info(f"\n[>>] Parallel processing with {self.max_workers} workers...\n")

        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
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
                        self.log_file,
                ): file_path
                for file_path in files
            }

            # Progress tracking
            iterator = as_completed(futures)
            if self._should_show_progress():
                iterator = tqdm(iterator, total=len(files), desc="Processing")

            # Collect results
            for future in iterator:
                file_path = futures[future]
                try:
                    success, stats_update, error = future.result()

                    # Update stats
                    self.stats.total_files += 1
                    if success:
                        self.stats.processed += stats_update['processed']
                        self.stats.skipped += stats_update['skipped']
                        self.stats.encoding_changes += stats_update['encoding_changes']
                        self.stats.newline_fixes += stats_update['newline_fixes']
                        self.stats.whitespace_fixes += stats_update['whitespace_fixes']
                        self.stats.bytes_removed += stats_update['bytes_removed']
                        self.stats.syntax_checks_passed += stats_update['syntax_checks_passed']
                        self.stats.syntax_checks_failed += stats_update['syntax_checks_failed']
                        if self.use_cache and self.cache and not self.dry_run:
                            self.cache.update(file_path)
                    else:
                        self.stats.errors += 1
                        # NEW-H1 fix: the worker may have incremented
                        # syntax_checks_failed inside process_file before
                        # returning False (pre-flight check path). Pull
                        # those counters over even on the failure branch,
                        # otherwise the summary will under-report every
                        # parallel --check failure as "0 failures".
                        self.stats.syntax_checks_failed += stats_update.get('syntax_checks_failed', 0)
                        self.stats.syntax_checks_passed += stats_update.get('syntax_checks_passed', 0)
                        self.errors.append((file_path, error))

                except Exception as e:
                    import traceback
                    tb_str = traceback.format_exc()
                    self.stats.errors += 1
                    self.errors.append((file_path, f"Future failed:\n{tb_str}"))

    def print_summary(self):
        """Print processing summary"""
        logger.info("\n" + "="*70)
        logger.info("PROCESSING SUMMARY")
        logger.info("="*70)
        logger.info(f"  Total files: {self.stats.total_files}")
        logger.info(f"  [+] Processed: {self.stats.processed}")
        logger.info(f"  [S] Skipped: {self.stats.skipped}")
        if self.use_cache:
            logger.info(f"  [C] Cached hits: {self.stats.cached}")
        logger.info(f"  [X] Errors: {self.stats.errors}")
        logger.info("")
        logger.info(f"  Encoding changes: {self.stats.encoding_changes}")
        logger.info(f"  Newline fixes: {self.stats.newline_fixes}")
        logger.info(f"  Whitespace fixes: {self.stats.whitespace_fixes}")
        logger.info(f"  Bytes removed: {self.stats.bytes_removed:,}")

        if self.stats.syntax_checks_passed > 0 or self.stats.syntax_checks_failed > 0:
            logger.info("")
            logger.info(f"  Syntax checks passed: {self.stats.syntax_checks_passed}")
            logger.info(f"  Syntax checks failed: {self.stats.syntax_checks_failed}")

        if self.errors:
            logger.error("\n[X] ERRORS:")
            for path, error in self.errors[:10]:
                logger.error(f"  {path.name}: {error}")
            if len(self.errors) > 10:
                logger.error(f"  ... and {len(self.errors) - 10} more")

        logger.info("="*70)

    def generate_reports(self):
        """Generate JSON and/or HTML reports if requested"""
        if not self.report_json and not self.report_html:
            return

        stats_dict = asdict(self.stats)
        stats_dict['error_details'] = [{"file": str(p), "error": err} for p, err in self.errors]

        if self.report_json:
            try:
                with open(self.report_json, 'w', encoding='utf-8') as f:
                    json.dump(stats_dict, f, indent=2)
                logger.success(f"[OK] JSON report saved to {self.report_json}")
            except Exception as e:
                logger.error(f"[X] Could not save JSON report: {e}")

        if self.report_html:
            try:
                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Code Normalizer Pro Report</title>
    <style>
        body {{ font-family: sans-serif; margin: 2rem; background: #f9f9f9; color: #333; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f0f0f0; }}
        .errors {{ color: #d9534f; margin-top: 2rem; background: #fdf7f7; padding: 1rem; border-radius: 4px; border: 1px solid #d9534f; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Code Normalizer Pro Report</h1>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            {"".join(f"<tr><td>{k.replace('_', ' ').title()}</td><td>{v}</td></tr>" for k, v in asdict(self.stats).items())}
        </table>
"""
                if self.errors:
                    html_content += "<div class='errors'><h2>Errors</h2><ul>"
                    for path, err in self.errors:
                        html_content += f"<li><strong>{path.name}</strong>: {err}</li>"
                    html_content += "</ul></div>"

                html_content += "</div></body></html>"
                
                with open(self.report_html, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                logger.success(f"[OK] HTML report saved to {self.report_html}")
            except Exception as e:
                logger.error(f"[X] Could not save HTML report: {e}")

def process_file_worker(file_path: Path, dry_run: bool, in_place: bool,
                       create_backup: bool, check_syntax: bool,
                       syntax_timeout: int = 10, expand_tabs: int = 0,
                       max_lines: int = 0, log_file: Optional[Path] = None) -> Tuple[bool, dict, str]:
    """Worker function for parallel processing"""
    if log_file:
        logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
            level="INFO",
            enqueue=True,
        )

    try:
        normalizer = CodeNormalizer(
            dry_run=dry_run,
            in_place=in_place,
            create_backup=create_backup,
            use_cache=False,  # Cache managed by main process
            interactive=False,
            parallel=False,
            syntax_timeout=syntax_timeout,
            expand_tabs=expand_tabs,
            max_lines=max_lines,
        )

        success = normalizer.process_file(file_path, check_syntax=check_syntax)

        stats_update = {
            'processed': normalizer.stats.processed,
            'skipped': normalizer.stats.skipped,
            'encoding_changes': normalizer.stats.encoding_changes,
            'newline_fixes': normalizer.stats.newline_fixes,
            'whitespace_fixes': normalizer.stats.whitespace_fixes,
            'bytes_removed': normalizer.stats.bytes_removed,
            'syntax_checks_passed': normalizer.stats.syntax_checks_passed,
            'syntax_checks_failed': normalizer.stats.syntax_checks_failed,
        }

        error = normalizer.errors[0][1] if normalizer.errors else ""
        return success, stats_update, error
        
    except Exception:
        import traceback
        tb_str = traceback.format_exc()
        empty_stats = {
            'processed': 0, 'skipped': 0, 'encoding_changes': 0, 'newline_fixes': 0, 
            'whitespace_fixes': 0, 'bytes_removed': 0, 'syntax_checks_passed': 0, 'syntax_checks_failed': 0
        }
        return False, empty_stats, f"Worker Crash:\n{tb_str}"


def install_git_hook(hook_type: str = "pre-commit") -> bool:
    """Install pre-commit hook for automatic normalization"""
    git_dir = Path(".git")

    if not git_dir.exists():
        logger.error("[X] Not a git repository")
        return False

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    hook_path = hooks_dir / hook_type

    normalizer_script = Path(__file__).resolve()

    # Create hook script
    hook_script = f"""#!/usr/bin/env python3
# Auto-generated by code_normalizer_pro.py
import subprocess
import sys
from pathlib import Path

def main():
    # Get staged Python files
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACM"],
        capture_output=True,
        text=True
    )

    files = [
        f for f in result.stdout.strip('\\0').split('\\0')
        if f.endswith('.py') and Path(f).exists()
    ]

    if not files:
        sys.exit(0)

    print(f"[?] Checking {{len(files)}} Python file(s)...")

    # Run normalizer in check mode, one file at a time. The CLI accepts a
    # single positional path, so passing all files at once breaks argparse.
    needs_normalization = []
    for file_path in files:
        result = subprocess.run(
            [sys.executable, {repr(str(normalizer_script))}, file_path, "--dry-run"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print("\\n[X] Normalizer execution failed")
            if result.stderr.strip():
                print(result.stderr.strip())
            sys.exit(result.returncode)

        if "Would normalize:" in result.stdout:
            needs_normalization.append(file_path)

    if needs_normalization:
        print("\\n[!] Some files need normalization:")
        for file_path in needs_normalization:
            print(f" - {{file_path}}")
        print("\\nRun: uv run code-normalizer-pro <file> --in-place")
        print("Or add --no-verify to skip this check")
        sys.exit(1)

    print("[OK] All files are normalized")
    sys.exit(0)

if __name__ == "__main__":
    main()
"""

    # Write hook
    hook_path.write_text(hook_script, encoding="utf-8", newline="\n")
    hook_path.chmod(0o755)

    logger.success(f"[OK] Installed {hook_type} hook at {hook_path}")
    logger.info(f"   Hook will check Python files before commit")
    logger.info(f"   Use 'git commit --no-verify' to skip check")

    return True


app = typer.Typer(
    help="Code Normalizer Pro - Production-grade normalization tool",
    add_completion=False,
)


@app.command()
def cli_main(
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
    fail_on_changes: bool = typer.Option(False, "--fail-on-changes", help="Exit 1 when --dry-run finds files that need normalization (useful for CI pipelines)")
):

    # pyproject.toml Configuration parsing
    cfg = {}
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

    # Apply config defaults where CLI didn't override
    ext = ext or cfg.get("ext", [".py"])
    workers = workers or cfg.get("workers", max(1, cpu_count() - 1))
    expand_tabs = expand_tabs or cfg.get("expand_tabs", 0)
    max_lines = max_lines or cfg.get("max_lines", 0)
    
    if log_file is None and cfg.get("log_file"):
        log_file = Path(cfg.get("log_file"))
        
    compress_logs = compress_logs or cfg.get("compress_logs", False)

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

    # Install hook mode
    if install_hook:
        success = install_git_hook()
        sys.exit(0 if success else 1)

    # Validate
    if not path:
        logger.error("Missing argument 'PATH'. Run with --help for usage.")
        sys.exit(1)

    if output and path.is_dir():
        logger.error("--output only works with single file")
        sys.exit(1)

    if no_backup and not in_place:
        logger.warning("--no-backup has no effect without --in-place")

    if interactive and parallel:
        logger.warning("--interactive disables --parallel")
        parallel = False

    # Assemble the exclusion set: start with defaults (unless disabled),
    # then layer any user-provided --exclude entries on top.
    if no_default_excludes:
        exclude_dirs: Set[str] = set(exclude or [])
    else:
        exclude_dirs = set(DEFAULT_EXCLUDE_DIRS) | set(exclude or [])

    # Create normalizer
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
    )

    logger.info("="*70)
    logger.info("CODE NORMALIZER PRO v3.1.1")
    logger.info("="*70)

    # Process
    try:
        if path.is_dir():
            normalizer.walk_and_process(path, ext, check_syntax=check)
        else:
            if not path.exists():
                logger.error(f"File not found: {path}")
                sys.exit(1)

            normalizer.process_file(path, output, check_syntax=check)

        # Summary
        normalizer.print_summary()
        normalizer.generate_reports()

        # Exit code
        if fail_on_changes and normalizer.stats.processed > 0:
            sys.exit(1)
        sys.exit(0 if normalizer.stats.errors == 0 else 1)

    except KeyboardInterrupt:
        logger.warning("\n\n[!] Interrupted by user")
        # Persist whatever cache updates accumulated before the interrupt so
        # subsequent runs can resume without re-scanning already-processed
        # files. Best-effort -- a failure here must not mask the SIGINT exit.
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
        # Save cache here too, for the same reason as KeyboardInterrupt
        try:
            if normalizer.use_cache and normalizer.cache and not normalizer.dry_run:
                normalizer.cache.save()
        except Exception:
            pass
        sys.exit(1)


def main():
    app()


if __name__ == "__main__":
    main()
