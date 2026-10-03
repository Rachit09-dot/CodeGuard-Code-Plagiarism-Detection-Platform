from __future__ import annotations

from itertools import combinations
from pathlib import Path

from .fingerprinter import build_fingerprint
from .normalizer import normalize_code
from .similarity import jaccard_similarity


class AnalysisService:
    """Service layer for plagiarism analysis."""

    def __init__(self, k: int = 5, window: int = 12):
        self.k = k
        self.window = window

    def analyze_file(self, file_path: str | Path) -> set[int]:
        source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        tokens = normalize_code(source)
        return build_fingerprint(tokens, k=self.k, window=self.window)

    def analyze_folder(self, folder: str | Path, threshold: float = 0.5) -> list[tuple[float, str, str]]:
        folder_path = Path(folder)
        files = sorted(folder_path.glob("*.py"), key=lambda path: path.name)
        if not files:
            raise FileNotFoundError(f"No .py files found in '{folder_path}'.")

        fingerprints: dict[str, set[int]] = {}
        for file_path in files:
            fingerprints[file_path.name] = self.analyze_file(file_path)

        results: list[tuple[float, str, str]] = []
        for left, right in combinations(files, 2):
            similarity = jaccard_similarity(fingerprints[left.name], fingerprints[right.name])
            results.append((similarity, left.name, right.name))

        results.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return results


def analyze_folder(folder: str | Path, threshold: float = 0.5, k: int = 5, window: int = 12):
    service = AnalysisService(k=k, window=window)
    return service.analyze_folder(folder, threshold=threshold)
