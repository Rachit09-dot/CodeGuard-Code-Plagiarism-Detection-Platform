"""Central configuration for the analysis engine.

All tuneable constants live here.  Values can be overridden via environment
variables so that Docker / CI deployments need not modify source code.

Environment variable names mirror the constant names (all upper-case).
"""

from __future__ import annotations

import os

__all__ = [
    "DEFAULT_K",
    "DEFAULT_WINDOW",
    "DEFAULT_THRESHOLD",
    "MIN_TOKENS_FOR_FINGERPRINT",
    "TOKEN_WEIGHT",
    "AST_WEIGHT",
    "MAX_FILE_SIZE_BYTES",
    "MAX_FILES_PER_SESSION",
    "HIGHLIGHT_MATCH_CAP",
    "ALLOWED_EXTENSIONS",
]


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# k-gram size — number of consecutive (normalised) tokens per gram
DEFAULT_K: int = _int("K_GRAM_SIZE", 5)

# Winnowing window size
DEFAULT_WINDOW: int = _int("WINDOW_SIZE", 12)

# Default similarity threshold (0–1)
DEFAULT_THRESHOLD: float = _float("SIMILARITY_THRESHOLD", 0.6)

# A submission must produce at least this many tokens to be considered
# "meaningful".  Below this, analysis status = "insufficient_content".
MIN_TOKENS_FOR_FINGERPRINT: int = _int("MIN_TOKENS_FOR_FINGERPRINT", DEFAULT_K)

# Combined score weights — must sum to 1.0
TOKEN_WEIGHT: float = _float("TOKEN_WEIGHT", 0.6)
AST_WEIGHT: float = _float("AST_WEIGHT", 0.4)

# Upload limits
MAX_FILE_SIZE_BYTES: int = _int("MAX_FILE_SIZE_BYTES", 10 * 1024 * 1024)  # 10 MB

# Maximum number of files allowed in a single analysis session.
# 30 files → 435 pairs, which is a reasonable upper bound for a classroom tool.
MAX_FILES_PER_SESSION: int = _int("MAX_FILES_PER_SESSION", 30)

# Maximum number of highlighted line-pairs returned to the frontend.
# Keeps the API response payload small for large files.
HIGHLIGHT_MATCH_CAP: int = _int("HIGHLIGHT_MATCH_CAP", 50)

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".py"})
