# CODE - Project Status

Last updated: 2026-04-26

---

## Current state

v3.2.0 code is complete. 63/67 tests passing. ruff and mypy both clean.
dist/ is empty -- run `python -m build` before PyPI upload.

Path chosen: Path 1 -- Solo Dev Tool (PyPI, bootstrap, no VC).

---

## What is done

**Core package**
- code_normalizer_pro\code_normalizer_pro.py -- v3.2.0, ~1530 lines
- code_normalizer_pro\cli.py -- runpy entry point
- code_normalizer_pro\__init__.py -- v3.2.0 version declaration
- code_normalizer_pro\py.typed -- PEP 561 marker for mypy consumers

**Packaging and build**
- pyproject.toml -- packaging config, authors, classifiers, URLs, dev extras
  (ruff>=0.4 and mypy>=1.0 added to dev extras in 3.2.0)
- setup.py -- mypyc compilation hook (graceful fallback for pure-Python wheel)
- requirements.txt -- tqdm, loguru, typer (runtime deps)
- uv.lock -- dependency lockfile

**CI / security**
- .github\workflows\ci.yml -- 3 OS x 4 Python matrix; ruff + mypy + pytest
  (80% coverage gate); build_wheels; build_sdist; publish on GitHub Release
- .github\workflows\codeql.yml -- CodeQL security scanning (weekly + PR)
- .github\dependabot.yml -- weekly pip + actions updates

**Tests**
- tests\test_code_normalize_pro.py -- 67 tests, all passing (pytest 9.0.2)
  Covers: normalize_text, process_file, CacheManager, all CLI flags,
  safety guards (git-repo guard, --yes bypass, empty-output guard, EOFError),
  parallel worker deduplication, BOM stripping, windows-1252 detection,
  interactive mode, dry-run, --fail-on-changes, log rotation.

**Documentation**
- README.md -- quick start, CLI table (incl. --version, --yes), non-goals section
- CHANGELOG.md -- full version history 1.0.0 through 3.2.0
- QUICK_REFERENCE.md -- dev commands, build/publish steps, release rollback
- docs\README.md -- full feature reference
- docs\RUNBOOK.md -- troubleshooting, backup restore, cache reset (new in 3.2.0)
- docs\ARCHITECTURE.md -- component map and execution flow
- docs\TEST_REPORT.md -- test results snapshot
- docs\launch\ -- outreach templates, user CSV, metrics JSON
- docs\sales\ -- pricing, pipeline CSV, customer offer template
- docs\release\alpha_release_checklist.md -- PyPI publish steps
- roadmaps\ -- all 6 strategic path documents
- EXECUTION_PLAN.md -- 7-day week-1 launch checklist
- SECURITY.md -- vulnerability disclosure policy
- CODE_OF_CONDUCT.md -- Contributor Covenant v2.1
- PROJECT_CHECKLIST.md -- 13-category launch readiness checklist (current)
- MISSINGMORE.txt -- open items and launch task sequence

**Safety hardening (added in 3.2.0)**
- --yes / -y flag: skips confirmation prompt for CI/scripting
- Git-repo guard: --no-backup outside git exits 1 unless --yes
- Empty-output guard: normalize_text() returning "" aborts write
- Cache schema version: _schema_version field prevents silent corruption
- --version flag: prints installed version and exits

---

## What still needs to happen before PyPI upload

1. Run: python -m build --sdist --wheel
2. Run: python -m twine check dist/*
3. Upload to TestPyPI, install fresh in clean venv, smoke test
4. Upload to PyPI, create GitHub Release for v3.2.0 (triggers CI publish job)

---

## Known open items (non-blocking for launch)

1. examples\ directory is empty -- populate before first marketing push
   (see MISSINGMORE.txt item 9 for suggested files)

---

## Week 1 launch tasks (EXECUTION_PLAN.md)

Items 10-17 in MISSINGMORE.txt. Build + TestPyPI verification (items 10-12)
must happen first. See EXECUTION_PLAN.md for day-by-day detail.
