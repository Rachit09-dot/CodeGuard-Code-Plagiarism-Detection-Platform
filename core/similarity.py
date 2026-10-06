"""Similarity metrics for fingerprint sets.

Metrics
-------
jaccard_similarity
    |A ∩ B| / |A ∪ B|.  Returns 0.0 when either set is empty (not 1.0 —
    two empty fingerprints carry *no* information and must never be
    classified as plagiarism).

containment_similarity
    |A ∩ B| / min(|A|, |B|).  Detects the case where a small submission is
    entirely contained inside a larger one; Jaccard alone would undercount
    that scenario.

Both functions accept ``set[int]`` (winnowed hash sets) as produced by
``build_fingerprint``.  An empty set means the source had insufficient
content to generate fingerprints; callers should treat this as
``insufficient_content`` rather than running similarity metrics.

All return values are clamped to [0.0, 1.0] to guard against floating-point
edge cases when fingerprint sets are constructed from external data.
"""

from __future__ import annotations

__all__ = ["jaccard_similarity", "containment_similarity", "clamp"]

# Minimum fingerprint size below which comparison is meaningless.
MIN_FINGERPRINT_SIZE = 1


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Return *value* clamped to the closed interval [*lo*, *hi*]."""
    return max(lo, min(hi, value))


def jaccard_similarity(a: set[int], b: set[int]) -> float:
    """Return Jaccard similarity between two fingerprint sets.

    Returns 0.0 if *either* set is empty — two empty fingerprints must not
    be reported as 1.0 similar.

    Result is clamped to [0.0, 1.0].
    """
    if not a or not b:
        return 0.0

    intersection = len(a & b)
    union = len(a | b)
    return clamp(intersection / union)


def containment_similarity(a: set[int], b: set[int]) -> float:
    """Return containment of the *smaller* set inside the *larger* set.

    containment = |A ∩ B| / min(|A|, |B|)

    This metric is high when one submission is essentially a subset of the
    other, even if Jaccard is moderate (because the larger set adds many
    unique hashes that inflate the union).

    Returns 0.0 if either set is empty.
    Result is clamped to [0.0, 1.0].
    """
    if not a or not b:
        return 0.0

    intersection = len(a & b)
    smaller = min(len(a), len(b))
    return clamp(intersection / smaller)
