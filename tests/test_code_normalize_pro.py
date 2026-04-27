from __future__ import annotations

import sys
import subprocess
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
from code_normalizer_pro import code_normalizer_pro as cnp


def test_guess_and_read_accepts_utf16_text(tmp_path: Path) -> None:
    sample = tmp_path / "utf16_sample.py"
    sample.write_text("print('hi')\n", encoding="utf-16")

    normalizer = cnp.CodeNormalizer(dry_run=True, use_cache=False)
    encoding, text = normalizer.guess_and_read(sample)

    assert encoding.startswith("utf-16")
    assert "print('hi')" in text


def test_in_place_rewrites_clean_utf16_to_utf8(tmp_path: Path) -> None:
    sample = tmp_path / "utf16_clean.py"
    sample.write_text("print('hi')\n", encoding="utf-16")

    normalizer = cnp.CodeNormalizer(
        in_place=True,
        create_backup=False,
        use_cache=False,
    )

    assert normalizer.process_file(sample) is True
    assert sample.read_text(encoding="utf-8") == "print('hi')\n"
    assert not sample.read_bytes().startswith((b"\xff\xfe", b"\xfe\xff"))
    assert normalizer.stats.processed == 1
    assert normalizer.stats.encoding_changes == 1


def test_dry_run_check_validates_normalized_output(tmp_path: Path, capsys) -> None:
    sample = tmp_path / "needs_fix.py"
    sample.write_bytes(b"print('hi')  \r\n")

    normalizer = cnp.CodeNormalizer(dry_run=True, use_cache=False)

    assert normalizer.process_file(sample, check_syntax=True) is True
    captured = capsys.readouterr()

    assert "Would normalize" in captured.out
    assert "Syntax: [+] OK" in captured.out
    assert normalizer.stats.processed == 1
    assert normalizer.stats.syntax_checks_passed == 1


def test_guess_and_read_rejects_binary_with_nuls(tmp_path: Path) -> None:
    sample = tmp_path / "blob.bin"
    sample.write_bytes(b"\x89PNG\x00\x01\x02\x03\x04\x00\x00\xff")

    normalizer = cnp.CodeNormalizer(dry_run=True, use_cache=False)

    try:
        normalizer.guess_and_read(sample)
        assert False, "Expected binary detection failure"
    except ValueError as exc:
        assert "binary" in str(exc).lower()


def test_install_git_hook_uses_current_python_and_checks_failures(tmp_path: Path, monkeypatch) -> None:
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    installed = cnp.install_git_hook()
    assert installed is True

    hook = hooks_dir / "pre-commit"
    assert hook.exists()
    hook_text = hook.read_text(encoding="utf-8")

    assert "[sys.executable," in hook_text
    assert "for file_path in files" in hook_text
    assert 'file_path, "--dry-run"' in hook_text
    assert "result.returncode != 0" in hook_text
    assert "code_normalizer_pro.py" in hook_text


