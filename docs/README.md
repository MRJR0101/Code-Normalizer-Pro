# Code Normalizer Pro — Full Reference

**Version 3.1.1** | [PyPI](https://pypi.org/project/code-normalizer-pro/) | [GitHub](https://github.com/MRJR0101/Code-Normalizer-Pro)

---

## Install

```bash
pip install code-normalizer-pro
```

---

## What it does

Deterministic, non-semantic cleanup for source trees:

- Converts non-UTF-8 files (UTF-16, Windows-1252, Latin-1, ISO-8859-1) to UTF-8
- Normalizes CRLF and bare CR line endings to LF
- Removes trailing whitespace from every line
- Enforces a final newline at end of file
- Skips binary files automatically

All changes are structural only. The tool never alters logic, identifiers, or values.

---

## Quick Start

```bash
# Preview what would change
code-normalizer-pro . --dry-run -e .py

# Apply in place
code-normalizer-pro . --in-place -e .py

# CI gate: fail if any file needs normalization
code-normalizer-pro . --dry-run --fail-on-changes
```

---

## All CLI Options

| Flag | Description |
|------|-------------|
| `PATH` | File or directory to process (positional) |
| `-e, --ext .EXT` | Process only this extension (repeatable; default: `.py`) |
| `-o, --output FILE` | Output file — single-file mode only |
| `--dry-run` | Preview changes without writing files |
| `--fail-on-changes` | Exit 1 when `--dry-run` finds files that need normalization (CI use) |
| `--in-place` | Edit files in place |
| `--no-backup` | Skip backup creation (dangerous with `--in-place`) |
| `--check` | Run per-language syntax validation; atomic: file is written only if the pre-flight check passes |
| `--timeout, --syntax-timeout N` | Timeout in seconds per file for `--check` (default: 10) |
| `--parallel` | Multi-core processing via `ProcessPoolExecutor` |
| `--workers N` | Number of parallel workers (default: CPU count minus 1) |
| `--cache / --no-cache` | Enable or disable the SHA256 incremental cache (default: on) |
| `--interactive` | Approve changes file-by-file with diff preview |
| `--exclude DIR` | Exclude a directory name from recursive walks (repeatable) |
| `--no-default-excludes` | Disable the built-in exclusion set |
| `--no-gitignore` | Do not skip files matched by `.gitignore` |
| `--install-hook` | Install a git pre-commit hook in the current repository |
| `--report-json FILE` | Save a JSON stats report |
| `--report-html FILE` | Save an HTML stats report |
| `--expand-tabs N` | Convert leading and inline tabs to N spaces |
| `--max-lines N` | Skip files exceeding N lines |
| `--log-file FILE` | Write execution logs to a file (rotated at 5 MB, kept 3) |
| `--compress-logs` | Compress rotated log files (`.gz`) |
| `-v, --verbose` | Show detailed per-file output |

---

## Default Exclusion Set

When walking directories the following names are pruned before descending.
This prevents the tool from modifying virtual environments, build artifacts,
and third-party packages.

```
.venv  venv  env  .env  site-packages  __pycache__
.git  .hg  .svn  node_modules
.tox  .mypy_cache  .pytest_cache  .ruff_cache  .cache
dist  build  .eggs
```

Add more with `--exclude DIR`. Disable entirely with `--no-default-excludes`
(use only for surgical single-directory runs where you know what is in scope).

---

## Supported Encodings

utf-8, utf-8-sig, utf-16, utf-16-le, utf-16-be, windows-1252, latin-1, iso-8859-1

---

## Supported Syntax Checkers (`--check`)

| Language | Checker | Requirement |
|----------|---------|-------------|
| Python | `python -m py_compile` | Built-in |
| JavaScript | `node --check` | Node.js |
| TypeScript | `tsc --noEmit` | TypeScript |
| Go | `gofmt -e` | Go toolchain |
| Rust | `rustc --crate-type lib` | Rust toolchain |
| C | `gcc -fsyntax-only` | GCC |
| C++ | `g++ -fsyntax-only` | G++ |
| Java | `javac` | JDK |
| JSON | `python -m json.tool` | Built-in |
| Shell | `bash -n` | bash |
| Ruby | `ruby -c` | Ruby |
| PHP | `php -l` | PHP |
| Perl | `perl -c` | Perl |
| Lua | `luac -p` | Lua |

If a checker is not installed the file is still normalized; the syntax result
is reported as "No checker available" rather than failing the run.

---

## Safety Model

- **Dry-run by default for inspection** — `--dry-run` never writes files
- **Atomic in-place writes** — files are staged to a `.cnp-tmp` sibling,
  syntax-checked in memory, then committed via `os.replace`; if the check
  fails the original is untouched
- **Automatic timestamped backups** — created before every in-place write
  (disable with `--no-backup`)
- **Binary detection** — files with null bytes are skipped
- **Symlink / junction cycle detection** — walkers cannot infinite-loop
- **Cache persists on Ctrl-C** — interrupted runs resume without re-scanning
- **No network calls, no telemetry**

---

## Incremental Cache

The cache file (`.normalize-cache.json`) is placed beside the directory being
processed. It stores SHA256 hash, size, and mtime per file. On the next run,
files whose mtime and size match are skipped without reading content.

```bash
# Disable cache for one run
code-normalizer-pro . --in-place --no-cache
```

---

## pyproject.toml Configuration

Persist your team's defaults so you don't have to repeat CLI flags.

```toml
[tool.code-normalizer-pro]
ext         = [".py", ".js", ".ts"]
expand_tabs = 4
parallel    = true
workers     = 4
max_lines   = 10000
log_file    = "logs/normalizer.log"
compress_logs = true
```

---

## CI Integration

### GitHub Actions — normalization gate

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: pip install code-normalizer-pro
- run: code-normalizer-pro . --dry-run --fail-on-changes
```

### GitHub Actions — use the bundled action

```yaml
- uses: MRJR0101/Code-Normalizer-Pro@v3.1.1
  with:
    args: ". --dry-run --fail-on-changes"
```

### pre-commit

```yaml
repos:
  - repo: https://github.com/MRJR0101/Code-Normalizer-Pro
    rev: v3.1.1
    hooks:
      - id: code-normalizer-pro
```

---

## Git Pre-Commit Hook (built-in)

```bash
cd your-repo
code-normalizer-pro --install-hook
```

The hook checks all staged Python files in dry-run mode and blocks the commit
if any need normalization. Run `git commit --no-verify` to bypass.

---

## Interactive Mode

Review each file before writing:

```bash
code-normalizer-pro . --interactive --in-place
```

At the prompt: `y` apply, `n` skip, `d` show full diff, `q` quit.

---

## Reports

```bash
# JSON stats after a run
code-normalizer-pro . --in-place --report-json run_stats.json

# HTML stats after a run
code-normalizer-pro . --in-place --report-html run_stats.html
```

---

## Version History

### v3.1.1 (2026-04-06)
- `--fail-on-changes` flag: exit 1 from `--dry-run` when normalization is needed
- Parallel `--check` stats fixed: `syntax_checks_failed` was dropped from workers
  that returned `success=False`; now merged correctly
- `Syntax: [OK]` now surfaces the reason string (e.g. `rustc not installed`)
- Confirmation prompt accepts `y`, `yes`, any case, with surrounding whitespace
- Dead `syntax_check()` method removed; `syntax_check_text` retained

### v3.1.0 (2026-04-06)
- `--exclude DIR` and `--no-default-excludes` flags
- `DEFAULT_EXCLUDE_DIRS` set (18 common noise directories)
- `--syntax-timeout` flag
- Symlink and junction cycle detection
- Atomic in-place writes: pre-flight syntax check before any write
- Cache persisted on `KeyboardInterrupt` and fatal exceptions
- Microsecond-resolution backup filenames (parallel-safe)
- Plain ASCII console output (no Unicode symbols)
- `newline_fixes` counter corrected (no longer double-counts CRLF)
- Subprocess encoding fixed for non-UTF-8 terminals (Windows cp1252)

### v3.0.0 (2026-02-09)
- Parallel processing via `ProcessPoolExecutor`
- SHA256 incremental caching
- Pre-commit git hook generation (`--install-hook`)
- Multi-language syntax checking (Python, JS, TS, Go, Rust, C, C++, Java)
- Interactive per-file approval mode with diff preview

### v2.0.0 (2026-02-09)
- Dry-run mode, in-place editing, timestamped backups
- tqdm progress bars, detailed statistics, Windows UTF-8 fix

### v1.0.0 (2026-02-09)
- UTF-8 encoding normalization, CRLF→LF, trailing whitespace, final newline, binary skip

---

## License

MIT License — Copyright (c) 2026 Michael Rawls Jr.
