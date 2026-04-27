"""EditorConfig resolution — hierarchical .editorconfig lookup with brace expansion."""

from __future__ import annotations

import configparser
import fnmatch
from pathlib import Path
from typing import Dict, List, Optional


class EditorConfigResolver:
    """Resolve per-file indent settings from ``.editorconfig`` hierarchies.

    Caches parsed files to avoid repeated filesystem reads within a single run.

    Usage::

        resolver = EditorConfigResolver()
        tabs_size = resolver.resolve_indent_size(path, default=expand_tabs)
    """

    def __init__(self) -> None:
        self._cache: Dict[Path, Optional[configparser.ConfigParser]] = {}

    def resolve_indent_size(self, path: Path, default: int = 0) -> int:
        """Return the tab-expansion size for *path*.

        Priority: *default* (CLI/config) > ``.editorconfig`` indent_size > 0 (disabled).
        """
        if default > 0:
            return default

        current = path.parent
        while True:
            parser = self._get_editorconfig(current)
            if parser:
                found, indent_size = False, 0
                for section in parser.sections():
                    if self._editorconfig_match(path.name, section):
                        if "indent_size" in parser[section]:
                            val = parser[section]["indent_size"]
                            if val.isdigit():
                                indent_size = int(val)
                                found = True
                if found:
                    return indent_size
                is_root = (
                    parser.has_section("__preamble__")
                    and parser["__preamble__"].get("root", "").lower() == "true"
                ) or parser.defaults().get("root", "").lower() == "true"
                if is_root:
                    break
            if current == current.parent:
                break
            current = current.parent

        return 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _expand_braces(self, pattern: str) -> List[str]:
        """Expand ``*.{js,py}`` into ``["*.js", "*.py"]``."""
        end = pattern.find("}")
        if end != -1:
            start = pattern.rfind("{", 0, end)
            if start != -1:
                pre, post = pattern[:start], pattern[end + 1:]
                expanded: List[str] = []
                for opt in pattern[start + 1:end].split(","):
                    expanded.extend(self._expand_braces(pre + opt + post))
                return expanded
        return [pattern]

    def _editorconfig_match(self, filename: str, pattern: str) -> bool:
        """Match *filename* against an editorconfig glob (supports brace expansion)."""
        return any(fnmatch.fnmatch(filename, p) for p in self._expand_braces(pattern))

    def _get_editorconfig(
        self, dir_path: Path
    ) -> Optional[configparser.ConfigParser]:
        if dir_path in self._cache:
            return self._cache[dir_path]

        ec_path = dir_path / ".editorconfig"
        if ec_path.exists():
            try:
                raw = ec_path.read_text(encoding="utf-8")
                if raw.lstrip() and not raw.lstrip().startswith("["):
                    raw = "[__preamble__]\n" + raw
                parser = configparser.ConfigParser(interpolation=None)
                parser.read_string(raw)
                self._cache[dir_path] = parser
                return parser
            except Exception:
                pass

        self._cache[dir_path] = None
        return None
