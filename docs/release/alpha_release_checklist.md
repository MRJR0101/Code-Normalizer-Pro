# Alpha Release Checklist

## Goal
Ship the first public alpha package for Path 1.

## Pre-Release Checks
1. Run tests:
   `python -m pytest -q`
2. Build package artifacts:
   `python -m build --sdist --wheel`
3. Validate release readiness:
   `python scripts/release_prep.py`
4. Validate package metadata:
   `python -m twine check dist/*`

## Publish Steps
1. Upload to TestPyPI:
   `python -m twine upload --repository testpypi dist/*`
2. Install and smoke test from TestPyPI in a fresh venv.
3. Upload to PyPI:
   `python -m twine upload dist/*`

## Post-Release
1. Tag release in GitHub (`v3.1.1` style).
2. Update `CHANGELOG.md` with release date.
3. Post outreach links and capture responses in `docs/launch/first_100_users.csv`.

