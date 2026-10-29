from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

try:  # load .env when present
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v.strip()


def _int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class _Config:
    # ---------- Logging / security ----------
    LOG_LEVEL: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO").upper())
    API_KEY: str = field(default_factory=lambda: _env("API_KEY", ""))
    FRONTEND_ORIGINS: tuple[str, ...] = field(default_factory=lambda: tuple(
        o.strip() for o in _env("FRONTEND_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500").split(",")
        if o.strip()))

    # ---------- Audio ----------
    SAMPLE_RATE: int = field(default_factory=lambda: _int("SAMPLE_RATE", 16000))

    # ---------- Qur'an data ----------
    QURAN_WORDS_PATH: str = field(default_factory=lambda: _env("QURAN_WORDS_PATH", "./data/quran/quran_words.json"))
    METADATA_PATH: str = field(default_factory=lambda: _env("METADATA_PATH", "./data/quran/metadata.json"))
    PAGE_MAP_PATH: str = field(default_factory=lambda: _env("PAGE_MAP_PATH", "./data/quran/madani_page_map.json"))
    PROFILES_PATH: str = field(default_factory=lambda: _env("PROFILES_PATH", ""))

    # ---------- ASR engine ----------
    ASR_ENGINE: str = field(default_factory=lambda: _env("ASR_ENGINE", "faster-whisper").lower())
    MODELS_DIR: str = field(default_factory=lambda: _env("MODELS_DIR", "./models"))
    # faster-whisper: a local directory, or a Hugging Face repo id that is downloaded once into MODELS_DIR.
    WHISPER_MODEL_DIR: str = field(default_factory=lambda: _env("WHISPER_MODEL_DIR", ""))
    WHISPER_MODEL_SIZE: str = field(default_factory=lambda: _env("WHISPER_MODEL_SIZE", "OdyAsh/faster-whisper-base-ar-quran"))
    WHISPER_BEAM_SIZE: int = field(default_factory=lambda: _int("WHISPER_BEAM_SIZE", 1))
    WHISPER_VAD: bool = field(default_factory=lambda: _bool("WHISPER_VAD", True))
    WHISPER_CPU_THREADS: int = field(default_factory=lambda: _int("WHISPER_CPU_THREADS", 4))
    WHISPER_COMPUTE_TYPE: str = field(default_factory=lambda: _env("WHISPER_COMPUTE_TYPE", "int8"))
    WHISPER_DEVICE: str = field(default_factory=lambda: _env("WHISPER_DEVICE", "cpu"))
    # Parallel decodes (one per concurrent reciter). Each needs ~WHISPER_CPU_THREADS cores.
    ASR_WORKERS: int = field(default_factory=lambda: _int("ASR_WORKERS", 1))

    # ---------- Streaming ----------
    # Decode the pending audio every STREAM_STEP_MS (lower = snappier, more CPU).
    STREAM_STEP_MS: int = field(default_factory=lambda: _int("STREAM_STEP_MS", 1000))
    # Audio kept un-committed before it is trimmed at the last stable word.
    STREAM_MAX_BUFFER_S: float = field(default_factory=lambda: _float("STREAM_MAX_BUFFER_S", 12.0))

    @property
    def engine(self) -> str:
        return self.ASR_ENGINE


@lru_cache(maxsize=1)
def get_config() -> _Config:
    return _Config()


CONFIG = get_config()
