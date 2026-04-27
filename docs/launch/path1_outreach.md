# Path 1 Outreach Templates

## Reddit Post Draft
Title: I built a fast code normalizer for multi-language repos (open feedback request)

Body:
I built `code-normalizer-pro` to normalize encoding/newlines/whitespace across Python, JS, TS, Go, Rust, C/C++, and Java.
It supports dry-run, parallel mode, caching, and pre-commit hooks.

I am looking for real project feedback:
- Is setup clear?
- What would block you from using it in CI?
- Which language workflow should I prioritize next?

Quick start:
1. `pip install code-normalizer-pro` (after publish)
2. `code-normalizer-pro . --dry-run`
3. `code-normalizer-pro . --parallel --in-place`

## Hacker News Post Draft
Title: Show HN: Code Normalizer Pro (parallel + cached normalization for multi-language repos)

Body:
Built a CLI that standardizes encoding/newlines/whitespace and supports syntax checks across multiple languages.
Primary focus is practical repository hygiene and predictable diffs.

Would value feedback on:
- CI usage patterns
- pre-commit integration expectations
- missing language/tooling support

## Dev.to Article Outline
1. Problem: noisy diffs from encoding/newline/whitespace drift.
2. Solution: deterministic normalization workflow.
3. Demo: dry-run, in-place, parallel, cache.
4. CI + pre-commit integration.
5. Lessons learned and roadmap.

