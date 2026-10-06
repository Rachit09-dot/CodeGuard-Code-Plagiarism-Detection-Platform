"""AST structural similarity — unit + regression tests.

Verifies the six key behavioural requirements from the spec:
  1. identical code → 1.0
  2. variable renaming → high (≥ 0.8)
  3. formatting/comment changes → high (≥ 0.8)
  4. literal changes only → high (≥ 0.8)  — AST ignores literal values
  5. completely unrelated programs → low (< 0.5)
  6. different control flow → meaningfully lower than identical

Also verifies error-safety:
  - invalid Python → 0.0, no exception
  - empty source parses OK
"""

import pytest
from core.ast_similarity import ast_similarity, extract_ast_tokens


# ---------------------------------------------------------------------------
# extract_ast_tokens
# ---------------------------------------------------------------------------

class TestExtractAstTokens:
    def test_valid_source_returns_list(self):
        result = extract_ast_tokens("def f(x):\n    return x")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_contains_expected_node_types(self):
        result = extract_ast_tokens("def f(x):\n    return x + 1")
        assert "FunctionDef" in result
        assert "Return" in result

    def test_for_loop_produces_For_node(self):
        result = extract_ast_tokens("for x in items:\n    print(x)")
        assert "For" in result

    def test_if_statement_produces_If_node(self):
        result = extract_ast_tokens("if x > 0:\n    pass")
        assert "If" in result

    def test_invalid_source_returns_none(self):
        assert extract_ast_tokens("def f(:") is None

    def test_empty_source_is_valid(self):
        result = extract_ast_tokens("")
        assert result is not None
        assert "Module" in result

    def test_variable_names_not_in_output(self):
        """AST tokens should be node-type names, not variable names."""
        result = extract_ast_tokens("my_unique_var_xyz = 42")
        assert "my_unique_var_xyz" not in result


# ---------------------------------------------------------------------------
# Requirement 1: identical code → 1.0
# ---------------------------------------------------------------------------

class TestIdenticalCode:
    def test_one_liner_identical(self):
        src = "x = 1 + 2"
        assert ast_similarity(src, src) == pytest.approx(1.0)

    def test_function_identical(self):
        src = "def f(x):\n    return x * 2"
        assert ast_similarity(src, src) == pytest.approx(1.0)

    def test_complex_program_identical(self):
        src = (
            "def total(nums):\n"
            "    s = 0\n"
            "    for v in nums:\n"
            "        if v > 0:\n"
            "            s += v\n"
            "    return s\n"
        )
        assert ast_similarity(src, src) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Requirement 2: variable renaming → high similarity
# ---------------------------------------------------------------------------

class TestVariableRenaming:
    def test_simple_rename(self):
        src_a = "def total(nums):\n    s = 0\n    for v in nums:\n        s += v\n    return s"
        src_b = "def compute(items):\n    acc = 0\n    for item in items:\n        acc += item\n    return acc"
        score = ast_similarity(src_a, src_b)
        assert score >= 0.8, f"Expected >= 0.8 for renamed vars, got {score}"

    def test_function_name_rename(self):
        src_a = "def process(data):\n    return sorted(data)"
        src_b = "def handle(lst):\n    return sorted(lst)"
        score = ast_similarity(src_a, src_b)
        assert score >= 0.8, f"Expected >= 0.8 for renamed function, got {score}"

    def test_loop_variable_rename(self):
        src_a = "for i in range(10):\n    print(i)"
        src_b = "for idx in range(10):\n    print(idx)"
        score = ast_similarity(src_a, src_b)
        assert score >= 0.8, f"Expected >= 0.8 for renamed loop var, got {score}"


# ---------------------------------------------------------------------------
# Requirement 3: formatting / whitespace / comment changes → high similarity
# ---------------------------------------------------------------------------

class TestFormattingChanges:
    def test_extra_blank_lines(self):
        src_a = "def f(x):\n    return x + 1"
        src_b = "def f(x):\n\n\n    return x + 1\n"
        assert ast_similarity(src_a, src_b) >= 0.8

    def test_comments_added(self):
        src_a = "def f(x):\n    return x + 1"
        src_b = "# computes f\ndef f(x):\n    # add one\n    return x + 1"
        assert ast_similarity(src_a, src_b) >= 0.8

    def test_operator_spacing(self):
        src_a = "result = a+b*c"
        src_b = "result = a + b * c"
        assert ast_similarity(src_a, src_b) >= 0.8


