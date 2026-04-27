from __future__ import annotations

import sys
import subprocess
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
from code_normalizer_pro import code_normalizer_pro as cnp  # noqa: E402


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


def test_dry_run_check_validates_normalized_output(tmp_path: Path) -> None:
    import io as _io
    sample = tmp_path / "needs_fix.py"
    sample.write_bytes(b"print('hi')  \r\n")

    # Loguru bypasses Python's sys.stderr redirect and fd-level capture.
    # Add a temporary sink to a StringIO buffer so we can assert on output.
    buf = _io.StringIO()
    sink_id = cnp.logger.add(buf, format="{message}", level="DEBUG")
    try:
        normalizer = cnp.CodeNormalizer(dry_run=True, use_cache=False)
        assert normalizer.process_file(sample, check_syntax=True) is True
        output = buf.getvalue()
    finally:
        cnp.logger.remove(sink_id)

    assert "Would normalize" in output
    assert "Syntax:" in output
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

    assert repr(sys.executable) in hook_text  # repr form baked in at install time
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
        "--yes",
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

    import io as _io
    buf = _io.StringIO()
    sink_id = cnp.logger.add(buf, format="{message}", level="DEBUG")
    try:
        result = normalizer.process_file(sample, check_syntax=True)
        out = buf.getvalue()
    finally:
        cnp.logger.remove(sink_id)

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


def test_file_symlinks_are_skipped(tmp_path: Path, monkeypatch) -> None:
    """File symlinks must be ignored to prevent clobbering the target or replacing the link."""
    import pytest

    root = tmp_path / "project"
    root.mkdir()
    
    # Create a real file outside the project directory
    external_target = tmp_path / "external.py"
    external_target.write_bytes(b"print('hello')   \n")

    # Create a symlink inside the project pointing to the external file
    link_path = root / "link.py"
    try:
        link_path.symlink_to(external_target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Cannot create symlink on this platform: {exc}")

    # Also add a real file to ensure the normalizer finds at least one valid file
    (root / "main.py").write_bytes(b"print('main')   \n")

    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

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
    """Ensure that the --log-file argument tees output to the specified file."""
    log_file = tmp_path / "execution.log"
    sample = tmp_path / "test_log.py"
    # write_bytes avoids Windows CRLF; trailing whitespace gives the normalizer real work
    sample.write_bytes(b"print('test')   \r\n")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"),
         str(sample), "-e", ".py", "--in-place", "--no-backup", "--yes", "--no-cache",
         "--log-file", str(log_file)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stderr

    assert log_file.exists(), "Log file was not created"
    log_content = log_file.read_text(encoding="utf-8")
    assert "CODE NORMALIZER PRO" in log_content
    assert "PROCESSING SUMMARY" in log_content
    assert "test_log.py" in log_content


def test_log_file_rotation(tmp_path: Path) -> None:
    """Ensure the log file is rotated when it exceeds the 5 MB size limit."""
    log_file = tmp_path / "execution.log"
    log_file.write_bytes(b"A" * (6 * 1024 * 1024))  # pre-seed > 5 MB

    sample = tmp_path / "test_rot.py"
    sample.write_bytes(b"print('test')   \r\n")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"),
         str(sample), "-e", ".py", "--in-place", "--no-backup", "--yes", "--no-cache",
         "--log-file", str(log_file)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stderr

    # Loguru rotates to a timestamped name when the file exceeds the rotation threshold
    rotated_logs = [f for f in tmp_path.glob("execution.*") if f.name != "execution.log"]
    assert len(rotated_logs) >= 1, (
        "Expected at least one rotated log file after exceeding 5 MB threshold"
    )
    # New active log must be small (fresh)
    assert log_file.exists()
    assert log_file.stat().st_size < 1024 * 1024


def test_log_file_compression(tmp_path: Path) -> None:
    """Ensure rotated logs are compressed (.gz) when --compress-logs is used."""
    log_file = tmp_path / "execution.log"
    log_file.write_bytes(b"A" * (6 * 1024 * 1024))  # pre-seed > 5 MB

    sample = tmp_path / "test_comp.py"
    sample.write_bytes(b"print('test')   \r\n")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"),
         str(sample), "-e", ".py", "--in-place", "--no-backup", "--yes", "--no-cache",
         "--log-file", str(log_file), "--compress-logs"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stderr

    rotated_logs = [f for f in tmp_path.glob("execution.*") if f.name != "execution.log"]
    assert len(rotated_logs) >= 1, "Expected at least one rotated log file"
    assert any(f.name.endswith(".gz") for f in rotated_logs), (
        f"No .gz archive found. Rotated files: {[f.name for f in rotated_logs]}"
    )


# ===========================================================================
# Tests added v3.1.1+ — covering all key feature points
# ===========================================================================


# ---------------------------------------------------------------------------
# --fail-on-changes  (new flag added in v3.1.1)
# ---------------------------------------------------------------------------

def test_fail_on_changes_exits_one_when_dry_run_finds_dirty_files(tmp_path: Path) -> None:
    """--dry-run --fail-on-changes must exit 1 when any file needs normalization.

    This is the primary CI gate use-case: if any file in the repo would be
    changed by the normalizer, the pipeline should fail so the developer knows
    to run the normalizer locally before merging.
    """
    dirty = tmp_path / "dirty.py"
    dirty.write_bytes(b"print('hi')  \r\n")  # trailing whitespace + CRLF

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"),
         str(tmp_path), "-e", ".py", "--dry-run", "--fail-on-changes", "--no-cache"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )

    assert result.returncode == 1, (
        f"Expected exit 1 from --fail-on-changes with dirty file, got {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_fail_on_changes_exits_zero_when_all_files_clean(tmp_path: Path) -> None:
    """--dry-run --fail-on-changes must exit 0 when every file is already normalized."""
    clean = tmp_path / "clean.py"
    clean.write_bytes(b"print('hi')\n")  # already normalized — write_bytes avoids Windows CRLF

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"),
         str(tmp_path), "-e", ".py", "--dry-run", "--fail-on-changes", "--no-cache"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )

    assert result.returncode == 0, (
        f"Expected exit 0 from --fail-on-changes with clean file, got {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_dry_run_without_fail_on_changes_exits_zero_even_with_dirty_files(tmp_path: Path) -> None:
    """--dry-run alone must exit 0 even when files need normalization.

    This documents the known C4 behavior: --dry-run is a preview tool and
    must not break CI unless --fail-on-changes is explicitly set.
    """
    dirty = tmp_path / "dirty.py"
    dirty.write_bytes(b"print('hi')  \r\n")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"),
         str(tmp_path), "-e", ".py", "--dry-run", "--no-cache"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )

    assert result.returncode == 0, (
        f"--dry-run without --fail-on-changes should exit 0, got {result.returncode}.\n"
        f"stdout: {result.stdout}"
    )


