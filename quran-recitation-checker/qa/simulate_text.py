"""
Text-level stress test of the tracker (no audio, no model needed).

Simulates a reciter + ASR on whole surahs:
  real mistakes   skipped word, wrong word (from elsewhere in the Qur'an), extra word
  not mistakes    repeating the previous 1-3 words
  ASR noise       misspelt correct words: confusable letters, dropped/added long vowels,
                  a word split in two, at --noise rate; some with low ASR confidence

  python qa/simulate_text.py --surahs 78-114 --noise 0.10
  python qa/simulate_text.py --surahs 2 --noise 0.15 --profiles medium

Reports per profile: recall on planted mistakes, false-positive rate on correct
words, split into clean words and ASR-misspelt words.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.profiles import get_profile  # noqa: E402
from app.quran.normalize import skeleton  # noqa: E402
from app.quran.text import get_quran  # noqa: E402
from app.quran.tracker import HypWord, RecitationTracker  # noqa: E402

CONFUSABLE = [("ض", "د"), ("ظ", "ذ"), ("ص", "س"), ("ط", "ت"), ("ح", "ه"), ("ق", "ك"),
              ("ث", "س"), ("ذ", "ز"), ("ع", "ا"), ("غ", "خ")]


def misspell(word: str, rng: random.Random) -> list[str]:
    w = skeleton(word).replace(" ", "")
    if len(w) < 2:
        return [w]
    kind = rng.random()
    if kind < 0.4:  # confusable consonant
        pairs = [(a, b) for a, b in CONFUSABLE if a in w or b in w]
        if pairs:
            a, b = rng.choice(pairs)
            return [w.replace(a, b, 1) if a in w else w.replace(b, a, 1)]
    if kind < 0.75:  # long vowel dropped or added
        i = rng.randrange(1, len(w))
        if w[i] in "اوي":
            return [w[:i] + w[i + 1:]]
        return [w[:i] + rng.choice("اوي") + w[i:]]
    if kind < 0.9 and len(w) >= 5:  # split in two
        i = rng.randrange(2, len(w) - 1)
        return [w[:i], w[i:]]
    i = rng.randrange(len(w))  # one letter replaced
    return [w[:i] + rng.choice("بتنملكسر") + w[i + 1:]]


def simulate(surah: int, rng: random.Random, noise: float, all_words: list[str]):
    q = get_quran()
    hyp: list[HypWord] = []
    truth: dict[tuple[int, int, int], str] = {}  # (ayah, idx) -> expected status
    noisy: set[tuple[int, int, int]] = set()
    planted_ins = 0
    recent: list[str] = []
    for a in range(1, q.ayah_count(surah) + 1):
        for w in q.words(surah, a):
            key = (surah, a, w.index)
            r = rng.random()
            if r < 0.015:
                truth[key] = "deletion"
                continue
            if r < 0.03:
                truth[key] = "substitution"
                cand = rng.choice(all_words)
                while skeleton(cand) == skeleton(w.imlaei) or len(skeleton(cand)) < 3:
                    cand = rng.choice(all_words)
                hyp.append(HypWord(cand, prob=0.9))
                recent.append(cand)
                continue
            truth[key] = "match"
            parts = w.imlaei.split()
            prob = 0.9
            if rng.random() < noise:
                noisy.add(key)
                parts = misspell(w.imlaei, rng) if len(parts) == 1 else parts
                prob = rng.choice([0.9, 0.5, 0.3])
            hyp += [HypWord(p, prob=prob) for p in parts]
            recent += parts
            if rng.random() < 0.02 and len(recent) >= 3:  # repeat previous words: not a mistake
                hyp += [HypWord(p, prob=0.9) for p in recent[-rng.randint(1, 3):]]
            if rng.random() < 0.01:
                extra = rng.choice(all_words)
                hyp.append(HypWord(extra, prob=0.9))
                planted_ins += 1
    return hyp, truth, noisy, planted_ins


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surahs", default="78-114")
    ap.add_argument("--noise", type=float, default=0.10)
    ap.add_argument("--profiles", default="easy,medium,strict")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    q = get_quran()
    lo, _, hi = args.surahs.partition("-")
    surahs = range(int(lo), int(hi or lo) + 1)
    all_words = [w.imlaei for s in range(1, 115) for a in range(1, q.ayah_count(s) + 1)
                 for w in q.words(s, a) if " " not in w.imlaei]

    print(f"surahs {args.surahs}, ASR misspelling rate {args.noise:.0%}")
    print("profile  recall(skip/wrong)  extra-words found  FP clean words  FP misspelt words  FP overall")
    for prof in args.profiles.split(","):
        rng = random.Random(args.seed)
        tp = mistakes = fp_clean = n_clean = fp_noisy = n_noisy = ins_found = ins_planted = 0
        for s in surahs:
            hyp, truth, noisy, planted_ins = simulate(s, rng, args.noise, all_words)
            tr = RecitationTracker(q, s, 1, get_profile(prof))
            for i in range(0, len(hyp), 2):
                tr.update(hyp[i:i + 2])
            tr.finish()
            for a in range(1, q.ayah_count(s) + 1):
                sts = tr.verse_statuses((s, a))
                for i, st in enumerate(sts):
                    exp = truth[(s, a, i)]
                    flagged = st["status"] in ("substitution", "deletion")
                    if exp == "match":
                        if (s, a, i) in noisy:
                            n_noisy += 1
                            fp_noisy += flagged
                        else:
                            n_clean += 1
                            fp_clean += flagged
                    else:
                        mistakes += 1
                        tp += flagged
                ins_found += tr.verse_summary((s, a))["insertions"]
            ins_planted += planted_ins
        fp_all = (fp_clean + fp_noisy) / max(1, n_clean + n_noisy)
        print(f"{prof:8} {tp / max(1, mistakes):>10.1%}          {ins_found:>4}/{ins_planted:<4}        "
              f"{fp_clean / max(1, n_clean):>6.2%}         {fp_noisy / max(1, n_noisy):>6.1%}          {fp_all:.2%}")


if __name__ == "__main__":
    main()
