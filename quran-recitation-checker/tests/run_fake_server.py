"""
Run the real server with the tone-burst fake ASR, plus a WAV that "recites" a
passage, for driving the browser UI without a model:

    python tests/run_fake_server.py 2:1-2:5 /tmp/recitation.wav [mistakes]

Chrome can then use the WAV as its microphone:
    --use-fake-device-for-media-stream --use-file-for-fake-audio-capture=/tmp/recitation.wav
"""
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


def main():
    span, out = sys.argv[1], sys.argv[2]
    with_mistakes = len(sys.argv) > 3
    from app.quran.text import get_quran
    q = get_quran()
    a, b = span.split("-")
    s1, a1 = map(int, a.split(":"))
    s2, a2 = map(int, b.split(":"))
    words = []
    for s, ay in q.iter_ayat(s1, a1):
        ws = [p for w in q.words(s, ay) for p in w.imlaei.split()]
        if with_mistakes and ay == a1 + 1:
            ws = ws[:1] + ws[2:]            # skip a word
        if with_mistakes and ay == a1 + 2:
            ws[1] = "الكافرين"              # wrong word
        words += ws
        if (s, ay) == (s2, a2):
            break
    vocab = ToneVocab()
    audio = synth(words, vocab)
    audio = np.concatenate([audio, np.zeros(SR * 30, np.float32)])  # Chrome loops the file
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())

    import uvicorn
    import app.asr.registry as registry
    registry._backend = FakeToneBackend(vocab)
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
