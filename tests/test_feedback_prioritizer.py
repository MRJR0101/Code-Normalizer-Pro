from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_feedback_prioritizer_outputs_top_terms(tmp_path: Path) -> None:
    csv_path = tmp_path / "users.csv"
    csv_path.write_text(
        "\n".join(
            [
                "date,channel,username_or_org,repo_size,status,feedback,follow_up_date,owner",
                "2026-02-12,reddit,a,small,contacted,needs better cache behavior,2026-02-19,MR",
                "2026-02-12,hn,b,small,contacted,needs better docs and cache examples,2026-02-19,MR",
            ]
        ),
        encoding="utf-8",
    )

    out_json = tmp_path / "top.json"
    out_md = tmp_path / "top.md"
    script = Path(__file__).resolve().parents[1] / "scripts" / "feedback_prioritizer.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--csv",
            str(csv_path),
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
            "--top",
            "2",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["feedback_records"] == 2
    assert len(payload["top_pain_points"]) == 2
    assert out_md.exists()

