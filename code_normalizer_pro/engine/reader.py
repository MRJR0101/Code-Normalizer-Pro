"""Encoding detection and file reading.

Standalone functions extracted from CodeNormalizer so they can be reused and
tested without instantiating a full normalizer.
"""

from __future__ import annotations

import mmap
from pathlib import Path
from typing import List, Tuple

COMMON_ENCODINGS: List[str] = [
    "utf-8",
    "utf-8-sig",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "windows-1252",
    "latin-1",
    "iso-8859-1",
]

_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _looks_like_utf16_text(data: bytes) -> bool:
    """Best-effort check for UTF-16 text content before binary rejection."""
    if not data:
        return False
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return True
    sample = data[:256]
    if len(sample) < 4:
        return False
    for enc in ("utf-16-le", "utf-16-be"):
        try:
            decoded = sample.decode(enc)
        except UnicodeDecodeError:
            continue
        if not decoded:
            continue
        printable = sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t")
        alpha = sum(1 for ch in decoded if ch.isalpha())
        printable_ratio = printable / len(decoded)
        if printable_ratio >= 0.85 and alpha >= max(1, len(decoded) // 20):
            return True
    return False


def guess_and_read(path: Path, *, max_size: int = _MAX_FILE_SIZE) -> Tuple[str, str]:
    """Detect file encoding and return ``(encoding_name, text_content)``.

    Raises
    ------
    ValueError
        If the file is binary or exceeds *max_size*.
    UnicodeError
        If no common encoding can decode the file.
    """
    if path.stat().st_size > max_size:
        raise ValueError("File exceeds maximum size limit of 50MB for in-memory processing")

    try:
        if path.stat().st_size > 0:
            with open(path, "rb") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    if b"\x00" in mm:
                        sample = mm[:256]
                        if not _looks_like_utf16_text(sample):
                            raise ValueError("File appears to be binary")
    except ValueError:
        raise
    except Exception:
        pass

    data = path.read_bytes()

    if b"\x00" in data and not _looks_like_utf16_text(data):
        raise ValueError("File appears to be binary")

    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", data[3:].decode("utf-8")

    last_error = None
    for enc in COMMON_ENCODINGS:
        try:
            return enc, data.decode(enc)
        except UnicodeDecodeError as e:
            last_error = e

    raise UnicodeError("Could not decode with common encodings") from last_error
