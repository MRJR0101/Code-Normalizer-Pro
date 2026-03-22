# code-normalizer-pro

![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![PyPI](https://img.shields.io/pypi/v/code-normalizer-pro?style=flat-square)

A CLI tool that runs a deterministic, non-semantic cleanup pass over a codebase —
fixing mixed encodings, inconsistent line endings, trailing whitespace, and missing
final newlines. One command. No config required.

```bash
code-normalizer-pro . --dry-run -e .py
```

---

## What Problem It Solves

Large repositories accumulate inconsistencies over time:

- mixed encodings
- mixed line endings
- stray whitespace
- missing final newlines
- partially normalized files

These inconsistencies create noise in diffs, complicate tooling, and make automation
less reliable across editors, CI systems, and refactoring passes.

`code-normalizer-pro` provides a deterministic pass over a codebase to normalize
these issues before linting, refactoring, or automated processing.

---

## Before / After

`·` marks trailing spaces.

```text
# Before
def add(a, b):····
    return a + b····
```

```text
# After
def add(a, b):
    return a + b
```

The normalized file is written with UTF-8 encoding, LF newlines, and a final newline.

---

## Installation

Requires Python `>=3.10`

```bash
pip install code-normalizer-pro
```

With `uv`:

```bash
uv tool install code-normalizer-pro
```

Optional dev install:

```bash
pip install "code-normalizer-pro[dev]"
```

---

## Quick Start

Preview changes without modifying files:

```bash
code-normalizer-pro . --dry-run -e .py
```

Normalize files in place:

```bash
code-normalizer-pro . --in-place -e .py
```

Normalize only Python and JavaScript files:

```bash
code-normalizer-pro . -e .py -e .js --in-place
```

Run syntax checks on normalized output:

```bash
code-normalizer-pro . --dry-run -e .py --check
```

Install the git pre-commit hook:

```bash
code-normalizer-pro --install-hook
```

By default, without `--dry-run` or `--in-place`, the tool writes clean-copy outputs
beside the originals instead of overwriting source files.

---

## Typical Workflow

1. `code-normalizer-pro . --dry-run` — preview what changes
2. `code-normalizer-pro . --dry-run --check` — add syntax validation
3. `code-normalizer-pro . --in-place` — apply changes
4. Run your linter or formatter
5. Commit

This reduces formatting noise and improves deterministic tool output.

---

## Features

- recursive repository scanning
- UTF-8 normalization for supported text encodings
- consistent newline normalization to LF
- trailing whitespace cleanup
- final newline enforcement
- optional extension filtering
- dry-run mode for previewing changes
- clean-copy output mode or explicit in-place editing
- hash-based incremental caching
- parallel processing
- interactive file-by-file approval
- syntax checking on normalized output
- git pre-commit hook installation

---

## CLI Options

| Option | Description |
|--------|-------------|
| `--dry-run` | show proposed changes without writing files |
| `--in-place` | apply normalization changes to the original files |
| `-o, --output` | write a normalized copy to a specific output file |
| `-e, --ext` | restrict processing to specific file extensions |
| `--check` | run syntax checks on normalized output |
| `--parallel` | process files with multiple workers |
| `--workers` | set the worker count for parallel mode |
| `--interactive` | approve each file before applying changes |
| `--cache` | enable incremental cache behavior (default) |
| `--no-cache` | force a full rescan without cache |
| `--no-backup` | disable backups for in-place edits |
| `--install-hook` | install a git pre-commit hook |
| `-v, --verbose` | show detailed processing information |

---

## Safety

`code-normalizer-pro` is conservative by design:

- transformations are deterministic and do not change program behavior
- binary files are skipped automatically
- `--dry-run` previews changes without writing anything
- in-place mode creates backups by default unless `--no-backup` is used
- syntax checks run against normalized output without rewriting the source file

---

## Supported Encodings

`utf-8` `utf-8-sig` `utf-16` `utf-16-le` `utf-16-be` `windows-1252` `latin-1` `iso-8859-1`

## Supported Syntax Checks

`Python` `JavaScript` `TypeScript` `Go` `Rust` `C` `C++` `Java`

If a checker is not installed, the tool reports it as unavailable rather than failing the run.

---

## When to Use

- preparing a repository for automated refactoring
- cleaning legacy codebases before a linting pass
- reducing formatting noise in version control history
- standardizing files before CI runs
- making source files consistent before AI-assisted tooling

---

## License

MIT License