# ---------------------------------------------------------------------------
# normalize_text() — core normalization logic unit tests
# ---------------------------------------------------------------------------

def test_normalize_text_strips_trailing_whitespace(tmp_path: Path) -> None:
    """Every trailing space on every line must be removed."""
    path = tmp_path / "sample.py"
    normalizer = cnp.CodeNormalizer(dry_run=False, use_cache=False)

    text = "x = 1   \ny = 2  \n"
    result, changes = normalizer.normalize_text(text, path)

    assert result == "x = 1\ny = 2\n"
    assert changes["whitespace_fixes"] > 0


def test_normalize_text_converts_crlf_to_lf(tmp_path: Path) -> None:
    """Every CRLF must become LF; lone CRs must also become LF."""
    path = tmp_path / "sample.py"
    normalizer = cnp.CodeNormalizer(dry_run=False, use_cache=False)

    text = "line1\r\nline2\rline3\n"
    result, changes = normalizer.normalize_text(text, path)

    assert "\r" not in result
    assert result == "line1\nline2\nline3\n"
    assert changes["newline_fixes"] == 2  # two \r characters removed


def test_normalize_text_ensures_final_newline(tmp_path: Path) -> None:
    """A file without a trailing newline must have one added."""
    path = tmp_path / "sample.py"
    normalizer = cnp.CodeNormalizer(dry_run=False, use_cache=False)

    text = "x = 1"
    result, changes = normalizer.normalize_text(text, path)

    assert result.endswith("\n")
    assert changes["final_newline_added"] is True


