# Alpha Release Checklist

## Goal
Ship the first public alpha package for Path 1.

## Pre-Release Checks
1. Run tests (all 67 must pass):
   `python -m pytest -q`
2. Lint and type check:
   `ruff check . && mypy code_normalizer_pro`
3. Build package artifacts:
   `python -m build --sdist --wheel`
4. Validate release readiness:
   `python scripts/release_prep.py`
5. Validate package metadata:
   `python -m twine check dist/*`

## Publish Steps
1. Upload to TestPyPI:
   `python -m twine upload --repository testpypi dist/*`
2. Install and smoke test from TestPyPI in a fresh venv:
   `pip install -i https://test.pypi.org/simple/ code-normalizer-pro`
   `code-normalizer-pro --version`
3. Upload to PyPI:
   `python -m twine upload dist/*`

## Post-Release
1. Create GitHub Release for `v3.2.0` (triggers CI publish job automatically).
2. Tag: `git tag v3.2.0 && git push --tags`
3. Post outreach links and capture responses in `docs/launch/first_100_users.csv`.

