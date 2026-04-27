# Test Report — Code Normalizer Pro v3.2.0

**Date:** 2026-04-26
**Version:** 3.2.0
**Python:** 3.10+ (tested on 3.10, 3.11, 3.12, 3.13 via CI)
**Status:** 67 passed, 0 failed, 0 errors

---

## Summary

| Metric | Value |
|--------|-------|
| Total tests | 67 |
| Passed | 67 |
| Failed | 0 |
| Errors | 0 |
| Ruff | Clean |
| Mypy | Clean |

---

## Test files

| File | Tests | Coverage area |
|------|-------|---------------|
| tests/test_code_normalize_pro.py | 63 | Core engine, CLI, safety guards |
| tests/test_launch_metrics.py | 1 | scripts/launch_metrics.py |
| tests/test_release_prep.py | 1 | scripts/release_prep.py |
| tests/test_feedback_prioritizer.py | 1 | scripts/feedback_prioritizer.py |
| tests/test_sales_pipeline_metrics.py | 1 | scripts/sales_pipeline_metrics.py |

---

## Coverage areas (test_code_normalize_pro.py)

**Encoding and normalization**
- UTF-16 detection and rewrite to UTF-8
- UTF-8 BOM stripping
- Windows-1252 detection and conversion
- CRLF to LF normalization
- Trailing whitespace removal
- Final newline enforcement
- Binary file detection and skip
- Idempotency (already-normalized files are no-ops)
- `cnp-ignore-file` directive
- `cnp: off` / `cnp: on` inline blocks
- Markdown hard-break preservation

**CLI flags**
- `--dry-run`: no writes, exits 0
- `--fail-on-changes`: exits 1 when dirty files found
- `--in-place`: rewrites files
- `--no-backup`: no sibling backup files created
- `--yes`: skips confirmation prompt non-interactively
- `--version`: prints installed version and exits
- `--parallel`: multi-worker processing
- `--log-file`: captures output to file with rotation and compression
- `--no-default-excludes`: allows scanning of normally-excluded dirs
- `--exclude`: prunes named directories
- `-e / --ext`: extension filtering
- `--output`: single-file output mode

**Safety guards**
- Git-repo guard: `--no-backup --in-place` outside git exits 1
- `--yes` override bypasses git-repo guard
- Empty-output guard: normalize_text() returning "" aborts write
- EOFError on `input()` in non-TTY environments handled gracefully

**CacheManager**
- Uncached miss forces processing
- Post-update cache hit skips reprocessing
- Cache invalidation on file change
- Cache save and load round-trip
- Deleted file handled gracefully
- Cache scoped to target directory (not CWD)

**Parallel processing**
- Parallel cache hits persisted correctly
- Worker log sinks initialized once per process (no duplicate entries)

**Reports and stats**
- `newline_fixes` and `whitespace_fixes` accounting
- Already-normalized files counted as skipped, not processed

**Other**
- Interactive mode user-decline path
- Git hook install exits nonzero outside git repo
- Backup file creation; no-backup leaves no siblings
- Confirmation prompt rejection cancels walk

---

## CI matrix

Runs on every push and pull request via `.github/workflows/ci.yml`:

| OS | Python 3.10 | Python 3.11 | Python 3.12 | Python 3.13 |
|----|-------------|-------------|-------------|-------------|
| ubuntu-latest | CI | CI | CI | CI |
| macos-latest | CI | CI | CI | CI |
| windows-latest | CI | CI | CI | CI |

Steps per matrix cell: install deps → ruff check → mypy → pytest (80% coverage gate) → CLI smoke check.
