"""Pure text normalisation — no file I/O, no instance state.

The standalone ``normalize_text()`` function is the core transformation.
``CodeNormalizer`` resolves the tab size via ``EditorConfigResolver`` and then
delegates here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple


def normalize_text(text: str, path: Path, *, tabs_size: int = 0) -> Tuple[str, dict]:
    """Normalize *text* content and return ``(normalized_text, change_counts)``.

    Parameters
    ----------
    text:
        Raw file content as a Unicode string.
    path:
        Source file path (used for extension checks, e.g. Markdown hard breaks).
    tabs_size:
        If > 0, expand tabs to this many spaces.  Already resolved by the caller
        via :class:`EditorConfigResolver`.

    Returns
    -------
    tuple
        ``(normalized_text, changes)`` where *changes* is a dict with keys
        ``newline_fixes``, ``whitespace_fixes``, ``bytes_removed``,
        ``final_newline_added``.
    """
    changes: dict = {
        "newline_fixes": 0,
        "whitespace_fixes": 0,
        "bytes_removed": 0,
        "final_newline_added": False,
    }

    if "cnp-ignore-file" in text:
        return text, changes

    original = text
    original_size = len(text.encode("utf-8"))

    if tabs_size > 0 and "\t" in text:
        text = text.expandtabs(tabs_size)

    if "\r\n" in text or "\r" in text:
        changes["newline_fixes"] = original.count("\r")
        text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = text.split("\n")
    stripped_lines = []
    is_markdown = path.suffix.lower() in {".md", ".markdown"}
    ignoring = False

    for orig_line in lines:
        if "cnp: off" in orig_line:
            ignoring = True
        elif "cnp: on" in orig_line:
            ignoring = False

        if ignoring:
            stripped_lines.append(orig_line)
        else:
            stripped = orig_line.rstrip()
            if is_markdown and orig_line.endswith("  "):
                stripped += "  "
            stripped_lines.append(stripped)

    changes["whitespace_fixes"] = sum(
        len(o) - len(s) for o, s in zip(lines, stripped_lines)
    )

    text = "\n".join(stripped_lines)

    if not text.endswith("\n"):
        text += "\n"
        changes["final_newline_added"] = True

    changes["bytes_removed"] = original_size - len(text.encode("utf-8"))

    return text, changes
