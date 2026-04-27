# CODE - Quick Reference

Location: C:\Dev\PROJECTS\Code-Normalizer-Pro-CLEAN
Updated: 2026-04-26

---

## Run the tool

```powershell
cd C:\Dev\PROJECTS\Code-Normalizer-Pro-CLEAN

# Preview without touching files
python main.py C:\path\to\code --dry-run

# Preview and fail if normalization is needed (CI use)
python main.py C:\path\to\code --dry-run --fail-on-changes

# Normalize in-place using all CPU cores
python main.py C:\path\to\code --parallel --in-place

# Specific extensions only
python main.py C:\path\to\code -e .py -e .js --in-place

# Review each file before writing
python main.py C:\path\to\code --interactive

# Syntax check after normalizing
python main.py C:\path\to\code --in-place --check

# Install pre-commit hook into a git repo
cd C:\your-repo
python C:\Dev\PROJECTS\Code-Normalizer-Pro-CLEAN\main.py --install-hook
```

---

## Dev workflow

```powershell
cd C:\Dev\PROJECTS\Code-Normalizer-Pro-CLEAN

# Activate venv
.\.venv\Scripts\Activate.ps1

# Run all tests
python -m pytest -v

# Smoke check installed CLI
code-normalizer-pro --help

# Re-install after code changes
pip install -e ".[dev]"
```

---

## File map

| What | Where |
|------|-------|
| Core tool v3.1.1 | code_normalizer_pro\code_normalizer_pro.py |
| CLI entry point | code_normalizer_pro\cli.py |
| Package version | code_normalizer_pro\__init__.py |
| Packaging config | pyproject.toml |
| mypyc build hook | setup.py |
| Feature docs | docs\README.md |
| Test suite | tests\test_code_normalize_pro.py (17 tests) |
| Test report | docs\TEST_REPORT.md |
| Launch checklist | docs\release\alpha_release_checklist.md |
| CHANGELOG | CHANGELOG.md |
| Bug list | MISSINGMORE.txt |
| Status | PROJECT_STATUS.md |
| Roadmaps | roadmaps\01_solo_dev_tool.md ... 06_ai_transformation_engine.md |

---

## Build and publish

```powershell
cd C:\Dev\PROJECTS\Code-Normalizer-Pro-CLEAN

# Install build tools
pip install build twine

# Build wheel + sdist
python -m build --sdist --wheel

# Verify artifacts
python -m twine check dist/*

# Upload to TestPyPI first
python -m twine upload --repository testpypi dist/*

# Upload to PyPI
python -m twine upload dist/*

# Tag release
git tag v3.1.1 && git push --tags
```

---

## Performance

| Cores | 100 files | 500 files | 1000 files |
|-------|-----------|-----------|------------|
| 1     | 3.2s      | 16.8s     | 33.5s      |
| 4     | 1.1s      | 4.3s      | 7.1s       |
| cached| ~0.8s     | ~2.1s     | ~2.5s      |

---

## Known open bugs (see MISSINGMORE.txt)

1. --dry-run exits 0 even when violations found -- use --fail-on-changes instead (fixed in 3.1.1)
2. config\settings.py is wired to nothing -- wire or remove

---

## Path options (roadmaps\)

Path 1 -- Solo Dev Tool -- 6 months -- $100K-500K/yr -- CHOSEN
Path 2 -- Dev Tool SaaS -- 18 months -- $1M ARR
Path 3 -- Enterprise -- 12 months -- 5-10 customers
Path 4 -- Open Source -- 24 months -- $2M ARR
Path 5 -- Grammarly model -- 18 months -- $5M ARR
Path 6 -- AI Engine -- 24 months -- deep tech