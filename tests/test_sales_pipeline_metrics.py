from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_sales_pipeline_metrics_reports_mrr(tmp_path: Path) -> None:
    csv_path = tmp_path / "pipeline.csv"
    csv_path.write_text(
        "\n".join(
            [
                "date,lead,channel,status,monthly_value_usd,next_action,next_action_date,notes",
                "2026-02-12,a,reddit,contacted,0,followup,2026-02-19,none",
                "2026-02-12,b,hn,pilot,299,onboarding,2026-02-19,none",
                "2026-02-12,c,devto,paying,49,retain,2026-02-19,none",
            ]
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "metrics.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "sales_pipeline_metrics.py"
    result = subprocess.run(
        [sys.executable, str(script), "--csv", str(csv_path), "--out", str(out_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["total_leads"] == 3
    assert payload["active_or_better"] == 2
    assert payload["paying_customers"] == 1
    assert payload["estimated_mrr_usd"] == 49.0

