#!/usr/bin/env bash
# examples/normalize_repo.sh
#
# One-shot normalization of a whole repository.
# Adjust extensions to match your stack.
#
# Usage:
#   bash examples/normalize_repo.sh            # dry-run (safe, no writes)
#   bash examples/normalize_repo.sh --apply    # actually normalize files

set -euo pipefail

DRY_RUN="--dry-run"
if [[ "${1:-}" == "--apply" ]]; then
  DRY_RUN=""
  echo "Running in APPLY mode — files will be modified."
else
  echo "Running in DRY-RUN mode — no files will be changed."
  echo "Pass --apply to write changes."
fi

# Normalize Python, JavaScript/TypeScript, and Go source files
code-normalizer-pro . $DRY_RUN \
  -e .py \
  -e .js -e .ts -e .jsx -e .tsx \
  -e .go \
  --workers 4 \
  --verbose

# Normalize text-based config and documentation files
code-normalizer-pro . $DRY_RUN \
  -e .md \
  -e .yml -e .yaml \
  -e .toml -e .ini -e .cfg \
  --workers 4
