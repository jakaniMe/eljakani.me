"""
ASR backend interface.

A backend is a *stateless* transcriber shared by all connections: it receives a
float32 mono 16 kHz buffer and returns words with timestamps (seconds, relative
to the buffer start) and, when available, a confidence in 0..1.

Streaming state (what has been heard, what is stable) lives in
app.asr.streaming.StreamingTranscriber, one per WebSocket connection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class AsrWord:
    text: str
    start: float
    end: float
    prob: float | None = None


class AsrBackend(Protocol):
    name: str

    def transcribe(self, audio: np.ndarray, prompt: str | None = None) -> list[AsrWord]:
        ...
