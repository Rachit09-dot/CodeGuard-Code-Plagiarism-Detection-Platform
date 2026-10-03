from __future__ import annotations

from typing import Any

from core import build_fingerprint, jaccard_similarity, normalize_code


def compare_code_pair(left_code: str, right_code: str) -> float:
    left_tokens = normalize_code(left_code)
    right_tokens = normalize_code(right_code)
    left_fp = build_fingerprint(left_tokens)
    right_fp = build_fingerprint(right_tokens)
    return jaccard_similarity(left_fp, right_fp)


def analyze_submission_files(files: list[tuple[str, str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for i, (left_name, left_code) in enumerate(files):
        for j in range(i + 1, len(files)):
            right_name, right_code = files[j]
            score = compare_code_pair(left_code, right_code)
            results.append({
                "file_a": left_name,
                "file_b": right_name,
                "score": round(score, 4),
                "suspicious": score >= 0.5,
            })

    results.sort(key=lambda item: (item["score"], item["file_a"], item["file_b"]), reverse=True)
    return results


def find_matching_regions(left_code: str, right_code: str) -> dict[str, Any]:
    left_lines = left_code.splitlines()
    right_lines = right_code.splitlines()

    left_map: dict[str, list[int]] = {}
    right_map: dict[str, list[int]] = {}

    for idx, line in enumerate(left_lines):
        key = " ".join(normalize_code(line))
        left_map.setdefault(key, []).append(idx)

    for idx, line in enumerate(right_lines):
        key = " ".join(normalize_code(line))
        right_map.setdefault(key, []).append(idx)

    matches: list[dict[str, int]] = []
    for key, left_indices in left_map.items():
        if key not in right_map:
            continue
        for left_idx in left_indices:
            for right_idx in right_map[key]:
                matches.append({"left": left_idx, "right": right_idx})

    return {
        "left_lines": left_lines,
        "right_lines": right_lines,
        "matches": matches[:20],
    }
