# Code-Normalizer-Pro — Future-Proof Strategy
**Generated:** 2026-04-26  
**Current version:** v3.2.0 — Pre-PyPI launch, Path 1 (Solo Dev Tool)  
**Engine:** `code_normalizer_pro.py` — 1,582 lines, single-module CLI  

---

## Evolution Timeline

```
V1.0 (NOW — v3.2.0): Single-file CLI engine
├── Works for:        ~10K files per run, single developer
├── Processing:       ProcessPoolExecutor (single machine, all cores)
├── Caching:          JSON flat file (.normalize-cache.json)
├── Config:           CLI flags only (no config file)
├── Distribution:     PyPI pip install
├── Bottleneck #1:    1,582-line monolith — can't grow without pain
├── Bottleneck #2:    No config file — flags don't survive CI/team reuse
└── Technical debt:   config/settings.py "not yet wired", cli.py runpy coupling

V2.0 (3–6 months): Modular CLI + Config + VS Code Extension
├── Works for:        ~100K files, team adoption, CI integration
├── Upgrade:          Split monolith into focused modules (see below)
├── Upgrade:          pyproject.toml [tool.code-normalizer-pro] config section
├── Upgrade:          VS Code extension (calls CLI, shows inline results)
├── Upgrade:          Opt-in telemetry (local report command only)
├── Upgrade:          Plugin-ready syntax checker interface
├── Bottleneck #1:    JSON cache becomes slow at ~50K+ file repos
└── Bottleneck #2:    No API — can't build team dashboard without one

V3.0 (6–12 months): API + Team Dashboard + Policy Engine (Path 2/3)
├── Works for:        Organizations, 100–1,000 developers
├── Upgrade:          REST API wrapping the core engine
├── Upgrade:          Team policy configs (org-wide settings stored server-side)
├── Upgrade:          Web dashboard showing normalization debt per repo
├── Upgrade:          Auth (JWT/OAuth), per-user API keys
├── Upgrade:          SQLite → PostgreSQL for normalization history
├── Bottleneck #1:    Single-server architecture hits wall at ~10K req/day
└── Bottleneck #2:    No rule plugin marketplace (Grammarly path blocked)

V4.0 (12–24 months): Rule Engine + AI Transformation + Enterprise
├── Works for:        Enterprise compliance, large CI farms, 10K+ developers
├── Upgrade:          Plugin marketplace for custom normalization rules
├── Upgrade:          AI-backed semantic suggestions (Path 6 direction)
├── Upgrade:          Event streaming for large pipeline integration
├── Upgrade:          SSO, audit logs, SOC 2 readiness (Path 3)
└── Scale ceiling:    Organizational complexity, sales cycle length
```

---

## Breaking Points

```
WILL BREAK AT:

1. 1,582-line monolith (adding VS Code extension or API to it)
   └→ The refactor that hurts most because it touches everything
   └→ Solution: Split NOW into modules before any new surface is added
   └→ Target module split (see Abstraction Strategy below)

2. ~50K files / run (JSON cache write performance)
   └→ Large monorepos hit multi-second parse/write on .normalize-cache.json
   └→ Solution: SQLite-backed cache with the same FileCache interface
   └→ Abstract NOW; swap the backend when you feel it

3. No config file (team/CI adoption)
   └→ Users can't commit shared normalization settings — CI flags drift
   └→ Solution: Read [tool.code-normalizer-pro] from pyproject.toml (v2.0)
   └→ This is the #1 friction point before paying customers appear

4. CLI-only surface (VS Code extension, API, CI action)
   └→ All three depend on the same core engine being importable as a library
   └→ Currently the engine is a runpy-launched script, not an importable module
   └→ Solution: Decouple engine class from CLI entry point (v2.0 module split)

5. Hardcoded SYNTAX_CHECKERS dict (new language support)
   └→ Every new language requires editing source code
   └→ Solution: Make syntax checker interface pluggable (v2.0, low effort)

6. No telemetry (can't measure product-market fit)
   └→ You don't know which flags users actually use, what breaks, what's slow
   └→ Solution: Opt-in local usage report (counts only, no file content)
   └→ Needed before deciding Path 2 vs Path 3 pivot

7. ProcessPoolExecutor single-machine ceiling (distributed CI farms)
   └→ Not relevant for Path 1; only matters at Path 3 enterprise scale
   └→ Solution: Worker queue (Redis/Celery) when you actually need it
```

---

## Abstraction Strategy