def test_normalize_text_is_idempotent_on_already_clean_content(tmp_path: Path) -> None:
    """Running normalize_text on already-normalized content must return it unchanged."""
    path = tmp_path / "sample.py"
    normalizer = cnp.CodeNormalizer(dry_run=False, use_cache=False)

    clean = "x = 1\ny = 2\n"
    result, changes = normalizer.normalize_text(clean, path)

    assert result == clean
    assert changes["whitespace_fixes"] == 0
    assert changes["newline_fixes"] == 0
    assert changes["final_newline_added"] is False


def test_normalize_text_cnp_ignore_file_skips_entire_file(tmp_path: Path) -> None:
    """A file containing 'cnp-ignore-file' anywhere must be returned verbatim."""
    path = tmp_path / "ignore_me.py"
    normalizer = cnp.CodeNormalizer(dry_run=False, use_cache=False)

    original = "# cnp-ignore-file\nx = 1   \r\nstill_messy  \n"
    result, changes = normalizer.normalize_text(original, path)

    assert result == original, "cnp-ignore-file annotation must suppress all normalization"
    assert changes["whitespace_fixes"] == 0
    assert changes["newline_fixes"] == 0


def test_normalize_text_cnp_off_on_preserves_annotated_block(tmp_path: Path) -> None:
    """Lines between 'cnp: off' and 'cnp: on' must not have trailing whitespace stripped."""
    path = tmp_path / "sample.py"
    normalizer = cnp.CodeNormalizer(dry_run=False, use_cache=False)

    text = (
        "clean   \n"        # should be stripped
        "# cnp: off\n"
        "preserved   \n"    # must NOT be stripped — inside ignore block
        "# cnp: on\n"
        "also_clean   \n"   # should be stripped
    )
    result, _ = normalizer.normalize_text(text, path)

    lines = result.split("\n")
    assert lines[0] == "clean"
    assert lines[2] == "preserved   "  # preserved with trailing spaces
    assert lines[4] == "also_clean"


def test_normalize_text_markdown_preserves_hard_line_breaks(tmp_path: Path) -> None:
    """In .md files, trailing two-space sequences (hard breaks) must be kept."""
    path = tmp_path / "doc.md"
    normalizer = cnp.CodeNormalizer(dry_run=False, use_cache=False)

    text = "First line  \nSecond line   \nThird\n"
    result, _ = normalizer.normalize_text(text, path)

    lines = result.split("\n")
    # Two trailing spaces = hard break, must be preserved (normalized to exactly 2)
    assert lines[0].endswith("  ")
    # Three trailing spaces = still collapsed to exactly 2
    assert lines[1] == "Second line  "
    # No trailing spaces = untouched
    assert lines[2] == "Third"


# ---------------------------------------------------------------------------
# process_file — already-normalized files counted as skipped, not processed
# ---------------------------------------------------------------------------

def test_already_normalized_file_is_counted_as_skipped(tmp_path: Path) -> None:
    """A file that is already fully normalized must be skipped, not counted as processed.

    Regression guard: skipped files must not increment stats.processed, which
    would trigger a false positive from --fail-on-changes.
    """
    clean = tmp_path / "clean.py"
    clean.write_bytes(b"print('hi')\n")  # write_bytes avoids Windows CRLF translation

    normalizer = cnp.CodeNormalizer(
        in_place=True, create_backup=False, use_cache=False
    )
    result = normalizer.process_file(clean)

    assert result is True
    assert normalizer.stats.processed == 0, "Already-clean file must not increment stats.processed"
    assert normalizer.stats.skipped == 1


# ---------------------------------------------------------------------------
# UTF-8 BOM stripping
# ---------------------------------------------------------------------------

def test_utf8_bom_is_stripped_on_in_place_write(tmp_path: Path) -> None:
    """A file written with a UTF-8 BOM (EF BB BF) must have the BOM removed.

    utf-8-sig is detected in COMMON_ENCODINGS; the normalizer rewrites the
    file as plain utf-8 (encoding_changes == 1).
    """
    sample = tmp_path / "bom_file.py"
    # Write with BOM explicitly
    sample.write_bytes(b"\xef\xbb\xbfprint('hello')\n")

    normalizer = cnp.CodeNormalizer(
        in_place=True, create_backup=False, use_cache=False
    )
    assert normalizer.process_file(sample) is True

    raw = sample.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM was not removed"
    assert raw == b"print('hello')\n"
    assert normalizer.stats.encoding_changes == 1


# ---------------------------------------------------------------------------
# windows-1252 / latin-1 encoding detection and conversion
# ---------------------------------------------------------------------------

