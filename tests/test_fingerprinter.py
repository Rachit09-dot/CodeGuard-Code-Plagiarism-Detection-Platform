"""Unit tests for the fingerprinter (k-gram hashing + winnowing).

Verifies:
* Identical token streams produce identical fingerprints.
* Fingerprints are sets of ints.
* Token streams shorter than k return empty set.
* Empty token stream returns empty set.
* Fingerprint is deterministic.
"""

import pytest
from core.fingerprinter import build_fingerprint
from core.normalizer import normalize_code


class TestBuildFingerprint:
    def test_identical_tokens_identical_fingerprint(self):
        tokens = ["for", "ID", "in", "ID", ":", "ID", "(", "ID", ")"]
        fp1 = build_fingerprint(tokens)
        fp2 = build_fingerprint(tokens)
        assert fp1 == fp2

    def test_returns_set_of_ints(self):
        tokens = ["for", "ID", "in", "ID", ":", "ID", "(", "ID", ")"]
        fp = build_fingerprint(tokens)
        assert isinstance(fp, set)
        for item in fp:
            assert isinstance(item, int)

    def test_empty_tokens_returns_empty_set(self):
        assert build_fingerprint([]) == set()

    def test_tokens_shorter_than_k_returns_empty_set(self):
        assert build_fingerprint(["a", "b"], k=5) == set()

    def test_deterministic(self):
        tokens = ["if", "ID", ":", "return", "NUM"]
        fp1 = build_fingerprint(tokens)
        fp2 = build_fingerprint(tokens)
        assert fp1 == fp2

    def test_different_tokens_different_fingerprint(self):
        tokens_a = ["for", "ID", "in", "ID", ":", "pass"]
        tokens_b = ["if", "ID", ":", "return", "NUM"]
        fp_a = build_fingerprint(tokens_a)
        fp_b = build_fingerprint(tokens_b)
        assert fp_a != fp_b

    def test_real_source_produces_nonempty_fingerprint(self):
        source = "\n".join([
            "def total(nums):",
            "    s = 0",
            "    for v in nums:",
            "        if v > 0:",
            "            s += v",
            "    return s",
        ])
        tokens = normalize_code(source)
        fp = build_fingerprint(tokens)
        assert len(fp) > 0

    def test_renamed_identifiers_same_fingerprint(self):
        """After normalisation, renaming identifiers should not change the fingerprint."""
        src_a = "def total(nums):\n    s = 0\n    for v in nums:\n        s += v\n    return s"
        src_b = "def compute(items):\n    acc = 0\n    for item in items:\n        acc += item\n    return acc"
        tokens_a = normalize_code(src_a)
        tokens_b = normalize_code(src_b)
        fp_a = build_fingerprint(tokens_a)
        fp_b = build_fingerprint(tokens_b)
        # They should be identical because identifiers all normalise to ID
        assert fp_a == fp_b
