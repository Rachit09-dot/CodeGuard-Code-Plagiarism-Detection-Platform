"""Core plagiarism analysis components."""

from .analysis_service import AnalysisService, PairResult, SubmissionResult, analyze_folder
from .ast_similarity import ast_similarity, extract_ast_tokens
from .config import (
    AST_WEIGHT,
    DEFAULT_K,
    DEFAULT_THRESHOLD,
    DEFAULT_WINDOW,
    MAX_FILE_SIZE_BYTES,
    MIN_TOKENS_FOR_FINGERPRINT,
    TOKEN_WEIGHT,
)
from .fingerprinter import build_fingerprint
from .normalizer import TokenizeError, normalize_code
from .similarity import clamp, containment_similarity, jaccard_similarity

__all__ = [
    # service
    "AnalysisService",
    "PairResult",
    "SubmissionResult",
    "analyze_folder",
    # AST
    "ast_similarity",
    "extract_ast_tokens",
    # config
    "AST_WEIGHT",
    "DEFAULT_K",
    "DEFAULT_THRESHOLD",
    "DEFAULT_WINDOW",
    "MAX_FILE_SIZE_BYTES",
    "MIN_TOKENS_FOR_FINGERPRINT",
    "TOKEN_WEIGHT",
    # fingerprint
    "build_fingerprint",
    # normalizer
    "normalize_code",
    "TokenizeError",
    # similarity
    "clamp",
    "containment_similarity",
    "jaccard_similarity",
]
