# I built a CLI to fix the encoding/newline/whitespace noise that pollutes your diffs

Every team I have worked on eventually hits the same invisible problem.

Someone on Windows commits a file. Someone on Mac pulls it. The diff shows 200 changed lines.
Nothing actually changed. It was trailing spaces, CRLF endings, a BOM, a file that got
re-saved in a different encoding. The code review is useless because the real changes are
buried in whitespace noise.

I got tired of fixing this manually on every project, so I built
[code-normalizer-pro](https://pypi.org/project/code-normalizer-pro/) -- a CLI that handles
all of it in one pass.

---

## What it does

One command normalizes an entire directory:

- Converts encoding to UTF-8 (handles UTF-16, UTF-8-BOM, Windows-1252, Latin-1, and more)
- Fixes line endings -- CRLF to LF
- Strips trailing whitespace from every line
- Ensures a single newline at end of file
- Skips binary files automatically

It works on Python, JavaScript, TypeScript, Go, Rust, C, C++, and Java files.

---

## Install

```
pip install code-normalizer-pro
```

Requires Python 3.10+. Core has zero dependencies beyond tqdm for progress bars.

---

## Basic usage

```
# See what would change without touching anything
code-normalizer-pro /path/to/project --dry-run

# Fix everything in-place
code-normalizer-pro /path/to/project --in-place

# Specific extensions only
code-normalizer-pro /path/to/project -e .py -e .js --in-place
```

Dry-run output looks like this:

```
Scanning /path/to/project...
  [changed] src/utils.py  -- trailing whitespace (34 chars), CRLF endings
  [changed] src/main.js   -- encoding: windows-1252 -> utf-8
  [skip]    assets/logo.png -- binary
  [ok]      tests/test_core.py

Total: 47 files | 2 changed | 1 skipped | 44 already clean
```

Nothing is written in dry-run mode. You see exactly what would happen.


---

## Parallel processing for large codebases

Sequential mode processes about 20-30 files per second. For a monorepo that is fine.
For anything over a few thousand files, use parallel mode:

```
code-normalizer-pro /path/to/project --parallel --in-place
```

It uses all available CPU cores by default. You can cap it:

```
code-normalizer-pro /path/to/project --parallel --workers 4 --in-place
```

Benchmarks on a Python codebase averaging 200 lines per file:

| Mode          | 100 files | 500 files | 1000 files |
|---------------|-----------|-----------|------------|
| Sequential    | 3.2s      | 16.8s     | 33.5s      |
| Parallel (4)  | 1.1s      | 4.3s      | 7.1s       |
| Parallel (8)  | 0.8s      | 2.9s      | 4.8s       |

---

## SHA256 caching for repeat runs

On the first run it processes everything and writes a `.normalize-cache.json` file.
On every run after that, unchanged files are skipped entirely.

```
code-normalizer-pro /path/to/project --cache --in-place --parallel
```

Second run output:

```
All discovered files were unchanged and skipped by cache.
Cached hits: 1000
Total runtime: 0.8s
```

This matters a lot in CI. If your normalize step runs on every push but only 5 files
actually changed, it finishes in under a second instead of 30.

---

## Pre-commit hook

This is the part that actually enforces standards across a team.

```
# Run once inside any git repo
code-normalizer-pro --install-hook
```

That writes a pre-commit hook that checks staged files before every commit.
If any file needs normalization, the commit is blocked and the fix command is printed:

```
Checking 5 staged file(s)...

Files that need normalization:
  src/feature.py
  src/utils.js

Run: code-normalizer-pro src/feature.py src/utils.js --in-place
Or:  git commit --no-verify  (to skip this check)
```

The developer fixes the files, re-stages, and commits. No config file required.
The hook uses the Python interpreter that installed the package, so it works
in virtualenvs without extra setup.


---

## CI integration

Add a normalization check to your pipeline in about 10 lines.

**GitHub Actions:**

```yaml
name: Code hygiene check

on: [push, pull_request]

jobs:
  normalize-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install code-normalizer-pro
      - run: code-normalizer-pro . --dry-run --parallel
```

The `--dry-run` flag currently exits 0 regardless of whether it finds violations.
A `--fail-on-changes` flag is on the roadmap -- for now, if you need CI to fail on
violations, you can grep the output for "changed" and exit 1 accordingly. I will
document the workaround in the README until the flag ships.

---

## Interactive mode

If you are normalizing a codebase for the first time and want to review each change
before it gets written:

```
code-normalizer-pro /path/to/project --interactive
```

It shows a diff for each file and waits for `y / n / d (show full diff) / q (quit)`.
Useful when you are not sure what you are about to change in a legacy codebase.

---

## What I learned building this

**Encoding detection is hard.** UTF-16 files without a BOM are indistinguishable from
binary garbage unless you do heuristic analysis. I ended up with a layered approach --
check for BOM first, then try a candidate list in order, then fall back to binary
detection. There are still edge cases.

**ProcessPoolExecutor and in-place writes need careful handling.** When you spawn
workers, backup creation has to happen before dispatch -- not inside the worker --
otherwise parallel mode silently skips backups. This is a known bug in the current
release that I am fixing next.

**Cache path matters.** The cache file should live next to the target directory,
not in CWD. If you run the tool from a different working directory each time, the
cache never hits. Also on the fix list.

---

## Current state and roadmap

This is v3.0.1-alpha.1. It works and I use it on my own projects daily.
These are the rough edges I am actively fixing:

- `--parallel --in-place` skips backups (data safety issue -- high priority)
- Cache file lands in CWD instead of target directory
- `--dry-run` exits 0 even when violations are found (need `--fail-on-changes`)
- No `--version` flag yet

**Coming next:**
- `.gitignore` pattern support (skip files the project already ignores)
- `--git-staged` mode (normalize only what is staged, like the pre-commit hook does)
- `--fail-on-changes` for CI
- `--version` flag

---

## Try it and tell me what is missing

```
pip install code-normalizer-pro
code-normalizer-pro . --dry-run
```

The two things I want to know from anyone who tries it:

1. Does it work in your CI setup? If it broke something, I want to know exactly how.
2. What language or workflow is missing that would make this useful to you?

Source is on GitHub: https://github.com/MRJR0101/code-normalizer-pro

If you hit a bug or have a feature request, open an issue. I respond to everything.

---

*Built with Python 3.10+. Zero required external dependencies except tqdm.*
*MIT license.*
