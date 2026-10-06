"""Token normalizer for the plagiarism analysis pipeline.

Strategy
--------
- Python *keywords* (for, if, return, in, while, def, class, …) are preserved
  verbatim.  They carry control-flow information and must NOT collapse to "ID".
- User-defined *identifiers* normalise to the placeholder "ID".
- Numeric literals  → "NUM"
- String  literals  → "STR"
- Operators / punctuation are kept as-is.
- Comments, whitespace tokens, and structural tokens (INDENT / DEDENT /
  NEWLINE / ENDMARKER / ENCODING) are discarded.
- The entire source is tokenised in one pass; physical lines are never
  processed individually.

Tokenisation errors (e.g. unterminated strings, invalid indentation) are
raised as ``TokenizeError`` so callers can handle them per submission rather
than letting the error propagate to the HTTP layer.
"""

from __future__ import annotations

import keyword
import tokenize
from tokenize import TokenError as TokenizeError  # re-exported for callers

__all__ = ["normalize_code", "TokenizeError"]


def normalize_code(source: str) -> list[str]:
    """Return a normalised token stream for *source*.

    Python keywords are preserved; user-defined identifiers are replaced with
    the placeholder ``"ID"``.

    Raises
    ------
    tokenize.TokenError
        If the source cannot be fully tokenised (e.g. unterminated string,
        mismatched brackets).
    """
    _SKIP_TYPES = {
        tokenize.COMMENT,
        tokenize.ENCODING,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
    }

    tokens: list[str] = []

    # Use an iterator-based readline so that exhaustion raises TokenError
    # for unterminated string/bracket constructs instead of hanging.
    lines = iter(source.splitlines(keepends=True))

    def _readline() -> str:
        try:
            return next(lines)
        except StopIteration:
            return ""

    stream = tokenize.generate_tokens(_readline)

    try:
        for tok in stream:
            tok_type = tok.type
            tok_string = tok.string

            if tok_type in _SKIP_TYPES:
                continue

            if tok_type == tokenize.NAME:
                # Preserve keywords so that `for` != `if` != `return`
                if keyword.iskeyword(tok_string) or keyword.issoftkeyword(tok_string):
                    tokens.append(tok_string)
                else:
                    tokens.append("ID")

            elif tok_type == tokenize.NUMBER:
                tokens.append("NUM")

            elif tok_type == tokenize.STRING:
                tokens.append("STR")

            else:
                # Operators, punctuation, OP tokens
                tokens.append(tok_string)
    except tokenize.TokenError:
        # Re-raise so callers can mark this submission as invalid_source
        raise

    return tokens