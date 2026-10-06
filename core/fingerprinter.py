"""Fingerprint builder using k-gram hashing + winnowing.

The entire source file is tokenised exactly *once* by ``normalize_code``
before this module is called.  This module only receives the resulting
normalised token list; it never tokenises physical lines individually.

Constants
---------
DEFAULT_K
    k-gram size (number of consecutive tokens per gram).
DEFAULT_WINDOW
    Winnowing window size.

Both values are sourced from ``core.config`` so they can be overridden
via environment variables without touching source code.
"""

from __future__ import annotations

import hashlib

from .config import DEFAULT_K, DEFAULT_WINDOW

__all__ = ["build_fingerprint", "DEFAULT_K", "DEFAULT_WINDOW"]


def build_fingerprint(
    tokens: list[str],
    k: int = DEFAULT_K,
    window: int = DEFAULT_WINDOW,
) -> set[int]:
    """Return a compact Winnowing fingerprint for *tokens*.

    Returns an *empty set* when the token list is too short to produce a
    k-gram, so callers can detect ``insufficient_content`` rather than
    comparing empty sets (which would incorrectly yield similarity 1.0 under
    naive Jaccard).

    Algorithm
    ---------
    1. Slide a window of width *k* over the token list to build k-grams.
    2. Hash each k-gram with SHA-1 (first 8 bytes → uint64).
    3. Apply Winnowing: for each window of *window* consecutive hashes,
       select the minimum hash.  The union of selected hashes is the
       fingerprint.
    """
    if len(tokens) < k:
        # Insufficient content — return empty set deliberately.
        return set()

    # Step 1: build k-gram hashes
    gram_hashes: list[int] = []
    for i in range(len(tokens) - k + 1):
        gram = tokens[i : i + k]
        payload = "|".join(gram).encode("utf-8")
        digest = hashlib.sha1(payload).digest()
        gram_hashes.append(int.from_bytes(digest[:8], byteorder="big", signed=False))

    # Step 2: winnowing
    if len(gram_hashes) <= window:
        # Fewer hashes than the window → keep the single minimum
        return {min(gram_hashes)}

    selected: set[int] = set()
    for start in range(len(gram_hashes) - window + 1):
        selected.add(min(gram_hashes[start : start + window]))

    return selected
