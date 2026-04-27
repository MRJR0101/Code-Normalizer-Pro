# VERIFY — Code Normalizer Pro v3.1.1

Run these steps in order to confirm the project is healthy after any change.

---

## 1. Environment setup

```powershell
cd C:\Dev\PROJECTS\Code-Normalizer-Pro-CLEAN
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

---

## 2. Run the test suite

```powershell
python -m pytest -v
```

Expected: 17 passed, 0 failed, 0 errors.

---

## 3. CLI smoke checks

```powershell
# Help
code-normalizer-pro --help

# Dry-run against the project itself
code-normalizer-pro . --dry-run -e .py

# Dry-run with CI exit gate (should exit 0 if project is already normalized)
code-normalizer-pro . --dry-run --fail-on-changes -e .py

# Parallel mode
code-normalizer-pro . --dry-run --parallel -e .py

# Syntax check mode
code-normalizer-pro files\smoke_case.py --dry-run --check
```

---

## 4. Build verification

```powershell
pip install build twine
python -m build --sdist --wheel
python -m twine check dist\*
```

Expected: `Checking dist\...: PASSED` for both the `.whl` and `.tar.gz`.

Inspect the wheel contents to confirm all three package files are present:

```powershell
python -c "
import zipfile
from pathlib import Path
whl = list(Path('dist').glob('*.whl'))[0]
with zipfile.ZipFile(whl) as z:
    [print(n) for n in sorted(z.namelist())]
"
```

Expected entries: `code_normalizer_pro/__init__.py`, `code_normalizer_pro/cli.py`,
`code_normalizer_pro/code_normalizer_pro.py`.

---

## 5. Release readiness check

```powershell
python scripts\release_prep.py
```

Expected: `ready_for_alpha_release: true`.

---

## 6. Git status

```powershell
git status
git log --oneline -5
```

Expected: clean working tree, at least 2 commits on `main`.