"""Syntax-checker registry and the standalone run_syntax_check() function.

SYNTAX_CHECKERS maps file extensions to checker configurations.  The registry
is intentionally a plain dict so new languages can be added via a simple
``SYNTAX_CHECKERS['.zig'] = {...}`` assignment — the plug-in hook (v2.0) will
wrap this with a ``register()`` helper that validates the entry shape.
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
