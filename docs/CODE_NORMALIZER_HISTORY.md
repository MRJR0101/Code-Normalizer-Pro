# Code Normalizer History

This note exists to stop lineage drift and rediscovery.

It captures the observed evolution of the code normalizer family as of
March 13, 2026, based on the current repo, PyPI packaging layout, and older
historical copies found elsewhere in the PyToolbelt tree.

## Current Source Of Truth

The current working source of truth is:

- `CODE/src/code_normalize_pro.py`

The packaged distribution copy is:

- `CODE/code_normalizer_pro/code_normalize_pro.py`

That packaged copy is currently a mirror of the same Pro engine, not a separate
product line.

## Naming Split

There are two naming conventions in play:

- `code_normalize_*` is the script/engine naming lineage
- `code_normalizer_pro` / `code-normalizer-pro` is the package/product naming

That split is why the repo can feel like it contains both "normalize" and
"normalizer" versions of the same tool.

## Historical Lineage

Observed lineage:

1. `CodeNormalizeUTF8/code_normalize.py`
2. `CodeNormalizeUTF8/code_normalize_enhanced.py`
3. `CODE/src/code_normalize_v2.py`
4. `CodeNormalizeUTF8/code_normalize_pro.py`
5. `CODE/src/code_normalize_pro.py`
6. `CODE/code_normalizer_pro/code_normalize_pro.py`
7. PyPI package `code-normalizer-pro`

## Important Historical Paths

Older historical snapshot found outside the active repo:

- `C:\Dev\PROJECTS\00_PyToolbelt\08_Linters\AssessmentInbox\devwide\incoming\PROJECTS\00_PyToolbelt\05_CodeQuality\02_Linting\CodeNormalizeUTF8`

That folder contains:

- `code_normalize.py`
- `code_normalize_enhanced.py`
- `code_normalize_pro.py`

This appears to be a historical snapshot or imported assessment copy, not the
current canonical source of truth.

## What The Comparison Showed

- `code_normalize_enhanced.py` and `CODE/src/code_normalize_v2.py` are nearly
  identical and clearly in the same direct line.
- The older `code_normalize_pro.py` and current `CODE/src/code_normalize_pro.py`
  are also clearly in the same line, with the current file containing later
  additions and fixes.
- The current packaged copy under `CODE/code_normalizer_pro/` is a distribution
  mirror of the current Pro engine.

## Inherited Regression Note

One confirmed bug was inherited forward from the older lineage:

- clean non-UTF-8 files could be skipped as "already normalized" if their text
  content did not change after decoding

Reason:

- the older code checked `if text == normalized` before deciding whether work
  was needed
- the actual UTF-8 rewrite happened later

This meant a clean UTF-16 file could remain UTF-16 while being reported as
already normalized.

That bug existed in the older historical copies and was not newly introduced in
the current repo.

## Practical Rule

Until the repo is structurally cleaned up, treat these locations as follows:

- `CODE/src/code_normalize_pro.py` is the authoritative implementation
- `CODE/code_normalizer_pro/code_normalize_pro.py` is the packaged mirror
- `CODE/src/code_normalize_v2.py` is legacy reference
- `CodeNormalizeUTF8/...` is historical context, not the place to continue work

## Open Cleanup Questions

- Should the package copy continue to exist as a separate mirrored file?
- Should the v2 reference remain in-tree once the lineage is documented elsewhere?
- Should older assessment snapshots be indexed somewhere so they stop feeling
  like vanished code?

Append more findings here when new historical links turn up.
