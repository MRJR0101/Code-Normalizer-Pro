"""File I/O helpers: atomic write, backup creation, output path, interactive diff."""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def create_backup_file(path: Path) -> Path:
    """Create a timestamped backup copy of *path* (microsecond-safe for parallel runs)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = path.with_suffix(f".backup_{timestamp}{path.suffix}")
    shutil.copy2(path, backup_path)
    return backup_path


def get_output_path(
    input_path: Path,
    output_path: Optional[Path],
    in_place: bool,
) -> Path:
    """Determine the destination path for normalised output."""
    if output_path:
        return output_path
    if in_place:
        return input_path
    return input_path.with_name(input_path.stem + "_clean" + input_path.suffix)


def atomic_write(out_path: Path, content: str) -> None:
    """Write *content* to *out_path* atomically via a temp-sibling + ``os.replace``.

    Preserves existing file permissions.  Falls back to a two-step rename on
    Windows when ``os.replace`` fails across volumes or with locked files.
    """
    tmp_path = out_path.with_name(out_path.name + ".cnp-tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8", newline="\n")
        if out_path.exists():
            shutil.copymode(out_path, tmp_path)
        try:
            os.replace(str(tmp_path), str(out_path))
        except OSError as replace_err:
            if out_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                fallback_bak = out_path.with_name(
                    f"{out_path.name}.bak_pre_{timestamp}"
                )
                os.rename(str(out_path), str(fallback_bak))
                try:
                    os.rename(str(tmp_path), str(out_path))
                    fallback_bak.unlink(missing_ok=True)
                except Exception as e:
                    os.rename(str(fallback_bak), str(out_path))
                    raise e from replace_err
            else:
                os.rename(str(tmp_path), str(out_path))
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def show_diff(path: Path, original: str, normalized: str) -> bool:
    """Display a line-by-line diff and prompt the user for approval.

    Returns ``True`` if the user approves applying the changes.
    """
    print(f"\n{'=' * 70}")
    print(f"File: {path}")
    print(f"{'=' * 70}")

    orig_lines = original.split("\n")
    norm_lines = normalized.split("\n")
    changes = [
        (i, orig, norm)
        for i, (orig, norm) in enumerate(zip(orig_lines, norm_lines), 1)
        if orig != norm
    ]

    for line_num, orig, norm in changes[:10]:
        print(f"\nLine {line_num}:")
        print(f"  - {repr(orig)}")
        print(f"  + {repr(norm)}")

    if len(changes) > 10:
        print(f"\n... and {len(changes) - 10} more changes")

    print(f"\n{'=' * 70}")

    while True:
        choice = input("Apply changes? [y]es / [n]o / [d]iff all / [q]uit: ").lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no"):
            return False
        if choice in ("d", "diff"):
            for line_num, orig, norm in changes:
                print(f"\nLine {line_num}:")
                print(f"  - {repr(orig)}")
                print(f"  + {repr(norm)}")
        elif choice in ("q", "quit"):
            print("Quitting...")
            sys.exit(0)
        else:
            print("Invalid choice. Please enter y, n, d, or q.")
