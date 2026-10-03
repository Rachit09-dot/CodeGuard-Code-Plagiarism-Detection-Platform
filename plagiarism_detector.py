#!/usr/bin/env python3
"""CLI entry point for the code plagiarism platform."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.analysis_service import AnalysisService


def print_report(results: list[tuple[float, str, str]], threshold: float) -> None:
    flagged = 0
    print(f"{'Score':>6}   {'File A':<20}  <->  {'File B':<20}")

    for score, left, right in results:
        is_suspicious = score >= threshold
        if is_suspicious:
            flagged += 1
        status = "[SUSPICIOUS]" if is_suspicious else ""
        print(f"{score:>5.2f}    {left:<20}  <->  {right:<20}   {status}")

    print(f"\nChecked {len(results)} pairs, flagged {flagged} (threshold={threshold})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect suspicious code similarities using token normalization and winnowing."
    )
    parser.add_argument("folder", help="Folder containing .py submissions")
    parser.add_argument(
        "threshold",
        nargs="?",
        type=float,
        default=0.5,
        help="Similarity threshold in the range 0 to 1 (default: 0.5)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    folder = Path(args.folder)

    if not folder.exists() or not folder.is_dir():
        print(f"Error: folder '{folder}' does not exist or is not a directory.", file=sys.stderr)
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

    print_report(results, args.threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