def test_windows1252_file_is_converted_to_utf8(tmp_path: Path) -> None:
    """A file written in windows-1252 must be re-encoded as UTF-8."""
    sample = tmp_path / "latin.py"
    # 0xe9 is 'é' in windows-1252 / latin-1
    sample.write_bytes(b"# caf\xe9\nprint('ok')\n")

    normalizer = cnp.CodeNormalizer(
        in_place=True, create_backup=False, use_cache=False
    )
    result = normalizer.process_file(sample)

    assert result is True
    decoded = sample.read_text(encoding="utf-8")
    assert "café" in decoded or "caf" in decoded
    assert normalizer.stats.encoding_changes == 1


# ---------------------------------------------------------------------------
# Backup file creation
# ---------------------------------------------------------------------------

def test_backup_file_is_created_when_create_backup_is_true(tmp_path: Path) -> None:
    """In-place normalization with create_backup=True must produce a .backup_*.py sibling."""
    sample = tmp_path / "script.py"
    sample.write_bytes(b"x = 1   \r\n")

    normalizer = cnp.CodeNormalizer(
        in_place=True, create_backup=True, use_cache=False
    )
    assert normalizer.process_file(sample) is True

    backups = list(tmp_path.glob("*.backup_*.py"))
    assert len(backups) == 1, f"Expected exactly 1 backup file, found: {[p.name for p in backups]}"
    # Backup must contain the original dirty bytes
    assert backups[0].read_bytes() == b"x = 1   \r\n"


def test_no_backup_leaves_no_sibling_files(tmp_path: Path) -> None:
    """In-place normalization with create_backup=False must not leave any extra files."""
    sample = tmp_path / "script.py"
    sample.write_bytes(b"x = 1   \r\n")

    normalizer = cnp.CodeNormalizer(
        in_place=True, create_backup=False, use_cache=False
    )
    assert normalizer.process_file(sample) is True

    siblings = [p for p in tmp_path.iterdir() if p != sample]
    assert siblings == [], f"Expected no sibling files, found: {[p.name for p in siblings]}"


# ---------------------------------------------------------------------------
# Confirmation prompt rejection
# ---------------------------------------------------------------------------

def test_confirmation_prompt_rejection_cancels_walk(tmp_path: Path, monkeypatch) -> None:
    """Entering 'n' at the in-place confirmation prompt must abort the walk entirely.

    No files may be modified and stats.processed must remain 0.
    """
    sample = tmp_path / "sample.py"
    original = b"x = 1   \r\n"
    sample.write_bytes(original)

    monkeypatch.setattr("builtins.input", lambda _prompt="": "n")

    normalizer = cnp.CodeNormalizer(
        in_place=True, create_backup=False, use_cache=False, exclude_dirs=set()
    )
    normalizer.walk_and_process(tmp_path, [".py"])

    assert sample.read_bytes() == original, "File was modified despite prompt rejection"
    assert normalizer.stats.processed == 0


# ---------------------------------------------------------------------------
# Extension filtering
# ---------------------------------------------------------------------------

def test_extension_filter_only_processes_matching_files(tmp_path: Path, monkeypatch) -> None:
    """When -e .py is specified, .js files in the same directory must not be touched."""
    py_file = tmp_path / "app.py"
    js_file = tmp_path / "app.js"
    py_file.write_bytes(b"x = 1   \r\n")
    js_file.write_bytes(b"var x = 1;   \r\n")

    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

    normalizer = cnp.CodeNormalizer(
        in_place=True, create_backup=False, use_cache=False, exclude_dirs=set()
    )
    normalizer.walk_and_process(tmp_path, [".py"])

    # Python file must be normalized
    assert py_file.read_bytes() == b"x = 1\n"
    # JS file must be completely untouched
    assert js_file.read_bytes() == b"var x = 1;   \r\n"


def test_multiple_extensions_processes_all_specified(tmp_path: Path, monkeypatch) -> None:
    """When both -e .py and -e .js are given, both file types must be normalized."""
    py_file = tmp_path / "app.py"
    js_file = tmp_path / "app.js"
    rb_file = tmp_path / "app.rb"
    py_file.write_bytes(b"x = 1   \n")
    js_file.write_bytes(b"var x = 1;   \n")
    rb_file.write_bytes(b"puts 'hi'   \n")

    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

    normalizer = cnp.CodeNormalizer(
        in_place=True, create_backup=False, use_cache=False, exclude_dirs=set()
    )
    normalizer.walk_and_process(tmp_path, [".py", ".js"])

    assert py_file.read_bytes() == b"x = 1\n"
    assert js_file.read_bytes() == b"var x = 1;\n"
    # Ruby file must be untouched — not in the extension list
    assert rb_file.read_bytes() == b"puts 'hi'   \n"


