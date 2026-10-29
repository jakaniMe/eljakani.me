"""
Build the QA set: real recitations + recitations with planted mistakes.

1. Downloads verse recordings from EveryAyah (several reciters).
2. Finds each word's time span by running the checker itself on the clean clip
   (only clips where every word is recognised are used as a base).
3. Writes, per clip, the original plus variants with one planted mistake:
     del  - one word cut out                      -> that word must be "deletion"
     sub  - one word replaced by a word from another verse -> "substitution"
     ins  - a word from another verse inserted   -> one extra word
   and optionally noisy copies (--noise-snr).
4. Writes qa/data/manifest.jsonl, read by qa/run_qa.py.

Usage
  python qa/build_dataset.py                       # defaults: 50+ ayat, 2 reciters
  python qa/build_dataset.py --reciters Alafasy_128kbps,Husary_128kbps,Minshawy_Murattal_128kbps \\
                             --random 60 --noise-snr 20

Your own recordings can be added to the manifest by hand, one JSON per line:
  {"id": "me-2-1", "audio": "path.wav", "surah": 2, "ayah": 1, "variant": "user",
   "expected": ["match", ...], "expected_insertions": 0}
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.request
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import CONFIG  # noqa: E402
from app.quran.matching import similarity  # noqa: E402
from app.quran.text import get_quran  # noqa: E402

SR = CONFIG.SAMPLE_RATE
EVERYAYAH = "https://everyayah.com/data/{reciter}/{surah:03d}{ayah:03d}.mp3"
DEFAULT_RECITERS = "Alafasy_128kbps,Husary_128kbps"


def pick_verses(n_random: int, seed: int) -> list[tuple[int, int]]:
    """Al-Fatiha, Al-Baqarah 1-5, and random ayat from Juz' 'Amma and the rest of the Qur'an."""
    q = get_quran()
    fixed = [(1, a) for a in range(1, 8)] + [(2, a) for a in range(1, 6)]
    rng = random.Random(seed)
    amma = [(s, a) for s in range(78, 115) for a in range(1, q.ayah_count(s) + 1)]
    rest = [(s, a) for s in range(2, 78) for a in range(1, q.ayah_count(s) + 1)
            if 4 <= len(q.words(s, a)) <= 30]
    picked = rng.sample(amma, n_random // 2) + rng.sample(rest, n_random - n_random // 2)
    return sorted(set(fixed + picked))


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            dest.write_bytes(r.read())
        return True
    except Exception as e:
        print(f"  ! {url}: {e}")
        return False


def write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def word_spans(audio, surah, ayah, backend):
    """[(start, end), ...] for each word of the verse, or None if not all recognised."""
    from app.offline import check_audio
    res = check_audio(audio, surah, ayah, "strict", backend)
    v = next((v for v in res["verses"] if (v["surah"], v["ayah"]) == (surah, ayah)), None)
    if not v or any(t["status"] != "match" or t.get("start") is None for t in v["token_statuses"]):
        return None
    return [(t["start"], t["end"]) for t in v["token_statuses"]]


def snap(audio: np.ndarray, t: float, radius: float = 0.06) -> int:
    """Sample index of the quietest 10 ms frame near time t (a clean cut point)."""
    hop = SR // 100
    lo = max(0, int((t - radius) * SR))
    hi = min(audio.size - hop, int((t + radius) * SR))
    if hi <= lo:
        return int(t * SR)
    frames = [(float(np.mean(audio[i:i + hop] ** 2)), i) for i in range(lo, hi, hop // 2)]
    return min(frames)[1] + hop // 2


def boundaries(audio, spans):
    """Cut points between words: before word 0, between i and i+1, after the last word."""
    cuts = [snap(audio, max(0.0, spans[0][0] - 0.05))]
    for (_, e), (s, _) in zip(spans, spans[1:]):
        cuts.append(snap(audio, (e + s) / 2))
    cuts.append(snap(audio, spans[-1][1] + 0.05))
    return cuts


def add_noise(audio: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    p = float(np.mean(audio ** 2)) or 1e-8
    noise = rng.standard_normal(audio.size).astype(np.float32)
    # pinkish: smooth white noise a little
    noise = np.convolve(noise, np.ones(4) / 4, mode="same")
    noise *= np.sqrt(p / (10 ** (snr_db / 10)) / (float(np.mean(noise ** 2)) or 1e-8))
    return (audio + noise).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "qa" / "data"))
    ap.add_argument("--reciters", default=DEFAULT_RECITERS)
    ap.add_argument("--random", type=int, default=40, help="random ayat on top of Al-Fatiha + Al-Baqarah 1-5")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--noise-snr", type=float, default=None, help="also write noisy copies at this SNR (dB)")
    args = ap.parse_args()

    from app.asr.registry import get_backend
    from app.offline import load_audio

    q = get_quran()
    out = Path(args.out)
    verses = pick_verses(args.random, args.seed)
    print(f"{len(verses)} ayat from {len({s for s, _ in verses})} surahs")
    backend = get_backend()
    rng = random.Random(args.seed)
    nrng = np.random.default_rng(args.seed)
    manifest = []

    for reciter in args.reciters.split(","):
        clips = []  # (surah, ayah, audio, spans)
        for s, a in verses:
            mp3 = out / "mp3" / reciter / f"{s:03d}{a:03d}.mp3"
            if not download(EVERYAYAH.format(reciter=reciter, surah=s, ayah=a), mp3):
                continue
            audio = load_audio(str(mp3))
            spans = word_spans(audio, s, a, backend)
            if spans is None:
                print(f"  {reciter} {s}:{a}: not every word recognised on the clean clip; used as 'ok' only")
            clips.append((s, a, audio, spans))
        print(f"{reciter}: {len(clips)} clips, {sum(c[3] is not None for c in clips)} usable for planted mistakes")

        # Donor words (from other verses of the same reciter) for substitutions/insertions.
        cuts_of = {(s, a): (audio, boundaries(audio, spans)) for s, a, audio, spans in clips if spans}
        donors = [(s, a, i) for (s, a), (_au, cuts) in cuts_of.items() for i in range(len(cuts) - 1)]

        for s, a, audio, spans in clips:
            words = q.words(s, a)
            n = len(words)
            base_id = f"{reciter}-{s}-{a}"
            entries = [("ok", audio, ["match"] * n, 0)]
            if spans and n >= 4:
                cuts = cuts_of[(s, a)][1]
                cands = [k for k in range(1, n - 1) if len(words[k].forms[0]) >= 3] or list(range(1, n - 1))
                k = rng.choice(cands)
                # deletion
                exp = ["match"] * n
                exp[k] = "deletion"
                entries.append(("del", np.concatenate([audio[:cuts[k]], audio[cuts[k + 1]:]]), exp, 0))
                # donor word that sounds clearly different from the target and its neighbours
                pool = [(ds, da, di) for ds, da, di in donors if (ds, da) != (s, a)
                        and len(q.words(ds, da)[di].forms[0]) >= 3
                        and all(similarity(q.words(ds, da)[di].forms[0], words[j].forms[0]) < 0.5
                                for j in range(max(0, k - 1), min(n, k + 2)))]
                if pool:
                    ds, da, di = rng.choice(pool)
                    daudio, dcuts = cuts_of[(ds, da)]
                    seg = daudio[dcuts[di]:dcuts[di + 1]]
                    exp = ["match"] * n
                    exp[k] = "substitution"
                    entries.append(("sub", np.concatenate([audio[:cuts[k]], seg, audio[cuts[k + 1]:]]), exp, 0))
                    gap = np.zeros(int(0.08 * SR), np.float32)
                    entries.append(("ins", np.concatenate([audio[:cuts[k + 1]], gap, seg, gap, audio[cuts[k + 1]:]]),
                                    ["match"] * n, 1))
            for variant, au, exp, ins in entries:
                versions = [("", au)]
                if args.noise_snr is not None:
                    versions.append((f"-snr{int(args.noise_snr)}", add_noise(au, args.noise_snr, nrng)))
                for suffix, au2 in versions:
                    cid = f"{base_id}-{variant}{suffix}"
                    path = out / "clips" / f"{cid}.wav"
                    write_wav(path, au2)
                    manifest.append({"id": cid, "audio": str(path.relative_to(out)), "reciter": reciter,
                                     "surah": s, "ayah": a, "variant": variant + suffix,
                                     "edited_word": next((i for i, e in enumerate(exp) if e != "match"),
                                                         None) if variant != "ins" else None,
                                     "expected": exp, "expected_insertions": ins})

    mf = out / "manifest.jsonl"
    mf.write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in manifest) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for m in manifest:
        counts[m["variant"]] = counts.get(m["variant"], 0) + 1
    print(f"wrote {mf}: {len(manifest)} clips {counts}")


if __name__ == "__main__":
    main()
