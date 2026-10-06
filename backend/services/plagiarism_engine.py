"""Backend service adapter between the FastAPI layer and the core engine.

Responsibilities
----------------
* ``prepare_submission``     — tokenise + fingerprint one submission (once).
* ``compare_code_pair``      — compare two raw source strings (convenience,
                               used when a cached SubmissionResult is not
                               available, e.g. the /api/compare POST endpoint).
* ``find_matching_regions``  — map matching token k-grams back to source lines
                               so the frontend can highlight them.  Uses the
                               SAME normalised token representation as
                               similarity; never tokenises individual lines.

The ``find_matching_regions`` function:
  1. Tokenises each file in full (one pass each).
  2. Builds k-grams from the full token stream.
  3. Intersects the fingerprint sets to find matching hashes.
  4. Maps each matching hash back to the source lines using stored token
     positions, so highlights are consistent with the score.
  5. Filters out blank / whitespace-only lines.
"""

from __future__ import annotations

import keyword
import tokenize
from typing import Any

from core import (
    AnalysisService,
    SubmissionResult,
    ast_similarity,
    build_fingerprint,
    containment_similarity,
    jaccard_similarity,
    normalize_code,
)
from core.config import DEFAULT_K, DEFAULT_THRESHOLD, DEFAULT_WINDOW, TOKEN_WEIGHT, AST_WEIGHT, HIGHLIGHT_MATCH_CAP

__all__ = [
    "prepare_submission",
    "compare_code_pair",
    "compare_pair_detail",
    "find_matching_regions",
]

_service = AnalysisService()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def prepare_submission(name: str, source: str) -> SubmissionResult:
    """Tokenise and fingerprint *source* exactly once.  Never raises."""
    return _service.prepare_submission(name, source)


def compare_code_pair(
    left_code: str,
    right_code: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Compare two raw source strings.

    Returns a dict with ``score``, ``jaccard_similarity``,
    ``containment_similarity``, ``ast_similarity``, ``suspicious``,
    ``status_a``, ``status_b``.
    """
    left = _service.prepare_submission("left", left_code)
    right = _service.prepare_submission("right", right_code)
    pair = _service.compare_pair(left, right, threshold=threshold)
    return pair.as_dict()


def compare_pair_detail(
    left: SubmissionResult,
    right: SubmissionResult,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Compare two pre-prepared SubmissionResults (reuses cached fingerprints)."""
    pair = _service.compare_pair(left, right, threshold=threshold)
    return pair.as_dict()


# ---------------------------------------------------------------------------
# Highlighting: token-position based, consistent with fingerprint similarity
# ---------------------------------------------------------------------------

def _tokenize_with_positions(source: str) -> list[dict[str, Any]]:
    """Return a list of token dicts with position metadata.

    Each entry: {type, string, norm, row_start, col_start, row_end, col_end}
    Skips comment / whitespace / structural tokens.
    """
    _SKIP = {
        tokenize.COMMENT,
        tokenize.ENCODING,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
    }

    result: list[dict[str, Any]] = []
    try:
        lines_iter = iter(source.splitlines(keepends=True))

        def _readline() -> str:
            try:
                return next(lines_iter)
            except StopIteration:
                return ""

        stream = tokenize.generate_tokens(_readline)
        for tok in stream:
            if tok.type in _SKIP:
                continue
            if tok.type == tokenize.NAME:
                norm = tok.string if (keyword.iskeyword(tok.string) or keyword.issoftkeyword(tok.string)) else "ID"
            elif tok.type == tokenize.NUMBER:
                norm = "NUM"
            elif tok.type == tokenize.STRING:
                norm = "STR"
            else:
                norm = tok.string

            result.append({
                "type": tok.type,
                "string": tok.string,
                "norm": norm,
                "row_start": tok.start[0] - 1,  # 0-indexed line
                "col_start": tok.start[1],
                "row_end": tok.end[0] - 1,
                "col_end": tok.end[1],
            })
    except tokenize.TokenError:
        pass  # return whatever we collected so far

    return result


def find_matching_regions(left_code: str, right_code: str) -> dict[str, Any]:
    """Return highlighted regions consistent with fingerprint-based similarity.

    Algorithm
    ---------
    1. Tokenise both files in full (one pass each) with position metadata.
    2. Build k-gram hashes for the full token stream (same as fingerprinting).
    3. Find the intersection of hashes (matching k-grams).
    4. Map each matching k-gram back to its source lines via position metadata.
    5. Collect the distinct line numbers that contain a matched k-gram token.
    6. Filter out lines that are blank or whitespace-only in the original source.

    The highlighted lines are therefore directly derived from the same
    fingerprint hashes used in the similarity score — no separate line-diff
    algorithm.
    """
    import hashlib

    k = DEFAULT_K
    left_lines = left_code.splitlines()
    right_lines = right_code.splitlines()

    left_toks = _tokenize_with_positions(left_code)
    right_toks = _tokenize_with_positions(right_code)

    def _build_gram_hash_map(toks: list[dict[str, Any]]) -> dict[int, list[int]]:
        """Return {hash: [token_start_index, ...]} for all k-grams."""
        norms = [t["norm"] for t in toks]
        gram_to_positions: dict[int, list[int]] = {}
        for i in range(len(norms) - k + 1):
            gram = norms[i : i + k]
            payload = "|".join(gram).encode("utf-8")
            h = int.from_bytes(hashlib.sha1(payload).digest()[:8], "big", signed=False)
            gram_to_positions.setdefault(h, []).append(i)
        return gram_to_positions

    left_map = _build_gram_hash_map(left_toks)
    right_map = _build_gram_hash_map(right_toks)

    shared_hashes = set(left_map.keys()) & set(right_map.keys())

    # Collect matched line numbers from token positions
    left_matched_lines: set[int] = set()
    right_matched_lines: set[int] = set()

    for h in shared_hashes:
        for pos in left_map[h]:
            for tok in left_toks[pos : pos + k]:
                left_matched_lines.add(tok["row_start"])
        for pos in right_map[h]:
            for tok in right_toks[pos : pos + k]:
                right_matched_lines.add(tok["row_start"])

    # Filter blank lines
    def _is_meaningful(lines: list[str], idx: int) -> bool:
        if idx < 0 or idx >= len(lines):
            return False
        return bool(lines[idx].strip())

    left_matched_lines = {i for i in left_matched_lines if _is_meaningful(left_lines, i)}
    right_matched_lines = {i for i in right_matched_lines if _is_meaningful(right_lines, i)}

    # Build matches list for frontend (pair left↔right by insertion order,
    # capped at 50 to keep payload reasonable)
    left_sorted = sorted(left_matched_lines)
    right_sorted = sorted(right_matched_lines)
    matches: list[dict[str, int]] = []
    for i, (l, r) in enumerate(zip(left_sorted, right_sorted)):
        if i >= HIGHLIGHT_MATCH_CAP:
            break
        matches.append({"left": l, "right": r})

    return {
        "left_lines": left_lines,
        "right_lines": right_lines,
        "left_matched_lines": left_sorted,
        "right_matched_lines": right_sorted,
        "matches": matches,
    }
