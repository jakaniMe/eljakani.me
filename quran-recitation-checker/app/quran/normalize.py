"""
Arabic text normalisation used for *matching* (never for display).

Everything is reduced to a "skeleton": bare letters, no harakat, no Qur'anic
marks, with spelling variants that the reciter cannot be heard to differ on
folded together (hamza seats, alif forms, taa marbuta, alif maqsura ...).

The reference side is the Imlaei (standard) spelling of each Mushaf word, which
is what the ASR models write, so the skeletons of a correctly recited word and
its reference are identical in the vast majority of cases.
"""
from __future__ import annotations

import re
from functools import lru_cache

# Harakat, tanween, shadda, sukun, superscript alif, Qur'anic annotation marks,
# small waw/yeh, tatweel and the Arabic punctuation block.
_STRIP = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")

_FOLD = str.maketrans({
    "ٱ": "ا",  # alif wasla
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ٲ": "ا",
    "ٳ": "ا",
    "ؤ": "و",
    "ئ": "ي",
    "ى": "ي",  # alif maqsura
    "ی": "ي",  # Farsi yeh
    "ة": "ه",  # taa marbuta
    "ک": "ك",  # Farsi kaf
    "ء": None,  # bare hamza: spelled in many ways, never decisive on its own
})

_NON_ARABIC = re.compile(r"[^ء-ي\s]")
_SPACES = re.compile(r"\s+")


@lru_cache(maxsize=65536)
def skeleton(text: str) -> str:
    """Return the matching skeleton of a word or phrase (spaces are kept)."""
    s = _STRIP.sub("", text)
    s = s.translate(_FOLD)
    s = _NON_ARABIC.sub(" ", s)
    return _SPACES.sub(" ", s).strip()


def words(text: str) -> list[str]:
    """Split ASR text into skeleton words, dropping empties."""
    return [w for w in skeleton(text).split(" ") if w]


# Kept for backwards compatibility with M1/M2 imports.
def normalize_text(s: str) -> str:
    return skeleton(s)


def strip_diacritics(s: str) -> str:
    return _STRIP.sub("", s)
