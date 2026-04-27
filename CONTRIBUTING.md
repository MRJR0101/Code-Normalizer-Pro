# Contributing

## Setup

1. Create and activate a Python 3.10+ virtual environment.
2. Install the package and dev dependencies:
   ```powershell
   pip install -e ".[dev]"
   ```
3. Run the test suite to confirm a clean baseline:
   ```powershell
   python -m pytest -v
   ```

## Development Workflow

1. Make focused, surgical changes.
2. Run the CLI smoke checks:
   ```powershell
   code-normalizer-pro --help
   code-normalizer-pro . --dry-run -e .py
   ```
3. Update `tests/` and `CHANGELOG.md` for any behavior change.
4. Run tests again before opening a PR.

## Refactor Rules

Large refactors follow the REFACTOR_LAW.txt workflow:
snapshot first, work on a temp copy, verify, then patch the live file.

## Release-Related Contributions

1. Build artifacts:
   ```powershell
   python -m build --sdist --wheel
   python -m twine check dist/*
   ```
2. Run the release readiness checker:
   ```powershell
   python scripts/release_prep.py
   ```
