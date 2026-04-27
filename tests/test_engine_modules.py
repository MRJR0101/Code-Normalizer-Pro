"""Unit tests for the extracted engine modules.

Covers:
  - engine/reader.py       (guess_and_read, COMMON_ENCODINGS, _looks_like_utf16_text)
  - engine/editorconfig.py (EditorConfigResolver)
  - engine/text_transform.py (normalize_text)
  - engine/fileops.py      (atomic_write, create_backup_file, get_output_path)
  - engine/workers.py      (_init_worker, process_file_worker)
  - engine/cache.py        (CacheBackend Protocol, JsonCacheBackend, SqliteCacheBackend)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from code_normalizer_pro.engine.reader import (
    COMMON_ENCODINGS,
    _looks_like_utf16_text,
    guess_and_read,
)
from code_normalizer_pro.engine.editorconfig import EditorConfigResolver
from code_normalizer_pro.engine.text_transform import normalize_text
from code_normalizer_pro.engine.fileops import (
    atomic_write,
    create_backup_file,
    get_output_path,
)
from code_normalizer_pro.engine.workers import _init_worker, process_file_worker
from code_normalizer_pro.engine.cache import (
    CacheBackend,
    CacheManager,
    JsonCacheBackend,
    SqliteCacheBackend,
)


# ===========================================================================
# reader.py
# ===========================================================================

class TestCommonEncodings:
    def test_is_list_of_strings(self) -> None:
        assert isinstance(COMMON_ENCODINGS, list)
        assert all(isinstance(enc, str) for enc in COMMON_ENCODINGS)

    def test_contains_utf8_and_latin1(self) -> None:
        assert "utf-8" in COMMON_ENCODINGS
        assert "latin-1" in COMMON_ENCODINGS

    def test_utf8_is_first(self) -> None:
        """utf-8 must come first so clean UTF-8 files are handled fastest."""
        assert COMMON_ENCODINGS[0] == "utf-8"


class TestLooksLikeUtf16Text:
    def test_empty_bytes_returns_false(self) -> None:
        assert _looks_like_utf16_text(b"") is False

    def test_utf16_bom_le_returns_true(self) -> None:
        assert _looks_like_utf16_text(b"\xff\xfehello") is True

    def test_utf16_bom_be_returns_true(self) -> None:
        assert _looks_like_utf16_text(b"\xfe\xffhello") is True

    def test_interleaved_control_chars_return_false(self) -> None:
        # Interleaved pattern: LE decodes to 50% printable, BE also 50% printable.
        # Both ratios fall below the 0.85 threshold → returns False.
        # b"\x01\x00\x00\x01..." as LE: U+0001 (non-print), U+0100 (Ā, print) → 50%
        # same bytes as BE: U+0100 (print), U+0001 (non-print) → 50%
        data = b"\x01\x00\x00\x01\x02\x00\x00\x02" * 32
        assert _looks_like_utf16_text(data) is False

    def test_null_only_bytes_returns_false(self) -> None:
        assert _looks_like_utf16_text(b"\x00\x00\x00\x00") is False


class TestGuessAndRead:
    def test_reads_utf8_file(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.py"
        f.write_text("x = 1\n", encoding="utf-8")
        enc, text = guess_and_read(f)
        assert enc == "utf-8"
        assert "x = 1" in text

    def test_reads_utf8_bom_file(self, tmp_path: Path) -> None:
        f = tmp_path / "bom.py"
        f.write_bytes(b"\xef\xbb\xbf# coding\n")
        enc, text = guess_and_read(f)
        assert enc == "utf-8-sig"
        assert "# coding" in text

    def test_reads_utf16_file(self, tmp_path: Path) -> None:
        f = tmp_path / "utf16.py"
        f.write_text("print('hi')\n", encoding="utf-16")
        enc, text = guess_and_read(f)
        assert enc.startswith("utf-16")
        assert "print('hi')" in text

    def test_reads_windows1252_file(self, tmp_path: Path) -> None:
        f = tmp_path / "w1252.py"
        f.write_bytes("caf\xe9\n".encode("windows-1252"))
        enc, text = guess_and_read(f)
        assert enc in ("windows-1252", "latin-1", "iso-8859-1")
        assert "caf" in text

    def test_raises_for_binary_file(self, tmp_path: Path) -> None:
        # Interleaved control-char pattern causes _looks_like_utf16_text to
        # return False for both LE and BE (printable ratio ~50% < threshold 85%).
        # guess_and_read must therefore raise ValueError("binary").
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\x01\x00\x00\x01\x02\x00\x00\x02" * 32)
        with pytest.raises(ValueError, match="binary"):
            guess_and_read(f)

    def test_raises_for_oversized_file(self, tmp_path: Path, monkeypatch) -> None:
        f = tmp_path / "big.py"
        f.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(f.stat().__class__, "st_size", property(lambda self: 51 * 1024 * 1024))
        with pytest.raises((ValueError, Exception)):
            guess_and_read(f, max_size=1024)

    def test_returns_tuple_of_two_strings(self, tmp_path: Path) -> None:
        f = tmp_path / "t.py"
        f.write_text("pass\n", encoding="utf-8")
        result = guess_and_read(f)
        assert isinstance(result, tuple) and len(result) == 2
        assert all(isinstance(x, str) for x in result)


# ===========================================================================
# editorconfig.py
# ===========================================================================

class TestEditorConfigResolver:
    def test_instantiates_without_error(self) -> None:
        resolver = EditorConfigResolver()
        assert resolver is not None

    def test_returns_zero_when_no_editorconfig_and_default_zero(
        self, tmp_path: Path
    ) -> None:
        resolver = EditorConfigResolver()
        result = resolver.resolve_indent_size(tmp_path / "sample.py", default=0)
        assert result == 0

    def test_default_overrides_editorconfig_lookup(
        self, tmp_path: Path
    ) -> None:
        """When default > 0 it short-circuits before any filesystem read."""
        resolver = EditorConfigResolver()
        result = resolver.resolve_indent_size(tmp_path / "sample.py", default=4)
        assert result == 4

    def test_reads_indent_size_from_editorconfig(self, tmp_path: Path) -> None:
        ec = tmp_path / ".editorconfig"
        ec.write_text("[*.py]\nindent_size = 2\n", encoding="utf-8")
        f = tmp_path / "sample.py"
        f.write_text("pass\n", encoding="utf-8")
        resolver = EditorConfigResolver()
        assert resolver.resolve_indent_size(f, default=0) == 2

    def test_ignores_non_matching_section(self, tmp_path: Path) -> None:
        ec = tmp_path / ".editorconfig"
        ec.write_text("[*.js]\nindent_size = 2\n", encoding="utf-8")
        f = tmp_path / "sample.py"
        f.write_text("pass\n", encoding="utf-8")
        resolver = EditorConfigResolver()
        assert resolver.resolve_indent_size(f, default=0) == 0

    def test_brace_expansion_matches_py_in_set(self, tmp_path: Path) -> None:
        ec = tmp_path / ".editorconfig"
        ec.write_text("[*.{py,js}]\nindent_size = 3\n", encoding="utf-8")
        f = tmp_path / "sample.py"
        f.write_text("pass\n", encoding="utf-8")
        resolver = EditorConfigResolver()
        assert resolver.resolve_indent_size(f, default=0) == 3

    def test_expand_braces_single_option(self) -> None:
        resolver = EditorConfigResolver()
        assert resolver._expand_braces("*.{py}") == ["*.py"]

    def test_expand_braces_multiple_options(self) -> None:
        resolver = EditorConfigResolver()
        result = resolver._expand_braces("*.{py,js,ts}")
        assert set(result) == {"*.py", "*.js", "*.ts"}

    def test_expand_braces_no_braces(self) -> None:
        resolver = EditorConfigResolver()
        assert resolver._expand_braces("*.py") == ["*.py"]

    def test_editorconfig_match_exact_extension(self) -> None:
        resolver = EditorConfigResolver()
        assert resolver._editorconfig_match("main.py", "*.py") is True

    def test_editorconfig_match_wrong_extension(self) -> None:
        resolver = EditorConfigResolver()
        assert resolver._editorconfig_match("main.py", "*.js") is False

    def test_caches_parsed_files(self, tmp_path: Path) -> None:
        """Second call for same directory must not re-read the file."""
        ec = tmp_path / ".editorconfig"
        ec.write_text("[*.py]\nindent_size = 4\n", encoding="utf-8")
        f = tmp_path / "sample.py"
        f.write_text("pass\n", encoding="utf-8")
        resolver = EditorConfigResolver()
        resolver.resolve_indent_size(f, default=0)
        # Overwrite the file — cached result should still be returned
        ec.write_text("[*.py]\nindent_size = 99\n", encoding="utf-8")
        assert resolver.resolve_indent_size(f, default=0) == 4


# ===========================================================================
# text_transform.py
# ===========================================================================

class TestNormalizeTextStandalone:
    def test_strips_trailing_whitespace(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        text, changes = normalize_text("x = 1   \n", f)
        assert text == "x = 1\n"
        assert changes["whitespace_fixes"] > 0

    def test_converts_crlf_to_lf(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        text, changes = normalize_text("a\r\nb\r\n", f)
        assert "\r" not in text
        assert changes["newline_fixes"] > 0

    def test_converts_bare_cr_to_lf(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        text, changes = normalize_text("a\rb\r", f)
        assert "\r" not in text
        assert changes["newline_fixes"] > 0

    def test_adds_final_newline(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        text, changes = normalize_text("x = 1", f)
        assert text.endswith("\n")
        assert changes["final_newline_added"] is True

    def test_idempotent_on_clean_content(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        clean = "x = 1\ny = 2\n"
        text, changes = normalize_text(clean, f)
        assert text == clean
        assert changes["whitespace_fixes"] == 0
        assert changes["newline_fixes"] == 0
        assert changes["final_newline_added"] is False

    def test_expands_tabs_when_tabs_size_given(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        text, _ = normalize_text("\tx = 1\n", f, tabs_size=4)
        assert "\t" not in text
        assert "    x = 1" in text

    def test_no_tab_expansion_when_tabs_size_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        text, _ = normalize_text("\tx = 1\n", f, tabs_size=0)
        assert "\t" in text

    def test_cnp_ignore_file_returns_unchanged(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        content = "x = 1   \r\n# cnp-ignore-file\n"
        text, _ = normalize_text(content, f)
        assert text == content

    def test_cnp_off_on_preserves_block(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        content = "clean   \n# cnp: off\nraw   \n# cnp: on\nclean again   \n"
        text, _ = normalize_text(content, f)
        assert "raw   " in text
        assert "clean   " not in text

    def test_markdown_preserves_hard_line_breaks(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        content = "line one  \nline two\n"
        text, _ = normalize_text(content, f)
        assert text.split("\n")[0].endswith("  ")

    def test_returns_correct_change_keys(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        _, changes = normalize_text("x\n", f)
        assert set(changes.keys()) == {
            "newline_fixes", "whitespace_fixes", "bytes_removed", "final_newline_added"
        }

    def test_bytes_removed_is_non_negative(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        _, changes = normalize_text("x = 1   \r\n", f)
        assert changes["bytes_removed"] >= 0


# ===========================================================================
# fileops.py
# ===========================================================================

class TestAtomicWrite:
    def test_creates_file_with_correct_content(self, tmp_path: Path) -> None:
        out = tmp_path / "out.py"
        atomic_write(out, "x = 1\n")
        assert out.read_text(encoding="utf-8") == "x = 1\n"

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        out = tmp_path / "out.py"
        out.write_text("old\n", encoding="utf-8")
        atomic_write(out, "new\n")
        assert out.read_text(encoding="utf-8") == "new\n"

    def test_no_temp_file_left_behind(self, tmp_path: Path) -> None:
        out = tmp_path / "out.py"
        atomic_write(out, "data\n")
        leftovers = list(tmp_path.glob("*.cnp-tmp"))
        assert leftovers == []

    def test_writes_utf8_content(self, tmp_path: Path) -> None:
        out = tmp_path / "out.py"
        atomic_write(out, "café\n")
        raw = out.read_bytes()
        assert raw == "café\n".encode("utf-8")

    def test_newlines_are_lf(self, tmp_path: Path) -> None:
        out = tmp_path / "out.py"
        atomic_write(out, "a\nb\n")
        raw = out.read_bytes()
        assert b"\r\n" not in raw


class TestCreateBackupFile:
    def test_returns_path(self, tmp_path: Path) -> None:
        src = tmp_path / "src.py"
        src.write_text("data\n", encoding="utf-8")
        bak = create_backup_file(src)
        assert isinstance(bak, Path)

    def test_backup_exists(self, tmp_path: Path) -> None:
        src = tmp_path / "src.py"
        src.write_text("data\n", encoding="utf-8")
        bak = create_backup_file(src)
        assert bak.exists()

    def test_backup_has_same_content(self, tmp_path: Path) -> None:
        src = tmp_path / "src.py"
        src.write_text("original\n", encoding="utf-8")
        bak = create_backup_file(src)
        assert bak.read_text(encoding="utf-8") == "original\n"

    def test_backup_name_contains_timestamp(self, tmp_path: Path) -> None:
        src = tmp_path / "src.py"
        src.write_text("x\n", encoding="utf-8")
        bak = create_backup_file(src)
        assert "backup_" in bak.name

    def test_two_backups_have_different_names(self, tmp_path: Path) -> None:
        import time
        src = tmp_path / "src.py"
        src.write_text("x\n", encoding="utf-8")
        bak1 = create_backup_file(src)
        time.sleep(0.01)
        bak2 = create_backup_file(src)
        assert bak1.name != bak2.name


class TestGetOutputPath:
    def test_in_place_returns_input_path(self, tmp_path: Path) -> None:
        p = tmp_path / "f.py"
        assert get_output_path(p, None, in_place=True) == p

    def test_explicit_output_path_returned(self, tmp_path: Path) -> None:
        p = tmp_path / "f.py"
        out = tmp_path / "out.py"
        assert get_output_path(p, out, in_place=False) == out

    def test_default_appends_clean_suffix(self, tmp_path: Path) -> None:
        p = tmp_path / "main.py"
        result = get_output_path(p, None, in_place=False)
        assert result.name == "main_clean.py"

    def test_explicit_path_takes_precedence_over_in_place(
        self, tmp_path: Path
    ) -> None:
        p = tmp_path / "f.py"
        out = tmp_path / "explicit.py"
        assert get_output_path(p, out, in_place=True) == out


# ===========================================================================
# workers.py
# ===========================================================================

class TestInitWorker:
    def test_runs_without_error_with_no_log_file(self) -> None:
        """_init_worker(None) must not raise regardless of loguru state."""
        _init_worker(None)

    def test_runs_without_error_with_log_file(self, tmp_path: Path) -> None:
        log = tmp_path / "worker.log"
        _init_worker(log)


class TestProcessFileWorker:
    def test_returns_three_tuple(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        f.write_text("x = 1\n", encoding="utf-8")
        result = process_file_worker(f, dry_run=True, in_place=False,
                                     create_backup=False, check_syntax=False)
        assert isinstance(result, tuple) and len(result) == 3

    def test_success_flag_true_for_valid_file(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        f.write_text("x = 1\n", encoding="utf-8")
        success, _, _ = process_file_worker(f, dry_run=True, in_place=False,
                                            create_backup=False, check_syntax=False)
        assert success is True

    def test_stats_dict_has_expected_keys(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        f.write_text("x = 1\n", encoding="utf-8")
        _, stats, _ = process_file_worker(f, dry_run=True, in_place=False,
                                          create_backup=False, check_syntax=False)
        expected_keys = {
            "processed", "skipped", "encoding_changes", "newline_fixes",
            "whitespace_fixes", "bytes_removed",
            "syntax_checks_passed", "syntax_checks_failed",
        }
        assert expected_keys.issubset(stats.keys())

    def test_error_string_empty_on_success(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        f.write_text("x = 1\n", encoding="utf-8")
        _, _, error = process_file_worker(f, dry_run=True, in_place=False,
                                          create_backup=False, check_syntax=False)
        assert error == ""

    def test_handles_nonexistent_file_gracefully(self, tmp_path: Path) -> None:
        f = tmp_path / "ghost.py"
        success, _, error = process_file_worker(f, dry_run=True, in_place=False,
                                               create_backup=False, check_syntax=False)
        assert success is False
        assert error != ""

    def test_normalizes_dirty_file_in_place(self, tmp_path: Path) -> None:
        f = tmp_path / "dirty.py"
        f.write_bytes(b"x = 1   \r\n")
        success, stats, _ = process_file_worker(f, dry_run=False, in_place=True,
                                                create_backup=False, check_syntax=False)
        assert success is True
        assert f.read_bytes() == b"x = 1\n"


# ===========================================================================
# cache.py — CacheBackend Protocol, JsonCacheBackend, SqliteCacheBackend
# ===========================================================================

class TestCacheBackendProtocol:
    def test_cachemanager_satisfies_protocol(self, tmp_path: Path) -> None:
        """isinstance check works because CacheBackend is @runtime_checkable."""
        cm = CacheManager(tmp_path / "cache.json")
        assert isinstance(cm, CacheBackend)

    def test_protocol_methods_present(self) -> None:
        for method in ("load", "save", "get_file_hash", "is_cached", "update"):
            assert hasattr(CacheBackend, method), f"Protocol missing: {method}"

    def test_arbitrary_class_without_methods_does_not_satisfy(self) -> None:
        class NotACache:
            pass
        assert not isinstance(NotACache(), CacheBackend)

    def test_class_with_all_methods_satisfies(self) -> None:
        from pathlib import Path as _Path

        class MinimalCache:
            def load(self) -> None: ...
            def save(self) -> None: ...
            def get_file_hash(self, path: _Path) -> str: return ""
            def is_cached(self, path: _Path) -> bool: return False
            def update(self, path: _Path) -> None: ...

        assert isinstance(MinimalCache(), CacheBackend)


class TestJsonCacheBackend:
    def test_is_cachemanager_alias(self) -> None:
        assert JsonCacheBackend is CacheManager

    def test_instantiates_correctly(self, tmp_path: Path) -> None:
        jcb = JsonCacheBackend(tmp_path / "j.json")
        assert isinstance(jcb, CacheManager)

    def test_satisfies_cachebackend_protocol(self, tmp_path: Path) -> None:
        jcb = JsonCacheBackend(tmp_path / "j.json")
        assert isinstance(jcb, CacheBackend)


class TestSqliteCacheBackendStub:
    def test_raises_not_implemented_on_init(self) -> None:
        with pytest.raises(NotImplementedError, match="SqliteCacheBackend"):
            SqliteCacheBackend()

    def test_load_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            SqliteCacheBackend.load(None)  # type: ignore[arg-type]

    def test_save_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            SqliteCacheBackend.save(None)  # type: ignore[arg-type]

    def test_is_cached_raises_not_implemented(self, tmp_path: Path) -> None:
        with pytest.raises(NotImplementedError):
            SqliteCacheBackend.is_cached(None, tmp_path / "f.py")  # type: ignore[arg-type]

    def test_update_raises_not_implemented(self, tmp_path: Path) -> None:
        with pytest.raises(NotImplementedError):
            SqliteCacheBackend.update(None, tmp_path / "f.py")  # type: ignore[arg-type]
