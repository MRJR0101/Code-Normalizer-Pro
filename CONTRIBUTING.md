# Contributing

## Setup
1. Create/activate a Python 3.10+ virtual environment.
2. Install dependencies:
   `python -m pip install -r requirements.txt`
3. Run tests:
   `python -m pytest -q`

## Development Workflow
1. Make focused changes.
2. Run CLI smoke checks:
   `python src/code_normalize_pro.py --help`
   `python main.py --help`
3. Update docs/tests for behavior changes.

## Release-Related Contributions
1. Build artifacts:
   `python -m build --sdist --wheel`
2. Run release readiness checker:
   `python scripts/release_prep.py`

