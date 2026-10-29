"""
Qur'an reference text: what we display (Uthmani) and what we compare (Imlaei).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterator

from app.config import CONFIG
from app.quran.normalize import skeleton

# Disjoined letters (al-muqatta'at) are recited by letter name, so the ASR may
# write either the joined form ("الم") or the names ("الف لام ميم").
_LETTER_NAMES = {
    "ا": "الف", "ل": "لام", "م": "ميم", "ر": "را", "ص": "صاد", "ك": "كاف",
    "ه": "ها", "ي": "يا", "ع": "عين", "ط": "طا", "س": "سين", "ح": "حا",
    "ق": "قاف", "ن": "نون",
}
_MUQATTAAT = {"الم", "المص", "الر", "المر", "كهيعص", "طه", "طسم", "طس", "يس", "ص", "حم", "عسق", "ق", "ن"}


@dataclass(frozen=True)
class RefWord:
    surah: int
    ayah: int
    index: int            # position inside the ayah
    display: str          # Uthmani, as shown in the Mushaf panel
    imlaei: str           # standard spelling (may be two words, e.g. "يَا أَيُّهَا")
    forms: tuple[str, ...]  # skeleton spellings accepted for this word (spaces removed)
    n_words: int          # max number of ASR words this word may be written as

    @property
    def key(self) -> str:
        return f"{self.surah}:{self.ayah}"


def _forms_for(imlaei: str, surah: int, ayah: int, index: int) -> tuple[tuple[str, ...], int]:
    sk = skeleton(imlaei)
    forms = [sk.replace(" ", "")]
    n_words = len(sk.split())
    first_word = index == 0 and (ayah == 1 or (surah == 42 and ayah == 2))
    if first_word and sk in _MUQATTAAT:
        names = [_LETTER_NAMES[c] for c in sk]
        forms.append("".join(names))
        n_words = max(n_words, len(names))
    return tuple(forms), n_words


class QuranText:
    def __init__(self, path: str):
        with open(path, encoding="utf-8") as f:
            raw: dict[str, list[list[str]]] = json.load(f)
        self._ayat: dict[tuple[int, int], tuple[RefWord, ...]] = {}
        self._counts: dict[int, int] = {}
        for key, pairs in raw.items():
            s, a = (int(x) for x in key.split(":"))
            ws = []
            for i, (u, im) in enumerate(pairs):
                forms, n = _forms_for(im, s, a, i)
                ws.append(RefWord(s, a, i, u, im, forms, n))
            self._ayat[(s, a)] = tuple(ws)
            self._counts[s] = max(self._counts.get(s, 0), a)

    # ---- lookups -------------------------------------------------------
    def words(self, surah: int, ayah: int) -> tuple[RefWord, ...]:
        try:
            return self._ayat[(surah, ayah)]
        except KeyError:
            raise KeyError(f"Āyah not found: {surah}:{ayah}") from None

    def display_tokens(self, surah: int, ayah: int) -> list[str]:
        return [w.display for w in self.words(surah, ayah)]

    def ayah_count(self, surah: int) -> int:
        if surah not in self._counts:
            raise KeyError(f"Surah not found: {surah}")
        return self._counts[surah]

    def exists(self, surah: int, ayah: int) -> bool:
        return (surah, ayah) in self._ayat

    def next_ayah(self, surah: int, ayah: int) -> tuple[int, int] | None:
        if ayah < self._counts.get(surah, 0):
            return surah, ayah + 1
        if surah < 114:
            return surah + 1, 1
        return None

    def iter_ayat(self, surah: int, ayah: int) -> Iterator[tuple[int, int]]:
        cur: tuple[int, int] | None = (surah, ayah)
        while cur is not None:
            yield cur
            cur = self.next_ayah(*cur)


@lru_cache(maxsize=1)
def get_quran() -> QuranText:
    return QuranText(CONFIG.QURAN_WORDS_PATH)
