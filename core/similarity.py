def jaccard_similarity(a: set[int], b: set[int]) -> float:
    """Compute Jaccard similarity between two fingerprint sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    union = a | b
    intersection = a & b
    return len(intersection) / len(union)
