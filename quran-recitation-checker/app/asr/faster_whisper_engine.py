"""
Whisper backend (CTranslate2 via faster-whisper).

Default model: OdyAsh/faster-whisper-base-ar-quran, a CTranslate2 conversion of
tarteel-ai/whisper-base-ar-quran (Whisper base fine-tuned on Qur'an recitation).
Any other CTranslate2 Whisper model (local folder or Hugging Face repo id) can be
configured with WHISPER_MODEL_SIZE / WHISPER_MODEL_DIR.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

import numpy as np

from app.asr.base import AsrWord

logger = logging.getLogger(__name__)


class FasterWhisperBackend:
    name = "faster-whisper"

    def __init__(self, model: str, *, download_root: str, device: str = "cpu",
                 compute_type: str = "int8", cpu_threads: int = 4, num_workers: int = 1,
                 beam_size: int = 1, use_vad: bool = True):
        from faster_whisper import WhisperModel

        self.model_name = model
        self.beam_size = beam_size
        self.use_vad = use_vad
        kwargs = dict(device=device, compute_type=compute_type, cpu_threads=cpu_threads,
                      num_workers=num_workers, download_root=download_root)
        try:
            self._model = WhisperModel(model, **kwargs)
        except Exception as e:
            # A download interrupted half-way leaves a broken cache (the "stuck at
            # loading model" issue reported on M2). Wipe that model's cache once
            # and download again.
            cached = Path(download_root) / f"models--{model.replace('/', '--')}"
            if Path(model).exists() or not cached.exists():
                raise
            logger.warning("Model load failed (%s); clearing %s and re-downloading", e, cached)
            shutil.rmtree(cached, ignore_errors=True)
            self._model = WhisperModel(model, **kwargs)
        logger.info("faster-whisper model ready: %s (%s, %s, threads=%d)",
                    model, device, compute_type, cpu_threads)

    def transcribe(self, audio: np.ndarray, prompt: str | None = None) -> list[AsrWord]:
        if audio.size < 1600:  # < 0.1 s
            return []
        segments, _info = self._model.transcribe(
            audio,
            language="ar",
            task="transcribe",
            beam_size=self.beam_size,
            best_of=1,
            temperature=0.0,
            initial_prompt=prompt or None,
            condition_on_previous_text=False,
            word_timestamps=True,
            vad_filter=self.use_vad,
            vad_parameters=dict(threshold=0.5, min_speech_duration_ms=200,
                                min_silence_duration_ms=600, speech_pad_ms=300),
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            hallucination_silence_threshold=2.0,
        )
        words: list[AsrWord] = []
        for seg in segments:
            for w in seg.words or []:
                text = w.word.strip()
                if text:
                    words.append(AsrWord(text, float(w.start), float(w.end), float(w.probability)))
        return words