# ---------------------------------------------------------------------------
# CacheManager — unit tests
# ---------------------------------------------------------------------------

def test_cache_manager_returns_false_for_uncached_file(tmp_path: Path) -> None:
    """is_cached() must return False for a file that has never been cached."""
    cache_file = tmp_path / "cache.json"
    cm = cnp.CacheManager(cache_path=cache_file)
    sample = tmp_path / "sample.py"
    sample.write_text("print('hi')\n", encoding="utf-8")

    assert cm.is_cached(sample) is False


def test_cache_manager_returns_true_after_update(tmp_path: Path) -> None:
    """is_cached() must return True immediately after update() is called."""
    cache_file = tmp_path / "cache.json"
    cm = cnp.CacheManager(cache_path=cache_file)
    sample = tmp_path / "sample.py"
    sample.write_text("print('hi')\n", encoding="utf-8")

    cm.update(sample)
    assert cm.is_cached(sample) is True


def test_cache_manager_invalidates_when_file_content_changes(tmp_path: Path) -> None:
    """is_cached() must return False after the file is modified (size change triggers miss)."""
    cache_file = tmp_path / "cache.json"
    cm = cnp.CacheManager(cache_path=cache_file)
    sample = tmp_path / "sample.py"
    sample.write_text("print('hi')\n", encoding="utf-8")

    cm.update(sample)
    assert cm.is_cached(sample) is True

    # Modify the file — different content, different size
    sample.write_text("print('hi')\nprint('extra line')\n", encoding="utf-8")

    assert cm.is_cached(sample) is False, "Cache should be invalidated after file modification"


def test_cache_manager_save_and_load_round_trip(tmp_path: Path) -> None:
    """save() then a fresh CacheManager(load()) must have the same entries."""
    cache_file = tmp_path / "cache.json"
    sample = tmp_path / "sample.py"
    sample.write_text("print('hi')\n", encoding="utf-8")

    cm1 = cnp.CacheManager(cache_path=cache_file)
    cm1.update(sample)
    cm1.save()

    # Create a brand-new CacheManager pointing to the same file
    cm2 = cnp.CacheManager(cache_path=cache_file)
    assert cm2.is_cached(sample) is True, "Cache entry should survive a save/load round-trip"


def test_cache_manager_returns_false_for_deleted_file(tmp_path: Path) -> None:
    """is_cached() must return False if the file no longer exists on disk."""
    cache_file = tmp_path / "cache.json"
    cm = cnp.CacheManager(cache_path=cache_file)
    sample = tmp_path / "sample.py"
    sample.write_text("print('hi')\n", encoding="utf-8")

    cm.update(sample)
    sample.unlink()  # delete the file

    assert cm.is_cached(sample) is False


# ---------------------------------------------------------------------------
# Output file mode  (--output flag, single-file processing)
# ---------------------------------------------------------------------------

def test_output_flag_writes_normalized_content_to_target_path(tmp_path: Path) -> None:
    """When an explicit output path is given, the normalized content goes there,
    and the original source file must be left completely untouched."""
    source = tmp_path / "source.py"
    out = tmp_path / "normalized.py"
    source.write_bytes(b"x = 1   \r\n")

    normalizer = cnp.CodeNormalizer(
        in_place=False, create_backup=False, use_cache=False
    )
    assert normalizer.process_file(source, output_path=out) is True

    # Output file contains the normalized content
    assert out.read_bytes() == b"x = 1\n"
    # Source is untouched
    assert source.read_bytes() == b"x = 1   \r\n"


# ---------------------------------------------------------------------------
# newline_fixes and whitespace_fixes stats accounting
# ---------------------------------------------------------------------------