# ---------------------------------------------------------------------------
# Requirement 4: literal value changes only → high similarity
# ---------------------------------------------------------------------------

class TestLiteralChanges:
    def test_different_integer_literals(self):
        src_a = "x = 42\ny = x + 1"
        src_b = "x = 99\ny = x + 1"
        score = ast_similarity(src_a, src_b)
        assert score >= 0.8, f"Expected >= 0.8 for literal change, got {score}"

    def test_different_string_literals(self):
        src_a = "msg = 'hello'\nprint(msg)"
        src_b = "msg = 'world'\nprint(msg)"
        score = ast_similarity(src_a, src_b)
        assert score >= 0.8, f"Expected >= 0.8 for string literal change, got {score}"


# ---------------------------------------------------------------------------
# Requirement 5: completely unrelated programs → low similarity
# ---------------------------------------------------------------------------

class TestUnrelatedPrograms:
    def test_sort_vs_fileio(self):
        src_a = "def sort_list(lst):\n    return sorted(lst)"
        src_b = "import os\ndef get_env(key):\n    return os.getenv(key, '')"
        score = ast_similarity(src_a, src_b)
        assert score < 0.5, f"Expected < 0.5 for unrelated programs, got {score}"

    def test_arithmetic_vs_class(self):
        src_a = "x = 1\ny = 2\nz = x + y\nprint(z)"
        src_b = (
            "class Dog:\n"
            "    def __init__(self, name):\n"
            "        self.name = name\n"
            "    def bark(self):\n"
            "        return 'woof'\n"
        )
        score = ast_similarity(src_a, src_b)
        assert score < 0.5, f"Expected < 0.5 for unrelated programs, got {score}"


# ---------------------------------------------------------------------------
# Requirement 6: different control flow → meaningfully lower
# ---------------------------------------------------------------------------

class TestDifferentControlFlow:
    def test_for_vs_if_lower_than_identical(self):
        src_for = "for x in data:\n    print(x)"
        src_if  = "if x in data:\n    print(x)"
        score_diff = ast_similarity(src_for, src_if)
        score_same = ast_similarity(src_for, src_for)
        assert score_same > score_diff, (
            f"Identical ({score_same:.3f}) should beat for-vs-if ({score_diff:.3f})"
        )

    def test_loop_vs_listcomp(self):
        src_loop = "result = []\nfor x in data:\n    result.append(x * 2)"
        src_comp = "result = [x * 2 for x in data]"
        score_diff = ast_similarity(src_loop, src_comp)
        score_same = ast_similarity(src_loop, src_loop)
        assert score_same > score_diff

    def test_while_vs_for_different(self):
        src_for   = "for i in range(10):\n    print(i)"
        src_while = "i = 0\nwhile i < 10:\n    print(i)\n    i += 1"
        score = ast_similarity(src_for, src_while)
        # Different structure: should not be 1.0
        assert score < 1.0

    def test_if_vs_try_different(self):
        src_if  = "if x > 0:\n    print(x)\nelse:\n    print(0)"
        src_try = "try:\n    print(x)\nexcept Exception:\n    print(0)"
        score = ast_similarity(src_if, src_try)
        assert score < 1.0


# ---------------------------------------------------------------------------
# Error safety
# ---------------------------------------------------------------------------

class TestErrorSafety:
    def test_invalid_left_returns_zero(self):
        assert ast_similarity("def f(:", "def f(x):\n    return x") == 0.0

    def test_invalid_right_returns_zero(self):
        assert ast_similarity("def f(x):\n    return x", "def f(:") == 0.0

    def test_both_invalid_returns_zero(self):
        assert ast_similarity("def f(:", "if x y") == 0.0

    def test_no_exception_on_invalid(self):
        # Must not raise any exception
        result = ast_similarity("!!!invalid!!!", "def f(x):\n    return x")
        assert result == 0.0

    def test_score_bounded_zero_to_one(self):
        src_a = "def f(x):\n    for i in range(x):\n        print(i)"
        src_b = "def g(n):\n    for j in range(n):\n        print(j)"
        score = ast_similarity(src_a, src_b)
        assert 0.0 <= score <= 1.0
