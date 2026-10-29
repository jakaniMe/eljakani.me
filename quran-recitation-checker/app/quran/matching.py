"""
Word similarity on normalised skeletons.
"""
from __future__ import annotations

from functools import lru_cache

try:  # optional C implementation, ~50x faster
    from rapidfuzz.distance import Levenshtein as _RFLev  # type: ignore

    def levenshtein(a: str, b: str) -> int:
        return _RFLev.distance(a, b)
except ImportError:  # pragma: no cover - pure-python fallback
    def levenshtein(a: str, b: str) -> int:
        if a == b:
            return 0
        if len(a) < len(b):
            a, b = b, a
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                cur.append(min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
            prev = cur
        return prev[-1]


@lru_cache(maxsize=262144)
def similarity(a: str, b: str) -> float:
    """1.0 for identical skeletons, falling linearly with edit distance."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    return max(0.0, 1.0 - levenshtein(a, b) / max(len(a), len(b)))


def best_similarity(forms: tuple[str, ...], heard: str) -> float:
    return max(similarity(f, heard) for f in forms)