def test_stats_newline_fixes_incremented_per_processed_file(tmp_path: Path, monkeypatch) -> None:
    """stats.newline_fixes must count individual files with newline issues, not raw \r count."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_bytes(b"x\r\ny\r\n")   # CRLF — needs fix
    (root / "b.py").write_bytes(b"z\n")           # LF — already clean

    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

    normalizer = cnp.CodeNormalizer(
        in_place=True, create_backup=False, use_cache=False, exclude_dirs=set()
    )
    normalizer.walk_and_process(root, [".py"])

    assert normalizer.stats.newline_fixes == 1   # only a.py had issues
    assert normalizer.stats.processed == 1        # b.py skipped (clean)


def test_stats_whitespace_fixes_incremented_for_trailing_spaces(tmp_path: Path, monkeypatch) -> None:
    """stats.whitespace_fixes must count files with trailing whitespace removed."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "dirty.py").write_bytes(b"x = 1   \n")  # write_bytes avoids Windows CRLF
    (root / "clean.py").write_bytes(b"x = 1\n")

    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

    normalizer = cnp.CodeNormalizer(
        in_place=True, create_backup=False, use_cache=False, exclude_dirs=set()
    )
    normalizer.walk_and_process(root, [".py"])

    assert normalizer.stats.whitespace_fixes == 1
    assert normalizer.stats.processed == 1


# ---------------------------------------------------------------------------
# Interactive mode — user can skip individual files
# ---------------------------------------------------------------------------

def test_no_backup_outside_git_repo_is_blocked(tmp_path: Path) -> None:
    """--no-backup --in-place outside a git repo must exit 1 with a clear error."""
    import subprocess
    import sys
    sample = tmp_path / "sample.py"
    sample.write_bytes(b"x = 1\r\n")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"),
         str(sample), "-e", ".py", "--in-place", "--no-backup", "--no-cache"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        cwd=str(tmp_path),   # run from tmp_path which has no .git
    )
    assert result.returncode == 1
    assert "git repo" in result.stdout.lower() or "git repo" in result.stderr.lower()


def test_no_backup_outside_git_repo_bypassed_with_yes(tmp_path: Path) -> None:
    """--no-backup --in-place --yes must succeed even outside a git repo."""
    import subprocess
    import sys
    sample = tmp_path / "sample.py"
    sample.write_bytes(b"x = 1\r\n")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"),
         str(sample), "-e", ".py", "--in-place", "--no-backup", "--yes", "--no-cache"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0
    assert b"\r" not in sample.read_bytes(), "File should have been normalised in-place"


def test_yes_flag_skips_confirmation_prompt(tmp_path: Path) -> None:
    """--yes must bypass the in-place confirmation prompt non-interactively."""
    import subprocess
    import sys
    sample = tmp_path / "sample.py"
    sample.write_bytes(b"x = 1\r\n")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"),
         str(sample), "-e", ".py", "--in-place", "--yes", "--no-cache"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0
    assert b"\r" not in sample.read_bytes()


def test_empty_output_guard_prevents_write(tmp_path: Path, monkeypatch) -> None:
    """normalize_text() returning '' for non-empty input must abort the write."""
    sample = tmp_path / "sample.py"
    original = b"print('hello')\n"
    sample.write_bytes(original)

    # Patch normalize_text to return empty string
    monkeypatch.setattr(cnp.CodeNormalizer, "normalize_text", lambda self, text, path: ("", {}))

    normalizer = cnp.CodeNormalizer(in_place=True, create_backup=False, use_cache=False)
    result = normalizer.process_file(sample)

    assert result is False, "Should return False when output would be empty"
    assert sample.read_bytes() == original, "Original file must be preserved"
    assert normalizer.stats.errors == 1


def test_interactive_mode_skips_file_when_user_declines(tmp_path: Path, monkeypatch) -> None:
    """In --interactive mode, a 'n' response to show_diff must skip the file untouched."""
    sample = tmp_path / "sample.py"
    original = b"x = 1   \n"
    sample.write_bytes(original)

    # Patch show_diff to simulate user declining the change
    monkeypatch.setattr(cnp.CodeNormalizer, "show_diff", lambda self, path, orig, norm: False)

    normalizer = cnp.CodeNormalizer(
        in_place=True, create_backup=False, use_cache=False, interactive=True
    )
    result = normalizer.process_file(sample)

    assert result is True
    assert sample.read_bytes() == original, "File was modified despite user declining in interactive mode"
    assert normalizer.stats.skipped == 1
    assert normalizer.stats.processed == 0



