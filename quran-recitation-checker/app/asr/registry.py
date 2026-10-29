"""
Loads the configured ASR backend once (in the background at startup) and
exposes its state for /health and the WebSocket handshake.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import threading
import time

from app.asr.base import AsrBackend
from app.config import CONFIG

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_backend: AsrBackend | None = None
_error: str | None = None
_loading = False
_load_seconds: float | None = None

# Decodes run here so the event loop never blocks on the model.
EXECUTOR = cf.ThreadPoolExecutor(max_workers=max(1, CONFIG.ASR_WORKERS), thread_name_prefix="asr")


def _create() -> AsrBackend:
    engine = CONFIG.engine
    if engine == "faster-whisper":
        from app.asr.faster_whisper_engine import FasterWhisperBackend
        return FasterWhisperBackend(
            CONFIG.WHISPER_MODEL_DIR or CONFIG.WHISPER_MODEL_SIZE,
            download_root=CONFIG.MODELS_DIR,
            device=CONFIG.WHISPER_DEVICE,
            compute_type=CONFIG.WHISPER_COMPUTE_TYPE,
            cpu_threads=CONFIG.WHISPER_CPU_THREADS,
            num_workers=max(1, CONFIG.ASR_WORKERS),
            beam_size=CONFIG.WHISPER_BEAM_SIZE,
            use_vad=CONFIG.WHISPER_VAD,
        )
    raise RuntimeError(f"Unknown ASR_ENGINE '{engine}' (supported: faster-whisper)")


def get_backend() -> AsrBackend:
    """Return the backend, loading it on first use (blocking)."""
    global _backend, _error, _loading, _load_seconds
    with _lock:
        if _backend is not None:
            return _backend
        _loading, _error = True, None
        t0 = time.time()
        try:
            _backend = _create()
            _load_seconds = round(time.time() - t0, 1)
            return _backend
        except Exception as e:
            _error = f"{type(e).__name__}: {e}"
            logger.exception("ASR engine failed to load")
            raise
        finally:
            _loading = False


def preload_in_background() -> None:
    def run():
        try:
            get_backend()
        except Exception:
            pass
    threading.Thread(target=run, name="asr-preload", daemon=True).start()


def status() -> dict:
    return {
        "engine": CONFIG.engine,
        "model": CONFIG.WHISPER_MODEL_DIR or CONFIG.WHISPER_MODEL_SIZE,
        "ready": _backend is not None,
        "loading": _loading,
        "error": _error,
        "load_seconds": _load_seconds,
    }
