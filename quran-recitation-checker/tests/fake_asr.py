"""
A deterministic stand-in for the ASR model, for tests without model downloads.

Words are "spoken" as tone bursts: word k of the vocabulary is a 0.3 s sine at
300 + 25*k Hz. FakeToneBackend finds the bursts in whatever buffer it is given
and returns the words with timestamps relative to that buffer, like Whisper.
A burst cut off by the end of the buffer is returned with a wrong-ish guess and
low probability, so the LocalAgreement logic is exercised for real.
"""
from __future__ import annotations

import numpy as np

from app.asr.base import AsrWord

SR = 16000
BURST = 0.30
GAP = 0.15


class ToneVocab:
    def __init__(self):
        self.words: list[str] = []
        self.index: dict[str, int] = {}

    def id(self, w: str) -> int:
        if w not in self.index:
            self.index[w] = len(self.words)
            self.words.append(w)
        return self.index[w]

    def freq(self, k: int) -> float:
        return 300.0 + 25.0 * k


def synth(words: list[str], vocab: ToneVocab, pause_after: dict[int, float] | None = None) -> np.ndarray:
    pause_after = pause_after or {}
    t = np.arange(int(BURST * SR)) / SR
    env = np.minimum(1.0, np.minimum(t, BURST - t) / 0.02)
    parts = [np.zeros(int(0.3 * SR), np.float32)]
    for i, w in enumerate(words):
        f = vocab.freq(vocab.id(w))
        parts.append((0.3 * env * np.sin(2 * np.pi * f * t)).astype(np.float32))
        parts.append(np.zeros(int((GAP + pause_after.get(i, 0.0)) * SR), np.float32))
    parts.append(np.zeros(int(0.5 * SR), np.float32))
    return np.concatenate(parts)


class FakeToneBackend:
    name = "fake-tone"

    def __init__(self, vocab: ToneVocab):
        self.vocab = vocab
        self.calls = 0

    def transcribe(self, audio: np.ndarray, prompt: str | None = None) -> list[AsrWord]:
        self.calls += 1
        hop = 160  # 10 ms frames
        n = audio.size // hop
        if n == 0:
            return []
        energy = np.sqrt((audio[:n * hop].reshape(n, hop) ** 2).mean(axis=1))
        voiced = energy > 0.02
        words: list[AsrWord] = []
        i = 0
        while i < n:
            if not voiced[i]:
                i += 1
                continue
            j = i
            while j < n and voiced[j]:
                j += 1
            seg = audio[i * hop:j * hop]
            dur = seg.size / SR
            spec = np.abs(np.fft.rfft(seg * np.hanning(seg.size)))
            f = np.argmax(spec) * SR / seg.size
            k = int(round((f - 300.0) / 25.0))
            complete = dur >= BURST * 0.8 or j < n
            if 0 <= k < len(self.vocab.words):
                if complete:
                    words.append(AsrWord(self.vocab.words[k], i * hop / SR, j * hop / SR, 0.95))
                else:  # truncated by the buffer end: unreliable guess
                    guess = self.vocab.words[(k + 1) % len(self.vocab.words)]
                    words.append(AsrWord(guess, i * hop / SR, j * hop / SR, 0.3))
            i = j
        return words
