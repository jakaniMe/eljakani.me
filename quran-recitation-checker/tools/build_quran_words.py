"""
Build data/quran/quran_words.json: one entry per word of the Qur'an with
  - the Uthmani spelling we DISPLAY (Tanzil Uthmani, identical to M2's text), and
  - the Imlaei (standard) spelling we COMPARE against the ASR output.

Why: the ASR models write standard (Imlaei) Arabic ("الكتاب", "الصلاة") while the
Mushaf text is Uthmani ("ٱلْكِتَٰبُ", "ٱلصَّلَوٰةَ"). Comparing the two directly was
the main reason M2 flagged correct recitation as wrong.

Sources
  - data/quran/tanzil_uthmani.json  (Tanzil.net Uthmani text, already shipped in M2)
  - quran-uthmani-imlaey-map.json   (word-by-word Uthmani -> Imlaei map from the
    `quran-transcript` package, MIT licence, https://github.com/obadx/quran-transcript)

Usage
  pip install quran-transcript   # only needed to (re)build the file
  python tools/build_quran_words.py [path/to/quran-uthmani-imlaey-map.json]

Output format
  {"1:1": [["بِسْمِ", "بِسْمِ"], ["ٱللَّهِ", "اللَّهِ"], ...], ...}
  i.e. "surah:ayah" -> list of [uthmani_display_word, imlaei_word(s)].
  The Imlaei side may contain a space (e.g. "يَا أَيُّهَا" for "يَـٰٓأَيُّهَا").
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TANZIL = ROOT / "data" / "quran" / "tanzil_uthmani.json"
OUT = ROOT / "data" / "quran" / "quran_words.json"

# Stand-alone pause (waqf) / sajdah marks that Tanzil writes as separate "words".
_MARK_ONLY = re.compile(r"^[ۖ-ۜ۞۩]+$")


def _default_map_path() -> Path:
    try:
        import quran_transcript  # type: ignore
    except ImportError:
        sys.exit("Pass the map path, or `pip install quran-transcript` first.")
    return Path(quran_transcript.__file__).parent / "quran-script" / "quran-uthmani-imlaey-map.json"


def main() -> None:
    map_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_map_path()
    tanzil = json.loads(TANZIL.read_text(encoding="utf-8"))
    rasm = json.loads(map_path.read_text(encoding="utf-8"))

    out: dict[str, list[list[str]]] = {}
    for sura in rasm["quran"]["sura"]:
        for aya in sura["aya"]:
            key = f'{sura["@index"]}:{aya["@index"]}'

            # Display words: Tanzil text, with pause marks glued to the previous word.
            display: list[str] = []
            for tok in tanzil[key].split():
                if _MARK_ONLY.match(tok) and display:
                    display[-1] = f"{display[-1]} {tok}"
                elif not _MARK_ONLY.match(tok):
                    display.append(tok)

            imlaei = [e["@imlaey"] for e in aya["rasm_map"]]
            if len(display) != len(imlaei):
                sys.exit(f"{key}: word count mismatch {len(display)} vs {len(imlaei)}")
            out[key] = [[u, i] for u, i in zip(display, imlaei)]

    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n_words = sum(len(v) for v in out.values())
    print(f"wrote {OUT} ({len(out)} ayat, {n_words} words)")


if __name__ == "__main__":
    main()
