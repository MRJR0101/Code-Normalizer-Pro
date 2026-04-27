#!/usr/bin/env python3
"""Summarize Path 1 launch-tracker metrics from CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


VALID_STATUSES = {
    "contacted",
    "replied",
    "interested",
    "active",
    "paying",
    "churned",
}


def summarize(csv_path: Path) -> dict:
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(row)

    by_status = {status: 0 for status in sorted(VALID_STATUSES)}
    by_channel: dict[str, int] = {}

    for row in rows:
        status = (row.get("status") or "").strip().lower()
        channel = (row.get("channel") or "").strip().lower() or "unknown"
        by_channel[channel] = by_channel.get(channel, 0) + 1
        if status in by_status:
            by_status[status] += 1

    total = len(rows)
    paying = by_status["paying"]
    conversion = (paying / total * 100.0) if total else 0.0

    return {
        "total_records": total,
        "status_breakdown": by_status,
        "channel_breakdown": dict(sorted(by_channel.items())),
        "paying_conversion_percent": round(conversion, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Path 1 launch CSV metrics.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("docs/launch/first_100_users.csv"),
        help="Path to launch tracker CSV.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/launch/metrics_summary.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Error: CSV not found: {args.csv}")
        return 1

    summary = summarize(args.csv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote metrics summary to {args.out}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