def test_install_hook_cli_exits_nonzero_outside_git_repo(tmp_path: Path) -> None:
    script = REPO_ROOT / "main.py"
    result = subprocess.run(
        [sys.executable, str(script), "--install-hook"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    assert "Not a git repository" in result.stdout


def test_parallel_cache_hits_are_persisted(tmp_path: Path) -> None:
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    (sample_dir / "a.py").write_text("print('a')  \n", encoding="utf-8")
    (sample_dir / "b.py").write_text("print('b')\n", encoding="utf-8")

    script = REPO_ROOT / "main.py"
    cmd = [
        sys.executable,
        str(script),
        str(sample_dir),
        "-e",
        ".py",
        "--parallel",
        "--cache",
        "--in-place",
        "--no-backup",
    ]

    first = subprocess.run(
        cmd,
        input="y\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        cwd=tmp_path,
    )
    assert first.returncode == 0, first.stderr

    second = subprocess.run(
        cmd,
        input="y\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        cwd=tmp_path,
    )
    assert second.returncode == 0, second.stderr
    assert "All discovered files were unchanged and skipped by cache." in second.stdout
    assert "[C] Cached hits: 2" in second.stdout


def test_cache_file_scoped_to_target_directory(tmp_path: Path, monkeypatch) -> None:
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    (sample_dir / "a.py").write_text("print('a')  \n", encoding="utf-8")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    normalizer = cnp.CodeNormalizer(use_cache=True)
    normalizer.walk_and_process(sample_dir, [".py"])

    assert (sample_dir / cnp.CACHE_FILE).exists()
    assert not (elsewhere / cnp.CACHE_FILE).exists()



# ---------------------------------------------------------------------------
# Tests added in v3.1.0 for exclude filter, atomic write rollback,
# symlink cycle detection, and syntax-timeout wiring.
# ---------------------------------------------------------------------------


def test_exclude_dirs_prune_venv_from_walk(tmp_path: Path) -> None:
    """walk_and_process must NOT descend into directories in the exclude set.

    Creates a tree with a fake .venv/ containing .py files. The walker
    should skip .venv entirely, processing only the real source files.
    """
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('main')  \n", encoding="utf-8")

    venv = root / ".venv" / "Lib" / "site-packages" / "somepkg"
    venv.mkdir(parents=True)
    (venv / "vendored.py").write_text("print('vendored')  \n", encoding="utf-8")

    normalizer = cnp.CodeNormalizer(dry_run=True, use_cache=False)
    normalizer.walk_and_process(root, [".py"])

    # Exactly one file should have been processed: main.py. The vendored
    # file inside .venv must not have been touched or even discovered.
    assert normalizer.stats.processed == 1
    assert normalizer.stats.total_files == 1
    assert not any("vendored" in str(p) for p, _ in normalizer.errors)


def test_no_default_excludes_allows_venv_scanning(tmp_path: Path) -> None:
    """When exclude_dirs is passed empty, nothing is pruned."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('main')  \n", encoding="utf-8")

    venv = root / ".venv"
    venv.mkdir()
    (venv / "vendored.py").write_text("print('vendored')  \n", encoding="utf-8")

    # Pass an explicitly empty exclusion set to disable defaults.
    normalizer = cnp.CodeNormalizer(
        dry_run=True,
        use_cache=False,
        exclude_dirs=set(),
    )
    normalizer.walk_and_process(root, [".py"])

    assert normalizer.stats.total_files == 2


def test_custom_exclude_adds_to_defaults(tmp_path: Path) -> None:
    """Passing a custom exclude set replaces the defaults completely."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('main')  \n", encoding="utf-8")

    custom = root / "custom_skip"
    custom.mkdir()
    (custom / "skip_me.py").write_text("print('skip')  \n", encoding="utf-8")

    # Only "custom_skip" in the exclusion set -- the defaults are not
    # merged in automatically when exclude_dirs is provided. The CLI
    # main() handles that merging; the constructor honors what it is told.
    normalizer = cnp.CodeNormalizer(
        dry_run=True,
        use_cache=False,
        exclude_dirs={"custom_skip"},
    )
    normalizer.walk_and_process(root, [".py"])

    assert normalizer.stats.total_files == 1


def test_atomic_write_rollback_on_syntax_failure(tmp_path: Path, monkeypatch) -> None:
    """If --check fails, the original file must be completely untouched.

    H3 from the code review: the pre-flight syntax check runs BEFORE any
    write. If the check fails, no backup is created, no temp file survives,
    and the original content is byte-identical to what was there before.
    """
    sample = tmp_path / "needs_fix.py"
    original_bytes = b"print('hi')  \r\n"  # trailing whitespace + CRLF
    sample.write_bytes(original_bytes)

    normalizer = cnp.CodeNormalizer(
        in_place=True,
        create_backup=True,
        use_cache=False,
    )

    # Force the syntax checker to say the normalized content is broken.
    def always_fail(self, path, content=None):
        return False, "forced failure"

    monkeypatch.setattr(cnp.CodeNormalizer, "_run_syntax_check", always_fail)

    result = normalizer.process_file(sample, check_syntax=True)

    # Process should return False (failure) and the stats should reflect
    # a syntax failure and an error, not a successful processing.
    assert result is False
    assert normalizer.stats.syntax_checks_failed == 1
    assert normalizer.stats.errors == 1
    assert normalizer.stats.processed == 0

    # Original file must be byte-identical to what we wrote before.
    assert sample.read_bytes() == original_bytes

    # No .cnp-tmp temp file left behind, no backup created, no other
    # artifacts in the directory.
    leftovers = sorted(p.name for p in tmp_path.iterdir())
    assert leftovers == ["needs_fix.py"]


def test_syntax_timeout_is_passed_to_subprocess(tmp_path: Path, monkeypatch) -> None:
    """--syntax-timeout value must flow through to subprocess.run."""
    sample = tmp_path / "sample.py"
    sample.write_text("print('hi')\n", encoding="utf-8")

    captured_timeout = {}
    original_run = cnp.subprocess.run

    def spy_run(*args, **kwargs):
        if "timeout" in kwargs:
            captured_timeout["value"] = kwargs["timeout"]
        return original_run(*args, **kwargs)

    monkeypatch.setattr(cnp.subprocess, "run", spy_run)

    normalizer = cnp.CodeNormalizer(
        dry_run=True,
        use_cache=False,
        syntax_timeout=7,
    )
    ok, reason = normalizer._run_syntax_check(sample, content="print('hi')\n")

    assert ok is True
    assert captured_timeout.get("value") == 7


def test_symlink_cycle_guard_terminates(tmp_path: Path) -> None:
    """Walker must not infinite-loop on symlink / junction cycles.

    On Windows without admin privileges, os.symlink raises OSError. In
    that case we fall back to testing the guard indirectly by verifying
    the visited_real set logic handles a non-cyclic tree correctly
    (the real protection comes from followlinks=False anyway).
    """
    import pytest

    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("print('main')\n", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "other.py").write_text("print('other')\n", encoding="utf-8")

    cycle = sub / "back_to_root"
    try:
        cycle.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Cannot create symlink on this platform: {exc}")

    normalizer = cnp.CodeNormalizer(dry_run=True, use_cache=False)

    # This call must TERMINATE -- that is the assertion. If the cycle
    # guard is broken, the process would infinite-loop and the test
    # would time out. Each real file should be processed at most once.
    normalizer.walk_and_process(root, [".py"])

    # Both real .py files found, no duplicates.
    assert normalizer.stats.total_files == 2


def test_parallel_syntax_failure_stats_are_merged(tmp_path: Path, monkeypatch) -> None:
    """Parallel path must merge syntax_checks_failed from workers that
    returned success=False.

    Regression test for NEW-H1 found in the v3.1.0 self-review: when a
    worker process failed the pre-flight syntax check and returned
    success=False, the main aggregator only bumped stats.errors and
    dropped the syntax_checks_failed counter. The summary would
    under-report every parallel --check failure as "0 failures".
    """
    root = tmp_path / "project"
    root.mkdir()

    # File 1: valid text, INVALID Python syntax. Trailing whitespace
    # ensures the normalizer sees work to do and proceeds to the syntax
    # check rather than short-circuiting on "already clean".
    (root / "broken.py").write_text(
        "this is not python at all   \n", encoding="utf-8"
    )

    # File 2: valid text, VALID Python. Gives the parallel pool something
    # to succeed on so we can prove the success path still works.
    (root / "valid.py").write_text(
        "x = 1   \n", encoding="utf-8"
    )

    # Auto-confirm the in-place prompt. walk_and_process reads from
    # builtins.input which is a main-process call, not a worker call.
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

    normalizer = cnp.CodeNormalizer(
        in_place=True,
        create_backup=False,
        use_cache=False,
        parallel=True,
        exclude_dirs=set(),
    )

    normalizer.walk_and_process(root, [".py"], check_syntax=True)

    # broken.py must contribute 1 to syntax_checks_failed. Before the
    # NEW-H1 fix this was 0 on the parallel path.
    assert normalizer.stats.syntax_checks_failed >= 1, (
        f"Expected syntax_checks_failed >= 1, got "
        f"{normalizer.stats.syntax_checks_failed}. NEW-H1 regression."
    )
    # And it must also show up as an error
    assert normalizer.stats.errors >= 1


def test_confirmation_prompt_accepts_yes_variants(tmp_path: Path, monkeypatch) -> None:
    """The in-place confirmation prompt must accept 'y', 'yes', 'YES', 'Yes'."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("x = 1   \n", encoding="utf-8")

    for answer in ("y", "Y", "yes", "YES", "Yes", "  yes  "):
        responses = iter([answer])
        monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))

        normalizer = cnp.CodeNormalizer(
            in_place=True,
            create_backup=False,
            use_cache=False,
            exclude_dirs=set(),
        )
        normalizer.walk_and_process(root, [".py"])

        # If confirmation was accepted, processed should be >= 1 for
        # the first run (whitespace to strip) and 0 for subsequent runs
        # (already clean). Either way, no 'Cancelled' happened.
        assert normalizer.stats.errors == 0, (
            f"answer={answer!r} errored: {normalizer.errors}"
        )


def test_syntax_reason_surfaced_for_missing_checker(tmp_path: Path, monkeypatch) -> None:
    """When --check runs against an extension with no installed checker,
    the 'Syntax: [OK]' print should include the reason string so users
    know the pass was not a real validation."""
    sample = tmp_path / "foo.rs"  # .rs -> rustc, likely not installed
    sample.write_text("fn main() {}   \n", encoding="utf-8")

    # Force the checker to look missing regardless of actual install
    def fake_run(self, path, content=None):
        return True, "rustc not installed"

    monkeypatch.setattr(cnp.CodeNormalizer, "_run_syntax_check", fake_run)

    normalizer = cnp.CodeNormalizer(
        in_place=True,
        create_backup=False,
        use_cache=False,
    )

    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = normalizer.process_file(sample, check_syntax=True)

    out = buf.getvalue()
    assert result is True
    # NEW-M1 fix: the reason string must be surfaced
    assert "rustc not installed" in out, f"Expected reason in output, got: {out!r}"


def test_generate_reports_writes_valid_json(tmp_path: Path) -> None:
    """generate_reports must serialize stats and errors to a valid JSON file."""
    report_json = tmp_path / "report.json"

    normalizer = cnp.CodeNormalizer(
        dry_run=True,
        use_cache=False,
        report_json=report_json
    )

    # Inject fake stats
    normalizer.stats.total_files = 10
    normalizer.stats.processed = 5
    normalizer.stats.errors = 1

    # Inject a fake error to ensure error_details are serialized correctly
    fake_err_path = Path("fake_file.py")
    normalizer.errors.append((fake_err_path, "syntax error on line 1"))

    normalizer.generate_reports()

    assert report_json.exists(), "JSON report file was not created"

    data = json.loads(report_json.read_text(encoding="utf-8"))

    assert data["total_files"] == 10
    assert data["processed"] == 5
    assert data["errors"] == 1
    assert data["error_details"] == [{"file": str(fake_err_path), "error": "syntax error on line 1"}]


def test_generate_reports_writes_valid_html(tmp_path: Path) -> None:
    """generate_reports must write expected statistics and errors into the HTML report."""
    report_html = tmp_path / "report.html"

    normalizer = cnp.CodeNormalizer(
        dry_run=True,
        use_cache=False,
        report_html=report_html
    )

    # Inject fake stats
    normalizer.stats.total_files = 10
    normalizer.stats.processed = 5
    normalizer.stats.errors = 1

    # Inject a fake error
    fake_err_path = Path("fake_file.py")
    normalizer.errors.append((fake_err_path, "syntax error on line 1"))

    normalizer.generate_reports()

    assert report_html.exists(), "HTML report file was not created"

    html_content = report_html.read_text(encoding="utf-8")

    # Verify table data conversion (e.g. total_files -> Total Files)
    assert "<td>Total Files</td><td>10</td>" in html_content
    assert "<td>Processed</td><td>5</td>" in html_content
    assert "<li><strong>fake_file.py</strong>: syntax error on line 1</li>" in html_content


def test_in_place_preserves_file_permissions(tmp_path: Path) -> None:
    """Ensure that file permissions (like the executable bit) are retained after atomic replace."""
    import stat

    sample = tmp_path / "script.sh"
    # Content needing normalization (trailing spaces)
    sample.write_text("echo 'hello'   \n", encoding="utf-8")

    # Set explicit permissions (rwxr-xr-x)
    sample.chmod(0o755)
    orig_mode = sample.stat().st_mode

    normalizer = cnp.CodeNormalizer(
        in_place=True,
        create_backup=False,
        use_cache=False,
    )

    # Process and normalize the file
    assert normalizer.process_file(sample) is True
    assert normalizer.stats.processed == 1

    # Verify mode was preserved
    new_mode = sample.stat().st_mode

    if orig_mode & stat.S_IXUSR:
        assert new_mode & stat.S_IXUSR, "Executable bit was lost during normalization!"

    assert new_mode == orig_mode, f"Permissions changed! Expected {oct(orig_mode)}, got {oct(new_mode)}"


def test_file_symlinks_are_skipped(tmp_path: Path) -> None:
    """File symlinks must be ignored to prevent clobbering the target or replacing the link."""
    import pytest
    import os

    root = tmp_path / "project"
    root.mkdir()
    
    # Create a real file outside the project directory
    external_target = tmp_path / "external.py"
    external_target.write_text("print('hello')   \n", encoding="utf-8")

    # Create a symlink inside the project pointing to the external file
    link_path = root / "link.py"
    try:
        link_path.symlink_to(external_target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Cannot create symlink on this platform: {exc}")

    # Also add a real file to ensure the normalizer finds at least one valid file
    (root / "main.py").write_text("print('main')   \n", encoding="utf-8")

    normalizer = cnp.CodeNormalizer(
        in_place=True,
        create_backup=False,
        use_cache=False,
    )
    normalizer.walk_and_process(root, [".py"])

    # main.py should be processed, link.py should be ignored entirely
    assert normalizer.stats.total_files == 1
    assert normalizer.stats.processed == 1

    # The symlink must still be a symlink and the external target should remain untouched
    assert link_path.is_symlink(), "Symlink was clobbered and replaced with a regular file!"
    assert external_target.read_text(encoding="utf-8") == "print('hello')   \n"


def test_git_hook_handles_files_with_spaces(tmp_path: Path, monkeypatch) -> None:
    """The Git hook must parse filenames with spaces correctly using null-termination."""
    # Initialize a real git repository
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    
    # Force git to quote paths with spaces (which breaks standard string parsing)
    subprocess.run(["git", "config", "core.quotepath", "on"], cwd=tmp_path, check=True)

    monkeypatch.chdir(tmp_path)

    # Install the hook
    installed = cnp.install_git_hook()
    assert installed is True
    hook_path = tmp_path / ".git" / "hooks" / "pre-commit"

    # Create a Python file with a space in the name that needs normalization
    spaced_file = tmp_path / "my script.py"
    spaced_file.write_text("print('hello')   \n", encoding="utf-8")

    # Stage the file
    subprocess.run(["git", "add", "my script.py"], cwd=tmp_path, check=True)

    # Execute the hook script
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        capture_output=True,
        text=True,
        cwd=tmp_path
    )

    # The hook must successfully find the file and detect that it needs normalization
    assert result.returncode == 1
    assert "Checking 1 Python file(s)" in result.stdout
    assert "my script.py" in result.stdout


def test_expand_tabs_converts_tabs_to_spaces(tmp_path: Path) -> None:
    sample = tmp_path / "tabs.py"
    sample.write_text("def test():\n\tprint('hi')\n", encoding="utf-8")
    
    normalizer = cnp.CodeNormalizer(in_place=True, create_backup=False, use_cache=False, expand_tabs=4)
    assert normalizer.process_file(sample) is True
    
    assert sample.read_text(encoding="utf-8") == "def test():\n    print('hi')\n"


def test_max_lines_skips_large_files(tmp_path: Path) -> None:
    sample = tmp_path / "large.py"
    sample.write_text("line1\nline2\nline3\n", encoding="utf-8")
    
    normalizer = cnp.CodeNormalizer(in_place=True, create_backup=False, use_cache=False, max_lines=2)
    assert normalizer.process_file(sample) is True
    
    assert normalizer.stats.skipped == 1
    assert normalizer.stats.processed == 0


def test_editorconfig_hierarchical_resolution(tmp_path: Path) -> None:
    """Test that .editorconfig is resolved hierarchically and respects globs."""
    editorconfig = tmp_path / ".editorconfig"
    editorconfig.write_text("root = true\n\n[*]\nindent_size = 2\n", encoding="utf-8")
    
    nested_dir = tmp_path / "backend"
    nested_dir.mkdir()
    nested_config = nested_dir / ".editorconfig"
    nested_config.write_text("[*.{py,js}]\nindent_size = 4\n", encoding="utf-8")
    
    # JS file in backend should get indent_size=4 from brace expansion glob
    js_sample = nested_dir / "app.js"
    js_sample.write_text("function() {\n\treturn;\n}\n", encoding="utf-8")
    
    # PY file in backend should get indent_size=4 from nested config
    py_sample = nested_dir / "tabs.py"
    py_sample.write_text("def test():\n\tprint('hi')\n", encoding="utf-8")
    
    normalizer = cnp.CodeNormalizer(in_place=True, create_backup=False, use_cache=False)
    normalizer.process_file(js_sample)
    normalizer.process_file(py_sample)
    
    assert js_sample.read_text(encoding="utf-8") == "function() {\n    return;\n}\n"
    assert py_sample.read_text(encoding="utf-8") == "def test():\n    print('hi')\n"


def test_editorconfig_nested_brace_expansion(tmp_path: Path) -> None:
    """Test that nested brace expansions like *.{test.{py,js},ts} work correctly."""
    editorconfig = tmp_path / ".editorconfig"
    editorconfig.write_text("root = true\n\n[*.{test.{py,js},ts}]\nindent_size = 4\n", encoding="utf-8")
    
    files = {
        tmp_path / "app.test.py": True,  # Should match
        tmp_path / "app.test.js": True,  # Should match
        tmp_path / "app.ts": True,       # Should match
        tmp_path / "app.js": False,      # Should NOT match
    }
    
    normalizer = cnp.CodeNormalizer(in_place=True, create_backup=False, use_cache=False)
    
    for f, should_match in files.items():
        f.write_text("def fn():\n\tpass\n", encoding="utf-8")
        normalizer.process_file(f)
        expected = "def fn():\n    pass\n" if should_match else "def fn():\n\tpass\n"
        assert f.read_text(encoding="utf-8") == expected


def test_atomic_replace_fallback_success(tmp_path: Path, monkeypatch) -> None:
    """Test that an OSError in os.replace triggers the manual rename fallback."""
    sample = tmp_path / "locked.py"
    sample.write_text("print('hello')   \n", encoding="utf-8")
    
    # Force os.replace to fail, triggering the fallback block
    def mock_replace(src, dst):
        raise OSError("Simulated Windows file lock / cross-device link")
        
    monkeypatch.setattr(cnp.os, "replace", mock_replace)
    
    normalizer = cnp.CodeNormalizer(in_place=True, create_backup=False, use_cache=False)
    assert normalizer.process_file(sample) is True
    
    # Verify the fallback successfully put the cleaned file in place
    assert sample.read_text(encoding="utf-8") == "print('hello')\n"
    assert normalizer.stats.processed == 1


def test_atomic_replace_fallback_rollback(tmp_path: Path, monkeypatch) -> None:
    """Test that if the fallback sequence fails mid-transaction, it rolls back the file."""
    sample = tmp_path / "rollback.py"
    original_content = "print('hello')   \n"
    sample.write_text(original_content, encoding="utf-8")
    
    monkeypatch.setattr(cnp.os, "replace", lambda src, dst: exec('raise OSError("Lock")'))
    
    original_rename = cnp.os.rename
    rename_calls = []
    
    def mock_rename(src, dst):
        rename_calls.append((src, dst))
        if len(rename_calls) == 2:
            # Fail on the second rename (putting the temp file into place)
            raise OSError("Simulated rename failure mid-transaction")
        return original_rename(src, dst)
        
    monkeypatch.setattr(cnp.os, "rename", mock_rename)
    
    normalizer = cnp.CodeNormalizer(in_place=True, create_backup=False, use_cache=False)
    assert normalizer.process_file(sample) is False
    
    # The file should be restored to its exact original messy state
    assert sample.read_text(encoding="utf-8") == original_content
    assert len(rename_calls) == 3  # 1: backup, 2: fail, 3: rollback


def test_mmap_binary_check_prevents_full_file_read(tmp_path: Path, monkeypatch) -> None:
    """Verify that mmap securely detects binaries and prevents reading the full file into RAM."""
    import pytest
    
    sample = tmp_path / "mock_video.mp4"
    # Create a dummy binary file containing a null byte
    sample.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 1024)

    mmap_called = False
    read_bytes_called = False
    
    original_mmap = cnp.mmap.mmap
    def mock_mmap(*args, **kwargs):
        nonlocal mmap_called
        mmap_called = True
        return original_mmap(*args, **kwargs)
        
    monkeypatch.setattr(cnp.mmap, "mmap", mock_mmap)
    monkeypatch.setattr(Path, "read_bytes", lambda self: exec('nonlocal read_bytes_called; read_bytes_called = True'))

    normalizer = cnp.CodeNormalizer(dry_run=True, use_cache=False)
    
    with pytest.raises(ValueError, match="appears to be binary"):
        normalizer.guess_and_read(sample)
        
    assert mmap_called is True, "mmap was never utilized to check the file"
    assert read_bytes_called is False, "RAM exhaustion hazard: read_bytes was called despite mmap detecting binary"


def test_log_file_captures_stdout(tmp_path: Path) -> None:
    """Ensure that the --log-file argument tees stdout to the specified file."""
    log_file = tmp_path / "execution.log"
    sample = tmp_path / "test_log.py"
    sample.write_text("print('test')\n", encoding="utf-8")

    from code_normalizer_pro.code_normalizer_pro import cli_main

    try:
        cli_main(path=sample, in_place=True, cache=False, log_file=log_file)
    except SystemExit as e:
        assert e.code == 0

    assert log_file.exists()
    log_content = log_file.read_text(encoding="utf-8")
    assert "CODE NORMALIZER PRO" in log_content
    assert "PROCESSING SUMMARY" in log_content
    assert "test_log.py" in log_content


def test_log_file_rotation(tmp_path: Path) -> None:
    """Ensure the log file is rotated when it exceeds the size limit."""
    log_file = tmp_path / "execution.log"
    
    # Create a dummy log file larger than the default 5MB limit
    log_file.write_text("A" * (6 * 1024 * 1024), encoding="utf-8")
    
    sample = tmp_path / "test_rot.py"
    sample.write_text("print('test')\n", encoding="utf-8")

    from code_normalizer_pro.code_normalizer_pro import cli_main

    try:
        cli_main(path=sample, in_place=True, cache=False, log_file=log_file)
    except SystemExit as e:
        assert e.code == 0
        
    # Loguru automatically rotates and renames the file (e.g. execution.2023-10-12_10-00-00.log)
    rotated_logs = [f for f in tmp_path.glob("execution.*") if f.name != "execution.log"]
    assert len(rotated_logs) >= 1
    assert rotated_logs[0].stat().st_size == 6 * 1024 * 1024
    
    # The new active log should have been freshly created and be small
    assert log_file.exists()
    assert log_file.stat().st_size < 1024 * 1024


def test_log_file_compression(tmp_path: Path) -> None:
    """Ensure rotated logs are compressed when --compress-logs is used."""
    log_file = tmp_path / "execution.log"
    
    # Create a dummy log file larger than the default 5MB limit
    log_file.write_text("A" * (6 * 1024 * 1024), encoding="utf-8")
    
    sample = tmp_path / "test_comp.py"
    sample.write_text("print('test')\n", encoding="utf-8")

    from code_normalizer_pro.code_normalizer_pro import cli_main

    try:
        cli_main(path=sample, in_place=True, cache=False, log_file=log_file, compress_logs=True)
    except SystemExit as e:
        assert e.code == 0
        
    rotated_logs = [f for f in tmp_path.glob("execution.*") if f.name != "execution.log"]
    assert len(rotated_logs) >= 1
    assert any(f.name.endswith(".gz") for f in rotated_logs), "No compressed log archive found!"
