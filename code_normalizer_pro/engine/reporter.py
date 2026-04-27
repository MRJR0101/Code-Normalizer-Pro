"""Reporter module: ProcessStats dataclass and report-generation functions.

The standalone ``print_summary`` and ``generate_reports`` functions accept stats
and error data as plain arguments so they can be called from anywhere without
requiring a full CodeNormalizer instance.  CodeNormalizer delegates to these
functions from its own same-named methods.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger


@dataclass
class ProcessStats:
    """Statistics for a single processing session."""

    total_files: int = 0
    processed: int = 0
    skipped: int = 0
    cached: int = 0
    errors: int = 0
    encoding_changes: int = 0
    newline_fixes: int = 0
    whitespace_fixes: int = 0
    syntax_checks_passed: int = 0
    syntax_checks_failed: int = 0
    bytes_removed: int = 0


def print_summary(
    stats: ProcessStats,
    errors: List[Tuple[Path, str]],
    use_cache: bool = True,
) -> None:
    """Print a human-readable processing summary via loguru."""
    logger.info("\n" + "=" * 70)
    logger.info("PROCESSING SUMMARY")
    logger.info("=" * 70)
    logger.info(f"  Total files: {stats.total_files}")
    logger.info(f"  [+] Processed: {stats.processed}")
    logger.info(f"  [S] Skipped: {stats.skipped}")
    if use_cache:
        logger.info(f"  [C] Cached hits: {stats.cached}")
    logger.info(f"  [X] Errors: {stats.errors}")
    logger.info("")
    logger.info(f"  Encoding changes: {stats.encoding_changes}")
    logger.info(f"  Newline fixes: {stats.newline_fixes}")
    logger.info(f"  Whitespace fixes: {stats.whitespace_fixes}")
    logger.info(f"  Bytes removed: {stats.bytes_removed:,}")

    if stats.syntax_checks_passed > 0 or stats.syntax_checks_failed > 0:
        logger.info("")
        logger.info(f"  Syntax checks passed: {stats.syntax_checks_passed}")
        logger.info(f"  Syntax checks failed: {stats.syntax_checks_failed}")

    if errors:
        logger.error("\n[X] ERRORS:")
        for path, error in errors[:10]:
            logger.error(f"  {path.name}: {error}")
        if len(errors) > 10:
            logger.error(f"  ... and {len(errors) - 10} more")

    logger.info("=" * 70)


def generate_reports(
    stats: ProcessStats,
    errors: List[Tuple[Path, str]],
    report_json: Optional[Path] = None,
    report_html: Optional[Path] = None,
) -> None:
    """Write JSON and/or HTML reports when the corresponding paths are provided."""
    if not report_json and not report_html:
        return

    stats_dict = asdict(stats)
    stats_dict["error_details"] = [
        {"file": str(p), "error": err} for p, err in errors
    ]

    if report_json:
        try:
            with open(report_json, "w", encoding="utf-8") as f:
                json.dump(stats_dict, f, indent=2)
            logger.success(f"[OK] JSON report saved to {report_json}")
        except Exception as e:
            logger.error(f"[X] Could not save JSON report: {e}")

    if report_html:
        try:
            rows = "".join(
                f"<tr><td>{k.replace('_', ' ').title()}</td><td>{v}</td></tr>"
                for k, v in asdict(stats).items()
            )
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Code Normalizer Pro Report</title>
    <style>
        body {{ font-family: sans-serif; margin: 2rem; background: #f9f9f9; color: #333; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f0f0f0; }}
        .errors {{ color: #d9534f; margin-top: 2rem; background: #fdf7f7; padding: 1rem; border-radius: 4px; border: 1px solid #d9534f; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Code Normalizer Pro Report</h1>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            {rows}
        </table>
"""
            if errors:
                html += "<div class='errors'><h2>Errors</h2><ul>"
                for path, err in errors:
                    html += f"<li><strong>{path.name}</strong>: {err}</li>"
                html += "</ul></div>"
            html += "</div></body></html>"

            with open(report_html, "w", encoding="utf-8") as f:
                f.write(html)
            logger.success(f"[OK] HTML report saved to {report_html}")
        except Exception as e:
            logger.error(f"[X] Could not save HTML report: {e}")
