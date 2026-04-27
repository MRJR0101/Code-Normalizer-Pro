#!/usr/bin/env python3
"""Generate top pain points from user feedback entries."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "have",
    "will",
    "your",
    "into",
    "just",
    "need",
    "wants",
    "want",
    "none",
    "good",
    "nice",
}


def extract_tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
    return [w for w in words if w not in STOP_WORDS]


def summarize_feedback(csv_path: Path, top_n: int = 3) -> dict:
    counter: Counter[str] = Counter()
    records = 0

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            feedback = (row.get("feedback") or "").strip()
            if feedback:
                records += 1
                counter.update(extract_tokens(feedback))

    top_terms = counter.most_common(top_n)
    return {
        "feedback_records": records,
        "top_pain_points": [{"term": term, "count": count} for term, count in top_terms],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prioritize top pain points from launch feedback.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("docs/launch/first_100_users.csv"),
        help="Feedback CSV path.",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("docs/launch/top_pain_points.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=Path("docs/launch/top_pain_points.md"),
        help="Output markdown summary path.",
    )
    parser.add_argument("--top", type=int, default=3, help="Number of top pain points.")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Error: feedback CSV not found: {args.csv}")
        return 1

    summary = summarize_feedback(args.csv, top_n=max(1, args.top))
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = ["# Top Pain Points", ""]
    lines.append(f"Feedback records analyzed: {summary['feedback_records']}")
    lines.append("")
    if summary["top_pain_points"]:
        for i, item in enumerate(summary["top_pain_points"], start=1):
            lines.append(f"{i}. {item['term']} ({item['count']})")
    else:
        lines.append("No feedback terms found yet.")
    lines.append("")
    args.out_md.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

