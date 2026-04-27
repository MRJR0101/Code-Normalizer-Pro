# CODE - Quick Reference

Location: C:\Dev\PROJECTS\Code-Normalizer-Pro-CLEAN
Updated: 2026-04-26
Version: 3.2.0

---

## Run the tool

```powershell
cd C:\Dev\PROJECTS\Code-Normalizer-Pro-CLEAN

# Check installed version
code-normalizer-pro --version

# Preview without touching files
code-normalizer-pro C:\path\to\code --dry-run

# Preview and fail if normalization is needed (CI use)
code-normalizer-pro C:\path\to\code --dry-run --fail-on-changes

# Normalize in-place using all CPU cores
code-normalizer-pro C:\path\to\code --parallel --in-place

# Specific extensions only
code-normalizer-pro C:\path\to\code -e .py -e .js --in-place

# Review each file before writing
code-normalizer-pro C:\path\to\code --interactive

# Syntax check after normalizing
code-normalizer-pro C:\path\to\code --in-place --check

# Install pre-commit hook into a git repo
cd C:\your-repo
code-normalizer-pro --install-hook

# Non-interactive in-place (CI / scripting)
code-normalizer-pro C:\path\to\code --in-place --yes
```

---

## Dev workflow

```powershell
cd C:\Dev\PROJECTS\Code-Normalizer-Pro-CLEAN

# Activate venv
.\.venv\Scripts\Activate.ps1

# Run all tests
python -m pytest -v

# Run tests with coverage report
python -m pytest -q --cov=code_normalizer_pro --cov-report=term-missing

# Lint
ruff check .

# Type check
mypy code_normalizer_pro

# Smoke check installed CLI
code-normalizer-pro --version
code-normalizer-pro --help

# Re-install after code changes
pip install -e ".[dev]"
```

---

## File map

| What | Where |
|------|-------|
| Core tool v3.2.0 | code_normalizer_pro\code_normalizer_pro.py |
| CLI entry point | code_normalizer_pro\cli.py |
| Package version | code_normalizer_pro\__init__.py |
| Packaging config | pyproject.toml |
| mypyc build hook | setup.py |
| Feature docs | docs\README.md |
| Test suite | tests\test_code_normalize_pro.py (63 tests) |
| Test report | docs\TEST_REPORT.md |
| Launch checklist | docs\release\alpha_release_checklist.md |
| CHANGELOG | CHANGELOG.md |
| Status | PROJECT_STATUS.md |
| Roadmaps | roadmaps\01_solo_dev_tool.md ... 06_ai_transformation_engine.md |
| Runbook | docs\RUNBOOK.md |

---

## Build and publish

```powershell
cd C:\Dev\PROJECTS\Code-Normalizer-Pro-CLEAN

# 1. Bump version in code_normalizer_pro\__init__.py and pyproject.toml
# 2. Add CHANGELOG entry

# 3. Install build tools
pip install build twine

# 4. Build wheel + sdist
python -m build --sdist --wheel

# 5. Verify artifacts (must show no errors before uploading)
python -m twine check dist/*

# 6. Upload to TestPyPI first
python -m twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ code-normalizer-pro
code-normalizer-pro --version   # verify correct version installed

# 7. Upload to PyPI
python -m twine upload dist/*

# 8. Create GitHub Release (triggers ci.yml publish job automatically)
git tag v3.2.0
git push --tags
# Then: GitHub -> Releases -> Draft new release -> select tag -> Publish
```

---

## Release rollback

PyPI releases cannot be deleted, only yanked. If a bad release goes out:

```powershell
# Yank the bad version (makes pip skip it unless explicitly pinned)
pip install twine
twine yank code-normalizer-pro 3.2.0 --reason "critical bug in release"

# Immediately publish a patch release
# 1. Fix the bug
# 2. Bump to 3.2.1 in __init__.py and pyproject.toml
# 3. Add CHANGELOG entry
# 4. Follow the Build and publish steps above
```

For users pinned to the bad version:
```bash
pip install "code-normalizer-pro==3.2.1"   # install the patch
# or
pip install "code-normalizer-pro!=3.2.0"    # skip the yanked version
```

---

## Performance

| Cores | 100 files | 500 files | 1000 files |
|-------|-----------|-----------|------------|
| 1     | 3.2s      | 16.8s     | 33.5s      |
| 4     | 1.1s      | 4.3s      | 7.1s       |
| cached| ~0.8s     | ~2.1s     | ~2.5s      |

Resource guidance: on RAM-constrained machines (< 4 GB), use `--max-workers 2`
to limit parallel memory use. Each worker holds one file in memory at a time.

---

## Path options (roadmaps\)

Path 1 -- Solo Dev Tool -- 6 months -- $100K-500K/yr -- CHOSEN
Path 2 -- Dev Tool SaaS -- 18 months -- $1M ARR
Path 3 -- Enterprise -- 12 months -- 5-10 customers
Path 4 -- Open Source -- 24 months -- $2M ARR
Path 5 -- Grammarly model -- 18 months -- $5M ARR
Path 6 -- AI Engine -- 24 months -- deep tech
