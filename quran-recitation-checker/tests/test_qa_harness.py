"""The QA harness itself (dataset synthesis + scoring), run with the fake ASR."""
import json
import os
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
os.chdir(ROOT)

from fake_asr import SR, FakeToneBackend, ToneVocab, synth  # noqa: E402


def test_build_and_score(tmp_path, monkeypatch):
    import app.asr.registry as registry
    from app.quran.text import get_quran
    from app.offline import check_audio, load_audio
    from qa import build_dataset, run_qa

    q = get_quran()
    vocab = ToneVocab()
    verses = [(1, 2), (1, 5), (1, 7), (2, 3), (2, 4), (112, 1), (112, 4)]
    words_of = {v: [p for w in q.words(*v) for p in w.imlaei.split()] for v in verses}

    def fake_download(url, dest):
        s, a = int(dest.stem[:3]), int(dest.stem[3:])
        audio = synth(words_of[(s, a)], vocab)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dest), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR)
            w.writeframes((audio * 32767).astype("<i2").tobytes())
        return True

    monkeypatch.setattr(registry, "_backend", FakeToneBackend(vocab))
    monkeypatch.setattr(build_dataset, "download", fake_download)
    monkeypatch.setattr(build_dataset, "pick_verses", lambda n, seed: verses)
    monkeypatch.setattr(sys, "argv", ["x", "--out", str(tmp_path), "--reciters", "Fake"])
    build_dataset.main()

    entries = [json.loads(x) for x in (tmp_path / "manifest.jsonl").read_text().splitlines()]
    variants = {e["variant"] for e in entries}
    assert variants == {"ok", "del", "sub", "ins"}

    backend = registry.get_backend()
    for prof in ("easy", "medium", "strict"):
        rows = [run_qa.score_clip(e, check_audio(load_audio(str(tmp_path / e["audio"])),
                                                 e["surah"], e["ayah"], prof, backend)) for e in entries]
        summ = run_qa.summarise(rows)
        assert summ["recall"] == 1.0, (prof, [r for r in rows if r["detected"] < r["mistakes"]])
        assert summ["type_accuracy"] == 1.0
        assert summ["false_positive_rate"] == 0.0, [r for r in rows if r["fp"]]