```
ABSTRACT NOW (low cost, high future value):

✓ Cache interface
    Current:  CacheManager writes/reads JSON directly
    Abstract: CacheBackend protocol with JsonCache and SqliteCache implementations
    Benefit:  Swap backend for large repos without touching engine logic
    Effort:   ~2 hours

✓ Syntax checker interface
    Current:  SYNTAX_CHECKERS is a hardcoded module-level dict
    Abstract: SyntaxChecker protocol / registry with a register() hook
    Benefit:  Users can add languages without forking the project
    Effort:   ~1 hour

✓ Config loading
    Current:  CLI flags only; config/settings.py exists but is not wired
    Abstract: ConfigLoader that merges pyproject.toml → env vars → CLI flags
    Benefit:  Teams can commit shared settings; CI just calls the tool
    Effort:   ~3 hours

✓ Normalizer core as importable library
    Current:  cli.py uses runpy to launch code_normalizer_pro.py as a script
    Abstract: CodeNormalizer class exposed cleanly from __init__.py
    Benefit:  VS Code extension, API, and CI action all import the same class
    Effort:   ~1 hour (the class already exists — just fix the import chain)

DON'T ABSTRACT YET:

✗ HTTP/API layer (not needed until Path 2 adoption signal)
✗ Auth/JWT (no multi-user until $5K MRR threshold from Path 1 roadmap)
✗ Plugin marketplace (premature until users ask for custom rule hooks)
✗ Database (SQLite cache is fine until 50K-file repos appear in feedback)
✗ Deployment / containerization (Dockerfile exists but don't over-invest yet)

WHEN TO ABSTRACT (the real trigger):
  - When the same pattern appears in 3+ places
  - When a new surface (VS Code, API) REQUIRES the interface
  - When user feedback identifies the missing seam
  - NOT "just in case"
```

---

## The Module Split — Do This Before v2.0 Feature Work

The monolith is 1,582 lines today. Every new feature makes the split harder.  
The REFACTOR_LAW.txt already captures the right discipline — apply it here.

```
CURRENT:
  code_normalizer_pro/
  └── code_normalizer_pro.py  ← 1,582 lines, everything in here

TARGET (v2.0 module layout):
  code_normalizer_pro/
  ├── __init__.py              ← exposes CodeNormalizer, __version__
  ├── cli.py                   ← Typer app only; imports from engine
  ├── engine/
  │   ├── normalizer.py        ← normalize_text(), process_file(), CodeNormalizer class
  │   ├── cache.py             ← CacheManager, FileCache, CacheBackend protocol
  │   ├── checkers.py          ← SYNTAX_CHECKERS registry, _run_syntax_check()
  │   ├── walker.py            ← walk_and_process(), gitignore filter, symlink guard
  │   └── reporter.py          ← print_summary(), generate_reports(), ProcessStats
  └── config.py                ← ConfigLoader (pyproject.toml + env + CLI merge)

SPLIT ORDER (safest sequence per REFACTOR_LAW):
  1. reporter.py  ← pure data structures, no side effects, easiest to extract
  2. cache.py     ← isolated by CacheManager boundary, add protocol here
  3. checkers.py  ← dict becomes a registry; no logic change
  4. walker.py    ← pulls from normalizer, do after normalizer is stable
  5. normalizer.py ← the hard one; do last, keep tests green throughout
  6. config.py    ← new file, wires pyproject.toml reading
```

---

## Technical Debt Map

```
ACCEPTABLE DEBT — fix at the right milestone:

  ► 1,582-line monolith
    Fix by: Before adding VS Code extension or API (v2.0 prerequisite)
    Risk if ignored: Each new feature takes 3× longer to add safely

  ► JSON cache (flat file)
    Fix by: When a user reports slowness on a large monorepo
    Risk if ignored: Silent slowness on repos >50K files

  ► ProcessPoolExecutor single-machine ceiling
    Fix by: Path 3 enterprise scale (not relevant for Path 1)
    Risk if ignored: None for current target users

  ► cli.py runpy coupling
    Fix by: During module split (free fix, very low effort)
    Risk if ignored: VS Code extension can't import engine cleanly

UNACCEPTABLE DEBT — address before or during v2.0:

  ✗ config/settings.py "not yet wired"
    Impact: Teams cannot share normalization settings across developers
    Fix:    Wire ConfigLoader as part of v2.0 (3 hours max)

  ✗ No telemetry whatsoever
    Impact: You cannot make a data-driven Path 1 → Path 2 decision
    Fix:    Add opt-in local usage counter (no network, counts only)
    Why now: Needed before you hit the 100-user milestone from roadmap

  ✗ 4 failing tests (63/67 passing)
    Impact: CI is not fully green before PyPI launch — first impression risk
    Fix:    Before the PyPI upload, not after

WHEN DEBT BECOMES A CRISIS:
  - You can't add VS Code extension without touching 500+ lines (monolith)
  - New team member takes >1 day to understand the file structure
  - Fixing one feature breaks two others (signals missing module boundaries)
  - Paying users ask for team config sharing and there's no way to do it
```

