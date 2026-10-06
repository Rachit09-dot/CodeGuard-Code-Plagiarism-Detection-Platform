"""Unit tests for similarity metrics.

Verifies:
* Jaccard: empty sets → 0.0 (not 1.0).
* Jaccard: identical sets → 1.0.
* Jaccard: disjoint sets → 0.0.
* Containment: small subset fully inside large set → 1.0.
* Containment: empty sets → 0.0.
* End-to-end similarity tests on real Python source.
"""

import pytest
from core.similarity import containment_similarity, jaccard_similarity
from core.normalizer import normalize_code
from core.fingerprinter import build_fingerprint


class TestJaccardSimilarity:
    def test_empty_and_empty_returns_zero(self):
        """Two empty fingerprints must NOT return 1.0."""
        assert jaccard_similarity(set(), set()) == 0.0

    def test_empty_and_nonempty_returns_zero(self):
        assert jaccard_similarity(set(), {1, 2, 3}) == 0.0

    def test_nonempty_and_empty_returns_zero(self):
        assert jaccard_similarity({1, 2, 3}, set()) == 0.0

    def test_identical_sets_returns_one(self):
        s = {1, 2, 3, 4, 5}
        assert jaccard_similarity(s, s) == 1.0

    def test_disjoint_sets_returns_zero(self):
        assert jaccard_similarity({1, 2, 3}, {4, 5, 6}) == 0.0

    def test_partial_overlap(self):
        a = {1, 2, 3, 4}
        b = {3, 4, 5, 6}
        # intersection = {3,4}, union = {1,2,3,4,5,6}
        assert jaccard_similarity(a, b) == pytest.approx(2 / 6)

    def test_symmetric(self):
        a = {1, 2, 3}
        b = {2, 3, 4}
        assert jaccard_similarity(a, b) == jaccard_similarity(b, a)


class TestContainmentSimilarity:
    def test_empty_and_empty_returns_zero(self):
        assert containment_similarity(set(), set()) == 0.0

    def test_subset_fully_contained(self):
        small = {1, 2, 3}
        large = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
        # intersection = 3, min size = 3 → 1.0
        assert containment_similarity(small, large) == pytest.approx(1.0)

    def test_disjoint_returns_zero(self):
        assert containment_similarity({1, 2}, {3, 4}) == 0.0

    def test_identical_returns_one(self):
        s = {1, 2, 3}
        assert containment_similarity(s, s) == pytest.approx(1.0)

    def test_symmetric_in_small_set(self):
        """Containment is NOT symmetric by definition but should behave consistently."""
        small = {1, 2}
        large = {1, 2, 3, 4}
        c_small_in_large = containment_similarity(small, large)
        c_large_in_small = containment_similarity(large, small)
        # Both use min(len(a), len(b)) = 2
        assert c_small_in_large == c_large_in_small


class TestEndToEndSimilarity:
    """Integration: normalise → fingerprint → similarity on real Python code."""

    def _fp(self, source: str):
        tokens = normalize_code(source)
        return build_fingerprint(tokens)

    def test_identical_source_high_jaccard(self):
        src = "def f(x):\n    return x * 2"
        assert jaccard_similarity(self._fp(src), self._fp(src)) == pytest.approx(1.0)

    def test_renamed_identifiers_high_jaccard(self):
        src_a = "def total(nums):\n    s = 0\n    for v in nums:\n        if v > 0:\n            s += v\n    return s"
        src_b = "def compute(items):\n    acc = 0\n    for item in items:\n        if item > 0:\n            acc += item\n    return acc"
        score = jaccard_similarity(self._fp(src_a), self._fp(src_b))
        assert score >= 0.9, f"Expected >= 0.9, got {score}"

    def test_unrelated_programs_low_jaccard(self):
        src_a = "def sort_list(lst):\n    return sorted(lst)"
        src_b = "import os\ndef get_env(key):\n    return os.getenv(key, '')"
        score = jaccard_similarity(self._fp(src_a), self._fp(src_b))
        assert score < 0.5, f"Expected < 0.5, got {score}"

    def test_different_control_flow_lower_score(self):
        """Changing for→if should produce noticeably different score."""
        src_for = "for x in data:\n    print(x)"
        src_if  = "if x in data:\n    print(x)"
        score = jaccard_similarity(self._fp(src_for), self._fp(src_if))
        # Not identical since keywords differ
        assert score < 1.0

    def test_empty_source_never_flags_plagiarism(self):
        fp_empty = self._fp("")
        fp_real  = self._fp("def f(x):\n    return x")
        assert jaccard_similarity(fp_empty, fp_real) == 0.0
        assert jaccard_similarity(fp_empty, fp_empty) == 0.0

    def test_containment_detects_subset(self):
        """A longer program that contains a shorter one should have high containment."""
        src_short = (
            "def f(x):\n"
            "    for i in range(x):\n"
            "        if i > 0:\n"
            "            print(i)\n"
            "    return x\n"
        )
        src_long = (
            src_short
            + "\ndef g(y):\n    for j in range(y):\n        if j > 0:\n            print(j)\n    return y\n"
            + "\ndef h(z):\n    for k in range(z):\n        if k > 0:\n            print(k)\n    return z\n"
        )
        c = containment_similarity(self._fp(src_short), self._fp(src_long))
        # The short program's fingerprints should be largely contained in the longer one
        assert c >= 0.5, f"Expected containment >= 0.5, got {c}"
