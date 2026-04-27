# Architecture

## Overview

`code-normalizer-pro` is a CLI-first normalization tool that scans files, applies deterministic text normalization, and optionally validates syntax.

## Components

- `code_normalizer_pro/code_normalizer_pro.py`: Primary CLI and processing engine (v3.1.1).
- `code_normalizer_pro/cli.py`: Installed entry point; uses `runpy` to invoke the engine.
- `code_normalizer_pro/__init__.py`: Package version declaration.
- `config/settings.py`: Environment-based runtime configuration baseline (not yet wired).
- `main.py`: Root-level entry point for direct `python main.py` invocation (development convenience).
- `setup.py`: mypyc compilation hook; builds a C-extension wheel when a compiler is available.

## Execution Flow

1. `code-normalizer-pro` CLI entry point → `code_normalizer_pro.cli:main`
2. `cli.py` → `runpy.run_path(code_normalizer_pro.py)`
3. Typer app parses arguments and calls `cli_main()`
4. `cli_main()` builds a `CodeNormalizer` instance
5. `CodeNormalizer.walk_and_process()` collects files (exclude-filter + symlink guard + gitignore filter)
6. Per-file: `process_file()` → guess encoding → normalize → atomic write or dry-run output
7. Optionally: `_process_parallel()` dispatches `process_file_worker()` across `ProcessPoolExecutor`
8. `print_summary()` + optional `generate_reports()`
9. Exit 0 (clean) or 1 (errors, or `--fail-on-changes` triggered)

## Key Design Decisions

- **Atomic writes with pre-flight syntax check**: when `--check` is enabled, the syntax check runs against the in-memory normalized content before any file is written. A failing check leaves the original file byte-identical.
- **Cache placed beside target**: `.normalize-cache.json` lives next to the directory being processed so running against two different projects from the same shell never cross-contaminates.
- **mypyc compilation optional**: `setup.py` catches `ImportError` from mypyc and falls back to a pure-Python build when a C compiler or mypyc DLL is blocked by policy.

## Operational Notes

- Requires Python 3.10+.
- Runtime dependencies: `tqdm`, `typer`, `loguru`.
- Parallel mode uses `ProcessPoolExecutor`; cache is managed by the main process only.
- Default exclusion set prevents accidental descent into `.venv`, `node_modules`, etc.