---

## Scaling Triggers — What Signal = What Action

```
SIGNAL                              ACTION
─────────────────────────────────────────────────────────────────────
100 users reached                → Add opt-in telemetry report command
First team/company usage          → Wire pyproject.toml config section
User reports slowness (large repo)→ Swap cache to SQLite backend
User requests new language support→ Expose SyntaxChecker plugin hook
$5K MRR                           → Evaluate Path 2 (SaaS API) seriously
VS Code extension in demand        → Do module split first, then build it
Enterprise inbound interest        → Path 3 checklist (SSO, audit logs)
AI refactoring requests            → Path 6 spike; evaluation harness needed
```

---

## Design Decisions With Future in Mind

### Config file — add it before teams adopt

```
TODAY:    code-normalizer-pro . --in-place -e .py -e .js --no-backup
v2.0:     [tool.code-normalizer-pro] in pyproject.toml
          extensions = [".py", ".js"]
          no_backup = false
          parallel = true

Why now: A team of 3 can't share CLI flags. Config is the unlock for
         team adoption, which is the unlock for the paid tier.
```

### Cache backend — abstract the interface, keep the implementation

```
TODAY:    CacheManager writes JSON directly
v2.0:     CacheManager accepts a CacheBackend (JsonCache by default)
v3.0:     SqliteCache when large repos signal the need

The interface is one protocol class.
The swap is one line in the constructor.
The cost of not doing it: rewrite CacheManager under load.
```

### VS Code extension architecture

```
WRONG:    Shell out to the CLI, parse stdout
RIGHT:    Import CodeNormalizer as a Python library via the VS Code
          Python extension API (no subprocess, no stdout parsing)

Prerequisite: Module split so CodeNormalizer is a clean importable class.
This is why the split is a prerequisite, not optional.
```

---

## Anti-Patterns to Avoid

```
✗ Building the SaaS API before 100 paying users ask for team features
  You're on Path 1. Stay there until the exit criteria ($5K MRR) trigger.

✗ Adding AI transformation before you understand the core user pain
  Path 6 is a vision, not a next step. The telemetry you add in v2.0
  will tell you whether users want smarter rules or just more languages.

✗ Merging all 6 roadmap paths into one product at once
  Each path is a pivot option, not a feature backlog. Choose one lane.

✗ Expanding the monolith further before the split
  Every new feature added to the 1,582-line file increases split cost.
  The split is already overdue; don't let it get to 2,500 lines.

✗ Skipping the 4 failing tests to ship faster
  Tests 64–67 are unknown failures. Don't ship to PyPI with a broken
  test suite. First impressions on PyPI are hard to undo.
```

---

## Success Criteria — What "Future-Proof" Looks Like at Each Stage

```
v2.0 ready when:
  ✓ Module split complete — each module under 400 lines
  ✓ pyproject.toml config section works end-to-end
  ✓ CodeNormalizer importable as a library (VS Code extension can use it)
  ✓ SyntaxChecker registry accepts external plugin hooks
  ✓ All 67 tests passing (including the 4 currently failing)
  ✓ Telemetry opt-in live (even if only 1 user uses it)

v3.0 ready when:
  ✓ 100+ users on Path 1, feedback loop established
  ✓ At least 1 team/company using it with shared config
  ✓ API design driven by actual user pain, not speculation
  ✓ Cache backend swapped to SQLite (triggered by user feedback)
  ✓ $5K MRR exit criterion from Path 1 roadmap reached

Overall health check — you can grow 10x without a full rewrite if:
  ✓ Core engine is importable, not just runnable
  ✓ Cache, checkers, config are swappable interfaces
  ✓ Telemetry exists to make the next pivot decision with data
  ✓ Module split done before any new surface is added
```

---

*Strategy built from: `docs/ARCHITECTURE.md`, `PROJECT_STATUS.md`, `roadmaps/01–06`, `REFACTOR_LAW.txt`, `pyproject.toml`, `code_normalizer_pro.py` (v3.2.0, 1,582 lines)*
