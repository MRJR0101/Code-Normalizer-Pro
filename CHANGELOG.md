# Changelog

All notable changes to this project are documented here.

## [3.1.1] - 2026-04-06

### Added

- **`--fail-on-changes` flag**: when set alongside `--dry-run`, the tool
  exits with code 1 if any files would be normalized. Enables CI pipelines
  to catch un-normalized files without writing to disk.
  Example: `code-normalizer-pro . --dry-run --fail-on-changes`

### Fixed

- **Parallel path stats merge bug (NEW-H1)**: when a worker process
  failed the pre-flight syntax check and returned `success=False`,
  `_process_parallel`'s else branch dropped the worker's
  `syntax_checks_failed` counter. The summary under-reported every
  parallel `--check` failure as zero. The aggregator now merges
  `syntax_checks_failed` and `syntax_checks_passed` from the worker's
  `stats_update` dict on both the success and failure branches.
  Regression test: `test_parallel_syntax_failure_stats_are_merged`.
- **Post-write syntax status loses the reason string (NEW-M1)**:
  after a successful atomic write with `--check`, the summary printed
  a hardcoded `Syntax: [OK]` regardless of what the pre-flight check
  actually reported. Returns like `rustc not installed` or
  `No checker available` were hidden, making the "pass" look like a
  real validation when it wasn't. Now tracks the reason string from
  the pre-flight check and surfaces it as `Syntax: [OK] (reason)`
  when the reason is anything other than plain "OK". Regression test:
  `test_syntax_reason_surfaced_for_missing_checker`.
- **Double-space typos left over from ASCII conversion (NEW-M3)**:
  the v3.1.0 bulk Unicode-to-ASCII replacement swapped `\u26a0\ufe0f`
  for `[!]` in two places but left the two trailing literal spaces
  intact, producing `[!]  In-place editing` and `[!]  Some files
  need normalization`. Both now use `[!] ` (single space).
- **Confirmation prompt rejected "yes" (pre-existing)**: the in-place
  confirmation used `if response.lower() != 'y'` which rejected
  "yes", "YES", "Yes", and any whitespace. Now accepts "y", "yes",
  and any case/whitespace variant via
  `response.strip().lower() not in ("y", "yes")`. Regression test:
  `test_confirmation_prompt_accepts_yes_variants`.

### Removed

- **Dead `syntax_check` method (NEW-M2)**: the v3.1.0 atomic-write
  refactor replaced the only internal caller with a direct
  `_run_syntax_check` call, leaving `syntax_check` as dead code.
  Removed. `syntax_check_text` is still there and still used by
  the dry-run code path.

### Changed

- **`--cache` CLI flag help text**: now accurately describes the
  flag as a no-op kept for script compatibility. The flag was
  always parsed but never read (`use_cache = not args.no_cache`
  only consulted `--no-cache`). Kept in place to avoid breaking
  any scripts that explicitly pass `--cache`. Behavior is
  unchanged.

### Test suite

- Went from 14 to 17 tests. All 17 passing.
- New tests cover the 3 correctness fixes above.

## [3.1.0] - 2026-04-06

### Added

- `--exclude DIR` CLI flag (repeatable): prune named subdirectories
  from recursive walks. Added to the built-in default set.
- `--no-default-excludes` CLI flag: disable the built-in exclusion
  set for surgical single-directory runs.
- `--syntax-timeout SECONDS` CLI flag: configurable timeout for
  `--check` syntax validation (default 10). Wired through the
  parallel worker as well.
- `DEFAULT_EXCLUDE_DIRS` constant covering 14 common noise
  directories: `.venv`, `venv`, `env`, `.env`, `site-packages`,
  `__pycache__`, `.git`, `.hg`, `.svn`, `node_modules`, `.tox`,
  `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.cache`, `dist`,
  `build`, `.eggs`.
