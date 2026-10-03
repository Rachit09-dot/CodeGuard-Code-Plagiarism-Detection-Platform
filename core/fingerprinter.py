import hashlib

K = 5
W = 12


def build_fingerprint(tokens: list[str], k: int = K, window: int = W) -> set[int]:
    """Create a compact fingerprint using k-gram hashing and winnowing."""
    if len(tokens) < k or not tokens:
        return set()

    kgrams = [tuple(tokens[i : i + k]) for i in range(len(tokens) - k + 1)]
    gram_hashes = []

    for gram in kgrams:
        payload = "|".join(gram).encode("utf-8")
        digest = hashlib.sha1(payload).digest()
        gram_hashes.append(int.from_bytes(digest[:8], byteorder="big", signed=False))

    if len(gram_hashes) <= window:
        return {min(gram_hashes)}

    selected: set[int] = set()
    for start in range(len(gram_hashes) - window + 1):
        window_hashes = gram_hashes[start : start + window]
        selected.add(min(window_hashes))

    return selected
