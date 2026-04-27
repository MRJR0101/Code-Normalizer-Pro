from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_release_prep_reports_ready_with_required_files(tmp_path: Path) -> None:
    for rel in [
        "README.md",
        "LICENSE",
        "pyproject.toml",
        "CHANGELOG.md",
        ".github/workflows/ci.yml",
        "docs/launch/path1_execution_tracker.md",
    ]:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "pkg-0.1.0-py3-none-any.whl").write_text("x", encoding="utf-8")
    (dist / "pkg-0.1.0.tar.gz").write_text("x", encoding="utf-8")

    script = Path(__file__).resolve().parents[1] / "scripts" / "release_prep.py"
    out = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), "--out", str(out)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ready_for_alpha_release"] is True
    assert payload["missing_files"] == []

