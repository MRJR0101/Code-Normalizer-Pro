"""Syntax-checker registry and the standalone run_syntax_check() function.

SYNTAX_CHECKERS maps file extensions to checker configurations.  Use the
``register()`` helper to add new languages safely — it validates the entry
shape and normalises the extension.  Direct dict mutation still works for
quick one-off overrides but ``register()`` is the recommended plugin API.

Plugin example::

    from code_normalizer_pro.engine.checkers import register
    register(".zig", ["zig", "ast-check"], file_arg=True)
    register(".gleam", ["gleam", "check"], stdin=False, file_arg=False)
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Checker registry
# ---------------------------------------------------------------------------

SYNTAX_CHECKERS: Dict[str, dict] = {
    ".py": {
        "command": [sys.executable, "-m", "py_compile"],
        "stdin": False,
        "file_arg": True,
    },
    ".js": {
        "command": ["node", "--check"],
        "stdin": False,
        "file_arg": True,
    },
    ".ts": {
        "command": ["tsc", "--noEmit"],
        "stdin": False,
        "file_arg": True,
    },
    ".go": {
        "command": ["gofmt", "-e"],
        "stdin": True,
        "file_arg": False,
    },
    ".rs": {
        "command": ["rustc", "--crate-type", "lib", "-"],
        "stdin": True,
        "file_arg": False,
    },
    ".c": {
        "command": ["gcc", "-fsyntax-only", "-x", "c"],
        "stdin": False,
        "file_arg": True,
    },
    ".cpp": {
        "command": ["g++", "-fsyntax-only", "-x", "c++"],
        "stdin": False,
        "file_arg": True,
    },
    ".java": {
        "command": ["javac", "-Xstdout"],
        "stdin": False,
        "file_arg": True,
    },
    ".json": {
        "command": [sys.executable, "-m", "json.tool"],
        "stdin": True,
        "file_arg": False,
    },
    ".sh": {
        "command": ["bash", "-n"],
        "stdin": False,
        "file_arg": True,
    },
    ".rb": {
        "command": ["ruby", "-c"],
        "stdin": False,
        "file_arg": True,
    },
    ".php": {
        "command": ["php", "-l"],
        "stdin": False,
        "file_arg": True,
    },
    ".pl": {
        "command": ["perl", "-c"],
        "stdin": False,
        "file_arg": True,
    },
    ".lua": {
        "command": ["luac", "-p"],
        "stdin": False,
        "file_arg": True,
    },
}


# ---------------------------------------------------------------------------
# Standalone checker function
# ---------------------------------------------------------------------------

def run_syntax_check(
    path: Path,
    content: Optional[str] = None,
    syntax_timeout: int = 10,
) -> Tuple[bool, str]:
    """Run the appropriate syntax checker for *path*.

    When *content* is supplied the check runs against that in-memory text
    (written to a temp file for file-arg checkers, or piped via stdin).
    When *content* is None the checker runs against the file on disk.

    Returns ``(ok, reason)`` where *reason* is a short human-readable string.
    A missing checker binary is treated as a pass (True, '<tool> not installed')
    so that users without every language toolchain installed are not blocked.
    """
    ext = path.suffix.lower()

    if ext not in SYNTAX_CHECKERS:
        return True, "No checker available"

    checker = SYNTAX_CHECKERS[ext]
    cmd = checker["command"].copy()
    temp_path: Optional[Path] = None
    temp_dir: Optional[tempfile.TemporaryDirectory] = None

    try:
        if checker["file_arg"]:
            target_path = path
            if content is not None:
                temp_dir = tempfile.TemporaryDirectory()
                temp_path = Path(temp_dir.name) / path.name
                temp_path.write_text(content, encoding="utf-8", newline="\n")
                target_path = temp_path

            # Use absolute path to prevent filenames starting with '-' being
            # parsed as flags by the checker binary.
            cmd.append(str(target_path.absolute()))
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=syntax_timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        else:
            if content is None:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            result = subprocess.run(
                cmd,
                input=content,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=syntax_timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        if result.returncode == 0:
            return True, "OK"
        return False, (result.stderr or "").strip()[:100]

    except FileNotFoundError:
        return True, f"{checker['command'][0]} not installed"
    except subprocess.TimeoutExpired:
        return False, f"Timeout after {syntax_timeout}s"
    except Exception as e:
        return False, str(e)[:100]
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


# ---------------------------------------------------------------------------
# Plugin registry API
# ---------------------------------------------------------------------------

def register(
    ext: str,
    command: list,
    *,
    stdin: bool = False,
    file_arg: bool = True,
) -> None:
    """Register a custom syntax checker for *ext*.

    Parameters
    ----------
    ext:
        File extension including the leading dot, e.g. ``".zig"``.
    command:
        Executable and fixed arguments, e.g. ``["zig", "ast-check"]``.
        The file path (or stdin content) is appended automatically at
        runtime based on *file_arg* / *stdin*.
    stdin:
        Pass file content via stdin rather than as a positional argument.
    file_arg:
        Append the file path as the last argument to *command*.
        Set to ``False`` when the checker only accepts stdin.

    Raises
    ------
    ValueError
        If *ext* does not start with ``'.'`` or *command* is empty.

    Example::

        from code_normalizer_pro.engine.checkers import register
        register(".zig", ["zig", "ast-check"], file_arg=True)
        register(".gleam", ["gleam", "check"], stdin=True, file_arg=False)
    """
    if not ext.startswith("."):
        raise ValueError(f"Extension must start with '.', got {ext!r}")
    if not command:
        raise ValueError("command must be a non-empty list")
    SYNTAX_CHECKERS[ext.lower()] = {
        "command": list(command),
        "stdin": bool(stdin),
        "file_arg": bool(file_arg),
    }


def unregister(ext: str) -> bool:
    """Remove a checker from the registry.

    Returns ``True`` if the extension existed and was removed, ``False`` if
    it was not present.

    Example::

        from code_normalizer_pro.engine.checkers import unregister
        unregister(".ts")   # disable TypeScript checking for this project
    """
    return SYNTAX_CHECKERS.pop(ext.lower(), None) is not None
