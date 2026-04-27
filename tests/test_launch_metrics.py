from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_launch_metrics_summary_and_cli(tmp_path: Path) -> None:
    csv_path = tmp_path / "first_100_users.csv"
    csv_path.write_text(
        "\n".join(
            [
                "date,channel,username_or_org,repo_size,status,feedback,follow_up_date,owner",
                "2026-02-12,reddit,user1,small,contacted,none,2026-02-19,MR",
                "2026-02-12,hn,user2,medium,paying,good,2026-02-19,MR",
                "2026-02-12,reddit,user3,small,interested,nice,2026-02-19,MR",
            ]
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "summary.json"
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "launch_metrics.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--csv", str(csv_path), "--out", str(out_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert out_path.exists()

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["total_records"] == 3
    assert payload["status_breakdown"]["paying"] == 1
    assert payload["status_breakdown"]["interested"] == 1
    assert payload["channel_breakdown"]["reddit"] == 2
    assert payload["paying_conversion_percent"] == 33.33

