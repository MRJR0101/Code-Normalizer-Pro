# VERIFY — Code Normalizer Pro v3.2.0

Run these steps in order to confirm the project is healthy after any change.

---

## 1. Environment setup

```powershell
cd <your-project-directory>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

---

## 2. Run the test suite

```powershell
python -m pytest -v
```

Expected: all tests passed, 0 failed, 0 errors.

```powershell
# With coverage report
python -m pytest -q --cov=code_normalizer_pro --cov-report=term-missing
```

Expected: coverage >= 80%.

---

## 3. Lint and type checks

```powershell
ruff check .
mypy code_normalizer_pro
```

Expected: `All checks passed!` from ruff; no errors from mypy.

---

## 4. CLI smoke checks

```powershell
# Version
code-normalizer-pro --version

# Help
code-normalizer-pro --help

# Dry-run against the project itself
code-normalizer-pro . --dry-run -e .py

# Dry-run with CI exit gate (should exit 0 if project is already normalized)
code-normalizer-pro . --dry-run --fail-on-changes -e .py

# Parallel mode
code-normalizer-pro . --dry-run --parallel -e .py

# Syntax check mode against any .py file
code-normalizer-pro <path-to-file>.py --dry-run --check
```

---

## 5. Build verification

```powershell
pip install build twine
python -m build --sdist --wheel
python -m twine check dist\*
```

Expected: `Checking dist\...: PASSED` for both the `.whl` and `.tar.gz`.

Inspect the wheel contents to confirm all package files are present:

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

## 6. Git status

```powershell
git status
git log --oneline -5
```

Expected: clean working tree, HEAD at v3.2.0 commit.
