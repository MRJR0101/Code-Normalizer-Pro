# Architecture

## Overview
`CODE` is a CLI-first normalization tool that scans files, applies deterministic text normalization, and optionally validates syntax.

## Components
- `src/code_normalize_pro.py`: Primary CLI and processing engine.
- `src/code_normalize_v2.py`: Stable legacy variant.
- `config/settings.py`: Environment-based runtime configuration baseline.
- `main.py`: Root entry point that dispatches into the primary CLI.

## Execution Flow
1. Parse CLI arguments.
2. Discover target files by extension.
3. Normalize encoding/newlines/whitespace.
4. Optionally run syntax checks.
5. Emit summary stats and optional reports.

## Operational Notes
- Designed to run with Python 3.10+.
- Supports dry-run and in-place modes.
- Can run parallel processing for larger repositories.

