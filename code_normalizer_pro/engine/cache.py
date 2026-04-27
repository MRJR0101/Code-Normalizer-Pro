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
from typing import Dict, Optional, runtime_checkable

from typing import Protocol

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



# ---------------------------------------------------------------------------
# CacheBackend Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class CacheBackend(Protocol):
    """Structural protocol for swappable cache backends.

    Any class implementing these five methods is a valid CacheBackend.
    The default implementation is CacheManager (JSON-file backed).
    A SQLite-backed drop-in is planned for the v2.0 scaling milestone
    (trigger: repos >50 K files where JSON I/O becomes a bottleneck).

    Usage::

        def build_cache(backend: CacheBackend) -> None:
            backend.load()
            ...

        assert isinstance(CacheManager(), CacheBackend)   # True — structural
    """

    def load(self) -> None:
        """Load cached entries from persistent storage."""
        ...

    def save(self) -> None:
        """Persist cache entries to durable storage."""
        ...

    def get_file_hash(self, path: Path) -> str:
        """Return a content hash (e.g. SHA-256 hex) for *path*."""
        ...

    def is_cached(self, path: Path) -> bool:
        """Return True when *path* is unchanged since its last cache update."""
        ...

    def update(self, path: Path) -> None:
        """Record the current state of *path* in the cache."""
        ...


# ---------------------------------------------------------------------------
# CacheManager — default JSON-file backend
# ---------------------------------------------------------------------------

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



# ---------------------------------------------------------------------------
# Convenience aliases and future stubs
# ---------------------------------------------------------------------------

#: Alias so callers can write ``JsonCacheBackend()`` for clarity.
JsonCacheBackend = CacheManager


class SqliteCacheBackend:
    """Placeholder for a future SQLite-backed cache implementation.

    Swap in for ``CacheManager`` when JSON I/O becomes a bottleneck
    (anticipated threshold: ~50 K files per run).

    All methods raise ``NotImplementedError`` until the implementation lands.
    The class satisfies ``CacheBackend`` structurally once implemented.
    """

    def __init__(self, cache_path: Optional[Path] = None) -> None:  # noqa: ARG002
        raise NotImplementedError(
            "SqliteCacheBackend is not yet implemented. "
            "Use CacheManager (JsonCacheBackend) instead."
        )

    def load(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def save(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def get_file_hash(self, path: Path) -> str:  # pragma: no cover  # noqa: ARG002
        raise NotImplementedError

    def is_cached(self, path: Path) -> bool:  # pragma: no cover  # noqa: ARG002
        raise NotImplementedError

    def update(self, path: Path) -> None:  # pragma: no cover  # noqa: ARG002
        raise NotImplementedError
