"""High-level analysis service.

Key design decisions
--------------------
* Each submission is tokenised and fingerprinted **exactly once** and the
  result is cached in a dict keyed by submission ID (or filename for the CLI
  path).  Subsequent pair comparisons reuse the cached representation.

* Full-file tokenisation: the entire source string is tokenised in one pass.
  Physical lines are never processed individually, so multiline constructs
  (multiline function calls, list literals, etc.) are handled correctly.

* Per-file error isolation: a ``TokenizeError`` or ``SyntaxError`` for one
  submission is recorded as ``status="invalid_source"``; it does not crash
  analysis of other submissions.

* Insufficient-content detection: if a submission produces fewer tokens than
  ``MIN_TOKENS_FOR_FINGERPRINT`` the status is ``"insufficient_content"`` and
  similarity is never computed for it.

* SHA-256 content hash: computed for every submission so exact duplicates
  can be detected without running the full fingerprint pipeline.

* Containment similarity is returned alongside Jaccard similarity.

* AST similarity is computed in addition to token similarity and the two are
  combined using configurable weights (``TOKEN_WEIGHT`` + ``AST_WEIGHT``).
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from tokenize import TokenError as TokenizeError
from typing import Any

from .ast_similarity import ast_similarity
from .config import (
    AST_WEIGHT,
    DEFAULT_K,
    DEFAULT_THRESHOLD,
    DEFAULT_WINDOW,
    MIN_TOKENS_FOR_FINGERPRINT,
    TOKEN_WEIGHT,
)
from .fingerprinter import build_fingerprint
from .normalizer import normalize_code
from .similarity import clamp, containment_similarity, jaccard_similarity

logger = logging.getLogger(__name__)

__all__ = ["AnalysisService", "SubmissionResult", "PairResult", "analyze_folder"]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SubmissionResult:
    """Per-submission analysis representation (computed once, cached)."""

    name: str
    source: str
    status: str                      # "ok" | "invalid_source" | "insufficient_content"
    error: str | None = None
    tokens: list[str] = field(default_factory=list)
    fingerprint: set[int] = field(default_factory=set)
    content_hash: str = ""           # SHA-256 hex digest of raw source

    @property
    def is_valid(self) -> bool:
        return self.status == "ok"


@dataclass
class PairResult:
    """Result of comparing two submissions."""

    name_a: str
    name_b: str
    jaccard: float
    containment: float
    ast_score: float
    combined_score: float
    suspicious: bool
    is_exact_duplicate: bool
    status_a: str
    status_b: str
    # Configuration snapshot — records what settings produced this result
    threshold: float = 0.0
    token_weight: float = TOKEN_WEIGHT
    ast_weight: float = AST_WEIGHT
    k: int = DEFAULT_K
    window: int = DEFAULT_WINDOW

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_a": self.name_a,
            "file_b": self.name_b,
            "score": round(self.combined_score, 4),
            "similarity_score": round(self.combined_score, 4),
            "jaccard_similarity": round(self.jaccard, 4),
            "containment_similarity": round(self.containment, 4),
            "ast_similarity": round(self.ast_score, 4),
            "token_similarity": round(self.jaccard, 4),  # kept for backward compat
            "is_exact_duplicate": self.is_exact_duplicate,
            "suspicious": self.suspicious,
            "status": "SUSPICIOUS" if self.suspicious else "LOW SIMILARITY",
            "status_a": self.status_a,
            "status_b": self.status_b,
            # Config snapshot — allows old results to be explained
            "analysis_config": {
                "threshold": self.threshold,
                "token_weight": self.token_weight,
                "ast_weight": self.ast_weight,
                "k_gram_size": self.k,
                "window_size": self.window,
            },
        }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AnalysisService:
    """Stateless analysis service.  Pass a cache dict to reuse fingerprints
    across multiple ``compare_pair`` calls for the same batch of submissions.
    """

    def __init__(
        self,
        k: int = DEFAULT_K,
        window: int = DEFAULT_WINDOW,
        token_weight: float = TOKEN_WEIGHT,
        ast_weight: float = AST_WEIGHT,
    ) -> None:
        self.k = k
        self.window = window
        self.token_weight = token_weight
        self.ast_weight = ast_weight

    # ------------------------------------------------------------------
    # Per-submission representation (cached externally by the caller)
    # ------------------------------------------------------------------

    def prepare_submission(self, name: str, source: str) -> SubmissionResult:
        """Tokenise and fingerprint *source* exactly once.

        Never raises — errors are captured in ``SubmissionResult.status``.
        """
        content_hash = hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()

        try:
            tokens = normalize_code(source)
        except TokenizeError as exc:
            logger.warning("Invalid source in '%s': %s", name, exc)
            return SubmissionResult(
                name=name,
                source=source,
                status="invalid_source",
                error=str(exc),
                content_hash=content_hash,
            )
        except Exception as exc:  # pragma: no cover — belt-and-suspenders
            logger.error("Unexpected tokenise error in '%s': %s", name, exc)
            return SubmissionResult(
                name=name,
                source=source,
                status="invalid_source",
                error=str(exc),
                content_hash=content_hash,
            )

        if len(tokens) < MIN_TOKENS_FOR_FINGERPRINT:
            logger.info("'%s' has insufficient content (%d tokens).", name, len(tokens))
            return SubmissionResult(
                name=name,
                source=source,
                status="insufficient_content",
                tokens=tokens,
                content_hash=content_hash,
            )

        fingerprint = build_fingerprint(tokens, k=self.k, window=self.window)
        return SubmissionResult(
            name=name,
            source=source,
            status="ok",
            tokens=tokens,
            fingerprint=fingerprint,
            content_hash=content_hash,
        )

    # ------------------------------------------------------------------
    # Pair comparison (reuses pre-built SubmissionResults)
    # ------------------------------------------------------------------

    def compare_pair(
        self,
        a: SubmissionResult,
        b: SubmissionResult,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> PairResult:
        """Compare two pre-prepared submissions.

        * Returns ``combined_score = 0.0`` when either submission is not
          "ok" — insufficient content / invalid source is never flagged.
        * Exact duplicate detection via SHA-256.
        * Scores: token Jaccard + containment + AST structural similarity
          combined with configurable weights.
        """
        # Exact duplicate shortcut
        is_exact = bool(a.content_hash and b.content_hash and a.content_hash == b.content_hash)

        if not a.is_valid or not b.is_valid:
            return PairResult(
                name_a=a.name,
                name_b=b.name,
                jaccard=0.0,
                containment=0.0,
                ast_score=0.0,
                combined_score=1.0 if is_exact else 0.0,
                suspicious=is_exact,
                is_exact_duplicate=is_exact,
                status_a=a.status,
                status_b=b.status,
                threshold=threshold,
                token_weight=self.token_weight,
                ast_weight=self.ast_weight,
                k=self.k,
                window=self.window,
            )

        jaccard = jaccard_similarity(a.fingerprint, b.fingerprint)
        contain = containment_similarity(a.fingerprint, b.fingerprint)
        ast_score = ast_similarity(a.source, b.source)

        # Combined score: weighted average of token Jaccard and AST similarity.
        # Containment is not in the combined score formula but IS returned so
        # the UI can show it and it is considered for the suspicious flag.
        # Clamped to [0, 1] to guard against floating-point edge cases when
        # weights are misconfigured (e.g. sum > 1.0).
        combined = clamp(self.token_weight * jaccard + self.ast_weight * ast_score)

        # Suspicious if combined score OR containment exceeds threshold
        suspicious = is_exact or combined >= threshold or contain >= threshold

        return PairResult(
            name_a=a.name,
            name_b=b.name,
            jaccard=jaccard,
            containment=contain,
            ast_score=ast_score,
            combined_score=combined,
            suspicious=suspicious,
            is_exact_duplicate=is_exact,
            status_a=a.status,
            status_b=b.status,
            threshold=threshold,
            token_weight=self.token_weight,
            ast_weight=self.ast_weight,
            k=self.k,
            window=self.window,
        )

    # ------------------------------------------------------------------
    # Folder-level analysis (CLI path)
    # ------------------------------------------------------------------

    def analyze_folder(
        self,
        folder: str | Path,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> list[tuple[float, str, str]]:
        """Analyse all .py files in *folder* with fingerprint caching.

        Returns a list of ``(score, file_a, file_b)`` tuples sorted by score
        descending, including only pairs where both submissions are "ok".
        """
        folder_path = Path(folder)
        files = sorted(folder_path.glob("*.py"), key=lambda p: p.name)
        if not files:
            raise FileNotFoundError(f"No .py files found in '{folder_path}'.")

        # Build representations once
        cache: dict[str, SubmissionResult] = {}
        for fp in files:
            source = fp.read_text(encoding="utf-8", errors="ignore")
            cache[fp.name] = self.prepare_submission(fp.name, source)

        results: list[tuple[float, str, str]] = []
        for left_path, right_path in combinations(files, 2):
            left = cache[left_path.name]
            right = cache[right_path.name]
            pair = self.compare_pair(left, right, threshold=threshold)
            results.append((pair.combined_score, left.name, right.name))

        results.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return results


# ---------------------------------------------------------------------------
# Module-level convenience function (used by CLI)
# ---------------------------------------------------------------------------

def analyze_folder(
    folder: str | Path,
    threshold: float = DEFAULT_THRESHOLD,
    k: int = DEFAULT_K,
    window: int = DEFAULT_WINDOW,
) -> list[tuple[float, str, str]]:
    service = AnalysisService(k=k, window=window)
    return service.analyze_folder(folder, threshold=threshold)
