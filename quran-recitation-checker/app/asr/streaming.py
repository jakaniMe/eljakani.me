"""
Streaming on top of a non-streaming ASR model ("LocalAgreement-2", as in
Macháček et al., "Turning Whisper into Real-Time Transcription System", 2023).

Every step the whole *uncommitted* audio buffer is transcribed again. A word is
committed (final) once two consecutive decodes agree on it. Committed audio is
then trimmed from the buffer, so the buffer stays short, but - unlike M2's
10-second sliding window - nothing that was said is ever forgotten: committed
words are kept and handed to the tracker exactly once.
"""
from __future__ import annotations

import logging
import threading

import numpy as np

from app.asr.base import AsrBackend, AsrWord
from app.quran.normalize import skeleton

logger = logging.getLogger(__name__)


def _same(a: AsrWord, b: AsrWord) -> bool:
    return skeleton(a.text) == skeleton(b.text)


class StreamingTranscriber:
    def __init__(self, backend: AsrBackend, sample_rate: int = 16000,
                 max_buffer_s: float = 12.0, hard_limit_s: float = 25.0, prompt_words: int = 20):
        self.backend = backend
        self.sr = sample_rate
        self.max_buffer_s = max_buffer_s
        self.hard_limit_s = hard_limit_s  # Whisper cannot look at more than 30 s
        self.prompt_words = prompt_words
        self._lock = threading.Lock()
        self._audio = np.zeros(0, dtype=np.float32)
        self._offset = 0.0           # absolute time (s) of _audio[0]
        self._received = 0           # samples received in total
        self._decoded_upto = 0       # value of _received at the last decode
        self.committed: list[AsrWord] = []
        self.tentative: list[AsrWord] = []
        self._last_end = 0.0         # absolute end time of the last committed word

    # --------------------------------------------------------------- input
    def add_pcm16(self, data: bytes) -> None:
        if len(data) % 2:
            data = data[:-1]
        x = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
        self.add_audio(x)

    def add_audio(self, x: np.ndarray) -> None:
        with self._lock:
            self._audio = np.concatenate([self._audio, x.astype(np.float32, copy=False)])
            self._received += x.size

    @property
    def now(self) -> float:
        return self._received / self.sr

    def pending_seconds(self) -> float:
        return (self._received - self._decoded_upto) / self.sr

    # ------------------------------------------------------------- decoding
    def process(self) -> tuple[list[AsrWord], list[AsrWord]]:
        """Decode the buffer. Returns (newly committed words, tentative words)."""
        with self._lock:
            audio, offset = self._audio.copy(), self._offset
            self._decoded_upto = self._received
        words = self._decode(audio, offset)

        # LocalAgreement-2: commit the prefix both decodes agree on.
        commit: list[AsrWord] = []
        for new, old in zip(words, self.tentative):
            if not _same(new, old):
                break
            commit.append(new)
        self.tentative = words[len(commit):]
        self._commit(commit)
        forced = self._trim()
        return commit + forced, list(self.tentative)

    def finish(self) -> list[AsrWord]:
        """End of stream: everything still pending becomes final."""
        with self._lock:
            audio, offset = self._audio.copy(), self._offset
            self._decoded_upto = self._received
        words = self._decode(audio, offset) if audio.size else []
        if not words:
            words = self.tentative
        self.tentative = []
        self._commit(words)
        with self._lock:
            self._audio = np.zeros(0, dtype=np.float32)
            self._offset = self.now
        return words

    def commit_tentative(self) -> list[AsrWord]:
        """Accept the pending words as they are (used when the reader navigates away)."""
        words, self.tentative = self.tentative, []
        self._commit(words)
        return words

    def _decode(self, audio: np.ndarray, offset: float) -> list[AsrWord]:
        prompt = " ".join(w.text for w in self.committed[-self.prompt_words:]) or None
        raw = self.backend.transcribe(audio, prompt)
        words = [AsrWord(w.text, w.start + offset, w.end + offset, w.prob) for w in raw]
        # Drop what was already committed (the buffer may still start inside it).
        words = [w for w in words if w.end > self._last_end + 0.05]
        # The model may repeat the last committed words at the buffer start.
        tail = self.committed[-5:]
        for n in range(min(len(tail), len(words)), 0, -1):
            if words[0].start - self._last_end < 1.0 and all(
                    _same(a, b) for a, b in zip(tail[-n:], words[:n])):
                words = words[n:]
                break
        return words

    def _commit(self, words: list[AsrWord]) -> None:
        if words:
            self.committed.extend(words)
            self._last_end = max(self._last_end, words[-1].end)

    def _trim(self) -> list[AsrWord]:
        """Drop committed audio from the buffer. Returns words committed by force."""
        forced: list[AsrWord] = []
        with self._lock:
            length = self._audio.size / self.sr
            if length <= self.max_buffer_s:
                return forced
            if self.tentative:
                cut_time = min(self._last_end, self.tentative[0].start)
            else:  # nothing pending: keep only a little context
                cut_time = max(self._last_end, self.now - 1.0)
            if length > self.hard_limit_s and cut_time - self._offset < length - self.hard_limit_s:
                # No agreement for a long time (noise, mumbling): force progress.
                cut_time = self.now - self.max_buffer_s
                forced = [w for w in self.tentative if w.end <= cut_time]
                if forced:
                    self.tentative = self.tentative[len(forced):]
                    self.committed.extend(forced)
                    self._last_end = forced[-1].end
            cut = int((cut_time - self._offset) * self.sr)
            if cut > 0:
                self._audio = self._audio[cut:]
                self._offset += cut / self.sr
        return forced
