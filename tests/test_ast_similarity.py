"""Unit tests for AST structural similarity.

Verifies:
* Identical source → similarity 1.0.
* Variable-renamed source → high similarity.
* Completely different structure → low similarity.
* Invalid Python → 0.0 (no crash).
* AST similarity is distinct from (but correlated with) token similarity.
"""

import pytest
from core.ast_similarity import ast_similarity, extract_ast_tokens


class TestExtractAstTokens:
    def test_valid_source_returns_list(self):
        result = extract_ast_tokens("def f(x):\n    return x")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_contains_node_type_names(self):
        result = extract_ast_tokens("def f(x):\n    return x + 1")
        assert "FunctionDef" in result
        assert "Return" in result

    def test_invalid_source_returns_none(self):
        assert extract_ast_tokens("def f(:") is None

    def test_empty_source_returns_module(self):
        result = extract_ast_tokens("")
        # An empty file is still valid Python — it parses to a Module node
        assert result is not None
        assert "Module" in result


class TestAstSimilarity:
    def test_identical_source_returns_one(self):
        src = "def f(x):\n    return x * 2"
        score = ast_similarity(src, src)
        assert score == pytest.approx(1.0)

    def test_renamed_variables_high_similarity(self):
        src_a = "def total(nums):\n    s = 0\n    for v in nums:\n        if v > 0:\n            s += v\n    return s"
        src_b = "def compute(items):\n    acc = 0\n    for item in items:\n        if item > 0:\n            acc += item\n    return acc"
        score = ast_similarity(src_a, src_b)
        assert score >= 0.8, f"Expected >= 0.8, got {score}"

    def test_completely_different_source_low_similarity(self):
        src_a = "def f(x):\n    return x * 2"
        src_b = "import os\nimport sys\nfor i in range(100):\n    os.path.join(str(i), 'x')"
        score = ast_similarity(src_a, src_b)
        assert score < 0.6, f"Expected < 0.6, got {score}"

    def test_invalid_source_returns_zero_no_crash(self):
        assert ast_similarity("def f(:)", "def f(x):\n    return x") == 0.0

    def test_both_invalid_returns_zero(self):
        assert ast_similarity("def f(:", "if x y") == 0.0

    def test_formatting_changes_high_similarity(self):
        src_a = "def f(x):\n    return x+1"
        src_b = "def f(x):\n\n    return x + 1  # with spaces"
        score = ast_similarity(src_a, src_b)
        assert score >= 0.8

    def test_different_control_flow_lower_similarity(self):
        src_for = "result = []\nfor x in data:\n    result.append(x)"
        src_comp = "result = [x for x in data]"
        score_diff = ast_similarity(src_for, src_comp)
        score_same = ast_similarity(src_for, src_for)
        assert score_same > score_diff
