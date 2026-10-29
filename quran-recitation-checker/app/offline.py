"""
Check a recorded file with exactly the live pipeline.

The audio is fed in 200 ms chunks and decoded every STREAM_STEP_MS of audio,
just like a live microphone, only faster than real time. Used by
POST /api/check, qa/check_file.py and the QA harness.
"""
from __future__ import annotations

import time

import numpy as np

from app.asr.base import AsrBackend
from app.config import CONFIG
from app.recitation import RecitationSession


def load_audio(path: str) -> np.ndarray:
    """Decode any audio/video file (wav, mp3, m4a, webm, mp4 ...) to float32 mono 16 kHz."""
    import av  # PyAV, installed with faster-whisper

    chunks = []
    with av.open(path) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=CONFIG.SAMPLE_RATE)
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def check_audio(audio: np.ndarray, surah: int, ayah: int, profile: str,
                backend: AsrBackend, session_id: str | None = None,
                step_ms: int | None = None, chunk_ms: int = 200) -> dict:
    step_s = (step_ms or CONFIG.STREAM_STEP_MS) / 1000.0
    rs = RecitationSession(backend, surah, ayah, profile, session_id)
    chunk = int(CONFIG.SAMPLE_RATE * chunk_ms / 1000)
    decode_ms: list[float] = []
    updates = 0
    t0 = time.perf_counter()
    for i in range(0, audio.size, chunk):
        rs.add_audio(audio[i:i + chunk])
        if rs.pending_seconds() >= step_s:
            rs.step()
            updates += 1
            decode_ms.append(rs.decode_ms or 0)
    final = rs.finish()
    wall = time.perf_counter() - t0

    tr = rs.tracker
    verses = []
    for key in sorted(tr.verses):
        if key in tr.touched_verses():
            s = tr.verse_summary(key)
            s["tokens"] = rs.q.display_tokens(*key)
            s["token_statuses"] = tr.verse_statuses(key)
            verses.append(s)
    duration = audio.size / CONFIG.SAMPLE_RATE
    return {
        "start": {"surah": surah, "ayah": ayah},
        "profile": rs.profile.name,
        "verses": verses,
        "transcript": " ".join(w.text for w in rs.stream.committed),
        "ended_at": {"surah": final["surah"], "ayah": final["ayah"]},
        "timing": {
            "audio_seconds": round(duration, 2),
            "processing_seconds": round(wall, 2),
            "real_time_factor": round(wall / duration, 3) if duration else None,
            "decodes": updates,
            "mean_decode_ms": round(float(np.mean(decode_ms)), 1) if decode_ms else None,
            "p95_decode_ms": round(float(np.percentile(decode_ms, 95)), 1) if decode_ms else None,
        },
    }
