"""
Sensitivity profiles (Easy / Medium / Strict).

All three profiles check whole words (wrong / skipped / extra). They differ in
how much ASR uncertainty is forgiven before a word is reported as wrong.

Values can be overridden without touching code by pointing PROFILES_PATH to a
JSON file of the same shape, e.g. {"medium": {"match_threshold": 0.7}}.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Profile:
    name: str
    # Skeleton similarity (0..1) at or above which a word counts as correct.
    match_threshold: float
    # A word the ASR itself was unsure about (probability < low_confidence) is
    # still accepted when similarity >= uncertain_threshold. Set
    # uncertain_threshold > 1 to disable this benefit of the doubt.
    uncertain_threshold: float
    low_confidence: float
    # Repeating words you already said (going back to re-read) is normal in
    # hifz practice; when False it is not counted as a mistake.
    count_repeats: bool
    # Weight of an extra (inserted) word in the accuracy score.
    insertion_penalty: float


DEFAULT_PROFILES: dict[str, Profile] = {
    "easy": Profile("easy", match_threshold=0.60, uncertain_threshold=0.34,
                    low_confidence=0.60, count_repeats=False, insertion_penalty=0.0),
    "medium": Profile("medium", match_threshold=0.75, uncertain_threshold=0.50,
                      low_confidence=0.45, count_repeats=False, insertion_penalty=0.25),
    "strict": Profile("strict", match_threshold=0.88, uncertain_threshold=2.0,
                      low_confidence=0.0, count_repeats=False, insertion_penalty=0.5),
}

_profiles: dict[str, Profile] = dict(DEFAULT_PROFILES)


def load_overrides(path: str | None) -> None:
    if not path:
        return
    p = Path(path)
    if not p.exists():
        logger.warning("PROFILES_PATH %s not found, using defaults", path)
        return
    data = json.loads(p.read_text(encoding="utf-8"))
    for name, values in data.items():
        base = _profiles.get(name, DEFAULT_PROFILES["medium"])
        _profiles[name] = replace(base, name=name, **values)
    logger.info("Loaded profile overrides for: %s", ", ".join(data))


def get_profile(name: str | None) -> Profile:
    return _profiles.get((name or "medium").lower(), _profiles["medium"])


def all_profiles() -> dict[str, Profile]:
    return dict(_profiles)
