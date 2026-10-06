"""Unit tests for the token normaliser.

Verifies:
* Python keywords are preserved verbatim.
* User-defined identifiers are collapsed to 'ID'.
* Numeric and string literals are collapsed.
* Comments / whitespace tokens are discarded.
* Multiline constructs are handled correctly.
* Invalid Python raises TokenizeError (not a hard crash).
"""

import pytest
from core.normalizer import TokenizeError, normalize_code


# ---------------------------------------------------------------------------
# Keyword preservation
# ---------------------------------------------------------------------------

class TestKeywordPreservation:
    def test_for_keyword_preserved(self):
        tokens = normalize_code("for x in y:\n    pass")
        assert "for" in tokens

    def test_if_keyword_preserved(self):
        tokens = normalize_code("if x:\n    pass")
        assert "if" in tokens

    def test_return_keyword_preserved(self):
        tokens = normalize_code("def f():\n    return 1")
        assert "return" in tokens

    def test_in_keyword_preserved(self):
        tokens = normalize_code("for x in y:\n    pass")
        assert "in" in tokens

    def test_while_keyword_preserved(self):
        tokens = normalize_code("while True:\n    break")
        assert "while" in tokens

    def test_yield_keyword_preserved(self):
        tokens = normalize_code("def g():\n    yield 1")
        assert "yield" in tokens

    def test_for_not_equal_to_if(self):
        """for and if must produce different token streams."""
        for_tokens = normalize_code("for x in data:\n    print(x)")
        if_tokens  = normalize_code("if x in data:\n    print(x)")
        assert for_tokens != if_tokens

    def test_return_not_equal_to_yield(self):
        ret_tokens   = normalize_code("def f():\n    return 1")
        yield_tokens = normalize_code("def f():\n    yield 1")
        assert ret_tokens != yield_tokens


# ---------------------------------------------------------------------------
# Identifier normalisation
# ---------------------------------------------------------------------------

class TestIdentifierNormalisation:
    def test_user_identifier_becomes_ID(self):
        tokens = normalize_code("alice = 1")
        assert "alice" not in tokens
        assert "ID" in tokens

    def test_different_identifiers_same_normalisation(self):
        t1 = normalize_code("counter = 0\ncounter += 1")
        t2 = normalize_code("student_name = 0\nstudent_name += 1")
        assert t1 == t2

    def test_keywords_not_collapsed_to_ID(self):
        tokens = normalize_code("for item in items:\n    continue")
        assert "ID" not in {t for t in tokens if t in {"for", "in", "continue"}}
        assert "for" in tokens
        assert "in" in tokens
        assert "continue" in tokens

    def test_function_name_normalised(self):
        tokens = normalize_code("def my_func():\n    pass")
        assert "my_func" not in tokens
        assert "ID" in tokens


# ---------------------------------------------------------------------------
# Literal normalisation
# ---------------------------------------------------------------------------

class TestLiteralNormalisation:
    def test_integer_literal_becomes_NUM(self):
        tokens = normalize_code("x = 42")
        assert "NUM" in tokens
        assert "42" not in tokens

    def test_float_literal_becomes_NUM(self):
        tokens = normalize_code("x = 3.14")
        assert "NUM" in tokens

    def test_string_literal_becomes_STR(self):
        tokens = normalize_code("x = 'hello'")
        assert "STR" in tokens
        assert "'hello'" not in tokens

    def test_fstring_becomes_STR(self):
        tokens = normalize_code('x = f"hi {name}"')
        assert "STR" in tokens


# ---------------------------------------------------------------------------
# Comment / whitespace removal
# ---------------------------------------------------------------------------

class TestCommentRemoval:
    def test_comment_not_in_tokens(self):
        tokens = normalize_code("x = 1  # this is a comment")
        for t in tokens:
            assert not t.startswith("#")

    def test_blank_source_returns_empty(self):
        tokens = normalize_code("")
        assert tokens == []

    def test_comment_only_source_returns_empty(self):
        tokens = normalize_code("# just a comment\n# another")
        assert tokens == []


# ---------------------------------------------------------------------------
# Multiline constructs
# ---------------------------------------------------------------------------

class TestMultilineConstructs:
    def test_multiline_function_call(self):
        source = "foo(\n    1,\n    2\n)"
        tokens = normalize_code(source)
        assert "NUM" in tokens
        assert len(tokens) > 0

    def test_multiline_list_literal(self):
        source = "x = [\n    1,\n    2,\n    3\n]"
        tokens = normalize_code(source)
        assert "NUM" in tokens

    def test_multiline_dict_literal(self):
        source = "d = {\n    'a': 1,\n    'b': 2\n}"
        tokens = normalize_code(source)
        assert "STR" in tokens
        assert "NUM" in tokens

    def test_multiline_function_def(self):
        source = "def foo(\n    a,\n    b\n):\n    return a + b"
        tokens = normalize_code(source)
        assert "def" in tokens
        assert "return" in tokens

    def test_multiline_string(self):
        source = 'x = """\nhello\nworld\n"""'
        tokens = normalize_code(source)
        assert "STR" in tokens


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_unterminated_multiline_string_raises_TokenizeError(self):
        """A multiline string that is never closed should raise TokenizeError."""
        with pytest.raises(TokenizeError):
            normalize_code("x = '''\nunterminated")

    def test_unclosed_bracket_raises_TokenizeError(self):
        """An unclosed bracket spanning lines should raise TokenizeError."""
        with pytest.raises(TokenizeError):
            normalize_code("foo(\n    1,")

    def test_valid_code_does_not_raise(self):
        tokens = normalize_code("x = 1 + 2")
        assert len(tokens) > 0

    def test_single_line_unterminated_string_returns_tokens(self):
        """Python 3.11 tokeniser recovers from single-line unterminated strings
        rather than raising; we document that behaviour here."""
        # Should not raise AND should not hang
        tokens = normalize_code("x = 'unterminated")
        assert isinstance(tokens, list)
