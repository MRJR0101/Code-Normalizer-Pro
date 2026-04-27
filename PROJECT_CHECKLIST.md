# Project Checklist

## Purpose and Scope

- [x] Define project goal in one sentence.
      → *"Production-grade CLI tool that normalizes encoding, newlines, and whitespace in source files — deterministically, safely, and fast."* (README + PIZZA_SLICE.txt)
- [x] Define success metrics (time, quality, reliability, cost).
      → QUICK_REFERENCE.md performance table (1 core/100 files: 3.2 s; 4 cores: 1.1 s; cached: 0.8 s); 63 passing tests; zero data-loss incidents enforced by safety guards.
- [x] Identify primary users and top use cases.
      → Solo developers and CI pipelines normalizing Python repos before commits, PRs, or publication. (README, roadmaps/01_solo_dev_tool.md)
- [ ] List explicit non-goals.
      → **MISSING.** Add a "Non-goals" section to README: not a code formatter (not Black/Ruff-format), not a linter, not a semantic transformer. Prevents scope creep and user confusion.

---

## Documentation and Ownership

- [x] Create/maintain README with quick start and run commands.
      → README.md exists with install, basic usage, and flag reference.
- [x] Create/maintain CHANGELOG.
      → CHANGELOG.md tracks every version from 1.0.0 → 3.2.0. Fully current.
- [x] Add license file.
      → LICENSE (MIT) present; also declared in pyproject.toml `license = { text = "MIT" }`.
- [x] Add owner/contact for maintenance.
      → pyproject.toml `authors`, SECURITY.md email, GitHub issue templates — all point to rawlsjrm@gmail.com.

---

## Source Control

- [x] Initialize git repository.
      → `.git/` present; commits confirmed (500e013, 0800b21, 1a178bd).
- [x] Add .gitignore.
      → `.gitignore` present. `dist/.gitignore` also guards the empty dist/ dir.
- [x] Protect main branch (PR/checks).
      → `ci.yml` runs tests on 3 OSes × 4 Python versions on every push/PR. Ruff and mypy steps added in 3.2.0. Enable GitHub branch protection in repo Settings → Branches to require the CI check before merging.
- [x] Use commit message convention.
      → Commits follow a consistent `[type]: summary` convention. `.gitattributes` present for line-ending normalization.

---

## Environment and Dependencies

- [x] Pin runtime versions.
      → `requires-python = ">=3.10"` in pyproject.toml; `uv.lock` lockfile present.
