# Runbook — code-normalizer-pro

This document covers normal operation, common failure modes, and recovery steps.

---

## Normal operation

**Preview before touching anything (always start here):**

```bash
code-normalizer-pro /path/to/repo --dry-run
```

**Apply changes with backups (default, safe):**

```bash
code-normalizer-pro /path/to/repo --in-place
```

**Apply changes without a prompt in CI:**

```bash
code-normalizer-pro /path/to/repo --in-place --yes
```

**Check that a repo is already normalized (CI gate):**

```bash
code-normalizer-pro /path/to/repo --dry-run --fail-on-changes
```

Expected exit codes: `0` = clean / changes applied, `1` = error or `--fail-on-changes` triggered.

---

## Troubleshooting

### The tool hangs / never finishes

**Likely cause:** a file exceeds `--max-lines` and is being processed line-by-line, or a `--check` syntax validation is waiting for a slow compiler.

Steps:
1. Press `Ctrl-C`. The cache is flushed on interrupt — the next run resumes from where it stopped.
2. Re-run with `--max-lines 5000` to skip very large files.
3. Re-run with `--timeout 5` to cap per-file syntax check time.
4. Re-run with `--no-cache` to verify the cache is not hiding the stuck file.

```bash
code-normalizer-pro /path/to/repo --dry-run --max-lines 5000 --timeout 5
```

---

### A file was not modified when I expected it to be

**Possible causes and checks:**

1. **File is cached** — already normalized on a previous run.
   ```bash
   code-normalizer-pro /path/to/file.py --dry-run --no-cache -v
   ```
   If `[+]` appears now but not before, the cache was hiding it. Delete `.normalize-cache.json` to reset.

2. **File extension not in scope** — default is `.py`. Check with `-e`.
   ```bash
   code-normalizer-pro /path/to/repo --dry-run -e .js -v
   ```

3. **File is in an excluded directory** — `.venv`, `build`, `node_modules`, etc. are skipped by default.
   ```bash
   code-normalizer-pro /path/to/repo --dry-run --no-default-excludes -v
   ```

4. **File is already normalized** — run with `--verbose` and look for `[S] SKIP` in the output. This means no changes were needed.

5. **File is binary** — binary files are always skipped. The tool checks for null bytes.

---

### Unexpected output / file looks wrong after normalization

**The tool only makes these changes:**
- Encoding → UTF-8
- Line endings → LF
- Trailing whitespace → removed
- Final newline → enforced

If the file looks semantically wrong, the tool did not cause it. Check the diff:

```bash
# If backup was created:
diff original.py original.py.cnp-bak_<timestamp>

# If using git:
git diff HEAD -- original.py
```

To restore from a backup, see the "Restoring from backup" section below.

---

### `--no-backup` was used and a file was corrupted

If `--no-backup --yes` was passed and the file is wrong, check git:

```bash
git checkout -- path/to/file.py     # restore from last commit
git stash                            # or stash all changes
```

If the repo is not under git and there is no backup, the original content is lost. This is why `--no-backup` outside a git repository is blocked by default (override only with `--yes` when you are certain).

---

### `--no-backup` is blocked with "git repo" error

The tool detected you are running `--in-place --no-backup` outside a git repository, which risks permanent data loss.

Options:
1. Commit your files to git first, then re-run.
2. If you intentionally want to proceed without git: `--yes` overrides the guard.
   ```bash
   code-normalizer-pro /path --in-place --no-backup --yes
   ```

---

### Cache issues

**Clear the cache for a specific directory:**

```bash
del /path/to/repo/.normalize-cache.json     # Windows
rm  /path/to/repo/.normalize-cache.json     # Unix
```

The cache is rebuilt automatically on the next run. It is always safe to delete.

**Cache schema version mismatch (after upgrading the tool):**

If you see a debug message like `Cache schema version mismatch — starting fresh`, the old cache has been discarded. This is intentional — a fresh scan runs and a new cache is written. No action needed.

---

### Duplicate log entries in `--log-file`

Log entries should appear once per file. If you see duplicates, you may be running an old version (< 3.2.0) where the per-worker log sink was initialized per-task rather than per-process.

Upgrade and re-run:
```bash
pip install --upgrade code-normalizer-pro
```

---

## Restoring from backup

When `--in-place` runs without `--no-backup`, a backup is created beside each modified file:

```
original.py.cnp-bak_20260426_211530_123456
```

To restore:

```bash
# Windows PowerShell
Copy-Item "original.py.cnp-bak_20260426_211530_123456" -Destination "original.py" -Force

# Unix
cp original.py.cnp-bak_20260426_211530_123456 original.py
```

To clean up all backups after verifying the results:

```bash
# Windows PowerShell
Get-ChildItem -Recurse -Filter "*.cnp-bak_*" | Remove-Item

# Unix
find . -name "*.cnp-bak_*" -delete
```

---

## Periodic maintenance

| Cadence | Task |
|---------|------|
| After each release | Delete old `.normalize-cache.json` files in CI workspaces |
| Monthly | Run `pip install --upgrade code-normalizer-pro` to get the latest |
| Quarterly | Review and clean up accumulated `.cnp-bak_*` backup files |
| On tool upgrade | If behavior changes, delete `.normalize-cache.json` to force a full re-scan |
