# code-normalizer-pro

![PyPI](https://img.shields.io/pypi/v/code-normalizer-pro?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

**code-normalizer-pro** is a Python CLI for **code normalization**, **whitespace cleanup**, **line ending normalization**, and **encoding normalization** across entire repositories.

It helps clean source trees by converting supported text files to UTF-8, normalizing CRLF/LF line endings, removing trailing whitespace, and enforcing a final newline. It is designed for codebase cleanup, CI preparation, refactoring prep, and repository hygiene.

## Install

```bash
pip install code-normalizer-pro
```

## Quick Start

Preview changes:

```bash
code-normalizer-pro . --dry-run -e .py
```

Apply changes in place:

```bash
code-normalizer-pro . --in-place -e .py
```

Run syntax checks after normalization:

```bash
code-normalizer-pro . --dry-run -e .py --check
```

## What This Tool Is For

Use `code-normalizer-pro` when you need:

- code normalization across a repository
- encoding normalization to UTF-8
- line ending normalization to LF
- whitespace cleanup before commits
- consistent source files before CI or refactoring
- reduced diff noise in Git history

## Features

- UTF-8 normalization for supported text encodings
- line ending normalization
- trailing whitespace removal
- final newline enforcement
- dry-run mode
- in-place normalization
- extension filtering
- parallel processing
- incremental caching
- interactive approval mode
- optional syntax checking
- git pre-commit hook installation

## Common Workflows

Normalize a full project:

```bash
code-normalizer-pro . --in-place
```

Normalize only Python and JavaScript files:

```bash
code-normalizer-pro . -e .py -e .js --in-place
```

Use parallel processing on a larger codebase:

```bash
code-normalizer-pro . --parallel --in-place
```

Install the pre-commit hook:

```bash
code-normalizer-pro --install-hook
```

## Before and After

Before:

```python
def add(a, b):
    return a + b
```

After:

```python
def add(a, b):
    return a + b
```

## CLI Options

| Option                          | Description                                                                        |
| ------------------------------- | ---------------------------------------------------------------------------------- |
| `--dry-run`                     | preview changes without writing files                                              |
| `--in-place`                    | modify files directly                                                              |
| `--check`                       | run syntax validation; atomic: file is only written if the pre-flight check passes |
| `--parallel`                    | enable multi-core processing                                                       |
| `--workers`                     | set worker count                                                                   |
| `--interactive`                 | approve changes per file                                                           |
| `--no-cache`                    | disable incremental cache                                                          |
| `--no-backup`                   | disable backups                                                                    |
| `--install-hook`                | install a git pre-commit hook                                                      |
| `-e, --ext`                     | process only specific extensions                                                   |
| `--exclude DIR`                 | exclude an additional directory name from walks (repeatable)                       |
| `--no-default-excludes`         | disable the built-in exclusion set (dangerous if a venv is in scope)               |
| `--timeout, --syntax-timeout N` | timeout per file for `--check` validation in seconds (default: 10)                 |
| `--report-json FILE`            | generate a JSON report of the normalization stats                                  |
| `--report-html FILE`            | generate an HTML report of the normalization stats                                 |
| `--expand-tabs N`               | convert leading and inline tabs to `N` spaces                                      |
| `--max-lines N`                 | skip files exceeding `N` lines                                                     |
| `--no-gitignore`                | do not skip files ignored by `.gitignore`                                          |
| `--log-file FILE`               | save execution logs to a file                                                      |
| `--compress-logs`               | compress rotated log files (`.gz`)                                                 |
| `-v, --verbose`                 | show detailed output                                                               |
| `--fail-on-changes`             | exit 1 when `--dry-run` finds files that need normalization (for CI pipelines)     |

## pyproject.toml Configuration

You can save your team's preferences inside a `pyproject.toml` file to avoid typing CLI arguments every time.

```toml
[tool.code-normalizer-pro]
ext = [".py", ".js"]
expand_tabs = 4
in_place = true
parallel = true
max_lines = 10000
workers = 4
compress_logs = true
```

## Bug fixes in 3.1.1

- **Parallel `--check` now counts failures correctly**: prior to
  3.1.1 the parallel path dropped `syntax_checks_failed` stats
  when a worker returned `success=False`, so the summary would
  say "0 failed" even when N files failed their pre-flight check.
- **`Syntax: [OK]` now shows the reason string** when it was not
  a real validation (e.g. `Syntax: [OK] (rustc not installed)`),
  so you can tell the difference between "actually passed" and
  "no checker was run".
- **Confirmation prompt accepts "y", "yes"**, case-insensitive
  with leading/trailing whitespace. Previously only bare "y"
  worked; "yes" was silently rejected as "no".
- **Dead `syntax_check` method removed**; `syntax_check_text`
  kept as part of the public API.
- **Removed unused `shutil` import**.
- **Double-space `[!]  ` typos fixed** in confirmation prompt
  and generated git hook script.

## Default exclusions (new in 3.1.0)

When walking directories recursively, the following directory names are
pruned by default to prevent the tool from descending into virtual
environments, build artifacts, and third-party package trees:

```
.venv, venv, env, .env, site-packages, __pycache__,
.git, .hg, .svn, node_modules,
.tox, .mypy_cache, .pytest_cache, .ruff_cache, .cache,
dist, build, .eggs
```

Use `--exclude DIR` to add more. Use `--no-default-excludes` to disable
the built-in set entirely (only recommended for surgical single-directory
runs where you know exactly what you are scanning).

## Safety

- deterministic, non-semantic cleanup only
- binary files are skipped
- dry-run mode allows safe preview
- backups are enabled by default for in-place edits
- syntax checks can validate normalized output
- default exclusion set prevents accidental descent into virtual
  environments, build artifacts, and third-party package trees
- symlink and junction cycles are detected and skipped so walkers
  never infinite-loop on cyclic directory structures
- atomic in-place writes: when `--check` is enabled, the syntax
  check runs against the normalized content in memory BEFORE any
  file is written. If the check fails, the original file is
  byte-identical to what it was before the invocation (no backup
  needed, no rollback, no partial state)
- cache is persisted on Ctrl-C so interrupted runs resume instead
  of re-scanning from scratch

## Supported Encodings

- utf-8
- utf-8-sig
- utf-16
- utf-16-le
- utf-16-be
- windows-1252
- latin-1
- iso-8859-1

## Supported Syntax Checks

- Python
- JavaScript
- TypeScript
- Go
- Rust
- C
- C++
- Java
- JSON
- Shell (bash -n)
- Ruby
- PHP
- Perl
- Lua

## Use Cases

- cleaning legacy repositories
- standardizing source files before CI
- preparing code for linting or formatting
- reducing whitespace-only diffs
- improving repository hygiene for teams
- normalizing files before AI-assisted code workflows

## License

MIT License
