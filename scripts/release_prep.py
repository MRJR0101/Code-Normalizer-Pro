#!/usr/bin/env python3
"""Validate repository readiness for an alpha package release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "pyproject.toml",
    "CHANGELOG.md",
    ".github/workflows/ci.yml",
    "docs/launch/path1_execution_tracker.md",
]


def check_repo(root: Path) -> dict:
    missing_files = [rel for rel in REQUIRED_FILES if not (root / rel).exists()]
    dist_dir = root / "dist"
    wheels = sorted(dist_dir.glob("*.whl")) if dist_dir.exists() else []
    sdists = sorted(dist_dir.glob("*.tar.gz")) if dist_dir.exists() else []

    return {
        "missing_files": missing_files,
        "has_wheel": bool(wheels),
        "has_sdist": bool(sdists),
        "wheel_files": [p.name for p in wheels],
        "sdist_files": [p.name for p in sdists],
        "ready_for_alpha_release": (not missing_files and bool(wheels) and bool(sdists)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check alpha release readiness.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root (default: current directory).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/release/release_readiness.json"),
        help="Output JSON report path.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    report = check_repo(root)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0 if report["ready_for_alpha_release"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

