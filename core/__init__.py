"""Core plagiarism analysis components."""

from .analysis_service import AnalysisService, analyze_folder
from .fingerprinter import build_fingerprint
from .normalizer import normalize_code
from .similarity import jaccard_similarity

__all__ = [
    "AnalysisService",
    "analyze_folder",
    "build_fingerprint",
    "normalize_code",
    "jaccard_similarity",
]
