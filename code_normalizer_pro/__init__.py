"""code-normalizer-pro package."""

from __future__ import annotations

from code_normalizer_pro.engine.normalizer import CodeNormalizer
from code_normalizer_pro.engine.reporter import ProcessStats

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("code-normalizer-pro")
except Exception:
    __version__ = "3.2.0"

__all__ = ["CodeNormalizer", "ProcessStats", "__version__"]