- Symlink and junction cycle detection via `os.walk(followlinks=False)`
  plus a `visited_real` set keyed on `os.path.realpath` of each
  directory, so walkers cannot infinite-loop on cyclic trees.
- 6 new test cases: exclude-filter default, exclude-filter disabled,
  custom exclude set, atomic-write rollback on syntax failure,
  syntax-timeout wiring, symlink cycle termination.

### Changed

- **Atomic in-place writes.** Files are now staged to a
  `.cnp-tmp` sibling, syntax-checked against the in-memory content
  BEFORE any write, and then committed via `os.replace`. If the
  pre-flight syntax check fails, the original file is completely
  untouched: no backup, no rollback, no partial state.
- Cache is now persisted on `KeyboardInterrupt` and on fatal
  exceptions, so interrupted runs resume cleanly on the next
  invocation instead of re-scanning from scratch.
- `create_backup_file` uses microsecond-resolution timestamps
  (`%Y%m%d_%H%M%S_%f`) so parallel backups within the same second
  cannot silently overwrite each other.
- `_run_syntax_check` subprocess calls pass
  `encoding="utf-8", errors="replace"` explicitly, eliminating
  `UnicodeDecodeError` crashes when compilers emit non-ASCII error
  messages on Windows (cp1252 default).
- All console output is now plain ASCII. Unicode symbols
  (`U+2299`, `U+2297`, `U+2713`, `U+2717`, `U+2192`, `U+1F4C1`,
  `U+1F680`, `U+1F50D`, `U+26A0`, `U+274C`, `U+2705`) replaced with
  bracketed ASCII markers: `[C]`, `[S]`, `[+]`, `[X]`, `->`, `[*]`,
  `[>>]`, `[?]`, `[!]`, `[OK]`. No more Windows console encoding
  surprises for users with non-UTF-8 terminals.

### Fixed

- `newline_fixes` stats counter was double-counting CRLF sequences
  (once for `\r\n` and again for the `\r` inside it). Now counts
  `\r` occurrences exactly once per line ending.
- The pre-`--check` write hazard: previously the normalized file
  was written to disk, THEN syntax-checked. A failing check left
  a bad file on disk and the user had to manually restore from
  backup. Now the check runs in memory before any write.
- Timeout errors from syntax checks now report the configured
  timeout value (`"Timeout after Ns"`) instead of a bare
  `"Timeout"` string.

### Notes

- All 8 existing tests still pass (2 had to be updated for the
  ASCII output change). Test suite is now 14 tests, all passing.
- The tool can now be safely pointed at large source trees that
  contain virtual environments, as long as the default exclusions
  are left enabled (which is the default).

## [3.0.2] - 2026-03-13

### Added

- Clean repository setup with proper package structure
- code_normalizer_pro/ package (cli.py, code_normalizer_pro.py, __init__.py)
- main.py root entry point via runpy
- pyproject.toml with console_scripts entry point
- CI workflow (.github/workflows/ci.yml)
- VERIFY.md with install and test commands

## [3.0.0] - 2026-02-09

### Added

- Parallel processing via ProcessPoolExecutor (3-10x speedup on multi-core)
- SHA256 incremental caching (.normalize-cache.json)
- Pre-commit git hook generation (--install-hook)
- Multi-language syntax checking: Python, JS, TS, Go, Rust, C, C++, Java
- Interactive per-file approval mode with diff preview (--interactive)

## [2.0.0] - 2026-02-09

### Added

- Dry-run mode (--dry-run)
- In-place editing with timestamped backups (--in-place)
- tqdm progress bars
- Detailed processing statistics
- Windows UTF-8 stdout fix

### Fixed

- argparse flag parsing bug

## [1.0.0] - 2026-02-09

### Added

- UTF-8 encoding normalization (utf-8, utf-8-sig, utf-16, utf-16-le, utf-16-be, windows-1252, latin-1, iso-8859-1)
- CRLF to LF line ending conversion
- Trailing whitespace removal
- Final newline enforcement
- Binary file detection and skip