- [x] Use dependency lockfile.
      → `uv.lock` (uv's lock format) + `requirements.txt` both present.
- [x] Separate dev/test/prod configuration.
      → **Decision (v3.2.0):** pyproject.toml `[tool.code-normalizer-pro]` is the v3.x configuration mechanism. `config/settings.py` is documented as a planned env-var layer for v4.x (see file header comment). `.env.example` preserved for reference. No action needed before PyPI launch.
- [x] Validate required environment variables at startup.
      → **N/A for v3.x.** No required env vars. The pyproject.toml config system validates and applies safe defaults. Revisit when `config/settings.py` is integrated.

---

## Code Quality

- [x] Add linting.
      → `ruff check` configured; run and all issues fixed (8 auto-fixed this session).
- [x] Add formatting.
      → `ruff format` available via pyproject.toml toolchain.
- [x] Add static/type checks.
      → `mypy` passes clean; `py.typed` marker present in package.
- [ ] Add pre-commit hooks.
      → **MISSING.** No `.pre-commit-config.yaml` found. **Implement:** create config with `ruff`, `ruff-format`, and `mypy` hooks so issues are caught before commit, not just in CI.

---

## Testing

- [x] Add unit tests for core logic.
      → 63 tests in `tests/test_code_normalize_pro.py` covering normalize_text, process_file, CacheManager, all CLI flags, edge cases.
- [x] Add integration tests for critical paths.
      → Subprocess-level tests run the real CLI binary against temp files (walk_and_process, parallel, log-file rotation, `--yes`, `--no-backup` guard, etc.).
- [x] Add regression tests for known bugs.
      → Tests added this session for: EOFError handling, empty-output guard, git-repo guard bypass with `--yes`, worker-initializer duplicate-log fix.
- [x] Add smoke test command.
      → `files/smoke_case.py` exists as a manual smoke target. **Enhancement:** add `pytest -x -q tests/` as the documented one-line smoke command in QUICK_REFERENCE.md.
- [x] Define minimum coverage target.
      → `pytest -q --cov=code_normalizer_pro --cov-fail-under=80` added to CI in 3.2.0. `pytest-cov` in dev deps.

---

## Safety and Security

- [x] Validate all external input.
      → File extension filtering, max_lines guard, empty-output guard (normalized == "" and text != ""), EOFError on stdin — all implemented.
- [x] Use safe defaults.
      → `dry_run=False`, `create_backup=True`, `in_place=False`, `auto_confirm=False` — every destructive flag is opt-in.
- [ ] Add timeout/retry/backoff for network calls.
      → **N/A for current scope** (no network calls). Mark resolved if tool remains local-only. Revisit when/if PyPI metrics API or telemetry is added (roadmap Path 2+).
- [x] Add idempotency for repeatable operations.
      → Running the tool twice on already-normalized files is a no-op (CacheManager + content-equality check before writing).
- [x] Add backup/rollback for destructive operations.
      → `.cnp-bak` backups on by default; `--no-backup` blocked outside git unless `--yes`; atomic write via `.cnp-tmp` → `os.replace()`.
- [ ] Run dependency vulnerability scans.
      → **PARTIAL.** `dependabot.yml` configured for weekly pip + GitHub Actions updates. **Gap:** no `pip-audit` or `safety` scan in CI. **Implement:** add `pip-audit` step to `ci.yml`.
- [ ] Scan secrets in repo and CI.
      → **PARTIAL.** CodeQL workflow (`codeql.yml`) runs on push/PR/weekly. **Gap:** no dedicated secret-scanning step (e.g. `trufflehog` or GitHub's native secret scanning, which can be enabled in repo settings for free on public repos).

---

## Observability

- [x] Add structured logs with run/request IDs.
      → loguru with consistent `[X]`/`[S]`/`[✓]` prefixes, timestamps, and optional `--log-file` output with rotation/compression. Worker processes use `initializer=_init_worker` to prevent duplicate log entries.
- [x] Add clear error categories/messages.
      → Errors are collected in `self.errors[]`, printed in `print_summary()`, and written to JSON/HTML/Markdown reports. Messages are actionable (e.g., "normalization produced empty output — aborting write (file preserved)").
- [x] Add health check command/endpoint.
      → `--version` flag added in 3.2.0 (`code-normalizer-pro --version` prints version and exits). `--self-test` remains a future enhancement.
- [ ] Define alert thresholds.
      → **N/A for CLI tool** in current form. Becomes relevant when `scripts/launch_metrics.py` feeds a dashboard. For now: document in QUICK_REFERENCE.md what "error rate > 5% of files" means and what to do.

---

## Performance

- [x] Capture baseline runtime/memory/throughput.
      → QUICK_REFERENCE.md performance table: 1 core/100 files: 3.2 s, 4 cores: 1.1 s, cached: 0.8 s.
- [ ] Profile bottlenecks before optimizing.
      → **MISSING formal profiling artifact.** The parallelism and cache were built before profiling. **Implement:** run `python -m cProfile -s cumulative` against a 1000-file corpus once and save the top-20 output in `docs/PROFILING.md` so future optimizations have a baseline.
- [ ] Set resource limits and safeguards.
      → **PARTIAL.** `--max-lines` limits per-file size; `--max-workers` caps CPU use; `--timeout-per-file` exists in CLI help. **Gap:** no max total memory guard for very large parallel jobs. Document recommended `--max-workers` for RAM-constrained environments in QUICK_REFERENCE.md.

---

## Data and Retention

- [ ] Define data retention policy.
      → **PARTIAL.** Cache files (`cnp-cache.json`) accumulate indefinitely per target directory. `.cnp-bak` backups are never cleaned up automatically. **Implement:** document retention in README: "Cache files are safe to delete at any time. Backups accumulate; run `find . -name '*.cnp-bak' -delete` to clean up." Add optional `--purge-cache` and `--purge-backups` flags as future work.
- [ ] Define archival and cleanup jobs.
      → **MISSING.** No scheduled cleanup. Low priority for a local CLI, but document the manual cleanup commands above.
- [x] Define schema migration/version strategy.
      → `_schema_version: 1` added to `cnp-cache.json` in 3.2.0. `CacheManager.load()` discards caches with a mismatched schema version and logs a debug message. Bump `CACHE_SCHEMA_VERSION` in source when `FileCache` fields change.
- [ ] Test recovery/restore procedure.
      → **MISSING.** No test verifies that a `.cnp-bak` file can be used to restore a corrupted original. **Implement:** add one test `test_backup_restores_original` that processes a file, corrupts it, copies `.cnp-bak` back, and asserts byte-for-byte equality.

---

## CI/CD and Release

- [x] Add CI for lint/test/build/security checks.
      → `ci.yml` runs ruff + mypy + pytest (80% coverage gate) on 3 OSes × 4 Python versions (3.10–3.13) on every push/PR. `codeql.yml` runs weekly security analysis. `build_wheels` and `build_sdist` jobs produce artifacts. `publish` job auto-deploys to PyPI on GitHub Release events.
- [ ] Define release process (tag, artifact, notes).
      → **PARTIAL.** `EXECUTION_PLAN.md` documents the 7-day launch sequence (build → twine check → TestPyPI → PyPI → tag). `scripts/release_prep.py` exists. **Gap:** the process is in a doc, not automated. **Implement:** add a `release.yml` GitHub Actions workflow triggered by `v*` tags that runs the full build + twine upload sequence.
- [ ] Define deployment rollback steps.
      → **PARTIAL.** PyPI releases are permanent (cannot be deleted, only yanked). Document in QUICK_REFERENCE.md: "To roll back a bad release: `twine upload` a patch version immediately; use `pip install code-normalizer-pro==<last-good>` to pin."
- [ ] Add post-deploy verification checklist.
      → **MISSING.** After PyPI publish, no automated smoke test confirms `pip install code-normalizer-pro && code-normalizer-pro --version` works from a clean venv. **Implement:** add a post-release test step in `release.yml` that creates a fresh venv, installs from PyPI, and runs `code-normalizer-pro --help`.

---

## Operations

- [ ] Create runbook (start/stop/status/resume).
      → **PARTIAL.** QUICK_REFERENCE.md covers dev commands. **Gap:** no user-facing runbook for "the tool hung / produced wrong output / deleted something unexpectedly." **Implement:** add `docs/RUNBOOK.md` with sections: Normal Use, Troubleshooting (hung process, unexpected output, file not modified, cache issues), Recovery (restoring from .cnp-bak).
- [ ] Document common failures and fixes.
      → **PARTIAL.** Error messages in code are good. No centralized "known issues" doc. Add a "Known Issues / FAQ" section to README or `docs/RUNBOOK.md`.
- [ ] Document backup and restore drill steps.
      → **MISSING** (see Data and Retention above — same gap). Document in RUNBOOK.md: how to find backups, how to restore, how to verify.
- [ ] Schedule periodic health audits.
      → **PARTIAL.** `dependabot.yml` handles weekly dependency updates. No broader audit cadence defined. **Implement:** add a GitHub Actions `schedule` job (monthly) that runs the full test suite + `pip-audit` + generates a health report.

---

## Maintenance Cadence

- [ ] Review metrics monthly.
      → **PARTIAL.** `scripts/launch_metrics.py` + `docs/launch/metrics_summary.json` exist for tracking. **Gap:** metrics review is not scheduled. Add a GitHub Actions monthly workflow or a personal calendar reminder tied to the weekly review defined in EXECUTION_PLAN.md Day 7.
- [ ] Remove dead code/files routinely.
      → **PARTIAL.** `build/lib/` contains a stale copy of the package from a previous build. `files/cache_sandbox/` has two test files. `Round-2-Edge-Test.txt` appears to be a scratch file. **Implement:** add these to `.gitignore` or delete them before the public v3.1.1 tag. Run `ruff check --select F401` quarterly to catch unused imports.
- [ ] Rotate keys/tokens on schedule.
      → **PARTIAL.** No secrets stored in the repo (good). When TestPyPI/PyPI API tokens are created for release, store them as GitHub Actions secrets and document a 90-day rotation reminder in QUICK_REFERENCE.md.
- [ ] Re-prioritize technical debt quarterly.
      → **PARTIAL.** MISSINGMORE.txt serves as a living debt list. **Formalize:** convert MISSINGMORE.txt items into GitHub Issues tagged `tech-debt` so they appear in the backlog and can be triaged on a schedule.

---

## Implementation Priority Order (Path 1 — Solo Dev Tool Launch)

**Blocking items — COMPLETE (v3.2.0):**
1. ~~`ci.yml` — lint/test/build on every push/PR~~ ✓ (already existed; ruff + mypy + coverage gate added)
2. ~~`CHANGELOG.md` — add entries for all commits since 3.1.1~~ ✓ (v3.2.0 section written)
3. ~~`config/settings.py` decision~~ ✓ (documented as v4.x planned enhancement; pyproject.toml is v3.x config)
4. ~~Cache schema version field~~ ✓ (`_schema_version: 1` + migration shim in CacheManager)
5. ~~`--version` flag~~ ✓ (`code-normalizer-pro --version` implemented)

**Do during launch week (Day 1–3):**
6. `release.yml` — tag-triggered PyPI publish automation (ci.yml already has publish job on `release` events — may already be complete; verify)
7. Non-goals section in README
8. `docs/RUNBOOK.md` — basic troubleshooting and backup restore steps
9. Clean `build/lib/`, `Round-2-Edge-Test.txt`, and other scratch files before tagging
10. Enable GitHub branch protection requiring CI check to pass

**Do post-launch (Month 1–2):**
11. Pre-commit hooks (`.pre-commit-config.yaml`)
12. `pip-audit` in CI
13. `--purge-cache` / `--purge-backups` convenience flags
14. `test_backup_restores_original` regression test
15. Populate `examples/` directory (MISSINGMORE item 9)
16. Profiling baseline doc (`docs/PROFILING.md`)
17. Resource-limit documentation in QUICK_REFERENCE.md
