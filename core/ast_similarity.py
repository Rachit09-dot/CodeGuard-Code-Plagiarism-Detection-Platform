"""AST structural similarity using Python's built-in ``ast`` module.

Strategy
--------
We compute a *node-type sequence* from each AST: a depth-first walk that
records the *type name* of every node (e.g. ``"FunctionDef"``,
``"For"``, ``"If"``).  Variable names and literal values are intentionally
ignored — only the structural shape of the program matters.

The node-type sequences are then compared using the same Jaccard fingerprint
pipeline (k-gram hashing + winnowing) used for token similarity, so the two
metrics are directly comparable and can be combined with configurable weights.

Returns
-------
``ast_similarity(source_a, source_b) -> float``
    A value in [0, 1].  Returns 0.0 if either source cannot be parsed.

``extract_ast_tokens(source) -> list[str] | None``
    Returns the node-type sequence, or ``None`` on parse failure.
"""

from __future__ import annotations

import ast

from .config import DEFAULT_K, DEFAULT_WINDOW
from .fingerprinter import build_fingerprint
from .similarity import jaccard_similarity

__all__ = ["ast_similarity", "extract_ast_tokens"]


def extract_ast_tokens(source: str) -> list[str] | None:
    """Return a depth-first node-type sequence for *source*, or ``None``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    node_types: list[str] = []
    for node in ast.walk(tree):
        node_types.append(type(node).__name__)
    return node_types


def ast_similarity(source_a: str, source_b: str) -> float:
    """Return structural AST similarity between two Python source strings.

    Uses the same Winnowing fingerprint approach as token similarity so
    results are on the same scale and directly combinable.

    Returns 0.0 if either source fails to parse (invalid syntax).
    """
    tokens_a = extract_ast_tokens(source_a)
    tokens_b = extract_ast_tokens(source_b)

    if tokens_a is None or tokens_b is None:
        return 0.0

    fp_a = build_fingerprint(tokens_a, k=DEFAULT_K, window=DEFAULT_WINDOW)
    fp_b = build_fingerprint(tokens_b, k=DEFAULT_K, window=DEFAULT_WINDOW)

    return jaccard_similarity(fp_a, fp_b)
