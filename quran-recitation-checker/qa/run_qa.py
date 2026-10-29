"""
Run the QA set through the live pipeline and report precision/recall.

  python qa/run_qa.py                       # all profiles, qa/data/manifest.jsonl
  python qa/run_qa.py --profiles medium --limit 40

Metrics (per profile)
  recall            planted mistakes that were reported at the right word
                    (deletion/substitution: that word is flagged; insertion: an extra
                    word is reported in that verse)
  type accuracy     ... and with the right type (deleted vs wrong word)
  false positives   correct words reported as wrong or skipped, over all correct words
  fp (not adjacent) same, ignoring the two words next to a planted edit (the cut
                    itself can clip them)
  clean verses      correct recitations with no flag at all
  decode ms         mean / p95 time per decode step; live needs < STREAM_STEP_MS

Writes qa/reports/qa_report.md and qa/reports/qa_report.json.
Targets from the project scope: recall >= 85 %, false positives <= 10 %.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TARGET_RECALL = 0.85
TARGET_FP = 0.10
FLAGS = ("substitution", "deletion")


def score_clip(entry: dict, result: dict) -> dict:
    s, a = entry["surah"], entry["ayah"]
    v = next((v for v in result["verses"] if (v["surah"], v["ayah"]) == (s, a)), None)
    got = [t["status"] for t in v["token_statuses"]] if v else ["pending"] * len(entry["expected"])
    exp = entry["expected"]
    k = entry.get("edited_word")
    out = {"id": entry["id"], "variant": entry["variant"], "got": got,
           "correct_words": 0, "fp": 0, "correct_words_far": 0, "fp_far": 0,
           "mistakes": 0, "detected": 0, "typed": 0,
           "accuracy": v["accuracy"] if v else 0.0, "heard": v["heard"] if v else ""}
    for i, (e, g) in enumerate(zip(exp, got)):
        if e == "match":
            out["correct_words"] += 1
            bad = g in FLAGS
            out["fp"] += bad
            if k is None or abs(i - k) > 1:
                out["correct_words_far"] += 1
                out["fp_far"] += bad
        else:
            out["mistakes"] += 1
            out["detected"] += g in FLAGS
            out["typed"] += g == e
    if entry.get("expected_insertions"):
        out["mistakes"] += 1
        found = bool(v) and v["insertions"] >= 1
        out["detected"] += found
        out["typed"] += found
    return out


def summarise(rows: list[dict]) -> dict:
    def tot(key):
        return sum(r[key] for r in rows)
    clean = [r for r in rows if r["variant"].startswith("ok") or r["variant"] == "user"]
    by_variant = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["mistakes"]:
            by_variant[r["variant"]][0] += r["detected"]
            by_variant[r["variant"]][1] += r["mistakes"]
    return {
        "clips": len(rows),
        "recall": tot("detected") / tot("mistakes") if tot("mistakes") else None,
        "type_accuracy": tot("typed") / tot("mistakes") if tot("mistakes") else None,
        "false_positive_rate": tot("fp") / tot("correct_words") if tot("correct_words") else None,
        "false_positive_rate_not_adjacent": tot("fp_far") / tot("correct_words_far") if tot("correct_words_far") else None,
        "clean_verses_without_flags": (sum(r["fp"] == 0 for r in clean) / len(clean)) if clean else None,
        "recall_by_variant": {k: d / n for k, (d, n) in sorted(by_variant.items())},
        "mistakes": tot("mistakes"), "correct_words": tot("correct_words"),
    }


def pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(ROOT / "qa" / "data" / "manifest.jsonl"))
    ap.add_argument("--profiles", default="easy,medium,strict")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "qa" / "reports"))
    args = ap.parse_args()

    from app.asr.registry import get_backend, status
    from app.config import CONFIG
    from app.offline import check_audio, load_audio

    mpath = Path(args.manifest)
    entries = [json.loads(line) for line in mpath.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        entries = entries[:args.limit]
    backend = get_backend()
    report = {"model": status()["model"], "engine": status()["engine"],
              "step_ms": CONFIG.STREAM_STEP_MS, "date": time.strftime("%Y-%m-%d %H:%M"),
              "profiles": {}}
    audio_cache = {}
    decode_ms: list[float] = []
    repeat_diffs: list[float] = []

    for prof in args.profiles.split(","):
        rows = []
        for n, e in enumerate(entries, 1):
            path = mpath.parent / e["audio"]
            if path not in audio_cache:
                audio_cache[path] = load_audio(str(path))
            res = check_audio(audio_cache[path], e["surah"], e["ayah"], prof, backend)
            if res["timing"]["mean_decode_ms"] is not None:
                decode_ms.append(res["timing"]["mean_decode_ms"])
            row = score_clip(e, res)
            rows.append(row)
            if prof == "medium" and e["variant"] == "ok" and len(repeat_diffs) < 10:
                again = score_clip(e, check_audio(audio_cache[path], e["surah"], e["ayah"], prof, backend))
                repeat_diffs.append(abs(again["accuracy"] - row["accuracy"]))
            flag = "" if row["fp"] == 0 and row["detected"] == row["mistakes"] else "  <--"
            print(f"[{prof}] {n}/{len(entries)} {e['id']}: {' '.join(g[0] for g in row['got'])}{flag}")
        summ = summarise(rows)
        report["profiles"][prof] = {"summary": summ, "clips": rows}
        print(f"[{prof}] recall {pct(summ['recall'])}  false positives {pct(summ['false_positive_rate'])}")

    report["decode_ms_mean"] = round(float(np.mean(decode_ms)), 1) if decode_ms else None
    report["repeatability_max_diff"] = max(repeat_diffs) if repeat_diffs else None

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "qa_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [
        "# QA report", "",
        f"- Date: {report['date']}",
        f"- ASR: {report['engine']} / `{report['model']}`, decode step {report['step_ms']} ms, "
        f"mean decode {report['decode_ms_mean']} ms",
        f"- Clips: {len(entries)} (manifest `{mpath}`)",
        f"- Repeatability (same clip twice, max accuracy difference): {pct(report['repeatability_max_diff'])}",
        "", f"Targets: recall >= {pct(TARGET_RECALL)}, false positives <= {pct(TARGET_FP)}", "",
        "| Profile | Recall | Right type | False positives | FP (not next to edit) | Clean verses with no flag | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for prof, data in report["profiles"].items():
        s = data["summary"]
        ok = (s["recall"] is None or s["recall"] >= TARGET_RECALL) and \
             (s["false_positive_rate"] is None or s["false_positive_rate"] <= TARGET_FP)
        lines.append(f"| {prof} | {pct(s['recall'])} | {pct(s['type_accuracy'])} | {pct(s['false_positive_rate'])} | "
                     f"{pct(s['false_positive_rate_not_adjacent'])} | {pct(s['clean_verses_without_flags'])} | "
                     f"{'PASS' if ok else 'FAIL'} |")
    lines += ["", "Recall by planted mistake type:", ""]
    for prof, data in report["profiles"].items():
        rv = ", ".join(f"{k}: {pct(v)}" for k, v in data["summary"]["recall_by_variant"].items())
        lines.append(f"- {prof}: {rv}")
    (out / "qa_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
