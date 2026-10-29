"""
Check one recording from the command line (same pipeline as live).

  python qa/check_file.py my_recitation.m4a --from 2:1 --profile medium
  python qa/check_file.py my_recitation.wav --from 112:1 --json result.json

Prints every verse that was recited with its words coloured:
green = correct, red = wrong word, red strike = skipped, grey = not recited.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COLORS = {"match": "\033[32m", "substitution": "\033[31m", "deletion": "\033[31;9m", "pending": "\033[90m"}
RESET = "\033[0m"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--from", dest="start", required=True, help="first verse, e.g. 2:1")
    ap.add_argument("--profile", default="medium")
    ap.add_argument("--json", default=None, help="also write the full result here")
    args = ap.parse_args()

    from app.asr.registry import get_backend
    from app.offline import check_audio, load_audio

    s, a = (int(x) for x in args.start.split(":"))
    res = check_audio(load_audio(args.audio), s, a, args.profile, get_backend())
    for v in res["verses"]:
        words = " ".join(f"{COLORS.get(t['status'], '')}{tok}{RESET}"
                         for tok, t in zip(v["tokens"], v["token_statuses"]))
        print(f"{v['surah']}:{v['ayah']}  {100 * v['accuracy']:.0f}%  "
              f"(wrong {v['substitutions']}, skipped {v['deletions']}, extra {v['insertions']})")
        print(f"  {words}")
        if v["extra_words"]:
            print(f"  extra: {', '.join(e['text'] for e in v['extra_words'])}")
    t = res["timing"]
    print(f"\naudio {t['audio_seconds']} s, processed in {t['processing_seconds']} s, "
          f"mean decode {t['mean_decode_ms']} ms")
    print(f"heard: {res['transcript']}")
    if args.json:
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
