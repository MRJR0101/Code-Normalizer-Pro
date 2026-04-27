# CODE - Project Status

Last updated: 2026-04-26

---

## Current state

v3.1.1 code is complete. Package scaffolding is fully in place.
Tests pass (17/17). pyproject.toml has authors, classifiers, all URLs, and
dev extras. dist/ is empty -- run `python -m build` before PyPI upload.

Path chosen: Path 1 -- Solo Dev Tool (PyPI, bootstrap, no VC).

---

## What is done

- code_normalizer_pro\code_normalizer_pro.py -- v3.1.1, 1481+ lines
- code_normalizer_pro\cli.py -- runpy entry point
- code_normalizer_pro\__init__.py -- v3.1.1 version declaration
- pyproject.toml -- packaging config, authors, classifiers, URLs, dev extras
- setup.py -- mypyc compilation hook (for compiled wheel distribution)
- requirements.txt -- tqdm, loguru, typer (runtime deps)
- .github\workflows\ci.yml -- CI: 3x3 matrix, build, publish gate
- .github\workflows\codeql.yml -- CodeQL security scanning
- .github\dependabot.yml -- weekly pip + actions updates
- tests\ -- 17 tests, all passing (pytest 9.0.2, Python 3.14)
- docs\README.md -- full feature reference
- docs\TEST_REPORT.md -- test results from 2026-02-09
- docs\launch\ -- outreach templates, user CSV, metrics JSON
- docs\sales\ -- pricing, pipeline CSV, customer offer template
- docs\release\alpha_release_checklist.md -- PyPI publish steps
- roadmaps\ -- all 6 strategic path documents
- EXECUTION_PLAN.md -- 7-day week-1 launch checklist
- SECURITY.md -- vulnerability disclosure policy (GitHub community standard)
- CODE_OF_CONDUCT.md -- Contributor Covenant v2.1 (GitHub community standard)

---

## What still needs to happen before PyPI upload

1. Run: python -m build --sdist --wheel
2. Run: python -m twine check dist/*
3. Upload to TestPyPI, install fresh, smoke test
4. Upload to PyPI, tag v3.1.1

---

## Known open bugs (non-blocking for launch)

See MISSINGMORE.txt for full list. Remaining open items:

1. config\settings.py env-var loader -- nothing imports it (wire or remove)
2. examples\ directory is empty -- populate before first marketing push

---

## Week 1 launch tasks (EXECUTION_PLAN.md)

All pending. Requires `python -m build` and TestPyPI verification first.
See EXECUTION_PLAN.md for day-by-day checklist.