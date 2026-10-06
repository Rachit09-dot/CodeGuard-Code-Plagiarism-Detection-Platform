#!/usr/bin/env python3
"""CLI entry point for the code plagiarism platform.

Usage
-----
    python plagiarism_detector.py <folder> [threshold] [--json]

Arguments
---------
folder
    Directory containing .py submission files.
threshold
    Similarity threshold in the range 0–1 (default: 0.5).  Pairs at or
    above this value are flagged as suspicious.

Options
-------
--json
    Print results as a JSON array instead of the human-readable table.

Examples
--------
    python plagiarism_detector.py submissions/
    python plagiarism_detector.py submissions/ 0.6
    python plagiarism_detector.py submissions/ 0.6 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.analysis_service import AnalysisService
from core.config import DEFAULT_THRESHOLD


def print_table(results: list[tuple[float, str, str]], threshold: float) -> None:
    flagged = 0
    print(f"{'Score':>6}   {'File A':<25}  <->  {'File B':<25}   Status")
    print("-" * 75)
    for score, left, right in results:
        is_suspicious = score >= threshold
        if is_suspicious:
            flagged += 1
        status = "[SUSPICIOUS]" if is_suspicious else ""
        print(f"{score:>5.2f}    {left:<25}  <->  {right:<25}   {status}")
    print(f"\nChecked {len(results)} pair(s) · {flagged} flagged  (threshold={threshold})")


def print_json(results: list[tuple[float, str, str]], threshold: float) -> None:
    output = [
        {
            "score": round(score, 4),
            "file_a": left,
            "file_b": right,
            "suspicious": score >= threshold,
        }
        for score, left, right in results
    ]
    print(json.dumps(output, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect suspicious code similarities using token normalisation and winnowing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("folder", help="Folder containing .py submissions.")
    parser.add_argument(
        "threshold",
        nargs="?",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Similarity threshold 0–1 (default: {DEFAULT_THRESHOLD}).",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output results as a JSON array.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    folder = Path(args.folder)

    if not folder.exists() or not folder.is_dir():
        print(
            f"Error: folder '{folder}' does not exist or is not a directory.",
            file=sys.stderr,
        )
        return 1

    if not 0.0 <= args.threshold <= 1.0:
        print("Error: threshold must be between 0 and 1.", file=sys.stderr)
        return 1

    try:
        service = AnalysisService()
        results = service.analyze_folder(folder, threshold=args.threshold)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print_json(results, args.threshold)
    else:
        print_table(results, args.threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
