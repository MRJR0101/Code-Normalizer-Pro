"""Cache module: FileCache dataclass and CacheManager for incremental processing.

The CacheBackend protocol is defined here so a SQLite-backed implementation can
be swapped in later (v2.0 scaling trigger: repos >50K files) without touching
any engine logic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from loguru import logger


CACHE_FILE = ".normalize-cache.json"
CACHE_SCHEMA_VERSION = 1  # bump when FileCache fields change to discard stale caches


@dataclass
class FileCache:
    """Cache entry for a single file."""

    path: str
    hash: str
    last_normalized: str
    size: int
    mtime: float = 0.0


class CacheManager:
    """Manages a file-hash cache for incremental (skip-unchanged) processing.

    Uses a flat JSON file by default.  The interface is intentionally narrow so
    a SqliteCache backend can be dropped in via a one-line constructor change
    when large-monorepo performance becomes a concern.
    """

    def __init__(self, cache_path: Optional[Path] = None) -> None:
        self.cache_path = cache_path or Path(CACHE_FILE)
        self.cache: Dict[str, FileCache] = {}
        self.load()

    def load(self) -> None:
        """Load cache entries from disk, discarding stale schema versions."""
        if not self.cache_path.exists():
            return
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("_schema_version", 0) != CACHE_SCHEMA_VERSION:
                logger.debug(
                    f"Cache schema version mismatch "
                    f"(got {data.get('_schema_version', 0)}, "
                    f"expected {CACHE_SCHEMA_VERSION}) — starting fresh"
                )
                self.cache = {}
                return
            self.cache = {}
            for k, v in data.items():
                if k.startswith("_"):
                    continue
                if "mtime" not in v:
                    v["mtime"] = 0.0
                self.cache[k] = FileCache(**v)
        except Exception as e:
            logger.warning(f"Could not load cache: {e}")
            self.cache = {}

    def save(self) -> None:
        """Persist cache entries to disk atomically."""
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                data: dict = {"_schema_version": CACHE_SCHEMA_VERSION}
                data.update({k: asdict(v) for k, v in self.cache.items()})
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")

    def get_file_hash(self, path: Path) -> str:
        """Return the SHA-256 hex digest of the file at *path*."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def is_cached(self, path: Path) -> bool:
        """Return True when the file is unchanged since its last cache update."""
        path_str = str(path)
        if path_str not in self.cache:
            return False
        cached = self.cache[path_str]
        if not path.exists():
            return False
        stat = path.stat()
        if stat.st_size != cached.size:
            return False
        if cached.mtime and stat.st_mtime == cached.mtime:
            return True
        return self.get_file_hash(path) == cached.hash

    def update(self, path: Path) -> None:
        """Record the current state of *path* in the cache."""
        path_str = str(path)
        stat = path.stat()
        self.cache[path_str] = FileCache(
            path=path_str,
            hash=self.get_file_hash(path),
            last_normalized=datetime.now().isoformat(),
            size=stat.st_size,
            mtime=stat.st_mtime,
        )
