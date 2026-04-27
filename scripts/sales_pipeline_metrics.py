#!/usr/bin/env python3
"""Summarize Path 1 sales pipeline metrics."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def summarize(csv_path: Path) -> dict:
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    paying = [r for r in rows if (r.get("status") or "").strip().lower() == "paying"]
    active = [r for r in rows if (r.get("status") or "").strip().lower() in {"pilot", "active", "paying"}]

    mrr = 0.0
    for row in paying:
        try:
            mrr += float((row.get("monthly_value_usd") or "0").strip() or 0)
        except ValueError:
            pass

    return {
        "total_leads": len(rows),
        "active_or_better": len(active),
        "paying_customers": len(paying),
        "estimated_mrr_usd": round(mrr, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize sales pipeline CSV.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("docs/sales/pipeline.csv"),
        help="Sales pipeline CSV.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/sales/pipeline_metrics.json"),
        help="Output metrics JSON path.",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Error: sales CSV not found: {args.csv}")
        return 1

    payload = summarize(args.csv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

